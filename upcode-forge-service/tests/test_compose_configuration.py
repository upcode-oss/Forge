"""Check Compose's actual interpolation and profile selection without starting containers."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PASSWORDS = ("POSTGRES_PASSWORD", "MARIADB_PASSWORD", "MARIADB_ROOT_PASSWORD")
SECRETS = ("FORGE_SECRET_KEY", "FORGE_SETUP_TOKEN")


@pytest.fixture
def compose():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is required; no daemon or containers are needed")
    version = subprocess.run(
        [docker, "compose", "version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if version.returncode:
        pytest.skip("Docker Compose plugin is not installed")

    def config(profile=None, overrides=None):
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in (*PASSWORDS, *SECRETS) and not key.startswith("COMPOSE_")
        }
        env.update(
            {
                "FORGE_SECRET_KEY": "test-secret-" + "a" * 40,
                "FORGE_SETUP_TOKEN": "test-setup-" + "b" * 40,
            }
        )
        env.update(overrides or {})
        args = [docker, "compose", "--env-file", os.devnull, "-f", str(ROOT / "docker-compose.yml")]
        if profile:
            args += ["--profile", profile]
        return subprocess.run(
            [*args, "config", "--format", "json"],
            env=env,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )

    return config


@pytest.mark.parametrize("empty", [False, True])
def test_sqlite_does_not_require_database_passwords(compose, empty):
    result = compose(overrides=dict.fromkeys(PASSWORDS, "") if empty else None)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert set(json.loads(result.stdout)["services"]) == {"backend", "frontend"}


@pytest.mark.parametrize(
    "profile,configured",
    [
        ("postgres", {"POSTGRES_PASSWORD": "test-postgres-password"}),
        (
            "mariadb",
            {
                "MARIADB_PASSWORD": "test-mariadb-password",
                "MARIADB_ROOT_PASSWORD": "test-root-password",
            },
        ),
    ],
)
def test_database_profile_only_needs_its_own_credentials(compose, profile, configured):
    result = compose(profile=profile, overrides=configured)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    services = json.loads(result.stdout)["services"]
    assert set(services) == {"backend", "frontend", profile}
    for name, password in configured.items():
        assert services[profile]["environment"][name] == password


@pytest.mark.parametrize("secret", SECRETS)
def test_application_secrets_remain_required(compose, secret):
    result = compose(overrides={secret: ""})
    assert result.returncode != 0
    assert secret in result.stderr
    assert all(password not in result.stderr for password in PASSWORDS)
