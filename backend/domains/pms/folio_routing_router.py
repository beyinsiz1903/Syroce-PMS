"""Folio Routing Instructions — oda/ekstra ücretlerini farklı folio'ya
veya master/şirket hesabına yönlendirme kuralları (Opera "routing").
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/folio-routing", tags=["PMS / Folio Routing"])


class RoutingInstructionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_folio_id: str = Field(min_length=1, max_length=100)
    dest_folio_id: str = Field(min_length=1, max_length=100)
    charge_codes: list[str] = Field(default_factory=list, max_length=50)
    from_date: date | None = None
    to_date: date | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_range(self):
        if self.source_folio_id == self.dest_folio_id or (self.from_date and self.to_date and self.from_date > self.to_date):
            raise ValueError("Kaynak/hedef veya tarih aralığı geçersiz")
        self.charge_codes = sorted({code.upper() for code in self.charge_codes if code})
        return self


class RoutingInstruction(RoutingInstructionCreate):
    id: str
    tenant_id: str
    created_by: str
    created_at: str
    active: bool = True


_INDEXES_INITIALIZED = False


async def _ensure_indexes() -> None:
    global _INDEXES_INITIALIZED
    if _INDEXES_INITIALIZED:
        return
    db = get_system_db()
    try:
        await db.folio_routing.create_index(
            [("tenant_id", 1), ("source_folio_id", 1), ("active", 1)],
            name="folio_routing_src",
        )
        await db.folio_routing.create_index([("tenant_id", 1), ("dest_folio_id", 1)], name="folio_routing_dest")
        _INDEXES_INITIALIZED = True
    except Exception:
        # Index oluşturulamazsa flag set edilmez → bir sonraki çağrıda yeniden denenir.
        pass


@router.get("", response_model=list[RoutingInstruction])
async def list_routing(
    folio_id: str | None = None,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_folio")),
):
    await _ensure_indexes()
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": user.tenant_id, "active": True}
    if folio_id:
        q["$or"] = [{"source_folio_id": folio_id}, {"dest_folio_id": folio_id}]
    docs = await db.folio_routing.find(q).sort("created_at", -1).to_list(500)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("", response_model=RoutingInstruction, status_code=201)
async def create_routing(body: RoutingInstructionCreate, user: User = Depends(get_current_user),
                         _perm=Depends(require_op("transfer_folio"))):
    await _ensure_indexes()
    db = get_system_db()
    if body.source_folio_id == body.dest_folio_id:
        raise HTTPException(400, "Kaynak ve hedef folio aynı olamaz")
    src = await db.folios.find_one({"_id": body.source_folio_id, "tenant_id": user.tenant_id}) or await db.folios.find_one({"id": body.source_folio_id, "tenant_id": user.tenant_id})
    dst = await db.folios.find_one({"_id": body.dest_folio_id, "tenant_id": user.tenant_id}) or await db.folios.find_one({"id": body.dest_folio_id, "tenant_id": user.tenant_id})
    if not src or not dst:
        raise HTTPException(404, "Folio bulunamadı")
    if src.get("status") != "open" or dst.get("status") != "open":
        raise HTTPException(409, "Yalnız açık folyolar arasında kural oluşturulabilir")
    if not src.get("booking_id") or src.get("booking_id") != dst.get("booking_id"):
        raise HTTPException(409, "Bu akış yalnız aynı rezervasyonun folyoları içindir; grup/oda aktarımı ayrı işlem gerektirir")
    from modules.pms_core.enterprise_billing import currency

    booking = await db.bookings.find_one({"tenant_id": user.tenant_id, "id": src["booking_id"]}, {"currency": 1})
    if not booking or currency(src.get("currency") or booking.get("currency")) != currency(dst.get("currency") or booking.get("currency")):
        raise HTTPException(409, "Folyo para birimleri aynı olmalı")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "created_by": user.email,
        "created_at": datetime.now(UTC).isoformat(),
        "active": True,
        **body.model_dump(mode="json"),
    }
    await db.folio_routing.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{routing_id}", status_code=204)
async def delete_routing(routing_id: str, user: User = Depends(get_current_user),
                         _perm=Depends(require_op("transfer_folio"))):
    db = get_system_db()
    res = await db.folio_routing.update_one(
        {"id": routing_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False, "deleted_at": datetime.now(UTC).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Routing kuralı bulunamadı")
    return None


@router.post("/apply/{folio_id}")
async def apply_routing(folio_id: str, user: User = Depends(get_current_user),
                        _perm=Depends(require_op("transfer_folio"))):
    """Actually move posted original items; never report a marker as a move.

    This legacy endpoint remains MANUAL. Automatic future-night/POS routing is
    not claimed by storing a rule. Overlaps or closed destinations fail closed.
    """
    from core.booking_atomicity import is_replica_set_unavailable, with_resource_locks
    from core.database import client
    from modules.pms_core.folio_allocation import FolioAllocationRequest, allocate_posted_debt
    from modules.pms_core.report_money import money

    db = get_system_db()
    source = await db.folios.find_one({"tenant_id": user.tenant_id, "id": folio_id})
    if not source or not source.get("booking_id"):
        raise HTTPException(404, "Kaynak folyo bulunamadı")

    async def commit(session):
        rules = await db.folio_routing.find({"tenant_id": user.tenant_id, "source_folio_id": folio_id, "active": True}, session=session).to_list(None)
        if not rules:
            return {"moved": 0, "rules": 0, "execution": "manual_posted_items"}
        charges = await db.folio_charges.find({"tenant_id": user.tenant_id, "folio_id": folio_id, "voided": {"$ne": True}}, {"_id": 0}, session=session).to_list(None)
        groups = {}
        for charge in charges:
            if not charge.get("id") or money(charge.get("total", charge.get("amount", 0))) <= 0 or charge.get("charge_category") == "split_adjustment":
                continue
            codes = {str(charge.get(key) or "").upper() for key in ["charge_code", "charge_category", "category"]} - {""}
            candidates = [rule for rule in rules if not rule.get("charge_codes") or codes.intersection(code.upper() for code in rule["charge_codes"])]
            if not candidates:
                continue
            day = str(charge.get("business_date") or charge.get("night_audit_date") or "")[:10]
            try:
                date.fromisoformat(day)
            except ValueError:
                raise HTTPException(409, "Masrafın muhasebe günü eksik; tarih tahminiyle yönlendirme yapılamaz") from None
            matched = [rule for rule in candidates if (not rule.get("from_date") or day >= rule["from_date"])
                       and (not rule.get("to_date") or day <= rule["to_date"])]
            if len(matched) > 1:
                raise HTTPException(409, "Aynı masraf birden fazla kurala uyuyor; çakışan kuralları düzeltin")
            if matched:
                groups.setdefault(matched[0]["id"], []).append(charge)
        moved = 0
        for rule in rules:
            selected = groups.get(rule["id"], [])
            if not selected:
                continue
            if len(selected) > 200:
                raise HTTPException(409, "Tek uygulamada en fazla 200 kalem taşınabilir; kalemleri tarih aralıklarıyla ayırın")
            ids = sorted(row["id"] for row in selected)
            total = sum(money(row.get("total", row.get("amount", 0))) for row in selected)
            key = uuid.uuid5(uuid.NAMESPACE_URL, f"routing:{user.tenant_id}:{rule['id']}:{','.join(ids)}:{total}")
            body = FolioAllocationRequest(request_id=key, booking_id=source["booking_id"], source_folio_id=folio_id,
                target_folio_id=rule["dest_folio_id"], mode="items", charge_ids=ids, expected_amount=total,
                reason=f"Yönlendirme kuralı {rule['id']}")
            await allocate_posted_debt(db, user.tenant_id, user.id, body, session=session)
            moved += len(ids)
        return {"moved": moved, "rules": len(rules), "execution": "manual_posted_items"}

    try:
        result = await with_resource_locks(client=client, db=db, tenant_id=user.tenant_id,
            locks_collection="reservation_financial_locks", resources=[("booking", source["booking_id"])], callback=commit)
    except Exception as exc:
        if is_replica_set_unavailable(exc):
            raise HTTPException(503, "Yönlendirme için transaction desteği gerekli") from exc
        raise
    from core.report_cache import invalidate_financial_report_caches

    invalidate_financial_report_caches(user.tenant_id)
    return result
