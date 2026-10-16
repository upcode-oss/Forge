from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_organizations import create
from test_organizations import people as people

from alembic import command
from app import database, git_service
from app.models import Instance, Repository, User
from app.security import verify

ROOT = "/api/v1"
REGISTRATION = {
    "username": "newcomer",
    "email": "newcomer@example.com",
    "display_name": "New Member",
    "password": "safe-registration-password",
}


def registration_setting(admin, enabled):
    instance = admin.get(f"{ROOT}/instance").json()
    response = admin.put(f"{ROOT}/instance", json={**instance, "registration_enabled": enabled})
    assert response.status_code == 200, response.text


def test_admin_can_enable_and_disable_registration_without_affecting_existing_accounts(
    admin, people
):
    visitor = people["visitor"]
    assert visitor.get(f"{ROOT}/instance").json()["registration_enabled"] is False
    assert visitor.post(f"{ROOT}/auth/register", json=REGISTRATION).status_code == 403
    registration_setting(admin, True)
    response = visitor.post(
        f"{ROOT}/auth/register",
        json={**REGISTRATION, "is_admin": True, "is_active": False},
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_admin"] is False and response.json()["is_active"] is True
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert visitor.get(f"{ROOT}/auth/me").json()["username"] == "newcomer"
    assert visitor.get(f"{ROOT}/users").status_code == 403
    assert "email" not in people["outsider"].get(f"{ROOT}/profiles/newcomer").json()
    with Session(database.engine) as db:
        user = db.scalar(select(User).where(User.username == "newcomer"))
        assert user.password_hash != REGISTRATION["password"]
        assert verify(REGISTRATION["password"], user.password_hash)
    registration_setting(admin, False)
    assert visitor.get(f"{ROOT}/auth/me").status_code == 200
    assert (
        people["outsider"]
        .post(
            f"{ROOT}/auth/register",
            json={
                **REGISTRATION,
                "username": "closed",
                "email": "closed@example.com",
            },
        )
        .status_code
        == 403
    )
    visitor.post(f"{ROOT}/auth/logout")
    assert visitor.post(f"{ROOT}/auth/login", json=REGISTRATION).status_code == 200


def test_only_administrators_can_change_registration_and_omitted_settings_are_preserved(
    admin, people
):
    payload = {**admin.get(f"{ROOT}/instance").json(), "registration_enabled": True}
    assert people["visitor"].put(f"{ROOT}/instance", json=payload).status_code == 401
    assert people["alice"].put(f"{ROOT}/instance", json=payload).status_code == 403
    registration_setting(admin, True)
    payload.pop("registration_enabled")
    assert admin.put(f"{ROOT}/instance", json=payload).status_code == 200
    assert admin.get(f"{ROOT}/instance").json()["registration_enabled"] is True


@pytest.mark.parametrize(
    "fields",
    [
        {"username": "../escape"},
        {"username": "Uppercase"},
        {"email": "invalid"},
        {"password": "short"},
        {"display_name": ""},
        {"display_name": "   "},
    ],
)
def test_registration_validates_account_fields(admin, people, fields):
    registration_setting(admin, True)
    assert (
        people["visitor"].post(f"{ROOT}/auth/register", json={**REGISTRATION, **fields}).status_code
        == 422
    )


def test_registration_rejects_duplicate_names_and_emails_and_enforces_request_protection(
    admin, people
):
    registration_setting(admin, True)
    visitor = people["visitor"]
    for headers in ({"X-Forge-Request": ""}, {"Origin": "https://untrusted.example"}):
        assert (
            visitor.post(f"{ROOT}/auth/register", json=REGISTRATION, headers=headers).status_code
            == 403
        )
    for fields in ({"username": "admin"}, {"email": "ADMIN@example.com"}):
        assert (
            visitor.post(f"{ROOT}/auth/register", json={**REGISTRATION, **fields}).status_code
            == 409
        )
    assert visitor.post(f"{ROOT}/auth/register", json=REGISTRATION).status_code == 201


def test_registration_is_rate_limited(admin, people):
    registration_setting(admin, True)
    visitor = people["visitor"]
    for _ in range(10):
        assert (
            visitor.post(
                f"{ROOT}/auth/register", json={**REGISTRATION, "username": "admin"}
            ).status_code
            == 409
        )
    assert visitor.post(f"{ROOT}/auth/register", json=REGISTRATION).status_code == 429


def test_registration_migration_preserves_existing_instance_and_defaults_to_closed(tmp_path):
    engine = database.make_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0006")
        connection.execute(
            text(
                "INSERT INTO instance (id, name, public_url, default_branch) VALUES (1, 'Existing Forge', 'https://forge.example', 'trunk')"
            )
        )
    database.migrate(engine)
    database.migrate(engine)
    with Session(engine) as db:
        instance = db.get(Instance, 1)
        assert instance.registration_enabled is False
        assert instance.name == "Existing Forge" and instance.default_branch == "trunk"
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()


@pytest.mark.parametrize("owner", ["user", "public-organization", "private-organization"])
def test_anonymous_repository_browsing_respects_repository_and_parent_visibility(
    admin, people, owner
):
    if owner != "user":
        create(admin, visibility="public")
    response = admin.post(
        f"{ROOT}/repositories",
        json={
            "name": "open-project",
            "visibility": "public",
            "organization": "team" if owner != "user" else None,
        },
    )
    assert response.status_code == 201, response.text
    repository = response.json()
    rid = repository["id"]
    with Session(database.engine) as db:
        git_service.run(git_service.path_for(db.get(Repository, rid)), "branch", "feature", "main")
    issue = admin.post(f"{ROOT}/repositories/{rid}/tickets", json={"title": "Public issue"}).json()
    assert (
        admin.post(
            f"{ROOT}/repositories/{rid}/tickets/{issue['id']}/comments",
            json={"body": "Public discussion"},
        ).status_code
        == 201
    )
    pull = admin.post(
        f"{ROOT}/repositories/{rid}/tickets",
        json={
            "kind": "pull",
            "title": "Public pull request",
            "source_branch": "feature",
            "target_branch": "main",
        },
    ).json()
    sha = admin.get(f"{ROOT}/repositories/{rid}/commits?ref=main").json()[0]["sha"]
    if owner == "private-organization":
        organization = admin.get(f"{ROOT}/organizations/team").json()
        assert (
            admin.put(
                f"{ROOT}/organizations/team", json={**organization, "visibility": "private"}
            ).status_code
            == 200
        )
    visitor = people["visitor"]
    paths = [
        "",
        "/branches",
        "/tree?ref=main",
        "/blob?ref=main&path=README.md",
        "/commits?ref=main",
        f"/commits/{sha}",
        "/tickets",
        f"/tickets/{issue['id']}",
        f"/tickets/{pull['id']}/diff",
    ]
    for path in paths:
        response = visitor.get(f"{ROOT}/repositories/{rid}{path}")
        assert response.status_code == (404 if owner == "private-organization" else 200), (
            path,
            response.text,
        )
    listed = visitor.get(f"{ROOT}/repositories").json()
    assert [repo["id"] for repo in listed] == ([] if owner == "private-organization" else [rid])
    if owner != "private-organization":
        assert listed[0]["role"] == "read"
        assert visitor.get(f"{ROOT}/profiles/admin").status_code == 200
        if owner == "public-organization":
            assert visitor.get(f"{ROOT}/organizations/team").status_code == 200


def test_anonymous_visitors_cannot_read_private_repositories_or_write_to_public_ones(admin, people):
    public = admin.post(
        f"{ROOT}/repositories", json={"name": "public", "visibility": "public"}
    ).json()
    private = admin.post(f"{ROOT}/repositories", json={"name": "private"}).json()
    visitor = people["visitor"]
    for suffix in (
        "",
        "/branches",
        "/tree?ref=main",
        "/blob?ref=main&path=README.md",
        "/commits?ref=main",
        "/tickets",
    ):
        assert visitor.get(f"{ROOT}/repositories/{private['id']}{suffix}").status_code == 404
    issue = admin.post(
        f"{ROOT}/repositories/{public['id']}/tickets", json={"title": "Issue"}
    ).json()
    for method, path, body in (
        ("POST", "/repositories", {"name": "unauthorized"}),
        ("DELETE", f"/repositories/{public['id']}", None),
        ("PUT", f"/repositories/{public['id']}", public),
        ("PUT", f"/repositories/{public['id']}/members", {"username": "alice", "role": "maintain"}),
        ("POST", f"/repositories/{public['id']}/tickets", {"title": "Unauthorized"}),
        (
            "POST",
            f"/repositories/{public['id']}/tickets/{issue['id']}/comments",
            {"body": "Unauthorized"},
        ),
        ("PUT", f"/repositories/{public['id']}/tickets/{issue['id']}/state?state=closed", None),
        ("POST", f"/repositories/{public['id']}/tickets/{issue['id']}/merge", None),
    ):
        assert visitor.request(method, ROOT + path, json=body).status_code == 401, path
    assert visitor.get(f"{ROOT}/repositories/{public['id']}/members").status_code == 401
    assert [repo["id"] for repo in admin.get(f"{ROOT}/repositories?scope=public").json()] == [
        public["id"]
    ]
    assert len(admin.get(f"{ROOT}/repositories").json()) == 2
