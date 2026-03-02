from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CreditTransaction, Scan, User


class CreditManager:
    """Manages credit balance and credit transaction records.

    Pricing (kobo):
      - Scan unlock:         ₦200  (20 000 kobo)
      - Chat message:        ₦50   ( 5 000 kobo)
      - Skin analysis:       ₦250  (25 000 kobo)  — paid users only
      - Voice transcription:  ₦100  (10 000 kobo)  — paid users only
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_paid_user(user: User) -> bool:
        """True if user has ever topped up real money via Paystack."""
        return bool(user.has_topped_up)

    async def get_balance(self, user_id: uuid.UUID) -> int:
        res = await self.db.execute(select(User.credits).where(User.id == user_id))
        credits = res.scalar_one_or_none()
        if credits is None:
            raise HTTPException(status_code=404, detail="User not found")
        return int(credits)

    # ------------------------------------------------------------------
    # Scan unlock  (₦200 — everyone)
    # ------------------------------------------------------------------

    async def require_and_deduct_for_full_scan(self, *, user: User, scan: Scan) -> dict | None:
        """First-access charge for a full scan.  Idempotent via scan.credit_deducted.

        Returns deduction info dict on first charge, None if already charged.
        """

        if scan.credit_deducted:
            return None

        if scan.user_id != user.id:
            raise HTTPException(status_code=403, detail="Scan does not belong to current user")

        cost = settings.PRICE_SCAN_UNLOCK_KOBO
        if user.credits < cost:
            raise HTTPException(status_code=402, detail="Insufficient balance")

        user.credits -= cost
        scan.credit_deducted = True
        scan.full_unlocked = True

        self.db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-cost,
                reason="scan_used",
                scan_id=scan.id,
            )
        )

        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(scan)

        return {"amount_deducted_kobo": cost, "balance_after_kobo": user.credits}

    # ------------------------------------------------------------------
    # Chat message  (₦50 — everyone)
    # ------------------------------------------------------------------

    async def deduct_for_chat(self, *, user: User, scan_id: uuid.UUID) -> None:
        cost = settings.PRICE_CHAT_MESSAGE_KOBO
        if user.credits < cost:
            raise HTTPException(status_code=402, detail="Insufficient balance for chat message")

        user.credits -= cost
        self.db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-cost,
                reason="chat_used",
                scan_id=scan_id,
            )
        )
        await self.db.commit()
        await self.db.refresh(user)

    # ------------------------------------------------------------------
    # Skin analysis  (₦250 — paid users only)
    # ------------------------------------------------------------------

    async def deduct_for_skin_analysis(self, *, user: User) -> None:
        if not self.is_paid_user(user):
            raise HTTPException(
                status_code=403,
                detail="Skin analysis requires a funded account. Top up to unlock.",
            )

        cost = settings.PRICE_SKIN_ANALYSIS_KOBO
        if user.credits < cost:
            raise HTTPException(status_code=402, detail="Insufficient balance for skin analysis")

        user.credits -= cost
        self.db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-cost,
                reason="skin_analysis",
            )
        )
        await self.db.commit()
        await self.db.refresh(user)

    # ------------------------------------------------------------------
    # Voice transcription  (₦100 — paid users only)
    # ------------------------------------------------------------------

    async def deduct_for_voice(self, *, user: User, scan_id: uuid.UUID | None = None) -> None:
        if not self.is_paid_user(user):
            raise HTTPException(
                status_code=403,
                detail="Voice transcription requires a funded account. Top up to unlock.",
            )

        cost = settings.PRICE_VOICE_TRANSCRIPTION_KOBO
        if user.credits < cost:
            raise HTTPException(status_code=402, detail="Insufficient balance for voice transcription")

        user.credits -= cost
        self.db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-cost,
                reason="voice_used",
                scan_id=scan_id,
            )
        )
        await self.db.commit()
        await self.db.refresh(user)

    # ------------------------------------------------------------------
    # Grant (top-up / signup bonus)
    # ------------------------------------------------------------------

    async def grant(self, *, user: User, amount: int, reason: str, scan_id: uuid.UUID | None = None) -> None:
        if amount == 0:
            return

        user.credits += int(amount)
        self.db.add(CreditTransaction(user_id=user.id, amount=int(amount), reason=reason, scan_id=scan_id))
        await self.db.commit()
        await self.db.refresh(user)
