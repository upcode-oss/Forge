"""Bound and normalize uploaded raster images before storing or serving them."""

import warnings
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool


def normalize_image(data, *, size, max_pixels, label, crop=False):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
                if image.width * image.height > max_pixels:
                    raise HTTPException(413, f"{label} must contain at most {max_pixels:,} pixels")
                image.load()
                image = ImageOps.exif_transpose(image).convert("RGBA")
                if crop:
                    image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
                else:
                    image.thumbnail(size, Image.Resampling.LANCZOS)
                # A fresh image drops EXIF, location, comments and color profiles.
                clean = Image.new("RGBA", image.size)
                clean.paste(image)
                output = BytesIO()
                clean.save(output, format="PNG")
                return output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(413, f"{label} dimensions are too large") from error
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
        raise HTTPException(400, "Upload a valid PNG, JPEG or WebP image") from error


async def read_image(request, normalizer, *, max_bytes, label):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in ("image/png", "image/jpeg", "image/webp", "application/octet-stream"):
        raise HTTPException(415, "Choose a PNG, JPEG or WebP image")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > max_bytes:
            raise HTTPException(413, f"{label} must be {max_bytes // (1024 * 1024)} MiB or smaller")
        data.extend(chunk)
    return await run_in_threadpool(normalizer, bytes(data))
