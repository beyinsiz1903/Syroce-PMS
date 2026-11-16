"""
Walk-in 30-saniye akisi: tek istekte misafir + rezervasyon + check-in.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.business_date_service import ensure_business_date_initialized
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module_role, require_op

router = APIRouter(prefix="/api/pms/walkin", tags=["pms"])


@router.get("/available-rooms")
async def available_rooms(
    nights: int = 1,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_room_status")),
):
    """Bugunden itibaren `nights` gece icin musait odalari dondur."""
    tenant_id = current_user.tenant_id
    day = await ensure_business_date_initialized(db, tenant_id)
    today = date.fromisoformat(day["business_date"])
    end = today + timedelta(days=max(1, min(14, nights)))
    today_s = today.isoformat()
    end_s = end.isoformat()

    rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "is_active": {"$ne": False}, "is_virtual": {"$ne": True},
         "status": {"$in": ["available", "inspected", "clean"]}},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "base_rate": 1, "rate": 1, "max_occupancy": 1},
    ).to_list(500)

    busy_ids = set()
    cursor = db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house"]},
            "check_in": {"$lt": end_s},
            "check_out": {"$gt": today_s},
        },
        {"_id": 0, "room_id": 1},
    )
    async for b in cursor:
        if b.get("room_id"):
            busy_ids.add(b["room_id"])

    out = []
    for r in rooms:
        if r["id"] in busy_ids:
            continue
        out.append(
            {
                "id": r["id"],
                "room_number": r.get("room_number"),
                "room_type": r.get("room_type"),
                "rate": float(r.get("base_rate") or r.get("rate") or 0),
                "max_occupancy": r.get("max_occupancy") or 2,
            }
        )
    out.sort(key=lambda x: str(x.get("room_number") or ""))
    return {"rooms": out, "count": len(out), "nights": nights, "business_date": today_s, "check_out": end_s}


class WalkinRequest(BaseModel):
    guest_name: str
    phone: str = ""
    id_number: str = ""
    email: str = ""
    room_id: str
    nights: int = Field(default=1, ge=1, le=14)
    adults: int = Field(default=1, ge=1, le=8)
    children: int = Field(default=0, ge=0, le=8)
    currency: str = Field(default="TRY", pattern=r"^[A-Z]{3}$")
    total_amount: float
    payment_amount: float = 0
    payment_method: str = "cash"
    note: str = ""


@router.post("/checkin")
async def walkin_checkin(
    payload: WalkinRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("create_booking")),
    _frontdesk=Depends(require_op("check_in")),
    _role=Depends(require_module_role("frontdesk")),
):
    """Use the canonical booking/check-in path; never write an isolated receipt."""
    import math

    from domains.pms.frontdesk_router import create_walk_in_booking
    from domains.pms.schemas import WalkInBookingRequest

    if not payload.guest_name.strip():
        raise HTTPException(400, "Misafir adi gerekli")
    if not math.isfinite(payload.total_amount) or payload.total_amount <= 0:
        raise HTTPException(400, "Tutar gecerli olmali")
    if not math.isfinite(payload.payment_amount) or payload.payment_amount != 0:
        raise HTTPException(400, "Ödemeyi girişten sonra misafir kartındaki Ödeme / Folyo alanından alın.")
    if not http_request.headers.get("Idempotency-Key"):
        raise HTTPException(400, "İşlem anahtarı eksik; walk-in formunu yenileyin.")
    result = await create_walk_in_booking(
        WalkInBookingRequest(
            guest_name=payload.guest_name.strip(), guest_phone=payload.phone,
            guest_email=payload.email or None, guest_id_number=payload.id_number or None,
            room_id=payload.room_id, nights=payload.nights,
            adults=payload.adults, children=payload.children,
            rate_per_night=payload.total_amount / payload.nights,
            special_requests=payload.note or None, currency=payload.currency,
        ),
        http_request=http_request, current_user=current_user, _perm=None,
    )
    return {**result, "ok": True, "balance": result["total_amount"]}
