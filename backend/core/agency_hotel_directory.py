"""Hotel directory of the agency extranet ("marketplace" in code).

Every active Syroce PMS hotel is visible to every agency so the agency can
send it a contract proposal. Visibility exposes no prices, allotment or
bookings: those require a hotel-approved contract. A hotel may opt out of the
directory (``marketplace_listings.is_listed == False``); that only hides it
from discovery and new proposals, existing approved contracts keep working.

A hotel does not need a ``marketplace_listings`` document: its profile is
derived from the tenant and its distributed content (``hotel_content``), with
listing fields taking precedence when present.
"""

from __future__ import annotations

TEASER_FIELDS = ("tenant_id", "hotel_name", "city", "country", "star_rating", "meal_plans",
                 "room_type_names", "cover_photo", "summary", "currency")


def tenant_is_active(tenant: dict | None) -> bool:
    return bool(tenant) and tenant.get("is_active") is not False and (tenant.get("subscription_status") or "active") == "active"


def _profile(tenant: dict, listing: dict | None, content: dict | None, currency: str) -> dict:
    listing = listing or {}
    content = content or {}
    photos = listing.get("photos") or content.get("images") or []
    description = listing.get("description") or content.get("description") or ""
    profile = {
        **listing,
        "tenant_id": tenant["id"],
        "hotel_name": listing.get("hotel_name") or content.get("hotel_name") or tenant.get("property_name") or "Otel",
        "city": listing.get("city") or content.get("city") or tenant.get("location") or "",
        "country": (listing.get("country") or content.get("country") or "TR").upper(),
        "star_rating": listing.get("star_rating") or content.get("star_rating"),
        "meal_plans": listing.get("meal_plans") or content.get("meal_plans") or [],
        "photos": photos,
        "description": description,
        "amenities": listing.get("amenities") or content.get("amenities") or [],
        "currency": (listing.get("currency") or currency or "TRY").upper(),
        "allowed_room_types": listing.get("allowed_room_types") or [],
        "blocked_dates": listing.get("blocked_dates") or [],
        "room_type_names": [rt.get("name") or rt.get("room_type") for rt in content.get("room_types") or [] if rt.get("name") or rt.get("room_type")],
        "cover_photo": photos[0] if photos else None,
        "summary": description[:280],
        # Explicit opt-out only; a hotel without a listing document is visible.
        "hidden": listing.get("is_listed") is False,
    }
    profile.pop("_id", None)
    return profile


async def _currencies(sysdb, tenant_ids: list[str]) -> dict[str, str]:
    rows = await sysdb.hotel_settings.find(
        {"tenant_id": {"$in": tenant_ids}}, {"_id": 0, "tenant_id": 1, "currency": 1}
    ).to_list(len(tenant_ids))
    found = {row["tenant_id"]: str(row.get("currency") or "TRY").upper() for row in rows if row.get("tenant_id")}
    return {tenant_id: found.get(tenant_id, "TRY") for tenant_id in tenant_ids}


async def hotel_profiles(sysdb, tenant_ids: list[str] | None = None, *, include_hidden: bool = True) -> list[dict]:
    """Profiles of active hotels (all of them when ``tenant_ids`` is None)."""
    query: dict = {"is_active": {"$ne": False}}
    if tenant_ids is not None:
        if not tenant_ids:
            return []
        query["id"] = {"$in": list(tenant_ids)}
    tenants = [t for t in await sysdb.tenants.find(query, {"_id": 0}).to_list(5000) if tenant_is_active(t) and t.get("id")]
    ids = [t["id"] for t in tenants]
    if not ids:
        return []
    listings = {d["tenant_id"]: d for d in await sysdb.marketplace_listings.find({"tenant_id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))}
    contents = {d["tenant_id"]: d for d in await sysdb.hotel_content.find({"tenant_id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))}
    currencies = await _currencies(sysdb, ids)
    profiles = [_profile(t, listings.get(t["id"]), contents.get(t["id"]), currencies[t["id"]]) for t in tenants]
    if not include_hidden:
        profiles = [p for p in profiles if not p["hidden"]]
    return sorted(profiles, key=lambda p: str(p["hotel_name"]).casefold())


async def hotel_profile(sysdb, tenant_id: str) -> dict | None:
    profiles = await hotel_profiles(sysdb, [tenant_id])
    return profiles[0] if profiles else None


def teaser(profile: dict) -> dict:
    """Pre-contract information: no prices, no availability, no contacts."""
    return {key: profile.get(key) for key in TEASER_FIELDS}


def matches_filters(profile: dict, *, city: str | None = None, country: str | None = None,
                    q: str | None = None, min_star_rating: int | None = None) -> bool:
    if city and str(profile.get("city") or "").casefold() != city.strip().casefold():
        return False
    if country and str(profile.get("country") or "").upper() != country.strip().upper():
        return False
    if q:
        needle = q.strip().casefold()
        if needle not in str(profile.get("hotel_name") or "").casefold() and needle not in str(profile.get("description") or "").casefold():
            return False
    if min_star_rating and int(profile.get("star_rating") or 0) < int(min_star_rating):
        return False
    return True
