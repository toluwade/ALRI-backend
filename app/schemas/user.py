from __future__ import annotations

from pydantic import BaseModel


class CreditsResponse(BaseModel):
    balance_kobo: int
    balance_naira: float
    cost_per_scan_naira: int = 500
