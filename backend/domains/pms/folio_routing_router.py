"""Folio Routing Instructions — oda/ekstra ücretlerini farklı folio'ya
veya master/şirket hesabına yönlendirme kuralları (Opera "routing").
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User

router = APIRouter(prefix="/api/folio-routing", tags=["PMS / Folio Routing"])


class RoutingInstructionCreate(BaseModel):
    source_folio_id: str = Field(..., description="Kaynak folio (oda misafiri)")
    dest_folio_id: str = Field(..., description="Hedef folio (master/şirket)")
    charge_codes: list[str] = Field(default_factory=list, description="['ROOM','TAX','BREAKFAST']; boş = TÜM")
    from_date: str | None = None
    to_date: str | None = None
    note: str | None = None


class RoutingInstruction(RoutingInstructionCreate):
    id: str
    tenant_id: str
    created_by: str
    created_at: str
    active: bool = True


async def _ensure_indexes() -> None:
    db = get_system_db()
    try:
        await db.folio_routing.create_index(
            [("tenant_id", 1), ("source_folio_id", 1), ("active", 1)],
            name="folio_routing_src",
        )
        await db.folio_routing.create_index(
            [("tenant_id", 1), ("dest_folio_id", 1)], name="folio_routing_dest"
        )
    except Exception:
        pass


@router.get("", response_model=list[RoutingInstruction])
async def list_routing(
    folio_id: str | None = None,
    user: User = Depends(get_current_user),
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
async def create_routing(
    body: RoutingInstructionCreate, user: User = Depends(get_current_user)
):
    await _ensure_indexes()
    db = get_system_db()
    if body.source_folio_id == body.dest_folio_id:
        raise HTTPException(400, "Kaynak ve hedef folio aynı olamaz")
    src = await db.folios.find_one(
        {"_id": body.source_folio_id, "tenant_id": user.tenant_id}
    ) or await db.folios.find_one(
        {"id": body.source_folio_id, "tenant_id": user.tenant_id}
    )
    dst = await db.folios.find_one(
        {"_id": body.dest_folio_id, "tenant_id": user.tenant_id}
    ) or await db.folios.find_one(
        {"id": body.dest_folio_id, "tenant_id": user.tenant_id}
    )
    if not src or not dst:
        raise HTTPException(404, "Folio bulunamadı")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "created_by": user.email,
        "created_at": datetime.now(UTC).isoformat(),
        "active": True,
        **body.model_dump(),
    }
    await db.folio_routing.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{routing_id}", status_code=204)
async def delete_routing(routing_id: str, user: User = Depends(get_current_user)):
    db = get_system_db()
    res = await db.folio_routing.update_one(
        {"id": routing_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False, "deleted_at": datetime.now(UTC).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Routing kuralı bulunamadı")
    return None


@router.post("/apply/{folio_id}")
async def apply_routing(folio_id: str, user: User = Depends(get_current_user)):
    """Folio'daki uygun ücretleri rota kurallarına göre hedef folio'ya taşır.
    Charges koleksiyonunu günceller; idempotent değil — manuel tetikleme.
    """
    db = get_system_db()
    rules = await db.folio_routing.find(
        {"tenant_id": user.tenant_id, "source_folio_id": folio_id, "active": True}
    ).to_list(50)
    if not rules:
        return {"moved": 0, "rules": 0}
    moved = 0
    for r in rules:
        match: dict[str, Any] = {
            "tenant_id": user.tenant_id,
            "folio_id": folio_id,
            "routed_to": {"$exists": False},
        }
        if r.get("charge_codes"):
            match["charge_code"] = {"$in": r["charge_codes"]}
        if r.get("from_date"):
            match.setdefault("posted_at", {})["$gte"] = r["from_date"]
        if r.get("to_date"):
            match.setdefault("posted_at", {})["$lte"] = r["to_date"]
        res = await db.folio_charges.update_many(
            match,
            {
                "$set": {
                    "routed_to": r["dest_folio_id"],
                    "routed_by_rule": r["id"],
                    "routed_at": datetime.now(UTC).isoformat(),
                }
            },
        )
        moved += res.modified_count
    return {"moved": moved, "rules": len(rules)}
