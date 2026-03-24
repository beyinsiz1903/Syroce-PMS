"""
Domain Router: Channel Manager

Extracted from legacy_routes.py — CM ARI endpoints + Admin API key management.
"""
import hashlib
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from core.audit import log_audit_event
from core.database import db
from core.security import (
    JWT_ALGORITHM,
    JWT_SECRET,
    security,
)
from models.enums import BookingStatus
from models.schemas import User

try:
    from domains.pms.room_block_models import BlockStatus
except ImportError:
    class BlockStatus:
        ACTIVE = "active"

router = APIRouter(prefix="/api", tags=["channel-manager-domain"])


# ── CM Models ───────────────────────────────────────────────────────

class CMActorType(str, Enum):
    user = "user"
    agency = "agency"
    system = "system"

class CMOrigin(str, Enum):
    ui = "ui"
    api = "api"
    webhook = "webhook"
    system = "system"

class CMScope(str, Enum):
    room = "room"
    booking = "booking"
    rate = "rate"
    availability = "availability"

class CMAction(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"
    confirm = "confirm"
    cancel = "cancel"

class APIKeyModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    prefix: str
    key_hash: str
    actor_type: CMActorType = CMActorType.agency
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: Optional[str] = None
    last_used_at: Optional[str] = None
    scopes: List[str] = ["cm:read", "cm:write"]

class CMRestrictions(BaseModel):
    stop_sell: bool = False
    min_stay: int = 1
    cta: bool = False
    ctd: bool = False
    max_stay: Optional[int] = None

class CMRateInfo(BaseModel):
    amount: Optional[float] = None
    currency: str = "TRY"
    tax_included: bool = True
    source: Optional[str] = None
    rate_plan_id: Optional[str] = None
    board_code: Optional[str] = None

class CMARIDay(BaseModel):
    date: str
    available: int
    sold: int
    restrictions: CMRestrictions
    rate: CMRateInfo

class CMARIRoomType(BaseModel):
    room_type_id: str
    name: str
    days: List[CMARIDay]

class CMARIV2Response(BaseModel):
    hotel_id: str
    currency: str = "TRY"
    date_from: str
    date_to: str
    room_types: List[CMARIRoomType]

class CMARIResponseDay(BaseModel):
    date: str
    room_type: str
    available: int
    sold: int
    stop_sell: bool = False
    rate: Optional[float] = None
    currency: str = "TRY"
    rate_source: Optional[str] = None

class CMARIResponse(BaseModel):
    tenant_id: str
    start_date: str
    end_date: str
    days: List[CMARIResponseDay]


# ── CM Helpers ──────────────────────────────────────────────────────

CM_PARTNER_WEBHOOK_URL = os.environ.get(
    "CM_PARTNER_WEBHOOK_URL", "https://agency.syroce.com/webhooks/cm"
)


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mask_api_key(raw: str) -> str:
    if not raw:
        return ""
    return f"{raw[:6]}...{raw[-4:]}"


def _generate_api_key() -> dict:
    raw = secrets.token_urlsafe(32)
    prefix = raw[:8]
    return {"raw": raw, "prefix": prefix, "hash": _hash_api_key(raw)}


async def cm_push_event(event: dict):
    """Push CM events to partner webhook (best-effort)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(CM_PARTNER_WEBHOOK_URL, json=event)
    except Exception as e:
        print(f"CM webhook push failed: {e}")


def require_cm_api_key(request: Request) -> dict:
    raw = request.headers.get("x-api-key")
    auth = request.headers.get("authorization")
    if not raw and auth and auth.lower().startswith("apikey "):
        raw = auth.split(" ", 1)[1].strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Missing API key")
    key_hash = _hash_api_key(raw)
    return {"raw": raw, "hash": key_hash}


async def get_cm_actor(
    request: Request,
    key_ctx: dict = Depends(require_cm_api_key),
) -> dict:
    api_key = await db.api_keys.find_one(
        {"key_hash": key_ctx["hash"], "is_active": True}, {"_id": 0}
    )
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    await db.api_keys.update_one(
        {"id": api_key["id"]},
        {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {
        "tenant_id": api_key["tenant_id"],
        "actor_type": api_key.get("actor_type", "agency"),
        "actor_id": api_key["id"],
        "origin": CMOrigin.api.value,
        "key_name": api_key.get("name"),
    }


async def _temp_require_super_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user_doc = await db.users.find_one(
            {"$or": [{"id": user_id}, {"user_id": user_id}]}, {"_id": 0}
        )
        if not user_doc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        user = User(**user_doc)
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin required")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


# ── Day-overlap helpers ─────────────────────────────────────────────

def _overlaps_day(check_in_s: str, check_out_s: str, day_s: str) -> bool:
    return check_in_s <= day_s < check_out_s


def _block_overlaps_day(start_s: str, end_s: Optional[str], day_s: str) -> bool:
    if end_s is None:
        return start_s <= day_s
    return start_s <= day_s < end_s


# ── CM ARI Endpoints ────────────────────────────────────────────────

@router.get("/cm/ari", response_model=CMARIResponse)
async def cm_get_ari(
    start_date: str,
    end_date: str,
    room_type: Optional[str] = None,
    operator_id: Optional[str] = None,
    actor: dict = Depends(get_cm_actor),
):
    """Channel Manager ARI endpoint (prod MVP)."""
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except Exception:
        raise HTTPException(status_code=400, detail="start_date/end_date must be YYYY-MM-DD")

    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date start_date'den once olamaz")
    if (ed - sd).days > 366:
        raise HTTPException(status_code=400, detail="Max 366 days range")

    tenant_id = actor["tenant_id"]

    room_query: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
    }
    if room_type:
        room_query["room_type"] = room_type

    rooms = await db.rooms.find(room_query, {"_id": 0, "id": 1, "room_type": 1}).to_list(5000)
    if not rooms:
        return CMARIResponse(tenant_id=tenant_id, start_date=start_date, end_date=end_date, days=[])

    ACTIVE_STATUSES = [
        BookingStatus.CONFIRMED.value,
        BookingStatus.GUARANTEED.value,
        BookingStatus.CHECKED_IN.value,
    ]

    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ACTIVE_STATUSES},
            "check_in": {"$lt": end_date},
            "check_out": {"$gt": start_date},
        },
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    ).to_list(10000)

    blocks = await db.room_blocks.find(
        {
            "tenant_id": tenant_id,
            "status": BlockStatus.ACTIVE if isinstance(BlockStatus.ACTIVE, str) else BlockStatus.ACTIVE.value if hasattr(BlockStatus.ACTIVE, 'value') else "active",
            "start_date": {"$lt": end_date},
            "$or": [{"end_date": None}, {"end_date": {"$gt": start_date}}],
        },
        {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1},
    ).to_list(10000)

    stop_sell = False
    if operator_id:
        ss = await db.stop_sales.find_one(
            {"tenant_id": tenant_id, "operator_id": operator_id, "active": True}, {"_id": 0}
        )
        stop_sell = bool(ss)

    periods = []
    if operator_id:
        room_type_id = room_type or rooms[0].get("room_type")
        periods = await db.rate_periods.find(
            {"tenant_id": tenant_id, "operator_id": operator_id, "room_type_id": room_type_id},
            {"_id": 0},
        ).sort("start_date", 1).to_list(200)

    rate_plans = await db.rate_plans.find(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    ).to_list(200)

    rooms_by_type: Dict[str, List[str]] = {}
    for r in rooms:
        rt = r.get("room_type") or "unknown"
        rooms_by_type.setdefault(rt, []).append(r["id"])

    days: List[CMARIResponseDay] = []
    cur = sd
    while cur <= ed:
        day_s = cur.isoformat()
        for rt, rt_room_ids in rooms_by_type.items():
            if room_type and rt != room_type:
                continue

            sold_ids = set()
            for b in bookings:
                rid = b.get("room_id")
                if rid in rt_room_ids and _overlaps_day(b.get("check_in", ""), b.get("check_out", ""), day_s):
                    sold_ids.add(rid)

            blocked_ids = set()
            for bl in blocks:
                rid = bl.get("room_id")
                if rid in rt_room_ids and _block_overlaps_day(bl.get("start_date", ""), bl.get("end_date"), day_s):
                    blocked_ids.add(rid)

            total = len(rt_room_ids)
            sold = len(sold_ids)
            blocked = len(blocked_ids)
            available = max(total - sold - blocked, 0)

            rate_val = None
            rate_source = None
            currency = "EUR"

            if periods:
                for p in periods:
                    ps = p.get("start_date")
                    pe = p.get("end_date")
                    if ps and pe and ps <= day_s <= pe:
                        rate_val = p.get("rate")
                        currency = p.get("currency", currency)
                        rate_source = "rate_periods"
                        break

            if rate_val is None and rate_plans:
                rp = rate_plans[0]
                rate_val = rp.get("base_price")
                currency = rp.get("currency", currency)
                rate_source = "rate_plans"

            if rate_val is None:
                room_doc = await db.rooms.find_one(
                    {"tenant_id": tenant_id, "room_type": rt}, {"_id": 0, "base_price": 1}
                )
                rate_val = room_doc.get("base_price") if room_doc else None
                rate_source = "rooms.base_price"

            days.append(
                CMARIResponseDay(
                    date=day_s, room_type=rt, available=available, sold=sold,
                    stop_sell=stop_sell, rate=rate_val, currency=currency, rate_source=rate_source,
                )
            )
        cur = cur + timedelta(days=1)

    await log_audit_event(
        tenant_id=tenant_id, user_id=actor["actor_id"],
        action="cm_read_ari", entity_type="cm",
        entity_id=f"{start_date}:{end_date}",
        details=f"CM ARI read (room_type={room_type}, operator_id={operator_id})",
        db=db,
    )

    return CMARIResponse(tenant_id=tenant_id, start_date=start_date, end_date=end_date, days=days)


@router.get("/cm/ari/v2", response_model=CMARIV2Response)
async def cm_get_ari_v2(
    start_date: str,
    end_date: str,
    room_type: Optional[str] = None,
    operator_id: Optional[str] = None,
    actor: dict = Depends(get_cm_actor),
):
    """CM ARI v2 (nested room_type -> days)."""
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except Exception:
        raise HTTPException(status_code=400, detail="start_date/end_date must be YYYY-MM-DD")
    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date start_date'den once olamaz")
    if (ed - sd).days > 366:
        raise HTTPException(status_code=400, detail="Max 366 days range")

    tenant_id = actor["tenant_id"]
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    currency = (tenant.get("currency") if tenant else None) or (tenant.get("default_currency") if tenant else None) or "TRY"

    room_query: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
    }
    if room_type:
        room_query["room_type"] = room_type

    rooms = await db.rooms.find(room_query, {"_id": 0, "id": 1, "room_type": 1}).to_list(5000)
    if not rooms:
        return CMARIV2Response(hotel_id=tenant_id, currency=currency, date_from=start_date, date_to=end_date, room_types=[])

    rooms_by_type: Dict[str, List[str]] = {}
    for r in rooms:
        rt = r.get("room_type") or "unknown"
        rooms_by_type.setdefault(rt, []).append(r["id"])

    ACTIVE_STATUSES = [
        BookingStatus.CONFIRMED.value,
        BookingStatus.GUARANTEED.value,
        BookingStatus.CHECKED_IN.value,
    ]

    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ACTIVE_STATUSES},
            "check_in": {"$lt": end_date},
            "check_out": {"$gt": start_date},
        },
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    ).to_list(20000)

    blocks = await db.room_blocks.find(
        {
            "tenant_id": tenant_id,
            "status": BlockStatus.ACTIVE if isinstance(BlockStatus.ACTIVE, str) else BlockStatus.ACTIVE.value if hasattr(BlockStatus.ACTIVE, 'value') else "active",
            "start_date": {"$lt": end_date},
            "$or": [{"end_date": None}, {"end_date": {"$gt": start_date}}],
        },
        {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1},
    ).to_list(20000)

    stop_sell = False
    if operator_id:
        ss = await db.stop_sales.find_one(
            {"tenant_id": tenant_id, "operator_id": operator_id, "active": True}, {"_id": 0}
        )
        stop_sell = bool(ss)

    periods = []
    if operator_id:
        room_type_id = room_type or rooms[0].get("room_type")
        periods = await db.rate_periods.find(
            {"tenant_id": tenant_id, "operator_id": operator_id, "room_type_id": room_type_id},
            {"_id": 0},
        ).sort("start_date", 1).to_list(500)

    rate_plans = await db.rate_plans.find(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    ).to_list(200)
    default_plan = rate_plans[0] if rate_plans else {}

    def _resolve_period(day_s: str) -> Optional[dict]:
        for p in periods:
            ps = p.get("start_date")
            pe = p.get("end_date")
            if ps and pe and ps <= day_s <= pe:
                return p
        return None

    room_types_out: List[CMARIRoomType] = []
    cur = sd
    while cur <= ed:
        day_s = cur.isoformat()
        for rt, rt_room_ids in rooms_by_type.items():
            if room_type and rt != room_type:
                continue

            sold_ids = set()
            for b in bookings:
                rid = b.get("room_id")
                if rid in rt_room_ids and _overlaps_day(b.get("check_in", ""), b.get("check_out", ""), day_s):
                    sold_ids.add(rid)

            blocked_ids = set()
            for bl in blocks:
                rid = bl.get("room_id")
                if rid in rt_room_ids and _block_overlaps_day(bl.get("start_date", ""), bl.get("end_date"), day_s):
                    blocked_ids.add(rid)

            total = len(rt_room_ids)
            sold = len(sold_ids)
            blocked = len(blocked_ids)
            available = max(total - sold - blocked, 0)

            period = _resolve_period(day_s) if periods else None

            restrictions = CMRestrictions(
                stop_sell=stop_sell or bool(period.get("stop_sell")) if period else stop_sell,
                min_stay=int(period.get("min_stay", 1)) if period else 1,
                cta=bool(period.get("cta", False)) if period else False,
                ctd=bool(period.get("ctd", False)) if period else False,
                max_stay=int(period.get("max_stay")) if period and period.get("max_stay") is not None else None,
            )

            rate_amount = None
            rate_source = None
            rate_plan_id = None
            board_code = None

            if period and period.get("rate") is not None:
                rate_amount = period.get("rate")
                rate_source = "rate_periods"
                rate_plan_id = period.get("rate_plan_id")
                board_code = period.get("board_code")
            elif default_plan:
                rate_amount = default_plan.get("base_price")
                rate_source = "rate_plans"
                rate_plan_id = default_plan.get("id")
                board_code = default_plan.get("meal_plan") or default_plan.get("board_code")

            if rate_amount is None:
                room_doc = await db.rooms.find_one(
                    {"tenant_id": tenant_id, "room_type": rt}, {"_id": 0, "base_price": 1}
                )
                rate_amount = room_doc.get("base_price") if room_doc else None
                rate_source = "rooms.base_price"

            rate_info = CMRateInfo(
                amount=rate_amount, currency=currency, tax_included=True,
                source=rate_source, rate_plan_id=rate_plan_id, board_code=board_code,
            )

            existing = next((x for x in room_types_out if x.room_type_id == rt), None)
            if not existing:
                existing = CMARIRoomType(room_type_id=rt, name=rt.title(), days=[])
                room_types_out.append(existing)

            existing.days.append(
                CMARIDay(date=day_s, available=available, sold=sold, restrictions=restrictions, rate=rate_info)
            )

        cur = cur + timedelta(days=1)

    await log_audit_event(
        tenant_id=tenant_id, user_id=actor["actor_id"],
        action="cm_read_ari_v2", entity_type="cm",
        entity_id=f"{start_date}:{end_date}",
        details=f"CM ARI v2 read (room_type={room_type}, operator_id={operator_id})",
        db=db,
    )

    return CMARIV2Response(
        hotel_id=tenant_id, currency=currency,
        date_from=start_date, date_to=end_date, room_types=room_types_out,
    )


# ── Admin API Key Management ────────────────────────────────────────

@router.post("/admin/api-keys")
async def create_partner_api_key(
    name: str = Body(..., embed=True),
    current_user: Any = Depends(_temp_require_super_admin),
):
    """Create partner API key (super_admin only). Returns raw key only once."""
    key = _generate_api_key()
    doc = APIKeyModel(
        tenant_id=current_user.tenant_id,
        name=name,
        prefix=key["prefix"],
        key_hash=key["hash"],
        actor_type=CMActorType.agency,
        created_by=current_user.id,
    ).model_dump()

    await db.api_keys.insert_one(doc)

    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="create_api_key",
        entity_type="api_key",
        entity_id=doc["id"],
        details=f"Created partner api key: {name}",
        db=db,
    )

    return {
        "id": doc["id"],
        "name": doc["name"],
        "tenant_id": doc["tenant_id"],
        "prefix": doc["prefix"],
        "api_key": key["raw"],
        "masked": _mask_api_key(key["raw"]),
    }


@router.get("/admin/api-keys")
async def list_partner_api_keys(current_user: Any = Depends(_temp_require_super_admin)):
    keys = await db.api_keys.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0, "key_hash": 0}
    ).sort("created_at", -1).to_list(200)
    return {"keys": keys, "count": len(keys)}


@router.post("/admin/api-keys/{key_id}/revoke")
async def revoke_partner_api_key(
    key_id: str, current_user: Any = Depends(_temp_require_super_admin)
):
    res = await db.api_keys.update_one(
        {"tenant_id": current_user.tenant_id, "id": key_id},
        {"$set": {"is_active": False}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"success": True}


# Missing import for Any type hint
from typing import Any  # noqa: E402
