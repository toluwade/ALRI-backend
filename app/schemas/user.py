from __future__ import annotations

from pydantic import BaseModel, Field


class PricingInfo(BaseModel):
    scan_unlock_naira: float
    chat_message_naira: float
    skin_analysis_naira: float
    voice_transcription_naira: float


class UserTierInfo(BaseModel):
    is_paid_user: bool
    chat_char_limit: int
    chat_max_messages: int
    can_use_skin_analysis: bool
    can_use_voice: bool


class CreditsResponse(BaseModel):
    balance_kobo: int
    balance_naira: float
    pricing: PricingInfo
    tier: UserTierInfo


class UpdateProfileRequest(BaseModel):
    age: int = Field(..., ge=1, le=150)
    sex: str = Field(..., pattern=r"^(male|female)$")
    weight_kg: float | None = Field(None, ge=1, le=500)
    height_cm: float | None = Field(None, ge=30, le=300)


class UpdateProfileResponse(BaseModel):
    ok: bool
    age: int
    sex: str
    weight_kg: float | None
    height_cm: float | None
