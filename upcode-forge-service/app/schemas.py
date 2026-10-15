import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(Credentials):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    is_admin: bool = False
    password: str = Field(min_length=12, max_length=256)

    @field_validator("username")
    @classmethod
    def username_valid(cls, value):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,49}", value):
            raise ValueError(
                "Use lowercase letters, numbers, underscores or hyphens; start with a letter"
            )
        return value


class SMTP(BaseModel):
    host: str = Field(default="", max_length=254)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=254)
    password: str = Field(default="", max_length=500)
    encryption: Literal["starttls", "tls"] = "starttls"
    from_address: EmailStr | None = None


class InstanceUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    public_url: str = Field(max_length=500)
    default_branch: str = Field(default="main", min_length=1, max_length=100)

    @field_validator("public_url")
    @classmethod
    def valid_url(cls, value):
        parts = urlsplit(value)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in ("", "/")
        ):
            raise ValueError("Enter an HTTP(S) origin without a path or credentials")
        return value.rstrip("/")


class Setup(InstanceUpdate):
    setup_token: str
    database_engine: Literal["sqlite", "postgresql", "mysql"] = "sqlite"
    database_host: str = Field(default="postgres", max_length=254)
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(default="forge", min_length=1, max_length=100)
    database_user: str = Field(default="forge", max_length=100)
    database_password: str = Field(default="", max_length=500)
    admin: UserCreate
    smtp: SMTP | None = None


class RepoCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,99}$")
    description: str = Field(default="", max_length=500)
    visibility: Literal["public", "private"] = "private"
    initialize: bool = True


class RepoUpdate(BaseModel):
    description: str = Field(max_length=500)
    visibility: Literal["public", "private"]
    default_branch: str = Field(min_length=1, max_length=100)


class RepoImport(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,99}$")
    description: str = Field(default="", max_length=500)
    visibility: Literal["public", "private"] = "private"
    source_url: str = Field(min_length=1, max_length=500)
    token: SecretStr | None = Field(default=None, max_length=500)

    @field_validator("source_url")
    @classmethod
    def source_valid(cls, value):
        parts = urlsplit(value.strip())
        segments = parts.path.strip("/").split("/")
        if (
            parts.scheme != "https"
            or parts.hostname not in ("github.com", "gitlab.com")
            or parts.port not in (None, 443)
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or len(segments) < 2
            or (parts.hostname == "github.com" and len(segments) != 2)
            or any(
                segment in (".", "..", "-") or not re.fullmatch(r"[A-Za-z0-9_.-]+", segment)
                for segment in segments
            )
        ):
            raise ValueError(
                "Use an HTTPS repository URL on github.com or gitlab.com without credentials"
            )
        name = "/".join(segments)
        if not name.endswith(".git"):
            name += ".git"
        return f"https://{parts.hostname}/{name}"


def profile_url(value):
    value = value.strip()
    if not value:
        return value
    parts = urlsplit(value)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Enter an HTTP(S) URL without credentials")
    return value


class SocialLink(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=1, max_length=500)

    @field_validator("label", "url")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("This field cannot be blank")
        return value.strip()

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return profile_url(value)


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    bio: str = Field(default="", max_length=500)
    company: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=100)
    website: str = Field(default="", max_length=500)
    public_email: EmailStr | None = None
    social_links: list[SocialLink] = Field(default_factory=list, max_length=10)

    @field_validator("display_name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("Display name cannot be blank")
        return value.strip()

    @field_validator("website")
    @classmethod
    def website_valid(cls, value):
        return profile_url(value)

    @field_validator("public_email", mode="before")
    @classmethod
    def empty_email(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class MemberInput(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    role: Literal["read", "write", "maintain"] = "read"


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    visibility: Literal["public", "private"] = "private"
    contact_email: EmailStr | None = None
    social_links: list[SocialLink] = Field(default_factory=list, max_length=10)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()

    @field_validator("contact_email", mode="before")
    @classmethod
    def empty_email(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class OrganizationCreate(OrganizationUpdate):
    slug: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,49}$")

    @field_validator("slug")
    @classmethod
    def available_slug(cls, value):
        if value == "new":
            raise ValueError("This URL name is reserved; choose another name")
        return value


class OrganizationMemberInput(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    role: Literal["owner", "maintainer", "reader"] = "reader"


class TicketCreate(BaseModel):
    kind: Literal["issue", "pull"] = "issue"
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=50000)
    source_branch: str | None = Field(default=None, max_length=100)
    target_branch: str | None = Field(default=None, max_length=100)


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class TokenInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: Literal["read", "write"] = "write"
    days: int = Field(default=90, ge=1, le=365)


class PasswordInput(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
