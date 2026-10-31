import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import database, two_factor
from app.main import app
from app.models import User

PATH = "/api/v1/auth/2fa"


@pytest.fixture
def secured_client(admin, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr(two_factor, "time", lambda: clock[0])
    yield admin, "safe-admin-password", clock


def setup_factor(client, password):
    response = client.post(PATH + "/setup", json={"password": password})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["qr_code"].startswith("data:image/svg+xml;base64,")
    return value["secret"]


def enable_factor(client, password, clock):
    secret = setup_factor(client, password)
    response = client.post(
        PATH + "/enable",
        json={"password": password, "code": pyotp.TOTP(secret).at(clock[0])},
    )
    assert response.status_code == 200, response.text
    codes = response.json()["recovery_codes"]
    assert len(codes) == len(set(codes)) == 10
    return secret, codes


def login(client, password, code=None):
    payload = {"username": "admin", "password": password}
    if code is not None:
        payload["two_factor_code"] = code
    return client.post("/api/v1/auth/login", json=payload)


def test_setup_requires_password_and_confirmation(secured_client):
    client, password, clock = secured_client
    assert client.post(PATH + "/setup", json={"password": "wrong"}).status_code == 401
    secret = setup_factor(client, password)
    assert client.get(PATH).json() == {"enabled": False, "recovery_codes_remaining": 0}
    assert login(client, password).status_code == 200
    assert (
        client.post(PATH + "/enable", json={"password": password, "code": "invalid"}).status_code
        == 401
    )
    response = client.post(
        PATH + "/enable", json={"password": password, "code": pyotp.TOTP(secret).at(clock[0])}
    )
    assert response.status_code == 200
    assert client.get(PATH).json()["enabled"] is True
    assert "secret" not in client.get(PATH).json()
    assert client.get(PATH).headers["cache-control"] == "no-store"


def test_password_alone_and_reused_totp_do_not_create_sessions(secured_client):
    client, password, clock = secured_client
    old = TestClient(app, headers={"X-Forge-Request": "1"})
    old.cookies.update(client.cookies)
    old_refresh = client.cookies.get("sprint_refresh")
    secret, _ = enable_factor(client, password, clock)
    assert old.get("/api/v1/auth/me").status_code == 401
    if old_refresh:
        assert old.post("/api/v1/auth/refresh").status_code == 401
    old.close()
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    response = login(client, password)
    assert response.json() == {"two_factor_required": True}
    assert "set-cookie" not in response.headers
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client, password, "invalid").status_code == 401
    assert login(client, password, pyotp.TOTP(secret).at(clock[0])).status_code == 401
    clock[0] += 30
    code = pyotp.TOTP(secret).at(clock[0])
    assert login(client, "wrong-password", code).status_code == 401
    assert login(client, password, code).status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert login(client, password, code).status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_recovery_codes_are_hashed_and_single_use(secured_client):
    client, password, clock = secured_client
    secret, codes = enable_factor(client, password, clock)
    with Session(database.engine) as db:
        user = db.query(User).filter_by(username="admin").one()
        assert secret not in user.mfa_secret_encrypted
        assert all(value not in user.mfa_recovery_hashes for value in codes)
        assert hashlib.sha256(codes[0].replace("-", "").encode()).hexdigest() in json.loads(
            user.mfa_recovery_hashes
        )
    assert not any(key.startswith("mfa_") for key in client.get("/api/v1/auth/me").json())
    client.post("/api/v1/auth/logout")
    assert login(client, password, codes[0].upper()).status_code == 200
    assert client.get(PATH).json()["recovery_codes_remaining"] == 9
    client.post("/api/v1/auth/logout")
    assert login(client, password, codes[0]).status_code == 401
    assert login(client, password, codes[1]).status_code == 200


def test_replacement_and_disable_require_password_and_factor(secured_client):
    client, password, clock = secured_client
    secret, codes = enable_factor(client, password, clock)
    clock[0] += 30
    code = pyotp.TOTP(secret).at(clock[0])
    assert (
        client.post(PATH + "/disable", json={"password": "wrong", "code": code}).status_code == 401
    )
    assert (
        client.post(PATH + "/disable", json={"password": password, "code": "invalid"}).status_code
        == 401
    )
    assert client.get(PATH).json()["enabled"] is True
    response = client.post(PATH + "/recovery-codes", json={"password": password, "code": code})
    assert response.status_code == 200, response.text
    replacement = response.json()["recovery_codes"]
    assert set(replacement).isdisjoint(codes)
    client.post("/api/v1/auth/logout")
    assert login(client, password, codes[0]).status_code == 401
    assert login(client, password, replacement[0]).status_code == 200
    assert (
        client.post(
            PATH + "/disable", json={"password": password, "code": replacement[1]}
        ).status_code
        == 200
    )
    assert client.get(PATH).json() == {"enabled": False, "recovery_codes_remaining": 0}
    client.post("/api/v1/auth/logout")
    assert login(client, password).status_code == 200


def test_account_lockout_survives_new_clients_and_expires(secured_client):
    client, password, clock = secured_client
    secret, _ = enable_factor(client, password, clock)
    client.post("/api/v1/auth/logout")
    for _ in range(5):
        assert login(client, password, "invalid").status_code == 401
    clock[0] += 30
    other = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        assert login(other, password, pyotp.TOTP(secret).at(clock[0])).status_code == 429
    finally:
        other.close()
    clock[0] += 301
    assert login(client, password, pyotp.TOTP(secret).at(clock[0])).status_code == 200


def test_setup_expires_and_enabled_secret_cannot_be_overwritten(secured_client):
    client, password, clock = secured_client
    secret = setup_factor(client, password)
    clock[0] += 601
    assert (
        client.post(
            PATH + "/enable", json={"password": password, "code": pyotp.TOTP(secret).at(clock[0])}
        ).status_code
        == 400
    )
    assert client.get(PATH).json()["enabled"] is False
    enable_factor(client, password, clock)
    assert client.post(PATH + "/setup", json={"password": password}).status_code == 409


def test_password_change_does_not_remove_second_factor(secured_client):
    client, password, clock = secured_client
    enable_factor(client, password, clock)
    new_password = "ChangedPassword123"
    response = client.post(
        "/api/v1/auth/password", json={"current_password": password, "new_password": new_password}
    )
    assert response.status_code == 200, response.text
    client.cookies.clear()
    assert login(client, new_password).json() == {"two_factor_required": True}
    assert client.get("/api/v1/auth/me").status_code == 401


def test_simultaneous_recovery_code_use_only_succeeds_once(secured_client):
    client, password, clock = secured_client
    _, codes = enable_factor(client, password, clock)

    def attempt(_):
        other = TestClient(app, headers={"X-Forge-Request": "1"})
        try:
            return login(other, password, codes[0]).status_code
        finally:
            other.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == [200, 401]


def test_upgrade_preserves_existing_password_and_defaults_to_disabled(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, password_hash VARCHAR(255) NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO users (id, password_hash) VALUES (1, 'existing-hash')")
        )
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO alembic_version VALUES ('0009')"))
    database.migrate(engine)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM users")).mappings().one()
        assert row["password_hash"] == "existing-hash"
        assert row["mfa_secret_encrypted"] is None
        assert row["mfa_last_step"] == -1
        assert row["mfa_recovery_hashes"] == "[]"
        assert row["mfa_failed_attempts"] == 0
    engine.dispose()


@pytest.mark.parametrize("action", ["disable", "recovery-codes"])
def test_factor_changes_revoke_previous_browser_sessions(secured_client, action):
    client, password, clock = secured_client
    secret, _ = enable_factor(client, password, clock)
    other = TestClient(app, headers={"X-Forge-Request": "1"})
    other.cookies.update(client.cookies)
    had_refresh = bool(other.cookies.get("sprint_refresh"))
    clock[0] += 30
    try:
        response = client.post(
            PATH + "/" + action,
            json={"password": password, "code": pyotp.TOTP(secret).at(clock[0])},
        )
        assert response.status_code == 200, response.text
        assert other.get("/api/v1/auth/me").status_code == 401
        if had_refresh:
            assert other.post("/api/v1/auth/refresh").status_code == 401
        assert client.get("/api/v1/auth/me").status_code == 200
    finally:
        other.close()


def test_management_requires_an_authenticated_account(secured_client):
    other = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        assert other.get(PATH).status_code == 401
        for action in ("setup", "enable", "disable", "recovery-codes"):
            assert (
                other.post(
                    PATH + "/" + action, json={"password": "AdminPassword123", "code": "123456"}
                ).status_code
                == 401
            )
    finally:
        other.close()
