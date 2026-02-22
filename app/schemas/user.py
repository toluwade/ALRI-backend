from __future__ import annotations

from pydantic import BaseModel


class CreditsResponse(BaseModel):
    credits: int
