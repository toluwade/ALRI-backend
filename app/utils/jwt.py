from __future__ import annotations

import datetime as dt
import uuid

import jwt

from app.config import settings


def create_access_token(*, user_id: uuid.UUID) -> str:
    now = dt.datetime.now(tz=dt.timezone.utc)
    exp = now + dt.timedelta(minutes=settings.JWT_EXPIRES_MINUTES)
    payload = {"sub": str(user_id), "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
