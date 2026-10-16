from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_organizations import add, create
from test_organizations import people as people

from app import database, git_service, repository_deletion
from app.models import Comment, Membership, Repository, Ticket, User

ROOT = "/api/v1/repositories"


def create_repository(client, **fields):
    response = client.post(ROOT, json={"name": "project", **fields})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("organization", [None, "team"])
def test_deletion_removes_git_and_related_records_without_affecting_other_repositories(
    admin, people, organization
):
    alice = people["alice"]
    if organization:
        create(alice)
    target = create_repository(alice, organization=organization)
    other = create_repository(admin)
    target_id, other_id = target["id"], other["id"]
    paths = {}
    records = {}
    with Session(database.engine) as db:
        user = db.scalar(select(User).where(User.username == "bob"))
        for rid in (target_id, other_id):
            paths[rid] = git_service.path_for(db.get(Repository, rid))
            member = Membership(repository_id=rid, user_id=user.id, role="write")
            db.add(member)
            tickets = [
                Ticket(repository_id=rid, author_id=user.id, kind=kind, title=kind)
                for kind in ("issue", "pull")
            ]
            db.add_all(tickets)
            db.flush()
            comments = [Comment(ticket_id=t.id, author_id=user.id, body="Discuss") for t in tickets]
            db.add_all(comments)
            db.flush()
            records[rid] = (member.id, [t.id for t in tickets], [c.id for c in comments])
        db.commit()

    response = alice.delete(f"{ROOT}/{target_id}")
    assert response.status_code == 204 and not response.content
    assert not paths[target_id].exists()
    assert paths[other_id].is_dir()
    assert not list(paths[target_id].parent.glob(".deleting-*"))
    assert alice.get(f"{ROOT}/{target_id}").status_code == 404
    assert alice.delete(f"{ROOT}/{target_id}").status_code == 404
    assert target_id not in [repo["id"] for repo in alice.get(ROOT).json()]
    assert people["visitor"].get(
        target["clone_url"] + "/info/refs?service=git-upload-pack"
    ).status_code == (401 if organization else 404)
    assert admin.get(f"{ROOT}/{other_id}/tree", params={"ref": "main"}).status_code == 200
    with Session(database.engine) as db:
        for rid, exists in ((target_id, False), (other_id, True)):
            member_id, ticket_ids, comment_ids = records[rid]
            assert (db.get(Repository, rid) is not None) == exists
            assert (db.get(Membership, member_id) is not None) == exists
            for tid in ticket_ids:
                assert (db.get(Ticket, tid) is not None) == exists
            for cid in comment_ids:
                assert (db.get(Comment, cid) is not None) == exists
    if organization:
        assert alice.get("/api/v1/organizations/team/repositories").json()["total"] == 0
        assert alice.delete("/api/v1/organizations/team").status_code == 204
    replacement = create_repository(alice, organization=None)
    assert replacement["name"] == "project"


@pytest.mark.parametrize("role", ["read", "write", "maintain"])
def test_personal_repository_deletion_requires_maintain_access(admin, people, role):
    repository = create_repository(admin)
    rid = repository["id"]
    assert (
        admin.put(f"{ROOT}/{rid}/members", json={"username": "alice", "role": role}).status_code
        == 200
    )
    response = people["alice"].delete(f"{ROOT}/{rid}")
    assert response.status_code == (204 if role == "maintain" else 403)
    assert admin.get(f"{ROOT}/{rid}").status_code == (404 if role == "maintain" else 200)


@pytest.mark.parametrize("role", ["owner", "maintainer", "reader"])
def test_organization_repository_deletion_uses_inherited_roles(admin, people, role):
    create(admin)
    repository = create_repository(admin, organization="team")
    assert add(admin, "alice", role).status_code == 200
    assert people["alice"].delete(f"{ROOT}/{repository['id']}").status_code == (
        403 if role == "reader" else 204
    )


def test_deletion_hides_private_organization_repositories_from_outsiders_and_admins(admin, people):
    create(people["alice"])
    repository = create_repository(people["alice"], organization="team")
    url = f"{ROOT}/{repository['id']}"
    assert add(people["alice"], "bob", "maintainer").status_code == 200
    assert people["alice"].delete("/api/v1/organizations/team/members/bob").status_code == 204
    for viewer in (admin, people["bob"], people["outsider"]):
        assert viewer.delete(url).status_code == 404
    assert people["visitor"].delete(url).status_code == 401
    assert people["alice"].get(url).status_code == 200


def test_instance_administrators_can_delete_personal_repositories(admin, people):
    repository = create_repository(people["alice"])
    assert admin.delete(f"{ROOT}/{repository['id']}").status_code == 204


def test_database_failure_restores_git_directory_and_related_records(admin, monkeypatch):
    repository = create_repository(admin)
    rid = repository["id"]
    issue = admin.post(f"{ROOT}/{rid}/tickets", json={"title": "Keep this issue"}).json()
    assert (
        admin.post(
            f"{ROOT}/{rid}/tickets/{issue['id']}/comments", json={"body": "Keep this comment"}
        ).status_code
        == 201
    )
    with Session(database.engine) as db:
        item = db.get(Repository, rid)
        path = git_service.path_for(item)

        def fail_commit():
            raise RuntimeError("Simulated database failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="Simulated database failure"):
            repository_deletion.remove(db, item)

    assert path.is_dir() and not list(path.parent.glob(".deleting-*"))
    assert admin.get(f"{ROOT}/{rid}/tree", params={"ref": "main"}).status_code == 200
    assert (
        admin.get(f"{ROOT}/{rid}/tickets/{issue['id']}").json()["comments"][0]["body"]
        == "Keep this comment"
    )


def test_filesystem_failure_keeps_repository_and_reports_error(admin, monkeypatch):
    repository = create_repository(admin)

    def fail_rename(*args, **kwargs):
        raise PermissionError("Simulated filesystem failure")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", fail_rename)
        response = admin.delete(f"{ROOT}/{repository['id']}")
    assert response.status_code == 500
    assert admin.get(f"{ROOT}/{repository['id']}/tree", params={"ref": "main"}).status_code == 200


def test_repository_with_missing_git_directory_can_still_be_deleted(admin):
    repository = create_repository(admin)
    with Session(database.engine) as db:
        repository_deletion.shutil.rmtree(
            git_service.path_for(db.get(Repository, repository["id"]))
        )
    assert admin.delete(f"{ROOT}/{repository['id']}").status_code == 204


def test_failed_post_commit_cleanup_is_logged_and_isolated_from_reused_ids(
    admin, monkeypatch, caplog
):
    repository = create_repository(admin)

    def fail_cleanup(*args, **kwargs):
        raise PermissionError("Simulated cleanup failure")

    with monkeypatch.context() as patch:
        patch.setattr(repository_deletion.shutil, "rmtree", fail_cleanup)
        assert admin.delete(f"{ROOT}/{repository['id']}").status_code == 204
    assert "Could not remove deleted repository files" in caplog.text
    replacement = create_repository(admin)
    assert admin.get(f"{ROOT}/{replacement['id']}/tree", params={"ref": "main"}).status_code == 200
