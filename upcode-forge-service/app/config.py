import ipaddress
import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORGE_", extra="ignore")
    data_dir: Path = Path("/data")
    secret_key: str
    setup_token: str
    bootstrap_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    max_git_body_mb: int = 100
    ssh_enabled: bool = False
    ssh_host: str = ""
    ssh_port: int = Field(default=2222, ge=1, le=65535)
    ssh_listen_host: str = "127.0.0.1"
    ssh_listen_port: int = Field(default=2222, ge=1, le=65535)

    @field_validator("ssh_host")
    @classmethod
    def valid_ssh_host(cls, value):
        value = value.strip()
        if not value:
            return value
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            if len(value) > 253 or not all(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in value.rstrip(".").split(".")
            ):
                raise ValueError(
                    "Enter an SSH hostname or IP address without a port or scheme"
                ) from None
        return value

    def validate_secrets(self):
        for name in ("secret_key", "setup_token"):
            value = getattr(self, name)
            if len(value) < 32 or "CHANGE_ME" in value:
                raise RuntimeError(
                    f"FORGE_{name.upper()} must be a random secret of 32+ characters"
                )


@lru_cache
def settings():
    return Settings()
