"""Measured, capacity-checked banquet table layouts (not a fire-safety plan)."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.entitlements.enforcement import require_feature
from core.security import get_current_user
from core.spa_mice_authz import require_mice_ops
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(dependencies=[Depends(require_feature("mice", "banquet_operations"))])


class TableIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=50)
    seats: int = Field(ge=1, le=100)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)


class SeatingIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    booking_index: int = Field(ge=0)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)
    tables: list[TableIn] = Field(min_length=1, max_length=100)
    expected_revision: str


def validate_layout(body, pax, capacity):
    if len({t.label.casefold() for t in body.tables}) != len(body.tables):
        raise HTTPException(422, "Masa adları benzersiz olmalıdır")
    seats = sum(t.seats for t in body.tables)
    if seats < pax or not capacity or seats > capacity:
        raise HTTPException(409, "Koltuk sayısı beklenen kişiden az veya salon düzen kapasitesinden fazla olamaz")
    for i, table in enumerate(body.tables):
        if table.x + table.width > body.width or table.y + table.height > body.height:
            raise HTTPException(422, "Masa ölçüleri salon sınırlarını aşıyor")
        for other in body.tables[i + 1:]:
            if table.x < other.x + other.width and other.x < table.x + table.width and table.y < other.y + other.height and other.y < table.y + table.height:
                raise HTTPException(409, "Masa alanları üst üste gelemez")


@router.get("/events/{event_id}/seating-plans")
async def seating_plans(event_id: str, current_user: User = Depends(get_current_user)):
    db, tid = get_system_db(), current_user.tenant_id
    event = await db.mice_events.find_one({"tenant_id": tid, "id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    spaces = {s["id"]: s.get("name") for s in await db.mice_spaces.find({"tenant_id": tid}, {"_id": 0, "id": 1, "name": 1}).to_list(None)}
    return {"bookings": [{**b, "space_name": spaces.get(b["space_id"], b["space_id"])} for b in event.get("space_bookings") or []],
            "plans": event.get("seating_plans") or [], "expected_revision": event.get("updated_at") or event.get("created_at"),
            "notice": "Ölçüler metredir. Bu operasyon çizimi kaçış yolu, erişilebilirlik veya yangın güvenliği onayı yerine geçmez; tesis yetkilisi kontrol etmelidir."}


@router.put("/events/{event_id}/seating-plan")
async def save_seating_plan(event_id: str, body: SeatingIn, current_user: User = Depends(get_current_user), _perm=Depends(require_op("manage_sales"))):
    require_mice_ops(current_user)
    db, tid = get_system_db(), current_user.tenant_id
    event = await db.mice_events.find_one({"tenant_id": tid, "id": event_id}, {"_id": 0})
    if not event or body.booking_index >= len(event.get("space_bookings") or []):
        raise HTTPException(404, "Etkinlik salon satırı bulunamadı")
    if event.get("signature") or event.get("status") in {"cancelled", "completed"} or event.get("finance_pending"):
        raise HTTPException(409, "Kapanmış/onaylı etkinlik için önce uygun revizyon akışını kullanın")
    if body.expected_revision != (event.get("updated_at") or event.get("created_at")):
        raise HTTPException(409, "Etkinlik değişti; yerleşimi yenileyin")
    booking = event["space_bookings"][body.booking_index]
    space = await db.mice_spaces.find_one({"tenant_id": tid, "id": booking["space_id"], "active": {"$ne": False}})
    capacity = int((space or {}).get(f"capacity_{booking.get('setup_style') or 'theatre'}") or 0)
    validate_layout(body, int(booking.get("expected_pax") or event.get("expected_pax") or 0), capacity)
    now = datetime.now(UTC).isoformat()
    plan = {**body.model_dump(exclude={"expected_revision"}), "space_id": booking["space_id"], "starts_at": booking["starts_at"], "ends_at": booking["ends_at"], "recorded_at": now, "recorded_by": current_user.username}
    plans = [p for p in event.get("seating_plans") or [] if p["booking_index"] != body.booking_index]
    result = await db.mice_events.update_one({"tenant_id": tid, "id": event_id, "updated_at": event.get("updated_at"), "signature": None}, {"$set": {"seating_plans": [*plans, plan], "updated_at": now}})
    if result.matched_count != 1:
        raise HTTPException(409, "Etkinlik değişti; yerleşim kaydedilmedi")
    return {"plan": plan}
