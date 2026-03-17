"""
PMS Router - Extracted from server.py
"""
import asyncio
import uuid
import io
import csv
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict

from core.database import db
from core.security import get_current_user
from core.helpers import (
    require_module, create_audit_log,
)
from models.enums import (
    UserRole, BookingStatus, FolioType,
    CompanyStatus, ChannelType, ContractedRateType, RateType,
    MarketSegment, CancellationPolicyType,
)
from models.schemas import (
    User, Room, RoomCreate, Guest, GuestCreate,
    Booking, BookingCreate, Folio, RateOverrideLog, RoomMoveHistory, _ensure_hotel_context,
)

try:
    from room_block_models import RoomBlockCreate
    from night_audit_module import QueueRoom
except ImportError:
    RoomBlockCreate = None
    QueueRoom = None

from core.utils import (
    generate_folio_number, generate_qr_code, generate_time_based_qr_token,
    get_cancellation_policy_details,
)
from modules.inventory.services.availability_read_service import AvailabilityReadService
from modules.inventory.services.create_room_block_service import CreateRoomBlockService
from modules.inventory.services.release_room_block_service import ReleaseRoomBlockService
from modules.reservations.services.create_reservation_service import CreateReservationService
from modules.reservations.services.reservation_read_service import ReservationReadService
from modules.reservations.services.update_reservation_service import UpdateReservationService
from shared_kernel.shadow_metrics import compare_availability_payloads, run_shadow_compare

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["pms"])
security = HTTPBearer()
create_reservation_service = CreateReservationService()
create_room_block_service = CreateRoomBlockService()
release_room_block_service = ReleaseRoomBlockService()
reservation_read_service = ReservationReadService()
update_reservation_service = UpdateReservationService()
availability_read_service = AvailabilityReadService()

# ── Local models ──

RejectReasonCode = Literal[
    "NO_AVAILABILITY", "PRICE_MISMATCH", "OVERBOOK", "POLICY", "OTHER",
]


class RejectRequest(BaseModel):
    reason_code: RejectReasonCode
    reason_note: Optional[str] = Field(default=None, max_length=500)


@router.post("/pms/rooms", response_model=Room)
async def create_room(
    room_data: RoomCreate,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    room = Room(tenant_id=current_user.tenant_id, **room_data.model_dump())
    room_dict = room.model_dump()
    room_dict['created_at'] = room_dict['created_at'].isoformat()
    await db.rooms.insert_one(room_dict)
    return room


@router.get("/pms/rooms", response_model=List[Room])
async def get_rooms(
    limit: int = 100,  # Optimized for 550+ room properties - load in batches
    offset: int = 0,
    status: Optional[str] = None,
    room_type: Optional[str] = None,
    view: Optional[str] = None,
    amenity: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Get rooms with pagination - Optimized for large properties (550+ rooms)"""
    
    # For small queries with filters, skip cache
    use_cache = (offset == 0 and not status and not room_type and not view and not amenity and limit >= 100)
    
    # Try Redis cache first (FASTEST!) - only for full list
    if use_cache:
        try:
            from redis_cache import redis_cache
            if redis_cache:
                cache_key = f"rooms:{current_user.tenant_id}:limit{limit}"
                cached = redis_cache.get(cache_key)
                if cached:
                    return cached
        except Exception:
            pass
        
        # Check pre-warmed cache second
        from cache_warmer import cache_warmer
        if cache_warmer:
            cached_data = cache_warmer.get_cached(f"rooms:{current_user.tenant_id}")
            if cached_data:
                # Process cached data quickly
                rooms = []
                for room in cached_data[:limit]:  # Apply limit to cached data
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
    query = {
        'tenant_id': current_user.tenant_id,
        '$or': [{'is_active': True}, {'is_active': {'$exists': False}}],
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
    projection = {'_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1, 'status': 1, 'floor': 1, 'capacity': 1, 'max_occupancy': 1, 'base_price': 1, 'tenant_id': 1, 'amenities': 1, 'view': 1, 'bed_type': 1, 'images': 1}
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
            pass

    return rooms




class RoomCsvImportResponse(BaseModel):
    created: int
    skipped: int
    errors: int
    skipped_room_numbers: List[str] = []
    error_rows: List[Dict[str, Any]] = []  # {row_number, error}



class RoomBulkRangeRequest(BaseModel):
    """Create many rooms quickly using a numeric range.

    Supports:
    - prefix (optional): e.g. "A" → A101, A102 ...
    - start/end inclusive
    """

    prefix: Optional[str] = None
    start_number: int
    end_number: int
    floor: int
    room_type: str
    capacity: int = 2
    base_price: float = 0
    amenities: List[str] = []
    view: Optional[str] = None
    bed_type: Optional[str] = None



class RoomBulkTemplateRequest(BaseModel):
    """Create N rooms based on a template.

    Supports prefix + starting number to auto-generate unique room_number values.
    """

    prefix: Optional[str] = None
    start_number: int = 1
    count: int
    floor: int
    room_type: str
    capacity: int = 2
    base_price: float = 0
    amenities: List[str] = []
    view: Optional[str] = None
    bed_type: Optional[str] = None



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

    ids: Optional[List[str]] = None
    room_numbers: Optional[List[str]] = None

    prefix: Optional[str] = None
    start_number: Optional[int] = None
    end_number: Optional[int] = None

    confirm_text: str



class RoomBulkDeleteResponse(BaseModel):
    to_delete: int
    deleted: int
    blocked: int
    blocked_rooms: List[str] = []
    deleted_room_numbers: List[str] = []


    rooms: List[Room] = []
    skipped_room_numbers: List[str] = []



@router.post("/pms/rooms/bulk/range", response_model=RoomBulkCreateResponse)
async def bulk_create_rooms_range(
    payload: RoomBulkRangeRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    if payload.end_number < payload.start_number:
        raise HTTPException(status_code=400, detail="end_number start_number'dan küçük olamaz")
    if payload.end_number - payload.start_number + 1 > 2000:
        raise HTTPException(status_code=400, detail="Tek seferde maksimum 2000 oda oluşturabilirsiniz")

    prefix = (payload.prefix or "").strip()

    created_rooms: List[Room] = []
    skipped: List[str] = []

    existing = await db.rooms.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "room_number": 1},
    ).to_list(5000)
    existing_numbers = set([r.get("room_number") for r in existing if r.get("room_number")])

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
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    if payload.count <= 0:
        raise HTTPException(status_code=400, detail="count 0'dan büyük olmalı")
    if payload.count > 2000:
        raise HTTPException(status_code=400, detail="Tek seferde maksimum 2000 oda oluşturabilirsiniz")

    prefix = (payload.prefix or "").strip()

    existing = await db.rooms.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "room_number": 1},
    ).to_list(5000)
    existing_numbers = set([r.get("room_number") for r in existing if r.get("room_number")])

    created_rooms: List[Room] = []
    skipped: List[str] = []
    docs = []

    current = payload.start_number
    created_count = 0
    safety = 0
    while created_count < payload.count:
        safety += 1
        if safety > payload.count + 5000:
            raise HTTPException(status_code=400, detail="Oda numarası üretiminde çok fazla çakışma oluştu")

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
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    # Permission: admin + super_admin
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if (payload.confirm_text or '').strip().upper() != 'DELETE':
        raise HTTPException(status_code=400, detail="Silme işlemini onaylamak için 'DELETE' yazmalısınız")

    target_ids = set(payload.ids or [])
    target_numbers = set([rn.strip() for rn in (payload.room_numbers or []) if rn and rn.strip()])

    if payload.start_number is not None or payload.end_number is not None:
        if payload.start_number is None or payload.end_number is None:
            raise HTTPException(status_code=400, detail="Range için start_number ve end_number zorunlu")
        if payload.end_number < payload.start_number:
            raise HTTPException(status_code=400, detail="end_number start_number'dan küçük olamaz")
        if payload.end_number - payload.start_number + 1 > 2000:
            raise HTTPException(status_code=400, detail="Tek seferde maksimum 2000 oda silebilirsiniz")

        prefix = (payload.prefix or '').strip()
        for n in range(payload.start_number, payload.end_number + 1):
            target_numbers.add(f"{prefix}{n}")

    if not target_ids and not target_numbers:
        raise HTTPException(status_code=400, detail="Silinecek oda seçilmedi")

    query: Dict[str, Any] = {
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

    blocked_room_ids = set([b.get('room_id') for b in active_bookings if b.get('room_id')])

    to_delete_rooms = [r for r in rooms if r['id'] not in blocked_room_ids]
    blocked_rooms = [r['room_number'] for r in rooms if r['id'] in blocked_room_ids]

    now = datetime.now(timezone.utc).isoformat()

    deleted_numbers: List[str] = []
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
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    # CSV rows limit safety
    MAX_ROWS = 2000

    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Lütfen .csv dosyası yükleyin")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="CSV dosyası boş")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="CSV dosyası çok büyük (max 2MB)")


    decoded = content.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(decoded))

    required = {'room_number','room_type','floor','capacity','base_price'}
    header = set([h.strip() for h in (reader.fieldnames or []) if h])
    missing = sorted(list(required - header))
    if missing:
        raise HTTPException(status_code=400, detail=f"Eksik kolonlar: {', '.join(missing)}")

    existing = await db.rooms.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "room_number": 1},
    ).to_list(10000)
    existing_numbers = set([r.get("room_number") for r in existing if r.get("room_number")])

    created = 0
    skipped_numbers: List[str] = []
    error_rows: List[Dict[str, Any]] = []
    docs = []

    for idx, row in enumerate(reader, start=2):  # header is row 1
        if idx > MAX_ROWS + 1:
            break

        try:
            room_number = (row.get('room_number') or '').strip()
            if not room_number:
                raise ValueError('room_number boş')

            if room_number in existing_numbers:
                skipped_numbers.append(room_number)
                continue

            room_type = (row.get('room_type') or 'standard').strip() or 'standard'
            floor = int((row.get('floor') or '1').strip() or 1)
            capacity = int((row.get('capacity') or '2').strip() or 2)
            base_price = float((row.get('base_price') or '0').strip() or 0)

            view = (row.get('view') or '').strip() or None
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
                view=view,
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


    return RoomBulkCreateResponse(
        created=len(created_rooms),
        skipped=len(skipped),
        rooms=created_rooms,
        skipped_room_numbers=skipped,
    )



@router.post("/pms/rooms/{room_id}/images")
async def upload_room_images(
    room_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    room = await db.rooms.find_one({'id': room_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    room_folder = UPLOAD_DIR / current_user.tenant_id / 'rooms' / room_id
    room_folder.mkdir(parents=True, exist_ok=True)

    saved_urls: List[str] = []
    for f in files:
        if f.content_type and not f.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail=f"Only image uploads allowed. Got: {f.content_type}")

        ext = Path(f.filename or '').suffix.lower()[:10]
        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            ext = ext if ext else '.jpg'

        filename = f"{uuid.uuid4()}{ext}"
        dest = room_folder / filename

        content = await f.read()
        if not content:
            continue
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image too large (max 10MB)")

        dest.write_bytes(content)
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
async def update_room(room_id: str, updates: Dict[str, Any], current_user: User = Depends(get_current_user)):
    await db.rooms.update_one({'id': room_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    room_doc = await db.rooms.find_one({'id': room_id}, {'_id': 0})
    return room_doc


@router.get("/pms/companies")
async def get_pms_companies(
    search: Optional[str] = None,
    status: Optional[CompanyStatus] = None,
    current_user: User = Depends(get_current_user)
):
    """Get all companies - PMS module alias."""
    query = {'tenant_id': current_user.tenant_id}
    
    if status:
        query['status'] = status
    
    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'corporate_code': {'$regex': search, '$options': 'i'}}
        ]
    
    companies = await db.companies.find(query, {'_id': 0}).to_list(1000)
    return companies



@router.post("/pms/guests", response_model=Guest)
async def create_guest(
    guest_data: GuestCreate,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guest = Guest(tenant_id=current_user.tenant_id, **guest_data.model_dump())
    guest_dict = guest.model_dump()
    guest_dict['created_at'] = guest_dict['created_at'].isoformat()
    await db.guests.insert_one(guest_dict)
    return guest


@router.get("/pms/guests", response_model=List[Guest])
@cached(ttl=300, key_prefix="pms_guests")  # Cache for 5 minutes
async def get_guests(
    limit: int = 1000,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guests_raw = await db.guests.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).skip(offset).limit(limit).to_list(limit)
    
    # Map database fields to model fields
    guests = []
    for guest in guests_raw:
        # Combine first_name and last_name into name if they exist
        if 'first_name' in guest and 'last_name' in guest:
            guest['name'] = f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
        elif 'name' not in guest:
            guest['name'] = guest.get('email', 'Unknown')
        
        # Use passport_number as id_number if id_number doesn't exist
        if 'id_number' not in guest and 'passport_number' in guest:
            guest['id_number'] = guest.get('passport_number', '')
        elif 'id_number' not in guest:
            guest['id_number'] = ''
        
        guests.append(guest)
    
    return guests


@router.post("/pms/bookings")
async def create_booking(
    booking_data: BookingCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    return await create_reservation_service.create(booking_data, current_user, request)


@router.get("/pms/bookings")
async def get_bookings(
    limit: int = 30,  # Further reduced for instant response
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _: None = Depends(require_module("pms")),
):
    """Get bookings - INSTANT RESPONSE"""
    current_user = await get_current_user(credentials)
    
    # Check pre-warmed cache for default query (no filters)
    if not start_date and not end_date and not status and offset == 0:
        from cache_warmer import cache_warmer
        if cache_warmer:
            cached_data = cache_warmer.get_cached(f"bookings:{current_user.tenant_id}")
            if cached_data:
                # Process and return immediately
                bookings = []
                for booking in cached_data[:limit]:
                    # Enrich guest_name if missing
                    if not booking.get('guest_name') and booking.get('guest_id'):
                        guest = await db.guests.find_one({'id': booking['guest_id']}, {'name': 1, 'first_name': 1, 'last_name': 1, '_id': 0})
                        if guest:
                            booking['guest_name'] = guest.get('name') or f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip() or 'Unknown Guest'
                    # Always enrich room_number from room document (handles room moves)
                    if booking.get('room_id'):
                        room = await db.rooms.find_one({'id': booking['room_id']}, {'room_number': 1, '_id': 0})
                        if room:
                            booking['room_number'] = room.get('room_number', 'Unknown Room')
                        elif not booking.get('room_number'):
                            booking['room_number'] = 'Unknown Room'
                    if 'rate_type' in booking:
                        rate_map = {'advance_purchase': 'promotional', 'member': 'promotional'}
                        if booking['rate_type'] in rate_map:
                            booking['rate_type'] = rate_map[booking['rate_type']]
                    if 'market_segment' in booking:
                        segment_map = {'business': 'corporate'}
                        if booking['market_segment'] in segment_map:
                            booking['market_segment'] = segment_map[booking['market_segment']]
                    bookings.append(booking)
                return bookings

    return await reservation_read_service.list_reservations(
        tenant_id=current_user.tenant_id,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
        status=status,
    )


@router.get("/bookings/{booking_id}/override-logs", response_model=List[RateOverrideLog])
@cached(ttl=600, key_prefix="booking_override_logs")  # Cache for 10 min
async def get_booking_override_logs(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get all rate override logs for a specific booking."""
    logs = await db.rate_override_logs.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('timestamp', -1).to_list(100)
    return logs


@router.post("/bookings/{booking_id}/override")

@router.post("/bookings/{booking_id}/approve")
async def approve_booking(
    booking_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Approve a pending booking (hotel-side).

    - Only bookings with status=pending can be approved
    - Idempotent: if already confirmed, returns current state
    - Ownership: booking.tenant_id must match current_user.tenant_id
    """
    _ensure_hotel_context(current_user)

    tenant_id = current_user.tenant_id

    # Lookup booking
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Idempotent: already confirmed
    if booking.get("status") == BookingStatus.CONFIRMED.value:
        return {"status": "ok", "booking": booking}

    if booking.get("status") != BookingStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Booking not in pending state: {booking.get('status')}",
        )

    now = datetime.now(timezone.utc)

    # Atomic-ish: update only if still pending
    res = await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tenant_id, "status": BookingStatus.PENDING.value},
        {"$set": {
            "status": BookingStatus.CONFIRMED.value,
            "approved_at": now,
            "approved_by_user_id": current_user.id,
            "updated_at": now,
        }},
    )

    if res.modified_count != 1:
        # Re-load and check final status
        fresh = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if fresh and fresh.get("status") == BookingStatus.CONFIRMED.value:
            return {"status": "ok", "booking": fresh}
        raise HTTPException(status_code=409, detail="Booking approval in progress")

    # Audit log (best-effort)
    try:
        await create_audit_log(
            tenant_id=tenant_id,
            user=current_user,
            action="BOOKING_APPROVED",
            entity_type="booking",
            entity_id=booking_id,
            changes={"status": BookingStatus.CONFIRMED.value},
            ip_address=request.client.host if request.client else None,
        )
    except Exception as e:
        print(f"⚠️ audit log failed (approve_booking): {e}")

    final = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"status": "ok", "booking": final, "booking_id": booking_id}



@router.post("/bookings/{booking_id}/reject")
async def reject_booking(
    booking_id: str,
    payload: RejectRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Reject a pending booking with reason.

    - Only bookings with status=pending can be rejected
    - Idempotent: if already rejected, returns current state
    - Ownership: booking.tenant_id must match current_user.tenant_id
    """
    _ensure_hotel_context(current_user)

    tenant_id = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Idempotent: already rejected
    if booking.get("status") == "rejected":
        return {"status": "ok", "booking": booking}

    if booking.get("status") == BookingStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="Booking already cancelled")

    if booking.get("status") != BookingStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Booking not in pending state: {booking.get('status')}",
        )

    now = datetime.now(timezone.utc)

    rejection_fields = {
        "status": REJECTED_STATUS,
        "rejected_at": now,
        "rejected_by_user_id": current_user.id,
        "rejection": {
            "reason_code": payload.reason_code,
            "reason_note": payload.reason_note,
        },
        "updated_at": now,
    }

    res = await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tenant_id, "status": BookingStatus.PENDING.value},
        {"$set": rejection_fields},
    )

    if res.modified_count != 1:
        fresh = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if fresh and fresh.get("status") == REJECTED_STATUS:
            return {"status": "ok", "booking": fresh}
        raise HTTPException(status_code=409, detail="Booking rejection in progress")

    try:
        await create_audit_log(
            tenant_id=tenant_id,
            user=current_user,
            action="BOOKING_REJECTED",
            entity_type="booking",
            entity_id=booking_id,
            changes={
                "status": REJECTED_STATUS,
                "reason_code": payload.reason_code,
                "reason_note": payload.reason_note,
            },
            ip_address=request.client.host if request.client else None,
        )
    except Exception as e:
        print(f"⚠️ audit log failed (reject_booking): {e}")

    final = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"status": "ok", "booking": final, "booking_id": booking_id}



@router.put("/pms/bookings/{booking_id}")
async def update_booking(
    booking_id: str,
    booking_data: dict,
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Update an existing booking while preserving the legacy response contract."""
    return await update_reservation_service.update(booking_id, booking_data, current_user, request)


@router.post("/pms/room-move-history")
async def create_room_move_history(
    move_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Log room move history for audit trail"""
    history = RoomMoveHistory(
        tenant_id=current_user.tenant_id,
        booking_id=move_data.get('booking_id'),
        old_room=move_data.get('old_room'),
        new_room=move_data.get('new_room'),
        old_check_in=move_data.get('old_check_in'),
        new_check_in=move_data.get('new_check_in'),
        reason=move_data.get('reason'),
        moved_by=move_data.get('moved_by', current_user.name)
    )
    
    history_dict = history.model_dump()
    history_dict['timestamp'] = history_dict['timestamp'].isoformat()
    
    await db.room_move_history.insert_one(history_dict)
    
    return {"message": "Room move logged successfully", "history": history}


@router.get("/pms/dashboard")
@cached(ttl=30, key_prefix="pms_dashboard")  # Cache for 30 seconds - very fast refresh
async def get_pms_dashboard(current_user: User = Depends(get_current_user)):
    # Try Redis cache first (FASTEST!)
    try:
        from redis_cache import redis_cache
        if redis_cache:
            cache_key = f"dashboard:{current_user.tenant_id}"
            cached = redis_cache.get(cache_key)
            if cached:
                return cached
    except Exception:
        pass
    
    # Check pre-warmed cache second
    from cache_warmer import cache_warmer
    if cache_warmer:
        cached_data = cache_warmer.get_cached(f"dashboard:{current_user.tenant_id}")
        if cached_data:
            return cached_data
    
    # Fallback: Ultra-fast aggregation
    pipeline = [
        {'$match': {'tenant_id': current_user.tenant_id}},
        {'$group': {
            '_id': None,
            'total_rooms': {'$sum': 1},
            'occupied_rooms': {'$sum': {'$cond': [{'$eq': ['$status', 'occupied']}, 1, 0]}}
        }}
    ]
    
    room_stats = await db.rooms.aggregate(pipeline).to_list(1)
    total_rooms = room_stats[0]['total_rooms'] if room_stats else 0
    occupied_rooms = room_stats[0]['occupied_rooms'] if room_stats else 0
    
    # Ultra-fast response - minimal queries
    result = {
        'total_rooms': total_rooms,
        'occupied_rooms': occupied_rooms,
        'available_rooms': total_rooms - occupied_rooms,
        'occupancy_rate': round((occupied_rooms / total_rooms * 100), 2) if total_rooms > 0 else 0,
        'today_checkins': 0,  # Skip for max speed
        'total_guests': 0  # Skip for max speed
    }
    
    # Cache in Redis for 5 seconds
    try:
        from redis_cache import redis_cache
        if redis_cache:
            cache_key = f"dashboard:{current_user.tenant_id}"
            redis_cache.set(cache_key, result, ttl=5)
    except Exception:
        pass
    
    return result


@router.get("/pms/room-services")
@cached(ttl=300, key_prefix="pms_room_services")  # Cache for 5 min
async def get_hotel_room_services(current_user: User = Depends(get_current_user)):
    services = await db.room_services.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return services


@router.put("/pms/room-services/{service_id}")
async def update_room_service(service_id: str, updates: Dict[str, Any], current_user: User = Depends(get_current_user)):
    if 'status' in updates and updates['status'] == 'completed':
        updates['completed_at'] = datetime.now(timezone.utc).isoformat()
    await db.room_services.update_one({'id': service_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    service = await db.room_services.find_one({'id': service_id}, {'_id': 0})
    return service


@router.get("/pms/room-blocks")
async def get_room_blocks(
    room_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get room blocks with optional filters"""
    query = {'tenant_id': current_user.tenant_id}
    
    if room_id:
        query['room_id'] = room_id
    
    if status:
        query['status'] = status
    
    if from_date or to_date:
        date_query = {}
        if from_date:
            date_query['$gte'] = from_date
        if to_date:
            date_query['$lte'] = to_date
        query['start_date'] = date_query
    
    blocks = await db.room_blocks.find(query, {'_id': 0}).to_list(1000)
    
    # Filter expired blocks
    today = datetime.now(timezone.utc).date().isoformat()
    for block in blocks:
        if block.get('end_date') and block['end_date'] < today and block['status'] == 'active':
            # Auto-expire
            await db.room_blocks.update_one(
                {'id': block['id']},
                {'$set': {'status': 'expired'}}
            )
            block['status'] = 'expired'
    
    return blocks


@router.post("/pms/room-blocks")
async def create_room_block(
    block_data: dict,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    payload = RoomBlockCreate(**block_data)
    return await create_room_block_service.create(payload, current_user, request)


@router.patch("/pms/room-blocks/{block_id}")
async def update_room_block(
    block_id: str,
    updates: dict,
    current_user: User = Depends(get_current_user)
):
    """Update a room block"""
    existing = await db.room_blocks.find_one({
        'tenant_id': current_user.tenant_id,
        'id': block_id
    })
    
    if not existing:
        raise HTTPException(404, "Block not found")
    
    # Only allow updates to active blocks
    if existing['status'] != 'active':
        raise HTTPException(400, "Cannot update cancelled or expired blocks")
    
    update_data = {}
    allowed_fields = ['reason', 'details', 'start_date', 'end_date', 'allow_sell']
    
    for field in allowed_fields:
        if field in updates:
            update_data[field] = updates[field]
    
    if update_data:
        await db.room_blocks.update_one(
            {'id': block_id},
            {'$set': update_data}
        )
        
        # Audit log
        await db.audit_logs.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'action': 'room_block_updated',
            'entity_type': 'room_block',
            'entity_id': block_id,
            'user': current_user.name,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'details': update_data
        })
    
    updated = await db.room_blocks.find_one({'id': block_id}, {'_id': 0})
    return updated


@router.post("/pms/room-blocks/{block_id}/cancel")
async def cancel_room_block(
    block_id: str,
    request: Request,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Release a room block through the semantic inventory service."""
    return await release_room_block_service.release(block_id, current_user, request, reason=reason)


@router.get("/pms/rooms/availability")
@cached(ttl=120, key_prefix="rooms_availability")  # Cache for 2 min
async def check_room_availability(
    check_in: str,
    check_out: str,
    request: Request,
    room_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Check room availability including blocks"""
    semantic_response = await availability_read_service.get_availability(
        tenant_id=current_user.tenant_id,
        check_in=check_in,
        check_out=check_out,
        room_type=room_type,
    )
    asyncio.create_task(
        run_shadow_compare(
            endpoint="availability",
            tenant_id=current_user.tenant_id,
            property_id=request.headers.get("x-property-id"),
            correlation_id=request.headers.get("x-correlation-id"),
            semantic_payload=semantic_response,
            legacy_loader=lambda: _legacy_check_room_availability(
                tenant_id=current_user.tenant_id,
                check_in=check_in,
                check_out=check_out,
                room_type=room_type,
            ),
            comparator=compare_availability_payloads,
            entity_id=f"{check_in}:{check_out}:{room_type or '*'}",
        )
    )
    return semantic_response


async def _legacy_check_room_availability(
    tenant_id: str,
    check_in: str,
    check_out: str,
    room_type: Optional[str] = None,
):
    query = {'tenant_id': tenant_id}

    if room_type:
        query['room_type'] = room_type

    rooms = await db.rooms.find(query, {'_id': 0}).to_list(1000)
    bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'status': {'$in': ['confirmed', 'checked_in', 'guaranteed']},
        'check_in': {'$lt': check_out},
        'check_out': {'$gt': check_in}
    }, {'_id': 0}).to_list(1000)
    blocks = await db.room_blocks.find({
        'tenant_id': tenant_id,
        'status': 'active',
        'start_date': {'$lt': check_out},
        '$or': [
            {'end_date': {'$gt': check_in}},
            {'end_date': None}
        ]
    }, {'_id': 0}).to_list(1000)

    available = []
    for room in rooms:
        is_booked = any(b['room_id'] == room['id'] for b in bookings)
        room_blocks = [b for b in blocks if b['room_id'] == room['id']]
        is_blocked = any(not b.get('allow_sell', False) for b in room_blocks)

        if not is_booked and not is_blocked:
            available.append({
                **room,
                'available': True
            })
        else:
            unavailable_reason = []
            if is_booked:
                unavailable_reason.append('booked')
            if is_blocked:
                block_info = [b for b in room_blocks if not b.get('allow_sell')]
                if block_info:
                    unavailable_reason.append(f"{block_info[0]['type']}")

            available.append({
                **room,
                'available': False,
                'reason': ', '.join(unavailable_reason),
                'blocks': room_blocks
            })

    return available


@router.get("/pms/staff-tasks")
async def get_staff_tasks(
    department: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get staff tasks (engineering, housekeeping, maintenance)"""
    query = {'tenant_id': current_user.tenant_id}
    if department:
        query['department'] = department
    if status:
        query['status'] = status
    
    tasks = await db.staff_tasks.find(query, {'_id': 0}).sort('created_at', -1).to_list(1000)
    return tasks


@router.post("/pms/staff-tasks")
async def create_staff_task(
    task_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create a new staff task"""
    task = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_type': task_data.get('task_type', 'maintenance'),
        'department': task_data.get('department', 'engineering'),
        'title': task_data.get('title', 'Staff Task'),
        'room_id': task_data.get('room_id'),
        'priority': task_data.get('priority', 'normal'),
        'description': task_data.get('description'),
        'assigned_to': task_data.get('assigned_to'),
        'status': task_data.get('status', 'pending'),
        'created_by': current_user.id,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    # Get room number if room_id provided
    if task['room_id']:
        room = await db.rooms.find_one({'id': task['room_id']}, {'_id': 0, 'room_number': 1})
        if room:
            task['room_number'] = room['room_number']
    
    await db.staff_tasks.insert_one(task)
    
    # Return the task without MongoDB ObjectId
    return {
        'id': task['id'],
        'tenant_id': task['tenant_id'],
        'task_type': task['task_type'],
        'department': task['department'],
        'title': task['title'],
        'room_id': task['room_id'],
        'room_number': task.get('room_number'),
        'priority': task['priority'],
        'description': task['description'],
        'assigned_to': task['assigned_to'],
        'status': task['status'],
        'created_by': task['created_by'],
        'created_at': task['created_at']
    }


@router.put("/pms/staff-tasks/{task_id}")
async def update_staff_task(
    task_id: str,
    update_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update staff task status"""
    await db.staff_tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )
    
    # Return updated task
    updated_task = await db.staff_tasks.find_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )
    
    if not updated_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return updated_task


@router.get("/pms/allotment-contracts")
async def get_allotment_contracts(
    current_user: User = Depends(get_current_user)
):
    """Get tour operator allotment contracts with dynamic usage count"""
    contracts = await db.allotment_contracts.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    # Dynamically calculate used_rooms from active bookings
    ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]
    for contract in contracts:
        room_type = contract.get('room_type')
        start_date = contract.get('start_date')
        end_date = contract.get('end_date')
        if room_type and start_date and end_date:
            # Find rooms of this type
            room_ids = []
            async for room in db.rooms.find(
                {"tenant_id": current_user.tenant_id, "room_type": room_type},
                {"_id": 0, "id": 1}
            ):
                room_ids.append(room["id"])

            if room_ids:
                used = await db.bookings.count_documents({
                    "tenant_id": current_user.tenant_id,
                    "room_id": {"$in": room_ids},
                    "status": {"$in": ACTIVE_STATUSES},
                    "check_in": {"$lt": end_date},
                    "check_out": {"$gt": start_date},
                })
                contract['used_rooms'] = used

    return contracts


@router.post("/pms/allotment-contracts")
async def create_allotment_contract(
    contract_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create new allotment contract"""
    contract = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'tour_operator': contract_data.get('tour_operator'),
        'room_type': contract_data.get('room_type'),
        'allocated_rooms': contract_data.get('allocated_rooms'),
        'used_rooms': 0,
        'start_date': contract_data.get('start_date'),
        'end_date': contract_data.get('end_date'),
        'rate': contract_data.get('rate'),
        'release_days': contract_data.get('release_days', 7),
        'status': 'active',
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.allotment_contracts.insert_one(contract)
    return contract


@router.post("/pms/allotment-contracts/{contract_id}/release")
async def release_allotment_rooms(
    contract_id: str,
    current_user: User = Depends(get_current_user)
):
    """Release unused allotment rooms back to inventory"""
    contract = await db.allotment_contracts.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    available_rooms = contract['allocated_rooms'] - contract.get('used_rooms', 0)
    
    await db.allotment_contracts.update_one(
        {'id': contract_id},
        {'$set': {
            'released_rooms': available_rooms,
            'released_at': datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "message": f"Released {available_rooms} rooms",
        "released_rooms": available_rooms
    }


@router.get("/pms/group-reservations")
async def get_group_reservations(current_user: User = Depends(get_current_user)):
    groups = await db.group_reservations.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
    return {'groups': groups}


@router.post("/pms/group-reservations")
async def create_group_reservation(
    group_data: dict,
    current_user: User = Depends(get_current_user)
):
    group = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        **group_data,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.group_reservations.insert_one(group)
    return group


@router.get("/pms/setup-status")
async def pms_setup_status(current_user: User = Depends(get_current_user)):
    """Return minimal setup status for PMS Lite onboarding (rooms/bookings counts)."""
    rooms_count = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id})
    return {"rooms_count": rooms_count, "bookings_count": bookings_count}



class RoomNote(BaseModel):
    """Room-specific notes"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    note_type: str  # maintenance, issue, preference, general
    description: str
    priority: str = "normal"
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class MiniBarUpdate(BaseModel):
    """Mini-bar last update tracking"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    updated_by: str
    items_restocked: Dict[str, int] = {}  # {item_name: quantity}
    items_consumed: Dict[str, int] = {}
    total_value: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.get("/rooms/{room_id}/details-enhanced")
@cached(ttl=180, key_prefix="room_details_enhanced")  # Cache for 3 min
async def get_room_details_enhanced(
    room_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get enhanced room details including:
    - Room notes (TV issues, pillow requests, etc)
    - Mini-bar last update
    - Next maintenance due
    """
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Get room notes
    notes = []
    async for note in db.room_notes.find({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id,
        'resolved': False
    }).sort('created_at', -1).limit(10):
        notes.append({
            'id': note.get('id'),
            'note_type': note.get('note_type'),
            'description': note.get('description'),
            'priority': note.get('priority'),
            'created_by': note.get('created_by'),
            'created_at': note.get('created_at')
        })
    
    # Get mini-bar last update
    minibar_update = await db.minibar_updates.find_one({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id
    }, sort=[('updated_at', -1)])
    
    minibar_info = None
    if minibar_update:
        updated_at = datetime.fromisoformat(minibar_update.get('updated_at'))
        hours_ago = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
        
        minibar_info = {
            'last_updated': minibar_update.get('updated_at'),
            'hours_ago': round(hours_ago, 1),
            'updated_by': minibar_update.get('updated_by'),
            'items_restocked': minibar_update.get('items_restocked', {}),
            'items_consumed': minibar_update.get('items_consumed', {}),
            'total_value': minibar_update.get('total_value', 0.0),
            'needs_restock': hours_ago > 24
        }
    
    # Get next maintenance due
    next_maintenance = await db.maintenance_schedule.find_one({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['scheduled', 'pending']},
        'scheduled_date': {'$gte': datetime.now(timezone.utc).isoformat()}
    }, sort=[('scheduled_date', 1)])
    
    maintenance_info = None
    if next_maintenance:
        scheduled_date = datetime.fromisoformat(next_maintenance.get('scheduled_date'))
        days_until = (scheduled_date - datetime.now(timezone.utc)).days
        
        maintenance_info = {
            'scheduled_date': next_maintenance.get('scheduled_date'),
            'days_until': days_until,
            'maintenance_type': next_maintenance.get('maintenance_type'),
            'description': next_maintenance.get('description'),
            'priority': next_maintenance.get('priority'),
            'is_overdue': days_until < 0
        }
    
    return {
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'room_type': room.get('room_type'),
        'status': room.get('status'),
        'notes': notes,
        'notes_count': len(notes),
        'minibar': minibar_info,
        'next_maintenance': maintenance_info,
        'alerts': [
            f"⚠️ {len(notes)} unresolved room notes" if notes else "✅ No outstanding room issues",
            "🍷 Mini-bar needs restock" if minibar_info and minibar_info.get('needs_restock') else None,
            f"🔧 Maintenance due in {maintenance_info['days_until']} days" if maintenance_info and maintenance_info['days_until'] <= 7 else None,
            "🚨 Maintenance OVERDUE!" if maintenance_info and maintenance_info.get('is_overdue') else None
        ]
    }



@router.post("/rooms/{room_id}/notes")
async def add_room_note(
    room_id: str,
    note_type: str,
    description: str,
    priority: str = "normal",
    current_user: User = Depends(get_current_user)
):
    """Add a note to a room"""
    note = RoomNote(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        note_type=note_type,
        description=description,
        priority=priority,
        created_by=current_user.name
    )
    
    note_dict = note.model_dump()
    note_dict['created_at'] = note_dict['created_at'].isoformat()
    await db.room_notes.insert_one(note_dict)
    
    return {'success': True, 'note_id': note.id, 'message': 'Room note added'}



@router.post("/rooms/{room_id}/minibar-update")
async def update_minibar(
    room_id: str,
    items_restocked: Dict[str, int] = {},
    items_consumed: Dict[str, int] = {},
    total_value: float = 0.0,
    current_user: User = Depends(get_current_user)
):
    """Update mini-bar status"""
    update = MiniBarUpdate(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        updated_by=current_user.name,
        items_restocked=items_restocked,
        items_consumed=items_consumed,
        total_value=total_value
    )
    
    update_dict = update.model_dump()
    update_dict['updated_at'] = update_dict['updated_at'].isoformat()
    await db.minibar_updates.insert_one(update_dict)
    
    return {'success': True, 'update_id': update.id, 'message': 'Mini-bar updated'}



@router.get("/reservations/{booking_id}/details-enhanced")
async def get_reservation_details_enhanced(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Enhanced reservation details showing:
    - Cancellation policy
    - OTA commission info
    - Rate breakdown
    """
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not booking:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    # Cancellation policy details
    policy = booking.get('cancellation_policy', CancellationPolicyType.H24)
    policy_details = get_cancellation_policy_details(policy)
    
    # OTA commission
    commission_info = None
    if booking.get('ota_channel'):
        commission_pct = booking.get('commission_pct', 15.0)
        total_amount = booking.get('total_amount', 0)
        commission_amount = total_amount * (commission_pct / 100)
        net_revenue = total_amount - commission_amount
        
        commission_info = {
            'ota_channel': booking.get('ota_channel'),
            'ota_confirmation': booking.get('ota_confirmation'),
            'commission_pct': commission_pct,
            'commission_amount': round(commission_amount, 2),
            'gross_revenue': round(total_amount, 2),
            'net_revenue': round(net_revenue, 2),
            'payment_model': booking.get('payment_model')
        }
    
    return {
        'booking_id': booking_id,
        'status': booking.get('status'),
        'cancellation_policy': {
            'type': policy,
            **policy_details
        },
        'commission': commission_info,
        'rate_breakdown': {
            'base_rate': booking.get('base_rate'),
            'total_amount': booking.get('total_amount'),
            'rate_type': booking.get('rate_type'),
            'market_segment': booking.get('market_segment')
        }
    }



@router.get("/reservations/double-booking-check")
async def check_double_booking_conflicts(
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Double-booking conflict detection engine
    - Identify potential conflicts
    - Room assignment overlaps
    """
    target_date = date or datetime.now().date().isoformat()
    
    # Get all bookings for the date
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lte': target_date},
        'check_out': {'$gte': target_date}
    }):
        bookings.append(booking)
    
    # Group by room
    room_bookings = {}
    for booking in bookings:
        room_id = booking.get('room_id')
        if room_id not in room_bookings:
            room_bookings[room_id] = []
        room_bookings[room_id].append(booking)
    
    # Find conflicts
    conflicts = []
    for room_id, room_booking_list in room_bookings.items():
        if len(room_booking_list) > 1:
            # Potential conflict
            room = await db.rooms.find_one({'id': room_id})
            conflicts.append({
                'room_id': room_id,
                'room_number': room.get('room_number') if room else 'Unknown',
                'booking_count': len(room_booking_list),
                'bookings': [{
                    'booking_id': b.get('id'),
                    'guest_id': b.get('guest_id'),
                    'check_in': b.get('check_in'),
                    'check_out': b.get('check_out'),
                    'status': b.get('status')
                } for b in room_booking_list]
            })
    
    return {
        'date': target_date,
        'total_conflicts': len(conflicts),
        'conflicts': conflicts,
        'status': 'conflicts_found' if conflicts else 'no_conflicts'
    }



@router.get("/reservations/adr-visibility")
async def get_adr_and_rate_visibility(
    start_date: str,
    end_date: str,
    room_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    ADR (Average Daily Rate) and rate code visibility
    - Daily ADR
    - By rate code
    - By room type
    """
    # Get all bookings in date range
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': start_date,
            '$lte': end_date
        }
    }):
        bookings.append(booking)
    
    # Calculate ADR
    total_room_revenue = sum(b.get('total_amount', 0) for b in bookings)
    total_room_nights = sum(
        (datetime.fromisoformat(b.get('check_out')) - datetime.fromisoformat(b.get('check_in'))).days
        for b in bookings
    )
    
    adr = total_room_revenue / total_room_nights if total_room_nights > 0 else 0
    
    # By rate type
    rate_breakdown = {}
    for booking in bookings:
        rate_type = booking.get('rate_type', 'bar')
        if rate_type not in rate_breakdown:
            rate_breakdown[rate_type] = {
                'bookings': 0,
                'revenue': 0
            }
        rate_breakdown[rate_type]['bookings'] += 1
        rate_breakdown[rate_type]['revenue'] += booking.get('total_amount', 0)
    
    # Calculate ADR per rate type
    for rate_type, data in rate_breakdown.items():
        data['adr'] = round(data['revenue'] / data['bookings'], 2) if data['bookings'] > 0 else 0
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'overall_adr': round(adr, 2),
        'total_room_revenue': round(total_room_revenue, 2),
        'total_room_nights': total_room_nights,
        'total_bookings': len(bookings),
        'rate_breakdown': rate_breakdown
    }



@router.post("/reservations/rate-override-panel")
async def create_rate_override_with_panel(
    booking_id: str,
    new_rate: float,
    override_reason: str,
    authorized_by: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Rate override panel with authorization tracking
    - Manager approval required
    - Reason tracking
    - Audit trail
    """
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    original_rate = booking.get('total_amount', 0)
    
    # Create override log
    override_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'user_id': current_user.id,
        'user_name': current_user.name,
        'original_rate': original_rate,
        'new_rate': new_rate,
        'override_reason': override_reason,
        'authorized_by': authorized_by or current_user.name,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    await db.rate_override_logs.insert_one(override_log)
    
    # Update booking
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'total_amount': new_rate,
            'base_rate': original_rate,
            'override_reason': override_reason
        }}
    )
    
    # Create audit log
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="RATE_OVERRIDE",
        entity_type="booking",
        entity_id=booking_id,
        changes={
            'original_rate': original_rate,
            'new_rate': new_rate,
            'reason': override_reason
        }
    )
    
    return {
        'success': True,
        'booking_id': booking_id,
        'original_rate': original_rate,
        'new_rate': new_rate,
        'override_id': override_log['id'],
        'message': 'Rate override applied successfully'
    }



class BookingSourceType(str, Enum):
    OTA = "ota"
    WEBSITE = "website"
    CORPORATE = "corporate"
    WALK_IN = "walk_in"
    PHONE = "phone"
    AGENT = "agent"


class ExtraCharge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    booking_id: str
    tenant_id: str
    charge_name: str
    charge_amount: float
    charge_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class MultiRoomBooking(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    group_name: str
    primary_booking_id: str
    related_booking_ids: List[str] = []
    total_rooms: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.get("/reservations/{booking_id}/ota-details")
async def get_ota_reservation_details(
    booking_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get detailed OTA reservation information including special requests, multi-room, source, extra charges"""
    current_user = await get_current_user(credentials)
    
    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Get extra charges
    extra_charges = []
    async for charge in db.extra_charges.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }):
        # Remove MongoDB _id field to avoid serialization issues
        if '_id' in charge:
            del charge['_id']
        extra_charges.append(charge)
    
    # Check if part of multi-room reservation
    multi_room_info = None
    multi_room = await db.multi_room_bookings.find_one({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'primary_booking_id': booking_id},
            {'related_booking_ids': booking_id}
        ]
    })
    
    if multi_room:
        # Get all related bookings
        related_bookings = []
        all_booking_ids = [multi_room['primary_booking_id']] + multi_room.get('related_booking_ids', [])
        async for related_booking in db.bookings.find({
            'id': {'$in': all_booking_ids},
            'tenant_id': current_user.tenant_id
        }):
            # Get room info
            room = await db.rooms.find_one({'id': related_booking['room_id'], 'tenant_id': current_user.tenant_id})
            related_bookings.append({
                'booking_id': related_booking['id'],
                'room_number': room.get('room_number') if room else 'N/A',
                'guest_name': await get_guest_name(related_booking['guest_id'], current_user.tenant_id)
            })
        
        multi_room_info = {
            'group_name': multi_room.get('group_name'),
            'total_rooms': multi_room.get('total_rooms'),
            'related_bookings': related_bookings
        }
    
    # Determine source of booking
    source_of_booking = BookingSourceType.WEBSITE.value  # Default
    if booking.get('ota_channel'):
        source_of_booking = BookingSourceType.OTA.value
    elif booking.get('company_id'):
        source_of_booking = BookingSourceType.CORPORATE.value
    elif booking.get('channel') == 'walk_in':
        source_of_booking = BookingSourceType.WALK_IN.value
    elif booking.get('channel') == 'phone':
        source_of_booking = BookingSourceType.PHONE.value
    
    return {
        'booking_id': booking_id,
        'special_requests': booking.get('special_requests', ''),
        'remarks': booking.get('notes', ''),
        'source_of_booking': source_of_booking,
        'ota_channel': booking.get('ota_channel'),
        'ota_confirmation': booking.get('ota_confirmation'),
        'extra_charges': extra_charges,
        'multi_room_info': multi_room_info,
        'commission_pct': booking.get('commission_pct'),
        'payment_model': booking.get('payment_model')
    }


class ExtraChargeCreate(BaseModel):
    charge_name: str
    charge_amount: float
    notes: Optional[str] = None


@router.post("/reservations/{booking_id}/extra-charges")
async def add_extra_charge(
    booking_id: str,
    data: ExtraChargeCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Add an extra charge to a reservation"""
    current_user = await get_current_user(credentials)
    
    # Verify booking exists
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Create extra charge
    extra_charge = ExtraCharge(
        booking_id=booking_id,
        tenant_id=current_user.tenant_id,
        charge_name=data.charge_name,
        charge_amount=data.charge_amount,
        notes=data.notes
    )
    
    await db.extra_charges.insert_one(extra_charge.model_dump())
    
    return {
        'success': True,
        'message': 'Extra charge added successfully',
        'extra_charge': extra_charge.model_dump()
    }


class MultiRoomReservationCreate(BaseModel):
    group_name: str
    primary_booking_id: str
    related_booking_ids: List[str]


@router.post("/reservations/multi-room")
async def create_multi_room_reservation(
    data: MultiRoomReservationCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Link multiple bookings as a multi-room reservation"""
    current_user = await get_current_user(credentials)
    
    # Create multi-room booking record
    multi_room = MultiRoomBooking(
        tenant_id=current_user.tenant_id,
        group_name=data.group_name,
        primary_booking_id=data.primary_booking_id,
        related_booking_ids=data.related_booking_ids,
        total_rooms=len(data.related_booking_ids) + 1
    )
    
    await db.multi_room_bookings.insert_one(multi_room.model_dump())
    
    return {
        'success': True,
        'message': 'Multi-room reservation created',
        'multi_room_id': multi_room.id
    }


class MultiRoomBookingCreate(BaseModel):
    guest_id: Optional[str] = None
    guest: Optional[GuestCreate] = None
    arrival_date: str
    departure_date: str
    rooms: List[dict]
    company_id: Optional[str] = None
    channel: ChannelType = ChannelType.DIRECT
    special_requests: Optional[str] = None
    # Corporate / contracted booking fields (applied to all rooms in this group)
    contracted_rate: Optional[ContractedRateType] = None
    rate_type: Optional[RateType] = None
    market_segment: Optional[MarketSegment] = None
    cancellation_policy: Optional[CancellationPolicyType] = None
    billing_address: Optional[str] = None
    billing_tax_number: Optional[str] = None
    billing_contact_person: Optional[str] = None


@router.post("/pms/bookings/multi-room", response_model=List[Booking])
async def create_multi_room_booking(
    payload: MultiRoomBookingCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a multi-room booking under one group_booking_id.

    - If guest_id is not provided but guest info is, creates the guest first.
    - Creates one Booking per room and links them with group_booking_id.
    - Auto-creates folio for each booking (same behavior as single booking).
    """
    # Resolve guest
    guest_id = payload.guest_id
    if not guest_id and payload.guest:
        guest = Guest(
            tenant_id=current_user.tenant_id,
            **payload.guest.model_dump()
        )
        guest_dict = guest.model_dump()
        guest_dict["created_at"] = guest_dict["created_at"].isoformat()
        await db.guests.insert_one(guest_dict)
        guest_id = guest.id

    if not guest_id:
        raise HTTPException(status_code=400, detail="guest_id or guest details must be provided")

    check_in_dt = datetime.fromisoformat(payload.arrival_date.replace("Z", "+00:00"))
    check_out_dt = datetime.fromisoformat(payload.departure_date.replace("Z", "+00:00"))

    group_id = str(uuid.uuid4())
    created_bookings: List[Booking] = []

    for room_data in payload.rooms:
        room_id = room_data.get("room_id")
        if not room_id:
            raise HTTPException(status_code=400, detail="room_id is required for each room")

        adults = int(room_data.get("adults", 1))
        children = int(room_data.get("children", 0))
        children_ages = room_data.get("children_ages", [])
        total_amount = float(room_data.get("total_amount", 0.0))
        base_rate = room_data.get("base_rate")
        rate_plan = room_data.get("rate_plan")
        package_code = room_data.get("package_code")

        booking = Booking(
            tenant_id=current_user.tenant_id,
            guest_id=guest_id,
            room_id=room_id,
            check_in=check_in_dt,
            check_out=check_out_dt,
            adults=adults,
            children=children,
            children_ages=children_ages,
            guests_count=adults + children,
            total_amount=total_amount,
            base_rate=base_rate,
            channel=payload.channel,
            rate_plan=rate_plan,
            special_requests=payload.special_requests,
            company_id=payload.company_id,
            # Apply corporate / contracted booking attributes from payload
            contracted_rate=payload.contracted_rate,
            rate_type=payload.rate_type,
            market_segment=payload.market_segment,
            cancellation_policy=payload.cancellation_policy,
            group_booking_id=group_id,
        )

        # Attach basic package info as note if provided
        if package_code:
            note = f"Package: {package_code}"
            booking.special_requests = f"{booking.special_requests} | {note}" if booking.special_requests else note

        qr_token = generate_time_based_qr_token(booking.id, expiry_hours=72)
        qr_data = f"booking:{booking.id}:token:{qr_token}"
        qr_code = generate_qr_code(qr_data)
        booking.qr_code = qr_code
        booking.qr_code_data = qr_token

        booking_dict = booking.model_dump()
        booking_dict["check_in"] = booking_dict["check_in"].isoformat()
        booking_dict["check_out"] = booking_dict["check_out"].isoformat()
        booking_dict["created_at"] = booking_dict["created_at"].isoformat()
        await db.bookings.insert_one(booking_dict)

        folio_number = await generate_folio_number(current_user.tenant_id)
        folio = Folio(
            tenant_id=current_user.tenant_id,
            booking_id=booking.id,
            folio_number=folio_number,
            folio_type=FolioType.GUEST,
            guest_id=guest_id,
        )
        folio_dict = folio.model_dump()
        folio_dict["created_at"] = folio_dict["created_at"].isoformat()
        await db.folios.insert_one(folio_dict)

        created_bookings.append(booking)

    return created_bookings



@router.get("/reservations/search")
async def search_reservations(
    query: str = None,
    check_in: str = None,
    check_out: str = None,
    status: str = None,
    booking_id: str = None,
    phone: str = None,
    email: str = None,
    current_user: User = Depends(get_current_user)
):
    """
    Comprehensive reservation search with multiple filters
    Search by: guest name, booking ID, phone, email, date range, status
    """
    try:
        filter_dict = {'tenant_id': current_user.tenant_id}
        
        # Search conditions
        search_conditions = []
        
        if query:
            # Search in guest name or booking ID
            search_conditions.append({
                '$or': [
                    {'guest_name': {'$regex': query, '$options': 'i'}},
                    {'id': {'$regex': query, '$options': 'i'}},
                    {'booking_number': {'$regex': query, '$options': 'i'}}
                ]
            })
        
        if booking_id:
            search_conditions.append({'id': booking_id})
        
        if phone:
            # Find guest by phone first
            guest = await db.guests.find_one({'phone': {'$regex': phone, '$options': 'i'}})
            if guest:
                search_conditions.append({'guest_id': guest['id']})
        
        if email:
            # Find guest by email first
            guest = await db.guests.find_one({'email': {'$regex': email, '$options': 'i'}})
            if guest:
                search_conditions.append({'guest_id': guest['id']})
        
        if check_in:
            search_conditions.append({'check_in': {'$gte': check_in}})
        
        if check_out:
            search_conditions.append({'check_out': {'$lte': check_out}})
        
        if status:
            search_conditions.append({'status': status})
        
        # Combine all conditions
        if search_conditions:
            filter_dict['$and'] = search_conditions
        
        # Find bookings
        bookings = await db.bookings.find(filter_dict).sort('check_in', -1).limit(50).to_list(50)
        
        # Enrich with guest and room data
        for booking in bookings:
            if booking.get('guest_id'):
                guest = await db.guests.find_one({'id': booking['guest_id']})
                if guest:
                    booking['guest_phone'] = guest.get('phone')
                    booking['guest_email'] = guest.get('email')
            
            if booking.get('room_id'):
                room = await db.rooms.find_one({'id': booking['room_id']})
                if room:
                    booking['room_number'] = room.get('room_number')
                    booking['room_type'] = room.get('room_type')
        
        return {
            'bookings': bookings,
            'count': len(bookings),
            'search_query': query,
            'filters_applied': {
                'check_in': check_in,
                'check_out': check_out,
                'status': status,
                'phone': phone,
                'email': email
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")



@router.post("/rooms/queue/add")
async def add_to_room_queue(
    queue_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Add guest to room queue (early arrival waiting list)"""
    current_user = await get_current_user(credentials)
    
    # Verify booking
    booking = await db.bookings.find_one({
        'id': queue_data['booking_id'],
        'tenant_id': current_user.tenant_id
    })
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Get guest info
    guest = await db.guests.find_one({'id': booking['guest_id']})
    
    # Determine priority
    priority = 5
    if guest and guest.get('vip_status'):
        priority = 1
    elif guest and guest.get('loyalty_tier') in ['gold', 'platinum']:
        priority = 2
    elif queue_data.get('priority'):
        priority = queue_data['priority']
    
    queue_entry = QueueRoom(
        tenant_id=current_user.tenant_id,
        booking_id=queue_data['booking_id'],
        guest_name=guest.get('name', 'Unknown') if guest else 'Unknown',
        room_type=booking.get('room_type', 'Standard'),
        priority=priority,
        requested_room=queue_data.get('requested_room'),
        arrival_time=queue_data.get('arrival_time'),
        special_requests=queue_data.get('special_requests'),
        vip_status=guest.get('vip_status', False) if guest else False
    )
    
    await db.room_queue.insert_one(queue_entry.model_dump())
    
    return {
        'success': True,
        'queue_id': queue_entry.id,
        'priority': priority,
        'message': f"{queue_entry.guest_name} added to room queue with priority {priority}"
    }


@router.get("/rooms/queue/list")
async def get_room_queue(
    status: str = "waiting",
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get room queue list sorted by priority"""
    current_user = await get_current_user(credentials)
    
    queue = await db.room_queue.find({
        'tenant_id': current_user.tenant_id,
        'status': status
    }, {'_id': 0}).sort('priority', 1).to_list(1000)
    
    # Get available rooms for assignment
    available_rooms = await db.rooms.find({
        'tenant_id': current_user.tenant_id,
        'status': 'available',
        'housekeeping_status': 'clean'
    }, {'_id': 0}).to_list(1000)
    
    return {
        'queue': queue,
        'queue_length': len(queue),
        'available_rooms': len(available_rooms),
        'recommendations': [
            {
                'queue_entry': q,
                'suggested_room': next((r for r in available_rooms if r['room_type'] == q['room_type']), None)
            }
            for q in queue[:10]
        ]
    }


@router.post("/rooms/queue/assign-priority")
async def assign_queue_priority(
    queue_id: str,
    priority: int,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Manually assign priority to queue entry"""
    current_user = await get_current_user(credentials)
    
    if priority < 1 or priority > 10:
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 10")
    
    result = await db.room_queue.update_one(
        {
            'id': queue_id,
            'tenant_id': current_user.tenant_id
        },
        {'$set': {'priority': priority}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    return {
        'success': True,
        'queue_id': queue_id,
        'new_priority': priority
    }


@router.post("/rooms/queue/notify-guest")
async def notify_guest_room_ready(
    queue_id: str,
    room_number: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Notify guest that their room is ready"""
    current_user = await get_current_user(credentials)
    
    # Get queue entry
    queue_entry = await db.room_queue.find_one({
        'id': queue_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Get booking
    await db.bookings.find_one({'id': queue_entry['booking_id']})
    
    # Update queue status
    await db.room_queue.update_one(
        {'id': queue_id},
        {
            '$set': {
                'status': 'assigned',
                'notified': True,
                'assigned_room': room_number,
                'notified_at': datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Send notification (mock)
    notification_message = f"Dear {queue_entry['guest_name']}, your room {room_number} is now ready! Please proceed to reception."
    
    print(f"📱 Room Ready Notification: {notification_message}")
    
    return {
        'success': True,
        'message': 'Guest notified successfully',
        'guest_name': queue_entry['guest_name'],
        'room_number': room_number,
        'notification': notification_message
    }


@router.delete("/rooms/queue/{queue_id}")
async def remove_from_queue(
    queue_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Remove entry from room queue"""
    current_user = await get_current_user(credentials)
    
    result = await db.room_queue.delete_one({
        'id': queue_id,
        'tenant_id': current_user.tenant_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    return {
        'success': True,
        'message': 'Entry removed from queue'
    }


