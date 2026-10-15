"""Encrypted SSH integration test; requires AsyncSSH and permission to bind loopback."""

import asyncio
import os
import shlex
import subprocess
import threading

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.config import settings
from app.ssh_server import start_ssh_server
from app.ssh_support import host_key_path

pytest.importorskip(
    "asyncssh", reason="Install the backend dependencies to run the SSH network test"
)


def test_encrypted_ssh_clone_push_shell_rejection_and_key_revocation(
    admin, repository, tmp_path, monkeypatch
):
    private = ed25519.Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
    )
    response = admin.post(
        "/api/v1/ssh-keys", json={"name": "SSH integration", "public_key": public.decode()}
    )
    assert response.status_code == 201
    key_id = response.json()["id"]
    identity = tmp_path / "id_ed25519"
    identity.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
    )
    identity.chmod(0o600)
    monkeypatch.setattr(settings(), "ssh_listen_host", "127.0.0.1")
    monkeypatch.setattr(settings(), "ssh_listen_port", 0)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    service = None
    try:
        service = asyncio.run_coroutine_threadsafe(start_ssh_server(), loop).result(timeout=10)
        port = service.listener.get_port()
        host = serialization.load_ssh_private_key(host_key_path().read_bytes(), password=None)
        host_public = host.public_key().public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
        )
        known = tmp_path / "known_hosts"
        known.write_bytes(f"[127.0.0.1]:{port} ".encode() + host_public + b"\n")
        ssh = [
            "ssh",
            "-F",
            "/dev/null",
            "-i",
            str(identity),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            f"UserKnownHostsFile={known}",
            "-o",
            "StrictHostKeyChecking=yes",
            "-p",
            str(port),
        ]
        env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_SSH_COMMAND": shlex.join(ssh),
        }

        def git(path, *args, check=True):
            result = subprocess.run(
                ["git", "-C", str(path), *args], env=env, capture_output=True, text=True, timeout=30
            )
            if check:
                assert result.returncode == 0, result.stderr
            return result

        clone = tmp_path / "clone"
        git(tmp_path, "clone", f"ssh://git@127.0.0.1:{port}/admin/demo.git", str(clone))
        git(
            clone,
            "-c",
            "user.name=Admin",
            "-c",
            "user.email=admin@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "Encrypted SSH push",
        )
        git(clone, "push", "origin", "main")
        commits = admin.get(f"/api/v1/repositories/{repository['id']}/commits?ref=main").json()
        assert commits[0]["subject"] == "Encrypted SSH push"
        rejected = subprocess.run(
            [*ssh, "git@127.0.0.1", "cat /etc/passwd"], capture_output=True, timeout=10
        )
        assert rejected.returncode == 1 and b"Only Git" in rejected.stderr
        assert admin.delete(f"/api/v1/ssh-keys/{key_id}").status_code == 200
        assert git(clone, "ls-remote", "origin", check=False).returncode != 0
    finally:
        if service:
            asyncio.run_coroutine_threadsafe(service.close(), loop).result(timeout=10)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()
