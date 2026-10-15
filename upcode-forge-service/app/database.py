import base64
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from alembic import command
from app.config import settings

engine = None


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings().secret_key.encode()).digest()))


def make_engine(url):
    result = create_engine(
        url,
        pool_pre_ping=True,
        connect_args=(
            {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        ),
    )
    if url.startswith("sqlite"):

        @event.listens_for(result, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return result


def migrate(target):
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    with target.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def load():
    global engine
    path = settings().data_dir / "installation.json"
    if path.exists():
        data = json.loads(path.read_text())
        engine = make_engine(cipher().decrypt(data["database"].encode()).decode())
        migrate(engine)


def save(url):
    path = settings().data_dir / "installation.json"
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump({"database": cipher().encrypt(url.encode()).decode()}, file)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


@contextmanager
def setup_lock():
    import fcntl

    with (settings().data_dir / "setup.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def get_db():
    from fastapi import HTTPException

    if engine is None:
        raise HTTPException(503, "Complete the installation setup first")
    with Session(engine) as session:
        yield session
