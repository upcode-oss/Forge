"""Authorize Git SSH commands and stream packs without invoking a shell."""

import asyncio
import os
import re
import shlex
import signal
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import database
from app.api import access
from app.config import settings
from app.git_service import path_for
from app.models import Repository, SSHKey, User, now

GIT_SSH_TIMEOUT = 120


@dataclass(frozen=True)
class SSHIdentity:
    key_id: int
    user_id: int
    fingerprint: str


@dataclass(frozen=True)
class GitCommand:
    username: str
    operation: str | None = None
    path: Path | None = None


def identity_for_fingerprint(fingerprint):
    if database.engine is None:
        return None
    with Session(database.engine) as db:
        row = db.execute(
            select(SSHKey.id, SSHKey.user_id, SSHKey.fingerprint)
            .join(User)
            .where(
                SSHKey.fingerprint == fingerprint,
                User.is_active.is_(True),
            )
        ).first()
        return SSHIdentity(*row) if row else None


def parse_command(command):
    if len(command) > 512 or any(char in command for char in "\r\n\x00"):
        raise HTTPException(400, "Only Git upload-pack and receive-pack commands are allowed")
    try:
        parts = shlex.split(command)
    except ValueError as error:
        raise HTTPException(400, "Invalid Git command") from error
    if len(parts) != 2 or parts[0] not in ("git-upload-pack", "git-receive-pack"):
        raise HTTPException(400, "Only Git upload-pack and receive-pack commands are allowed")
    match = re.fullmatch(r"/?([a-z][a-z0-9_-]{0,49})/([a-z0-9][a-z0-9_-]{0,99})\.git", parts[1])
    if match is None:
        raise HTTPException(400, "Use the SSH clone URL shown by Forge")
    return parts[0], match[1], match[2]


def authorize(identity, command):
    if database.engine is None:
        raise HTTPException(503, "Complete the installation setup first")
    with Session(database.engine) as db:
        key = db.get(SSHKey, identity.key_id) if isinstance(identity, SSHIdentity) else None
        if key and (key.user_id != identity.user_id or key.fingerprint != identity.fingerprint):
            key = None
        user = db.get(User, key.user_id) if key else None
        if user is None or not user.is_active:
            raise HTTPException(401, "SSH key is no longer authorized")
        if command:
            operation, owner, name = parse_command(command)
            writing = operation == "git-receive-pack"
            if writing and key.scope != "write":
                raise HTTPException(403, "This SSH key is read-only")
            repository = db.scalar(
                select(Repository)
                .join(User, User.id == Repository.owner_id)
                .where(
                    User.username == owner,
                    Repository.name == name,
                )
            )
            if repository is None:
                raise HTTPException(404, "Repository not found")
            access(db, repository.id, user, "write" if writing else "read")
            result = GitCommand(user.username, operation, path_for(repository))
        else:
            result = GitCommand(user.username)
        key.last_used_at = now()
        db.commit()
        return result


def git_environment(protocol):
    env = {
        "PATH": os.defpath,
        "LANG": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    if protocol in ("version=1", "version=2"):
        env["GIT_PROTOCOL"] = protocol
    return env


async def run_git(process, command):
    child = await asyncio.create_subprocess_exec(
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        command.operation.removeprefix("git-"),
        str(command.path),
        env=git_environment(process.env.get("GIT_PROTOCOL")),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    input_error = None

    def stop():
        if child.returncode is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    async def incoming():
        nonlocal input_error
        received = 0
        try:
            while chunk := await process.stdin.read(65536):
                received += len(chunk)
                if received > settings().max_git_body_mb * 1024 * 1024:
                    input_error = "Git request exceeds the configured size limit"
                    stop()
                    return
                child.stdin.write(chunk)
                await child.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            input_error = "Git connection interrupted"
            stop()
        finally:
            child.stdin.close()

    async def outgoing(source, target):
        while chunk := await source.read(65536):
            target.write(chunk)
            await target.drain()

    reader = asyncio.create_task(incoming())
    try:
        await asyncio.wait_for(
            asyncio.gather(
                child.wait(),
                outgoing(child.stdout, process.stdout),
                outgoing(child.stderr, process.stderr),
            ),
            timeout=GIT_SSH_TIMEOUT,
        )
        if input_error:
            process.stderr.write((input_error + "\n").encode())
        return 1 if input_error or child.returncode < 0 else child.returncode
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        stop()
        await child.wait()


async def handle_process(process):
    try:
        if process.subsystem or process.term_type:
            raise HTTPException(400, "Forge provides Git access only")
        command = await run_in_threadpool(
            authorize, process.get_extra_info("forge_identity"), process.command
        )
        if command.operation is None:
            process.stdout.write(
                f"Hi @{command.username}! SSH authentication succeeded. Forge provides Git access only.\n".encode()
            )
            process.exit(0)
            return
        process.exit(await run_git(process, command))
    except HTTPException as error:
        process.stderr.write(f"Forge: {error.detail}\n".encode())
        process.exit(1)
    except TimeoutError:
        process.stderr.write(b"Forge: Git operation timed out\n")
        process.exit(1)
    except (OSError, ConnectionError):
        process.stderr.write(b"Forge: Git transport failed\n")
        process.exit(1)
