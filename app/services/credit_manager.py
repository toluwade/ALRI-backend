from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditTransaction, Scan, User
from app.models.tariff import Tariff
from app.services.notification_service import NotificationService
from app.services.tariff_loader import get_tariffs


class CreditManager:
    """Manages credit balance and credit transaction records.

    Pricing is loaded from the tariffs table (admin-configurable).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._tariffs: Tariff | None = None

    async def _get_tariffs(self) -> Tariff:
        if self._tariffs is None:
            self._tariffs = await get_tariffs(self.db)
        return self._tariffs

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
    # Scan unlock  (admin-configurable — default ₦200)
    # ------------------------------------------------------------------

    async def require_and_deduct_for_full_scan(self, *, user: User, scan: Scan) -> dict | None:
        """First-access charge for a full scan.  Idempotent via scan.credit_deducted.

        Returns deduction info dict on first charge, None if already charged.
        """

        if scan.credit_deducted:
            return None

        if scan.user_id != user.id:
            raise HTTPException(status_code=403, detail="Scan does not belong to current user")

        tariffs = await self._get_tariffs()
        cost = tariffs.cost_per_scan_unlock_kobo
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
        await NotificationService(self.db).create(
            user_id=user.id,
            type="credit_deducted",
            title="Scan Unlock",
            body=f"₦{cost // 100} deducted to unlock full scan results.",
            ref_id=str(scan.id),
        )

        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(scan)

        return {"amount_deducted_kobo": cost, "balance_after_kobo": user.credits}

    # ------------------------------------------------------------------
    # Chat message  (admin-configurable — default ₦50)
    # ------------------------------------------------------------------

    async def deduct_for_chat(self, *, user: User, scan_id: uuid.UUID) -> None:
        tariffs = await self._get_tariffs()
        cost = tariffs.cost_per_chat_kobo
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
        await NotificationService(self.db).create(
            user_id=user.id,
            type="credit_deducted",
            title="Chat Message",
            body=f"₦{cost // 100} deducted for a chat message.",
            ref_id=str(scan_id),
        )
        await self.db.commit()
        await self.db.refresh(user)

    # ------------------------------------------------------------------
    # Skin chat message  (same price as blood chat, separate reason)
    # ------------------------------------------------------------------

    async def deduct_for_skin_chat(self, *, user: User, skin_analysis_id: uuid.UUID) -> None:
        tariffs = await self._get_tariffs()
        cost = tariffs.cost_per_chat_kobo
        if user.credits < cost:
            raise HTTPException(status_code=402, detail="Insufficient balance for chat message")

        user.credits -= cost
        self.db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-cost,
                reason="skin_chat_used",
            )
        )
        await NotificationService(self.db).create(
            user_id=user.id,
            type="credit_deducted",
            title="Skin Chat Message",
            body=f"₦{cost // 100} deducted for a skin chat message.",
            ref_id=str(skin_analysis_id),
        )
        await self.db.commit()
        await self.db.refresh(user)

    # ------------------------------------------------------------------
    # File upload in chat  (admin-configurable — default ₦50)
    # ------------------------------------------------------------------

    async def deduct_for_file_upload(self, *, user: User, scan_id: uuid.UUID) -> None:
        tariffs = await self._get_tariffs()
        cost = tariffs.cost_per_file_upload_kobo
        if user.credits < cost:
            raise HTTPException(status_code=402, detail="Insufficient balance for file upload")

        user.credits -= cost
        self.db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-cost,
                reason="file_upload",
                scan_id=scan_id,
            )
        )
        await NotificationService(self.db).create(
            user_id=user.id,
            type="credit_deducted",
            title="File Upload",
            body=f"₦{cost // 100} deducted for file upload in chat.",
            ref_id=str(scan_id),
        )
        await self.db.commit()
        await self.db.refresh(user)

    # ------------------------------------------------------------------
    # Skin analysis  (admin-configurable — default ₦250, paid users only)
    # ------------------------------------------------------------------

    async def deduct_for_skin_analysis(self, *, user: User) -> None:
        if not self.is_paid_user(user):
            raise HTTPException(
                status_code=403,
                detail="Skin analysis requires a funded account. Top up to unlock.",
            )

        tariffs = await self._get_tariffs()
        cost = tariffs.cost_per_skin_analysis_kobo
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
        await NotificationService(self.db).create(
            user_id=user.id,
            type="credit_deducted",
            title="Skin Analysis",
            body=f"₦{cost // 100} deducted for skin analysis.",
        )
        await self.db.commit()
        await self.db.refresh(user)

    # ------------------------------------------------------------------
    # Voice transcription  (admin-configurable — default ₦100, paid users only)
    # ------------------------------------------------------------------

    async def deduct_for_voice(self, *, user: User, scan_id: uuid.UUID | None = None) -> None:
        if not self.is_paid_user(user):
            raise HTTPException(
                status_code=403,
                detail="Voice transcription requires a funded account. Top up to unlock.",
            )

        tariffs = await self._get_tariffs()
        cost = tariffs.cost_per_transcription_kobo
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
        await NotificationService(self.db).create(
            user_id=user.id,
            type="credit_deducted",
            title="Voice Transcription",
            body=f"₦{cost // 100} deducted for voice transcription.",
            ref_id=str(scan_id) if scan_id else None,
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
        await NotificationService(self.db).create(
            user_id=user.id,
            type="credit_received",
            title="Credits Received",
            body=f"₦{amount // 100:,} credited: {reason.replace('_', ' ').title()}",
        )
        await self.db.commit()
        await self.db.refresh(user)
