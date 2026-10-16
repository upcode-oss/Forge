import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from app.database import get_db
from app.images import normalize_image, read_image
from app.models import User
from app.security import current_user, throttle

router = APIRouter(prefix="/api/v1")
MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000
AVATAR_SIZE = 256


def avatar_url(user):
    if not user.avatar_digest:
        return None
    return f"/api/v1/avatars/{user.username}/{user.avatar_digest}.png"


def normalize_avatar(data):
    return normalize_image(
        data,
        size=(AVATAR_SIZE, AVATAR_SIZE),
        max_pixels=MAX_AVATAR_PIXELS,
        label="Profile pictures",
        crop=True,
    )


async def read_avatar(request: Request):
    return await read_image(
        request,
        normalize_avatar,
        max_bytes=MAX_AVATAR_BYTES,
        label="Profile pictures",
    )


@router.put("/profile/avatar")
async def upload_avatar(request: Request, db=Depends(get_db), user=Depends(current_user)):
    throttle(f"avatar:{user.id}")
    normalized = await read_avatar(request)
    user.avatar = normalized
    user.avatar_digest = hashlib.sha256(normalized).hexdigest()
    db.commit()
    return {"avatar_url": avatar_url(user)}


@router.delete("/profile/avatar")
def remove_avatar(db=Depends(get_db), user=Depends(current_user)):
    user.avatar = None
    user.avatar_digest = None
    db.commit()
    return {"avatar_url": None}


@router.get("/avatars/{username}/{digest}.png")
def avatar(username: str, digest: str, db=Depends(get_db)):
    user = db.scalar(
        select(User).where(
            User.username == username.lower(),
            User.is_active.is_(True),
            User.avatar_digest == digest,
        )
    )
    if user is None or user.avatar is None:
        raise HTTPException(404, "Profile picture not found")
    return Response(content=user.avatar, media_type="image/png")
