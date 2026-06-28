"""Opera #10 — Hurdle Rates.
Tarih bazlı minimum kabul edilebilir oran (revenue management eşiği).
- CRUD: hurdle tanımları (tarih aralığı, room_type, channel, min_rate)
- Check: bir tarih+oda+kanal+teklif fiyat için kabul/red kararı
- Specificity önceliği: room_type+channel > room_type > channel > all
- Yetki: manage_rates
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hurdle-rates", tags=["Hurdle Rates"])

_INDEX_INIT = False


async def _ensure_indexes(db) -> None:
    global _INDEX_INIT
    if _INDEX_INIT:
        return
    try:
        await db.hurdle_rates.create_index(
            [("tenant_id", 1), ("date_from", 1), ("date_to", 1)],
            name="hurdle_date_range",
            partialFilterExpression={"active": True},
        )
        _INDEX_INIT = True
    except Exception as e:  # noqa: BLE001
        logger.error("Hurdle index oluşturulamadı: %s", e)
        raise HTTPException(503, "Altyapı hazır değil") from e


class HurdleRate(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1, max_length=120)
    date_from: str = Field(..., description="ISO date YYYY-MM-DD")
    date_to: str = Field(..., description="ISO date YYYY-MM-DD")
    room_type: str | None = Field(None, max_length=64)  # None → tüm tipler
    channel: str | None = Field(None, max_length=64)  # None → tüm kanallar
    min_rate: float = Field(..., ge=0)
    currency: str = Field("TRY", min_length=3, max_length=3)
    note: str | None = None
    active: bool = True

    @model_validator(mode="after")
    def _validate_dates(self):
        try:
            df = date.fromisoformat(self.date_from)
            dt = date.fromisoformat(self.date_to)
        except ValueError as e:
            raise ValueError("date_from/date_to ISO date olmalı (YYYY-MM-DD)") from e
        if dt < df:
            raise ValueError("date_to, date_from'dan küçük olamaz")
        return self


class HurdleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    date_from: str | None = None
    date_to: str | None = None
    room_type: str | None = None
    channel: str | None = None
    min_rate: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    note: str | None = None


def _specificity(h: dict) -> int:
    """Daha spesifik = daha yüksek skor."""
    s = 0
    if h.get("room_type"):
        s += 2
    if h.get("channel"):
        s += 1
    return s


# ---------- CRUD ----------


@router.get("/", response_model=list[HurdleRate])
async def list_hurdles(
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    cur = db.hurdle_rates.find({"tenant_id": user.tenant_id, "active": True}).sort([("date_from", 1), ("name", 1)])
    out: list[dict[str, Any]] = []
    async for d in cur:
        d.pop("_id", None)
        out.append(d)
    return out


@router.post("/", response_model=HurdleRate, status_code=201)
async def create_hurdle(
    payload: HurdleRate,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    await _ensure_indexes(db)
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["currency"] = doc["currency"].upper()
    doc["created_by"] = user.email
    doc["created_at"] = datetime.now(UTC).isoformat()
    await db.hurdle_rates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/{hurdle_id}", response_model=HurdleRate)
async def update_hurdle(
    hurdle_id: str,
    payload: HurdleUpdate,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "Güncellenecek alan yok")

    # Tarih güncellemesi varsa doğrula
    if "date_from" in changes or "date_to" in changes:
        existing = await db.hurdle_rates.find_one(
            {
                "id": hurdle_id,
                "tenant_id": user.tenant_id,
                "active": True,
            }
        )
        if not existing:
            raise HTTPException(404, "Hurdle bulunamadı")
        df = changes.get("date_from", existing["date_from"])
        dt = changes.get("date_to", existing["date_to"])
        try:
            d_f = date.fromisoformat(df)
            d_t = date.fromisoformat(dt)
        except ValueError as e:
            raise HTTPException(400, "date_from/date_to ISO date olmalı") from e
        if d_t < d_f:
            raise HTTPException(400, "date_to, date_from'dan küçük olamaz")

    if "currency" in changes and changes["currency"]:
        changes["currency"] = changes["currency"].upper()
    changes["updated_by"] = user.email
    changes["updated_at"] = datetime.now(UTC).isoformat()

    res = await db.hurdle_rates.update_one(
        {"id": hurdle_id, "tenant_id": user.tenant_id, "active": True},
        {"$set": changes},
    )
    if not res.matched_count:
        raise HTTPException(404, "Hurdle bulunamadı")
    doc = await db.hurdle_rates.find_one({"id": hurdle_id, "tenant_id": user.tenant_id})
    doc.pop("_id", None)
    return doc


@router.delete("/{hurdle_id}", status_code=204)
async def delete_hurdle(
    hurdle_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    db = get_system_db()
    res = await db.hurdle_rates.update_one(
        {"id": hurdle_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False, "deleted_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Hurdle bulunamadı")


# ---------- Check ----------


@router.get("/check")
async def check_rate(
    target_date: str = Query(..., alias="date", description="ISO date"),
    proposed_rate: float = Query(..., ge=0),
    room_type: str | None = None,
    channel: str | None = None,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    """Verilen tarih+oda+kanal için en spesifik aktif hurdle'ı bulur,
    proposed_rate hurdle'a uyup uymadığını döner."""
    try:
        date.fromisoformat(target_date)
    except ValueError as e:
        raise HTTPException(400, "date ISO format olmalı (YYYY-MM-DD)") from e

    db = get_system_db()
    q: dict[str, Any] = {
        "tenant_id": user.tenant_id,
        "active": True,
        "date_from": {"$lte": target_date},
        "date_to": {"$gte": target_date},
    }
    candidates: list[dict[str, Any]] = []
    async for d in db.hurdle_rates.find(q):
        # room_type filtresi: hurdle.room_type None → wildcard, eşleşen veya wildcard
        if d.get("room_type") and room_type and d["room_type"] != room_type:
            continue
        if d.get("room_type") and not room_type:
            # room_type belirli ama check'te oda yok → atla (specifik kuralı garanti edemeyiz)
            continue
        if d.get("channel") and channel and d["channel"] != channel:
            continue
        if d.get("channel") and not channel:
            continue
        d.pop("_id", None)
        candidates.append(d)

    if not candidates:
        return {
            "date": target_date,
            "proposed_rate": proposed_rate,
            "applied_hurdle": None,
            "allowed": True,
            "reason": "Bu tarih/oda/kanal için aktif hurdle yok",
        }

    # En spesifik + en yüksek min_rate'i seç (specificity tie-breaker olarak)
    best = max(candidates, key=lambda h: (_specificity(h), float(h.get("min_rate", 0))))
    allowed = float(proposed_rate) >= float(best["min_rate"])
    return {
        "date": target_date,
        "room_type": room_type,
        "channel": channel,
        "proposed_rate": proposed_rate,
        "applied_hurdle": {
            "id": best["id"],
            "name": best["name"],
            "min_rate": best["min_rate"],
            "currency": best["currency"],
            "room_type": best.get("room_type"),
            "channel": best.get("channel"),
            "specificity": _specificity(best),
        },
        "allowed": allowed,
        "reason": "OK" if allowed else f"Teklif {proposed_rate} < hurdle {best['min_rate']} {best['currency']}",
    }
