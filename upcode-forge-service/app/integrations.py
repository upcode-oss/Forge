from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.database import cipher, get_db
from app.instance_link import create_link_router
from app.models import Instance, InstanceConnection, User
from app.security import admin_user, dummy_hash, throttle, verify


def authenticate(db, username, password, request):
    throttle(f"login:{request.client.host}")
    user = db.scalar(select(User).where(User.username == username))
    valid = verify(password, user.password_hash if user else dummy_hash)
    if not valid or not user or not user.is_active:
        raise HTTPException(401, "Username or password is incorrect")
    if not user.is_admin:
        raise HTTPException(403, "Administrator access required")


def identity(db):
    instance = db.get(Instance, 1)
    return {"name": instance.name, "url": instance.public_url}


router = APIRouter(prefix="/api/v1")
router.include_router(
    create_link_router(
        product="forge",
        model=InstanceConnection,
        get_db=get_db,
        admin=admin_user,
        authenticate=authenticate,
        identity=identity,
        encrypt=lambda value: cipher().encrypt(value.encode()).decode(),
        decrypt=lambda value: cipher().decrypt(value.encode()).decode(),
    )
)
