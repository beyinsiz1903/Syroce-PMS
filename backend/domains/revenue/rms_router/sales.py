"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import (
    AddCompetitorRequest,
    AutoPricingRequest,
    DemandForecastRequest,
    ScrapePricesRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: sales) ───


@router.get("/sales/group-bookings")
@cached(ttl=300, key_prefix="sales_group_bookings")  # Cache for 5 min
async def get_group_bookings(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get group bookings (weddings, meetings, conferences)"""
    current_user = await get_current_user(credentials)

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
    credentials: HTTPAuthorizationCredentials = Depends(security)
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



@router.post("/sales/corporate-contract")
async def create_corporate_contract(
    contract: CorporateContractCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new corporate contract"""
    current_user = await get_current_user(credentials)

    contract_id = str(uuid.uuid4())
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
        'total_bookings': 0,
        'total_room_nights': 0,
        'total_revenue': 0,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.corporate_contracts.insert_one(corporate_contract)

    return {
        'message': 'Corporate contract created',
        'contract_id': contract_id,
        'company_name': contract.company_name
    }




@router.put("/sales/corporate-contract/{contract_id}")
async def update_corporate_contract(
    contract_id: str,
    contract: CorporateContractCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Update a corporate contract"""
    current_user = await get_current_user(credentials)

    existing = await db.corporate_contracts.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })

    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

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
    credentials: HTTPAuthorizationCredentials = Depends(security)
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

