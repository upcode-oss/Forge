import hashlib
import warnings
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.database import get_db
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
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
                if image.width * image.height > MAX_AVATAR_PIXELS:
                    raise HTTPException(
                        413, "Profile pictures must contain at most 16 million pixels"
                    )
                image.load()
                image = ImageOps.exif_transpose(image).convert("RGBA")
                square = ImageOps.fit(
                    image, (AVATAR_SIZE, AVATAR_SIZE), method=Image.Resampling.LANCZOS
                )
                # A new image drops EXIF, location information, comments and color profiles.
                clean = Image.new("RGBA", square.size)
                clean.paste(square)
                output = BytesIO()
                clean.save(output, format="PNG")
                return output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(413, "Profile picture dimensions are too large") from error
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
        raise HTTPException(400, "Upload a valid PNG, JPEG or WebP image") from error


@router.put("/profile/avatar")
async def upload_avatar(request: Request, db=Depends(get_db), user=Depends(current_user)):
    throttle(f"avatar:{user.id}")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in ("image/png", "image/jpeg", "image/webp", "application/octet-stream"):
        raise HTTPException(415, "Choose a PNG, JPEG or WebP image")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_AVATAR_BYTES:
            raise HTTPException(413, "Profile pictures must be 5 MiB or smaller")
        data.extend(chunk)
    normalized = await run_in_threadpool(normalize_avatar, bytes(data))
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
