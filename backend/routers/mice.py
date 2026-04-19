"""MICE — Meetings, Incentives, Conferences & Events / Banquet.

Mirrors the Opera/Protel banquet management spine:
* Function spaces (rooms/halls) with capacities per setup style
* Events with proper sales lifecycle (lead → tentative → definite →
  confirmed → cancelled / completed) and conflict-checked space holds
* Resource lines (F&B menus, AV equipment, decor) per event
* Auto-computed quote totals
* Function diary (calendar)
* BEO (Banquet Event Order) summary endpoint
* Charge-to-master integration emitting Xchange POSTING_CHARGE
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User

router = APIRouter(prefix="/api/mice", tags=["mice"])

# ── Function spaces ──────────────────────────────────────────────
class FunctionSpaceIn(BaseModel):
    name: str
    location: str | None = None  # floor / wing
    area_m2: float = Field(0, ge=0)
    capacity_theatre: int = Field(0, ge=0)
    capacity_classroom: int = Field(0, ge=0)
    capacity_banquet: int = Field(0, ge=0)
    capacity_cocktail: int = Field(0, ge=0)
    capacity_u_shape: int = Field(0, ge=0)
    capacity_boardroom: int = Field(0, ge=0)
    hourly_rate: float = Field(0, ge=0)
    daily_rate: float = Field(0, ge=0)
    currency: str = "TRY"
    amenities: list[str] = Field(default_factory=list)  # ["projector","stage",...]
    active: bool = True


@router.get("/spaces")
async def list_spaces(current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    cur = db.mice_spaces.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("name", 1)
    items = [doc async for doc in cur]
    if not items:
        items = await _seed_spaces(current_user.tenant_id)
    return {"spaces": items}


async def _seed_spaces(tenant_id: str) -> list[dict]:
    db = get_system_db()
    seeds = [
        ("Grand Balo Salonu", "Bodrum kat", 480, 500, 280, 320, 450, 0, 0, 8000, 35000),
        ("Bosphorus Toplantı Salonu", "1. kat", 120, 120, 70, 80, 100, 50, 40, 2500, 12000),
        ("Boardroom", "1. kat", 35, 0, 0, 0, 0, 0, 14, 1500, 6000),
        ("Teras Etkinlik Alanı", "Çatı", 220, 0, 0, 150, 250, 0, 0, 3500, 18000),
    ]
    docs = []
    for s in seeds:
        n, loc, area, th, cl, bq, ck, us, br, hr, dr = s
        docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": n, "location": loc, "area_m2": area,
            "capacity_theatre": th, "capacity_classroom": cl,
            "capacity_banquet": bq, "capacity_cocktail": ck,
            "capacity_u_shape": us, "capacity_boardroom": br,
            "hourly_rate": hr, "daily_rate": dr, "currency": "TRY",
            "amenities": ["wifi", "projector", "ses-sistemi"],
            "active": True,
            "created_at": datetime.now(UTC).isoformat(),
        })
    await db.mice_spaces.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/spaces")
async def create_space(body: FunctionSpaceIn,
                       current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    doc = {"id": str(uuid.uuid4()),
           "tenant_id": current_user.tenant_id,
           **body.model_dump(),
           "created_at": datetime.now(UTC).isoformat()}
    await db.mice_spaces.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/spaces/{space_id}")
async def update_space(space_id: str, body: FunctionSpaceIn,
                       current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    res = await db.mice_spaces.update_one(
        {"id": space_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()},
    )
    if not res.matched_count:
        raise HTTPException(404, "Mekan bulunamadı")
    return {"ok": True}


@router.delete("/spaces/{space_id}")
async def delete_space(space_id: str,
                       current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    await db.mice_spaces.delete_one(
        {"id": space_id, "tenant_id": current_user.tenant_id})
    return {"ok": True}


# ── Catalog: F&B menus and AV/decor packages ────────────────────
class MenuPackageIn(BaseModel):
    name: str
    type: str = "fb"  # fb / av / decor
    price_per_person: float = Field(0, ge=0)
    flat_price: float = Field(0, ge=0)
    currency: str = "TRY"
    description: str | None = None
    active: bool = True


@router.get("/menus")
async def list_menus(current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    cur = db.mice_menus.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("type", 1)
    items = [doc async for doc in cur]
    if not items:
        items = await _seed_menus(current_user.tenant_id)
    return {"menus": items}


async def _seed_menus(tenant_id: str) -> list[dict]:
    db = get_system_db()
    seeds = [
        ("Coffee Break (Standart)", "fb", 250, 0),
        ("Açık Büfe Öğle Yemeği", "fb", 950, 0),
        ("Gala Akşam Yemeği (4 Kap)", "fb", 1850, 0),
        ("AV Paketi (projeksiyon+ses)", "av", 0, 4500),
        ("Çiçek & Sahne Dekorasyonu", "decor", 0, 12000),
    ]
    docs = []
    for n, t, pp, fp in seeds:
        docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": n, "type": t,
            "price_per_person": pp, "flat_price": fp,
            "currency": "TRY", "description": None, "active": True,
            "created_at": datetime.now(UTC).isoformat(),
        })
    await db.mice_menus.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/menus")
async def create_menu(body: MenuPackageIn,
                      current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    doc = {"id": str(uuid.uuid4()),
           "tenant_id": current_user.tenant_id,
           **body.model_dump(),
           "created_at": datetime.now(UTC).isoformat()}
    await db.mice_menus.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/menus/{menu_id}")
async def update_menu(menu_id: str, body: MenuPackageIn,
                      current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    res = await db.mice_menus.update_one(
        {"id": menu_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()},
    )
    if not res.matched_count:
        raise HTTPException(404, "Menü bulunamadı")
    return {"ok": True}


@router.delete("/menus/{menu_id}")
async def delete_menu(menu_id: str,
                      current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    await db.mice_menus.delete_one(
        {"id": menu_id, "tenant_id": current_user.tenant_id})
    return {"ok": True}


# ── Events ──────────────────────────────────────────────────────
EVENT_STATUSES = {"lead", "tentative", "definite",
                  "confirmed", "completed", "cancelled"}


class SpaceBookingIn(BaseModel):
    space_id: str
    starts_at: datetime
    ends_at: datetime
    setup_style: str = "theatre"  # theatre/classroom/banquet/cocktail/u_shape/boardroom
    expected_pax: int = Field(0, ge=0)


class ResourceLineIn(BaseModel):
    menu_id: str | None = None
    name: str
    type: str = "fb"  # fb / av / decor / other
    quantity: float = 1
    unit: str = "pax"  # pax / unit / hour
    unit_price: float = 0
    notes: str | None = None


class EventIn(BaseModel):
    name: str
    client_name: str
    client_email: str | None = None
    client_phone: str | None = None
    organizer_user: str | None = None  # sales rep
    event_type: str = "meeting"  # meeting/conference/wedding/gala/training/other
    status: str = "lead"
    expected_pax: int = Field(0, ge=0)
    start_date: date
    end_date: date
    space_bookings: list[SpaceBookingIn] = Field(default_factory=list)
    resources: list[ResourceLineIn] = Field(default_factory=list)
    notes: str | None = None
    reservation_id: str | None = None  # link to room block / master folio


def _line_total(r: dict) -> float:
    return float(r.get("unit_price", 0)) * float(r.get("quantity", 1))


def _compute_totals(event: dict, spaces_by_id: dict[str, dict]) -> dict:
    space_total = 0.0
    for sb in event.get("space_bookings", []):
        sp = spaces_by_id.get(sb["space_id"])
        if not sp:
            continue
        # Use daily_rate when ≥6h, hourly_rate otherwise
        s = datetime.fromisoformat(sb["starts_at"])
        e = datetime.fromisoformat(sb["ends_at"])
        hours = max(1.0, (e - s).total_seconds() / 3600.0)
        space_total += sp["daily_rate"] if hours >= 6 else sp["hourly_rate"] * hours
    resources_total = sum(_line_total(r) for r in event.get("resources", []))
    return {
        "space_total": round(space_total, 2),
        "resources_total": round(resources_total, 2),
        "grand_total": round(space_total + resources_total, 2),
    }


async def _check_space_conflict(tenant_id: str, bookings: list[dict],
                                exclude_event_id: str | None = None) -> str | None:
    db = get_system_db()
    for sb in bookings:
        s_iso = sb["starts_at"] if isinstance(sb["starts_at"], str) else sb["starts_at"].isoformat()
        e_iso = sb["ends_at"] if isinstance(sb["ends_at"], str) else sb["ends_at"].isoformat()
        q = {
            "tenant_id": tenant_id,
            "status": {"$in": ["tentative", "definite", "confirmed"]},
            "space_bookings.space_id": sb["space_id"],
        }
        if exclude_event_id:
            q["id"] = {"$ne": exclude_event_id}
        async for ev in db.mice_events.find(q):
            for other in ev.get("space_bookings", []):
                if other.get("space_id") != sb["space_id"]:
                    continue
                if other["starts_at"] < e_iso and s_iso < other["ends_at"]:
                    return f"Mekan çakışması: {ev.get('name')} ({other['starts_at'][:16]})"
    return None


@router.get("/events")
async def list_events(
    status: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if status:
        q["status"] = status
    if date_from:
        q["end_date"] = {"$gte": date_from}
    if date_to:
        q.setdefault("start_date", {})["$lte"] = date_to
    cur = db.mice_events.find(q, {"_id": 0}).sort("start_date", 1).limit(500)
    items = [d async for d in cur]
    # Aggregate quick stats
    pipe = [
        {"$match": {"tenant_id": current_user.tenant_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1},
                    "total": {"$sum": "$totals.grand_total"}}},
    ]
    summary: dict[str, dict] = {}
    async for r in db.mice_events.aggregate(pipe):
        summary[r["_id"]] = {"count": r["n"],
                             "total_value": round(r.get("total", 0) or 0, 2)}
    return {"events": items, "summary": summary}


async def _expand_resource_prices(tenant_id: str, resources: list[dict],
                                  pax: int) -> list[dict]:
    db = get_system_db()
    out = []
    for r in resources:
        line = dict(r)
        if r.get("menu_id"):
            menu = await db.mice_menus.find_one(
                {"id": r["menu_id"], "tenant_id": tenant_id})
            if menu:
                if menu.get("price_per_person"):
                    line["unit_price"] = menu["price_per_person"]
                    line["unit"] = "pax"
                    if not line.get("quantity") or line["quantity"] in (0, 1):
                        line["quantity"] = pax
                elif menu.get("flat_price"):
                    line["unit_price"] = menu["flat_price"]
                    line["unit"] = "unit"
                    line["quantity"] = max(1, line.get("quantity", 1))
                line["name"] = line.get("name") or menu["name"]
                line["type"] = menu.get("type", line.get("type", "fb"))
        out.append(line)
    return out


@router.post("/events")
async def create_event(body: EventIn,
                       current_user: User = Depends(get_current_user)) -> dict:
    if body.status not in EVENT_STATUSES:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    tenant_id = current_user.tenant_id

    bookings = [b.model_dump() for b in body.space_bookings]
    for b in bookings:
        b["starts_at"] = b["starts_at"].isoformat() if isinstance(b["starts_at"], datetime) else b["starts_at"]
        b["ends_at"] = b["ends_at"].isoformat() if isinstance(b["ends_at"], datetime) else b["ends_at"]

    if body.status in {"tentative", "definite", "confirmed"}:
        conflict = await _check_space_conflict(tenant_id, bookings)
        if conflict:
            raise HTTPException(409, conflict)

    resources = await _expand_resource_prices(
        tenant_id, [r.model_dump() for r in body.resources], body.expected_pax,
    )

    spaces_by_id = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": tenant_id})}
    event_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        **body.model_dump(exclude={"space_bookings", "resources"}),
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "space_bookings": bookings,
        "resources": resources,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }
    event_doc["totals"] = _compute_totals(event_doc, spaces_by_id)
    await db.mice_events.insert_one(event_doc)
    event_doc.pop("_id", None)
    return event_doc


@router.get("/events/{event_id}")
async def get_event(event_id: str,
                    current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    doc = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Etkinlik bulunamadı")
    return doc


@router.put("/events/{event_id}")
async def update_event(event_id: str, body: EventIn,
                       current_user: User = Depends(get_current_user)) -> dict:
    if body.status not in EVENT_STATUSES:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    tenant_id = current_user.tenant_id
    bookings = [b.model_dump() for b in body.space_bookings]
    for b in bookings:
        b["starts_at"] = b["starts_at"].isoformat() if isinstance(b["starts_at"], datetime) else b["starts_at"]
        b["ends_at"] = b["ends_at"].isoformat() if isinstance(b["ends_at"], datetime) else b["ends_at"]
    if body.status in {"tentative", "definite", "confirmed"}:
        conflict = await _check_space_conflict(tenant_id, bookings, exclude_event_id=event_id)
        if conflict:
            raise HTTPException(409, conflict)
    resources = await _expand_resource_prices(
        tenant_id, [r.model_dump() for r in body.resources], body.expected_pax)
    spaces_by_id = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": tenant_id})}
    update = {
        **body.model_dump(exclude={"space_bookings", "resources"}),
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "space_bookings": bookings,
        "resources": resources,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    update["totals"] = _compute_totals(update, spaces_by_id)
    res = await db.mice_events.update_one(
        {"id": event_id, "tenant_id": tenant_id}, {"$set": update})
    if not res.matched_count:
        raise HTTPException(404, "Etkinlik bulunamadı")
    return {"ok": True, "totals": update["totals"]}


class StatusUpdate(BaseModel):
    status: str


@router.post("/events/{event_id}/status")
async def change_status(event_id: str, body: StatusUpdate,
                        current_user: User = Depends(get_current_user)) -> dict:
    if body.status not in EVENT_STATUSES:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    tenant_id = current_user.tenant_id
    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": tenant_id})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    cur_status = event.get("status", "lead")
    if body.status not in _MICE_TRANSITIONS.get(cur_status, set()):
        raise HTTPException(
            409, f"Geçersiz geçiş: {cur_status} → {body.status}")
    if body.status in {"definite", "confirmed"} and cur_status not in {"definite", "confirmed"}:
        conflict = await _check_space_conflict(
            tenant_id, event.get("space_bookings", []), exclude_event_id=event_id)
        if conflict:
            raise HTTPException(409, conflict)
    update = {"status": body.status,
              "updated_at": datetime.now(UTC).isoformat()}
    if body.status == "completed":
        update["completed_at"] = datetime.now(UTC).isoformat()
        await _post_event_to_folio(tenant_id, event)
    # IMPORTANT: tenant_id in write filter (cross-tenant safety).
    await db.mice_events.update_one(
        {"id": event_id, "tenant_id": tenant_id}, {"$set": update})
    return {"ok": True, "status": body.status}


_MICE_TRANSITIONS: dict[str, set[str]] = {
    "lead": {"tentative", "cancelled"},
    "tentative": {"definite", "cancelled", "lead"},
    "definite": {"confirmed", "tentative", "cancelled"},
    "confirmed": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": {"lead"},  # allow re-opening a cancelled lead
}


async def _post_event_to_folio(tenant_id: str, event: dict) -> None:
    db = get_system_db()
    total = float((event.get("totals") or {}).get("grand_total", 0))
    if total <= 0 or not event.get("reservation_id"):
        return
    posting = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "reservation_id": event["reservation_id"],
        "folio_id": event["reservation_id"],
        "transaction_code": "MICE",
        "description": f"Etkinlik: {event.get('name')}",
        "amount": total,
        "currency": "TRY",
        "posting_type": "CHARGE",
        "posted_at": datetime.now(UTC).isoformat(),
        "source": "mice_module",
        "reference": event["id"],
    }
    await db.folio_postings.insert_one(posting)
    try:
        from integrations.xchange.bus import bus
        from integrations.xchange.schemas import MessageType
        await bus.publish(
            tenant_id=tenant_id,
            message_type=MessageType.POSTING_CHARGE,
            payload={
                "posting_id": posting["id"],
                "reservation_id": posting["reservation_id"],
                "folio_id": posting["folio_id"],
                "posting_type": "CHARGE",
                "transaction_code": "MICE",
                "description": posting["description"],
                "amount": total,
                "currency": "TRY",
                "posted_at": posting["posted_at"],
            },
            message_id=f"mice-{event['id']}",
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("mice").warning(
            "Xchange POSTING_CHARGE publish failed (best-effort): %s", exc)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str,
                       current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    res = await db.mice_events.delete_one(
        {"id": event_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Etkinlik bulunamadı")
    return {"ok": True}


# ── Function diary (calendar feed) ─────────────────────────────
@router.get("/diary")
async def diary(
    date_from: str = Query(...),
    date_to: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    cur = db.mice_events.find({
        "tenant_id": current_user.tenant_id,
        "start_date": {"$lte": date_to},
        "end_date": {"$gte": date_from},
    }, {"_id": 0, "name": 1, "status": 1, "client_name": 1,
        "expected_pax": 1, "start_date": 1, "end_date": 1,
        "space_bookings": 1, "id": 1, "totals": 1})
    return {"events": [d async for d in cur]}


# ── BEO (Banquet Event Order) ──────────────────────────────────
@router.get("/events/{event_id}/beo")
async def beo(event_id: str,
              current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    event = await db.mice_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    spaces_by_id = {s["id"]: s async for s in db.mice_spaces.find(
        {"tenant_id": current_user.tenant_id})}
    space_lines = []
    for sb in event.get("space_bookings", []):
        sp = spaces_by_id.get(sb["space_id"], {})
        space_lines.append({
            "space_name": sp.get("name", "—"),
            "starts_at": sb["starts_at"], "ends_at": sb["ends_at"],
            "setup_style": sb.get("setup_style"),
            "expected_pax": sb.get("expected_pax"),
        })
    return {
        "event": {k: event[k] for k in (
            "id", "name", "client_name", "client_email", "client_phone",
            "organizer_user", "event_type", "status", "expected_pax",
            "start_date", "end_date", "notes", "totals") if k in event},
        "spaces": space_lines,
        "resources": event.get("resources", []),
    }
