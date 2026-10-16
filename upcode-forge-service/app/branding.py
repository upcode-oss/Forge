import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.database import get_db
from app.images import normalize_image, read_image
from app.models import Instance
from app.security import admin_user, throttle

router = APIRouter(prefix="/api/v1/instance", tags=["instance branding"])
MAX_LOGO_BYTES = 5 * 1024 * 1024
MAX_LOGO_PIXELS = 16_000_000
LOGO_SIZE = (512, 512)


def logo_url(instance):
    if not instance.logo_digest:
        return None
    return f"/api/v1/instance/logo/{instance.logo_digest}.png"


def normalize_logo(data):
    return normalize_image(
        data,
        size=LOGO_SIZE,
        max_pixels=MAX_LOGO_PIXELS,
        label="Instance logos",
    )


@router.put("/logo")
async def upload_logo(request: Request, db=Depends(get_db), user=Depends(admin_user)):
    throttle(f"instance-logo:{user.id}")
    normalized = await read_image(
        request,
        normalize_logo,
        max_bytes=MAX_LOGO_BYTES,
        label="Instance logos",
    )
    instance = db.get(Instance, 1)
    instance.logo = normalized
    instance.logo_digest = hashlib.sha256(normalized).hexdigest()
    db.commit()
    return {"logo_url": logo_url(instance)}


@router.delete("/logo")
def remove_logo(db=Depends(get_db), user=Depends(admin_user)):
    instance = db.get(Instance, 1)
    instance.logo = None
    instance.logo_digest = None
    db.commit()
    return {"logo_url": None}


@router.get("/logo/{digest}.png")
def logo(digest: str, db=Depends(get_db)):
    instance = db.get(Instance, 1)
    if instance.logo_digest != digest or instance.logo is None:
        raise HTTPException(404, "Instance logo not found")
    return Response(content=instance.logo, media_type="image/png")
