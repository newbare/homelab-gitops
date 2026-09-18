import os
import sys


def _env(key, required=True, default=None):
    value = os.environ.get(key, default)
    if required and not value:
        print(f"[X] Variável de ambiente obrigatória não definida: {key}", file=sys.stderr)
        sys.exit(1)
    return value


def load():
    return {
        "url": _env("KEYCLOAK_URL").rstrip("/"),
        "admin_user": _env("KEYCLOAK_ADMIN_USER"),
        "admin_pass": _env("KEYCLOAK_ADMIN_PASS"),
        "realm": _env("KEYCLOAK_REALM"),
        "client_id": _env("KEYCLOAK_CLIENT_ID"),
        "client_secret": _env("KEYCLOAK_CLIENT_SECRET"),
        "redirect_uri": _env("KEYCLOAK_REDIRECT_URI"),
        "web_origin": _env("KEYCLOAK_WEB_ORIGIN"),
        "temp_password": _env("KEYCLOAK_TEMP_PASSWORD"),
    }
