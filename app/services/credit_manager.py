from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditTransaction, Scan, User


# Balance rules (stored in kobo)
INITIAL_BALANCE_KOBO = 500_000  # ₦5,000 signup bonus
COST_PER_FULL_SCAN_KOBO = 50_000  # ₦500 per scan unlock


class CreditManager:
    """Manages credit balance and credit transaction records.

    Rule: /scan/{id}/full costs 1 credit on *first access per scan*.
    Subsequent views are free (scan.credit_deducted == True).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_balance(self, user_id: uuid.UUID) -> int:
        res = await self.db.execute(select(User.credits).where(User.id == user_id))
        credits = res.scalar_one_or_none()
        if credits is None:
            raise HTTPException(status_code=404, detail="User not found")
        return int(credits)

    async def require_and_deduct_for_full_scan(self, *, user: User, scan: Scan) -> None:
        """Enforces credit payment for full scan access.

        - If scan.credit_deducted already True -> no charge.
        - Else charge COST_PER_FULL_SCAN, fail if insufficient credits.
        - Records CreditTransaction with reason='scan_used'.
        """

        if scan.credit_deducted:
            return

        # Ensure scan belongs to user (avoid charging user for someone else's scan)
        if scan.user_id != user.id:
            raise HTTPException(status_code=403, detail="Scan does not belong to current user")

        if user.credits < COST_PER_FULL_SCAN_KOBO:
            raise HTTPException(status_code=402, detail="Insufficient balance")

        user.credits -= COST_PER_FULL_SCAN_KOBO
        scan.credit_deducted = True
        scan.full_unlocked = True

        self.db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-COST_PER_FULL_SCAN_KOBO,
                reason="scan_used",
                scan_id=scan.id,
            )
        )

        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(scan)

    async def grant(self, *, user: User, amount: int, reason: str, scan_id: uuid.UUID | None = None) -> None:
        if amount == 0:
            return

        user.credits += int(amount)
        self.db.add(CreditTransaction(user_id=user.id, amount=int(amount), reason=reason, scan_id=scan_id))
        await self.db.commit()
        await self.db.refresh(user)

