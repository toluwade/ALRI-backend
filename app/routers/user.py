from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import CreditTransaction, User
from app.schemas.user import CreditsResponse
from app.services.paystack import initialize_transaction

router = APIRouter(prefix="/user", tags=["user"])


class FundRequest(BaseModel):
    amount_naira: int = Field(..., ge=100, description="Amount to fund in Naira")
    callback_url: str | None = None


class FundResponse(BaseModel):
    authorization_url: str
    access_code: str
    reference: str


@router.get("/credits", response_model=CreditsResponse)
async def credits(current_user: User = Depends(get_current_user)) -> CreditsResponse:
    bal = int(current_user.credits)
    return CreditsResponse(
        balance_kobo=bal,
        balance_naira=bal / 100.0,
        cost_per_scan_naira=500,
    )


@router.post("/fund", response_model=FundResponse)
async def fund_account(
    body: FundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FundResponse:
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Paystack not configured")

    if not current_user.email:
        raise HTTPException(status_code=400, detail="Email required to fund account")

    amount_kobo = int(body.amount_naira) * 100
    if amount_kobo <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    reference = f"alri_fund_{current_user.id.hex}_{uuid.uuid4().hex[:10]}"

    data = await initialize_transaction(
        email=current_user.email,
        amount_kobo=amount_kobo,
        reference=reference,
        metadata={
            "user_id": str(current_user.id),
            "amount_kobo": amount_kobo,
            "kind": "fund",
        },
        callback_url=body.callback_url or f"{settings.APP_URL.rstrip('/')}/dashboard",
    )

    # record intent (optional) to allow idempotency checks later
    db.add(
        CreditTransaction(
            user_id=current_user.id,
            amount=0,
            reason=f"paystack_init:{reference}"[:50],
            scan_id=None,
        )
    )
    await db.commit()

    return FundResponse(
        authorization_url=data["authorization_url"],
        access_code=data["access_code"],
        reference=data["reference"],
    )
