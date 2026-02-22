from __future__ import annotations

from pydantic import BaseModel, Field


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., description="Google ID token from client")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: str
    email: str | None = None
    phone: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    auth_provider: str | None = None
    age: int | None = None
    sex: str | None = None
    credits: int


class MeResponse(BaseModel):
    user: UserProfile
