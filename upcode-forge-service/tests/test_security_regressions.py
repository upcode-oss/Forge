import asyncio
import base64
import time
from io import BytesIO
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from alembic import command
from app import database, git_http, git_service, profiles, repository_deletion
from app.main import app
from app.models import AccessToken, Comment, Membership, Repository, Ticket, User
from app.security import attempts, digest, password_slots


def packet(value):
    return f"{len(value) + 4:04x}".encode() + value


LS_REFS = packet(b"command=ls-refs\n") + b"0001" + packet(b"symrefs\n") + b"0000"


def test_login_limit_does_not_lock_other_accounts_behind_the_proxy(admin):
    attempts.clear()
    attacker = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        for index in range(10):
            assert (
                attacker.post(
                    "/api/v1/auth/login",
                    json={"username": f"unknown-{index}", "password": "incorrect"},
                ).status_code
                == 401
            )
        assert (
            attacker.post(
                "/api/v1/auth/login", json={"username": "unknown", "password": "incorrect"}
            ).status_code
            == 429
        )
        assert (
            admin.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "safe-admin-password"},
            ).status_code
            == 200
        )
    finally:
        attacker.close()


def test_password_floods_do_not_queue_other_api_requests(admin):
    acquired = 0
    while password_slots.acquire(blocking=False):
        acquired += 1
    try:
        assert (
            admin.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "safe-admin-password"},
            ).status_code
            == 429
        )
        assert admin.get("/api/v1/auth/me").status_code == 200
    finally:
        for _ in range(acquired):
            password_slots.release()
    assert (
        admin.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "safe-admin-password"}
        ).status_code
        == 200
    )


def test_git_rechecks_token_revocation_after_reading_the_request_body(admin, repository):
    raw = admin.post("/api/v1/tokens", json={"name": "Delayed read", "scope": "read"}).json()[
        "token"
    ]

    def delayed_body():
        # The HTTP transport has authorized the request before consuming its body.
        with Session(database.engine) as db:
            db.execute(delete(AccessToken).where(AccessToken.digest == digest(raw)))
            db.commit()
        yield LS_REFS

    authorization = base64.b64encode(f"admin:{raw}".encode()).decode()
    reader = TestClient(app)
    try:
        response = reader.post(
            "/git/admin/demo.git/git-upload-pack",
            headers={
                "Authorization": f"Basic {authorization}",
                "Content-Type": "application/x-git-upload-pack-request",
                "Git-Protocol": "version=2",
            },
            content=delayed_body(),
        )
    finally:
        reader.close()
    assert response.status_code == 401


def test_delayed_public_git_request_cannot_read_a_replacement_private_repository(admin):
    original = admin.post(
        "/api/v1/repositories", json={"name": "public-before-deletion", "visibility": "public"}
    ).json()

    def delayed_body():
        with Session(database.engine) as db:
            repository_deletion.remove(db, db.get(Repository, original["id"]))
            owner = db.scalar(select(User).where(User.username == "admin"))
            replacement = Repository(
                owner_id=owner.id,
                created_by_id=owner.id,
                name="confidential-replacement",
                visibility="private",
                description="Private replacement",
                default_branch="main",
            )
            db.add(replacement)
            db.flush()
            git_service.initialize(replacement, owner, True)
            db.commit()
        yield LS_REFS

    visitor = TestClient(app)
    try:
        response = visitor.post(
            "/git/admin/public-before-deletion.git/git-upload-pack",
            headers={
                "Content-Type": "application/x-git-upload-pack-request",
                "Git-Protocol": "version=2",
            },
            content=delayed_body(),
        )
    finally:
        visitor.close()
    assert response.status_code == 404


def test_repository_ids_are_not_reused_after_deletion(admin, repository):
    original_id = repository["id"]
    assert admin.delete(f"/api/v1/repositories/{original_id}").status_code == 204
    replacement = admin.post("/api/v1/repositories", json={"name": "replacement"})
    assert replacement.status_code == 201
    assert replacement.json()["id"] > original_id
    with database.engine.connect() as connection:
        assert "AUTOINCREMENT" in connection.scalar(
            text("SELECT sql FROM sqlite_master WHERE name = 'repositories'")
        )


@pytest.mark.parametrize("after_image", [False, True])
def test_large_png_exif_is_rejected_before_normalization(admin, after_image):
    output = BytesIO()
    Image.new("RGB", (1, 1)).save(output, format="PNG")
    chunk = BytesIO()
    PngImagePlugin.putchunk(chunk, b"eXIf", b"Exif\0\0" * 20_000)
    clean = output.getvalue()
    position = len(clean) - 12 if after_image else 33
    malicious = clean[:position] + chunk.getvalue() + clean[position:]
    assert len(malicious) < 5 * 1024 * 1024
    response = admin.put(
        "/api/v1/profile/avatar", content=malicious, headers={"Content-Type": "image/png"}
    )
    assert response.status_code == 413


def test_git_request_body_has_a_deadline(admin, repository, monkeypatch):
    monkeypatch.setattr(git_http, "GIT_REQUEST_TIMEOUT", 0.01)
    admin.put(
        f"/api/v1/repositories/{repository['id']}",
        json={"description": "", "visibility": "public", "default_branch": "main"},
    )

    async def receive():
        await asyncio.sleep(60)
        return {"type": "http.request", "body": LS_REFS, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/git/admin/demo.git/git-upload-pack",
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-git-upload-pack-request")],
            "client": ("127.0.0.1", 12345),
        },
        receive,
    )
    with Session(database.engine) as db, pytest.raises(HTTPException) as failure:
        asyncio.run(git_http.transport("admin", "demo", "git-upload-pack", request, db))
    assert failure.value.status_code == 408


def test_repository_identity_migration_preserves_existing_references(tmp_path):
    target = database.make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with target.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0012")
    with Session(target) as db:
        owner = User(
            username="owner", email="owner@example.com", display_name="Owner", password_hash="hash"
        )
        db.add(owner)
        db.flush()
        repository = Repository(owner_id=owner.id, name="existing")
        db.add(repository)
        db.flush()
        repository_id, owner_id = repository.id, owner.id
        ticket = Ticket(repository_id=repository_id, author_id=owner_id, kind="issue", title="Keep")
        db.add_all([ticket, Membership(repository_id=repository_id, user_id=owner_id, role="read")])
        db.flush()
        db.add(Comment(ticket_id=ticket.id, author_id=owner_id, body="Keep comment"))
        db.commit()
    database.migrate(target)
    with Session(target) as db:
        assert db.get(Repository, repository_id).name == "existing"
        assert db.scalar(select(Ticket)).repository_id == repository_id
        assert db.scalar(select(Membership)).repository_id == repository_id
        assert db.scalar(select(Comment)).body == "Keep comment"
        assert db.scalar(text("PRAGMA foreign_keys")) == 1
        assert db.execute(text("PRAGMA foreign_key_check")).first() is None
        db.execute(delete(Comment))
        db.execute(delete(Ticket))
        db.execute(delete(Membership))
        db.execute(delete(Repository))
        db.commit()
        replacement = Repository(owner_id=owner_id, name="replacement")
        db.add(replacement)
        db.commit()
        assert replacement.id > repository_id
    target.dispose()


def test_anonymous_profile_scans_stop_at_the_git_time_budget(admin, monkeypatch):
    for name in ("one", "two", "three"):
        assert admin.post("/api/v1/repositories", json={"name": name}).status_code == 201
    calls = []

    def slow_history(*args, **kwargs):
        calls.append(kwargs["timeout"])
        time.sleep(0.03)
        return b""

    monkeypatch.setattr(profiles, "ACTIVITY_TIMEOUT", 0.02)
    monkeypatch.setattr(git_service, "run", slow_history)
    visitor = TestClient(app)
    try:
        response = visitor.get("/api/v1/profiles/admin")
        assert response.status_code == 200
        assert response.json()["activity"]["incomplete"] is True
        assert len(calls) == 1 and 0 < calls[0] <= 0.02
    finally:
        visitor.close()


def test_excess_profile_scans_do_not_queue_other_api_requests(admin):
    assert profiles.activity_slots.acquire(blocking=False)
    assert profiles.activity_slots.acquire(blocking=False)
    try:
        assert admin.get("/api/v1/profiles/admin").status_code == 429
        assert admin.get("/api/v1/auth/me").status_code == 200
    finally:
        profiles.activity_slots.release()
        profiles.activity_slots.release()
    assert admin.get("/api/v1/profiles/admin").status_code == 200
