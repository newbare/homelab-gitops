import logging

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger("provisioner")


class RetryableHTTPError(Exception):
    pass


class KeycloakClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=retry_if_exception_type(
            (RetryableHTTPError, requests.ConnectionError, requests.Timeout)
        ),
        reraise=True,
    )
    def _request(self, method, url, token=None, **kwargs):
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        r = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        if r.status_code in (429, 500, 502, 503, 504):
            raise RetryableHTTPError(f"{r.status_code} em {url}")
        return r

    def authenticate(self):
        url = f"{self.cfg['url']}/realms/master/protocol/openid-connect/token"
        r = self._request("POST", url, data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": self.cfg["admin_user"],
            "password": self.cfg["admin_pass"],
        })
        r.raise_for_status()
        self.token = r.json()["access_token"]
        return self.token

    def ensure_realm(self):
        url = f"{self.cfg['url']}/admin/realms"
        payload = {
            "realm": self.cfg["realm"],
            "enabled": True,
            "loginWithEmailAllowed": True,
            "duplicateEmailsAllowed": False,
            "resetPasswordAllowed": True,
            "editUsernameAllowed": False,
        }
        r = self._request("POST", url, token=self.token, json=payload)
        if r.status_code == 409:
            log.info(f"Realm '{self.cfg['realm']}' já existe.")
            return
        r.raise_for_status()
        log.info(f"Realm '{self.cfg['realm']}' criado.")

    def get_client_by_client_id(self, client_id):
        url = f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/clients"
        r = self._request("GET", url, token=self.token,
                          params={"clientId": client_id})
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    def ensure_client(self):
        url = f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/clients"
        payload = {
            "clientId": self.cfg["client_id"],
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "secret": self.cfg["client_secret"],
            "redirectUris": [self.cfg["redirect_uri"]],
            "webOrigins": [self.cfg["web_origin"]],
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": True,
        }

        existing = self.get_client_by_client_id(self.cfg["client_id"])
        if existing:
            r = self._request("PUT", f"{url}/{existing['id']}",
                              token=self.token, json=payload)
            r.raise_for_status()
            log.info(f"Client '{self.cfg['client_id']}' atualizado "
                     f"(redirectUri={self.cfg['redirect_uri']}).")
            return

        r = self._request("POST", url, token=self.token, json=payload)
        r.raise_for_status()
        log.info(f"Client '{self.cfg['client_id']}' criado.")

    def ensure_roles(self, roles):
        url = f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/roles"
        for role in roles:
            r = self._request("POST", url, token=self.token,
                              json={"name": role, "description": f"Role {role}"})
            if r.status_code == 409:
                log.debug(f"Role '{role}' já existe.")
            else:
                r.raise_for_status()
                log.info(f"Role '{role}' criada.")

    def get_user_by_username(self, username):
        url = f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/users"
        r = self._request("GET", url, token=self.token,
                          params={"username": username, "exact": "true"})
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    def upsert_user(self, user):
        username = user["username"].strip()
        payload = {
            "username": username,
            "email": user["email"].strip(),
            "firstName": (user.get("firstName") or "").strip(),
            "lastName": (user.get("lastName") or "").strip(),
            "enabled": True,
            "emailVerified": True,
        }

        existing = self.get_user_by_username(username)
        if existing:
            url = f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/users/{existing['id']}"
            r = self._request("PUT", url, token=self.token, json=payload)
            r.raise_for_status()
            return existing["id"], "updated"

        payload["credentials"] = [{
            "type": "password",
            "value": self.cfg["temp_password"],
            "temporary": True,
        }]
        url = f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/users"
        r = self._request("POST", url, token=self.token, json=payload)
        r.raise_for_status()
        new_user = self.get_user_by_username(username)
        return new_user["id"], "created"

    def assign_role(self, user_id, role_name):
        r = self._request(
            "GET",
            f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/roles/{role_name}",
            token=self.token,
        )
        r.raise_for_status()
        role = r.json()
        url = f"{self.cfg['url']}/admin/realms/{self.cfg['realm']}/users/{user_id}/role-mappings/realm"
        r = self._request("POST", url, token=self.token, json=[role])
        if r.status_code in (204, 409):
            return
        r.raise_for_status()
