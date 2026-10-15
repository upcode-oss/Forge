import hashlib
import secrets
from collections import defaultdict, deque
from datetime import UTC, timedelta
from threading import Lock
from time import monotonic

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from app.database import get_db
from app.models import AccessToken, User, now

hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_hex(32))
attempts = defaultdict(deque)
attempt_lock = Lock()


def throttle(key):
    with attempt_lock:
        current = monotonic()
        for stale in [
            item for item, values in attempts.items() if not values or values[-1] < current - 300
        ]:
            del attempts[stale]
        values = attempts[key]
        if len(values) >= 10:
            raise HTTPException(429, "Too many attempts. Try again in five minutes.")
        values.append(current)


def verify(password, encoded):
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue_token(db, user, name, kind="session", scope="write", days=7):
    raw = "fg_" + secrets.token_urlsafe(40)
    record = AccessToken(
        user_id=user.id,
        name=name,
        digest=digest(raw),
        kind=kind,
        scope=scope,
        expires_at=now() + timedelta(days=days),
    )
    db.add(record)
    db.commit()
    return raw


def token_user(db, raw, kind):
    token = db.scalar(
        select(AccessToken).where(AccessToken.digest == digest(raw), AccessToken.kind == kind)
    )
    if token is None or token.expires_at.replace(tzinfo=UTC) <= now():
        return None, None
    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        return None, None
    return user, token


def optional_user(request: Request, db=Depends(get_db)):
    user, _ = token_user(db, request.cookies.get("forge_session", ""), "session")
    return user


def current_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return user


def admin_user(user=Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Administrator access required")
    return user
