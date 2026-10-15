from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORGE_", extra="ignore")
    data_dir: Path = Path("/data")
    secret_key: str
    setup_token: str
    bootstrap_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    max_git_body_mb: int = 100

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
