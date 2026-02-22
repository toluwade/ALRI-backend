from __future__ import annotations

from pydantic import BaseModel


class ManualMarkerIn(BaseModel):
    marker: str
    value: float
    unit: str | None = None


class MarkerOut(BaseModel):
    name: str | None = None
    value: float | None = None
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    status: str | None = None
    explanation: str | None = None
    is_preview: bool = False
