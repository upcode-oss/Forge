import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import attempts


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FORGE_SECRET_KEY", "test-secret-" + "a" * 40)
    monkeypatch.setenv("FORGE_SETUP_TOKEN", "test-setup-" + "b" * 40)
    monkeypatch.setenv("FORGE_BOOTSTRAP_ORIGIN", "http://testserver")
    monkeypatch.setenv("FORGE_SSH_ENABLED", "false")
    settings.cache_clear()
    attempts.clear()
    with TestClient(app, headers={"X-Forge-Request": "1"}) as result:
        yield result
    settings.cache_clear()


@pytest.fixture
def setup_payload():
    return {
        "name": "Test Forge",
        "public_url": "http://testserver",
        "default_branch": "main",
        "setup_token": "test-setup-" + "b" * 40,
        "database_engine": "sqlite",
        "admin": {
            "username": "admin",
            "email": "admin@example.com",
            "display_name": "Admin",
            "password": "safe-admin-password",
        },
    }


@pytest.fixture
def admin(client, setup_payload):
    assert client.post("/api/v1/setup", json=setup_payload).status_code == 201
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "safe-admin-password"}
        ).status_code
        == 200
    )
    return client


@pytest.fixture
def repository(admin):
    response = admin.post(
        "/api/v1/repositories", json={"name": "demo", "description": "A real Git repository"}
    )
    assert response.status_code == 201, response.text
    return response.json()
