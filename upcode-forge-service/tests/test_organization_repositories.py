import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_organizations import add, create, profile
from test_organizations import people as people
from test_profiles_import import local_import as local_import
from test_profiles_import import source as source
from test_ssh import Process, add_key, pktline

from alembic import command
from app import database, git_service
from app.config import settings
from app.git_ssh import authorize, handle_process, identity_for_fingerprint, parse_command
from app.models import Comment, Membership, Organization, Repository, SSHKey, Ticket

ROOT = "/api/v1/organizations"
REPOS = "/api/v1/repositories"


def create_repo(client, name="project", organization="team", **fields):
    response = client.post(REPOS, json={"name": name, "organization": organization, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def token(client, username, scope="write"):
    value = client.post("/api/v1/tokens", json={"name": "Git", "scope": scope}).json()["token"]
    return (username, value)


def test_organization_and_personal_repositories_have_independent_namespaces(
    admin, repository, monkeypatch
):
    monkeypatch.setattr(settings(), "ssh_enabled", True)
    create(admin, "admin", visibility="public")
    organization = create_repo(admin, "demo", "admin", visibility="public")
    assert organization["owner"] == "admin" and organization["owner_type"] == "organization"
    assert organization["owner_profile_url"] == "/o/admin"
    assert organization["clone_url"] == "http://testserver/git/organizations/admin/demo.git"
    assert organization["ssh_clone_url"].endswith("/organizations/admin/demo.git")
    assert repository["clone_url"] == "http://testserver/git/admin/demo.git"
    with Session(database.engine) as db:
        stored = db.get(Repository, organization["id"])
        assert (
            stored.owner_id is None
            and stored.organization_id is not None
            and stored.created_by_id == 1
        )
    identity = identity_for_fingerprint(add_key(admin)["fingerprint"])
    assert (
        authorize(identity, "git-upload-pack 'organizations/admin/demo.git'").path.name
        == f"{organization['id']}.git"
    )
    assert (
        authorize(identity, "git-upload-pack 'admin/demo.git'").path.name
        == f"{repository['id']}.git"
    )
    assert admin.post(REPOS, json={"name": "demo", "organization": "admin"}).status_code == 409
    create(admin, "other")
    create_repo(admin, "demo", "other")
    assert len(admin.get(REPOS).json()) == 3


@pytest.mark.parametrize("role", ["owner", "maintainer", "reader"])
def test_organization_roles_apply_to_creation_settings_tickets_and_repository_lists(
    admin, people, role
):
    create(admin)
    repository = create_repo(admin)
    rid = repository["id"]
    assert add(admin, "alice", role).status_code == 200
    alice = people["alice"]
    expected = "read" if role == "reader" else "maintain"
    assert alice.get(f"{REPOS}/{rid}").json()["role"] == expected
    assert alice.get(f"{REPOS}/{rid}/tree", params={"ref": "main"}).json()[0]["name"] == "README.md"
    assert alice.post(REPOS, json={"name": "second", "organization": "team"}).status_code == (
        403 if role == "reader" else 201
    )
    assert alice.put(
        f"{REPOS}/{rid}", json={**repository, "description": "Updated"}
    ).status_code == (403 if role == "reader" else 200)
    assert alice.post(f"{REPOS}/{rid}/tickets", json={"title": "Team issue"}).status_code == (
        403 if role == "reader" else 201
    )
    assert alice.put(
        f"{REPOS}/{rid}/members", json={"username": "bob", "role": "write"}
    ).status_code == (403 if role == "reader" else 200)
    assert rid in [item["id"] for item in alice.get(REPOS).json()]
    listing = alice.get(f"{ROOT}/team/repositories").json()
    assert listing["total"] == (1 if role == "reader" else 2)
    owners = alice.get("/api/v1/repository-owners").json()
    assert owners["username"] == "alice"
    assert [item["slug"] for item in owners["organizations"]] == (
        [] if role == "reader" else ["team"]
    )


def test_parent_privacy_hides_repositories_and_their_activity_details(admin, people):
    create(admin, visibility="public")
    public = create_repo(admin, "open", visibility="public")
    private = create_repo(admin, "secret")
    visitor, outsider = people["visitor"], people["outsider"]
    assert [item["id"] for item in visitor.get(f"{ROOT}/team/repositories").json()["items"]] == [
        public["id"]
    ]
    assert outsider.get(f"{REPOS}/{private['id']}").status_code == 404
    assert outsider.get(f"{REPOS}/{public['id']}").status_code == 200
    assert (
        admin.put(f"{ROOT}/team", json={**profile(admin), "visibility": "private"}).status_code
        == 200
    )
    assert admin.get(f"{REPOS}/{public['id']}").json()["visibility"] == "private"
    for viewer in (visitor, outsider):
        assert viewer.get(f"{ROOT}/team/repositories").status_code == 404
    assert outsider.get(f"{REPOS}/{public['id']}").status_code == 404
    assert (
        outsider.get(REPOS).json() == []
        and outsider.get("/api/v1/dashboard").json()["repositories"] == 0
    )
    activity = visitor.get("/api/v1/profiles/admin").json()
    assert activity["repositories"] == []
    assert activity["activity"]["private_total"] > 0
    assert sum(activity["activity"]["totals"].values()) == 0
    assert (
        admin.post(
            REPOS, json={"name": "leak", "organization": "team", "visibility": "public"}
        ).status_code
        == 422
    )
    assert admin.put(f"{REPOS}/{public['id']}", json=public).status_code == 422
    assert admin.delete(f"{ROOT}/team").status_code == 409
    assert admin.get(f"{REPOS}/{private['id']}").status_code == 200


def test_private_organization_requires_membership_even_with_direct_repository_grants(admin, people):
    create(people["alice"])
    repository = create_repo(people["alice"])
    rid = repository["id"]
    assert add(people["alice"], "bob").status_code == 200
    assert (
        people["alice"]
        .put(f"{REPOS}/{rid}/members", json={"username": "bob", "role": "write"})
        .status_code
        == 200
    )
    assert people["bob"].get(f"{REPOS}/{rid}").json()["role"] == "write"
    assert people["alice"].delete(f"{ROOT}/team/members/bob").status_code == 204
    for viewer in (people["bob"], admin):
        assert viewer.get(f"{REPOS}/{rid}").status_code == 404
        assert viewer.get(REPOS).json() == []
    assert (
        people["bob"].post(REPOS, json={"name": "blocked", "organization": "team"}).status_code
        == 404
    )
    assert admin.get("/api/v1/repository-owners").json()["organizations"] == []


def test_real_http_git_packs_and_scope_checks_for_organization_repositories(
    admin, people, tmp_path
):
    create(admin, visibility="public")
    repository = create_repo(admin, visibility="public")
    add(admin, "alice", "maintainer")
    add(admin, "bob")
    alice, bob = people["alice"], people["bob"]
    base = repository["clone_url"].removeprefix("http://testserver")
    visitor = people["visitor"]
    discovery = visitor.get(base + "/info/refs?service=git-upload-pack")
    assert discovery.status_code == 200 and b"refs/heads/main" in discovery.content
    server = settings().data_dir / "repositories" / f"{repository['id']}.git"
    old = git_service.run(server, "rev-parse", "HEAD").strip()
    result = visitor.post(
        base + "/git-upload-pack",
        content=pktline(b"want " + old + b"\n") + b"0000" + pktline(b"done\n"),
        headers={"Content-Type": "application/x-git-upload-pack-request"},
    )
    assert result.status_code == 200 and b"PACK" in result.content
    working = tmp_path / "working"
    git_service.run(tmp_path, "clone", str(server), str(working))
    git_service.run(
        working,
        "-c",
        "user.name=Alice",
        "-c",
        "user.email=alice@example.com",
        "commit",
        "--allow-empty",
        "-m",
        "Organization push",
    )
    new = git_service.run(working, "rev-parse", "HEAD").strip()
    pack = git_service.run(
        working, "pack-objects", "--stdout", "--revs", input=new + b"\n^" + old + b"\n"
    )
    data = pktline(old + b" " + new + b" refs/heads/main\0report-status\n") + b"0000" + pack
    headers = {"Content-Type": "application/x-git-receive-pack-request"}
    assert (
        visitor.post(base + "/git-receive-pack", content=data, headers=headers).status_code == 401
    )
    assert (
        bob.post(
            base + "/git-receive-pack", content=data, headers=headers, auth=token(bob, "bob")
        ).status_code
        == 403
    )
    assert (
        alice.post(
            base + "/git-receive-pack",
            content=data,
            headers=headers,
            auth=token(alice, "alice", "read"),
        ).status_code
        == 403
    )
    pushed = alice.post(
        base + "/git-receive-pack", content=data, headers=headers, auth=token(alice, "alice")
    )
    assert pushed.status_code == 200 and b"unpack ok" in pushed.content
    assert git_service.run(server, "rev-parse", "HEAD").strip() == new
    admin.put(f"{ROOT}/team", json={**profile(admin), "visibility": "private"})
    for slug in ("team", "does-not-exist"):
        response = visitor.get(
            f"/git/organizations/{slug}/project.git/info/refs?service=git-upload-pack"
        )
        assert response.status_code == 401 and "www-authenticate" in response.headers
    credentials = token(alice, "alice")
    assert (
        alice.get(base + "/info/refs?service=git-upload-pack", auth=credentials).status_code == 200
    )
    assert admin.delete(f"{ROOT}/team/members/alice").status_code == 204
    assert (
        alice.get(base + "/info/refs?service=git-upload-pack", auth=credentials).status_code == 404
    )


def test_ssh_pack_streaming_rechecks_inherited_roles_and_revocation(admin, people):
    create(admin)
    repository = create_repo(admin)
    add(admin, "alice", "maintainer")
    alice = people["alice"]
    identity = identity_for_fingerprint(add_key(alice)["fingerprint"])
    command_line = "git-receive-pack 'organizations/team/project.git'"
    assert parse_command(command_line) == ("git-receive-pack", "organizations/team", "project")
    process = Process(identity, command_line)
    asyncio.run(handle_process(process))
    assert process.status == 0 and b"refs/heads/main" in process.stdout.data
    assert add(admin, "alice", "reader").status_code == 200
    with pytest.raises(HTTPException) as error:
        authorize(identity, command_line)
    assert error.value.status_code == 403
    assert (
        authorize(identity, "git-upload-pack 'organizations/team/project.git'").path.name
        == f"{repository['id']}.git"
    )
    admin.delete(f"{ROOT}/team/members/alice")
    with pytest.raises(HTTPException) as error:
        authorize(identity, "git-upload-pack 'organizations/team/project.git'")
    assert error.value.status_code == 404


def test_import_into_organization_preserves_history_and_does_not_create_user_repository(
    admin, people, local_import
):
    create(admin)
    add(admin, "alice", "maintainer")
    response = people["alice"].post(
        REPOS + "/import",
        json={
            "name": "imported",
            "organization": "team",
            "source_url": "https://github.com/upstream/project",
        },
    )
    assert response.status_code == 201, response.text
    repository = response.json()
    assert repository["owner_type"] == "organization" and repository["owner"] == "team"
    assert repository["default_branch"] == "trunk"
    assert admin.get(f"{REPOS}/{repository['id']}/branches").json() == ["feature", "trunk"]
    assert admin.get("/api/v1/profiles/alice").json()["repositories"] == []
    assert (
        people["outsider"]
        .post(
            REPOS + "/import",
            json={
                "name": "blocked",
                "organization": "team",
                "source_url": "https://github.com/upstream/project",
            },
        )
        .status_code
        == 404
    )


def test_migration_preserves_populated_repositories_and_all_foreign_keys(tmp_path):
    target = database.make_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with target.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0005")
        for statement in (
            "INSERT INTO users (id, username, email, display_name, password_hash, is_admin, is_active, created_at) VALUES (1, 'legacy', 'legacy@example.com', 'Legacy', 'hash', 1, 1, CURRENT_TIMESTAMP)",
            "INSERT INTO repositories (id, owner_id, name, description, visibility, default_branch, created_at) VALUES (7, 1, 'existing', 'Preserved', 'private', 'main', CURRENT_TIMESTAMP)",
            "INSERT INTO memberships (id, repository_id, user_id, role) VALUES (3, 7, 1, 'read')",
            "INSERT INTO tickets (id, repository_id, author_id, kind, title, body, state, created_at) VALUES (9, 7, 1, 'issue', 'Preserved', '', 'open', CURRENT_TIMESTAMP)",
            "INSERT INTO comments (id, ticket_id, author_id, body, created_at) VALUES (11, 9, 1, 'Preserved comment', CURRENT_TIMESTAMP)",
            "INSERT INTO ssh_keys (id, user_id, name, public_key, fingerprint, scope, created_at) VALUES (5, 1, 'Key', 'key', 'SHA256:preserved', 'write', CURRENT_TIMESTAMP)",
        ):
            connection.execute(text(statement))
    database.migrate(target)
    with Session(target) as db:
        assert db.scalar(text("PRAGMA foreign_keys")) == 1
        repository = db.get(Repository, 7)
        assert (
            repository.owner_id == repository.created_by_id == 1
            and repository.organization_id is None
        )
        assert repository.name == "existing" and repository.description == "Preserved"
        assert db.get(Membership, 3).repository_id == 7
        assert db.get(Ticket, 9).repository_id == 7
        assert db.get(Comment, 11).body == "Preserved comment"
        assert db.get(SSHKey, 5).fingerprint == "SHA256:preserved"
        organization = Organization(slug="new-team", name="Team")
        db.add(organization)
        db.flush()
        db.add(Repository(organization_id=organization.id, name="existing"))
        db.commit()
        for fields in (
            {},
            {"owner_id": 1, "organization_id": organization.id},
            {"organization_id": 99999},
        ):
            db.add(Repository(name="invalid", **fields))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    database.migrate(target)
    target.dispose()
