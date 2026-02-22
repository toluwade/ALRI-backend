from __future__ import annotations

from dataclasses import dataclass


ABNORMAL_STATUSES = {"low", "high", "critical", "borderline_low", "borderline_high"}

COMMON_MARKERS = [
    "glucose",
    "hba1c",
    "total_cholesterol",
    "ldl",
    "hdl",
    "triglycerides",
    "hemoglobin",
    "wbc",
    "creatinine",
    "tsh",
    "vitamin_d",
]


@dataclass
class PreviewSelection:
    marker_ids: list[str]


def select_preview_markers(markers: list[dict], *, max_items: int = 4) -> list[dict]:
    """Select 3-4 markers.

    Input: list of dicts containing at least {name, status}.
    Output: subset of markers.
    """
    if not markers:
        return []

    def canon(n: str) -> str:
        return (n or "").strip().lower().replace(" ", "_").replace("-", "_")

    abnormal = [m for m in markers if (m.get("status") or "").lower() in ABNORMAL_STATUSES]
    if abnormal:
        # Prefer critical/high/low first, then borderline.
        order = {"critical": 0, "high": 1, "low": 1, "borderline_high": 2, "borderline_low": 2}
        abnormal.sort(key=lambda m: order.get((m.get("status") or "").lower(), 99))
        return abnormal[:max_items]

    # If all normal, pick commonly understood markers.
    by_name = {canon(m.get("name")): m for m in markers}
    chosen: list[dict] = []
    for key in COMMON_MARKERS:
        if key in by_name and by_name[key] not in chosen:
            chosen.append(by_name[key])
        if len(chosen) >= max_items:
            break

    if chosen:
        return chosen

    return markers[:max_items]
