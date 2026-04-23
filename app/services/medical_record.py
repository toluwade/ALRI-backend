"""Medical record aggregation — builds a unified view of a user's health data.

Combines: profile, all completed scans (with markers + interpretations),
skin analyses, and biomarker trends across scans.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Scan, SkinAnalysis, User
from app.models.interpretation import Interpretation
from app.models.marker import Marker


def _to_iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def build_medical_record(db: AsyncSession, user_id: uuid.UUID) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return {"error": "User not found"}

    # Scans (completed only — don't leak unfinished ones)
    scans_rows = (
        await db.execute(
            select(Scan)
            .where(Scan.user_id == user_id, Scan.status == "completed")
            .order_by(Scan.created_at.desc())
        )
    ).scalars().all()

    scan_ids = [s.id for s in scans_rows]

    # Load markers for all scans in one go
    markers_by_scan: dict[uuid.UUID, list[Marker]] = defaultdict(list)
    if scan_ids:
        marker_rows = (
            await db.execute(select(Marker).where(Marker.scan_id.in_(scan_ids)))
        ).scalars().all()
        for m in marker_rows:
            markers_by_scan[m.scan_id].append(m)

    # Load interpretations
    interpretations_by_scan: dict[uuid.UUID, Interpretation] = {}
    if scan_ids:
        interp_rows = (
            await db.execute(
                select(Interpretation).where(Interpretation.scan_id.in_(scan_ids))
            )
        ).scalars().all()
        for i in interp_rows:
            interpretations_by_scan[i.scan_id] = i

    scans = []
    for s in scans_rows:
        markers = markers_by_scan.get(s.id, [])
        interp = interpretations_by_scan.get(s.id)
        scans.append(
            {
                "id": str(s.id),
                "date": _to_iso(s.created_at),
                "input_type": s.input_type,
                "source": s.source,
                "marker_count": len(markers),
                "full_unlocked": s.full_unlocked,
                "markers": [
                    {
                        "id": str(m.id),
                        "name": m.name,
                        "value": float(m.value) if m.value is not None else None,
                        "unit": m.unit,
                        "reference_low": float(m.reference_low)
                        if m.reference_low is not None
                        else None,
                        "reference_high": float(m.reference_high)
                        if m.reference_high is not None
                        else None,
                        "status": m.status,
                    }
                    for m in markers
                ],
                "summary": interp.summary if interp else None,
                "correlations": interp.correlations if interp else None,
            }
        )

    # Skin analyses
    skin_rows = (
        await db.execute(
            select(SkinAnalysis)
            .where(
                SkinAnalysis.user_id == user_id,
                SkinAnalysis.status == "completed",
            )
            .order_by(SkinAnalysis.created_at.desc())
        )
    ).scalars().all()

    skin_analyses = [
        {
            "id": str(sa.id),
            "date": _to_iso(sa.created_at),
            "result": sa.analysis_result,
        }
        for sa in skin_rows
    ]

    # Biomarker trends — any marker that appears in 2+ completed + unlocked scans
    # (skip preview values; we want the real data)
    trends: dict[str, list[dict]] = defaultdict(list)
    for s in scans_rows:
        if not s.full_unlocked:
            continue
        for m in markers_by_scan.get(s.id, []):
            if m.name and m.value is not None and not m.is_preview:
                trends[m.name].append(
                    {
                        "value": float(m.value),
                        "unit": m.unit,
                        "status": m.status,
                        "reference_low": float(m.reference_low)
                        if m.reference_low is not None
                        else None,
                        "reference_high": float(m.reference_high)
                        if m.reference_high is not None
                        else None,
                        "date": _to_iso(s.created_at),
                        "scan_id": str(s.id),
                    }
                )

    # Keep only markers with 2+ data points and sort chronologically (oldest first)
    trend_list = []
    for name, points in trends.items():
        if len(points) >= 2:
            points.sort(key=lambda p: p["date"] or "")
            trend_list.append({"name": name, "points": points})

    trend_list.sort(key=lambda t: t["name"])

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "profile": {
            "name": user.name,
            "email": user.email,
            "age": user.age,
            "sex": user.sex,
            "weight_kg": float(user.weight_kg) if user.weight_kg else None,
            "height_cm": float(user.height_cm) if user.height_cm else None,
            "preferred_locale": user.preferred_locale,
            "preferred_currency": user.preferred_currency,
        },
        "counts": {
            "scans": len(scans),
            "skin_analyses": len(skin_analyses),
            "tracked_markers": len(trend_list),
        },
        "scans": scans,
        "skin_analyses": skin_analyses,
        "trends": trend_list,
    }
