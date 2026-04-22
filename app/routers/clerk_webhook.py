"""Clerk webhook handler — sync user locale/currency prefs into our DB.

Subscribes to user.created / user.updated events from Clerk. Clerk signs
webhooks with svix; we verify HMAC-SHA256 manually so we don't add the
svix dependency.

Header format:
    svix-id:         <msg_id>
    svix-timestamp:  <unix_seconds>
    svix-signature:  "v1,<base64_sig> v1,<another>"
Signed payload:   "{svix-id}.{svix-timestamp}.{body}"
Secret is `whsec_<base64>` from Clerk dashboard.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])

SUPPORTED_LOCALES = {"en", "fr", "de", "nl", "es"}
SUPPORTED_CURRENCIES = {"NGN", "USD", "EUR", "GBP", "USDT"}


def _verify_svix_signature(
    payload: bytes, headers: dict, secret: str, tolerance_seconds: int = 300
) -> bool:
    svix_id = headers.get("svix-id") or headers.get("Svix-Id")
    svix_timestamp = headers.get("svix-timestamp") or headers.get("Svix-Timestamp")
    svix_signature = headers.get("svix-signature") or headers.get("Svix-Signature")

    if not (svix_id and svix_timestamp and svix_signature):
        return False

    try:
        if abs(time.time() - int(svix_timestamp)) > tolerance_seconds:
            return False
    except ValueError:
        return False

    secret_bytes = base64.b64decode(secret.removeprefix("whsec_"))
    message = f"{svix_id}.{svix_timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(secret_bytes, message, hashlib.sha256).digest()).decode()

    # Header may have multiple signatures "v1,sig1 v1,sig2" — accept any match.
    for chunk in svix_signature.split(" "):
        if "," not in chunk:
            continue
        _version, received = chunk.split(",", 1)
        if hmac.compare_digest(expected, received):
            return True
    return False


def _pick(metadata: dict | None, key: str) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) else None


@router.post("/clerk")
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.CLERK_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Clerk webhook secret not configured")

    raw = await request.body()
    if not _verify_svix_signature(raw, dict(request.headers), settings.CLERK_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(raw)
    etype = event.get("type")
    data = event.get("data") or {}

    if etype not in {"user.created", "user.updated"}:
        return {"ok": True, "ignored": etype}

    clerk_user_id = data.get("id")
    if not clerk_user_id:
        return {"ok": True, "note": "no user id"}

    # Extract preferences from public + unsafe metadata. unsafeMetadata wins
    # because it's the client-settable one (used by our LocaleSwitcher / useCurrency).
    public_meta = data.get("public_metadata") or {}
    unsafe_meta = data.get("unsafe_metadata") or {}

    raw_locale = _pick(unsafe_meta, "preferred_locale") or _pick(public_meta, "preferred_locale")
    raw_currency = _pick(unsafe_meta, "preferred_currency") or _pick(public_meta, "preferred_currency")

    preferred_locale = (
        raw_locale if raw_locale in SUPPORTED_LOCALES else None
    )
    preferred_currency = (
        raw_currency.upper() if raw_currency and raw_currency.upper() in SUPPORTED_CURRENCIES else None
    )

    # Match user by email (our DB keys on email; Clerk webhooks include email addresses)
    emails = data.get("email_addresses") or []
    primary_email = None
    for e in emails:
        if e.get("id") == data.get("primary_email_address_id"):
            primary_email = e.get("email_address")
            break
    if not primary_email and emails:
        primary_email = emails[0].get("email_address")

    if not primary_email:
        return {"ok": True, "note": "no primary email"}

    result = await db.execute(select(User).where(User.email == primary_email.lower()))
    user = result.scalar_one_or_none()
    if not user:
        logger.info("Clerk webhook for user not yet in DB: %s", primary_email)
        return {"ok": True, "note": "user not in db"}

    changed = False
    if preferred_locale and user.preferred_locale != preferred_locale:
        user.preferred_locale = preferred_locale
        changed = True
    if preferred_currency and user.preferred_currency != preferred_currency:
        user.preferred_currency = preferred_currency
        changed = True

    if changed:
        await db.commit()
        logger.info(
            "Synced Clerk prefs for %s: locale=%s currency=%s",
            primary_email,
            preferred_locale,
            preferred_currency,
        )

    return {"ok": True, "changed": changed}
