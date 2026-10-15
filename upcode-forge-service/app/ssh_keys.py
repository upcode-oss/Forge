from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import get_db
from app.models import Instance, SSHKey
from app.security import current_user, throttle
from app.ssh_support import host_fingerprint, parse_public_key, ssh_endpoint

router = APIRouter(prefix="/api/v1")


class SSHKeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    public_key: str = Field(min_length=1, max_length=16384)
    scope: str = Field(default="write", pattern=r"^(read|write)$")

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("Enter a key name")
        return value.strip()


def key_data(key):
    return {
        "id": key.id,
        "name": key.name,
        "public_key": key.public_key,
        "fingerprint": key.fingerprint,
        "scope": key.scope,
        "created_at": key.created_at.replace(tzinfo=UTC),
        "last_used_at": key.last_used_at.replace(tzinfo=UTC) if key.last_used_at else None,
    }


@router.get("/ssh")
def ssh_status(db=Depends(get_db), user=Depends(current_user)):
    host, port = ssh_endpoint(db.get(Instance, 1).public_url)
    return {
        "enabled": settings().ssh_enabled,
        "host": host,
        "port": port,
        "username": "git",
        "host_fingerprint": host_fingerprint() if settings().ssh_enabled else None,
    }


@router.get("/ssh-keys")
def list_keys(db=Depends(get_db), user=Depends(current_user)):
    return [
        key_data(key)
        for key in db.scalars(
            select(SSHKey).where(SSHKey.user_id == user.id).order_by(SSHKey.created_at.desc())
        )
    ]


@router.post("/ssh-keys", status_code=201)
def add_key(payload: SSHKeyInput, db=Depends(get_db), user=Depends(current_user)):
    throttle(f"ssh-key:{user.id}")
    canonical, fingerprint = parse_public_key(payload.public_key)
    if db.scalar(select(func.count()).select_from(SSHKey).where(SSHKey.user_id == user.id)) >= 50:
        raise HTTPException(409, "Remove an unused key before adding more (maximum 50)")
    key = SSHKey(
        user_id=user.id,
        name=payload.name,
        public_key=canonical,
        fingerprint=fingerprint,
        scope=payload.scope,
    )
    db.add(key)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "This SSH key is already registered") from error
    return key_data(key)


@router.delete("/ssh-keys/{key_id}")
def remove_key(key_id: int, db=Depends(get_db), user=Depends(current_user)):
    db.execute(delete(SSHKey).where(SSHKey.id == key_id, SSHKey.user_id == user.id))
    db.commit()
    return {"ok": True}
