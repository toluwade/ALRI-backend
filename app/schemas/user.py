from __future__ import annotations

from pydantic import BaseModel


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
