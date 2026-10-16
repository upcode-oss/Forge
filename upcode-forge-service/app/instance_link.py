"""Forge/Sprint instance-link protocol v1. Keep this module identical in both services."""

import secrets
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

PREFIX = "/integrations/instance"


def origin(value: str) -> str:
    value = value.strip()
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme in ("http", "https")
            and parts.hostname
            and parts.port != 0
            and parts.username is None
            and parts.password is None
            and not parts.query
            and not parts.fragment
            and parts.path in ("", "/")
            and not any(char.isspace() or ord(char) < 32 or char == "\\" for char in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Enter an HTTP(S) origin without a path or credentials")
    host = parts.hostname.lower()
    host = f"[{host}]" if ":" in host else host.encode("idna").decode()
    if parts.port is not None and (parts.scheme, parts.port) not in (
        ("http", 80),
        ("https", 443),
    ):
        host += f":{parts.port}"
    return f"{parts.scheme}://{host}"


class LinkColumns:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(36), unique=True)
    peer_url: Mapped[str] = mapped_column(String(500))
    peer_name: Mapped[str] = mapped_column(String(200))
    secret_encrypted: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConnectInput(BaseModel):
    url: str = Field(max_length=500)
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)

    _url = field_validator("url")(origin)


class Identity(BaseModel):
    protocol: Literal[1] = 1
    product: Literal["forge", "sprint"]
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=500)

    _url = field_validator("url")(origin)


class PeerStatus(Identity):
    connection_id: UUID
    state: Literal["pending", "connected"]


class PairInput(BaseModel):
    identity: Identity
    connection_id: UUID
    secret: SecretStr = Field(min_length=40, max_length=100)
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)


def request_peer(url, method, path, *, secret=None, connection_id=None, payload=None):
    """Never forward browser cookies, follow redirects, or expose remote error bodies."""
    headers = {"X-Forge-Request": "1"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
        headers["X-Instance-Connection"] = str(connection_id)
    try:
        with (
            httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client,
            client.stream(
                method, f"{url}/api/v1{PREFIX}{path}", headers=headers, json=payload
            ) as response,
        ):
            if response.status_code in (401, 403):
                raise HTTPException(
                    400, "The other instance rejected the credentials or connection key"
                )
            if response.status_code == 409:
                raise HTTPException(409, "The other instance already has a different connection")
            if not response.is_success:
                raise HTTPException(502, "The other instance could not complete the request")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 65536:
                    raise HTTPException(502, "Invalid response from the other instance")
            if method == "DELETE":
                return None
            return PeerStatus.model_validate_json(content)
    except (httpx.HTTPError, ValidationError) as exc:
        raise HTTPException(
            502,
            "Cannot verify the other instance. Check both public URLs, "
            "network access and TLS certificates.",
        ) from exc


def create_link_router(
    *,
    product,
    model,
    get_db,
    admin,
    authenticate,
    identity,
    encrypt,
    decrypt,
    pair_limit=None,
    route_class=APIRoute,
):
    """Adapters supply each application's existing identity, permissions and encryption."""

    def no_store(response: Response):
        response.headers["Cache-Control"] = "no-store"

    router = APIRouter(
        prefix=PREFIX,
        tags=["instance connection"],
        route_class=route_class,
        dependencies=[Depends(no_store)],
    )
    other = "sprint" if product == "forge" else "forge"
    pair_limit = pair_limit or (lambda endpoint: endpoint)

    def local_identity(db):
        return Identity(product=product, **identity(db))

    def status(db, row):
        return PeerStatus(
            **local_identity(db).model_dump(),
            connection_id=row.connection_id,
            state=row.state,
        )

    def summary(row):
        if row is None:
            return None
        return {
            "connection_id": row.connection_id,
            "product": other,
            "name": row.peer_name,
            "url": row.peer_url,
            "state": row.state,
            "created_at": row.created_at,
        }

    def verified_peer(peer, row):
        if (
            peer.product != other
            or peer.url != row.peer_url
            or str(peer.connection_id) != row.connection_id
        ):
            raise HTTPException(502, "The other instance returned an unexpected identity")

    def peer_row(request, db):
        row = db.get(model, 1)
        authorization = request.headers.get("authorization", "")
        supplied = authorization.removeprefix("Bearer ")
        if (
            row is None
            or request.headers.get("x-instance-connection") != row.connection_id
            or not secrets.compare_digest(supplied.encode(), decrypt(row.secret_encrypted).encode())
        ):
            raise HTTPException(401, "Invalid instance connection")
        return row

    def insert(db, row):
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "A connection is already being configured") from exc

    @router.get("", dependencies=[Depends(admin)])
    def detail(db=Depends(get_db)):
        return summary(db.get(model, 1))

    @router.get("/peer")
    def peer(request: Request, db=Depends(get_db)):
        return status(db, peer_row(request, db))

    @router.get("/check")
    def check(request: Request, db=Depends(get_db)):
        row = peer_row(request, db)
        remote = request_peer(
            row.peer_url,
            "GET",
            "/peer",
            secret=decrypt(row.secret_encrypted),
            connection_id=row.connection_id,
        )
        verified_peer(remote, row)
        return status(db, row)

    @router.post("/pair")
    @pair_limit
    def pair(payload: PairInput, request: Request, db=Depends(get_db)):
        # Authentication and permission checks happen before any callback or mutation.
        authenticate(db, payload.username, payload.password.get_secret_value(), request)
        if payload.identity.product != other or payload.identity.url == local_identity(db).url:
            raise HTTPException(400, f"Only a separate {other.title()} instance can be connected")
        row = db.get(model, 1)
        if row is not None and (
            row.connection_id != str(payload.connection_id)
            or row.peer_url != payload.identity.url
            or not secrets.compare_digest(
                decrypt(row.secret_encrypted), payload.secret.get_secret_value()
            )
        ):
            raise HTTPException(409, "Disconnect the existing instance first")
        # Prove the caller controls its advertised URL before storing its key.
        candidate = model(
            id=1,
            connection_id=str(payload.connection_id),
            peer_url=payload.identity.url,
            peer_name=payload.identity.name,
            secret_encrypted=encrypt(payload.secret.get_secret_value()),
            state="connected",
            created_at=datetime.now(UTC),
        )
        remote = request_peer(
            candidate.peer_url,
            "GET",
            "/peer",
            secret=payload.secret.get_secret_value(),
            connection_id=candidate.connection_id,
        )
        verified_peer(remote, candidate)
        if row is None:
            row = candidate
            insert(db, row)
        else:
            row.state = "connected"
            row.peer_name = remote.name
            db.commit()
        return status(db, row)

    @router.post("", dependencies=[Depends(admin)])
    def connect(payload: ConnectInput, db=Depends(get_db)):
        own = local_identity(db)
        if payload.url == own.url:
            raise HTTPException(400, "An instance cannot connect to itself")
        row = db.get(model, 1)
        if row is not None and (row.state != "pending" or row.peer_url != payload.url):
            raise HTTPException(409, "Disconnect the existing instance first")
        if row is None:
            row = model(
                id=1,
                connection_id=str(uuid4()),
                peer_url=payload.url,
                peer_name=other.title(),
                secret_encrypted=encrypt(secrets.token_urlsafe(48)),
                state="pending",
                created_at=datetime.now(UTC),
            )
            # Commit before calling out so the callback can verify ownership.
            insert(db, row)
        remote = request_peer(
            row.peer_url,
            "POST",
            "/pair",
            payload={
                "identity": own.model_dump(),
                "connection_id": row.connection_id,
                "secret": decrypt(row.secret_encrypted),
                "username": payload.username,
                "password": payload.password.get_secret_value(),
            },
        )
        verified_peer(remote, row)
        if remote.state != "connected":
            raise HTTPException(502, "The other instance has not completed the connection")
        row.peer_name = remote.name
        row.state = "connected"
        db.commit()
        return summary(row)

    @router.post("/test", dependencies=[Depends(admin)])
    def test(db=Depends(get_db)):
        row = db.get(model, 1)
        if row is None:
            raise HTTPException(404, "No instance is connected")
        remote = request_peer(
            row.peer_url,
            "GET",
            "/check",
            secret=decrypt(row.secret_encrypted),
            connection_id=row.connection_id,
        )
        verified_peer(remote, row)
        if remote.state != "connected":
            raise HTTPException(409, "The other instance has not completed the connection")
        row.state = "connected"
        row.peer_name = remote.name
        db.commit()
        return summary(row)

    @router.delete("/peer")
    def unpair(request: Request, db=Depends(get_db)):
        row = peer_row(request, db)
        db.delete(row)
        db.commit()
        return {"message": "Instance disconnected"}

    @router.delete("", dependencies=[Depends(admin)])
    def disconnect(force: bool = False, db=Depends(get_db)):
        row = db.get(model, 1)
        if row is not None:
            if not force:
                request_peer(
                    row.peer_url,
                    "DELETE",
                    "/peer",
                    secret=decrypt(row.secret_encrypted),
                    connection_id=row.connection_id,
                )
            db.delete(row)
            db.commit()
        return {"message": "Instance disconnected"}

    return router
