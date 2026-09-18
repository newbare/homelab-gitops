import csv
from unittest.mock import MagicMock

import pytest

from src import provisioner
from src.keycloak_client import KeycloakClient


@pytest.fixture
def csv_file(tmp_path):
    p = tmp_path / "users.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "email", "firstName", "lastName", "role"])
        writer.writerow(["jefferson.leite", "jefferson@example.com", "Jefferson", "Leite", "resilience-admins"])
        writer.writerow(["maria.silva", "maria@example.com", "Maria", "Silva", "resilience-devs"])
    return p


@pytest.fixture
def client():
    cfg = {
        "url": "http://keycloak.test",
        "admin_user": "admin",
        "admin_pass": "admin",
        "realm": "resilience",
        "client_id": "backstage",
        "client_secret": "secret",
        "redirect_uri": "http://localhost:3000/api/auth/oidc/handler/frame",
        "web_origin": "http://localhost:3000",
        "temp_password": "Mudar@123",
    }
    c = KeycloakClient(cfg)
    c.token = "fake-token"
    return c


class TestLoadUsers:
    def test_load_csv(self, csv_file):
        users = provisioner.load_users(csv_file)
        assert len(users) == 2
        assert users[0]["username"] == "jefferson.leite"
        assert users[0]["role"] == "resilience-admins"

    def test_unsupported_format(self, tmp_path):
        p = tmp_path / "users.txt"
        p.write_text("nada")
        with pytest.raises(ValueError, match="Formato não suportado"):
            provisioner.load_users(p)


class TestUpsertUser:
    def test_create_new_user(self, client):
        client.get_user_by_username = MagicMock(side_effect=[None, {"id": "abc-123"}])
        client._request = MagicMock()
        client._request.return_value.status_code = 201
        client._request.return_value.raise_for_status = MagicMock()

        user = {"username": "novo.user", "email": "novo@example.com",
                "firstName": "Novo", "lastName": "User", "role": "resilience-devs"}
        user_id, action = client.upsert_user(user)
        assert action == "created"
        assert user_id == "abc-123"

    def test_update_existing_user(self, client):
        client.get_user_by_username = MagicMock(return_value={"id": "abc-123"})
        client._request = MagicMock()
        client._request.return_value.status_code = 204
        client._request.return_value.raise_for_status = MagicMock()

        user = {"username": "jefferson.leite", "email": "jefferson@example.com",
                "firstName": "Jefferson", "lastName": "Leite", "role": "resilience-admins"}
        user_id, action = client.upsert_user(user)
        assert action == "updated"
        assert user_id == "abc-123"


class TestRun:
    def test_dry_run_does_not_call_keycloak(self, client):
        users = [{"username": "u1", "role": "r1"}, {"username": "u2", "role": "r2"}]
        client.authenticate = MagicMock()
        client.upsert_user = MagicMock()

        stats = provisioner.run(client, users, dry_run=True)

        client.authenticate.assert_not_called()
        client.upsert_user.assert_not_called()
        assert stats == {"created": 0, "updated": 0, "errors": 0}

    def test_run_counts_created_and_updated(self, client):
        users = [{"username": "u1", "role": "r1"},
                 {"username": "u2", "role": "r1"},
                 {"username": "u3", "role": "r2"}]

        client.authenticate = MagicMock()
        client.ensure_realm = MagicMock()
        client.ensure_client = MagicMock()
        client.ensure_roles = MagicMock()
        client.assign_role = MagicMock()
        client.upsert_user = MagicMock(side_effect=[
            ("id-1", "created"), ("id-2", "created"), ("id-3", "updated"),
        ])

        stats = provisioner.run(client, users, workers=1)
        assert stats["created"] == 2
        assert stats["updated"] == 1
        assert stats["errors"] == 0

    def test_run_counts_errors(self, client):
        users = [{"username": "ok", "role": "r1"}, {"username": "fail", "role": "r1"}]

        client.authenticate = MagicMock()
        client.ensure_realm = MagicMock()
        client.ensure_client = MagicMock()
        client.ensure_roles = MagicMock()
        client.assign_role = MagicMock()
        client.upsert_user = MagicMock(side_effect=[("id-1", "created"), Exception("boom")])

        stats = provisioner.run(client, users, workers=1)
        assert stats["created"] == 1
        assert stats["errors"] == 1
