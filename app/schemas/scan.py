from __future__ import annotations

from pydantic import BaseModel

from app.schemas.marker import ManualMarkerIn, MarkerOut


class UploadResponse(BaseModel):
    scan_id: str
    status: str


class ManualScanRequest(BaseModel):
    markers: list[ManualMarkerIn]


class StatusResponse(BaseModel):
    status: str


class StatusCounts(BaseModel):
    normal: int = 0
    borderline_high: int = 0
    borderline_low: int = 0
    high: int = 0
    low: int = 0
    critical: int = 0


class PreviewResponse(BaseModel):
    preview_markers: list[MarkerOut]
    total_markers: int
    preview_summary: str | None = None
    status_counts: StatusCounts | None = None
    created_at: str | None = None


class FullResponse(BaseModel):
    markers: list[MarkerOut]
    summary: str | None = None
    correlations: list[dict] | None = None
    report_url: str | None = None
