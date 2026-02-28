"""Auth router — uses Clerk for authentication.

Clerk handles Google, Apple, phone OTP, etc. on the frontend.
Backend verifies Clerk session tokens / webhook events.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.auth import MeResponse, TokenResponse, UserProfile
from app.services import email as email_svc
from app.utils.jwt import create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


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


async def _verify_clerk_token(session_token: str) -> dict:
    """Verify a Clerk session token and return user info."""
    if not settings.CLERK_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Clerk not configured")

    async with httpx.AsyncClient() as client:
        # Verify session with Clerk API
        resp = await client.get(
            "https://api.clerk.com/v1/sessions/verify",
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
            params={"token": session_token},
            timeout=10,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Clerk session")
        return resp.json()


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

    clerk_data = await _verify_clerk_token(session_token)
    clerk_user_id = clerk_data.get("user_id")

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
        user = User(
            email=email,
            phone=phone,
            name=name,
            avatar_url=avatar,
            auth_provider=provider,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Send welcome email
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

    token = create_access_token(user_id=user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=_to_profile(current_user))
