import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from alembic import command
from app import database, git_service, profiles, repository_import
from app.config import settings
from app.main import app
from app.models import Membership, Repository, User


def run_git(path, *args, env=None):
    return git_service.run(path, *args, env=env)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "upstream"
    path.mkdir()
    run_git(path, "init", "--initial-branch=trunk")
    run_git(path, "config", "user.name", "Admin")
    run_git(path, "config", "user.email", "admin@example.com")
    (path / "README.md").write_text("# Imported history\n")
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Original history")
    run_git(path, "tag", "v1.0")
    run_git(path, "branch", "feature")
    return path


@pytest.fixture
def local_import(monkeypatch, source):
    original = subprocess.run
    calls = []

    def execute(args, **kwargs):
        if "clone" in args and "--bare" in args:
            calls.append((args, kwargs))
            env = kwargs["env"]
            askpass = Path(env["GIT_ASKPASS"])
            assert (
                not env["FORGE_IMPORT_TOKEN"]
                or env["FORGE_IMPORT_TOKEN"] not in askpass.read_text()
            )
            for prompt, key in [
                ("Username for HTTPS", "FORGE_IMPORT_USERNAME"),
                ("Password for HTTPS", "FORGE_IMPORT_TOKEN"),
            ]:
                answer = original(
                    [str(askpass), prompt], env=env, capture_output=True, text=True, check=True
                )
                assert answer.stdout.rstrip("\n") == env[key]
            # Exercise a real clone while replacing only the remote transport in tests.
            args = [args[0], "-c", "protocol.file.allow=always", *args[1:-2], str(source), args[-1]]
        return original(args, **kwargs)

    monkeypatch.setattr(repository_import.subprocess, "run", execute)
    return calls


@pytest.mark.parametrize(
    "host,path,username",
    [
        ("github.com", "owner/project", "x-access-token"),
        ("gitlab.com", "group/subgroup/project.git", "oauth2"),
    ],
)
def test_import_preserves_history_branches_tags_and_discards_credentials(
    admin, local_import, host, path, username
):
    token = "private-upstream-token"
    response = admin.post(
        "/api/v1/repositories/import",
        json={
            "name": "imported",
            "source_url": f"https://{host}/{path}",
            "token": token,
        },
    )
    assert response.status_code == 201, response.text
    repo = response.json()
    assert repo["default_branch"] == "trunk"
    assert repo["visibility"] == "private"
    rid = repo["id"]
    assert admin.get(f"/api/v1/repositories/{rid}/branches").json() == ["feature", "trunk"]
    assert (
        admin.get(f"/api/v1/repositories/{rid}/commits?ref=trunk").json()[0]["subject"]
        == "Original history"
    )
    assert (
        admin.get(f"/api/v1/repositories/{rid}/blob?ref=v1.0&path=README.md").json()["content"]
        == "# Imported history\n"
    )
    config = (settings().data_dir / "repositories" / f"{rid}.git" / "config").read_text()
    assert "origin" not in config and token not in config and host not in config
    args, kwargs = local_import[0]
    assert token not in " ".join(args)
    assert kwargs["env"]["FORGE_IMPORT_USERNAME"] == username
    assert kwargs["env"]["FORGE_IMPORT_TOKEN"] == token
    assert "credential.helper=" in args and "http.followRedirects=false" in args
    assert "protocol.allow=never" in args
    assert not Path(kwargs["env"]["GIT_ASKPASS"]).exists()
    assert token not in response.text
    assert (
        admin.post(
            "/api/v1/repositories/import",
            json={
                "name": "imported",
                "source_url": f"https://{host}/{path}",
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "git@github.com:owner/repo.git",
        "https://127.0.0.1/repo.git",
        "https://github.com.evil.test/owner/repo",
        "http://github.com/owner/repo",
        "https://token@github.com/owner/repo",
        "https://github.com:444/owner/repo",
        "https://github.com/owner/repo?token=secret",
        "https://gitlab.com/group/../repo",
        "https://gitlab.com/group/repo/-/tree/main",
        "https://github.com/owner/repo%0aevil",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner/repo/extra",
    ],
)
def test_import_rejects_unsafe_sources(admin, url):
    assert (
        admin.post(
            "/api/v1/repositories/import", json={"name": "unsafe", "source_url": url}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("timeout", [False, True])
def test_failed_import_cleans_database_and_partial_repository(admin, monkeypatch, timeout):
    def failed(args, **kwargs):
        destination = Path(args[-1])
        destination.mkdir()
        (destination / "partial").write_text("incomplete")
        if timeout:
            raise subprocess.TimeoutExpired(args, 180)
        return subprocess.CompletedProcess(args, 128)

    monkeypatch.setattr(repository_import.subprocess, "run", failed)
    response = admin.post(
        "/api/v1/repositories/import",
        json={
            "name": "broken",
            "source_url": "https://github.com/owner/repo",
        },
    )
    assert response.status_code == (408 if timeout else 400)
    assert admin.get("/api/v1/repositories").json() == []
    assert list((settings().data_dir / "repositories").iterdir()) == []


def test_import_requires_session(admin):
    with TestClient(app) as visitor:
        assert (
            visitor.post(
                "/api/v1/repositories/import",
                headers={"X-Forge-Request": "1"},
                json={
                    "name": "imported",
                    "source_url": "https://github.com/owner/repo",
                },
            ).status_code
            == 401
        )


def test_empty_repository_import_has_no_fake_commits(admin, source, local_import):
    for ref in run_git(source, "for-each-ref", "--format=%(refname)").decode().splitlines():
        run_git(source, "update-ref", "-d", ref)
    result = admin.post(
        "/api/v1/repositories/import",
        json={
            "name": "empty-import",
            "source_url": "https://github.com/owner/empty",
            "visibility": "public",
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["default_branch"] == "trunk"
    assert admin.get(f"/api/v1/repositories/{result.json()['id']}/branches").json() == []
    activity = admin.get("/api/v1/profiles/admin").json()["activity"]
    assert activity["totals"]["commits"] == 0 and not activity["incomplete"]


def test_calendar_reflects_new_commits_and_visibility_immediately(admin, repository):
    rid = repository["id"]
    update = {"description": "", "visibility": "public", "default_branch": "main"}
    assert admin.put(f"/api/v1/repositories/{rid}", json=update).status_code == 200
    assert admin.get("/api/v1/profiles/admin").json()["activity"]["totals"]["commits"] == 1
    with Session(database.engine) as db:
        repo = db.get(Repository, rid)
        path = git_service.path_for(repo)
        parent = git_service.resolve(path, "main")
        tree = run_git(path, "rev-parse", "HEAD^{tree}").decode().strip()
        sha = (
            run_git(
                path,
                "-c",
                "user.name=Admin",
                "-c",
                "user.email=admin@example.com",
                "commit-tree",
                tree,
                "-p",
                parent,
                "-m",
                "New contribution",
            )
            .decode()
            .strip()
        )
        run_git(path, "update-ref", "refs/heads/main", sha, parent)
    assert admin.get("/api/v1/profiles/admin").json()["activity"]["totals"]["commits"] == 2
    assert (
        admin.put(
            f"/api/v1/repositories/{rid}", json={**update, "visibility": "private"}
        ).status_code
        == 200
    )
    profile = admin.get("/api/v1/profiles/admin").json()
    assert profile["activity"]["total"] == 3 and profile["repositories"] == []
    assert profile["activity"]["private_total"] == 3
    assert profile["activity"]["totals"]["commits"] == 0


def test_public_profile_editing_privacy_activity_and_deactivation(admin):
    profile = {
        "display_name": "Alice Developer",
        "bio": "Building useful things.",
        "company": "Upcode",
        "location": "Vienna",
        "website": "https://example.com",
        "public_email": "hello@example.com",
        "social_links": [
            {"label": "GitHub", "url": "https://github.com/alice"},
            {"label": "Mastodon", "url": "https://fosstodon.org/@alice"},
        ],
    }
    assert admin.put("/api/v1/profile", json=profile).status_code == 200
    assert admin.get("/api/v1/auth/me").json()["display_name"] == profile["display_name"]
    assert admin.get("/api/v1/auth/me").json()["email"] == "admin@example.com"
    assert admin.get("/api/v1/profile").json()["social_links"] == profile["social_links"]
    private = admin.post("/api/v1/repositories", json={"name": "secret-work"}).json()
    public = admin.post(
        "/api/v1/repositories", json={"name": "open-work", "visibility": "public"}
    ).json()
    for repo in [private, public]:
        ticket = admin.post(
            f"/api/v1/repositories/{repo['id']}/tickets", json={"title": "Work"}
        ).json()
        admin.post(
            f"/api/v1/repositories/{repo['id']}/tickets/{ticket['id']}/comments",
            json={"body": "Progress"},
        )
    visitor = TestClient(app)
    try:
        response = visitor.get("/api/v1/profiles/admin")
        assert response.status_code == 200
        data = response.json()
        assert data["bio"] == profile["bio"] and data["public_email"] == "hello@example.com"
        assert "email" not in data and "is_admin" not in data and "password_hash" not in data
        assert "admin@example.com" not in response.text and "secret-work" not in response.text
        assert [repo["name"] for repo in data["repositories"]] == ["open-work"]
        assert data["repository_count"] == 1
        assert data["activity"]["totals"] == {
            "commits": 1,
            "repositories": 1,
            "issues": 1,
            "pulls": 0,
            "comments": 1,
        }
        assert data["activity"]["total"] == 8 and not data["activity"]["incomplete"]
        assert data["activity"]["private_total"] == 4
        assert sum(day["count"] for day in data["activity"]["days"]) == 8
        assert sum(day["private_count"] for day in data["activity"]["days"]) == 4
        assert data["activity"]["longest_streak"] == 1
        assert visitor.get("/api/v1/profiles/missing").status_code == 404
        assert visitor.get("/api/v1/profiles/admin?year=9999").status_code == 422
        assert (
            visitor.put(
                "/api/v1/profile", json=profile, headers={"X-Forge-Request": "1"}
            ).status_code
            == 401
        )
    finally:
        visitor.close()
    admin.put("/api/v1/profile", json={"display_name": "Admin", "public_email": ""})
    assert admin.get("/api/v1/profiles/admin").json()["public_email"] is None
    assert admin.get("/api/v1/profiles/admin").json()["social_links"] == []
    with Session(database.engine) as db:
        db.get(User, 1).is_active = False
        db.commit()
    assert admin.get("/api/v1/profiles/admin").status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        {"website": "javascript:alert(1)"},
        {"public_email": "invalid"},
        {"display_name": "   "},
        {"social_links": [{"label": "Bad", "url": "data:text/html,test"}]},
        {"social_links": [{"label": "Bad", "url": "https://token@example.com"}]},
        {"social_links": [{"label": " ", "url": "https://example.com"}]},
        {"social_links": [{"label": "Link", "url": "https://example.com"}] * 11},
    ],
)
def test_profile_validation(admin, change):
    assert admin.put("/api/v1/profile", json={"display_name": "Admin", **change}).status_code == 422


@pytest.mark.parametrize("visibilities", [("private", "public"), ("private", "private")])
def test_imported_history_counts_in_correct_year_and_deduplicates(
    admin, source, local_import, visibilities
):
    occurred = datetime.now(UTC) - timedelta(days=400)
    with Session(database.engine) as db:
        db.get(User, 1).created_at = occurred - timedelta(days=1)
        db.commit()
    env = {"GIT_AUTHOR_DATE": occurred.isoformat(), "GIT_COMMITTER_DATE": occurred.isoformat()}
    run_git(source, "commit", "--allow-empty", "-m", "Historical contribution", env=env)
    run_git(source, "branch", "another-copy")
    for name, visibility in zip(("first", "second"), visibilities, strict=True):
        result = admin.post(
            "/api/v1/repositories/import",
            json={
                "name": name,
                "source_url": "https://github.com/owner/repo",
                "visibility": visibility,
            },
        )
        assert result.status_code == 201, result.text
    data = admin.get(f"/api/v1/profiles/admin?year={occurred.year}").json()
    is_public = "public" in visibilities
    assert data["activity"]["totals"]["commits"] == (1 if is_public else 0)
    assert data["activity"]["private_total"] == (0 if is_public else 1)
    assert data["activity"]["total"] == 1
    day = next(
        day for day in data["activity"]["days"] if day["date"] == occurred.date().isoformat()
    )
    assert day["count"] == 1
    current = admin.get("/api/v1/profiles/admin").json()["activity"]
    assert current["totals"]["commits"] == (1 if is_public else 0)
    assert current["total"] == 3


@pytest.mark.parametrize("registration_year", [2022, 2042])
def test_calendar_years_start_at_registration_and_extend_to_current_year(
    admin, monkeypatch, registration_year
):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2042, 4, 15, 12, tzinfo=UTC)

    monkeypatch.setattr(profiles, "datetime", Clock)
    with Session(database.engine) as db:
        db.get(User, 1).created_at = datetime(registration_year, 1, 1, tzinfo=UTC)
        db.commit()
    response = admin.get("/api/v1/profiles/admin")
    assert response.status_code == 200
    activity = response.json()["activity"]
    assert activity["year"] == 2042
    assert activity["available_years"] == list(range(registration_year, 2043))
    first = admin.get(f"/api/v1/profiles/admin?year={registration_year}")
    assert first.status_code == 200
    assert first.json()["activity"]["year"] == registration_year
    for invalid in (registration_year - 1, 2043):
        assert admin.get(f"/api/v1/profiles/admin?year={invalid}").status_code == 422


def test_private_contributions_respect_profile_owners_memberships(admin, repository):
    alice_id = admin.post(
        "/api/v1/users",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "alice-password-long",
        },
    ).json()["id"]
    rid = repository["id"]
    with Session(database.engine) as db:
        path = git_service.path_for(db.get(Repository, rid))
        tree = run_git(path, "rev-parse", "HEAD^{tree}").decode().strip()
        sha = (
            run_git(
                path,
                "-c",
                "user.name=Alice",
                "-c",
                "user.email=alice@example.com",
                "commit-tree",
                tree,
                "-p",
                "HEAD",
                "-m",
                "Confidential commit",
            )
            .decode()
            .strip()
        )
        run_git(path, "update-ref", "refs/heads/main", sha)
    # Matching a commit email alone does not expose contributions in an inaccessible private repo.
    assert admin.get("/api/v1/profiles/alice").json()["activity"]["total"] == 0
    member = admin.put(
        f"/api/v1/repositories/{rid}/members", json={"username": "alice", "role": "write"}
    )
    assert member.status_code == 200
    alice = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        alice.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "alice-password-long"}
        )
        ticket = alice.post(
            f"/api/v1/repositories/{rid}/tickets", json={"title": "Secret issue"}
        ).json()
        alice.post(
            f"/api/v1/repositories/{rid}/tickets/{ticket['id']}/comments",
            json={"body": "Secret comment"},
        )
        response = admin.get("/api/v1/profiles/alice")
        data = response.json()
        assert data["activity"]["total"] == 3 and data["activity"]["private_total"] == 3
        assert data["repositories"] == [] and data["repository_count"] == 0
        assert sum(data["activity"]["totals"].values()) == 0
        assert sum(day["private_count"] for day in data["activity"]["days"]) == 3
        for secret in (
            sha,
            "Confidential commit",
            "Secret issue",
            "Secret comment",
            "alice@example.com",
            '"demo"',
        ):
            assert secret not in response.text
        with Session(database.engine) as db:
            member_id = db.scalar(select(Membership.id).where(Membership.user_id == alice_id))
        assert admin.delete(f"/api/v1/repositories/{rid}/members/{member_id}").status_code == 200
        assert admin.get("/api/v1/profiles/alice").json()["activity"]["total"] == 0
    finally:
        alice.close()


def test_migration_preserves_existing_accounts(tmp_path):
    target = database.make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with target.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.execute(
            text(
                "INSERT INTO users (id, username, email, display_name, password_hash, is_admin, is_active, created_at) "
                "VALUES (1, 'legacy', 'legacy@example.com', 'Legacy', 'preserved-hash', 1, 1, CURRENT_TIMESTAMP)"
            )
        )
    database.migrate(target)
    with Session(target) as db:
        user = db.scalar(select(User))
        assert user.password_hash == "preserved-hash" and user.email == "legacy@example.com"
        assert user.bio == "" and user.company == "" and user.public_email is None
        assert json.loads(user.social_links) == []
        assert user.avatar is None and user.avatar_digest is None
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
        assert db.scalar(select(Repository)) is None
    target.dispose()
