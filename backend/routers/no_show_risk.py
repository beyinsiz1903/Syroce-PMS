"""
No-Show Risk Skoru — booking ozelliklerine gore 0-100 risk skoru hesaplar.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/pms/no-show-risk", tags=["pms"])


def _parse_date(s) -> date | None:
    if not s:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except Exception:
        return None


async def _guest_history(tenant_id: str, guest_id: str) -> dict:
    if not guest_id:
        return {"total": 0, "no_show": 0, "cancel": 0}
    total = await db.bookings.count_documents({"tenant_id": tenant_id, "guest_id": guest_id})
    ns = await db.bookings.count_documents({"tenant_id": tenant_id, "guest_id": guest_id, "status": "no_show"})
    cn = await db.bookings.count_documents({"tenant_id": tenant_id, "guest_id": guest_id, "status": "cancelled"})
    return {"total": total, "no_show": ns, "cancel": cn}


async def _score_booking(tenant_id: str, b: dict) -> dict:
    score = 0
    factors: list[dict] = []

    hist = await _guest_history(tenant_id, b.get("guest_id"))
    if hist["no_show"] >= 1:
        delta = min(40, 25 + (hist["no_show"] - 1) * 10)
        score += delta
        factors.append({"label": f"Geçmişte {hist['no_show']} no-show", "delta": delta})
    if hist["cancel"] >= 2:
        score += 10
        factors.append({"label": f"Geçmişte {hist['cancel']} iptal", "delta": 10})

    pay_status = (b.get("payment_status") or "").lower()
    if pay_status in ("unpaid", "pending", ""):
        score += 20
        factors.append({"label": "Ödeme yapılmamış", "delta": 20})

    deposit = float(b.get("deposit_amount") or 0)
    if deposit <= 0:
        score += 15
        factors.append({"label": "Depozit alınmamış", "delta": 15})

    channel = (b.get("source_channel") or b.get("channel") or "").lower()
    if any(k in channel for k in ("booking", "expedia", "ota", "agoda", "hotelbeds")):
        score += 10
        factors.append({"label": f"OTA kanalı ({channel})", "delta": 10})

    ci = _parse_date(b.get("check_in"))
    created = _parse_date(b.get("created_at"))
    if ci and created:
        lead = (ci - created).days
        if lead > 60:
            score += 10
            factors.append({"label": f"Lead time {lead} gün", "delta": 10})
        elif lead < 0:
            score += 5
            factors.append({"label": "Geçmiş tarihli rezervasyon", "delta": 5})

    nights = int(b.get("nights") or 1)
    if nights == 1:
        score += 5
        factors.append({"label": "Tek gece konaklama", "delta": 5})

    if ci:
        wd = ci.weekday()
        if wd in (4, 5):
            score -= 5
            factors.append({"label": "Hafta sonu (talep yüksek)", "delta": -5})

    score = max(0, min(100, score))
    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"

    return {
        "booking_id": b.get("id"),
        "score": score,
        "level": level,
        "factors": factors,
        "guest_history": hist,
    }


@router.get("/{booking_id}")
async def get_risk(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_bookings")),
):
    b = await db.bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Rezervasyon bulunamadi")
    return await _score_booking(current_user.tenant_id, b)


class BulkRequest(BaseModel):
    booking_ids: list[str]


@router.post("/bulk")
async def bulk_risk(
    payload: BulkRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_bookings")),
):
    if not payload.booking_ids:
        return {"results": {}}
    tenant_id = current_user.tenant_id
    ids = payload.booking_ids[:200]
    bookings = await db.bookings.find(
        {"tenant_id": tenant_id, "id": {"$in": ids}},
        {"_id": 0},
    ).to_list(len(ids))

    # N+1 onleyici: tum guest history'leri tek aggregation ile cek
    guest_ids = [b.get("guest_id") for b in bookings if b.get("guest_id")]
    hist_map: dict[str, dict] = {}
    if guest_ids:
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "guest_id": {"$in": guest_ids}}},
            {
                "$group": {
                    "_id": "$guest_id",
                    "total": {"$sum": 1},
                    "no_show": {"$sum": {"$cond": [{"$eq": ["$status", "no_show"]}, 1, 0]}},
                    "cancel": {"$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}},
                }
            },
        ]
        async for h in db.bookings.aggregate(pipeline):
            hist_map[h["_id"]] = {"total": h["total"], "no_show": h["no_show"], "cancel": h["cancel"]}

    # _score_booking yerine inline (cached hist_map ile)
    out = {}
    for b in bookings:
        s = await _score_with_history(tenant_id, b, hist_map.get(b.get("guest_id"), {"total": 0, "no_show": 0, "cancel": 0}))
        out[b["id"]] = {"score": s["score"], "level": s["level"]}
    return {"results": out}


async def _score_with_history(tenant_id: str, b: dict, hist: dict) -> dict:
    """_score_booking'in DB-cache'lenmis varyanti."""
    score = 0
    factors: list[dict] = []
    if hist["no_show"] >= 1:
        delta = min(40, 25 + (hist["no_show"] - 1) * 10)
        score += delta
        factors.append({"label": f"Gecmiste {hist['no_show']} no-show", "delta": delta})
    if hist["cancel"] >= 2:
        score += 10
        factors.append({"label": f"Gecmiste {hist['cancel']} iptal", "delta": 10})
    if (b.get("payment_status") or "").lower() in ("unpaid", "pending", ""):
        score += 20
    if float(b.get("deposit_amount") or 0) <= 0:
        score += 15
    ch = (b.get("source_channel") or b.get("channel") or "").lower()
    if any(k in ch for k in ("booking", "expedia", "ota", "agoda", "hotelbeds")):
        score += 10
    nights = int(b.get("nights") or 1)
    if nights == 1:
        score += 5
    score = max(0, min(100, score))
    level = "high" if score >= 70 else ("medium" if score >= 40 else "low")
    return {"score": score, "level": level}
