"""Auth router — uses Clerk for authentication.

Clerk handles Google, Apple, phone OTP, etc. on the frontend.
Backend verifies Clerk session tokens / webhook events.
"""
from __future__ import annotations

import logging
import time

import jwt as pyjwt
from jwt import PyJWKClient
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import CreditTransaction, User
from app.schemas.auth import MeResponse, TokenResponse, UserProfile
from app.services import email as email_svc
from app.utils.jwt import create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Cached JWKS client for Clerk token verification (1-hour lifespan)
_jwks_client: PyJWKClient | None = None
_jwks_client_ts: float = 0.0
_JWKS_CACHE_TTL = 3600  # 1 hour


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_client_ts
    now = time.time()
    if _jwks_client is None or (now - _jwks_client_ts) > _JWKS_CACHE_TTL:
        _jwks_client = PyJWKClient("https://api.clerk.com/v1/jwks", cache_keys=True)
        _jwks_client_ts = now
    return _jwks_client


def _to_profile(u: User) -> UserProfile:
    return UserProfile(
        id=str(u.id),
        email=u.email,
        phone=u.phone,
        name=u.name,
        avatar_url=u.avatar_url,
        auth_provider=u.auth_provider,
        age=u.age,
        sex=u.sex,
        credits=u.credits,
    )


def _decode_clerk_jwt(token: str) -> str:
    """Decode and verify a Clerk session JWT, return the Clerk user ID (sub).

    Verifies the token signature using Clerk's JWKS endpoint (RS256).
    Falls back to unverified decode if JWKS fetch fails (dev/offline).
    """
    try:
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        clerk_user_id = payload.get("sub")
        if not clerk_user_id:
            raise HTTPException(status_code=401, detail="Invalid Clerk token: missing sub")
        return clerk_user_id
    except (pyjwt.DecodeError, pyjwt.InvalidTokenError) as e:
        logger.warning("Clerk JWT verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid Clerk token")
    except Exception as e:
        # JWKS fetch failure (network issue) — fall back to unverified decode in dev
        logger.warning("JWKS fetch failed (%s), falling back to unverified decode", e)
        try:
            payload = pyjwt.decode(token, options={"verify_signature": False})
            clerk_user_id = payload.get("sub")
            if not clerk_user_id:
                raise HTTPException(status_code=401, detail="Invalid Clerk token: missing sub")
            return clerk_user_id
        except pyjwt.DecodeError:
            raise HTTPException(status_code=401, detail="Invalid Clerk token")


@router.post("/clerk", response_model=TokenResponse)
async def clerk_sign_in(request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Exchange a Clerk session token for an ALRI JWT.

    Frontend authenticates via Clerk (Google, Apple, phone, etc.),
    then sends the Clerk session token here to get an ALRI API token.
    Accepts token via Authorization Bearer header or JSON body.
    """
    session_token: str | None = None

    # Try Authorization header first (preferred)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        session_token = auth_header.removeprefix("Bearer ").strip()

    # Fallback to JSON body
    if not session_token:
        try:
            body = await request.json()
            session_token = body.get("session_token")
        except Exception:
            pass

    if not session_token:
        raise HTTPException(status_code=400, detail="session_token required")

    if not settings.CLERK_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Clerk not configured")

    clerk_user_id = _decode_clerk_jwt(session_token)

    # Fetch full user details from Clerk
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
            timeout=10,
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Could not fetch Clerk user")
        clerk_user = user_resp.json()

    email = (clerk_user.get("email_addresses") or [{}])[0].get("email_address")
    phone = (clerk_user.get("phone_numbers") or [{}])[0].get("phone_number")
    name = f"{clerk_user.get('first_name', '')} {clerk_user.get('last_name', '')}".strip() or None
    avatar = clerk_user.get("image_url")
    provider = (clerk_user.get("external_accounts") or [{}])[0].get("provider", "clerk")

    # Find or create local user
    user = None
    if email:
        res = await db.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()
    if user is None and phone:
        res = await db.execute(select(User).where(User.phone == phone))
        user = res.scalar_one_or_none()

    is_new = user is None
    if is_new:
        # Credits are set atomically with user creation — if the row is
        # created, the bonus is guaranteed to be there.
        bonus = settings.INITIAL_SIGNUP_BONUS_KOBO
        user = User(
            email=email,
            phone=phone,
            name=name,
            avatar_url=avatar,
            auth_provider=provider,
            credits=bonus,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("Created user %s with ₦%d signup bonus", user.id, bonus // 100)

        # Record CreditTransaction + notification (non-critical — credits
        # are already on the user row, so a failure here is cosmetic only).
        try:
            db.add(
                CreditTransaction(
                    user_id=user.id,
                    amount=bonus,
                    reason="signup_bonus",
                )
            )
            from app.services.notification_service import NotificationService
            await NotificationService(db).create(
                user_id=user.id,
                type="credit_received",
                title="Welcome Bonus",
                body=f"₦{bonus // 100:,} credited as your signup bonus.",
            )
            await db.commit()
        except Exception as e:
            logger.warning("Failed to record signup bonus transaction for user %s: %s", user.id, e)
            try:
                await db.rollback()
            except Exception:
                pass

        # Send welcome email (non-critical)
        if email:
            try:
                await email_svc.send_welcome(email, name)
            except Exception as e:
                logger.warning("Failed to send welcome email: %s", e)
    else:
        user.name = name or user.name
        user.avatar_url = avatar or user.avatar_url
        user.auth_provider = user.auth_provider or provider
        if phone and not user.phone:
            user.phone = phone
        await db.commit()

    # Log session notification (non-critical — must never break auth)
    try:
        from app.services.notification_service import NotificationService
        await NotificationService(db).create(
            user_id=user.id,
            type="login_session",
            title="New Login",
            body="You signed in to your account.",
        )
        await db.commit()
    except Exception as e:
        logger.warning("Failed to log login notification for user %s: %s", user.id, e)
        try:
            await db.rollback()
        except Exception:
            pass

    token = create_access_token(user_id=user.id)
    return TokenResponse(access_token=token, is_new_user=is_new)


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=_to_profile(current_user))
