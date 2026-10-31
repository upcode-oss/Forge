from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete

from app import database, two_factor
from app.api import start_session
from app.database import get_db
from app.models import AccessToken, Instance
from app.security import current_user, throttle, verify

router = APIRouter(prefix="/api/v1/auth/2fa", tags=["two-factor authentication"])


class PasswordProof(BaseModel):
    password: SecretStr = Field(min_length=1, max_length=256)


class FactorProof(PasswordProof):
    code: SecretStr = Field(min_length=1, max_length=32)


def prepare(db, user, payload):
    throttle(f"2fa:{user.id}")
    if not verify(payload.password.get_secret_value(), user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    two_factor.lock_account(db, user)


def decrypt(value):
    return database.cipher().decrypt(value.encode()).decode()


def renew_session(db, user, response):
    db.execute(
        delete(AccessToken).where(AccessToken.user_id == user.id, AccessToken.kind == "session")
    )
    start_session(db, user, response)


@router.get("")
def status(user=Depends(current_user)):
    return two_factor.status(user)


@router.post("/setup")
def setup(payload: PasswordProof, user=Depends(current_user), db=Depends(get_db)):
    prepare(db, user, payload)
    instance = db.get(Instance, 1)
    result = two_factor.setup(
        user,
        f"{user.username}@{urlsplit(instance.public_url).netloc}",
        "Upcode Forge",
        lambda value: database.cipher().encrypt(value.encode()).decode(),
    )
    db.commit()
    return result


@router.post("/enable")
def enable(
    payload: FactorProof, response: Response, user=Depends(current_user), db=Depends(get_db)
):
    prepare(db, user, payload)
    codes = two_factor.enable(db, user, payload.code.get_secret_value(), decrypt)
    renew_session(db, user, response)
    return {"recovery_codes": codes}


@router.post("/disable")
def disable(
    payload: FactorProof, response: Response, user=Depends(current_user), db=Depends(get_db)
):
    prepare(db, user, payload)
    two_factor.disable(db, user, payload.code.get_secret_value(), decrypt)
    renew_session(db, user, response)
    return {"enabled": False}


@router.post("/recovery-codes")
def regenerate(
    payload: FactorProof, response: Response, user=Depends(current_user), db=Depends(get_db)
):
    prepare(db, user, payload)
    codes = two_factor.regenerate(db, user, payload.code.get_secret_value(), decrypt)
    renew_session(db, user, response)
    return {"recovery_codes": codes}
