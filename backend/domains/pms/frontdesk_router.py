"""
PMS / Front Desk Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import base64
import io
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.context import OperationContext
from core.database import db
from core.security import (
    get_current_user,
)
from core.utils import generate_folio_number
from domains.pms.frontdesk_service import frontdesk_service
from models.enums import BookingStatus, ChannelType, ChargeCategory, PaymentMethod, PaymentType
from models.schemas import Booking, Guest, User
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.pms_core.role_permission_service import require_op  # v94 DW

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Front Desk"])


from domains.pms.schemas import (  # noqa: E402
    GuestAlert,
    KeycardIssueRequest,
    PassportScanData,
    PassportScanRequest,
    WalkInBookingRequest,
)


@router.get("/arrivals/today")
async def get_todays_arrivals(current_user: User = Depends(get_current_user)):
    """Bugünün varışları - VIP, grup ve özel isteklerle"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_todays_arrivals(ctx)
    return result.data


@router.post("/frontdesk/express-checkin")
async def express_checkin_qr(qr_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """QR code ile express check-in"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.express_checkin(ctx, qr_data["qr_code"])
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data



@router.post("/frontdesk/kiosk-checkin")
async def kiosk_checkin(checkin_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    booking_id = checkin_data.get('booking_id')
    if not booking_id:
        raise HTTPException(status_code=400, detail="booking_id is required")
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get('status') not in ('confirmed', 'guaranteed'):
        raise HTTPException(status_code=400, detail=f"Booking status '{booking.get('status')}' is not eligible for check-in")
    room_key = f"DK-{booking.get('room_number', 'X')}-{str(uuid.uuid4())[:6].upper()}"
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'status': 'checked_in', 'checked_in_at': datetime.now(UTC).isoformat(), 'kiosk_checkin': True}}
    )
    return {'success': True, 'message': f"Kiosk check-in basarili: Oda {booking.get('room_number')}", 'room_key': room_key, 'room_number': booking.get('room_number'), 'note': 'Kiosk entegrasyonu aktif. Dijital anahtar olusturuldu.'}

# ============= ADVANCED LOYALTY =============



@router.get("/frontdesk/audit-checklist")
@cached(ttl=180, key_prefix="frontdesk_audit_checklist")  # Tur 3: was 7s, cache 3 min (tenant-aware)
async def get_frontdesk_audit_checklist(
    current_user: User = Depends(get_current_user)  # Tur 3: tenant-scoped cache key
):
    """Front desk için night audit öncesi checklist"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_audit_checklist(ctx)
    return result.data




@router.post("/frontdesk/checkin/{booking_id}")
async def check_in_guest(booking_id: str, create_folio: bool = True, force_clean: bool = False, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Check-in guest with validations and auto-folio creation. force_clean=true cleans a dirty room before check-in."""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.checkin(ctx, booking_id, create_folio, force_clean)
    if not result.ok:
        code_map = {"NOT_FOUND": 404, "ALREADY_CHECKED_IN": 400, "ROOM_NOT_READY": 400}
        raise HTTPException(status_code=code_map.get(result.code, 400), detail=result.error)
    return result.data



@router.post("/frontdesk/checkout/{booking_id}")
async def check_out_guest(
    booking_id: str,
    force: bool = False,
    auto_close_folios: bool = True,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Check-out guest with balance validation and folio closure"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.checkout(ctx, booking_id, force, auto_close_folios)
    if not result.ok:
        code_map = {"NOT_FOUND": 404, "ALREADY_CHECKED_OUT": 400, "OUTSTANDING_BALANCE": 402}
        raise HTTPException(status_code=code_map.get(result.code, 400), detail=result.error)
    return result.data



class FolioChargeRequest(BaseModel):
    charge_category: ChargeCategory | None = None
    charge_type: str | None = None  # legacy alias
    description: str
    amount: float
    quantity: float = 1.0


class FolioPaymentRequest(BaseModel):
    amount: float
    method: PaymentMethod = PaymentMethod.CASH
    payment_type: PaymentType = PaymentType.INTERIM
    reference: str | None = None
    notes: str | None = None


_LEGACY_CHARGE_MAP = {
    "f_and_b": ChargeCategory.FOOD,
    "fnb": ChargeCategory.FOOD,
    "food_beverage": ChargeCategory.FOOD,
    "drink": ChargeCategory.BEVERAGE,
}


async def _ensure_booking(tenant_id: str, booking_id: str) -> dict:
    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


async def _ensure_open_folio(tenant_id: str, booking_id: str, guest_id: str | None = None) -> dict:
    folio = await db.folios.find_one(
        {"tenant_id": tenant_id, "booking_id": booking_id, "status": "open", "folio_type": "guest"},
        {"_id": 0},
    )
    if folio:
        return folio
    folio = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "folio_number": await generate_folio_number(tenant_id),
        "folio_type": "guest",
        "status": "open",
        "guest_id": guest_id,
        "company_id": None,
        "balance": 0.0,
        "notes": None,
        "created_at": datetime.now(UTC).isoformat(),
        "closed_at": None,
    }
    await db.folios.insert_one(dict(folio))
    folio.pop("_id", None)
    return folio


# ──────────────────────────────────────────────────────────────────────
# Folio Routing helpers — booking.routing_rules içindeki kategori-bazlı
# kuralları uygulayıp charge'ı doğru folio'ya yönlendirir. Routing kuralı
# yoksa veya eşleşmiyorsa default (misafir folyo) döner.
# ──────────────────────────────────────────────────────────────────────

# RoutingInstructions UI kategorileri ↔ ChargeCategory enum eşleme.
# UI tarafında 'fb' ve 'telephone'/'business_center' gibi kategoriler var;
# backend ChargeCategory enum'una çevirip kuralı charge_category alanı
# üzerinden eşleştirebilelim.
_ROUTING_CATEGORY_ALIASES: dict[str, set[str]] = {
    "room": {"room"},
    "fb": {"food", "beverage"},
    "minibar": {"minibar"},
    "laundry": {"laundry"},
    "telephone": {"phone"},
    "spa": {"spa"},
    "parking": {"other"},
    "business_center": {"internet", "other"},
    "other": {"other"},
}


def _rule_matches_category(rule_category: str | None, charge_category: str) -> bool:
    """UI kategori → ChargeCategory eşleşmesi. Eşleşme yoksa False."""
    if not rule_category:
        return False
    aliases = _ROUTING_CATEGORY_ALIASES.get(rule_category.lower(), {rule_category.lower()})
    return charge_category.lower() in aliases


async def _resolve_routed_folio(
    tenant_id: str,
    booking: dict,
    target: str,
) -> dict | None:
    """Routing target ('company', 'travel_agent', 'group_master') için
    açık folyoyu bulur veya gerekiyorsa oluşturur. 'guest' veya bilinmeyen
    target için None döner (default akış misafir folyosu).
    """
    booking_id = booking.get("id")
    if not booking_id or target == "guest":
        return None

    async def _lazy_upsert_folio(folio_type: str, party_id: str, note: str) -> dict:
        """Atomik açık folyo bul-veya-oluştur. Eşzamanlı charge'larda
        race condition'ı önlemek için find_one_and_update + upsert
        kullanılır; aynı (tenant, booking, type, party) için yalnızca tek
        açık folyo oluşur. AFTER document'ı döner.
        """
        from pymongo import ReturnDocument
        filter_doc = {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "folio_type": folio_type,
            "company_id": party_id,
            "status": "open",
        }
        set_on_insert = {
            "id": str(uuid.uuid4()),
            "folio_number": await generate_folio_number(tenant_id),
            "guest_id": booking.get("guest_id"),
            "balance": 0.0,
            "notes": note,
            "created_at": datetime.now(UTC).isoformat(),
            "closed_at": None,
        }
        doc = await db.folios.find_one_and_update(
            filter_doc,
            {"$setOnInsert": set_on_insert},
            upsert=True,
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        return doc

    if target == "company":
        company_id = booking.get("company_id")
        if not company_id:
            return None
        return await _lazy_upsert_folio("company", company_id, "Auto-created by routing rule")

    if target == "travel_agent":
        agency_id = booking.get("agency_id") or booking.get("travel_agent_id")
        if not agency_id:
            return None
        return await _lazy_upsert_folio(
            "agency", agency_id, "Auto-created by routing rule (travel agent)"
        )

    if target == "group_master":
        group_id = booking.get("group_id") or booking.get("group_booking_id")
        if not group_id:
            return None
        # Grup master folyosu booking_id yerine group_id ile saklanır.
        existing = await db.folios.find_one(
            {
                "tenant_id": tenant_id,
                "group_id": group_id,
                "folio_type": "guest",
                "status": "open",
            },
            {"_id": 0},
        )
        return existing  # Group master folyo manuel açılır; otomatik yaratmıyoruz.

    return None


async def _apply_routing_for_charge(
    tenant_id: str,
    booking: dict,
    charge_category: str,
    default_folio: dict,
) -> dict:
    """Booking.routing_rules içinden charge_category'ye uyan ilk aktif
    kuralı bulup hedef folyoyu döner. Kural yoksa default_folio döner.
    """
    rules = booking.get("routing_rules") or []
    if not rules:
        return default_folio
    for rule in rules:
        if rule.get("active") is False:
            continue
        if not _rule_matches_category(rule.get("category"), charge_category):
            continue
        # Split (percentage/equal) henüz desteklenmiyor — tek folyoya
        # tam yönlendirme yapılır. Split desteklenince burada birden çok
        # folio_charges yazılması ve oranların ayrılması gerekir.
        # MVP'de UI yalnızca tam yönlendirme kuralı üretiyor; defansif
        # olarak split tanımlı kuralları sessizce atlamak yerine ilk
        # split target'a yönlendiriyoruz (idempotent ve mevcut davranışı
        # bozmaz).
        target = rule.get("target")
        if not target and isinstance(rule.get("splits"), list) and rule["splits"]:
            target = rule["splits"][0].get("target")
        if not target:
            continue
        routed = await _resolve_routed_folio(tenant_id, booking, target)
        if routed:
            return routed
    return default_folio


@router.post("/frontdesk/folio/{booking_id}/charge")
async def add_folio_charge(
    booking_id: str,
    payload: FolioChargeRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v97 DW
):
    if payload.amount <= 0 or payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="amount ve quantity 0'dan büyük olmalı")

    category = payload.charge_category
    if category is None and payload.charge_type:
        key = payload.charge_type.lower()
        if key in _LEGACY_CHARGE_MAP:
            category = _LEGACY_CHARGE_MAP[key]
        else:
            try:
                category = ChargeCategory(key)
            except ValueError:
                category = ChargeCategory.OTHER
    if category is None:
        raise HTTPException(status_code=400, detail="charge_category gerekli")

    booking = await _ensure_booking(current_user.tenant_id, booking_id)
    default_folio = await _ensure_open_folio(
        current_user.tenant_id, booking_id, booking.get("guest_id")
    )
    # Routing rules: kategori uyuşan kural varsa hedef folyoya yönlendir.
    # Hedef yoksa veya resolve edilemezse default (misafir) folyo kullanılır.
    target_folio = await _apply_routing_for_charge(
        current_user.tenant_id, booking, category.value, default_folio
    )
    unit_price = float(payload.amount)
    quantity = float(payload.quantity)
    net_amount = unit_price * quantity
    now_iso = datetime.now(UTC).isoformat()
    charge_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "folio_id": target_folio["id"],
        "booking_id": booking_id,
        "charge_category": category.value,
        "description": payload.description,
        "unit_price": unit_price,
        "quantity": quantity,
        "amount": net_amount,
        "tax_amount": 0.0,
        "total": net_amount,
        "posted_by": current_user.name,
        "posted_at": now_iso,
        "date": now_iso,
    }
    # Routed flag — UI'da "şirkete yönlendirildi" rozeti için.
    if target_folio["id"] != default_folio["id"]:
        charge_doc["routed_from_folio_id"] = default_folio["id"]
        charge_doc["routed_to_folio_id"] = target_folio["id"]
    await db.folio_charges.insert_one(dict(charge_doc))
    await db.folios.update_one(
        {"id": target_folio["id"], "tenant_id": current_user.tenant_id},
        {"$inc": {"balance": net_amount}},
    )
    return charge_doc


@router.post("/frontdesk/folio/{booking_id}/payment")
async def add_folio_payment(
    booking_id: str,
    payload: FolioPaymentRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount 0'dan büyük olmalı")

    booking = await _ensure_booking(current_user.tenant_id, booking_id)
    folio = await _ensure_open_folio(current_user.tenant_id, booking_id, booking.get("guest_id"))
    amount = float(payload.amount)
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    method_value = payload.method.value if hasattr(payload.method, "value") else str(payload.method)
    type_value = payload.payment_type.value if hasattr(payload.payment_type, "value") else str(payload.payment_type)
    payment_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "amount": amount,
        "method": method_value,
        "payment_type": type_value,
        "status": "paid",
        "voided": False,
        "reference": payload.reference,
        "notes": payload.notes,
        "processed_by": current_user.name,
        "processed_at": now_iso,
    }
    # Vardiya kontrolü: nakit ödemede aktif vardiya zorunlu
    from domains.pms.cashier_service import ensure_active_shift, record_cash_transaction
    await ensure_active_shift(current_user.tenant_id, method_value)

    await db.payments.insert_one(dict(payment_doc))
    await db.folios.update_one(
        {"id": folio["id"], "tenant_id": current_user.tenant_id},
        {"$inc": {"balance": -amount}},
    )
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"$inc": {"paid_amount": amount}},
    )

    # Kasa hareketine yaz — cash için race-safe rollback
    is_cash = method_value.lower() == "cash"
    try:
        await record_cash_transaction(
            tenant_id=current_user.tenant_id,
            amount=amount,
            method=method_value,
            direction="in",
            description=f"Folio ödemesi - Oda {booking.get('room_number', '?')}",
            txn_type="folio_payment",
            ref_type="payment",
            ref_id=payment_doc["id"],
            created_by=current_user.email,
            created_by_name=getattr(current_user, "name", None) or current_user.email,
            idempotency_key=f"payment:{payment_doc['id']}",
            require_open_shift=is_cash,
        )
    except HTTPException as he:
        if is_cash and he.status_code == 409:
            try:
                await db.payments.delete_one({"id": payment_doc["id"], "tenant_id": current_user.tenant_id})
                await db.folios.update_one(
                    {"id": folio["id"], "tenant_id": current_user.tenant_id},
                    {"$inc": {"balance": amount}},
                )
                await db.bookings.update_one(
                    {"id": booking_id, "tenant_id": current_user.tenant_id},
                    {"$inc": {"paid_amount": -amount}},
                )
            except Exception:
                import logging as _lg
                _lg.getLogger(__name__).exception("payment rollback failed after cashier 409")
        raise
    except Exception:
        import logging as _lg
        _lg.getLogger(__name__).exception("cashier txn record failed")

    return payment_doc



@router.get("/frontdesk/folio/{booking_id}")
async def get_folio(booking_id: str, current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_folio(ctx, booking_id)
    if not result.ok:
        code = 404 if result.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=code, detail=result.error)
    return result.data


# rbac-allow: cache-rbac — FO arrivals operasyonel (FO/HK/manager)
@router.get("/frontdesk/arrivals")
@cached(ttl=120, key_prefix="frontdesk_arrivals")
async def get_arrivals(date: str | None = None, current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_arrivals(ctx, date)
    return result.data


# rbac-allow: cache-rbac — FO departures operasyonel
@router.get("/frontdesk/departures")
@cached(ttl=120, key_prefix="frontdesk_departures")
async def get_departures(date: str | None = None, current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_departures(ctx, date)
    return result.data


# rbac-allow: cache-rbac — FO inhouse operasyonel
@router.get("/frontdesk/inhouse")
@cached(ttl=180, key_prefix="frontdesk_inhouse")
async def get_inhouse_guests(current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_inhouse(ctx)
    return result.data


# ============= REPORTING =============

# ============= MANAGEMENT REPORTS =============



@router.post("/frontdesk/passport-scan")
async def scan_passport(
    request: PassportScanRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """
    Scan passport and extract data automatically
    Uses OCR to extract passport information
    """
    # In production, integrate with OCR service like:
    # - OCR.space
    # - Google Cloud Vision
    # - Azure Computer Vision
    # - Amazon Textract

    # For MVP, we'll simulate OCR response
    # In real implementation, send image_base64 to OCR service

    try:
        # Simulated OCR extraction (in production, call actual OCR API)
        # Example with Google Vision or OCR.space would be:
        # response = await ocr_service.extract_passport(request.image_base64)

        extracted_data = PassportScanData(
            passport_number="",
            name="",
            surname="",
            nationality="",
            date_of_birth="",
            expiry_date="",
            sex=""
        )

        return {
            'success': True,
            'extracted_data': extracted_data.model_dump(),
            'confidence': 0,
            'message': 'Pasaport tarama altyapisi hazir. Lutfen OCR servis entegrasyonunu yapilandiriniz.',
            'requires_ocr_config': True
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Passport scan failed: {str(e)}")




@router.post("/frontdesk/walk-in-booking")
async def create_walk_in_booking(
    request: WalkInBookingRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """
    Quick walk-in booking - create guest, booking, and check-in with one click
    """
    try:
        # 1. Check room availability
        room = await db.rooms.find_one({
            'id': request.room_id,
            'tenant_id': current_user.tenant_id
        })

        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        if room.get('status') not in ['available', 'inspected']:
            raise HTTPException(
                status_code=400,
                detail=f"Room {room.get('room_number')} is not available (status: {room.get('status')})"
            )

        # 2. Create or find guest
        guest_email = request.guest_email or f"walkin_{uuid.uuid4().hex[:8]}@hotel.local"

        # Try to find existing guest by phone or email
        existing_guest = await db.guests.find_one({
            'tenant_id': current_user.tenant_id,
            '$or': [
                {'phone': request.guest_phone},
                {'email': guest_email}
            ]
        })

        if existing_guest:
            guest_id = existing_guest['id']
        else:
            # Create new guest
            new_guest = Guest(
                tenant_id=current_user.tenant_id,
                name=request.guest_name,
                email=guest_email,
                phone=request.guest_phone,
                id_number=request.guest_id_number or f"WALKIN-{uuid.uuid4().hex[:8]}",
                nationality=request.nationality
            )

            guest_dict = new_guest.model_dump()
            guest_dict['created_at'] = guest_dict['created_at'].isoformat()
            await db.guests.insert_one(guest_dict)
            guest_id = new_guest.id

        # 3. Calculate dates and amount
        check_in = datetime.now(UTC).replace(hour=14, minute=0, second=0, microsecond=0)
        check_out = check_in + timedelta(days=request.nights)

        rate = request.rate_per_night or room.get('base_price', 100.0)
        total_amount = rate * request.nights

        # 4. Create booking
        new_booking = Booking(
            tenant_id=current_user.tenant_id,
            guest_id=guest_id,
            room_id=request.room_id,
            check_in=check_in.date().isoformat(),
            check_out=check_out.date().isoformat(),
            adults=request.adults,
            children=request.children,
            children_ages=[],
            guests_count=request.adults + request.children,
            total_amount=total_amount,
            status=BookingStatus.CONFIRMED,
            channel=ChannelType.DIRECT,
            special_requests=request.special_requests
        )

        booking_dict = new_booking.model_dump()
        booking_dict['created_at'] = booking_dict['created_at'].isoformat()
        from core.atomic_booking import BookingConflictError, create_booking_atomic
        try:
            await create_booking_atomic(booking_dict)
        except BookingConflictError as e:
            raise HTTPException(status_code=409, detail=str(e))

        # 5. Atomic check-in (booking + room + folio + audit + outbox in one transaction)
        from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
        try:
            checkin_result = await check_in_booking_atomic(
                booking_id=new_booking.id,
                tenant_id=current_user.tenant_id,
                actor_id=current_user.id,
                actor_name=current_user.name,
            )
        except CheckInError as e:
            raise HTTPException(status_code=400, detail=f"Walk-in booking created but check-in failed: {e}")

        # 6. KBS auto-notify when a real ID number was provided (TC kimlik / passport)
        # Skips placeholder IDs (those start with "WALKIN-").
        kbs_notified = False
        kbs_reference = None
        try:
            real_id = (request.guest_id_number or '').strip()
            if real_id and not real_id.upper().startswith('WALKIN-'):
                kbs_reference = str(uuid.uuid4())[:8].upper()
                kbs_doc = {
                    "_id": str(uuid.uuid4()),
                    "tenant_id": current_user.tenant_id,
                    "booking_id": new_booking.id,
                    "kbs_reference": kbs_reference,
                    "status": "sent",
                    "sent_at": datetime.now(UTC).isoformat(),
                    "sent_by": current_user.email,
                    "source": "walk_in_auto",
                    "guest_data": {
                        "name": request.guest_name,
                        "id_number": real_id,
                        "nationality": request.nationality,
                        "phone": request.guest_phone,
                    },
                }
                await db.kbs_notifications.insert_one(kbs_doc)
                await db.bookings.update_one(
                    {"id": new_booking.id, "tenant_id": current_user.tenant_id},
                    {"$set": {
                        "kbs_status": "sent",
                        "kbs_sent_at": datetime.now(UTC).isoformat(),
                        "kbs_reference": kbs_reference,
                    }}
                )
                kbs_notified = True
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "KBS auto-notify failed for walk-in booking %s; booking remains valid",
                new_booking.id,
            )

        return {
            'success': True,
            'message': "Walk-in booking created and checked in successfully",
            'booking_id': new_booking.id,
            'guest_id': guest_id,
            'room_number': room.get('room_number'),
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat(),
            'total_amount': total_amount,
            'checked_in_at': checkin_result.get('checked_in_at'),
            'kbs_notified': kbs_notified,
            'kbs_reference': kbs_reference,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Walk-in booking failed: {str(e)}")




@router.get("/frontdesk/guest-alerts/{guest_id}")
async def get_guest_alerts(
    guest_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get all active alerts for a guest"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_guest_alerts(ctx, guest_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data




@router.post("/frontdesk/guest-alerts")
async def create_guest_alert(
    guest_id: str,
    alert_type: str,
    title: str,
    description: str,
    priority: str = "normal",
    expires_days: int | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Create a custom alert for a guest"""
    expires_at = None
    if expires_days:
        expires_at = datetime.now(UTC) + timedelta(days=expires_days)

    alert = GuestAlert(
        tenant_id=current_user.tenant_id,
        guest_id=guest_id,
        alert_type=alert_type,
        priority=priority,
        title=title,
        description=description,
        expires_at=expires_at
    )

    alert_dict = alert.model_dump()
    alert_dict['created_at'] = alert_dict['created_at'].isoformat()
    if alert_dict.get('expires_at'):
        alert_dict['expires_at'] = alert_dict['expires_at'].isoformat()

    await db.guest_alerts.insert_one(alert_dict)

    return {
        'success': True,
        'alert_id': alert.id,
        'message': 'Guest alert created successfully'
    }


@router.delete("/frontdesk/guest-alerts/{alert_id}")
async def delete_guest_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    result = await db.guest_alerts.delete_one({'id': alert_id, 'tenant_id': current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {'success': True, 'message': 'Alert deleted'}


# ============= HOUSEKEEPING ENHANCEMENTS =============



@router.post("/self-checkin/generate-door-qr")
async def generate_door_qr_code(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """
    Generate QR code for door lock
    - Digital key
    - Time-limited access
    - Room entry tracking
    """
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id})

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    qr_data = {
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'valid_from': booking.get('check_in'),
        'valid_until': booking.get('check_out'),
        'access_token': str(uuid.uuid4()),
        'generated_at': datetime.now(UTC).isoformat()
    }

    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(json.dumps(qr_data))
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()

    return {
        'success': True,
        'booking_id': booking_id,
        'qr_code_base64': qr_base64,
        'qr_data': qr_data,
        'valid_from': qr_data['valid_from'],
        'valid_until': qr_data['valid_until'],
    }




@router.post("/self-checkin/digital-signature")
async def capture_digital_signature(
    booking_id: str,
    signature_base64: str,
    registration_card_data: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """
    Capture digital signature
    - Guest signs registration card
    - Legally binding
    - Stored with booking
    """
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id})

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    signature_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'signature_base64': signature_base64,
        'registration_card_data': registration_card_data,
        'signed_at': datetime.now(UTC).isoformat(),
        'ip_address': None,
        'device_type': 'kiosk'
    }

    await db.digital_signatures.insert_one(signature_record)

    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'digital_signature_id': signature_record['id']}}
    )

    return {
        'success': True,
        'signature_id': signature_record['id'],
        'message': 'Digital signature captured successfully'
    }




@router.post("/self-checkin/police-notification")
async def auto_police_notification(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """
    Automatic police notification
    - Required by law in many countries
    - Guest ID information
    - Automated submission
    """
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id})

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    guest = await db.guests.find_one({'id': booking.get('guest_id'), 'tenant_id': current_user.tenant_id})

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    notification_data = {
        'id': str(uuid.uuid4()),
        'booking_id': booking_id,
        'guest_name': guest.get('name'),
        'guest_id_number': guest.get('id_number'),
        'nationality': guest.get('nationality'),
        'check_in': booking.get('check_in'),
        'check_out': booking.get('check_out'),
        'room_number': None,  # Get from room
        'submitted_at': datetime.now(UTC).isoformat(),
        'status': 'submitted',
        'reference_number': f"POL-{uuid.uuid4().hex[:8].upper()}"
    }

    await db.police_notifications.insert_one(notification_data)

    return {
        'success': True,
        'notification_id': notification_data['id'],
        'reference_number': notification_data['reference_number'],
        'status': 'submitted',
        'message': 'Police notification submitted successfully',
        'note': 'In production: Integrate with local police system (GIYBIS, Alloggiati Web, etc.)'
    }


# ============= NIGHT AUDIT SYSTEM =============



@router.post("/keycard/issue")
async def issue_keycard(
    request: KeycardIssueRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Issue a new keycard for a booking"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.issue_keycard(ctx, request.booking_id, request.card_type, request.validity_hours)
    if not result.ok:
        code_map = {"NOT_FOUND": 404, "INVALID_STATUS": 400, "NO_ROOM": 400}
        raise HTTPException(status_code=code_map.get(result.code, 400), detail=result.error)
    return result.data


@router.put("/keycard/{keycard_id}/deactivate")
async def deactivate_keycard(
    keycard_id: str,
    reason: str = "checkout",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Deactivate/cancel a keycard"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.deactivate_keycard(ctx, keycard_id, reason)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data




@router.get("/keycard/booking/{booking_id}")
async def get_booking_keycards(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get all keycards for a booking"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_booking_keycards(ctx, booking_id)
    return result.data


# ============================================================================
# UNIFIED ARRIVALS/DEPARTURES - SHARED ACROSS ALL DEPARTMENTS
# ============================================================================


@router.get("/unified/today-arrivals")
async def get_today_arrivals_unified(current_user: User = Depends(get_current_user)):
    """Unified endpoint for today's arrivals"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_unified_arrivals(ctx)
    return result.data


@router.get("/unified/today-departures")
async def get_today_departures_unified(current_user: User = Depends(get_current_user)):
    """Unified endpoint for today's departures"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_unified_departures(ctx)
    return result.data


@router.get("/unified/in-house")
async def get_in_house_unified(current_user: User = Depends(get_current_user)):
    """Unified endpoint for in-house guests"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_unified_inhouse(ctx)
    return result.data


# ============================================================================
# CLEANING REQUESTS - GUEST TO HOUSEKEEPING INTEGRATION
# ============================================================================


