"""Opt-in regression for the actual non-root backend image and restrictive checkouts."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


def docker_run(docker, *args, timeout=30):
    return subprocess.run(
        [docker, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def backend_image(tmp_path_factory):
    if os.environ.get("FORGE_TEST_DOCKER") != "1":
        pytest.skip("Set FORGE_TEST_DOCKER=1 to build and test the backend image")
    docker = shutil.which("docker")
    assert docker, "Docker is required for this opt-in test"
    context = tmp_path_factory.mktemp("backend-restrictive-context")
    backend = ROOT / "upcode-forge-service"
    for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "alembic.ini"):
        shutil.copyfile(backend / name, context / name)
    for name in ("app", "alembic"):
        shutil.copytree(
            backend / name,
            context / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for path in context.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    assert (context / "app/__init__.py").stat().st_mode & 0o777 == 0o600
    image = f"forge-runtime-permissions-test:{uuid4().hex}"
    try:
        result = docker_run(docker, "build", "--tag", image, str(context), timeout=600)
        assert result.returncode == 0, result.stdout + result.stderr
        yield docker, image
    finally:
        docker_run(docker, "image", "rm", image)


SETUP_AND_CHECK = r"""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

assert os.geteuid() == 10001
for path in Path("/app").rglob("*"):
    assert os.access(path, os.R_OK), f"Unreadable application path: {path}"
    assert not os.access(path, os.W_OK), f"Writable application path: {path}"
    if path.is_dir():
        assert os.access(path, os.X_OK), f"Unsearchable application directory: {path}"
assert os.access("/data", os.W_OK)

opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request("http://127.0.0.1:8000" + path, data=body, headers={
        "Content-Type": "application/json", "X-Forge-Request": "1",
    })
    with opener.open(req, timeout=10) as response:
        return json.load(response)

assert request("/health")["setup_completed"] is False
request("/api/v1/setup", {
    "name": "Container Test Forge", "public_url": "http://localhost:3000",
    "setup_token": os.environ["FORGE_SETUP_TOKEN"], "database_engine": "sqlite",
    "admin": {"username": "admin", "email": "admin@example.com", "display_name": "Admin",
              "password": "container-test-password"},
})
request("/api/v1/auth/login", {"username": "admin", "password": "container-test-password"})
repository = request("/api/v1/repositories", {"name": "container-test"})
assert repository["name"] == "container-test"
assert request("/health")["setup_completed"] is True
assert Path("/data/installation.json").stat().st_mode & 0o777 == 0o600
host_key = Path("/data/ssh/host_ed25519")
assert host_key.stat().st_mode & 0o777 == 0o600
print(json.dumps({"ssh_host_key": hashlib.sha256(host_key.read_bytes()).hexdigest()}))
"""


def test_non_root_backend_starts_sets_up_and_restarts(backend_image):
    docker, image = backend_image
    container = f"forge-runtime-permissions-test-{uuid4().hex}"

    def wait_ready():
        code = (
            "import json, urllib.request; "
            "print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)))"
        )
        for _ in range(40):
            response = docker_run(docker, "exec", container, "python", "-c", code)
            if response.returncode == 0:
                return response.stdout
            time.sleep(0.25)
        logs = docker_run(docker, "logs", container)
        pytest.fail("Backend did not become ready:\n" + logs.stdout + logs.stderr)

    try:
        result = docker_run(
            docker,
            "run",
            "--detach",
            "--name",
            container,
            "--network",
            "none",
            "--security-opt",
            "no-new-privileges:true",
            "--env",
            "FORGE_SECRET_KEY=test-secret-" + "a" * 40,
            "--env",
            "FORGE_SETUP_TOKEN=test-setup-" + "b" * 40,
            "--env",
            "FORGE_SSH_ENABLED=true",
            image,
        )
        assert result.returncode == 0, result.stderr
        assert "False" in wait_ready()
        checked = docker_run(docker, "exec", container, "python", "-c", SETUP_AND_CHECK)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        host_key = json.loads(checked.stdout)["ssh_host_key"]
        restarted = docker_run(docker, "restart", "--time", "2", container)
        assert restarted.returncode == 0, restarted.stderr
        assert "True" in wait_ready()
        persisted = docker_run(
            docker,
            "exec",
            container,
            "python",
            "-c",
            "import hashlib; from pathlib import Path; "
            "print(hashlib.sha256(Path('/data/ssh/host_ed25519').read_bytes()).hexdigest())",
        )
        assert persisted.returncode == 0, persisted.stderr
        assert persisted.stdout.strip() == host_key
    finally:
        docker_run(docker, "rm", "--force", container)
