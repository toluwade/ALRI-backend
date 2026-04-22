"""Google Places API (New) wrapper with Redis caching.

Uses the v1 Places API — cheaper than the legacy Places API and supports
field masks so we only pay for the fields we actually use.

Docs: https://developers.google.com/maps/documentation/places/web-service/nearby-search
"""
from __future__ import annotations

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PLACES_API = "https://places.googleapis.com/v1"

# Keep field masks TIGHT — each field billed separately. These cover list + card.
NEARBY_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.types",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
        "places.currentOpeningHours.openNow",
    ]
)

DETAIL_FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "primaryType",
        "types",
        "rating",
        "userRatingCount",
        "internationalPhoneNumber",
        "websiteUri",
        "googleMapsUri",
        "currentOpeningHours",
        "businessStatus",
    ]
)

# Health-related Places types we expose in the filter.
# Full type list: https://developers.google.com/maps/documentation/places/web-service/place-types
CARE_TYPES = {
    "doctor": "doctor",
    "hospital": "hospital",
    "dental_clinic": "dental_clinic",
    "dentist": "dentist",
    "pharmacy": "pharmacy",
    "physiotherapist": "physiotherapist",
    "medical_lab": "medical_lab",
}

CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 hours


def _round_latlng(value: float) -> str:
    # ~110m resolution at the equator; adjacent users hit the same cache.
    return f"{value:.3f}"


async def _redis():
    from redis.asyncio import Redis

    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def search_nearby(
    *,
    lat: float,
    lng: float,
    radius_m: int = 3000,
    place_type: str = "doctor",
    max_results: int = 20,
) -> list[dict]:
    if place_type not in CARE_TYPES:
        raise ValueError(f"Unsupported care type: {place_type}")
    if not settings.GOOGLE_PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not configured")

    cache_key = (
        f"places:nearby:{place_type}:{_round_latlng(lat)}:"
        f"{_round_latlng(lng)}:{radius_m}:{max_results}"
    )
    redis = await _redis()
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning("Redis cache read failed: %s", e)

    body = {
        "includedTypes": [CARE_TYPES[place_type]],
        "maxResultCount": max_results,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_m,
            }
        },
        "rankPreference": "DISTANCE",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PLACES_API}/places:searchNearby",
            headers={
                "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
                "X-Goog-FieldMask": NEARBY_FIELD_MASK,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.error("Places nearby error %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        places = resp.json().get("places", [])

    try:
        await redis.set(cache_key, json.dumps(places), ex=CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning("Redis cache write failed: %s", e)

    return places


async def get_place_details(place_id: str) -> dict:
    if not settings.GOOGLE_PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not configured")

    cache_key = f"places:detail:{place_id}"
    redis = await _redis()
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning("Redis cache read failed: %s", e)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PLACES_API}/places/{place_id}",
            headers={
                "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
                "X-Goog-FieldMask": DETAIL_FIELD_MASK,
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.error("Places detail error %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()

    try:
        await redis.set(cache_key, json.dumps(data), ex=CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning("Redis cache write failed: %s", e)

    return data
