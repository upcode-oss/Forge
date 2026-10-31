"""Personal MCP credentials: fixed scope ceiling and live owner authorization."""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from app.mcp_tools import SCOPE_DESCRIPTIONS
from app.models import MCPKey, User

PREFIX = "forge_mcp_"


def fail(status, message):
    raise HTTPException(status, message)


def require_enabled(db):
    from app.mcp_settings import enabled

    if not enabled(db):
        fail(404, "MCP is disabled for this instance.")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def credential_digest(user):
    return digest(user.password_hash + "\0" + (user.mfa_secret_encrypted or ""))


def now():
    return datetime.now(UTC)


def available_scopes(db, user):
    scopes = {"profile.read", "repositories.read", "repositories.create"}
    if user.is_admin:
        return set(SCOPE_DESCRIPTIONS)
    from sqlalchemy import exists, or_

    from app.models import Membership, OrganizationMember, Repository
    from app.repository_access import visible

    for level, roles in (("maintain", ("maintain",)), ("write", ("write", "maintain"))):
        grants = or_(
            Repository.owner_id == user.id,
            exists().where(
                Membership.repository_id == Repository.id,
                Membership.user_id == user.id,
                Membership.role.in_(roles),
            ),
            exists().where(
                OrganizationMember.organization_id == Repository.organization_id,
                OrganizationMember.user_id == user.id,
                OrganizationMember.role.in_(("owner", "maintainer")),
            ),
        )
        if db.scalar(select(Repository.id).where(visible(user), grants).limit(1)) is not None:
            scopes.add("repositories." + level)
    return scopes


def key_data(record, user):
    return {
        "status": "revoked"
        if record.revoked_at
        else (
            "expired"
            if record.expires_at.replace(tzinfo=UTC) <= now()
            else (
                "credentials_changed"
                if record.password_digest != credential_digest(user)
                else "active"
            )
        ),
        "id": record.id,
        "name": record.name,
        "scopes": json.loads(record.scopes),
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "last_used_at": record.last_used_at,
        "revoked_at": record.revoked_at,
    }


def create_key(db, user, name, scopes, days):
    require_enabled(db)
    requested = set(scopes)
    if not requested or not requested.issubset(SCOPE_DESCRIPTIONS):
        fail(422, "Select at least one supported MCP permission.")
    if not requested.issubset(available_scopes(db, user)):
        fail(403, "A key cannot have permissions that you do not currently have.")
    raw = PREFIX + secrets.token_urlsafe(32)
    record = MCPKey(
        user_id=user.id,
        name=name.strip(),
        digest=digest(raw),
        scopes=json.dumps(sorted(requested)),
        password_digest=credential_digest(user),
        expires_at=now() + timedelta(days=days),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"key": raw, "record": key_data(record, user)}


def authenticate(db, raw, *, touch=False):
    require_enabled(db)
    if not isinstance(raw, str) or not raw.startswith(PREFIX) or len(raw) > 100:
        fail(401, "A valid personal MCP key is required.")
    record = db.scalar(select(MCPKey).where(MCPKey.digest == digest(raw)))
    if (
        record is None
        or record.revoked_at is not None
        or record.expires_at.replace(tzinfo=UTC) <= now()
    ):
        fail(401, "The MCP key is invalid, expired, or revoked.")
    user = db.get(User, record.user_id)
    if (
        user is None
        or not user.is_active
        or not hmac.compare_digest(record.password_digest, credential_digest(user))
    ):
        fail(401, "The MCP key owner is inactive or the account credentials changed.")
    scopes = set(json.loads(record.scopes)) & available_scopes(db, user)
    if touch:
        record.last_used_at = now()
        db.commit()
    return user, record, scopes


def list_keys(db, user):
    return [
        key_data(record, user)
        for record in db.scalars(
            select(MCPKey).where(MCPKey.user_id == user.id).order_by(MCPKey.created_at.desc())
        )
    ]


def revoke_key(db, user, key_id):
    record = db.scalar(select(MCPKey).where(MCPKey.id == key_id, MCPKey.user_id == user.id))
    if record is None:
        fail(404, "MCP key not found.")
    if record.revoked_at is None:
        record.revoked_at = now()
        db.commit()
    return {"revoked": True}


def revoke_all(db, user_id):
    db.execute(
        update(MCPKey)
        .where(MCPKey.user_id == user_id, MCPKey.revoked_at.is_(None))
        .values(revoked_at=now())
    )
