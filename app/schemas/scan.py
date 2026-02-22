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


class PreviewResponse(BaseModel):
    preview_markers: list[MarkerOut]
    total_markers: int


class FullResponse(BaseModel):
    markers: list[MarkerOut]
    summary: str | None = None
    correlations: list[dict] | None = None
    report_url: str | None = None
