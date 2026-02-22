from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from google.auth.transport import requests as grequests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.auth import GoogleAuthRequest, MeResponse, TokenResponse, UserProfile
from app.utils.jwt import create_access_token

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


@router.post("/google", response_model=TokenResponse)
async def google_sign_in(payload: GoogleAuthRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured")

    try:
        info = id_token.verify_oauth2_token(payload.id_token, grequests.Request(), settings.GOOGLE_CLIENT_ID)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    email = info.get("email")
    name = info.get("name")
    picture = info.get("picture")

    if not email:
        raise HTTPException(status_code=400, detail="Google token missing email")

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(email=email, name=name, avatar_url=picture, auth_provider="google")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # update basic info
        user.name = name or user.name
        user.avatar_url = picture or user.avatar_url
        user.auth_provider = user.auth_provider or "google"
        await db.commit()

    token = create_access_token(user_id=user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=_to_profile(current_user))
