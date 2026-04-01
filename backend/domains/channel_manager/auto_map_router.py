"""
Auto-Map Router — Otomatik Oda Esleme
PMS oda tipleri ile provider (Exely/HotelRunner) oda tiplerini
isim benzerligine gore otomatik eslestirme.
"""
import logging
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/auto-map", tags=["Auto-Map"])

SIMILARITY_THRESHOLD = 0.4


class AutoMapSuggestRequest(BaseModel):
    provider: str  # "exely" or "hotelrunner"


class AutoMapApplyItem(BaseModel):
    pms_room_type: str
    provider_room_code: str
    provider_room_name: str
    provider_rate_plan_code: str | None = None
    provider_rate_plan_name: str | None = None


class AutoMapApplyRequest(BaseModel):
    provider: str
    mappings: list[AutoMapApplyItem]


def _similarity(a: str, b: str) -> float:
    """Calculate string similarity score between 0 and 1."""
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    if a_lower == b_lower:
        return 1.0
    # Direct substring check
    if a_lower in b_lower or b_lower in a_lower:
        return 0.85
    # Common hotel room type aliases
    aliases = {
        "standard": ["standart", "std", "standard", "standart oda"],
        "deluxe": ["deluxe", "dlx", "deluxe oda", "delüks"],
        "suite": ["suite", "suit", "süit", "suit oda"],
        "superior": ["superior", "sup", "superior oda", "süperior"],
        "junior suite": ["junior suite", "jr suite", "junior süit", "jr süit"],
        "family": ["family", "aile", "aile odasi", "family room"],
    }
    for _key, alias_list in aliases.items():
        a_match = any(alias in a_lower for alias in alias_list)
        b_match = any(alias in b_lower for alias in alias_list)
        if a_match and b_match:
            return 0.9
    return SequenceMatcher(None, a_lower, b_lower).ratio()


async def _get_pms_room_types(tenant_id: str) -> list[dict]:
    """Get unique PMS room types with counts."""
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "room_type": {"$ne": None}}},
        {"$group": {"_id": "$room_type", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    results = []
    async for doc in db.rooms.aggregate(pipeline):
        if doc["_id"]:
            results.append({"code": doc["_id"], "name": doc["_id"], "room_count": doc["count"]})
    return results


async def _get_exely_provider_rooms(tenant_id: str) -> tuple[list[dict], list[dict]]:
    """Get Exely provider room types and rate plans."""
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        return [], []
    room_types = conn.get("room_types", [])
    rate_plans = conn.get("rate_plans", [])
    return room_types, rate_plans


async def _get_hr_provider_rooms(tenant_id: str) -> tuple[list[dict], list[dict]]:
    """Get HotelRunner provider room types and rate plans from cached rooms."""
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        {"_id": 0, "cached_rooms": 1},
    )
    if not conn:
        return [], []
    cached = conn.get("cached_rooms", [])
    room_types = {}
    rate_plans = {}
    for room in cached:
        inv_code = room.get("inv_code", "")
        name = room.get("name", "")
        rate_code = room.get("rate_code", "")
        rate_name = room.get("rate_plan_name", "Ana fiyat")
        if inv_code and inv_code not in room_types:
            room_types[inv_code] = {"code": inv_code, "name": name}
        if rate_code and rate_code not in rate_plans:
            rate_plans[rate_code] = {"code": rate_code, "name": rate_name}
    return list(room_types.values()), list(rate_plans.values())


async def _get_existing_mappings(tenant_id: str, provider: str) -> list[dict]:
    """Get existing mappings for a provider."""
    if provider == "exely":
        return await db.exely_room_mappings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(200)
    elif provider == "hotelrunner":
        return await db.hotelrunner_room_mappings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(200)
    return []


@router.post("/suggest")
async def suggest_auto_mappings(
    payload: AutoMapSuggestRequest,
    current_user: User = Depends(get_current_user),
):
    """Suggest auto-mappings based on name similarity."""
    provider = payload.provider.lower()
    if provider not in ("exely", "hotelrunner"):
        raise HTTPException(status_code=400, detail="Gecersiz provider. 'exely' veya 'hotelrunner' olmali.")

    pms_types = await _get_pms_room_types(current_user.tenant_id)
    if not pms_types:
        raise HTTPException(status_code=404, detail="PMS'de oda tipi bulunamadi.")

    if provider == "exely":
        provider_rooms, provider_rates = await _get_exely_provider_rooms(current_user.tenant_id)
    else:
        provider_rooms, provider_rates = await _get_hr_provider_rooms(current_user.tenant_id)

    if not provider_rooms:
        raise HTTPException(status_code=404, detail=f"{provider} provider'da oda tipi bulunamadi.")

    # Get existing mappings to exclude already-mapped pairs
    existing = await _get_existing_mappings(current_user.tenant_id, provider)
    if provider == "exely":
        mapped_pms_types = {m.get("pms_room_type") for m in existing}
        mapped_provider_codes = {m.get("exely_room_code") for m in existing}
    else:
        mapped_pms_types = {m.get("pms_room_type") for m in existing}
        mapped_provider_codes = {m.get("hr_inv_code") for m in existing}

    suggestions = []
    used_provider_codes = set()

    for pms in pms_types:
        if pms["code"] in mapped_pms_types:
            continue

        best_match = None
        best_score = 0.0

        for pr in provider_rooms:
            pr_code = pr.get("code", "")
            pr_name = pr.get("name", "")

            if pr_code in mapped_provider_codes or pr_code in used_provider_codes:
                continue

            score = _similarity(pms["name"], pr_name)
            if score > best_score:
                best_score = score
                best_match = pr

        if best_match and best_score >= SIMILARITY_THRESHOLD:
            used_provider_codes.add(best_match["code"])
            suggestion = {
                "pms_room_type": pms["code"],
                "pms_room_name": pms["name"],
                "pms_room_count": pms["room_count"],
                "provider_room_code": best_match["code"],
                "provider_room_name": best_match["name"],
                "similarity_score": round(best_score, 2),
                "confidence": "high" if best_score >= 0.8 else "medium" if best_score >= 0.6 else "low",
            }
            # For Exely, add default rate plan
            if provider == "exely" and provider_rates:
                suggestion["provider_rate_plan_code"] = provider_rates[0]["code"]
                suggestion["provider_rate_plan_name"] = provider_rates[0]["name"]
            suggestions.append(suggestion)

    # Also return unmapped PMS types that couldn't be matched
    unmapped_pms = []
    suggested_pms = {s["pms_room_type"] for s in suggestions}
    for pms in pms_types:
        if pms["code"] not in mapped_pms_types and pms["code"] not in suggested_pms:
            unmapped_pms.append({
                "code": pms["code"],
                "name": pms["name"],
                "room_count": pms["room_count"],
            })

    # Unmapped provider rooms
    unmapped_provider = []
    suggested_provider = {s["provider_room_code"] for s in suggestions}
    for pr in provider_rooms:
        if pr["code"] not in mapped_provider_codes and pr["code"] not in suggested_provider:
            unmapped_provider.append(pr)

    return {
        "provider": provider,
        "suggestions": sorted(suggestions, key=lambda x: x["similarity_score"], reverse=True),
        "unmapped_pms_types": unmapped_pms,
        "unmapped_provider_rooms": unmapped_provider,
        "existing_mapping_count": len(existing),
        "total_pms_types": len(pms_types),
        "total_provider_rooms": len(provider_rooms),
    }


@router.post("/apply")
async def apply_auto_mappings(
    payload: AutoMapApplyRequest,
    current_user: User = Depends(get_current_user),
):
    """Apply selected auto-mapping suggestions."""
    provider = payload.provider.lower()
    if provider not in ("exely", "hotelrunner"):
        raise HTTPException(status_code=400, detail="Gecersiz provider.")

    created = 0
    errors = []

    for m in payload.mappings:
        try:
            if provider == "exely":
                doc = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": current_user.tenant_id,
                    "pms_room_type": m.pms_room_type,
                    "exely_room_code": m.provider_room_code,
                    "exely_rate_plan_code": m.provider_rate_plan_code or "",
                    "exely_room_name": m.provider_room_name,
                    "sync_availability": True,
                    "sync_price": True,
                    "sync_restrictions": True,
                    "auto_mapped": True,
                    "created_at": datetime.now(UTC).isoformat(),
                    "created_by": current_user.name,
                }
                # Check for duplicate
                existing = await db.exely_room_mappings.find_one({
                    "tenant_id": current_user.tenant_id,
                    "pms_room_type": m.pms_room_type,
                    "exely_room_code": m.provider_room_code,
                })
                if existing:
                    errors.append(f"{m.pms_room_type} -> {m.provider_room_name} zaten eslenmis")
                    continue
                await db.exely_room_mappings.insert_one(doc)

            elif provider == "hotelrunner":
                doc = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": current_user.tenant_id,
                    "pms_room_type": m.pms_room_type,
                    "hr_inv_code": m.provider_room_code,
                    "hr_rate_code": m.provider_rate_plan_code or "",
                    "hr_room_name": m.provider_room_name,
                    "sync_availability": True,
                    "sync_price": True,
                    "sync_restrictions": True,
                    "auto_mapped": True,
                    "created_at": datetime.now(UTC).isoformat(),
                    "created_by": current_user.name,
                }
                existing = await db.hotelrunner_room_mappings.find_one({
                    "tenant_id": current_user.tenant_id,
                    "hr_inv_code": m.provider_room_code,
                })
                if existing:
                    errors.append(f"{m.pms_room_type} -> {m.provider_room_name} zaten eslenmis")
                    continue
                await db.hotelrunner_room_mappings.insert_one(doc)

            created += 1
        except Exception as e:
            errors.append(f"{m.pms_room_type}: {str(e)}")

    return {
        "message": f"{created} esleme olusturuldu",
        "created": created,
        "errors": errors,
    }


@router.get("/status/{provider}")
async def get_mapping_status(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Get overall mapping status for a provider."""
    provider = provider.lower()
    if provider not in ("exely", "hotelrunner"):
        raise HTTPException(status_code=400, detail="Gecersiz provider.")

    pms_types = await _get_pms_room_types(current_user.tenant_id)
    existing = await _get_existing_mappings(current_user.tenant_id, provider)

    if provider == "exely":
        provider_rooms, provider_rates = await _get_exely_provider_rooms(current_user.tenant_id)
        mapped_pms = {m.get("pms_room_type") for m in existing}
    else:
        provider_rooms, provider_rates = await _get_hr_provider_rooms(current_user.tenant_id)
        mapped_pms = {m.get("pms_room_type") for m in existing}

    unmapped_count = sum(1 for p in pms_types if p["code"] not in mapped_pms)
    total_pms = len(pms_types)
    mapped_count = total_pms - unmapped_count

    return {
        "provider": provider,
        "total_pms_types": total_pms,
        "total_provider_rooms": len(provider_rooms),
        "total_provider_rate_plans": len(provider_rates),
        "mapped_count": mapped_count,
        "unmapped_count": unmapped_count,
        "completion_pct": round((mapped_count / total_pms * 100) if total_pms > 0 else 0, 1),
        "existing_mappings": len(existing),
    }
