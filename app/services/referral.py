"""Referral code generation + idempotent bonus crediting."""
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
CODE_LEN = 6


def _generate_code() -> str:
    return "".join(random.choices(CODE_ALPHABET, k=CODE_LEN))


async def ensure_referral_code(db: AsyncSession, user: User) -> str:
    """Guarantee the user has a referral_code. Returns the current one."""
    if user.referral_code:
        return user.referral_code

    for _ in range(10):
        code = _generate_code()
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
    if len(code) < 4 or len(code) > 12:
        return None
    result = await db.execute(select(User).where(User.referral_code == code))
    return result.scalar_one_or_none()


def referral_reason(referee_id: uuid.UUID) -> str:
    """Unique reason string used for idempotent credit transactions."""
    return f"referral_bonus:{referee_id}"


async def award_referral_bonus_if_first_topup(
    db: AsyncSession, referee: User
) -> bool:
    """Called after a referee completes a top-up.

    Credits the referrer (if any) the configured referral_bonus_kobo. Idempotent:
    the CreditTransaction row uses a fixed reason string per referee, so even if
    called multiple times only the first successful insert credits the referrer.
    Returns True if a credit was granted this call.
    """
    if not referee.referred_by:
        return False

    reason = referral_reason(referee.id)

    # Idempotency check — skip if we've already awarded for this referee.
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
