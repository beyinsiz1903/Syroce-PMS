"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import (
    require_op,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: sales) ───


@router.get("/sales/group-bookings")
@cached(ttl=300, key_prefix="sales_group_bookings")  # Cache for 5 min
async def get_group_bookings(
    status: str | None = None,
    current_user=Depends(get_current_user),  # v68 Bug DE: tenant-scoped cache key
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH (sales/admin meşru, HK NO)
):
    """Get group bookings (weddings, meetings, conferences)"""

    query = {
        'tenant_id': current_user.tenant_id,
        'booking_type': 'group'
    }

    if status:
        query['status'] = status

    group_bookings = []
    async for booking in db.group_bookings.find(query).sort('event_date', 1):
        group_bookings.append({
            'id': booking.get('id'),
            'group_name': booking.get('group_name'),
            'group_type': booking.get('group_type'),  # wedding, meeting, conference
            'event_date': booking.get('event_date').date().isoformat() if booking.get('event_date') else None,
            'start_date': booking.get('start_date').date().isoformat() if booking.get('start_date') else None,
            'end_date': booking.get('end_date').date().isoformat() if booking.get('end_date') else None,
            'total_rooms': booking.get('total_rooms', 0),
            'total_guests': booking.get('total_guests', 0),
            'total_revenue': booking.get('total_revenue', 0),
            'status': booking.get('status'),
            'contact_person': booking.get('contact_person'),
            'contact_email': booking.get('contact_email'),
        })

    return group_bookings

class GroupBookingCreate(BaseModel):
    group_name: str
    group_type: str  # wedding, meeting, conference
    event_date: str
    start_date: str
    end_date: str
    total_rooms: int
    total_guests: int
    contact_person: str
    contact_email: str
    contact_phone: str
    special_requirements: str | None = None
    notes: str | None = None



@router.post("/sales/group-booking")
async def create_group_booking(
    booking: GroupBookingCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_sales")),  # v92 DW
):
    """Create a new group booking"""
    current_user = await get_current_user(credentials)

    booking_id = str(uuid.uuid4())
    group_booking = {
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'booking_type': 'group',
        'group_name': booking.group_name,
        'group_type': booking.group_type,
        'event_date': datetime.fromisoformat(booking.event_date),
        'start_date': datetime.fromisoformat(booking.start_date),
        'end_date': datetime.fromisoformat(booking.end_date),
        'total_rooms': booking.total_rooms,
        'total_guests': booking.total_guests,
        'contact_person': booking.contact_person,
        'contact_email': booking.contact_email,
        'contact_phone': booking.contact_phone,
        'special_requirements': booking.special_requirements,
        'notes': booking.notes,
        'status': 'inquiry',
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.group_bookings.insert_one(group_booking)

    return {
        'message': 'Group booking created',
        'booking_id': booking_id,
        'group_name': booking.group_name
    }




@router.get("/sales/corporate-contracts")
async def get_corporate_contracts(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get corporate contracts"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    contracts = []
    async for contract in db.corporate_contracts.find(query).sort('start_date', -1):
        contracts.append({
            'id': contract.get('id'),
            'company_name': contract.get('company_name'),
            'contract_type': contract.get('contract_type'),  # direct, negotiated, corporate_rate
            'rate_code': contract.get('rate_code'),
            'negotiated_rate': contract.get('negotiated_rate'),
            'discount_percentage': contract.get('discount_percentage', 0),
            'start_date': contract.get('start_date').date().isoformat() if contract.get('start_date') else None,
            'end_date': contract.get('end_date').date().isoformat() if contract.get('end_date') else None,
            'allotment': contract.get('allotment', 0),
            'blackout_dates': contract.get('blackout_dates', []),
            'status': contract.get('status'),
            'approval_status': contract.get('approval_status', 'draft'),
            'approval_history': contract.get('approval_history', []),
            'total_bookings': contract.get('total_bookings', 0),
            'total_room_nights': contract.get('total_room_nights', 0),
            'total_revenue': contract.get('total_revenue', 0),
            'contact_person': contract.get('contact_person'),
            'notes': contract.get('notes', '')
        })

    return {
        'contracts': contracts,
        'count': len(contracts),
        'active_contracts': len([c for c in contracts if c['status'] == 'active'])
    }


class CorporateContractCreate(BaseModel):
    company_name: str
    contract_type: str
    rate_code: str
    negotiated_rate: float | None = None
    discount_percentage: float | None = 0
    start_date: str
    end_date: str
    allotment: int | None = 0
    blackout_dates: list[str] | None = []
    contact_person: str
    contact_email: str
    contact_phone: str
    notes: str | None = None


# Corporate-contract approval state machine. Independent of the active/expired
# `status` field — this governs whether a negotiated contract has cleared the
# approval workflow. Terminal states (approved) only re-open via an explicit
# reject→draft resubmission cycle.
CONTRACT_APPROVAL_TRANSITIONS: dict[str, set[str]] = {
    'draft': {'pending'},
    'pending': {'approved', 'rejected'},
    'rejected': {'draft'},
    'approved': set(),
}


async def _assert_contract_unique(
    tenant_id: str,
    contract: "CorporateContractCreate",
    exclude_id: str | None = None,
) -> None:
    """Tenant-scoped duplicate guard for corporate contracts.

    Rejects (409) a create/update whose ``rate_code`` or ``contact_email``
    collides with another contract in the same tenant. Blank values are
    ignored. ``exclude_id`` skips the row being updated so a no-op PUT does not
    self-collide.
    """
    checks: list[tuple[str, str]] = []
    if contract.rate_code and contract.rate_code.strip():
        checks.append(("rate_code", contract.rate_code.strip()))
    if contract.contact_email and contract.contact_email.strip():
        checks.append(("contact_email", contract.contact_email.strip()))
    for field, value in checks:
        flt: dict = {"tenant_id": tenant_id, field: value}
        if exclude_id:
            flt["id"] = {"$ne": exclude_id}
        dup = await db.corporate_contracts.find_one(flt, {"_id": 0, "id": 1})
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Bu {field} ile kayıtlı sözleşme zaten var")


class ContractApprovalTransition(BaseModel):
    to_status: str  # pending | approved | rejected | draft (resubmit)
    reason: str | None = None



@router.post("/sales/corporate-contract")
async def create_corporate_contract(
    contract: CorporateContractCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_sales")),  # v92 DW
):
    """Create a new corporate contract"""
    current_user = await get_current_user(credentials)

    # Tenant-scoped duplicate guard: rate_code and contact_email must be
    # unique within a tenant so a negotiated rate / billing contact cannot be
    # double-registered (409 rejected, not silently accepted).
    await _assert_contract_unique(current_user.tenant_id, contract)

    contract_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    corporate_contract = {
        'id': contract_id,
        'tenant_id': current_user.tenant_id,
        'company_name': contract.company_name,
        'contract_type': contract.contract_type,
        'rate_code': contract.rate_code,
        'negotiated_rate': contract.negotiated_rate,
        'discount_percentage': contract.discount_percentage,
        'start_date': datetime.fromisoformat(contract.start_date),
        'end_date': datetime.fromisoformat(contract.end_date),
        'allotment': contract.allotment,
        'blackout_dates': contract.blackout_dates,
        'contact_person': contract.contact_person,
        'contact_email': contract.contact_email,
        'contact_phone': contract.contact_phone,
        'notes': contract.notes,
        'status': 'active',
        # Approval workflow is independent of the active/expired `status`.
        # New contracts always start in `draft` and must walk the approval
        # state machine (draft→pending→approved/rejected) before being
        # considered commercially binding.
        'approval_status': 'draft',
        'approval_history': [],
        'total_bookings': 0,
        'total_room_nights': 0,
        'total_revenue': 0,
        'created_at': now,
        'created_by': current_user.username
    }

    await db.corporate_contracts.insert_one(corporate_contract)

    return {
        'message': 'Corporate contract created',
        'contract_id': contract_id,
        'company_name': contract.company_name,
        'approval_status': 'draft'
    }




@router.put("/sales/corporate-contract/{contract_id}")
async def update_corporate_contract(
    contract_id: str,
    contract: CorporateContractCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_sales")),  # v89 DW
):
    """Update a corporate contract"""
    current_user = await get_current_user(credentials)

    existing = await db.corporate_contracts.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })

    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    await _assert_contract_unique(
        current_user.tenant_id, contract, exclude_id=contract_id)

    await db.corporate_contracts.update_one(
        {'id': contract_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'company_name': contract.company_name,
                'contract_type': contract.contract_type,
                'rate_code': contract.rate_code,
                'negotiated_rate': contract.negotiated_rate,
                'discount_percentage': contract.discount_percentage,
                'start_date': datetime.fromisoformat(contract.start_date),
                'end_date': datetime.fromisoformat(contract.end_date),
                'allotment': contract.allotment,
                'blackout_dates': contract.blackout_dates,
                'contact_person': contract.contact_person,
                'contact_email': contract.contact_email,
                'contact_phone': contract.contact_phone,
                'notes': contract.notes,
                'updated_at': datetime.now(UTC),
                'updated_by': current_user.username
            }
        }
    )

    return {
        'message': 'Contract updated',
        'contract_id': contract_id
    }


@router.post("/sales/corporate-contract/{contract_id}/approval-transition")
async def transition_corporate_contract_approval(
    contract_id: str,
    body: ContractApprovalTransition,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_sales")),
):
    """Advance a corporate contract through its approval state machine.

    Allowed transitions (see ``CONTRACT_APPROVAL_TRANSITIONS``):
      draft → pending → approved | rejected, and rejected → draft (resubmit).
    Any other transition is rejected with 409 so the approval lifecycle is
    hard-enforced server-side rather than simulated client-side.
    """
    current_user = await get_current_user(credentials)

    existing = await db.corporate_contracts.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })
    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    from_status = existing.get('approval_status', 'draft')
    to_status = (body.to_status or '').strip().lower()

    if to_status not in {'draft', 'pending', 'approved', 'rejected'}:
        raise HTTPException(
            status_code=400,
            detail=f"Geçersiz onay durumu: {to_status}")

    allowed = CONTRACT_APPROVAL_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(f"Geçersiz onay geçişi: {from_status} → {to_status}. "
                    f"İzin verilen: {sorted(allowed) or 'yok (terminal)'}"))

    now = datetime.now(UTC)
    history_entry = {
        'from_status': from_status,
        'to_status': to_status,
        'reason': body.reason,
        'at': now.isoformat(),
        'by': current_user.username,
    }

    await db.corporate_contracts.update_one(
        {'id': contract_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'approval_status': to_status,
                'updated_at': now,
                'updated_by': current_user.username,
            },
            '$push': {'approval_history': history_entry},
        }
    )

    return {
        'message': 'Contract approval transitioned',
        'contract_id': contract_id,
        'from_status': from_status,
        'approval_status': to_status,
    }


@router.get("/sales/ota-promotions")
async def get_ota_promotions(
    active_only: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get OTA promotions"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if active_only:
        today = datetime.now(UTC)
        query['start_date'] = {'$lte': today}
        query['end_date'] = {'$gte': today}
        query['is_active'] = True

    promotions = []
    async for promo in db.ota_promotions.find(query).sort('start_date', -1):
        promotions.append({
            'id': promo.get('id'),
            'promotion_name': promo.get('promotion_name'),
            'ota_channel': promo.get('ota_channel'),  # booking.com, expedia, airbnb
            'promotion_type': promo.get('promotion_type'),  # discount, free_night, upgrade
            'discount_percentage': promo.get('discount_percentage', 0),
            'discount_amount': promo.get('discount_amount', 0),
            'start_date': promo.get('start_date').date().isoformat() if promo.get('start_date') else None,
            'end_date': promo.get('end_date').date().isoformat() if promo.get('end_date') else None,
            'min_stay_nights': promo.get('min_stay_nights', 1),
            'max_bookings': promo.get('max_bookings', 0),
            'current_bookings': promo.get('current_bookings', 0),
            'is_active': promo.get('is_active', True),
            'terms': promo.get('terms', ''),
            'created_at': promo.get('created_at').isoformat() if promo.get('created_at') else None
        })

    return {
        'promotions': promotions,
        'count': len(promotions),
        'active_count': len([p for p in promotions if p['is_active']])
    }


class OTAPromotionCreate(BaseModel):
    promotion_name: str
    ota_channel: str
    promotion_type: str
    discount_percentage: float | None = 0
    discount_amount: float | None = 0
    start_date: str
    end_date: str
    min_stay_nights: int | None = 1
    max_bookings: int | None = 0
    terms: str | None = None



@router.post("/sales/ota-promotion")
async def create_ota_promotion(
    promotion: OTAPromotionCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_sales")),  # v89 DW
):
    """Create a new OTA promotion"""
    current_user = await get_current_user(credentials)

    promo_id = str(uuid.uuid4())
    ota_promotion = {
        'id': promo_id,
        'tenant_id': current_user.tenant_id,
        'promotion_name': promotion.promotion_name,
        'ota_channel': promotion.ota_channel,
        'promotion_type': promotion.promotion_type,
        'discount_percentage': promotion.discount_percentage,
        'discount_amount': promotion.discount_amount,
        'start_date': datetime.fromisoformat(promotion.start_date),
        'end_date': datetime.fromisoformat(promotion.end_date),
        'min_stay_nights': promotion.min_stay_nights,
        'max_bookings': promotion.max_bookings,
        'current_bookings': 0,
        'is_active': True,
        'terms': promotion.terms,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.ota_promotions.insert_one(ota_promotion)

    return {
        'message': 'OTA promotion created',
        'promotion_id': promo_id,
        'promotion_name': promotion.promotion_name
    }


# --------------------------------------------------------------------------
# Revenue Management - Pickup Report, CompSet, Market Share
# --------------------------------------------------------------------------

