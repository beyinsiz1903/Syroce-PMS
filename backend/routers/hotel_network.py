"""Closed hotel-to-hotel inventory, referral and property-transfer network.

This bounded context intentionally does not mutate agency contracts or reuse an
agency identity. Hotels remain independent tenants. Cross-tenant reads/writes
are permitted only after an explicit contract or an accepted spot request.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, model_validator
from pymongo import ReturnDocument

from core.atomic_booking import BookingConflictError, create_booking_atomic
from core.database import db
from core.security import get_current_user
from core.tenant_db import get_system_db, tenant_context
from models.schemas import User

router = APIRouter(prefix="/api/hotel-network", tags=["Hotel Network"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _tenant(user: User) -> str:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(403, "Otel bağlamı gerekli")
    return tenant_id


async def _hotel_name(sysdb, tenant_id: str) -> str:
    hotel = await sysdb.tenants.find_one(
        {"$or": [{"id": tenant_id}, {"tenant_id": tenant_id}]},
        {"_id": 0, "property_name": 1, "hotel_name": 1, "name": 1},
    )
    return (hotel or {}).get("property_name") or (hotel or {}).get("hotel_name") or (hotel or {}).get("name") or "Otel"


async def _active_contract(sysdb, a: str, b: str) -> dict | None:
    pair = sorted([a, b])
    return await sysdb.hotel_network_contracts.find_one(
        {"tenant_pair": pair, "status": "active"}, {"_id": 0}
    )


async def _audit(sysdb, tenant_id: str, actor_id: str, action: str, entity_id: str, details: dict | None = None) -> None:
    await sysdb.hotel_network_audit_logs.insert_one({
        "id": _id(), "tenant_id": tenant_id, "actor_id": actor_id,
        "action": action, "entity_id": entity_id, "details": details or {},
        "created_at": _now(),
    })


class NetworkContractCreate(BaseModel):
    partner_tenant_id: str = Field(..., min_length=1, max_length=128)
    valid_from: str
    valid_to: str
    approval_mode: str = Field(default="automatic", pattern="^(automatic|manual)$")
    settlement_model: str = Field(default="net_rate", pattern="^(net_rate|commission)$")
    commission_pct: float = Field(default=0, ge=0, le=100)
    payment_terms_days: int = Field(default=15, ge=0, le=90)
    allowed_room_types: list[str] = Field(default_factory=list, max_length=100)
    special_terms: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_dates(self):
        try:
            if datetime.fromisoformat(self.valid_to) <= datetime.fromisoformat(self.valid_from):
                raise ValueError("Bitiş tarihi başlangıçtan sonra olmalıdır")
        except (TypeError, ValueError) as exc:
            raise ValueError("Geçerli sözleşme tarihleri girilmelidir") from exc
        return self


class ContractDecision(BaseModel):
    accept: bool
    note: str = Field(default="", max_length=1000)


class NetworkListingCreate(BaseModel):
    room_type: str = Field(..., min_length=1, max_length=160)
    date_start: str
    date_end: str
    nightly_rate: float = Field(..., gt=0)
    allotment: int = Field(default=1, ge=1, le=500)
    visibility: str = Field(default="network", pattern="^(network|contracts_only|selected)$")
    selected_tenant_ids: list[str] = Field(default_factory=list, max_length=200)
    approval_mode: str = Field(default="manual", pattern="^(automatic|manual)$")
    amenities: list[str] = Field(default_factory=list, max_length=50)
    meal_plan: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=1000)


class NetworkRequestCreate(BaseModel):
    listing_id: str
    check_in: str
    check_out: str
    guest_name: str = Field(..., min_length=2, max_length=160)
    guest_email: EmailStr | None = None
    guest_phone: str = Field(default="", max_length=40)
    adults: int = Field(default=2, ge=1, le=20)
    children: int = Field(default=0, ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list, max_length=20)
    source_booking_id: str | None = Field(default=None, max_length=128)
    collect_by: str = Field(default="target_hotel", pattern="^(source_hotel|target_hotel)$")
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_stay(self):
        if len(self.child_ages) != self.children or any(age < 0 or age > 17 for age in self.child_ages):
            raise ValueError("Her çocuk için 0-17 arasında yaş girilmelidir")
        if datetime.fromisoformat(self.check_out) <= datetime.fromisoformat(self.check_in):
            raise ValueError("Çıkış tarihi girişten sonra olmalıdır")
        return self


class NetworkRequestDecision(BaseModel):
    accept: bool
    reason: str = Field(default="", max_length=1000)
    alternative_rate: float | None = Field(default=None, gt=0)


@router.post("/contracts")
async def propose_contract(data: NetworkContractCreate, user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    if data.partner_tenant_id == tenant_id:
        raise HTTPException(400, "Tesis kendi kendisiyle sözleşme yapamaz")
    sysdb = get_system_db()
    await _hotel_name(sysdb, data.partner_tenant_id)  # existence is deliberately not leaked
    pair = sorted([tenant_id, data.partner_tenant_id])
    existing = await sysdb.hotel_network_contracts.find_one(
        {"tenant_pair": pair, "status": {"$in": ["pending", "active"]}}, {"_id": 0, "id": 1}
    )
    if existing:
        raise HTTPException(409, "Bu iki tesis arasında açık bir sözleşme süreci var")
    doc = {
        "id": _id(), "tenant_pair": pair, "proposer_tenant_id": tenant_id,
        "partner_tenant_id": data.partner_tenant_id, "status": "pending",
        **data.model_dump(exclude={"partner_tenant_id"}),
        "created_by": user.id, "created_at": _now(), "updated_at": _now(),
    }
    await sysdb.hotel_network_contracts.insert_one(doc)
    await _audit(sysdb, tenant_id, user.id, "contract.proposed", doc["id"], {"partner_tenant_id": data.partner_tenant_id})
    doc.pop("_id", None)
    return {"ok": True, "contract": doc}


@router.get("/contracts")
async def list_contracts(user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    sysdb = get_system_db()
    rows = await sysdb.hotel_network_contracts.find(
        {"tenant_pair": tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    for row in rows:
        other = next((item for item in row["tenant_pair"] if item != tenant_id), tenant_id)
        row["partner_name"] = await _hotel_name(sysdb, other)
        row["direction"] = "outgoing" if row.get("proposer_tenant_id") == tenant_id else "incoming"
    return {"contracts": rows}


@router.post("/contracts/{contract_id}/decision")
async def decide_contract(contract_id: str, data: ContractDecision, user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    sysdb = get_system_db()
    contract = await sysdb.hotel_network_contracts.find_one(
        {"id": contract_id, "tenant_pair": tenant_id, "status": "pending"}, {"_id": 0}
    )
    if not contract:
        raise HTTPException(404, "Bekleyen sözleşme bulunamadı")
    if contract["proposer_tenant_id"] == tenant_id:
        raise HTTPException(403, "Teklifi gönderen tesis kendi teklifini onaylayamaz")
    status = "active" if data.accept else "rejected"
    await sysdb.hotel_network_contracts.update_one(
        {"id": contract_id, "status": "pending"},
        {"$set": {"status": status, "decision_note": data.note, "decided_by": user.id, "decided_at": _now(), "updated_at": _now()}},
    )
    await _audit(sysdb, tenant_id, user.id, f"contract.{status}", contract_id)
    return {"ok": True, "status": status}


@router.post("/listings")
async def create_listing(data: NetworkListingCreate, user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    if datetime.fromisoformat(data.date_end) <= datetime.fromisoformat(data.date_start):
        raise HTTPException(400, "İlan bitiş tarihi başlangıçtan sonra olmalıdır")
    doc = {
        "id": _id(), "seller_tenant_id": tenant_id, "status": "active",
        "reserved_count": 0, **data.model_dump(), "created_by": user.id,
        "created_at": _now(), "updated_at": _now(),
    }
    sysdb = get_system_db()
    await sysdb.hotel_network_listings.insert_one(doc)
    await _audit(sysdb, tenant_id, user.id, "listing.created", doc["id"], {"visibility": doc["visibility"]})
    doc.pop("_id", None)
    return {"ok": True, "listing": doc}


@router.get("/feed")
async def network_feed(
    check_in: str | None = Query(None), check_out: str | None = Query(None),
    room_type: str | None = Query(None), user: User = Depends(get_current_user),
):
    tenant_id = _tenant(user)
    sysdb = get_system_db()
    query: dict = {"seller_tenant_id": {"$ne": tenant_id}, "status": "active"}
    if check_in and check_out:
        query.update({"date_start": {"$lte": check_in}, "date_end": {"$gte": check_out}})
    if room_type:
        query["room_type"] = room_type
    rows = await sysdb.hotel_network_listings.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    visible = []
    for row in rows:
        contract = await _active_contract(sysdb, tenant_id, row["seller_tenant_id"])
        if row["visibility"] == "contracts_only" and not contract:
            continue
        if row["visibility"] == "selected" and tenant_id not in row.get("selected_tenant_ids", []):
            continue
        available = int(row.get("allotment", 0)) - int(row.get("reserved_count", 0))
        if available <= 0:
            continue
        item = {k: v for k, v in row.items() if k not in {"seller_tenant_id", "selected_tenant_ids", "created_by"}}
        item["available"] = available
        item["relationship"] = "contracted" if contract else "spot"
        item["seller_name"] = await _hotel_name(sysdb, row["seller_tenant_id"]) if contract else "Kapalı devre tesis"
        item["automatic_confirmation"] = bool(contract and contract.get("approval_mode") == "automatic" and row.get("approval_mode") == "automatic")
        visible.append(item)
    return {"listings": visible}


@router.get("/listings/mine")
async def my_listings(user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    rows = await get_system_db().hotel_network_listings.find(
        {"seller_tenant_id": tenant_id}, {"_id": 0, "selected_tenant_ids": 0, "created_by": 0}
    ).sort("created_at", -1).to_list(500)
    for row in rows:
        row["available"] = max(0, int(row.get("allotment", 0)) - int(row.get("reserved_count", 0)))
    return {"listings": rows}


async def _create_target_booking(sysdb, request_doc: dict, actor_id: str) -> dict:
    target = request_doc["target_tenant_id"]
    with tenant_context(target):
        rooms = await db.rooms.find(
            {"tenant_id": target, "room_type": request_doc["room_type"], "is_active": {"$ne": False}, "status": {"$nin": ["maintenance", "out_of_order", "blocked"]}},
            {"_id": 0},
        ).to_list(500)
    if not rooms:
        raise HTTPException(409, "Hedef tesiste uygun oda tipi kalmadı")
    booking_id = _id()
    target_name = await _hotel_name(sysdb, target)
    source_name = await _hotel_name(sysdb, request_doc["source_tenant_id"])
    last_conflict = None
    for room in rooms:
        booking = {
            "id": booking_id, "tenant_id": target, "room_id": room.get("id"),
            "room_type": request_doc["room_type"], "guest_name": request_doc["guest_name"],
            "guest_email": request_doc.get("guest_email"), "guest_phone": request_doc.get("guest_phone", ""),
            "check_in": request_doc["check_in"] + "T14:00:00+00:00",
            "check_out": request_doc["check_out"] + "T11:00:00+00:00",
            "adults": request_doc.get("adults", 2), "children": request_doc.get("children", 0),
            "child_ages": request_doc.get("child_ages", []), "status": "confirmed",
            "source_channel": "hotel_network", "source": f"Otel Ağı · {source_name}",
            "source_hotel_id": request_doc["source_tenant_id"], "source_hotel_name": source_name,
            "hotel_network_request_id": request_doc["id"], "total_amount": request_doc["total_amount"],
            "currency": "TRY", "notes": request_doc.get("note", ""), "created_by": actor_id,
            "created_at": _now(), "updated_at": _now(), "target_hotel_name": target_name,
        }
        try:
            return await create_booking_atomic(tenant_id=target, booking_doc=booking)
        except BookingConflictError as exc:
            last_conflict = exc
    raise HTTPException(409, f"Hedef tesiste oda kalmadı: {last_conflict or 'müsaitlik değişti'}")


async def _post_interhotel_ledger(sysdb, request_doc: dict, target_booking: dict) -> list[dict]:
    gross = float(request_doc["total_amount"])
    commission = round(gross * float(request_doc.get("commission_pct", 0)) / 100, 2)
    if request_doc["collect_by"] == "source_hotel":
        amount = round(gross - commission, 2)
        debtor, creditor, reason = request_doc["source_tenant_id"], request_doc["target_tenant_id"], "Konaklama net bedeli"
    else:
        amount = commission
        debtor, creditor, reason = request_doc["target_tenant_id"], request_doc["source_tenant_id"], "Yönlendirme komisyonu"
    transfer_ref = f"OTA-{datetime.now(UTC).year}-{request_doc['id'][:8].upper()}"
    common = {
        "id": _id(), "transfer_reference": transfer_ref, "request_id": request_doc["id"],
        "source_booking_id": request_doc.get("source_booking_id"), "target_booking_id": target_booking["id"],
        "gross_amount": gross, "commission_amount": commission, "amount": amount,
        "currency": "TRY", "reason": reason, "status": "open", "created_at": _now(),
    }
    debit = {**common, "id": _id(), "tenant_id": debtor, "counterparty_tenant_id": creditor, "entry_type": "payable"}
    credit = {**common, "id": _id(), "tenant_id": creditor, "counterparty_tenant_id": debtor, "entry_type": "receivable"}
    await sysdb.hotel_network_ledger.insert_many([debit, credit])
    return [debit, credit]


async def _accept_request(sysdb, request_doc: dict, actor_id: str) -> dict:
    claimed = await sysdb.hotel_network_requests.find_one_and_update(
        {"id": request_doc["id"], "status": "pending"},
        {"$set": {"status": "processing", "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        current = await sysdb.hotel_network_requests.find_one({"id": request_doc["id"]}, {"_id": 0})
        if current and current.get("status") == "accepted":
            return current
        raise HTTPException(409, "Talep başka bir işlem tarafından sonuçlandırıldı")
    listing_claimed = False
    target_booking = None
    try:
        listing = await sysdb.hotel_network_listings.find_one_and_update(
            {
                "id": claimed["listing_id"], "status": "active",
                "$expr": {"$lt": [{"$ifNull": ["$reserved_count", 0]}, "$allotment"]},
            },
            {"$inc": {"reserved_count": 1}, "$set": {"updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )
        if not listing:
            raise HTTPException(409, "Paylaşılan kontenjan doldu")
        listing_claimed = True
        target_booking = await _create_target_booking(sysdb, claimed, actor_id)
        ledger = await _post_interhotel_ledger(sysdb, claimed, target_booking)
        if claimed.get("source_booking_id"):
            with tenant_context(claimed["source_tenant_id"]):
                await db.bookings.update_one(
                    {"tenant_id": claimed["source_tenant_id"], "id": claimed["source_booking_id"]},
                    {"$set": {"property_transfer_status": "accepted", "transferred_to_tenant_id": claimed["target_tenant_id"], "transferred_to_booking_id": target_booking["id"], "hotel_network_request_id": claimed["id"], "updated_at": _now()}},
                )
        await sysdb.hotel_network_requests.update_one(
            {"id": claimed["id"], "status": "processing"},
            {"$set": {"status": "accepted", "target_booking_id": target_booking["id"], "transfer_reference": ledger[0]["transfer_reference"], "accepted_by": actor_id, "accepted_at": _now(), "updated_at": _now()}},
        )
        await _audit(sysdb, claimed["target_tenant_id"], actor_id, "request.accepted", claimed["id"], {"target_booking_id": target_booking["id"]})
        return {"ok": True, "status": "accepted", "target_booking_id": target_booking["id"], "transfer_reference": ledger[0]["transfer_reference"]}
    except Exception:
        if listing_claimed and target_booking is None:
            await sysdb.hotel_network_listings.update_one(
                {"id": claimed["listing_id"], "reserved_count": {"$gt": 0}},
                {"$inc": {"reserved_count": -1}, "$set": {"updated_at": _now()}},
            )
        next_status = "needs_review" if target_booking else "pending"
        update = {"status": next_status, "updated_at": _now()}
        if target_booking:
            update["target_booking_id"] = target_booking["id"]
        await sysdb.hotel_network_requests.update_one(
            {"id": claimed["id"], "status": "processing"}, {"$set": update}
        )
        raise


@router.post("/requests")
async def create_request(data: NetworkRequestCreate, user: User = Depends(get_current_user)):
    source = _tenant(user)
    sysdb = get_system_db()
    listing = await sysdb.hotel_network_listings.find_one({"id": data.listing_id, "status": "active"}, {"_id": 0})
    if not listing or listing["seller_tenant_id"] == source:
        raise HTTPException(404, "Paylaşım ilanı bulunamadı")
    contract = await _active_contract(sysdb, source, listing["seller_tenant_id"])
    allowed = listing["visibility"] == "network" or bool(contract) or source in listing.get("selected_tenant_ids", [])
    if not allowed:
        raise HTTPException(403, "Bu paylaşım yalnız yetkili tesislere açıktır")
    if not (listing["date_start"] <= data.check_in and listing["date_end"] >= data.check_out):
        raise HTTPException(409, "Talep tarihleri paylaşım aralığı dışında")
    source_booking = None
    if data.source_booking_id:
        with tenant_context(source):
            source_booking = await db.bookings.find_one({"tenant_id": source, "id": data.source_booking_id}, {"_id": 0, "id": 1})
        if not source_booking:
            raise HTTPException(404, "Kaynak rezervasyon bulunamadı")
    nights = (datetime.fromisoformat(data.check_out) - datetime.fromisoformat(data.check_in)).days
    commission_pct = float((contract or {}).get("commission_pct", 0))
    doc = {
        "id": _id(), "listing_id": listing["id"], "source_tenant_id": source,
        "target_tenant_id": listing["seller_tenant_id"], "room_type": listing["room_type"],
        "nightly_rate": listing["nightly_rate"], "total_amount": round(listing["nightly_rate"] * nights, 2),
        "allotment": listing["allotment"], "commission_pct": commission_pct,
        "relationship": "contracted" if contract else "spot", "status": "pending",
        **data.model_dump(exclude={"listing_id"}), "created_by": user.id, "created_at": _now(), "updated_at": _now(),
    }
    await sysdb.hotel_network_requests.insert_one(doc)
    await _audit(sysdb, source, user.id, "request.created", doc["id"], {"target_tenant_id": doc["target_tenant_id"], "relationship": doc["relationship"]})
    doc.pop("_id", None)
    automatic = bool(contract and contract.get("approval_mode") == "automatic" and listing.get("approval_mode") == "automatic")
    if automatic:
        return await _accept_request(sysdb, doc, user.id)
    return {"ok": True, "status": "pending", "request": {k: v for k, v in doc.items() if k not in {"guest_email", "guest_phone"}}}


@router.get("/requests")
async def list_requests(user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    sysdb = get_system_db()
    rows = await sysdb.hotel_network_requests.find(
        {"$or": [{"source_tenant_id": tenant_id}, {"target_tenant_id": tenant_id}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    for row in rows:
        row["direction"] = "outgoing" if row["source_tenant_id"] == tenant_id else "incoming"
        row["source_hotel_name"] = await _hotel_name(sysdb, row["source_tenant_id"])
        row["target_hotel_name"] = await _hotel_name(sysdb, row["target_tenant_id"])
        if row["direction"] == "incoming" and row.get("status") not in {"accepted", "completed"}:
            row["guest_name"] = "Kabul sonrası paylaşılacak"
            row.pop("guest_email", None)
            row.pop("guest_phone", None)
    return {"requests": rows}


@router.post("/requests/{request_id}/decision")
async def decide_request(request_id: str, data: NetworkRequestDecision, user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    sysdb = get_system_db()
    request_doc = await sysdb.hotel_network_requests.find_one(
        {"id": request_id, "target_tenant_id": tenant_id, "status": "pending"}, {"_id": 0}
    )
    if not request_doc:
        raise HTTPException(404, "Bekleyen talep bulunamadı")
    if not data.accept:
        if len(data.reason.strip()) < 3:
            raise HTTPException(400, "Ret nedeni zorunludur")
        await sysdb.hotel_network_requests.update_one(
            {"id": request_id, "target_tenant_id": tenant_id, "status": "pending"},
            {"$set": {"status": "rejected", "decision_reason": data.reason.strip(), "decided_by": user.id, "decided_at": _now(), "updated_at": _now()}},
        )
        await _audit(sysdb, tenant_id, user.id, "request.rejected", request_id, {"reason": data.reason.strip()})
        return {"ok": True, "status": "rejected"}
    if data.alternative_rate:
        request_doc["nightly_rate"] = data.alternative_rate
        nights = (datetime.fromisoformat(request_doc["check_out"]) - datetime.fromisoformat(request_doc["check_in"])).days
        request_doc["total_amount"] = round(data.alternative_rate * nights, 2)
        await sysdb.hotel_network_requests.update_one(
            {"id": request_id, "status": "pending"},
            {"$set": {"nightly_rate": data.alternative_rate, "total_amount": request_doc["total_amount"], "alternative_note": data.reason, "updated_at": _now()}},
        )
    return await _accept_request(sysdb, request_doc, user.id)


@router.get("/ledger")
async def network_ledger(status: str | None = Query(None), user: User = Depends(get_current_user)):
    tenant_id = _tenant(user)
    query: dict = {"tenant_id": tenant_id}
    if status:
        query["status"] = status
    sysdb = get_system_db()
    rows = await sysdb.hotel_network_ledger.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    receivable = round(sum(row["amount"] for row in rows if row["entry_type"] == "receivable" and row["status"] == "open"), 2)
    payable = round(sum(row["amount"] for row in rows if row["entry_type"] == "payable" and row["status"] == "open"), 2)
    for row in rows:
        row["counterparty_name"] = await _hotel_name(sysdb, row["counterparty_tenant_id"])
    return {"entries": rows, "summary": {"open_receivable": receivable, "open_payable": payable, "net": round(receivable - payable, 2), "currency": "TRY"}}
