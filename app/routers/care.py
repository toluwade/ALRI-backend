"""Find Care router — proxy to Google Places for doctor/clinic discovery.

All calls require an authenticated ALRI user so we keep the Places API
key server-side and can rate-limit per user.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.user import User
from app.routers.auth import get_current_user
from app.services.google_places import (
    CARE_TYPES,
    get_place_details,
    search_nearby,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/care", tags=["care"])


class NearbyPlace(BaseModel):
    id: str
    name: str
    address: str | None = None
    lat: float
    lng: float
    primary_type: str | None = None
    types: list[str] = []
    rating: float | None = None
    user_rating_count: int | None = None
    open_now: bool | None = None
    business_status: str | None = None


class NearbyResponse(BaseModel):
    places: list[NearbyPlace]
    center: dict
    radius_m: int
    type: str


class PlaceDetails(BaseModel):
    id: str
    name: str
    address: str | None = None
    lat: float
    lng: float
    primary_type: str | None = None
    types: list[str] = []
    rating: float | None = None
    user_rating_count: int | None = None
    phone: str | None = None
    website: str | None = None
    google_maps_uri: str | None = None
    business_status: str | None = None
    opening_hours_weekday_text: list[str] = []


def _place_to_nearby(p: dict) -> NearbyPlace:
    loc = p.get("location") or {}
    name = (p.get("displayName") or {}).get("text", "")
    hours = p.get("currentOpeningHours") or {}
    return NearbyPlace(
        id=p.get("id", ""),
        name=name,
        address=p.get("formattedAddress"),
        lat=loc.get("latitude", 0.0),
        lng=loc.get("longitude", 0.0),
        primary_type=p.get("primaryType"),
        types=p.get("types", []),
        rating=p.get("rating"),
        user_rating_count=p.get("userRatingCount"),
        open_now=hours.get("openNow") if hours else None,
        business_status=p.get("businessStatus"),
    )


def _place_to_details(p: dict) -> PlaceDetails:
    loc = p.get("location") or {}
    name = (p.get("displayName") or {}).get("text", "")
    hours = p.get("currentOpeningHours") or {}
    return PlaceDetails(
        id=p.get("id", ""),
        name=name,
        address=p.get("formattedAddress"),
        lat=loc.get("latitude", 0.0),
        lng=loc.get("longitude", 0.0),
        primary_type=p.get("primaryType"),
        types=p.get("types", []),
        rating=p.get("rating"),
        user_rating_count=p.get("userRatingCount"),
        phone=p.get("internationalPhoneNumber"),
        website=p.get("websiteUri"),
        google_maps_uri=p.get("googleMapsUri"),
        business_status=p.get("businessStatus"),
        opening_hours_weekday_text=hours.get("weekdayDescriptions") or [],
    )


@router.get("/nearby", response_model=NearbyResponse)
async def nearby(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(3000, ge=500, le=50000),
    type: str = Query("doctor", description=f"one of: {', '.join(CARE_TYPES)}"),
    max_results: int = Query(20, ge=1, le=20),
    _user: User = Depends(get_current_user),
) -> NearbyResponse:
    if type not in CARE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {type}")

    try:
        raw = await search_nearby(
            lat=lat,
            lng=lng,
            radius_m=radius_m,
            place_type=type,
            max_results=max_results,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Places search failed")
        raise HTTPException(status_code=502, detail=f"Places lookup failed: {e}")

    return NearbyResponse(
        places=[_place_to_nearby(p) for p in raw],
        center={"lat": lat, "lng": lng},
        radius_m=radius_m,
        type=type,
    )


@router.get("/place/{place_id}", response_model=PlaceDetails)
async def place_details(
    place_id: str,
    _user: User = Depends(get_current_user),
) -> PlaceDetails:
    try:
        raw = await get_place_details(place_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Place details failed")
        raise HTTPException(status_code=502, detail=f"Place lookup failed: {e}")

    return _place_to_details(raw)
