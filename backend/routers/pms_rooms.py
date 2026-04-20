"""
PMS Rooms Router — Extracted from routers/pms.py (Stage 1 decomposition)
Room CRUD, bulk operations, CSV import, image upload.
"""
import csv
import io
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from core.database import db
from core.helpers import require_module, require_super_admin_guard
from core.security import get_current_user
from models.enums import CompanyStatus
from models.schemas import Room, RoomCreate, User

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/backend/uploads"))

router = APIRouter(prefix="/api", tags=["pms"])


# ── Local models ──


class RoomCsvImportResponse(BaseModel):
    created: int
    skipped: int
    errors: int
    skipped_room_numbers: list[str] = []
    error_rows: list[dict[str, Any]] = []


class RoomBulkRangeRequest(BaseModel):
    """Create many rooms quickly using a numeric range.

    Supports:
    - prefix (optional): e.g. "A" -> A101, A102 ...
    - start/end inclusive
    """

    prefix: str | None = None
    start_number: int
    end_number: int
    floor: int
    room_type: str
    capacity: int = 2
    base_price: float = 0
    amenities: list[str] = []
    view: str | None = None
    bed_type: str | None = None


class RoomBulkTemplateRequest(BaseModel):
    """Create N rooms based on a template.

    Supports prefix + starting number to auto-generate unique room_number values.
    """

    prefix: str | None = None
    start_number: int = 1
    count: int
    floor: int
    room_type: str
    capacity: int = 2
    base_price: float = 0
    amenities: list[str] = []
    view: str | None = None
    bed_type: str | None = None


class RoomBulkCreateResponse(BaseModel):
    created: int
    skipped: int


class RoomBulkDeleteRequest(BaseModel):
    """Soft-delete many rooms in one request.

    Supports:
    - ids: explicit room ids
    - room_numbers: explicit room numbers
    - prefix + start/end numeric range

    Safety:
    - requires confirm_text == 'DELETE'
    - blocks rooms with active/checked_in bookings in date range
    """

    ids: list[str] | None = None
    room_numbers: list[str] | None = None

    prefix: str | None = None
    start_number: int | None = None
    end_number: int | None = None

    confirm_text: str


class RoomBulkDeleteResponse(BaseModel):
    to_delete: int
    deleted: int
    blocked: int
    blocked_rooms: list[str] = []
    deleted_room_numbers: list[str] = []

    rooms: list[Room] = []
    skipped_room_numbers: list[str] = []


# ── Routes ──


@router.post("/pms/rooms", response_model=Room)
async def create_room(
    room_data: RoomCreate,
    current_user: User = Depends(require_super_admin_guard(not_found=False)),
    _: None = Depends(require_module("pms")),
):
    room = Room(tenant_id=current_user.tenant_id, **room_data.model_dump())
    room_dict = room.model_dump()
    room_dict['created_at'] = room_dict['created_at'].isoformat()
    await db.rooms.insert_one(room_dict)
    return room


@router.get("/pms/rooms", response_model=list[Room])
async def get_rooms(
    limit: int = 100,  # Optimized for 550+ room properties - load in batches
    offset: int = 0,
    status: str | None = None,
    room_type: str | None = None,
    view: str | None = None,
    amenity: str | None = None,
    include_virtual: bool = False,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Get rooms with pagination - Optimized for large properties (550+ rooms)"""

    # For small queries with filters, skip cache
    use_cache = (offset == 0 and not status and not room_type and not view and not amenity and not include_virtual and limit >= 100)

    # Try Redis cache first (FASTEST!) - only for full list
    if use_cache:
        try:
            from redis_cache import redis_cache
            if redis_cache:
                cache_key = f"rooms:{current_user.tenant_id}:limit{limit}:nv"
                cached = redis_cache.get(cache_key)
                if cached:
                    # Filter virtual from cached data
                    return [r for r in cached if not r.get('is_virtual')]
        except Exception:
            logger.debug("pms_rooms: redis cache read failed", exc_info=True)

        # Check pre-warmed cache second
        from cache_warmer import cache_warmer
        if cache_warmer:
            cached_data = cache_warmer.get_cached(f"rooms:{current_user.tenant_id}")
            if cached_data:
                # Process cached data quickly
                rooms = []
                for room in cached_data[:limit]:  # Apply limit to cached data
                    # Skip virtual rooms
                    if room.get('is_virtual'):
                        continue
                    # Ensure tenant_id is present
                    if 'tenant_id' not in room:
                        room['tenant_id'] = current_user.tenant_id

                    if 'floor' in room and isinstance(room['floor'], str):
                        try:
                            room['floor'] = int(room['floor'])
                        except Exception:
                            room['floor'] = 1
                    elif 'floor' not in room:
                        room['floor'] = 1

                    if 'capacity' not in room and 'max_occupancy' in room:
                        room['capacity'] = room['max_occupancy']
                    elif 'capacity' not in room:
                        room['capacity'] = 2

                    rooms.append(room)
                return rooms

    # Build query with filters
    # Backward compatible: old room docs may not have is_active field.
    active_cond = {'$or': [{'is_active': True}, {'is_active': {'$exists': False}}]}
    base_conds = [active_cond]
    if not include_virtual:
        base_conds.append({'$or': [{'is_virtual': False}, {'is_virtual': {'$exists': False}}]})
    query = {
        'tenant_id': current_user.tenant_id,
        '$and': base_conds,
    }
    if status:
        query['status'] = status
    if room_type:
        query['room_type'] = room_type
    if view:
        query['view'] = view
    if amenity:
        query['amenities'] = amenity

    # Fallback: Ultra-minimal projection with pagination
    projection = {'_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1, 'status': 1, 'floor': 1, 'capacity': 1, 'max_occupancy': 1, 'base_price': 1, 'tenant_id': 1, 'amenities': 1, 'view': 1, 'bed_type': 1, 'images': 1, 'is_virtual': 1}
    rooms_raw = await db.rooms.find(query, projection).skip(offset).limit(limit).to_list(limit)

    # Fix field mapping
    rooms = []
    for room in rooms_raw:
        # Convert floor to int if it's string
        if 'floor' in room and isinstance(room['floor'], str):
            try:
                room['floor'] = int(room['floor'])
            except Exception:
                room['floor'] = 1
        elif 'floor' not in room:
            room['floor'] = 1

        # Map max_occupancy to capacity if needed
        if 'capacity' not in room and 'max_occupancy' in room:
            room['capacity'] = room['max_occupancy']
        elif 'capacity' not in room:
            room['capacity'] = 2

        rooms.append(room)

    # Cache result in Redis for 30 seconds (only for full lists)
    if use_cache:
        try:
            from redis_cache import redis_cache
            if redis_cache:
                cache_key = f"rooms:{current_user.tenant_id}:limit{limit}"
                redis_cache.set(cache_key, rooms, ttl=30)
        except Exception:
            logger.debug("pms_rooms: redis cache write failed", exc_info=True)

    return rooms


@router.post("/pms/rooms/bulk/range", response_model=RoomBulkCreateResponse)
async def bulk_create_rooms_range(
    payload: RoomBulkRangeRequest,
    current_user: User = Depends(require_super_admin_guard(not_found=False)),
    _: None = Depends(require_module("pms")),
):
    if payload.end_number < payload.start_number:
        raise HTTPException(status_code=400, detail="end_number start_number'dan kucuk olamaz")
    if payload.end_number - payload.start_number + 1 > 2000:
        raise HTTPException(status_code=400, detail="Tek seferde maksimum 2000 oda olusturabilirsiniz")

    prefix = (payload.prefix or "").strip()

    created_rooms: list[Room] = []
    skipped: list[str] = []

    existing = await db.rooms.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "room_number": 1},
    ).to_list(5000)
    existing_numbers = {r.get("room_number") for r in existing if r.get("room_number")}

    docs = []
    for n in range(payload.start_number, payload.end_number + 1):
        room_number = f"{prefix}{n}"
        if room_number in existing_numbers:
            skipped.append(room_number)
            continue

        room = Room(
            tenant_id=current_user.tenant_id,
            room_number=room_number,
            room_type=payload.room_type,
            floor=payload.floor,
            capacity=payload.capacity,
            base_price=payload.base_price,
            amenities=payload.amenities,
            view=payload.view,
            bed_type=payload.bed_type,
        )
        room_dict = room.model_dump()
        room_dict['created_at'] = room_dict['created_at'].isoformat()
        docs.append(room_dict)
        created_rooms.append(room)

    if docs:
        await db.rooms.insert_many(docs)

    return RoomBulkCreateResponse(
        created=len(created_rooms),
        skipped=len(skipped),
        rooms=created_rooms,
        skipped_room_numbers=skipped,
    )


@router.post("/pms/rooms/bulk/template", response_model=RoomBulkCreateResponse)
async def bulk_create_rooms_template(
    payload: RoomBulkTemplateRequest,
    current_user: User = Depends(require_super_admin_guard(not_found=False)),
    _: None = Depends(require_module("pms")),
):
    if payload.count <= 0:
        raise HTTPException(status_code=400, detail="count 0'dan buyuk olmali")
    if payload.count > 2000:
        raise HTTPException(status_code=400, detail="Tek seferde maksimum 2000 oda olusturabilirsiniz")

    prefix = (payload.prefix or "").strip()

    existing = await db.rooms.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "room_number": 1},
    ).to_list(5000)
    existing_numbers = {r.get("room_number") for r in existing if r.get("room_number")}

    created_rooms: list[Room] = []
    skipped: list[str] = []
    docs = []

    current = payload.start_number
    created_count = 0
    safety = 0
    while created_count < payload.count:
        safety += 1
        if safety > payload.count + 5000:
            raise HTTPException(status_code=400, detail="Oda numarasi uretiminde cok fazla cakisma olustu")

        room_number = f"{prefix}{current}"
        current += 1

        if room_number in existing_numbers:
            skipped.append(room_number)
            continue

        room = Room(
            tenant_id=current_user.tenant_id,
            room_number=room_number,
            room_type=payload.room_type,
            floor=payload.floor,
            capacity=payload.capacity,
            base_price=payload.base_price,
            amenities=payload.amenities,
            view=payload.view,
            bed_type=payload.bed_type,
        )
        room_dict = room.model_dump()
        room_dict['created_at'] = room_dict['created_at'].isoformat()
        docs.append(room_dict)
        created_rooms.append(room)
        existing_numbers.add(room_number)
        created_count += 1

    if docs:
        await db.rooms.insert_many(docs)

    return RoomBulkCreateResponse(
        created=len(created_rooms),
        skipped=len(skipped),
        rooms=created_rooms,
        skipped_room_numbers=skipped,
    )


@router.post("/pms/rooms/bulk/delete", response_model=RoomBulkDeleteResponse)
async def bulk_delete_rooms(
    payload: RoomBulkDeleteRequest,
    current_user: User = Depends(require_super_admin_guard(not_found=False)),
    _: None = Depends(require_module("pms")),
):
    # Permission: super_admin only

    if (payload.confirm_text or '').strip().upper() != 'DELETE':
        raise HTTPException(status_code=400, detail="Silme islemini onaylamak icin 'DELETE' yazmalisiniz")

    target_ids = set(payload.ids or [])
    target_numbers = {rn.strip() for rn in (payload.room_numbers or []) if rn and rn.strip()}

    if payload.start_number is not None or payload.end_number is not None:
        if payload.start_number is None or payload.end_number is None:
            raise HTTPException(status_code=400, detail="Range icin start_number ve end_number zorunlu")
        if payload.end_number < payload.start_number:
            raise HTTPException(status_code=400, detail="end_number start_number'dan kucuk olamaz")
        if payload.end_number - payload.start_number + 1 > 2000:
            raise HTTPException(status_code=400, detail="Tek seferde maksimum 2000 oda silebilirsiniz")

        prefix = (payload.prefix or '').strip()
        for n in range(payload.start_number, payload.end_number + 1):
            target_numbers.add(f"{prefix}{n}")

    if not target_ids and not target_numbers:
        raise HTTPException(status_code=400, detail="Silinecek oda secilmedi")

    query: dict[str, Any] = {
        "tenant_id": current_user.tenant_id,
        "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
    }
    or_clauses = []
    if target_ids:
        or_clauses.append({"id": {"$in": list(target_ids)}})
    if target_numbers:
        or_clauses.append({"room_number": {"$in": list(target_numbers)}})
    if or_clauses:
        query["$or"] = or_clauses

    rooms = await db.rooms.find(query, {"_id": 0, "id": 1, "room_number": 1}).to_list(5000)

    room_ids = [r['id'] for r in rooms]
    if not room_ids:
        return RoomBulkDeleteResponse(to_delete=0, deleted=0, blocked=0)

    active_bookings = await db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "room_id": {"$in": room_ids},
            "status": {"$in": ["confirmed", "checked_in"]},
            "is_active": True,
        },
        {"_id": 0, "room_id": 1},
    ).to_list(5000)

    blocked_room_ids = {b.get('room_id') for b in active_bookings if b.get('room_id')}

    to_delete_rooms = [r for r in rooms if r['id'] not in blocked_room_ids]
    blocked_rooms = [r['room_number'] for r in rooms if r['id'] in blocked_room_ids]

    now = datetime.now(UTC).isoformat()

    deleted_numbers: list[str] = []
    if to_delete_rooms:
        ids_to_delete = [r['id'] for r in to_delete_rooms]
        deleted_numbers = [r['room_number'] for r in to_delete_rooms]
        await db.rooms.update_many(
            {"tenant_id": current_user.tenant_id, "id": {"$in": ids_to_delete}},
            {"$set": {"is_active": False, "deleted_at": now}},
        )

    return RoomBulkDeleteResponse(
        to_delete=len(rooms),
        deleted=len(to_delete_rooms),
        blocked=len(blocked_rooms),
        blocked_rooms=blocked_rooms,
        deleted_room_numbers=deleted_numbers,
    )


@router.post("/pms/rooms/import-csv", response_model=RoomCsvImportResponse)
async def import_rooms_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_super_admin_guard(not_found=False)),
    _: None = Depends(require_module("pms")),
):
    # CSV rows limit safety
    MAX_ROWS = 2000

    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Lutfen .csv dosyasi yukleyin")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="CSV dosyasi bos")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="CSV dosyasi cok buyuk (max 2MB)")

    decoded = content.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(decoded))

    required = {'room_number', 'room_type', 'floor', 'capacity', 'base_price'}
    header = {h.strip() for h in (reader.fieldnames or []) if h}
    missing = sorted(required - header)
    if missing:
        raise HTTPException(status_code=400, detail=f"Eksik kolonlar: {', '.join(missing)}")

    existing = await db.rooms.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "room_number": 1},
    ).to_list(10000)
    existing_numbers = {r.get("room_number") for r in existing if r.get("room_number")}

    created = 0
    skipped_numbers: list[str] = []
    error_rows: list[dict[str, Any]] = []
    docs = []

    for idx, row in enumerate(reader, start=2):  # header is row 1
        if idx > MAX_ROWS + 1:
            break

        try:
            room_number = (row.get('room_number') or '').strip()
            if not room_number:
                raise ValueError('room_number bos')

            if room_number in existing_numbers:
                skipped_numbers.append(room_number)
                continue

            room_type = (row.get('room_type') or 'standard').strip() or 'standard'
            floor = int((row.get('floor') or '1').strip() or 1)
            capacity = int((row.get('capacity') or '2').strip() or 2)
            base_price = float((row.get('base_price') or '0').strip() or 0)

            view_val = (row.get('view') or '').strip() or None
            bed_type = (row.get('bed_type') or '').strip() or None

            amenities_raw = (row.get('amenities') or '').strip()
            amenities = [a.strip() for a in amenities_raw.split('|') if a.strip()] if amenities_raw else []

            room = Room(
                tenant_id=current_user.tenant_id,
                room_number=room_number,
                room_type=room_type,
                floor=floor,
                capacity=capacity,
                base_price=base_price,
                amenities=amenities,
                view=view_val,
                bed_type=bed_type,
            )
            room_dict = room.model_dump()
            room_dict['created_at'] = room_dict['created_at'].isoformat()
            docs.append(room_dict)
            existing_numbers.add(room_number)
            created += 1
        except Exception as e:
            error_rows.append({"row_number": idx, "error": str(e)})

    if docs:
        await db.rooms.insert_many(docs)

    return RoomCsvImportResponse(
        created=created,
        skipped=len(skipped_numbers),
        errors=len(error_rows),
        skipped_room_numbers=skipped_numbers,
        error_rows=error_rows[:50],
    )


@router.post("/pms/rooms/{room_id}/images")
async def upload_room_images(
    room_id: str,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    room = await db.rooms.find_one({'id': room_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    room_folder = UPLOAD_DIR / current_user.tenant_id / 'rooms' / room_id
    room_folder.mkdir(parents=True, exist_ok=True)

    saved_urls: list[str] = []
    for f in files:
        if f.content_type and not f.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail=f"Only image uploads allowed. Got: {f.content_type}")

        ext = Path(f.filename or '').suffix.lower()[:10]
        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            ext = ext if ext else '.jpg'

        filename = f"{uuid.uuid4()}{ext}"
        dest = room_folder / filename

        file_content = await f.read()
        if not file_content:
            continue
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image too large (max 10MB)")

        dest.write_bytes(file_content)
        url = f"/api/uploads/{current_user.tenant_id}/rooms/{room_id}/{filename}"
        saved_urls.append(url)

    if not saved_urls:
        return {"success": True, "uploaded": 0, "images": room.get('images', [])}

    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$push': {'images': {'$each': saved_urls}}}
    )

    updated = await db.rooms.find_one({'id': room_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    return {"success": True, "uploaded": len(saved_urls), "images": updated.get('images', [])}


@router.put("/pms/rooms/{room_id}")
async def update_room(room_id: str, updates: dict[str, Any], current_user: User = Depends(get_current_user)):
    await db.rooms.update_one({'id': room_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    room_doc = await db.rooms.find_one({'id': room_id}, {'_id': 0})
    return room_doc


@router.get("/pms/companies")
async def get_pms_companies(
    search: str | None = None,
    status: CompanyStatus | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get all companies - PMS module alias."""
    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status

    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'corporate_code': {'$regex': search, '$options': 'i'}},
        ]

    companies = await db.companies.find(query, {'_id': 0}).to_list(1000)
    return companies


# ── Virtual Rooms ──

VIRTUAL_ROOM_PREFIX = "V-"

ROOM_TYPE_VIRTUAL_MAP = {
    "Standard": "V-STD",
    "standard": "V-STD",
    "Deluxe": "V-DLX",
    "Superior": "V-SUP",
    "Suite": "V-STE",
    "Junior Suite": "V-JST",
    "Family": "V-FAM",
}


@router.post("/pms/rooms/virtual/seed")
async def seed_virtual_rooms(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Create one virtual room per room type for no-show assignments."""
    tenant_id = current_user.tenant_id

    # Get unique room types from existing rooms
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}},
        {"$group": {"_id": "$room_type"}},
    ]
    type_docs = await db.rooms.aggregate(pipeline).to_list(50)
    room_types = [t["_id"] for t in type_docs if t["_id"]]

    created = []
    skipped = []
    for rt in room_types:
        vnum = ROOM_TYPE_VIRTUAL_MAP.get(rt, f"V-{rt[:3].upper()}")
        exists = await db.rooms.find_one(
            {"tenant_id": tenant_id, "room_number": vnum, "is_virtual": True},
        )
        if exists:
            skipped.append(vnum)
            continue

        room_doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "room_number": vnum,
            "room_type": rt,
            "floor": 0,
            "capacity": 99,
            "base_price": 0,
            "status": "available",
            "amenities": [],
            "is_virtual": True,
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.rooms.insert_one({**room_doc})
        created.append(vnum)

    return {"created": created, "skipped": skipped, "total": len(created)}


@router.get("/pms/rooms/virtual")
async def get_virtual_rooms(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """List all virtual rooms for this tenant."""
    rooms = await db.rooms.find(
        {"tenant_id": current_user.tenant_id, "is_virtual": True},
        {"_id": 0},
    ).to_list(50)
    return rooms


class NoShowVirtualRequest(BaseModel):
    booking_id: str
    charge_first_night: bool = False
    no_show_reason: str | None = None  # misafir_gelmedi, iptal_gec_islendi, overbooking


@router.post("/pms/bookings/no-show-virtual")
async def no_show_to_virtual_room(
    req: NoShowVirtualRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Mark booking as no-show and assign to virtual room of matching type."""
    tenant_id = current_user.tenant_id
    booking = await db.bookings.find_one(
        {"id": req.booking_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    if booking.get("status") not in ("confirmed", "guaranteed", "no_show"):
        raise HTTPException(
            status_code=400,
            detail=f"Bu durumdaki rezervasyona no-show islemi yapilamaz: {booking.get('status')}",
        )

    room_type = booking.get("room_type", "Standard")
    vnum = ROOM_TYPE_VIRTUAL_MAP.get(room_type, f"V-{room_type[:3].upper()}")

    # Find or create virtual room
    virtual_room = await db.rooms.find_one(
        {"tenant_id": tenant_id, "room_number": vnum, "is_virtual": True},
        {"_id": 0},
    )
    if not virtual_room:
        virtual_room = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "room_number": vnum,
            "room_type": room_type,
            "floor": 0,
            "capacity": 99,
            "base_price": 0,
            "status": "available",
            "amenities": [],
            "is_virtual": True,
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.rooms.insert_one({**virtual_room})

    # Release previously assigned room if any
    old_room_id = booking.get("room_id")
    if old_room_id:
        await db.rooms.update_one(
            {"id": old_room_id},
            {"$set": {"status": "available", "current_booking_id": None}},
        )

    # Update booking
    VALID_REASONS = {"misafir_gelmedi", "iptal_gec_islendi", "overbooking"}
    reason = req.no_show_reason if req.no_show_reason in VALID_REASONS else "misafir_gelmedi"

    update_fields = {
        "room_id": virtual_room["id"],
        "status": "no_show",
        "no_show_at": datetime.now(UTC).isoformat(),
        "no_show_processed_by": current_user.name,
        "no_show_reason": reason,
    }
    await db.bookings.update_one(
        {"id": req.booking_id},
        {"$set": update_fields},
    )

    return {
        "message": "No-show islemi tamamlandi ve sanal odaya atandi",
        "booking_id": req.booking_id,
        "virtual_room": vnum,
        "virtual_room_id": virtual_room["id"],
        "no_show_reason": reason,
    }
