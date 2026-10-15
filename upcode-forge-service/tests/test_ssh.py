import asyncio
import subprocess
import sys
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import database, git_service, git_ssh, ssh_server
from app.config import Settings, settings
from app.git_ssh import authorize, handle_process, identity_for_fingerprint, parse_command
from app.main import app
from app.models import User
from app.ssh_support import ensure_host_key, host_fingerprint, ssh_clone_url


def public(key):
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
    )


def add_key(client, key=None, scope="write"):
    key = key or ed25519.Ed25519PrivateKey.generate()
    response = client.post(
        "/api/v1/ssh-keys", json={"name": "Laptop", "public_key": public(key), "scope": scope}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "key",
    [
        ed25519.Ed25519PrivateKey.generate(),
        ec.generate_private_key(ec.SECP256R1()),
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
    ],
)
def test_add_list_duplicate_revoke_and_openssh_fingerprints(admin, tmp_path, key):
    result = add_key(admin, key)
    path = tmp_path / "key.pub"
    path.write_text(public(key) + " original-comment\n")
    output = subprocess.check_output(["ssh-keygen", "-lf", str(path)], text=True)
    assert result["fingerprint"] in output
    assert result["last_used_at"] is None and result["public_key"] == public(key)
    assert admin.get("/api/v1/ssh-keys").json() == [result]
    assert (
        admin.post(
            "/api/v1/ssh-keys",
            json={"name": "Duplicate", "public_key": public(key) + " another-comment"},
        ).status_code
        == 409
    )
    assert admin.delete(f"/api/v1/ssh-keys/{result['id']}").status_code == 200
    assert admin.get("/api/v1/ssh-keys").json() == []


@pytest.mark.parametrize(
    "value",
    [
        "ssh-ed25519 invalid-base64",
        "ssh-rsa AAAA",
        "ssh-dss AAAA",
        "ssh-ed25519-cert-v01@openssh.com AAAA",
        'command="whoami" ssh-ed25519 AAAA',
        "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate\n-----END OPENSSH PRIVATE KEY-----",
        "ssh-ed25519 AAAA\nssh-ed25519 AAAA",
        "not a key",
    ],
)
def test_key_validation_rejects_options_certificates_private_keys_and_malformed_keys(admin, value):
    assert (
        admin.post("/api/v1/ssh-keys", json={"name": "Bad", "public_key": value}).status_code == 422
    )


def test_weak_rsa_keys_are_rejected(admin):
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    assert (
        admin.post("/api/v1/ssh-keys", json={"name": "Weak", "public_key": public(key)}).status_code
        == 422
    )


def test_keys_are_private_to_their_owner_and_globally_unique(admin):
    owner_key = ed25519.Ed25519PrivateKey.generate()
    item = add_key(admin, owner_key)
    admin.post(
        "/api/v1/users",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "display_name": "Alice",
            "password": "alice-password-long",
        },
    )
    alice = TestClient(app, headers={"X-Forge-Request": "1"})
    anonymous = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        alice.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "alice-password-long"}
        )
        assert alice.get("/api/v1/ssh-keys").json() == []
        assert alice.delete(f"/api/v1/ssh-keys/{item['id']}").status_code == 200
        assert len(admin.get("/api/v1/ssh-keys").json()) == 1
        assert (
            alice.post(
                "/api/v1/ssh-keys", json={"name": "Duplicate", "public_key": public(owner_key)}
            ).status_code
            == 409
        )
        assert anonymous.get("/api/v1/ssh-keys").status_code == 401
        assert (
            anonymous.post(
                "/api/v1/ssh-keys", json={"name": "Unauthorized", "public_key": public(owner_key)}
            ).status_code
            == 401
        )
        assert anonymous.delete(f"/api/v1/ssh-keys/{item['id']}").status_code == 401
    finally:
        alice.close()
        anonymous.close()


@pytest.mark.parametrize(
    "command",
    [
        "sh",
        "ls /data",
        "git-upload-pack ../../secret.git",
        "git-upload-pack '/data/repositories/1.git'",
        "git-upload-pack '//admin/demo.git'",
        "git-upload-pack '~/demo.git'",
        "git-upload-pack --help",
        "git-upload-pack 'admin/demo.git'; id",
        "git-upload-pack 'admin/demo.git;id'",
        "git-receive-pack 'admin/demo.git' && id",
        "git-upload-pack 'admin/demo.git'\nid",
        "git-upload-pack 'admin/demo.git'\0",
        "git-upload-pack 'admin/demo.git",
        "git upload-pack 'admin/demo.git'",
    ],
)
def test_ssh_command_parser_rejects_shell_and_path_injection(command):
    with pytest.raises(HTTPException):
        parse_command(command)


def test_permissions_read_only_keys_and_revocation_are_checked_per_command(admin, repository):
    item = add_key(admin, scope="read")
    identity = identity_for_fingerprint(item["fingerprint"])
    result = authorize(identity, "git-upload-pack '/admin/demo.git'")
    assert result.path == settings().data_dir / "repositories" / f"{repository['id']}.git"
    assert admin.get("/api/v1/ssh-keys").json()[0]["last_used_at"] is not None
    with pytest.raises(HTTPException) as error:
        authorize(identity, "git-receive-pack 'admin/demo.git'")
    assert error.value.status_code == 403
    admin.delete(f"/api/v1/ssh-keys/{item['id']}")
    # Even a reused SQL id must not authorize an old SSH connection with a different key.
    add_key(admin)
    with pytest.raises(HTTPException) as error:
        authorize(identity, "git-upload-pack 'admin/demo.git'")
    assert error.value.status_code == 401
    new = admin.get("/api/v1/ssh-keys").json()[0]
    identity = identity_for_fingerprint(new["fingerprint"])
    with Session(database.engine) as db:
        db.get(User, 1).is_active = False
        db.commit()
    assert identity_for_fingerprint(new["fingerprint"]) is None
    with pytest.raises(HTTPException):
        authorize(identity, "git-upload-pack 'admin/demo.git'")


def test_private_repository_memberships_apply_to_ssh(admin, repository):
    admin.post(
        "/api/v1/users",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "display_name": "Alice",
            "password": "alice-password-long",
        },
    )
    alice = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        alice.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "alice-password-long"}
        )
        item = add_key(alice)
        identity = identity_for_fingerprint(item["fingerprint"])
        with pytest.raises(HTTPException) as error:
            authorize(identity, "git-upload-pack 'admin/demo.git'")
        assert error.value.status_code == 404
        rid = repository["id"]
        admin.put(f"/api/v1/repositories/{rid}/members", json={"username": "alice", "role": "read"})
        assert (
            authorize(identity, "git-upload-pack 'admin/demo.git'").operation == "git-upload-pack"
        )
        with pytest.raises(HTTPException):
            authorize(identity, "git-receive-pack 'admin/demo.git'")
        admin.put(
            f"/api/v1/repositories/{rid}/members", json={"username": "alice", "role": "write"}
        )
        assert (
            authorize(identity, "git-receive-pack 'admin/demo.git'").operation == "git-receive-pack"
        )
    finally:
        alice.close()


def test_clone_urls_settings_and_persistent_host_key(admin, repository, monkeypatch):
    assert repository["ssh_clone_url"] is None
    config = settings()
    monkeypatch.setattr(config, "ssh_enabled", True)
    key = ensure_host_key()
    original = key.read_bytes()
    assert ensure_host_key().read_bytes() == original
    assert key.stat().st_mode & 0o777 == 0o600 and key.parent.stat().st_mode & 0o777 == 0o700
    assert admin.get("/api/v1/ssh").json() == {
        "enabled": True,
        "host": "testserver",
        "port": 2222,
        "username": "git",
        "host_fingerprint": host_fingerprint(),
    }
    assert (
        admin.get(f"/api/v1/repositories/{repository['id']}").json()["ssh_clone_url"]
        == "ssh://git@testserver:2222/admin/demo.git"
    )
    monkeypatch.setattr(config, "ssh_host", "git.example.com")
    monkeypatch.setattr(config, "ssh_port", 22)
    assert (
        ssh_clone_url("https://web.example.com", "admin", "demo")
        == "ssh://git@git.example.com:22/admin/demo.git"
    )
    monkeypatch.setattr(config, "ssh_host", "::1")
    assert (
        ssh_clone_url("http://testserver", "admin", "demo") == "ssh://git@[::1]:22/admin/demo.git"
    )


@pytest.mark.parametrize(
    "host", ["https://host", "host:22", "host/path", "host;id", "host with spaces", "git@host"]
)
def test_invalid_ssh_hosts_are_rejected(host):
    with pytest.raises(ValueError):
        Settings(secret_key="x" * 40, setup_token="y" * 40, ssh_host=host)


class Reader:
    def __init__(self, data):
        self.data = data

    async def read(self, size):
        if self.data is None:
            await asyncio.Future()
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


class Writer:
    def __init__(self):
        self.data = bytearray()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass


class Process:
    subsystem = None
    term_type = None
    env = {"LD_PRELOAD": "forbidden", "GIT_CONFIG_COUNT": "1"}

    def __init__(self, identity, command, data=b"0000"):
        self.identity, self.command = identity, command
        self.stdin, self.stdout, self.stderr = Reader(data), Writer(), Writer()
        self.status = None

    def get_extra_info(self, name):
        return self.identity if name == "forge_identity" else None

    def exit(self, status):
        self.status = status


def test_real_git_pack_streaming_and_shell_rejection(admin, repository):
    item = add_key(admin)
    identity = identity_for_fingerprint(item["fingerprint"])
    for operation in ("git-upload-pack", "git-receive-pack"):
        process = Process(identity, f"{operation} '/admin/demo.git'")
        asyncio.run(handle_process(process))
        assert process.status == 0, process.stderr.data
        assert b"refs/heads/main" in process.stdout.data
    greeting = Process(identity, None)
    asyncio.run(handle_process(greeting))
    assert greeting.status == 0 and b"@admin" in greeting.stdout.data
    rejected = Process(identity, "cat /etc/passwd")
    asyncio.run(handle_process(rejected))
    assert rejected.status == 1 and b"Only Git" in rejected.stderr.data
    assert "LD_PRELOAD" not in git_ssh.git_environment(None)
    assert "GIT_CONFIG_COUNT" not in git_ssh.git_environment(None)
    assert git_ssh.git_environment("version=2")["GIT_PROTOCOL"] == "version=2"


def pktline(data):
    return f"{len(data) + 4:04x}".encode() + data


def test_real_git_push_updates_the_repository_through_ssh_handler(admin, repository, tmp_path):
    identity = identity_for_fingerprint(add_key(admin)["fingerprint"])
    server = settings().data_dir / "repositories" / f"{repository['id']}.git"
    working = tmp_path / "working"
    git_service.run(tmp_path, "clone", str(server), str(working))
    git_service.run(
        working,
        "-c",
        "user.name=Admin",
        "-c",
        "user.email=admin@example.com",
        "commit",
        "--allow-empty",
        "-m",
        "SSH push",
    )
    old = git_service.run(server, "rev-parse", "HEAD").strip()
    new = git_service.run(working, "rev-parse", "HEAD").strip()
    pack = git_service.run(
        working, "pack-objects", "--stdout", "--revs", input=new + b"\n^" + old + b"\n"
    )
    data = pktline(old + b" " + new + b" refs/heads/main\0report-status\n") + b"0000" + pack
    process = Process(identity, "git-receive-pack 'admin/demo.git'", data)
    asyncio.run(handle_process(process))
    assert process.status == 0, process.stderr.data
    assert b"unpack ok" in process.stdout.data
    assert git_service.run(server, "rev-parse", "HEAD").strip() == new


def test_ssh_stream_limits_and_timeout_stop_git(admin, repository, monkeypatch):
    identity = identity_for_fingerprint(add_key(admin)["fingerprint"])
    monkeypatch.setattr(settings(), "max_git_body_mb", 0)
    process = Process(identity, "git-upload-pack 'admin/demo.git'")
    asyncio.run(handle_process(process))
    assert process.status == 1 and b"size limit" in process.stderr.data
    monkeypatch.setattr(settings(), "max_git_body_mb", 100)
    monkeypatch.setattr(git_ssh, "GIT_SSH_TIMEOUT", 0.05)
    process = Process(identity, "git-upload-pack 'admin/demo.git'", None)
    asyncio.run(handle_process(process))
    assert process.status == 1 and b"timed out" in process.stderr.data


class Connection:
    def __init__(self):
        self.extra, self.closed = {"peername": ("127.0.0.1", 12345)}, False

    def set_extra_info(self, **kwargs):
        self.extra.update(kwargs)

    def get_extra_info(self, name, default=None):
        return self.extra.get(name, default)

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def test_server_authentication_binding_and_forwarding_rejection(admin):
    private = ed25519.Ed25519PrivateKey.generate()
    item = add_key(admin, private)
    connections = set()
    server = ssh_server.server_factory(SimpleNamespace(SSHServer=object), connections)()
    connection = Connection()
    server.connection_made(connection)
    assert server.begin_auth("git") is True and server.public_key_auth_supported() is True
    key = SimpleNamespace(export_public_key=lambda _: public(private).encode())
    assert asyncio.run(server.validate_public_key("wrong-user", key)) is False
    assert asyncio.run(server.validate_public_key("git", key)) is True
    assert connection.extra["forge_identity"].key_id == item["id"]
    assert server.connection_requested("localhost", 80, "localhost", 12345) is False
    assert server.server_requested("localhost", 0) is False
    assert server.unix_connection_requested("/run/docker.sock") is False
    assert server.unix_server_requested("/tmp/forward.sock") is False
    admin.delete(f"/api/v1/ssh-keys/{item['id']}")
    assert asyncio.run(server.validate_public_key("git", key)) is False
    server.connection_lost(None)
    assert not connections


def test_listener_options_disable_non_git_access_and_shutdown_closes_connections(
    admin, monkeypatch
):
    recorded = {}
    listener = Connection()

    async def create_server(factory, host, port, **kwargs):
        recorded.update(kwargs)
        recorded.update(host=host, port=port)
        return listener

    monkeypatch.setitem(
        sys.modules, "asyncssh", SimpleNamespace(SSHServer=object, create_server=create_server)
    )
    service = asyncio.run(ssh_server.start_ssh_server())
    for option in (
        "password_auth",
        "kbdint_auth",
        "host_based_auth",
        "gss_auth",
        "gss_kex",
        "allow_pty",
        "agent_forwarding",
        "x11_forwarding",
        "allow_scp",
    ):
        assert recorded[option] is False
    assert recorded["encoding"] is None and recorded["sftp_factory"] is None
    connection = Connection()
    service.connections.add(connection)
    asyncio.run(service.close())
    assert listener.closed and connection.closed
