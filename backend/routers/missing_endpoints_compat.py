"""Compatibility / stub endpoints for modules referenced by the frontend
but not yet (re)implemented in the active backend.

These return safe defaults so dependent UI pages do not crash.
Once a real domain router is added, the corresponding stub here can be removed.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.database import db
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api", tags=["compat"])


# ─────────────────────────────────────────────────────────────────────
# UPSELL
# ─────────────────────────────────────────────────────────────────────
@router.get("/upsell/products")
async def upsell_products(
    current_user= Depends(get_current_user),
    category: str | None = None,
):
    """Return active upsell products for the tenant."""
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id, "is_active": {"$ne": False}}
    if category:
        q["category"] = category
    items: list[dict] = []
    async for p in db.upsell_products.find(q, {"_id": 0}).limit(200):
        items.append(p)
    return {"products": items, "total": len(items)}


# ─────────────────────────────────────────────────────────────────────
# GDPR / KVKK COMPLIANCE
# ─────────────────────────────────────────────────────────────────────
@router.get("/gdpr/compliance-status")
async def gdpr_compliance_status(current_user= Depends(get_current_user)):
    tid = current_user.tenant_id
    guests = await db.guests.count_documents({"tenant_id": tid})
    consents = await db.kvkk_consents.count_documents({"tenant_id": tid}) if tid else 0
    erasure = await db.kvkk_erasure_requests.count_documents({"tenant_id": tid}) if tid else 0
    score = 100 if guests == 0 else round(min(100, (consents / max(guests, 1)) * 100))
    return {
        "compliance_score": score,
        "total_guests": guests,
        "consented_guests": consents,
        "erasure_requests": erasure,
        "data_processing_agreements": 0,
        "last_audit": None,
        "status": "active",
    }


@router.get("/gdpr/dpa")
async def gdpr_dpa(current_user= Depends(get_current_user)):
    items: list[dict] = []
    async for d in db.dpa_records.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).limit(100):
        items.append(d)
    return {"agreements": items, "total": len(items)}


@router.get("/gdpr/retention-policy")
async def gdpr_retention(current_user= Depends(get_current_user)):
    return {
        "policies": [
            {"data_type": "guest_pii", "retention_days": 730, "auto_anonymize": True},
            {"data_type": "booking_history", "retention_days": 1825, "auto_anonymize": False},
            {"data_type": "payment_records", "retention_days": 3650, "auto_anonymize": False},
            {"data_type": "marketing_consents", "retention_days": 365, "auto_anonymize": True},
        ]
    }


# ─────────────────────────────────────────────────────────────────────
# CENTRAL OFFICE (multi-property HQ view)
# ─────────────────────────────────────────────────────────────────────
@router.get("/central-office/dashboard")
async def central_office_dashboard(current_user= Depends(get_current_user)):
    tid = current_user.tenant_id
    properties: list[dict] = []
    async for h in db.hotels.find(
        {"tenant_id": tid},
        {"_id": 0, "id": 1, "hotel_name": 1, "code": 1, "city": 1, "is_active": 1},
    ).limit(100):
        properties.append(h)
    return {
        "properties": properties,
        "total_properties": len(properties),
        "kpis": {
            "total_revenue_mtd": 0.0,
            "total_bookings_mtd": 0,
            "average_occupancy": 0.0,
            "average_adr": 0.0,
        },
    }


@router.get("/central-office/alerts")
async def central_office_alerts(current_user= Depends(get_current_user)):
    return {"alerts": [], "total": 0}


@router.get("/central-office/occupancy-comparison")
async def central_office_occupancy(current_user= Depends(get_current_user)):
    return {"properties": [], "period": {"start": None, "end": None}}


@router.get("/central-office/revenue-report")
async def central_office_revenue(current_user= Depends(get_current_user)):
    return {"properties": [], "totals": {"revenue": 0.0, "bookings": 0}}


# ─────────────────────────────────────────────────────────────────────
# CENTRAL PRICING
# ─────────────────────────────────────────────────────────────────────
@router.get("/central-pricing/rates")
async def central_pricing_rates(current_user= Depends(get_current_user)):
    return {"rates": [], "total": 0}


@router.get("/central-pricing/rate-history")
async def central_pricing_history(current_user= Depends(get_current_user)):
    return {"history": [], "total": 0}


@router.get("/central-pricing/rate-templates")
async def central_pricing_templates(current_user= Depends(get_current_user)):
    return {"templates": [], "total": 0}


# ─────────────────────────────────────────────────────────────────────
# SECURITY / IP ACCESS CONTROL
# ─────────────────────────────────────────────────────────────────────
@router.get("/security/ip/rules")
async def ip_rules_list(current_user= Depends(get_current_user)):
    items: list[dict] = []
    async for r in db.ip_rules.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).limit(500):
        items.append(r)
    return {"rules": items, "total": len(items)}


class IPRuleCreate(BaseModel):
    ip_address: str
    rule_type: str
    description: str = ""


@router.post("/security/ip/rules")
async def ip_rules_create(
    body: IPRuleCreate,
    current_user= Depends(get_current_user),
    _perm=Depends(require_op("manage_secrets")),
):
    if body.rule_type not in ("whitelist", "blacklist"):
        raise HTTPException(status_code=422, detail="rule_type must be whitelist or blacklist")
    if not body.ip_address.strip():
        raise HTTPException(status_code=422, detail="ip_address required")
    rule = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "ip_address": body.ip_address.strip(),
        "rule_type": body.rule_type,
        "description": body.description,
        "created_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.ip_rules.insert_one(rule)
    rule.pop("_id", None)
    return rule


@router.delete("/security/ip/rules/{rule_id}")
async def ip_rules_delete(
    rule_id: str,
    current_user= Depends(get_current_user),
    _perm=Depends(require_op("manage_secrets")),
):
    res = await db.ip_rules.delete_one({"id": rule_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True, "id": rule_id}


@router.post("/security/ip/check")
async def ip_check(current_user= Depends(get_current_user)):
    return {"client_ip": None, "allowed": True, "matched_rule": None}


# ─────────────────────────────────────────────────────────────────────
# AGENCY / HOTEL BOOKING REQUESTS
# ─────────────────────────────────────────────────────────────────────
@router.get("/hotel/booking-requests")
async def hotel_booking_requests(
    current_user= Depends(get_current_user),
    status: str | None = None,
):
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if status and status != "all":
        q["status"] = status
    items: list[dict] = []
    async for r in db.agency_booking_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(500):
        items.append(r)
    return {"items": items, "total": len(items)}


@router.post("/hotel/booking-requests/{request_id}/approve")
async def hotel_booking_request_approve(
    request_id: str,
    current_user= Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),
):
    req = await db.agency_booking_requests.find_one(
        {"request_id": request_id, "tenant_id": current_user.tenant_id}
    )
    if not req:
        raise HTTPException(status_code=404, detail="Talep bulunamadi")
    now = datetime.now(UTC).isoformat()
    await db.agency_booking_requests.update_one(
        {"request_id": request_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "approved",
            "approved_at": now,
            "approved_by": current_user.id,
            "updated_at": now,
        }}
    )
    return {"approved": True, "request_id": request_id}


class BookingRequestRejectBody(BaseModel):
    # Pydantic seviyesinde min_length=5 — boş/eksik gövde için 422
    # döner; ayrıca aşağıdaki validator whitespace-only stringi de eler.
    # max_length=1000 DB write amplification'a karşı koruma.
    reason: str = Field(..., min_length=5, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        stripped = (v or "").strip()
        if len(stripped) < 5:
            raise ValueError("Red nedeni en az 5 karakter olmalıdır")
        return stripped


@router.post("/hotel/booking-requests/{request_id}/reject")
async def hotel_booking_request_reject(
    request_id: str,
    body: BookingRequestRejectBody,
    current_user= Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),
):
    req = await db.agency_booking_requests.find_one(
        {"request_id": request_id, "tenant_id": current_user.tenant_id}
    )
    if not req:
        raise HTTPException(status_code=404, detail="Talep bulunamadi")
    now = datetime.now(UTC).isoformat()
    await db.agency_booking_requests.update_one(
        {"request_id": request_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "rejected",
            "rejected_at": now,
            "rejected_by": current_user.id,
            "resolution_notes": body.reason,
            "updated_at": now,
        }}
    )
    return {"rejected": True, "request_id": request_id}


# ─────────────────────────────────────────────────────────────────────
# MEDIA LIBRARY
# ─────────────────────────────────────────────────────────────────────
@router.get("/media/list")
async def media_list(
    current_user= Depends(get_current_user),
    module: str | None = None,
    entity_id: str | None = None,
):
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if module:
        q["module"] = module
    if entity_id:
        q["entity_id"] = entity_id
    items: list[dict] = []
    async for m in db.media_files.find(q, {"_id": 0}).sort("created_at", -1).limit(500):
        items.append(m)
    return {"items": items, "total": len(items)}


# ─────────────────────────────────────────────────────────────────────
# BOOKING GUEST-INFO PATCH (used by ArrivalList side panel)
# ─────────────────────────────────────────────────────────────────────
class GuestInfoPatch(BaseModel):
    guest_name: str | None = None
    guest_phone: str | None = None
    guest_email: str | None = None
    notes: str | None = None
    special_requests: str | None = None
    arrival_time: str | None = None


@router.patch("/bookings/{booking_id}/guest-info")
async def patch_booking_guest_info(
    booking_id: str,
    body: GuestInfoPatch,
    current_user= Depends(get_current_user),
    _perm=Depends(require_op("manage_guests")),
):
    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id}
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")
    update = {k: v for k, v in body.dict().items() if v is not None}
    if not update:
        return {"updated": False, "id": booking_id}
    update["updated_at"] = datetime.now(UTC).isoformat()
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"$set": update}
    )
    return {"updated": True, "id": booking_id, **update}
