from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import database
from app.main import app
from app.models import Organization, OrganizationMember, User

ROOT = "/api/v1/organizations"


@pytest.fixture
def people(admin):
    with ExitStack() as stack:
        clients = {}
        for username in ("alice", "bob", "outsider"):
            response = admin.post(
                "/api/v1/users",
                json={
                    "username": username,
                    "display_name": username.title(),
                    "email": f"{username}@example.com",
                    "password": "safe-test-password",
                },
            )
            assert response.status_code == 201, response.text
            client = TestClient(app, headers={"X-Forge-Request": "1"})
            stack.callback(client.close)
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={
                        "username": username,
                        "password": "safe-test-password",
                    },
                ).status_code
                == 200
            )
            clients[username] = client
        visitor = TestClient(app, headers={"X-Forge-Request": "1"})
        stack.callback(visitor.close)
        clients["visitor"] = visitor
        yield clients


def create(client, slug="team", **fields):
    response = client.post(ROOT, json={"slug": slug, "name": "Forge Team", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def add(client, username, role="reader", slug="team"):
    return client.put(f"{ROOT}/{slug}/members", json={"username": username, "role": role})


def profile(client, slug="team"):
    return client.get(f"{ROOT}/{slug}").json()


def test_any_account_can_create_and_creator_becomes_owner(admin, people):
    org = create(
        people["alice"],
        contact_email="team@example.com",
        social_links=[
            {"label": "GitHub", "url": "https://github.com/team"},
        ],
    )
    assert org["visibility"] == "private" and org["role"] == "owner"
    assert org["member_count"] == 1 and org["avatar_url"] is None
    assert profile(people["alice"])["contact_email"] == "team@example.com"
    assert profile(people["alice"])["social_links"][0]["label"] == "GitHub"
    assert admin.get(f"{ROOT}/team").status_code == 404
    duplicate = admin.post(ROOT, json={"slug": "team", "name": "Duplicate"})
    assert duplicate.status_code == 409
    with Session(database.engine) as db:
        assert len(db.scalars(select(Organization)).all()) == 1
        assert len(db.scalars(select(OrganizationMember)).all()) == 1


def test_private_organizations_are_hidden_from_search_profiles_and_direct_access(admin, people):
    create(admin, "secret", name="Secret Team", description="hidden-project")
    create(admin, "open", name="Public Team", description="visible-project", visibility="public")
    assert add(admin, "alice", slug="secret").status_code == 200
    for viewer in (people["visitor"], people["outsider"]):
        for endpoint in ("secret", "secret/members", "SECRET"):
            assert viewer.get(f"{ROOT}/{endpoint}").status_code == 404
        result = viewer.get(ROOT).json()
        assert result["total"] == 1 and result["items"][0]["slug"] == "open"
        assert viewer.get(ROOT, params={"q": "hidden-project"}).json()["total"] == 0
        response = viewer.get("/api/v1/profiles/admin")
        assert [item["slug"] for item in response.json()["organizations"]] == ["open"]
        assert "hidden-project" not in response.text and '"secret"' not in response.text
    assert people["alice"].get(f"{ROOT}/secret").status_code == 200
    assert [
        o["slug"] for o in people["alice"].get("/api/v1/profiles/admin").json()["organizations"]
    ] == ["open", "secret"]
    mine = people["alice"].get(ROOT, params={"scope": "mine"}).json()
    assert [o["slug"] for o in mine["items"]] == ["secret"]
    assert people["alice"].get(ROOT).json()["total"] == 1
    assert people["visitor"].get(ROOT, params={"scope": "mine"}).status_code == 401


def test_public_search_matches_name_slug_description_and_paginates(admin, people):
    create(admin, "upcode", name="Engineering", description="Builds Forge", visibility="public")
    create(admin, "other", name="Other", visibility="public")
    visitor = people["visitor"]
    for term in ("ENGINEERING", "upcode", "  forge  "):
        result = visitor.get(ROOT, params={"q": term}).json()
        assert result["total"] == 1 and result["items"][0]["slug"] == "upcode"
    for literal in ("%", "_", "' OR 1=1"):
        assert visitor.get(ROOT, params={"q": literal}).json()["total"] == 0
    first = visitor.get(ROOT, params={"limit": 1}).json()
    second = visitor.get(ROOT, params={"limit": 1, "offset": 1}).json()
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    members = visitor.get(f"{ROOT}/upcode/members")
    assert members.status_code == 200 and members.json()[0]["username"] == "admin"
    assert "admin@example.com" not in members.text and "password" not in members.text
    create(admin, "austria", name="Österreich", visibility="public")
    result = visitor.get(ROOT, params={"q": "Österreich"}).json()
    assert result["total"] == 1 and result["items"][0]["slug"] == "austria"


@pytest.mark.parametrize("role", ["reader", "maintainer", "owner"])
def test_roles_enforce_profile_privacy_and_membership_permissions(admin, people, role):
    create(admin)
    assert add(admin, "alice", role).status_code == 200
    alice = people["alice"]
    current = profile(alice)
    assert current["role"] == role
    edited = alice.put(
        f"{ROOT}/team", json={**current, "name": "Updated", "description": "New description"}
    )
    assert edited.status_code == (403 if role == "reader" else 200)
    changed_visibility = alice.put(f"{ROOT}/team", json={**current, "visibility": "public"})
    assert changed_visibility.status_code == (200 if role == "owner" else 403)
    assert add(alice, "bob").status_code == (403 if role == "reader" else 200)
    assert add(alice, "bob", "maintainer").status_code == (200 if role == "owner" else 403)
    assert add(alice, "bob", "owner").status_code == (200 if role == "owner" else 403)
    if role != "owner":
        assert add(alice, "alice", "owner").status_code == 403
        assert add(alice, "admin", "reader").status_code == 403
        assert alice.delete(f"{ROOT}/team/members/admin").status_code == 403
        assert alice.delete(f"{ROOT}/team").status_code == 403
    if role == "maintainer":
        assert alice.delete(f"{ROOT}/team/members/bob").status_code == 204
    if role == "reader":
        assert alice.delete(f"{ROOT}/team/members/alice").status_code == 204
        assert alice.get(f"{ROOT}/team").status_code == 404


def test_last_owner_is_protected_and_ownership_can_be_transferred(admin, people):
    create(admin)
    assert add(admin, "admin", "reader").status_code == 409
    assert admin.delete(f"{ROOT}/team/members/admin").status_code == 409
    assert add(admin, "alice", "owner").status_code == 200
    assert add(admin, "admin", "maintainer").status_code == 200
    assert people["alice"].delete(f"{ROOT}/team/members/alice").status_code == 409
    assert admin.delete(f"{ROOT}/team/members/admin").status_code == 204
    assert admin.get(f"{ROOT}/team").status_code == 404


def test_concurrent_owner_departures_keep_one_owner(admin, people):
    create(admin)
    assert add(admin, "alice", "owner").status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [
            pool.submit(client.delete, f"{ROOT}/team/members/{name}")
            for client, name in ((admin, "admin"), (people["alice"], "alice"))
        ]
        assert sorted(request.result().status_code for request in requests) == [204, 409]
    with Session(database.engine) as db:
        assert (
            len(
                db.scalars(
                    select(OrganizationMember).where(OrganizationMember.role == "owner")
                ).all()
            )
            == 1
        )


def png(color="red"):
    image = Image.new("RGB", (48, 32), color)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("location", "private-location")
    output = BytesIO()
    image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def upload(client, data=None):
    return client.put(
        f"{ROOT}/team/avatar",
        content=data if data is not None else png(),
        headers={"Content-Type": "image/png"},
    )


def test_organization_avatar_privacy_normalization_and_membership_revocation(admin, people):
    create(admin)
    assert add(admin, "alice", "maintainer").status_code == 200
    assert add(admin, "bob").status_code == 200
    response = upload(people["alice"])
    assert response.status_code == 200, response.text
    url = response.json()["avatar_url"]
    assert profile(admin)["avatar_url"] == url
    for viewer in (people["visitor"], people["outsider"]):
        assert viewer.get(url).status_code == 404
    picture = people["bob"].get(url)
    assert picture.status_code == 200 and picture.headers["cache-control"] == "no-store"
    assert b"private-location" not in picture.content
    with Image.open(BytesIO(picture.content)) as image:
        assert image.size == (256, 256) and image.info == {}
    assert upload(people["bob"]).status_code == 403
    assert upload(people["outsider"]).status_code == 404
    assert admin.delete(f"{ROOT}/team/members/bob").status_code == 204
    assert people["bob"].get(url).status_code == 404
    assert (
        admin.put(f"{ROOT}/team", json={**profile(admin), "visibility": "public"}).status_code
        == 200
    )
    assert people["visitor"].get(url).status_code == 200
    organizations = people["visitor"].get("/api/v1/profiles/alice").json()["organizations"]
    assert len(organizations) == 1 and organizations[0]["avatar_url"] == url
    assert (
        admin.put(f"{ROOT}/team", json={**profile(admin), "visibility": "private"}).status_code
        == 200
    )
    assert people["visitor"].get(url).status_code == 404
    assert people["visitor"].get("/api/v1/profiles/alice").json()["organizations"] == []
    assert upload(admin, b"not a picture").status_code == 400
    assert admin.get(url).status_code == 200
    new = upload(admin, png("blue")).json()["avatar_url"]
    assert new != url and admin.get(url).status_code == 404
    assert people["alice"].delete(f"{ROOT}/team/avatar").status_code == 200
    assert admin.get(new).status_code == 404


def test_deactivated_accounts_cannot_be_added_or_exposed(admin, people):
    create(admin, visibility="public")
    assert add(admin, "bob").status_code == 200
    with Session(database.engine) as db:
        db.scalar(select(User).where(User.username == "bob")).is_active = False
        db.commit()
    assert add(admin, "bob").status_code == 404
    assert people["bob"].put(f"{ROOT}/team", json=profile(admin)).status_code == 401
    assert profile(admin)["member_count"] == 1
    assert len(people["visitor"].get(f"{ROOT}/team/members").json()) == 1


def test_owner_deletion_removes_memberships_without_deleting_accounts(admin, people):
    create(admin)
    add(admin, "alice")
    url = upload(admin).json()["avatar_url"]
    assert admin.delete(f"{ROOT}/team").status_code == 204
    assert admin.get(f"{ROOT}/team").status_code == 404
    assert admin.get(url).status_code == 404
    assert people["alice"].get(ROOT, params={"scope": "mine"}).json()["items"] == []
    with Session(database.engine) as db:
        assert db.scalar(select(OrganizationMember)) is None
        assert db.scalar(select(User).where(User.username == "alice")) is not None
    create(admin)


@pytest.mark.parametrize(
    "fields",
    [
        {"slug": "Bad Name"},
        {"slug": "new"},
        {"name": "   "},
        {"visibility": "secret"},
        {"contact_email": "invalid"},
        {"social_links": [{"label": "X", "url": "javascript:alert(1)"}]},
        {"social_links": [{"label": "X", "url": "https://user:password@example.com"}]},
    ],
)
def test_invalid_organization_fields_are_rejected(admin, fields):
    assert admin.post(ROOT, json={"slug": "team", "name": "Team", **fields}).status_code == 422


def test_organization_mutations_require_authentication_and_request_protection(admin, people):
    create(admin, visibility="public")
    visitor = people["visitor"]
    assert visitor.post(ROOT, json={"slug": "team2", "name": "Team"}).status_code == 401
    assert visitor.put(f"{ROOT}/team", json=profile(admin)).status_code == 401
    assert add(visitor, "alice").status_code == 401
    assert visitor.delete(f"{ROOT}/team").status_code == 401
    assert visitor.delete(f"{ROOT}/team/avatar").status_code == 401
    assert add(people["outsider"], "outsider", "owner").status_code == 403
    assert people["outsider"].delete(f"{ROOT}/team/members/admin").status_code == 403
    assert (
        admin.post(
            ROOT,
            json={"slug": "blocked", "name": "Team"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    visitor.headers.pop("X-Forge-Request")
    assert visitor.post(ROOT, json={"slug": "blocked", "name": "Team"}).status_code == 403
