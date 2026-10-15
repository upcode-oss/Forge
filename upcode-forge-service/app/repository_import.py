"""One-time imports. Credentials are supplied through askpass and never stored in Git config."""

import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from app import git_service as git


def clone(repository, payload):
    destination = git.path_for(repository)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Ignore host Git configuration, credential helpers, URL rewrites and trace settings.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
        and key.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
    }
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
    )
    with tempfile.TemporaryDirectory(prefix="forge-import-") as directory:
        askpass = Path(directory) / "askpass"
        askpass.write_text(
            '#!/bin/sh\ncase "$1" in\n'
            '  *Username*) printf "%s\\n" "$FORGE_IMPORT_USERNAME" ;;\n'
            '  *) printf "%s\\n" "$FORGE_IMPORT_TOKEN" ;;\nesac\n'
        )
        askpass.chmod(0o700)
        env.update(
            GIT_ASKPASS=str(askpass),
            LC_ALL="C",
            FORGE_IMPORT_USERNAME=(
                "oauth2"
                if urlsplit(payload.source_url).hostname == "gitlab.com"
                else "x-access-token"
            ),
            FORGE_IMPORT_TOKEN=payload.token.get_secret_value() if payload.token else "",
        )
        try:
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "credential.helper=",
                    "-c",
                    "protocol.allow=never",
                    "-c",
                    "protocol.https.allow=always",
                    "-c",
                    "http.followRedirects=false",
                    "-c",
                    "http.lowSpeedLimit=1024",
                    "-c",
                    "http.lowSpeedTime=30",
                    "clone",
                    "--bare",
                    "--quiet",
                    "--",
                    payload.source_url,
                    str(destination),
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180,
            )
        except subprocess.TimeoutExpired as error:
            raise HTTPException(
                408, "Import timed out. Try a smaller repository or retry later."
            ) from error
        if result.returncode:
            raise HTTPException(
                400,
                "Import failed. Check the repository URL and token permissions. Use the repository's current URL; redirects are disabled.",
            )
    git.run(destination, "remote", "remove", "origin")
    git.run(destination, "config", "http.receivepack", "true")
    git.run(destination, "config", "receive.denyNonFastforwards", "true")
    git.run(destination, "config", "receive.denyDeletes", "true")
    branch = git.run(destination, "symbolic-ref", "--short", "HEAD").decode().strip()
    repository.default_branch = git.valid_branch(branch)
