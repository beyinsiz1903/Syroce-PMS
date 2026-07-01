"""Opera #12 — Profile UDF (User-Defined Fields).
Misafir profillerinde tenant'a özel custom alanlar: tanım yönetimi + guest
profile'larına değer yazma/okuma.

Backend zaten esnek (guests dict), bu router yapılandırılmış UI desteği sağlar.
Yetki: manage_guests (definitions CRUD + value write).

PUT davranışı: MERGE (partial update). Payload'taki anahtarlar yazılır;
gönderilmeyen mevcut anahtarlar korunur. Bir anahtarı silmek için açıkça
null gönderin.
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

router = APIRouter(prefix="/api/profile-udf", tags=["Profile UDF"])

FIELD_TYPES = ("text", "number", "date", "select", "boolean", "multiselect")
_INDEX_INIT = False


async def _ensure_indexes(db) -> None:
    """Race koşullarında duplicate key engeli için partial unique index."""
    global _INDEX_INIT
    if _INDEX_INIT:
        return
    try:
        await db.profile_udf_defs.create_index(
            [("tenant_id", 1), ("key", 1)],
            unique=True,
            partialFilterExpression={"active": True},
            name="udf_def_unique_active_key",
        )
        _INDEX_INIT = True
    except Exception as e:  # noqa: BLE001
        logger.warning("UDF index oluşturulamadı: %s", e)


class UdfDefinition(BaseModel):
    id: str | None = None
    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=120)
    type: str = Field("text")
    required: bool = False
    options: list[str] = Field(default_factory=list)
    help_text: str | None = None
    section: str | None = None
    order: int = 100
    active: bool = True


class UdfValuesPayload(BaseModel):
    values: dict[str, Any]


# ---------- Definitions ----------


@router.get("/definitions", response_model=list[UdfDefinition])
async def list_definitions(user: User = Depends(get_current_user)):
    """Tüm authenticated kullanıcılar tanımları okuyabilir (form render için)."""
    db = get_system_db()
    cur = db.profile_udf_defs.find({"tenant_id": user.tenant_id, "active": True}).sort([("section", 1), ("order", 1), ("label", 1)])
    out: list[dict[str, Any]] = []
    async for d in cur:
        d.pop("_id", None)
        out.append(d)
    return out


@router.post("/definitions", response_model=UdfDefinition, status_code=201)
async def create_definition(
    payload: UdfDefinition,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_guests")),
):
    if payload.type not in FIELD_TYPES:
        raise HTTPException(400, f"Geçersiz tip. Seçenekler: {', '.join(FIELD_TYPES)}")
    if payload.type in ("select", "multiselect") and not payload.options:
        raise HTTPException(400, "select/multiselect için en az bir seçenek gerekli")

    db = get_system_db()
    await _ensure_indexes(db)

    existing = await db.profile_udf_defs.find_one(
        {
            "tenant_id": user.tenant_id,
            "key": payload.key,
            "active": True,
        }
    )
    if existing:
        raise HTTPException(409, f"Bu anahtar zaten kullanımda: {payload.key}")

    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["created_by"] = user.email
    doc["created_at"] = datetime.now(UTC).isoformat()
    try:
        await db.profile_udf_defs.insert_one(doc)
    except Exception as e:  # noqa: BLE001
        # Race: partial unique index 11000 → 409
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(409, f"Bu anahtar zaten kullanımda: {payload.key}") from e
        raise
    doc.pop("_id", None)
    return doc


@router.delete("/definitions/{def_id}", status_code=204)
async def delete_definition(
    def_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_guests")),
):
    db = get_system_db()
    res = await db.profile_udf_defs.update_one(
        {"id": def_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False, "deleted_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Tanım bulunamadı")


# ---------- Values on guest profiles ----------


@router.get("/guests/{guest_id}")
async def get_guest_udf_values(guest_id: str, user: User = Depends(get_current_user)):
    db = get_system_db()
    guest = await db.guests.find_one(
        {
            "$or": [{"id": guest_id}, {"_id": guest_id}],
            "tenant_id": user.tenant_id,
        }
    )
    if not guest:
        raise HTTPException(404, "Misafir bulunamadı")
    values = guest.get("custom_fields", {}) or {}

    defs = []
    async for d in db.profile_udf_defs.find({"tenant_id": user.tenant_id, "active": True}).sort([("section", 1), ("order", 1)]):
        d.pop("_id", None)
        defs.append(d)

    return {
        "guest_id": guest_id,
        "guest_name": guest.get("full_name") or guest.get("name") or guest.get("email"),
        "definitions": defs,
        "values": values,
    }


def _coerce_value(v: Any, d: dict) -> Any:
    """Tip dönüşümü ve doğrulama. None/boş string → None döner."""
    if v is None or v == "":
        return None
    t = d["type"]
    if t == "number":
        try:
            return float(v)
        except (ValueError, TypeError) as e:
            raise HTTPException(400, f"'{d['key']}' alanı sayı olmalı") from e
    if t == "boolean":
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes", "evet")
    if t == "date":
        # ISO date (YYYY-MM-DD veya YYYY-MM-DDTHH:MM…)
        try:
            datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return str(v)
        except ValueError as e:
            raise HTTPException(400, f"'{d['key']}' alanı geçerli ISO tarih olmalı (YYYY-MM-DD)") from e
    if t == "select":
        if d.get("options") and v not in d["options"]:
            raise HTTPException(400, f"'{d['key']}' için geçersiz seçenek: {v}")
        return v
    if t == "multiselect":
        vals = v if isinstance(v, list) else [v]
        if d.get("options"):
            bad = [x for x in vals if x not in d["options"]]
            if bad:
                raise HTTPException(400, f"'{d['key']}' için geçersiz seçenekler: {bad}")
        return vals
    return str(v)


@router.put("/guests/{guest_id}")
async def set_guest_udf_values(
    guest_id: str,
    payload: UdfValuesPayload,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_guests")),
):
    """MERGE davranışı: payload'taki anahtarlar mevcut custom_fields üzerine yazılır,
    gönderilmeyenler korunur. Bir anahtarı silmek için açıkça null gönderin."""
    db = get_system_db()
    guest = await db.guests.find_one(
        {
            "$or": [{"id": guest_id}, {"_id": guest_id}],
            "tenant_id": user.tenant_id,
        }
    )
    if not guest:
        raise HTTPException(404, "Misafir bulunamadı")

    defs: list[dict[str, Any]] = []
    async for d in db.profile_udf_defs.find({"tenant_id": user.tenant_id, "active": True}):
        d.pop("_id", None)
        defs.append(d)
    by_key = {d["key"]: d for d in defs}

    # Mevcut değerleri al, payload ile MERGE et
    merged = dict(guest.get("custom_fields", {}) or {})
    for k, v in (payload.values or {}).items():
        d = by_key.get(k)
        if not d:
            continue  # tanımsız anahtarları sessizce at
        merged[k] = _coerce_value(v, d)

    # Required kontrolü (None/"" sayılır; False/0 geçerlidir)
    missing = []
    for d in defs:
        if not d.get("required"):
            continue
        val = merged.get(d["key"])
        if val is None or val == "" or (isinstance(val, list) and not val):
            missing.append(d["key"])
    if missing:
        raise HTTPException(400, f"Zorunlu alanlar boş: {', '.join(missing)}")

    await db.guests.update_one(
        {"$or": [{"id": guest_id}, {"_id": guest_id}], "tenant_id": user.tenant_id},
        {
            "$set": {
                "custom_fields": merged,
                "custom_fields_updated_at": datetime.now(UTC).isoformat(),
                "custom_fields_updated_by": user.email,
            }
        },
    )
    return {"ok": True, "values": merged}
