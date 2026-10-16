from io import BytesIO
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from app import branding, database
from app.main import app
from app.models import Instance


def image_bytes(format="PNG", color="red", size=(600, 200)):
    output = BytesIO()
    image = Image.new("RGBA" if format == "PNG" else "RGB", size, color)
    options = {}
    if format == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Comment", "private-logo-metadata")
        options["pnginfo"] = metadata
    image.save(output, format=format, **options)
    return output.getvalue()


def upload(client, data=None, content_type="image/png"):
    return client.put(
        "/api/v1/instance/logo",
        content=image_bytes() if data is None else data,
        headers={"Content-Type": content_type},
    )


@pytest.mark.parametrize(
    "format,content_type", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_logo_upload_is_public_normalized_and_persistent(admin, format, content_type):
    assert admin.get("/api/v1/instance").json()["logo_url"] is None
    result = upload(admin, image_bytes(format), content_type)
    assert result.status_code == 200, result.text
    url = result.json()["logo_url"]
    assert url.startswith("/api/v1/instance/logo/") and url.endswith(".png")
    visitor = TestClient(app)
    try:
        assert visitor.get("/api/v1/instance").json()["logo_url"] == url
        picture = visitor.get(url)
        assert picture.status_code == 200
        assert picture.headers["content-type"] == "image/png"
        assert picture.headers["x-content-type-options"] == "nosniff"
        with Image.open(BytesIO(picture.content)) as image:
            assert image.size == (512, 171)
            assert image.format == "PNG" and image.mode == "RGBA"
            assert image.info == {}
        assert b"private-logo-metadata" not in picture.content
        database.engine.dispose()
        database.engine = None
        database.load()
        assert visitor.get(url).content == picture.content
    finally:
        visitor.close()


def test_logo_keeps_transparency_and_does_not_enlarge_small_images(admin):
    result = upload(admin, image_bytes(color=(20, 40, 60, 80), size=(90, 30)))
    with Image.open(BytesIO(admin.get(result.json()["logo_url"]).content)) as image:
        assert image.size == (90, 30)
        assert image.getpixel((45, 15)) == (20, 40, 60, 80)


def test_replacing_and_resetting_logo_invalidates_previous_urls(admin):
    original = upload(admin).json()["logo_url"]
    replacement = upload(admin, image_bytes(color="blue")).json()["logo_url"]
    assert replacement != original
    assert admin.get(original).status_code == 404
    assert admin.get(replacement).status_code == 200
    assert admin.delete("/api/v1/instance/logo").json() == {"logo_url": None}
    assert admin.get(replacement).status_code == 404
    assert admin.get("/api/v1/instance").json()["logo_url"] is None
    assert admin.delete("/api/v1/instance/logo").status_code == 200


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
def test_invalid_logo_preserves_existing_image(admin, data, content_type, status):
    url = upload(admin).json()["logo_url"]
    assert upload(admin, data, content_type).status_code == status
    assert admin.get("/api/v1/instance").json()["logo_url"] == url
    assert admin.get(url).status_code == 200


def test_logo_limits_preserve_existing_image(admin, monkeypatch):
    url = upload(admin).json()["logo_url"]
    result = admin.put(
        "/api/v1/instance/logo",
        content=(b"x" * 1024 * 1024 for _ in range(6)),
        headers={"Content-Type": "image/png"},
    )
    assert result.status_code == 413
    monkeypatch.setattr(branding, "MAX_LOGO_PIXELS", 100)
    assert upload(admin).status_code == 413
    assert admin.get("/api/v1/instance").json()["logo_url"] == url


def test_logo_changes_require_administrator_and_request_protection(admin):
    url = upload(admin).json()["logo_url"]
    visitor = TestClient(app)
    try:
        assert upload(visitor).status_code == 403
        visitor.headers["X-Forge-Request"] = "1"
        assert upload(visitor).status_code == 401
        assert visitor.delete("/api/v1/instance/logo").status_code == 401
        assert (
            admin.put(
                "/api/v1/instance/logo",
                content=image_bytes(),
                headers={"Content-Type": "image/png", "Origin": "https://untrusted.example"},
            ).status_code
            == 403
        )
        assert (
            admin.post(
                "/api/v1/users",
                json={
                    "username": "reader",
                    "display_name": "Reader",
                    "email": "reader@example.com",
                    "password": "reader-password-long",
                },
            ).status_code
            == 201
        )
        assert (
            visitor.post(
                "/api/v1/auth/login",
                json={
                    "username": "reader",
                    "password": "reader-password-long",
                },
            ).status_code
            == 200
        )
        assert upload(visitor).status_code == 403
        assert visitor.delete("/api/v1/instance/logo").status_code == 403
        assert admin.get(url).status_code == 200
    finally:
        visitor.close()


def test_logo_migration_preserves_existing_instance(tmp_path):
    target = database.make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with target.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0008")
            connection.execute(
                text(
                    "INSERT INTO instance (id, name, public_url, default_branch, registration_enabled, "
                    "smtp_config) VALUES (1, 'Existing Forge', 'https://forge.example', 'main', 1, "
                    "'preserved-encrypted-configuration')"
                )
            )
        database.migrate(target)
        with Session(target) as db:
            instance = db.get(Instance, 1)
            assert instance.name == "Existing Forge"
            assert instance.public_url == "https://forge.example"
            assert instance.registration_enabled is True
            assert instance.smtp_config == "preserved-encrypted-configuration"
            assert instance.logo is None and instance.logo_digest is None
    finally:
        target.dispose()
