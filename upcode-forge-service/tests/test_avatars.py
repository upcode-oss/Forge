from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy.orm import Session

from app import avatars, database
from app.main import app
from app.models import User


def image_bytes(format="PNG", color="red"):
    output = BytesIO()
    image = Image.new("RGB", (48, 32), color)
    options = {}
    if format == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Comment", "private-location-metadata")
        options["pnginfo"] = metadata
    image.save(output, format=format, **options)
    return output.getvalue()


def upload(client, data=None, content_type="image/png"):
    return client.put(
        "/api/v1/profile/avatar",
        content=data if data is not None else image_bytes(),
        headers={"Content-Type": content_type},
    )


@pytest.mark.parametrize(
    "format,content_type", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_profile_picture_upload_is_normalized_public_and_persistent(admin, format, content_type):
    assert admin.get("/api/v1/profile").json()["avatar_url"] is None
    response = upload(admin, image_bytes(format), content_type)
    assert response.status_code == 200, response.text
    url = response.json()["avatar_url"]
    assert url.startswith("/api/v1/avatars/admin/") and url.endswith(".png")
    assert admin.get("/api/v1/profile").json()["avatar_url"] == url
    assert admin.get("/api/v1/auth/me").json()["avatar_url"] == url
    assert admin.get("/api/v1/profiles/admin").json()["avatar_url"] == url
    visitor = TestClient(app)
    try:
        picture = visitor.get(url)
        assert picture.status_code == 200
        assert picture.headers["content-type"] == "image/png"
        assert picture.headers["x-content-type-options"] == "nosniff"
        assert b"private-location-metadata" not in picture.content
        with Image.open(BytesIO(picture.content)) as image:
            assert image.size == (256, 256) and image.format == "PNG"
            assert image.info == {}
            assert image.getpixel((128, 128))[0] > 240
        database.engine.dispose()
        database.engine = None
        database.load()
        assert visitor.get(url).content == picture.content
    finally:
        visitor.close()


def test_profile_picture_replacement_removal_and_deactivation(admin):
    original = upload(admin).json()["avatar_url"]
    new = upload(admin, image_bytes(color="blue")).json()["avatar_url"]
    assert new != original
    assert admin.get(original).status_code == 404 and admin.get(new).status_code == 200
    assert admin.delete("/api/v1/profile/avatar").json() == {"avatar_url": None}
    assert admin.get(new).status_code == 404
    assert admin.get("/api/v1/profiles/admin").json()["avatar_url"] is None
    assert admin.delete("/api/v1/profile/avatar").status_code == 200
    new = upload(admin).json()["avatar_url"]
    with Session(database.engine) as db:
        db.get(User, 1).is_active = False
        db.commit()
    assert admin.get(new).status_code == 404


@pytest.mark.parametrize(
    "data,content_type,status",
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml", 415),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/png", 400),
        (b"not an image", "image/jpeg", 400),
        (b"", "image/png", 400),
        (b"\x89PNG\r\n\x1a\n", "image/png", 400),
    ],
)
def test_invalid_upload_preserves_existing_picture(admin, data, content_type, status):
    url = upload(admin).json()["avatar_url"]
    result = upload(admin, data, content_type)
    assert result.status_code == status, result.text
    assert admin.get("/api/v1/profile").json()["avatar_url"] == url
    assert admin.get(url).status_code == 200


def test_avatar_limits_reject_large_bodies_and_dimensions(admin, monkeypatch):
    url = upload(admin).json()["avatar_url"]
    result = admin.put(
        "/api/v1/profile/avatar",
        content=(b"x" * 1024 * 1024 for _ in range(6)),
        headers={"Content-Type": "image/png"},
    )
    assert result.status_code == 413
    monkeypatch.setattr(avatars, "MAX_AVATAR_PIXELS", 100)
    assert upload(admin).status_code == 413
    assert admin.get("/api/v1/profile").json()["avatar_url"] == url


def test_avatar_upload_requires_session_and_request_protection(admin):
    visitor = TestClient(app)
    try:
        assert upload(visitor).status_code == 403
        visitor.headers["X-Forge-Request"] = "1"
        assert upload(visitor).status_code == 401
        assert visitor.delete("/api/v1/profile/avatar").status_code == 401
        assert (
            admin.put(
                "/api/v1/profile/avatar",
                content=image_bytes(),
                headers={
                    "Content-Type": "image/png",
                    "Origin": "https://untrusted.example",
                },
            ).status_code
            == 403
        )
    finally:
        visitor.close()


def test_avatar_changes_apply_only_to_signed_in_account(admin):
    admin_url = upload(admin).json()["avatar_url"]
    response = admin.post(
        "/api/v1/users",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "alice-password-long",
        },
    )
    assert response.status_code == 201
    alice = TestClient(app, headers={"X-Forge-Request": "1"})
    try:
        assert (
            alice.post(
                "/api/v1/auth/login", json={"username": "alice", "password": "alice-password-long"}
            ).status_code
            == 200
        )
        alice_url = alice.put(
            "/api/v1/profile/avatar?user_id=1",
            content=image_bytes(color="blue"),
            headers={"Content-Type": "image/png"},
        ).json()["avatar_url"]
        assert "/alice/" in alice_url
        assert admin.get("/api/v1/profile").json()["avatar_url"] == admin_url
        assert alice.delete("/api/v1/profile/avatar?user_id=1").status_code == 200
        assert admin.get(admin_url).status_code == 200
    finally:
        alice.close()
