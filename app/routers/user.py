from __future__ import annotations

from fastapi import APIRouter, Depends

from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.user import CreditsResponse

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/credits", response_model=CreditsResponse)
async def credits(current_user: User = Depends(get_current_user)) -> CreditsResponse:
    return CreditsResponse(credits=current_user.credits)
