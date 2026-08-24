"""Internal cross-property price directives.

This router never writes to an OTA/provider. It records an approved Syroce
rate directive and its immutable history for the properties in the user's
chain. Provider distribution remains an explicit, separate workflow.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from core.audit import log_audit_event
from core.security import get_current_user
from core.tenant_db import get_system_db
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/central-pricing", tags=["Central Pricing"])
system_db = get_system_db()


class BulkRateUpdate(BaseModel):
    room_type: str = Field(min_length=1, max_length=160)
    new_rate: Decimal = Field(ge=Decimal("-10000000"), le=Decimal("10000000"))
    adjustment_type: Literal["fixed", "percentage", "increment"] = "fixed"
    effective_from: date
    currency: str = Field(default="TRY", min_length=3, max_length=3)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("room_type", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Alan boş olamaz")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_adjustment(self):
        if self.adjustment_type == "fixed" and self.new_rate < 0:
            raise ValueError("Sabit fiyat negatif olamaz")
        return self


class RateTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    rates: dict[str, Decimal] = Field(min_length=1, max_length=100)
    currency: str = Field(default="TRY", min_length=3, max_length=3)

    @field_validator("rates")
    @classmethod
    def validate_rates(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(not key.strip() or amount < 0 or amount > Decimal("10000000") for key, amount in value.items()):
            raise ValueError("Oda tipi ve fiyat değerleri geçerli olmalıdır")
        return {key.strip(): amount for key, amount in value.items()}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _actor_id(current_user) -> str:
    return str(getattr(current_user, "id", None) or getattr(current_user, "email", None) or "unknown")


def _money(value) -> float:
    try:
        return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0.0


async def _chain_context(current_user) -> tuple[str, list[dict]]:
    tenant_id = current_user.tenant_id
    own = await system_db.tenants.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {"_id": 0, "chain_id": 1, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1, "is_chain_headquarters": 1},
    )
    chain_id = (own or {}).get("chain_id") or tenant_id
    if (own or {}).get("chain_id"):
        role = getattr(getattr(current_user, "role", None), "value", getattr(current_user, "role", None))
        is_hq = bool(getattr(current_user, "is_chain_headquarters", False) or (own or {}).get("is_chain_headquarters"))
        if role != "super_admin" and not is_hq:
            raise HTTPException(403, "Zincir fiyat yönetimi yalnız merkez tesis kullanıcılarına açıktır")
        tenants = await system_db.tenants.find(
            {"chain_id": chain_id},
            {"_id": 0, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1},
        ).to_list(500)
    else:
        tenants = [own or {"tenant_id": tenant_id, "name": tenant_id}]
    properties = [
        {
            "tenant_id": row.get("tenant_id") or row.get("id"),
            "property_name": row.get("hotel_name") or row.get("name") or row.get("tenant_id") or row.get("id"),
        }
        for row in tenants
        if row.get("tenant_id") or row.get("id")
    ]
    return chain_id, properties


async def _property_room_rates(chain_id: str, property_doc: dict) -> dict:
    tenant_id = property_doc["tenant_id"]
    rooms = await system_db.rooms.find(
        {"tenant_id": tenant_id, "is_active": {"$ne": False}},
        {"_id": 0, "room_type": 1, "type": 1, "base_price": 1, "base_rate": 1},
    ).to_list(20000)
    grouped: dict[str, dict] = defaultdict(lambda: {"count": 0, "rates": []})
    for room in rooms:
        room_type = str(room.get("room_type") or room.get("type") or "Standard")
        grouped[room_type]["count"] += 1
        candidate = room.get("base_price", room.get("base_rate"))
        if candidate is not None:
            grouped[room_type]["rates"].append(_money(candidate))

    directives = await system_db.central_pricing_rates.find(
        {"chain_id": chain_id, "tenant_id": tenant_id},
        {"_id": 0},
    ).to_list(500)
    directive_by_type = {row["room_type"]: row for row in directives}
    all_room_types = sorted(set(grouped) | set(directive_by_type))
    room_rates = []
    for room_type in all_room_types:
        room_group = grouped.get(room_type, {"count": 0, "rates": []})
        directive = directive_by_type.get(room_type, {})
        base_rate = directive.get("current_rate")
        if base_rate is None:
            rates = room_group["rates"]
            base_rate = _money(sum(rates) / len(rates)) if rates else 0.0
        room_rates.append(
            {
                "room_type": room_type,
                "base_rate": _money(base_rate),
                "count": room_group["count"],
                "currency": directive.get("currency", "TRY"),
                "effective_from": directive.get("effective_from"),
                "provider_sync_status": directive.get("provider_sync_status", "not_requested"),
            }
        )
    return {**property_doc, "room_rates": room_rates}


@router.get("/rates")
async def get_central_rates(current_user=Depends(get_current_user)):
    chain_id, properties = await _chain_context(current_user)
    rows = [await _property_room_rates(chain_id, property_doc) for property_doc in properties]
    return {"chain_id": chain_id, "properties": rows, "total": len(rows), "provider_write": False}


@router.post("/bulk-update")
async def bulk_update_rates(
    body: BulkRateUpdate,
    current_user=Depends(get_current_user),
    _permission=Depends(require_op("manage_pricing")),
):
    chain_id, properties = await _chain_context(current_user)
    now = _now()
    batch_id = str(uuid.uuid4())
    history = []
    for property_doc in properties:
        tenant_id = property_doc["tenant_id"]
        query = {"chain_id": chain_id, "tenant_id": tenant_id, "room_type": body.room_type}
        existing = await system_db.central_pricing_rates.find_one(query, {"_id": 0})
        if existing and existing.get("current_rate") is not None:
            old_rate = Decimal(str(existing["current_rate"]))
        else:
            rooms = await system_db.rooms.find(
                {"tenant_id": tenant_id, "$or": [{"room_type": body.room_type}, {"type": body.room_type}]},
                {"_id": 0, "base_price": 1, "base_rate": 1},
            ).to_list(20000)
            values = [Decimal(str(row.get("base_price", row.get("base_rate")))) for row in rooms if row.get("base_price", row.get("base_rate")) is not None]
            old_rate = (sum(values) / len(values)) if values else Decimal("0")
        if body.adjustment_type == "fixed":
            final_rate = body.new_rate
        elif body.adjustment_type == "percentage":
            final_rate = old_rate * (Decimal("1") + body.new_rate / Decimal("100"))
        else:
            final_rate = old_rate + body.new_rate
        if final_rate < 0:
            raise HTTPException(status_code=422, detail=f"{property_doc['property_name']} için hesaplanan fiyat negatif olamaz")
        final_rate = Decimal(str(_money(final_rate)))
        directive = {
            **query,
            "property_name": property_doc["property_name"],
            "current_rate": float(final_rate),
            "currency": body.currency,
            "effective_from": body.effective_from.isoformat(),
            "reason": body.reason,
            "provider_sync_status": "not_requested",
            "updated_at": now,
            "updated_by": _actor_id(current_user),
            "batch_id": batch_id,
        }
        await system_db.central_pricing_rates.update_one(
            query,
            {"$set": directive, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
            upsert=True,
        )
        event = {
            "id": str(uuid.uuid4()),
            "batch_id": batch_id,
            "chain_id": chain_id,
            "tenant_id": tenant_id,
            "property_name": property_doc["property_name"],
            "room_type": body.room_type,
            "old_rate": _money(old_rate),
            "new_rate": float(final_rate),
            "adjustment_type": body.adjustment_type,
            "adjustment_value": float(body.new_rate),
            "currency": body.currency,
            "effective_from": body.effective_from.isoformat(),
            "reason": body.reason,
            "provider_write": False,
            "updated_at": now,
            "updated_by": _actor_id(current_user),
        }
        await system_db.central_pricing_history.insert_one(event.copy())
        history.append(event)

    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=_actor_id(current_user),
        action="central_pricing.bulk_updated",
        entity_type="central_pricing_batch",
        entity_id=batch_id,
        details=f"{body.room_type} için {len(history)} tesiste merkezi fiyat kararı kaydedildi",
        after_value={"request": body.model_dump(mode="json"), "results": history},
        db=system_db,
        severity="warning",
    )
    return {
        "batch_id": batch_id,
        "total_updated": len(history),
        "updates": history,
        "provider_write": False,
        "message": "Fiyat kararı Syroce içinde kaydedildi; OTA/sağlayıcıya gönderilmedi.",
    }


@router.get("/rate-history")
async def get_rate_history(current_user=Depends(get_current_user)):
    chain_id, _ = await _chain_context(current_user)
    history = await system_db.central_pricing_history.find(
        {"chain_id": chain_id},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(1000)
    return {"history": history, "total": len(history)}


@router.get("/rate-templates")
async def get_rate_templates(current_user=Depends(get_current_user)):
    chain_id, _ = await _chain_context(current_user)
    templates = await system_db.central_pricing_templates.find(
        {"chain_id": chain_id, "is_active": {"$ne": False}},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(500)
    return {"templates": templates, "total": len(templates)}


@router.post("/rate-templates", status_code=201)
async def create_rate_template(
    body: RateTemplateCreate,
    current_user=Depends(get_current_user),
    _permission=Depends(require_op("manage_pricing")),
):
    chain_id, _ = await _chain_context(current_user)
    now = _now()
    template = {
        "id": str(uuid.uuid4()),
        "chain_id": chain_id,
        "tenant_id": current_user.tenant_id,
        "name": body.name.strip(),
        "description": body.description.strip(),
        "rates": {key: float(value) for key, value in body.rates.items()},
        "currency": body.currency.upper(),
        "is_active": True,
        "created_at": now,
        "created_by": _actor_id(current_user),
        "updated_at": now,
        "updated_by": _actor_id(current_user),
    }
    await system_db.central_pricing_templates.insert_one(template.copy())
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=_actor_id(current_user),
        action="central_pricing.template.created",
        entity_type="central_pricing_template",
        entity_id=template["id"],
        details=f"Merkezi fiyat şablonu oluşturuldu: {template['name']}",
        after_value=template,
        db=system_db,
    )
    return {key: value for key, value in template.items() if key not in {"chain_id", "tenant_id"}}
