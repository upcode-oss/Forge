import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_mock_engine

from app.config import settings
from app.main import app
from app.models import Base


def test_setup_is_authorized_validated_and_locked(client, setup_payload):
    assert client.get("/api/v1/setup/status").json() == {"completed": False}
    assert client.get("/health").status_code == 200
    assert (
        client.post("/api/v1/setup", json={**setup_payload, "setup_token": "wrong"}).status_code
        == 403
    )
    assert (
        client.post("/api/v1/setup", json={**setup_payload, "default_branch": "--evil"}).status_code
        == 422
    )
    assert client.post("/api/v1/setup", json=setup_payload).status_code == 201
    assert client.post("/api/v1/setup", json=setup_payload).status_code == 409
    assert client.get("/api/v1/auth/me").status_code == 401
    stored = json.loads((settings().data_dir / "installation.json").read_text())
    assert "sqlite" not in stored["database"]
    assert (settings().data_dir / "installation.json").stat().st_mode & 0o777 == 0o600
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "safe-admin-password"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").json()["is_admin"]


def test_csrf_and_session_revocation(admin):
    assert admin.post("/api/v1/auth/logout", headers={"X-Forge-Request": ""}).status_code == 403
    assert (
        admin.post(
            "/api/v1/auth/logout", headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert admin.post("/api/v1/auth/logout").status_code == 200
    assert admin.get("/api/v1/auth/me").status_code == 401


def test_repository_git_tree_commit_and_input_validation(admin, repository):
    rid = repository["id"]
    assert admin.get(f"/api/v1/repositories/{rid}/branches").json() == ["main"]
    entries = admin.get(f"/api/v1/repositories/{rid}/tree", params={"ref": "main"}).json()
    assert entries[0]["name"] == "README.md"
    assert (
        "# demo"
        in admin.get(
            f"/api/v1/repositories/{rid}/blob", params={"ref": "main", "path": "README.md"}
        ).json()["content"]
    )
    assert (
        admin.get(
            f"/api/v1/repositories/{rid}/tree", params={"ref": "--output=/tmp/evil"}
        ).status_code
        == 422
    )
    assert (
        admin.get(
            f"/api/v1/repositories/{rid}/blob", params={"ref": "main", "path": "../../etc/passwd"}
        ).status_code
        == 409
    )
    commits = admin.get(f"/api/v1/repositories/{rid}/commits", params={"ref": "main"}).json()
    assert commits[0]["subject"] == "Initial commit"
    assert (
        "README.md"
        in admin.get(f"/api/v1/repositories/{rid}/commits/{commits[0]['sha']}").json()["diff"]
    )
    assert admin.post("/api/v1/repositories", json={"name": "demo"}).status_code == 409
    assert admin.post("/api/v1/repositories", json={"name": "../../evil"}).status_code == 422


def test_private_access_membership_issues_and_admin_controls(admin, repository):
    rid = repository["id"]
    result = admin.post(
        "/api/v1/users",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "display_name": "Alice",
            "password": "alice-password-long",
        },
    )
    assert result.status_code == 201
    alice_id = result.json()["id"]
    alice = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        assert (
            alice.post(
                "/api/v1/auth/login", json={"username": "alice", "password": "alice-password-long"}
            ).status_code
            == 200
        )
        assert alice.get("/api/v1/repositories").json() == []
        assert alice.get(f"/api/v1/repositories/{rid}").status_code == 404
        assert alice.get("/api/v1/users").status_code == 403
        assert (
            admin.put(
                f"/api/v1/repositories/{rid}/members", json={"username": "alice", "role": "read"}
            ).status_code
            == 200
        )
        assert alice.get(f"/api/v1/repositories/{rid}").status_code == 200
        assert (
            alice.post(
                f"/api/v1/repositories/{rid}/tickets", json={"title": "Not permitted"}
            ).status_code
            == 403
        )
        admin.put(
            f"/api/v1/repositories/{rid}/members", json={"username": "alice", "role": "write"}
        )
        response = alice.post(
            f"/api/v1/repositories/{rid}/tickets",
            json={"title": "Improve README", "body": "Add examples"},
        )
        assert response.status_code == 201
        tid = response.json()["id"]
        assert (
            alice.post(
                f"/api/v1/repositories/{rid}/tickets/{tid}/comments", json={"body": "Working on it"}
            ).status_code
            == 201
        )
        assert (
            alice.get(f"/api/v1/repositories/{rid}/tickets/{tid}").json()["comments"][0]["body"]
            == "Working on it"
        )
        assert (
            alice.put(f"/api/v1/repositories/{rid}/tickets/{tid}/state?state=closed").status_code
            == 200
        )
        assert admin.put(f"/api/v1/users/{alice_id}/active?active=false").status_code == 200
        assert alice.get("/api/v1/auth/me").status_code == 401
    finally:
        alice.close()


def test_tokens_password_and_smtp_secrets(admin):
    raw = admin.post("/api/v1/tokens", json={"name": "Laptop", "scope": "read", "days": 1}).json()[
        "token"
    ]
    listing = admin.get("/api/v1/tokens").json()
    assert raw.startswith("fg_") and "digest" not in listing[0] and "token" not in listing[0]
    assert admin.delete(f"/api/v1/tokens/{listing[0]['id']}").status_code == 200
    assert admin.get("/api/v1/tokens").json() == []
    assert (
        admin.put(
            "/api/v1/instance/smtp",
            json={
                "host": "smtp.example.com",
                "password": "sensitive-smtp-password",
                "from_address": "forge@example.com",
            },
        ).status_code
        == 200
    )
    smtp = admin.get("/api/v1/instance/smtp").json()
    assert smtp["password"] == "" and smtp["has_password"]
    assert (
        admin.post(
            "/api/v1/auth/password",
            json={
                "current_password": "safe-admin-password",
                "new_password": "a-different-password",
            },
        ).status_code
        == 200
    )
    assert admin.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("dialect", ["postgresql+psycopg://", "mysql+pymysql://", "sqlite://"])
def test_schema_compiles_for_supported_databases(dialect):
    statements = []
    engine = create_mock_engine(
        dialect,
        lambda sql, *args, **kwargs: statements.append(str(sql.compile(dialect=engine.dialect))),
    )
    Base.metadata.create_all(engine)
    assert len(statements) == len(Base.metadata.tables) + sum(
        len(table.indexes) for table in Base.metadata.tables.values()
    )
