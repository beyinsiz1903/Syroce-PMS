"""Compatibility / transitional endpoints for modules referenced by the
frontend but not yet promoted to a dedicated domain router.

NOT every endpoint here is a "fake" — many already perform real, tenant-scoped
DB reads/writes; they live here only because their long-term home (a proper
`backend/domains/<area>/router.py`) hasn't been carved out yet.

Each endpoint is annotated with one of the following status labels (see
`docs/MODULE_INVENTORY.md` for the project-wide convention):

    # STATUS: production_ready  → real CRUD with permissions; safe to migrate
    #                              as-is to a domain router
    # STATUS: partial            → real DB read but missing
    #                              create/update/delete or workflow
    # STATUS: stub               → returns hard-coded / empty defaults so the
    #                              UI does not crash; backend logic missing
    # STATUS: deprecated         → kept only for old clients; remove on next
    #                              frontend release

Migration target: every endpoint here should either move to a domain router
or be deleted. New endpoints SHOULD NOT be added to this file.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.database import db
from core.security import get_current_user
from core.tenant_db import get_system_db
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api", tags=["compat"])
_system_db = get_system_db()


# ─────────────────────────────────────────────────────────────────────
# UPSELL
# ─────────────────────────────────────────────────────────────────────
# STATUS: partial — real tenant-scoped DB read; create/update/delete missing.
#                   Move to domains/sales/upsell_router.py when CRUD is added.
@router.get("/upsell/products")
async def upsell_products(
    current_user=Depends(get_current_user),
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
# CENTRAL OFFICE (multi-property HQ view)
# ─────────────────────────────────────────────────────────────────────
async def _central_chain_properties(current_user) -> list[dict]:
    tenant_id = current_user.tenant_id
    own = await _system_db.tenants.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {"_id": 0, "chain_id": 1, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1, "is_chain_headquarters": 1},
    )
    chain_id = (own or {}).get("chain_id")
    if chain_id:
        role = getattr(getattr(current_user, "role", None), "value", getattr(current_user, "role", None))
        is_hq = bool(getattr(current_user, "is_chain_headquarters", False) or (own or {}).get("is_chain_headquarters"))
        if role != "super_admin" and not is_hq:
            raise HTTPException(403, "Zincir geneli merkezi ofis görünümü yalnız merkez tesis kullanıcılarına açıktır")
        tenants = await _system_db.tenants.find(
            {"chain_id": chain_id},
            {"_id": 0, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1},
        ).to_list(500)
    else:
        tenants = [own or {"id": tenant_id, "name": tenant_id}]
    return [
        {
            "tenant_id": tenant.get("tenant_id") or tenant.get("id"),
            "property_name": tenant.get("hotel_name") or tenant.get("name") or tenant.get("tenant_id") or tenant.get("id"),
        }
        for tenant in tenants
        if tenant.get("tenant_id") or tenant.get("id")
    ]


async def _central_property_metrics(property_doc: dict, period_start: str, period_end: str, today: str) -> dict:
    tenant_id = property_doc["tenant_id"]
    rooms = await _system_db.rooms.find({"tenant_id": tenant_id}, {"_id": 0, "status": 1}).to_list(10000)
    occupied = sum(1 for room in rooms if room.get("status") == "occupied")
    charges = await _system_db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": {"$gte": period_start, "$lt": period_end}},
                {"date": {"$gte": period_start, "$lt": period_end}},
            ],
        },
        {"_id": 0, "total": 1, "amount": 1},
    ).to_list(100000)
    revenue = round(sum(float(row.get("total", row.get("amount", 0)) or 0) for row in charges), 2)
    today_checkins = await _system_db.bookings.count_documents(
        {"tenant_id": tenant_id, "check_in": today, "status": {"$ne": "cancelled"}}
    )
    total_guests = await _system_db.guests.count_documents({"tenant_id": tenant_id})
    total_rooms = len(rooms)
    return {
        **property_doc,
        "id": tenant_id,
        "total_rooms": total_rooms,
        "occupied_rooms": occupied,
        "available_rooms": max(0, total_rooms - occupied),
        "occupancy_rate": round((occupied / total_rooms) * 100, 2) if total_rooms else 0.0,
        "today_checkins": today_checkins,
        "total_guests": total_guests,
        "total_revenue": revenue,
    }


@router.get("/central-office/dashboard")
async def central_office_dashboard(current_user=Depends(get_current_user), _perm=Depends(require_op("view_executive_reports"))):
    now = datetime.now(UTC)
    today = now.date().isoformat()
    month_start = now.date().replace(day=1).isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    properties = await _central_chain_properties(current_user)
    breakdown = await asyncio.gather(
        *(_central_property_metrics(property_doc, month_start, tomorrow, today) for property_doc in properties)
    )
    total_rooms = sum(row["total_rooms"] for row in breakdown)
    occupied = sum(row["occupied_rooms"] for row in breakdown)
    total_revenue = round(sum(row["total_revenue"] for row in breakdown), 2)
    return {
        "properties": breakdown,
        "property_breakdown": breakdown,
        "chain_kpi": {
            "total_properties": len(breakdown),
            "total_rooms": total_rooms,
            "chain_occupancy_rate": round((occupied / total_rooms) * 100, 2) if total_rooms else 0.0,
            "today_checkins": sum(row["today_checkins"] for row in breakdown),
            "total_guests": sum(row["total_guests"] for row in breakdown),
        },
        "total_properties": len(breakdown),
        "kpis": {
            "total_revenue_mtd": total_revenue,
            "average_occupancy": round((occupied / total_rooms) * 100, 2) if total_rooms else 0.0,
        },
    }


@router.get("/central-office/alerts")
async def central_office_alerts(current_user=Depends(get_current_user), _perm=Depends(require_op("view_executive_reports"))):
    properties = await _central_chain_properties(current_user)
    alerts = []
    for property_doc in properties:
        tenant_id = property_doc["tenant_id"]
        failed_night = await _system_db.night_audit_runs.count_documents(
            {"tenant_id": tenant_id, "gl_bridge_status": "failed"}
        )
        failed_pos = await _system_db.pos_transactions.count_documents(
            {"tenant_id": tenant_id, "gl_bridge_status": "failed"}
        )
        if failed_night or failed_pos:
            alerts.append(
                {
                    "id": f"gl:{tenant_id}",
                    "property": property_doc["property_name"],
                    "type": "Muhasebe Köprüsü",
                    "severity": "warning",
                    "message": f"{failed_night} gece denetimi ve {failed_pos} POS aktarımı bekliyor.",
                }
            )
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/central-office/occupancy-comparison")
async def central_office_occupancy(current_user=Depends(get_current_user), _perm=Depends(require_op("view_executive_reports"))):
    now = datetime.now(UTC)
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    properties = await _central_chain_properties(current_user)
    comparison = await asyncio.gather(*(_central_property_metrics(row, today, tomorrow, today) for row in properties))
    return {"comparison": comparison, "properties": comparison, "period": {"start": today, "end": today}}


@router.get("/central-office/revenue-report")
async def central_office_revenue(current_user=Depends(get_current_user), _perm=Depends(require_op("view_executive_reports"))):
    now = datetime.now(UTC)
    today = now.date().isoformat()
    start = now.date().replace(day=1).isoformat()
    end = (now.date() + timedelta(days=1)).isoformat()
    properties = await _central_chain_properties(current_user)
    rows = await asyncio.gather(*(_central_property_metrics(row, start, end, today) for row in properties))
    total = round(sum(row["total_revenue"] for row in rows), 2)
    return {
        "properties": rows,
        "total_chain_revenue": total,
        "totals": {"revenue": total},
        "period": {"start": start, "end": today},
    }


# ─────────────────────────────────────────────────────────────────────
# SECURITY / IP ACCESS CONTROL
# ─────────────────────────────────────────────────────────────────────
# STATUS: production_ready — real CRUD on db.ip_rules with require_op
#                            permission gates. Move to a dedicated
#                            routers/security_ip.py.
@router.get("/security/ip/rules")
async def ip_rules_list(current_user=Depends(get_current_user)):
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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("manage_secrets")),
):
    res = await db.ip_rules.delete_one({"id": rule_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True, "id": rule_id}


# STATUS: stub — always returns allowed=true. Should evaluate request IP
#                against rules + return matched_rule.
@router.post("/security/ip/check")
async def ip_check(current_user=Depends(get_current_user)):
    return {"client_ip": None, "allowed": True, "matched_rule": None}


# ─────────────────────────────────────────────────────────────────────
# AGENCY / HOTEL BOOKING REQUESTS
# ─────────────────────────────────────────────────────────────────────
# STATUS: production_ready — real list/approve/reject workflow with
#                            require_op + tenant scope + audit fields.
#                            Move to routers/agency_portal.py companion.
@router.get("/hotel/booking-requests")
async def hotel_booking_requests(
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),
):
    req = await db.agency_booking_requests.find_one({"request_id": request_id, "tenant_id": current_user.tenant_id})
    if not req:
        raise HTTPException(status_code=404, detail="Talep bulunamadi")
    now = datetime.now(UTC).isoformat()
    await db.agency_booking_requests.update_one(
        {"request_id": request_id, "tenant_id": current_user.tenant_id},
        {
            "$set": {
                "status": "approved",
                "approved_at": now,
                "approved_by": current_user.id,
                "updated_at": now,
            }
        },
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
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),
):
    req = await db.agency_booking_requests.find_one({"request_id": request_id, "tenant_id": current_user.tenant_id})
    if not req:
        raise HTTPException(status_code=404, detail="Talep bulunamadi")
    now = datetime.now(UTC).isoformat()
    await db.agency_booking_requests.update_one(
        {"request_id": request_id, "tenant_id": current_user.tenant_id},
        {
            "$set": {
                "status": "rejected",
                "rejected_at": now,
                "rejected_by": current_user.id,
                "resolution_notes": body.reason,
                "updated_at": now,
            }
        },
    )
    return {"rejected": True, "request_id": request_id}


# ─────────────────────────────────────────────────────────────────────
# MEDIA LIBRARY
# ─────────────────────────────────────────────────────────────────────
# STATUS: partial — real list of media_files; no upload/delete/metadata
#                   endpoints. Upload path is handled separately by
#                   /uploads/* (static mount).
@router.get("/media/list")
async def media_list(
    current_user=Depends(get_current_user),
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
# STATUS: production_ready — real PATCH with permission + tenant scope.
#                            Move to routers/pms_bookings.py.
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
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("manage_guests")),
):
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")
    update = {k: v for k, v in body.dict().items() if v is not None}
    if not update:
        return {"updated": False, "id": booking_id}
    update["updated_at"] = datetime.now(UTC).isoformat()
    await db.bookings.update_one({"id": booking_id, "tenant_id": current_user.tenant_id}, {"$set": update})
    return {"updated": True, "id": booking_id, **update}
