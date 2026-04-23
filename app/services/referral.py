"""Referral code generation + idempotent bonus crediting.

Reward policy (set 2026-04-23): credit the referrer the configured
`tariffs.referral_bonus_kobo` the moment a referee signs up. Idempotent via a
unique CreditTransaction reason string per referee.
"""
from __future__ import annotations

import logging
import random
import string
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditTransaction, User
from app.services.credit_manager import CreditManager
from app.services.tariff_loader import get_tariffs

logger = logging.getLogger(__name__)

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LEN_RANDOM = 6
CODE_MAX_LEN = 12


def _sanitize_prefix(raw: str | None, max_len: int = 4) -> str:
    if not raw:
        return ""
    clean = "".join(c for c in raw.upper() if c.isalnum())
    return clean[:max_len]


def _generate_code(first_name: str | None = None) -> str:
    """Coin a code from the user's first name + a short random suffix.

    "Tolu"    → "TOLU5K"
    "Micheal" → "MICH9X"
    None      → "A3K7XP"   (fallback: pure random)
    """
    prefix = _sanitize_prefix(first_name)
    if prefix:
        suffix_len = max(2, CODE_LEN_RANDOM - len(prefix))
        return prefix + "".join(random.choices(CODE_ALPHABET, k=suffix_len))
    return "".join(random.choices(CODE_ALPHABET, k=CODE_LEN_RANDOM))


def _first_name_from(user: User) -> str | None:
    if not user.name:
        return None
    parts = user.name.strip().split()
    return parts[0] if parts else None


async def ensure_referral_code(db: AsyncSession, user: User) -> str:
    """Guarantee the user has a referral_code. Returns the current one.

    For new users, seeds with their first name (e.g. TOLU5K). For users
    who already have a code from an earlier backfill, keep it as-is so
    existing shared links don't break.
    """
    if user.referral_code:
        return user.referral_code

    first_name = _first_name_from(user)

    for _ in range(10):
        code = _generate_code(first_name)
        if len(code) > CODE_MAX_LEN:
            continue
        existing = await db.execute(
            select(User.id).where(User.referral_code == code)
        )
        if existing.scalar_one_or_none() is None:
            user.referral_code = code
            await db.commit()
            await db.refresh(user)
            return code

    raise RuntimeError("Could not generate unique referral code after 10 attempts")


async def resolve_referrer(db: AsyncSession, code: str | None) -> User | None:
    if not code:
        return None
    code = code.strip().upper()
    if len(code) < 4 or len(code) > CODE_MAX_LEN:
        return None
    result = await db.execute(select(User).where(User.referral_code == code))
    return result.scalar_one_or_none()


def referral_reason(referee_id: uuid.UUID) -> str:
    """Unique reason string used for idempotent credit transactions."""
    return f"referral_bonus:{referee_id}"


async def award_referral_bonus(db: AsyncSession, referee: User) -> bool:
    """Credit the referrer — safe to call multiple times per referee.

    Idempotent: the first successful insert on reason=referral_bonus:{referee_id}
    wins; later calls short-circuit. Returns True if this call did the credit.
    Also prevents self-referral.
    """
    if not referee.referred_by:
        return False
    if referee.referred_by == referee.id:
        logger.warning("Blocked self-referral for user %s", referee.id)
        return False

    reason = referral_reason(referee.id)

    already = await db.execute(
        select(CreditTransaction.id).where(CreditTransaction.reason == reason).limit(1)
    )
    if already.scalar_one_or_none() is not None:
        return False

    referrer_result = await db.execute(
        select(User).where(User.id == referee.referred_by)
    )
    referrer = referrer_result.scalar_one_or_none()
    if not referrer:
        logger.warning(
            "Referee %s points to referrer %s which no longer exists",
            referee.id,
            referee.referred_by,
        )
        return False

    tariffs = await get_tariffs(db)
    bonus = tariffs.referral_bonus_kobo
    if bonus <= 0:
        return False

    await CreditManager(db).grant(
        user=referrer,
        amount=bonus,
        reason=reason,
    )
    logger.info(
        "Referral bonus: %s earned ₦%d for referring %s",
        referrer.id,
        bonus // 100,
        referee.id,
    )
    return True
