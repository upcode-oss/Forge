import base64
import binascii
import hashlib
import os
from urllib.parse import urlsplit

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from fastapi import HTTPException

from app.config import settings


def parse_public_key(value):
    lines = value.strip().splitlines()
    if len(lines) != 1:
        raise HTTPException(422, "Paste one SSH public key, never a private key")
    fields = lines[0].split()
    algorithms = {
        "ssh-ed25519",
        "ssh-rsa",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
    }
    if len(fields) < 2 or fields[0] not in algorithms:
        raise HTTPException(
            422, "Use an Ed25519, ECDSA or RSA public key without authorized_keys options"
        )
    try:
        key = serialization.load_ssh_public_key(f"{fields[0]} {fields[1]}".encode("ascii"))
        if isinstance(key, rsa.RSAPublicKey) and key.key_size < 2048:
            raise HTTPException(422, "RSA keys must have at least 2048 bits")
        canonical = key.public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
        )
        raw = base64.b64decode(canonical.split()[1], validate=True)
    except (ValueError, TypeError, UnicodeError, binascii.Error, UnsupportedAlgorithm) as error:
        raise HTTPException(422, "Invalid SSH public key") from error
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    return canonical.decode(), fingerprint


def ssh_endpoint(public_url):
    host = settings().ssh_host or urlsplit(public_url).hostname
    return host, settings().ssh_port


def ssh_clone_url(public_url, owner, name):
    if not settings().ssh_enabled:
        return None
    host, port = ssh_endpoint(public_url)
    if ":" in host:
        host = f"[{host}]"
    return f"ssh://git@{host}:{port}/{owner}/{name}.git"


def host_key_path():
    return settings().data_dir / "ssh" / "host_ed25519"


def ensure_host_key():
    path = host_key_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if not path.exists():
        key = ed25519.Ed25519PrivateKey.generate()
        data = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    path.chmod(0o600)
    return path


def host_fingerprint():
    path = host_key_path()
    if not path.exists():
        return None
    private = serialization.load_ssh_private_key(path.read_bytes(), password=None)
    public = private.public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
    )
    return parse_public_key(public.decode())[1]
