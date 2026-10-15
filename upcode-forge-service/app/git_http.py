import base64
import binascii
import os
import subprocess
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api import access
from app.config import settings
from app.database import get_db
from app.git_service import path_for
from app.models import Organization
from app.repository_access import find_repository
from app.security import throttle, token_user

router = APIRouter()


def execute(repository, suffix, request, incoming, outgoing, username):
    executable = (
        subprocess.check_output(["git", "--exec-path"], text=True).strip() + "/git-http-backend"
    )
    env = {
        **os.environ,
        "GIT_PROJECT_ROOT": str(path_for(repository).parent),
        "GIT_HTTP_EXPORT_ALL": "1",
        "PATH_INFO": f"/{repository.id}.git/{suffix}",
        "REQUEST_METHOD": request.method,
        "QUERY_STRING": request.url.query,
        "CONTENT_TYPE": request.headers.get("content-type", ""),
        "CONTENT_LENGTH": str(incoming.tell()),
        "REMOTE_USER": username,
        "REMOTE_ADDR": request.client.host,
        "SERVER_PROTOCOL": "HTTP/1.1",
    }
    if request.headers.get("git-protocol"):
        env["HTTP_GIT_PROTOCOL"] = request.headers["git-protocol"]
    if request.headers.get("content-encoding"):
        env["HTTP_CONTENT_ENCODING"] = request.headers["content-encoding"]
    incoming.seek(0)
    try:
        result = subprocess.run(
            [executable],
            stdin=incoming,
            stdout=outgoing,
            stderr=subprocess.PIPE,
            timeout=120,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(408, "Git request timed out") from error
    if result.returncode:
        raise HTTPException(500, "Git transport failed")
    outgoing.seek(0)
    headers = {}
    status = 200
    while True:
        line = outgoing.readline(8192).strip()
        if not line:
            break
        key, value = line.decode("latin-1").split(":", 1)
        if key.lower() == "status":
            status = int(value.strip().split()[0])
        else:
            headers[key] = value.strip()
    return headers, status


async def transport(owner: str, name: str, suffix: str, request: Request, db):
    service = request.query_params.get("service", "")
    if request.method == "GET" and (
        suffix != "info/refs" or service not in ("git-upload-pack", "git-receive-pack")
    ):
        raise HTTPException(404, "Unsupported Git request")
    if request.method == "POST" and suffix not in ("git-upload-pack", "git-receive-pack"):
        raise HTTPException(404, "Unsupported Git request")
    if (
        request.method == "POST"
        and request.headers.get("content-type") != f"application/x-{suffix}-request"
    ):
        raise HTTPException(415, "Invalid Git content type")
    writing = service == "git-receive-pack" or suffix == "git-receive-pack"
    user, token = None, None
    authorization = request.headers.get("authorization", "")
    if authorization:
        try:
            scheme, encoded = authorization.split(" ", 1)
            if scheme.lower() != "basic":
                raise ValueError()
            username, raw = base64.b64decode(encoded, validate=True).decode().split(":", 1)
            user, token = token_user(db, raw, "git")
            if user and user.username != username:
                user = None
        except (ValueError, UnicodeError, binascii.Error):
            user = None
        if not user:
            throttle(f"git:{request.client.host}")
            raise HTTPException(
                401,
                "Invalid Git access token",
                headers={"WWW-Authenticate": 'Basic realm="Upcode Forge"'},
            )
    if owner.startswith("organizations/") and user is None:
        organization = db.scalar(
            select(Organization).where(Organization.slug == owner.removeprefix("organizations/"))
        )
        if organization is None or organization.visibility == "private":
            # Also challenge for unknown organizations, allowing Git to request
            # credentials without revealing whether a private namespace exists.
            raise HTTPException(
                401,
                "Use your username and a Git access token",
                headers={"WWW-Authenticate": 'Basic realm="Upcode Forge"'},
            )
    repository = find_repository(db, owner, name)
    if repository is None:
        raise HTTPException(404, "Repository not found")
    # Parent visibility is checked before authentication prompts, so a guessed
    # private organization's URL never reveals its existence.
    if repository.organization_id and user is not None:
        access(db, repository.id, user)
    if not user and (writing or repository.visibility != "public"):
        raise HTTPException(
            401,
            "Use your username and a Git access token",
            headers={"WWW-Authenticate": 'Basic realm="Upcode Forge"'},
        )
    access(db, repository.id, user, "write" if writing else "read")
    if writing and token.scope != "write":
        raise HTTPException(403, "This token is read-only")
    incoming, outgoing = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    try:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > settings().max_git_body_mb * 1024 * 1024:
                raise HTTPException(413, "Git request exceeds the configured size limit")
            incoming.write(chunk)
        headers, status = await run_in_threadpool(
            execute, repository, suffix, request, incoming, outgoing, user.username if user else ""
        )
    except BaseException:
        incoming.close()
        outgoing.close()
        raise
    incoming.close()

    def stream():
        try:
            while chunk := outgoing.read(65536):
                yield chunk
        finally:
            outgoing.close()

    return StreamingResponse(stream(), status_code=status, headers=headers)


@router.api_route("/git/organizations/{owner}/{name}.git/{suffix:path}", methods=["GET", "POST"])
async def organization_git_http(
    owner: str, name: str, suffix: str, request: Request, db=Depends(get_db)
):
    return await transport(f"organizations/{owner}", name, suffix, request, db)


@router.api_route("/git/{owner}/{name}.git/{suffix:path}", methods=["GET", "POST"])
async def git_http(owner: str, name: str, suffix: str, request: Request, db=Depends(get_db)):
    return await transport(owner, name, suffix, request, db)
