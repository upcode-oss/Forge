"""Authenticator-based two-factor authentication and single-use recovery codes."""

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
from time import time

import pyotp
import qrcode
from fastapi import HTTPException
from qrcode.image.svg import SvgPathImage
from sqlalchemy import update

from app.models import User


class TwoFactorRequired(Exception):
    pass


def fail(status_code, message):
    raise HTTPException(status_code, message)


def lock_account(db, user):
    # A guarded write serializes factor use/changes, including on SQLite.
    result = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.is_active.is_(True),
            User.password_hash == user.password_hash,
            User.mfa_secret_encrypted == user.mfa_secret_encrypted,
        )
        .values(mfa_last_step=User.mfa_last_step)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        fail(401, "Your account changed. Sign in again.")
    db.refresh(user)


def status(user):
    return {
        "enabled": bool(user.mfa_secret_encrypted),
        "recovery_codes_remaining": len(json.loads(user.mfa_recovery_hashes)),
    }


def matching_step(secret, code, last_step=-1):
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    step = int(time()) // 30
    totp = pyotp.TOTP(secret)
    for candidate in (step, step - 1, step + 1):
        if candidate > last_step and hmac.compare_digest(totp.at(candidate * 30), code):
            return candidate
    return None


def verify_code(db, user, code, decrypt, *, pending=False):
    current = int(time())
    if user.mfa_locked_until and user.mfa_locked_until > current:
        fail(429, "Too many verification attempts. Try again in five minutes.")
    if user.mfa_locked_until:
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
    encrypted = user.mfa_pending_secret_encrypted if pending else user.mfa_secret_encrypted
    if not encrypted:
        fail(400, "Two-factor authentication is not configured.")
    value = code.strip()
    step = matching_step(decrypt(encrypted), value, -1 if pending else user.mfa_last_step)
    valid = step is not None
    if valid:
        user.mfa_last_step = step
    elif not pending:
        normalized = value.replace("-", "").replace(" ", "").lower()
        hashes = json.loads(user.mfa_recovery_hashes)
        candidate = hashlib.sha256(normalized.encode()).hexdigest()
        for index, stored in enumerate(hashes):
            if hmac.compare_digest(candidate, stored):
                hashes.pop(index)
                user.mfa_recovery_hashes = json.dumps(hashes)
                valid = True
                break
    if not valid:
        user.mfa_failed_attempts += 1
        if user.mfa_failed_attempts >= 5:
            user.mfa_locked_until = current + 300
        # Persist the failure even though the request returns an error.
        db.commit()
        fail(401, "Invalid or already used code. Use a new app code or an unused recovery code.")
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None


def new_recovery_codes(user):
    codes = []
    hashes = []
    for _ in range(10):
        value = secrets.token_hex(10)
        codes.append("-".join(value[index : index + 5] for index in range(0, 20, 5)))
        hashes.append(hashlib.sha256(value.encode()).hexdigest())
    user.mfa_recovery_hashes = json.dumps(hashes)
    return codes


def setup(user, account_name, issuer, encrypt):
    if user.mfa_secret_encrypted:
        fail(409, "Two-factor authentication is already enabled.")
    secret = pyotp.random_base32()
    user.mfa_pending_secret_encrypted = encrypt(secret)
    user.mfa_pending_expires_at = int(time()) + 600
    uri = pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)
    image = qrcode.make(uri, image_factory=SvgPathImage, box_size=6, border=4)
    output = io.BytesIO()
    image.save(output)
    return {
        "secret": secret,
        "qr_code": "data:image/svg+xml;base64," + base64.b64encode(output.getvalue()).decode(),
        "expires_in": 600,
    }


def enable(db, user, code, decrypt):
    if user.mfa_secret_encrypted:
        fail(409, "Two-factor authentication is already enabled.")
    if not user.mfa_pending_expires_at or user.mfa_pending_expires_at <= int(time()):
        fail(400, "Setup has expired. Start two-factor setup again.")
    verify_code(db, user, code, decrypt, pending=True)
    user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_expires_at = None
    return new_recovery_codes(user)


def disable(db, user, code, decrypt):
    verify_code(db, user, code, decrypt)
    user.mfa_secret_encrypted = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_expires_at = None
    user.mfa_last_step = -1
    user.mfa_recovery_hashes = "[]"


def regenerate(db, user, code, decrypt):
    verify_code(db, user, code, decrypt)
    return new_recovery_codes(user)
