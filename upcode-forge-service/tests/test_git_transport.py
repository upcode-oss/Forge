import base64
import os
import socket
import subprocess
import threading
import time

import httpx
import pytest
import uvicorn

from app.main import app


@pytest.fixture
def live(admin):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    listener.close()


def git(path, *args, token=None, check=True):
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    if token:
        encoded = base64.b64encode(f"admin:{token}".encode()).decode()
        env.update(
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="http.extraHeader",
            GIT_CONFIG_VALUE_0=f"Authorization: Basic {encoded}",
        )
    result = subprocess.run(
        ["git", "-C", str(path), *args], env=env, capture_output=True, text=True, timeout=30
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def test_real_git_clone_push_pull_request_merge_and_token_revocation(
    admin, repository, live, tmp_path
):
    rid = repository["id"]
    url = f"{live}/git/admin/demo.git"
    raw = admin.post("/api/v1/tokens", json={"name": "Integration", "scope": "write"}).json()[
        "token"
    ]
    with httpx.Client() as anonymous:
        assert anonymous.get(url + "/info/refs?service=git-upload-pack").status_code == 401
        assert anonymous.get(url + "/HEAD").status_code == 404
    clone = tmp_path / "clone"
    git(tmp_path, "clone", url, str(clone), token=raw)
    git(clone, "config", "user.name", "Forge Test")
    git(clone, "config", "user.email", "forge@example.com")
    git(clone, "switch", "-c", "feature")
    (clone / "hello.txt").write_text("Hello from a real Git push!\n")
    git(clone, "add", "hello.txt")
    git(clone, "commit", "-m", "Add hello")
    git(clone, "push", "origin", "feature", token=raw)
    assert "feature" in admin.get(f"/api/v1/repositories/{rid}/branches").json()
    response = admin.post(
        f"/api/v1/repositories/{rid}/tickets",
        json={
            "kind": "pull",
            "title": "Add hello",
            "source_branch": "feature",
            "target_branch": "main",
        },
    )
    assert response.status_code == 201, response.text
    ticket_id = response.json()["id"]
    assert (
        "Hello from"
        in admin.get(f"/api/v1/repositories/{rid}/tickets/{ticket_id}/diff").json()["diff"]
    )
    response = admin.post(f"/api/v1/repositories/{rid}/tickets/{ticket_id}/merge")
    assert response.status_code == 200, response.text
    assert (
        admin.get(f"/api/v1/repositories/{rid}/blob?ref=main&path=hello.txt").json()["content"]
        == "Hello from a real Git push!\n"
    )
    assert admin.post(f"/api/v1/repositories/{rid}/tickets/{ticket_id}/merge").status_code == 400
    # A conflicting merge must leave both the branch and ticket unchanged.
    git(clone, "fetch", "origin", token=raw)
    git(clone, "switch", "main")
    git(clone, "reset", "--hard", "origin/main")
    git(clone, "switch", "-c", "conflict")
    (clone / "hello.txt").write_text("Source change\n")
    git(clone, "commit", "-am", "Change source")
    git(clone, "push", "origin", "conflict", token=raw)
    git(clone, "switch", "main")
    (clone / "hello.txt").write_text("Destination change\n")
    git(clone, "commit", "-am", "Change destination")
    git(clone, "push", "origin", "main", token=raw)
    conflict = admin.post(
        f"/api/v1/repositories/{rid}/tickets",
        json={
            "kind": "pull",
            "title": "Conflicting changes",
            "source_branch": "conflict",
            "target_branch": "main",
        },
    ).json()
    assert (
        admin.post(f"/api/v1/repositories/{rid}/tickets/{conflict['id']}/merge").status_code == 409
    )
    assert (
        admin.get(f"/api/v1/repositories/{rid}/tickets/{conflict['id']}").json()["state"] == "open"
    )
    assert (
        admin.get(f"/api/v1/repositories/{rid}/blob?ref=main&path=hello.txt").json()["content"]
        == "Destination change\n"
    )
    readonly = admin.post("/api/v1/tokens", json={"name": "Read only", "scope": "read"}).json()[
        "token"
    ]
    assert (
        git(clone, "push", "origin", "feature:denied", token=readonly, check=False).returncode != 0
    )
    token_id = next(
        t["id"] for t in admin.get("/api/v1/tokens").json() if t["name"] == "Integration"
    )
    admin.delete(f"/api/v1/tokens/{token_id}")
    assert git(clone, "ls-remote", "origin", token=raw, check=False).returncode != 0
    admin.put(
        f"/api/v1/repositories/{rid}",
        json={"description": "Public now", "visibility": "public", "default_branch": "main"},
    )
    assert git(clone, "ls-remote", "origin", check=False).returncode == 0
    assert git(clone, "push", "origin", "feature:anonymous", check=False).returncode != 0
