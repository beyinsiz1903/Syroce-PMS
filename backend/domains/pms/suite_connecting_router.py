"""Opera #9 — Suite & Connecting Rooms.
İki yapı:
  1) Suite: master oda + bileşen odalar (suite satılınca tüm bileşenler
     bloke olur). Bir oda yalnızca bir suite'in master'ı veya bileşeni olabilir.
  2) Connecting pair: yan yana kapı bağlı iki oda (esnek bilgi; housekeeping
     ve aile rezervasyonları için).
Yetki: manage_rates (oda yapılandırma yetkisi).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/suite-connecting", tags=["Suite & Connecting"])

_INDEX_INIT = False


async def _ensure_indexes(db) -> None:
    global _INDEX_INIT
    if _INDEX_INIT:
        return
    try:
        await db.suite_definitions.create_index(
            [("tenant_id", 1), ("master_room_id", 1)],
            unique=True,
            partialFilterExpression={"active": True},
            name="suite_master_unique_active",
        )
        # Multikey unique on all_room_ids — component+master exclusivity
        await db.suite_definitions.create_index(
            [("tenant_id", 1), ("all_room_ids", 1)],
            unique=True,
            partialFilterExpression={"active": True},
            name="suite_all_rooms_unique_active",
        )
        await db.connecting_pairs.create_index(
            [("tenant_id", 1), ("room_a_id", 1), ("room_b_id", 1)],
            unique=True,
            partialFilterExpression={"active": True},
            name="connecting_pair_unique_active",
        )
        _INDEX_INIT = True
    except Exception as e:  # noqa: BLE001
        logger.error("Suite/Connecting index oluşturulamadı: %s", e)
        raise HTTPException(503, "Altyapı hazır değil, tekrar deneyin") from e


class SuiteDefinition(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1, max_length=120)
    master_room_id: str
    component_room_ids: list[str] = Field(default_factory=list)
    description: str | None = None
    active: bool = True


class ConnectingPair(BaseModel):
    id: str | None = None
    room_a_id: str
    room_b_id: str
    note: str | None = None
    active: bool = True


async def _get_room(db, tenant_id: str, room_id: str) -> dict | None:
    return await db.rooms.find_one(
        {
            "$or": [{"id": room_id}, {"_id": room_id}],
            "tenant_id": tenant_id,
        }
    )


async def _room_in_use(db, tenant_id: str, room_id: str, exclude_suite_id: str | None = None) -> str | None:
    """Oda başka bir aktif suite'in master'ı veya bileşeni mi? İlgili suite adını döner."""
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "active": True,
        "$or": [{"master_room_id": room_id}, {"component_room_ids": room_id}],
    }
    if exclude_suite_id:
        q["id"] = {"$ne": exclude_suite_id}
    s = await db.suite_definitions.find_one(q)
    return s["name"] if s else None


# ---------- Suites ----------


@router.get("/suites", response_model=list[SuiteDefinition])
async def list_suites(
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    cur = db.suite_definitions.find({"tenant_id": user.tenant_id, "active": True}).sort([("name", 1)])
    out: list[dict[str, Any]] = []
    async for d in cur:
        d.pop("_id", None)
        out.append(d)
    return out


@router.post("/suites", response_model=SuiteDefinition, status_code=201)
async def create_suite(
    payload: SuiteDefinition,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    await _ensure_indexes(db)

    if payload.master_room_id in payload.component_room_ids:
        raise HTTPException(400, "Master oda bileşen olarak eklenemez")
    if len(set(payload.component_room_ids)) != len(payload.component_room_ids):
        raise HTTPException(400, "Bileşen odalarda tekrar var")

    # Tüm odalar var mı?
    all_ids = [payload.master_room_id, *payload.component_room_ids]
    for rid in all_ids:
        if not await _get_room(db, user.tenant_id, rid):
            raise HTTPException(400, f"Oda bulunamadı: {rid}")

    # Çakışma: oda başka bir suite'te kullanılıyor mu?
    for rid in all_ids:
        used_in = await _room_in_use(db, user.tenant_id, rid)
        if used_in:
            raise HTTPException(409, f"Oda '{rid}' zaten suite'te: {used_in}")

    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    # Multikey index için derived alan (master + components — exclusivity garantisi)
    doc["all_room_ids"] = [payload.master_room_id, *payload.component_room_ids]
    doc["created_by"] = user.email
    doc["created_at"] = datetime.now(UTC).isoformat()
    try:
        await db.suite_definitions.insert_one(doc)
    except Exception as e:  # noqa: BLE001
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(
                409,
                "Bu suite'teki bir oda zaten başka bir aktif suite'te kullanılıyor",
            ) from e
        raise
    doc.pop("_id", None)
    return doc


@router.delete("/suites/{suite_id}", status_code=204)
async def delete_suite(
    suite_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    res = await db.suite_definitions.update_one(
        {"id": suite_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False, "deleted_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Suite bulunamadı")


@router.get("/suites/{suite_id}/blocked-rooms")
async def suite_blocked_rooms(
    suite_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    """Suite satıldığında bloke edilecek oda id'lerinin listesi (master + bileşenler).
    Booking akışı bu uçtan ID listesini alıp tüm odaları işaretler."""
    db = get_system_db()
    s = await db.suite_definitions.find_one(
        {
            "id": suite_id,
            "tenant_id": user.tenant_id,
            "active": True,
        }
    )
    if not s:
        raise HTTPException(404, "Suite bulunamadı")
    return {
        "suite_id": suite_id,
        "name": s["name"],
        "rooms_to_block": [s["master_room_id"], *s.get("component_room_ids", [])],
    }


# ---------- Connecting pairs ----------


@router.get("/connecting", response_model=list[ConnectingPair])
async def list_connecting(
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    cur = db.connecting_pairs.find({"tenant_id": user.tenant_id, "active": True}).sort([("room_a_id", 1)])
    out: list[dict[str, Any]] = []
    async for d in cur:
        d.pop("_id", None)
        out.append(d)
    return out


def _normalize_pair(a: str, b: str) -> tuple[str, str]:
    """Çift sırasını normalize et (alfabetik) — A↔B = B↔A."""
    return (a, b) if a <= b else (b, a)


@router.post("/connecting", response_model=ConnectingPair, status_code=201)
async def create_connecting(
    payload: ConnectingPair,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    if payload.room_a_id == payload.room_b_id:
        raise HTTPException(400, "Oda kendine bağlanamaz")
    db = get_system_db()
    await _ensure_indexes(db)

    a, b = _normalize_pair(payload.room_a_id, payload.room_b_id)
    for rid in (a, b):
        if not await _get_room(db, user.tenant_id, rid):
            raise HTTPException(400, f"Oda bulunamadı: {rid}")

    existing = await db.connecting_pairs.find_one(
        {
            "tenant_id": user.tenant_id,
            "room_a_id": a,
            "room_b_id": b,
            "active": True,
        }
    )
    if existing:
        raise HTTPException(409, "Bu çift zaten kayıtlı")

    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["room_a_id"] = a
    doc["room_b_id"] = b
    doc["created_by"] = user.email
    doc["created_at"] = datetime.now(UTC).isoformat()
    try:
        await db.connecting_pairs.insert_one(doc)
    except Exception as e:  # noqa: BLE001
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(409, "Bu çift zaten kayıtlı") from e
        raise
    doc.pop("_id", None)
    return doc


@router.delete("/connecting/{pair_id}", status_code=204)
async def delete_connecting(
    pair_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    res = await db.connecting_pairs.update_one(
        {"id": pair_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False, "deleted_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Çift bulunamadı")


@router.get("/rooms/{room_id}/connections")
async def room_connections(
    room_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    """Bir odanın bağlı olduğu diğer odalar (her iki yön)."""
    db = get_system_db()
    cur = db.connecting_pairs.find(
        {
            "tenant_id": user.tenant_id,
            "active": True,
            "$or": [{"room_a_id": room_id}, {"room_b_id": room_id}],
        }
    )
    out: list[str] = []
    async for d in cur:
        other = d["room_b_id"] if d["room_a_id"] == room_id else d["room_a_id"]
        out.append(other)
    return {"room_id": room_id, "connected_to": out}
