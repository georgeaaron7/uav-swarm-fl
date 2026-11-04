from __future__ import annotations

import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from . import models as m
from .database import get, insert, rows

hasher = PasswordHasher()


def token():
    return secrets.token_urlsafe(32)


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def uid():
    return secrets.token_hex(16)


def new_user(c, username, role="owner", password=None):
    password = password or token()
    user = insert(
        c,
        m.users,
        id=uid(),
        username=username,
        data={
            "password_hash": hasher.hash(password),
            "role": role,
            "created": time.time(),
        },
    )
    return user, password


def login(c, username, password):
    user = next((u for u in rows(c, m.users) if u["username"] == username), None)
    # A dummy verification prevents cheap account-enumeration timing differences.
    digest = user["data"]["password_hash"] if user else hasher.hash(token())
    try:
        hasher.verify(digest, password)
    except (VerificationError, InvalidHashError):
        return None
    if not user:
        return None
    credential = token()
    insert(
        c,
        m.sessions,
        id=fingerprint(credential),
        user_id=user["id"],
        expires=time.time() + 12 * 3600,
        data={},
    )
    return credential


def principal(c, credential):
    key = fingerprint(credential)
    session = get(c, m.sessions, key)
    if session and session["expires"] > time.time():
        user = get(c, m.users, session["user_id"])
        return {
            "id": user["id"],
            "role": user["data"]["role"],
            "username": user["username"],
        }
    worker = next(
        (
            w
            for w in rows(c, m.workers)
            if w["data"].get("credential_hash") == key and not w["data"].get("revoked")
        ),
        None,
    )
    if worker:
        return {"id": worker["id"], "role": "worker", "owner_id": worker["owner_id"]}
    return None
