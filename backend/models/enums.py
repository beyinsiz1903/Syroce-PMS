"""
Syroce PMS - Enum Definitions
All enum types used across the application.
Extracted from server.py for modularity.
"""
from enum import Enum
from typing import Dict, List
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
import uuid

# ============= ENUMS =============

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"  # Platform admin - can manage all hotels
    ADMIN = "admin"  # Full access - Owner/IT (single hotel)
    SUPERVISOR = "supervisor"  # Management oversight
    FRONT_DESK = "front_desk"  # Reservations, check-in/out
    HOUSEKEEPING = "housekeeping"  # Room status, tasks
    SALES = "sales"  # Corporate accounts, contracts
    FINANCE = "finance"  # Accounting, invoices, AR
    STAFF = "staff"  # Limited access
    GUEST = "guest"  # Guest portal
    AGENCY_ADMIN = "agency_admin"  # Agency admin - can manage agency
    AGENCY_AGENT = "agency_agent"  # Agency staff - can create requests

class Permission(str, Enum):
    # Booking permissions
    VIEW_BOOKINGS = "view_bookings"
    CREATE_BOOKING = "create_booking"
    EDIT_BOOKING = "edit_booking"
    DELETE_BOOKING = "delete_booking"
    CHECKIN = "checkin"
    CHECKOUT = "checkout"
    
    # Folio permissions
    VIEW_FOLIO = "view_folio"
    POST_CHARGE = "post_charge"
    POST_PAYMENT = "post_payment"
    VOID_CHARGE = "void_charge"
    TRANSFER_FOLIO = "transfer_folio"
    CLOSE_FOLIO = "close_folio"
    OVERRIDE_RATE = "override_rate"
    
    # Company permissions
    VIEW_COMPANIES = "view_companies"
    CREATE_COMPANY = "create_company"
    EDIT_COMPANY = "edit_company"
    
    # Housekeeping permissions
    VIEW_HK_BOARD = "view_hk_board"
    UPDATE_ROOM_STATUS = "update_room_status"
    ASSIGN_TASK = "assign_task"
    
    # Reports permissions
    VIEW_REPORTS = "view_reports"
    VIEW_FINANCIAL_REPORTS = "view_financial_reports"
    EXPORT_DATA = "export_data"
    
    # Admin permissions
    MANAGE_USERS = "manage_users"
    MANAGE_ROOMS = "manage_rooms"
    SYSTEM_SETTINGS = "system_settings"

class RoomStatus(str, Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    DIRTY = "dirty"
    CLEANING = "cleaning"
    INSPECTED = "inspected"
    MAINTENANCE = "maintenance"
    OUT_OF_ORDER = "out_of_order"

class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    GUARANTEED = "guaranteed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    REFUNDED = "refunded"

class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    ONLINE = "online"

class ChargeType(str, Enum):
    ROOM = "room"

# ============= CHANNEL MANAGER (PROD MVP) =============

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

class APIKey(BaseModel):
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


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _mask_api_key(raw: str) -> str:
    if not raw:
        return ""
    return f"{raw[:6]}...{raw[-4:]}"


def _generate_api_key() -> dict:
    # 32 bytes urlsafe ~ 43 chars
    raw = secrets.token_urlsafe(32)
    prefix = raw[:8]
    return {"raw": raw, "prefix": prefix, "hash": _hash_api_key(raw)}


def require_cm_api_key(request: Request) -> dict:
    """Validate CM Partner API key.

    Header options:
    - X-API-Key: <raw>
    - Authorization: ApiKey <raw>

    Returns dict:
    {tenant_id, actor_type, actor_id, origin}
    """
    raw = request.headers.get('x-api-key')
    auth = request.headers.get('authorization')
    if not raw and auth and auth.lower().startswith('apikey '):
        raw = auth.split(' ', 1)[1].strip()

    if not raw:
        raise HTTPException(status_code=401, detail="Missing API key")

    key_hash = _hash_api_key(raw)

    # We can't use async here (Depends sync), so we return hash and raw; async dep will load.
    return {"raw": raw, "hash": key_hash}


async def get_cm_actor(
    request: Request,
    key_ctx: dict = Depends(require_cm_api_key),
) -> dict:
    # Lookup by hash
    api_key = await db.api_keys.find_one({"key_hash": key_ctx['hash'], "is_active": True}, {"_id": 0})
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    await db.api_keys.update_one(
        {"id": api_key['id']},
        {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}},
    )

    return {
        "tenant_id": api_key['tenant_id'],
        "actor_type": api_key.get('actor_type', 'agency'),
        "actor_id": api_key['id'],
        "origin": CMOrigin.api.value,
        "key_name": api_key.get('name'),
    }


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
    source: Optional[str] = None  # rate_periods|rate_plans|rooms.base_price
    rate_plan_id: Optional[str] = None
    board_code: Optional[str] = None  # RO/BB/HB/FB



# CM partner webhook URL (push)
CM_PARTNER_WEBHOOK_URL = os.environ.get('CM_PARTNER_WEBHOOK_URL', 'https://agency.syroce.com/webhooks/cm')


async def cm_push_event(event: dict):
    """Push CM events to partner webhook.

    Best-effort delivery (no outbox/retry yet).
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(CM_PARTNER_WEBHOOK_URL, json=event)
    except Exception as e:
        print(f"CM webhook push failed: {e}")

class CMARIDay(BaseModel):
    date: str  # YYYY-MM-DD
    available: int
    sold: int
    restrictions: CMRestrictions
    rate: CMRateInfo


class CMARIRoomType(BaseModel):
    room_type_id: str  # for now equals room_type
    name: str
    days: List[CMARIDay]


class CMARIV2Response(BaseModel):
    hotel_id: str  # tenant_id
    currency: str = "TRY"
    date_from: str
    date_to: str
    room_types: List[CMARIRoomType]


class CMARIResponseDay(BaseModel):
    date: str  # YYYY-MM-DD
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


@api_router.get("/cm/ari", response_model=CMARIResponse)
async def cm_get_ari(
    start_date: str,
    end_date: str,
    room_type: Optional[str] = None,
    operator_id: Optional[str] = None,
    actor: dict = Depends(get_cm_actor),
):
    """Channel Manager ARI endpoint (prod MVP).

    - tenant resolved from API key
    - availability computed from rooms - active bookings - room blocks
    - stop_sell applied via stop_sales (operator-based if provided)
    - rate resolved from rate_periods (operator_id+room_type_id) if available; fallback rate_plans/rooms

    NOTE: rate_periods uses room_type_id, but current PMS uses room_type strings.
    For now, we treat room_type_id == room_type.
    """

    # Basic input validation
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except Exception:
        raise HTTPException(status_code=400, detail="start_date/end_date must be YYYY-MM-DD")

    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date start_date'den önce olamaz")

    if (ed - sd).days > 366:
        raise HTTPException(status_code=400, detail="Max 366 days range")

    tenant_id = actor['tenant_id']

    # Rooms by type (active only; backward compatible)
    room_query: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
    }
    if room_type:
        room_query["room_type"] = room_type

    rooms = await db.rooms.find(room_query, {"_id": 0, "id": 1, "room_type": 1}).to_list(5000)
    if not rooms:
        return CMARIResponse(tenant_id=tenant_id, start_date=start_date, end_date=end_date, days=[])

    # Active bookings in range
    ACTIVE_STATUSES = [
        BookingStatus.CONFIRMED.value,
        BookingStatus.GUARANTEED.value,
        BookingStatus.CHECKED_IN.value,
    ]

    # Overlap: booking.check_in < end_date AND booking.check_out > start_date
    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ACTIVE_STATUSES},
            "check_in": {"$lt": end_date},
            "check_out": {"$gt": start_date},
        },
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    ).to_list(10000)

    # Room blocks in range (room_blocks uses start_date/end_date; end_date may be null => open-ended)
    blocks = await db.room_blocks.find(
        {
            "tenant_id": tenant_id,
            "status": BlockStatus.ACTIVE.value,
            "start_date": {"$lt": end_date},
            "$or": [
                {"end_date": None},
                {"end_date": {"$gt": start_date}},
            ],
        },
        {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1},
    ).to_list(10000)

    # Stop-sell (operator-based)
    stop_sell = False
    if operator_id:
        ss = await db.stop_sales.find_one({"tenant_id": tenant_id, "operator_id": operator_id, "active": True}, {"_id": 0})
        stop_sell = bool(ss)

    # Rates: use rate_periods if operator_id present
    # rate_periods uses start_date/end_date strings; date compare should be parsed or kept yyyy-mm-dd
    periods = []
    if operator_id:
        # In this PMS, we do not yet have a room_type_id table; treat room_type_id as room_type.
        room_type_id = room_type or rooms[0].get('room_type')
        periods = await db.rate_periods.find(
            {"tenant_id": tenant_id, "operator_id": operator_id, "room_type_id": room_type_id},
            {"_id": 0},
        ).sort('start_date', 1).to_list(200)

    # Rate plans fallback (BAR by default)
    rate_plans = await db.rate_plans.find({"tenant_id": tenant_id, "is_active": True}, {"_id": 0}).to_list(200)

    # Pre-group rooms by type
    rooms_by_type: Dict[str, List[str]] = {}
    for r in rooms:
        rt = r.get('room_type') or 'unknown'
        rooms_by_type.setdefault(rt, []).append(r['id'])

    # Helper: compute sold for a day
    def _overlaps_day(check_in_s: str, check_out_s: str, day_s: str) -> bool:
        # check_in/check_out are YYYY-MM-DD strings
        # day is within [check_in, check_out)
        return check_in_s <= day_s < check_out_s

    # Helper: compute blocked for a day
    def _block_overlaps_day(start_s: str, end_s: Optional[str], day_s: str) -> bool:
        if end_s is None:
            return start_s <= day_s
        return start_s <= day_s < end_s

    days: List[CMARIResponseDay] = []
    cur = sd
    while cur <= ed:
        day_s = cur.isoformat()


        for rt, rt_room_ids in rooms_by_type.items():
            if room_type and rt != room_type:
                continue

            sold_ids = set()
            for b in bookings:
                rid = b.get('room_id')
                if rid in rt_room_ids and _overlaps_day(b.get('check_in',''), b.get('check_out',''), day_s):
                    sold_ids.add(rid)

            blocked_ids = set()
            for bl in blocks:
                rid = bl.get('room_id')
                if rid in rt_room_ids and _block_overlaps_day(bl.get('start_date',''), bl.get('end_date'), day_s):
                    blocked_ids.add(rid)

            total = len(rt_room_ids)
            sold = len(sold_ids)
            blocked = len(blocked_ids)
            available = max(total - sold - blocked, 0)

            # resolve rate
            rate_val = None
            rate_source = None
            currency = "EUR"

            # 1) rate_periods: pick period where day within [start_date,end_date]
            if periods:
                for p in periods:
                    ps = p.get('start_date')
                    pe = p.get('end_date')
                    if ps and pe and ps <= day_s <= pe:
                        rate_val = p.get('rate')
                        currency = p.get('currency', currency)
                        rate_source = 'rate_periods'
                        break

            # 2) rate_plans fallback
            if rate_val is None and rate_plans:
                # take first active plan
                rp = rate_plans[0]
                rate_val = rp.get('base_price')
                currency = rp.get('currency', currency)
                rate_source = 'rate_plans'

            # 3) rooms.base_price fallback
            if rate_val is None:
                room_doc = await db.rooms.find_one({"tenant_id": tenant_id, "room_type": rt}, {"_id": 0, "base_price": 1})
                rate_val = room_doc.get('base_price') if room_doc else None
                rate_source = 'rooms.base_price'

            days.append(
                CMARIResponseDay(
                    date=day_s,
                    room_type=rt,
                    available=available,
                    sold=sold,
                    stop_sell=stop_sell,
                    rate=rate_val,
                    currency=currency,
                    rate_source=rate_source,
                )
            )
        cur = cur + timedelta(days=1)

    # Audit (new schema will be added in later phase; log minimal now)
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=actor['actor_id'],
        action='cm_read_ari',
        entity_type='cm',
        entity_id=f"{start_date}:{end_date}",
        details=f"CM ARI read (room_type={room_type}, operator_id={operator_id})",
        db=db,
    )

    return CMARIResponse(tenant_id=tenant_id, start_date=start_date, end_date=end_date, days=days)



@api_router.get("/cm/ari/v2", response_model=CMARIV2Response)
async def cm_get_ari_v2(
    start_date: str,
    end_date: str,
    room_type: Optional[str] = None,
    operator_id: Optional[str] = None,
    actor: dict = Depends(get_cm_actor),
):
    """CM ARI v2 (nested room_type -> days).

    Backward compatible: keeps existing /cm/ari.

    Restrictions source (decision 2c): pulled from rate_periods when operator_id is provided.
    If restriction fields missing, defaults: min_stay=1, cta=false, ctd=false.

    Currency (decision 3a): tenant default currency (if available) else TRY.
    tax_included default: true.

    NOTE: rate_periods uses string dates (YYYY-MM-DD). We compare lexically but input is validated.
    """

    # Validate dates
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except Exception:
        raise HTTPException(status_code=400, detail="start_date/end_date must be YYYY-MM-DD")
    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date start_date'den önce olamaz")
    if (ed - sd).days > 366:
        raise HTTPException(status_code=400, detail="Max 366 days range")

    tenant_id = actor['tenant_id']

    # Tenant currency (best-effort)
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    currency = (tenant.get('currency') if tenant else None) or (tenant.get('default_currency') if tenant else None) or "TRY"

    # Rooms
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
        rt = r.get('room_type') or 'unknown'
        rooms_by_type.setdefault(rt, []).append(r['id'])

    # Active bookings
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

    # Room blocks
    blocks = await db.room_blocks.find(
        {
            "tenant_id": tenant_id,
            "status": BlockStatus.ACTIVE.value,
            "start_date": {"$lt": end_date},
            "$or": [
                {"end_date": None},
                {"end_date": {"$gt": start_date}},
            ],
        },
        {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1},
    ).to_list(20000)

    # Stop-sell (operator-based)
    stop_sell = False
    if operator_id:
        ss = await db.stop_sales.find_one({"tenant_id": tenant_id, "operator_id": operator_id, "active": True}, {"_id": 0})
        stop_sell = bool(ss)

    # rate_periods (rate + restrictions)
    periods = []
    if operator_id:
        # Treat room_type_id as room_type
        room_type_id = room_type or rooms[0].get('room_type')
        periods = await db.rate_periods.find(
            {"tenant_id": tenant_id, "operator_id": operator_id, "room_type_id": room_type_id},
            {"_id": 0},
        ).sort('start_date', 1).to_list(500)

    rate_plans = await db.rate_plans.find({"tenant_id": tenant_id, "is_active": True}, {"_id": 0}).to_list(200)
    default_plan = rate_plans[0] if rate_plans else {}

    def _overlaps_day(check_in_s: str, check_out_s: str, day_s: str) -> bool:
        return check_in_s <= day_s < check_out_s

    def _block_overlaps_day(start_s: str, end_s: Optional[str], day_s: str) -> bool:
        if end_s is None:
            return start_s <= day_s
        return start_s <= day_s < end_s

    def _resolve_period(day_s: str) -> Optional[dict]:
        for p in periods:
            ps = p.get('start_date')
            pe = p.get('end_date')
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
                rid = b.get('room_id')
                if rid in rt_room_ids and _overlaps_day(b.get('check_in',''), b.get('check_out',''), day_s):
                    sold_ids.add(rid)

            blocked_ids = set()
            for bl in blocks:
                rid = bl.get('room_id')
                if rid in rt_room_ids and _block_overlaps_day(bl.get('start_date',''), bl.get('end_date'), day_s):
                    blocked_ids.add(rid)

            total = len(rt_room_ids)
            sold = len(sold_ids)
            blocked = len(blocked_ids)
            available = max(total - sold - blocked, 0)

            # rate + restrictions
            period = _resolve_period(day_s) if periods else None

            # restrictions from rate_periods (decision 2c)
            restrictions = CMRestrictions(
                stop_sell=stop_sell or bool(period.get('stop_sell')) if period else stop_sell,
                min_stay=int(period.get('min_stay', 1)) if period else 1,
                cta=bool(period.get('cta', False)) if period else False,
                ctd=bool(period.get('ctd', False)) if period else False,
                max_stay=int(period.get('max_stay')) if period and period.get('max_stay') is not None else None,
            )

            rate_amount = None
            rate_source = None
            rate_plan_id = None
            board_code = None

            if period and period.get('rate') is not None:
                rate_amount = period.get('rate')
                rate_source = 'rate_periods'
                rate_plan_id = period.get('rate_plan_id')
                board_code = period.get('board_code')
            elif default_plan:
                rate_amount = default_plan.get('base_price')
                rate_source = 'rate_plans'
                rate_plan_id = default_plan.get('id')
                board_code = default_plan.get('meal_plan') or default_plan.get('board_code')

            if rate_amount is None:
                room_doc = await db.rooms.find_one({"tenant_id": tenant_id, "room_type": rt}, {"_id": 0, "base_price": 1})
                rate_amount = room_doc.get('base_price') if room_doc else None
                rate_source = 'rooms.base_price'

            rate_info = CMRateInfo(
                amount=rate_amount,
                currency=currency,
                tax_included=True,
                source=rate_source,
                rate_plan_id=rate_plan_id,
                board_code=board_code,
            )

            # add day to proper room_type bucket
            existing = next((x for x in room_types_out if x.room_type_id == rt), None)
            if not existing:
                existing = CMARIRoomType(room_type_id=rt, name=rt.title(), days=[])
                room_types_out.append(existing)

            existing.days.append(
                CMARIDay(
                    date=day_s,
                    available=available,
                    sold=sold,
                    restrictions=restrictions,
                    rate=rate_info,
                )
            )

        cur = cur + timedelta(days=1)

    await log_audit_event(
        tenant_id=tenant_id,
        user_id=actor['actor_id'],
        action='cm_read_ari_v2',
        entity_type='cm',
        entity_id=f"{start_date}:{end_date}",
        details=f"CM ARI v2 read (room_type={room_type}, operator_id={operator_id})",
        db=db,
    )

    return CMARIV2Response(
        hotel_id=tenant_id,
        currency=currency,
        date_from=start_date,
        date_to=end_date,
        room_types=room_types_out,
    )

# Temporary auth function for Channel Manager endpoints
async def temp_require_super_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Temporary super admin check for Channel Manager endpoints"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')
        
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_doc = await db.users.find_one({'$or': [{'id': user_id}, {'user_id': user_id}]}, {'_id': 0})
        
        if not user_doc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        
        user = User(**user_doc)
        if user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin required")
        
        return user
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


# Main require_super_admin function for use throughout the file
async def require_super_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Require super admin authentication for admin endpoints"""
    return await temp_require_super_admin(credentials)


@api_router.post("/admin/api-keys")
async def create_partner_api_key(
    name: str = Body(..., embed=True),
    current_user: Any = Depends(temp_require_super_admin),
):
    """Create partner API key (super_admin only).

    Returns raw key only once.
    """
    key = _generate_api_key()
    doc = APIKey(
        tenant_id=current_user.tenant_id,
        name=name,
        prefix=key['prefix'],
        key_hash=key['hash'],
        actor_type=CMActorType.agency,
        created_by=current_user.id,
    ).model_dump()

    await db.api_keys.insert_one(doc)

    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action='create_api_key',
        entity_type='api_key',
        entity_id=doc['id'],
        details=f"Created partner api key: {name}",
        db=db,
    )

    return {
        "id": doc['id'],
        "name": doc['name'],
        "tenant_id": doc['tenant_id'],
        "prefix": doc['prefix'],
        "api_key": key['raw'],
        "masked": _mask_api_key(key['raw']),
    }


@api_router.get("/admin/api-keys")
async def list_partner_api_keys(current_user: Any = Depends(temp_require_super_admin)):
    keys = await db.api_keys.find({"tenant_id": current_user.tenant_id}, {"_id": 0, "key_hash": 0}).sort('created_at', -1).to_list(200)
    return {"keys": keys, "count": len(keys)}


@api_router.post("/admin/api-keys/{key_id}/revoke")
async def revoke_partner_api_key(key_id: str, current_user: Any = Depends(temp_require_super_admin)):
    res = await db.api_keys.update_one({"tenant_id": current_user.tenant_id, "id": key_id}, {"$set": {"is_active": False}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"success": True}

    FOOD = "food"
    BEVERAGE = "beverage"
    LAUNDRY = "laundry"
    MINIBAR = "minibar"
    PHONE = "phone"
    SPA = "spa"
    OTHER = "other"

class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"

class LoyaltyTier(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"

class RoomServiceStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class ChannelType(str, Enum):
    DIRECT = "direct"
    BOOKING_COM = "booking_com"
    EXPEDIA = "expedia"
    AIRBNB = "airbnb"
    AGODA = "agoda"
    OWN_WEBSITE = "own_website"
    HOTELS_COM = "hotels_com"
    TRIP_ADVISOR = "trip_advisor"

class ChannelStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    SYNCING = "syncing"

class MappingStatus(str, Enum):
    MAPPED = "mapped"
    UNMAPPED = "unmapped"
    CONFLICT = "conflict"
    NEEDS_REVIEW = "needs_review"

class PricingStrategy(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    COMPETITIVE = "competitive"
    OCCUPANCY_BASED = "occupancy_based"

class ContractedRateType(str, Enum):
    CORP_STD = "corp_std"  # Standard Corporate
    CORP_PREF = "corp_pref"  # Preferred Corporate
    GOV = "gov"  # Government Rate
    TA = "ta"  # Travel Agent Rate
    CREW = "crew"  # Airline Crew Rate
    MICE = "mice"  # Event/Conference Rate
    LTS = "lts"  # Long Stay/Project Rate
    TOU = "tou"  # Tour Operator/Series Group Rate

class RateType(str, Enum):
    STANDARD = "standard"  # Standard Rate
    BAR = "bar"  # Best Available Rate / Rack Rate
    CORPORATE = "corporate"
    GOVERNMENT = "government"
    WHOLESALE = "wholesale"
    PACKAGE = "package"
    PROMOTIONAL = "promotional"
    NON_REFUNDABLE = "non_refundable"
    LONG_STAY = "long_stay"
    DAY_USE = "day_use"

class MarketSegment(str, Enum):
    CORPORATE = "corporate"
    LEISURE = "leisure"
    GROUP = "group"
    MICE = "mice"
    GOVERNMENT = "government"
    CREW = "crew"
    WHOLESALE = "wholesale"
    LONG_STAY = "long_stay"
    COMPLIMENTARY = "complimentary"
    OTHER = "other"

class CancellationPolicyType(str, Enum):
    SAME_DAY = "same_day"  # Free cancellation until 18:00
    H24 = "h24"  # 24 hours before check-in
    H48 = "h48"  # 48 hours before check-in
    H72 = "h72"  # 72 hours before check-in
    D7 = "d7"  # 7 days before check-in
    D14 = "d14"  # 14 days before check-in
    NON_REFUNDABLE = "non_refundable"
    FLEXIBLE = "flexible"
    SPECIAL_EVENT = "special_event"

class CompanyStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"  # Quick-created from booking form
    INACTIVE = "inactive"

class OTAChannel(str, Enum):
    BOOKING_COM = "booking_com"
    EXPEDIA = "expedia"
    AIRBNB = "airbnb"
    AGODA = "agoda"
    HOTELS_COM = "hotels_com"
    DIRECT = "direct"  # Direct booking
    PHONE = "phone"  # Phone booking
    WALK_IN = "walk_in"

class OTAPaymentModel(str, Enum):
    AGENCY = "agency"  # OTA collects, pays hotel
    HOTEL_COLLECT = "hotel_collect"  # Hotel collects from guest
    VIRTUAL_CARD = "virtual_card"  # OTA provides virtual card
    PREPAID = "prepaid"  # Guest prepaid to OTA

class ParityStatus(str, Enum):
    NEGATIVE = "negative"  # OTA cheaper (bad)
    POSITIVE = "positive"  # Direct cheaper (good)
    EQUAL = "equal"  # Same rate
    UNKNOWN = "unknown"

class ChannelHealth(str, Enum):
    HEALTHY = "healthy"
    DELAYED = "delayed"
    ERROR = "error"
    OFFLINE = "offline"

class FolioType(str, Enum):
    GUEST = "guest"
    COMPANY = "company"
    AGENCY = "agency"

class FolioStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    TRANSFERRED = "transferred"
    VOIDED = "voided"

class ChargeCategory(str, Enum):
    ROOM = "room"
    FOOD = "food"
    BEVERAGE = "beverage"
    MINIBAR = "minibar"
    SPA = "spa"
    LAUNDRY = "laundry"
    PHONE = "phone"
    INTERNET = "internet"
    PARKING = "parking"
    CITY_TAX = "city_tax"
    SERVICE_CHARGE = "service_charge"
    OTHER = "other"

class FolioOperationType(str, Enum):
    TRANSFER = "transfer"
    SPLIT = "split"
    MERGE = "merge"
    VOID = "void"
    REFUND = "refund"

class PaymentType(str, Enum):
    PREPAYMENT = "prepayment"
    DEPOSIT = "deposit"
    INTERIM = "interim"
    FINAL = "final"
    REFUND = "refund"

# Finance Mobile Enhancements - Department & Risk Management
class DepartmentType(str, Enum):
    ROOMS = "rooms"  # Konaklama
    FNB = "fnb"  # Restaurant, Bar, Room Service
    SPA = "spa"  # SPA & Wellness
    LAUNDRY = "laundry"  # Laundry / Dry Cleaning
    MINIBAR = "minibar"  # Mini Bar
    TELEPHONE = "telephone"  # Telephone / Communication
    TRANSPORTATION = "transportation"  # VIP Transfer
    TECHNICAL = "technical"  # Technical Charges
    HOUSEKEEPING_CHARGES = "housekeeping_charges"  # Lost&Found Compensation
    OTHER = "other"  # Other Services

class RiskLevel(str, Enum):
    NORMAL = "normal"  # 0-7 days - Green
    WARNING = "warning"  # 8-14 days - Yellow
    CRITICAL = "critical"  # 15-30 days - Red
    SUSPICIOUS = "suspicious"  # 30+ days - Black



# Maintenance & Technical Service Enums
class MaintenanceTaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    WAITING_PARTS = "waiting_parts"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class MaintenancePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    EMERGENCY = "emergency"

class WarehouseLocation(str, Enum):
    MAIN_WAREHOUSE = "main_warehouse"
    FLOOR_STORAGE = "floor_storage"
    WORKSHOP = "workshop"
    EXTERNAL = "external"

class MaintenanceType(str, Enum):
    CORRECTIVE = "corrective"  # Arıza onarımı
    PREVENTIVE = "preventive"  # Önleyici bakım
    PLANNED = "planned"  # Planlı bakım
    EMERGENCY = "emergency"  # Acil müdahale


# F&B Management Enums
class OrderStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"

class OutletType(str, Enum):
    RESTAURANT = "restaurant"
    BAR = "bar"
    ROOM_SERVICE = "room_service"
    CAFE = "cafe"
    POOLSIDE = "poolside"
    BANQUET = "banquet"

class MeasurementUnit(str, Enum):
    KG = "kg"
    GRAM = "gram"
    LITER = "liter"
    ML = "ml"
    PIECE = "piece"
    PORTION = "portion"


# Front Office Mobile Enums
class GuestRequestType(str, Enum):
    EXTRA_TOWEL = "extra_towel"
    EXTRA_PILLOW = "extra_pillow"
    ROOM_CLEANING = "room_cleaning"
    WAKE_UP_CALL = "wake_up_call"
    TAXI = "taxi"
    RESTAURANT_RESERVATION = "restaurant_reservation"
    LATE_CHECKOUT = "late_checkout"
    EARLY_CHECKIN = "early_checkin"
    MAINTENANCE = "maintenance"
    OTHER = "other"

class GuestRequestStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class CheckInStatus(str, Enum):
    PRE_ARRIVAL = "pre_arrival"
    CHECKING_IN = "checking_in"
    CHECKED_IN = "checked_in"
    IN_HOUSE = "in_house"


# Housekeeping Enhanced Enums
class InspectionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class LostFoundStatus(str, Enum):
    FOUND = "found"
    IN_STORAGE = "in_storage"
    CLAIMED = "claimed"


# Revenue Management Enums
class MarketSegment(str, Enum):
    CORPORATE = "corporate"
    LEISURE = "leisure"
    GROUP = "group"
    MICE = "mice"
    GOVERNMENT = "government"
    WHOLESALE = "wholesale"
    NEGOTIATED = "negotiated"

# Duplicate PricingStrategy enum removed - using the first one





# Role-Permission Mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [p.value for p in Permission],  # All permissions
    UserRole.SUPERVISOR: [
        Permission.VIEW_BOOKINGS, Permission.CREATE_BOOKING, Permission.EDIT_BOOKING,
        Permission.CHECKIN, Permission.CHECKOUT,
        Permission.VIEW_FOLIO, Permission.POST_CHARGE, Permission.POST_PAYMENT,
        Permission.OVERRIDE_RATE, Permission.CLOSE_FOLIO,
        Permission.VIEW_COMPANIES, Permission.EDIT_COMPANY,
        Permission.VIEW_HK_BOARD, Permission.UPDATE_ROOM_STATUS, Permission.ASSIGN_TASK,
        Permission.VIEW_REPORTS, Permission.VIEW_FINANCIAL_REPORTS
    ],
    UserRole.FRONT_DESK: [
        Permission.VIEW_BOOKINGS, Permission.CREATE_BOOKING, Permission.EDIT_BOOKING,
        Permission.CHECKIN, Permission.CHECKOUT,
        Permission.VIEW_FOLIO, Permission.POST_CHARGE, Permission.POST_PAYMENT,
        Permission.VIEW_COMPANIES,
        Permission.VIEW_HK_BOARD,
        Permission.VIEW_REPORTS
    ],
    UserRole.HOUSEKEEPING: [
        Permission.VIEW_BOOKINGS,
        Permission.VIEW_HK_BOARD, Permission.UPDATE_ROOM_STATUS, Permission.ASSIGN_TASK
    ],
    UserRole.SALES: [
        Permission.VIEW_BOOKINGS, Permission.CREATE_BOOKING,
        Permission.VIEW_COMPANIES, Permission.CREATE_COMPANY, Permission.EDIT_COMPANY,
        Permission.VIEW_REPORTS
    ],
    UserRole.FINANCE: [
        Permission.VIEW_BOOKINGS,
        Permission.VIEW_FOLIO, Permission.POST_CHARGE, Permission.POST_PAYMENT,
        Permission.VOID_CHARGE, Permission.CLOSE_FOLIO,
        Permission.VIEW_COMPANIES,
        Permission.VIEW_REPORTS, Permission.VIEW_FINANCIAL_REPORTS, Permission.EXPORT_DATA
    ],
    UserRole.STAFF: [
        Permission.VIEW_BOOKINGS,
        Permission.VIEW_HK_BOARD
    ]
}
