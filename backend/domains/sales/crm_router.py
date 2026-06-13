"""
Sales / CRM Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import CompanyStatus
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v92 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Sales / CRM"])


from domains.sales.schemas import (  # noqa: E402
    CreateLeadRequest,
    PmsLiteLeadCreateRequest,
    PmsLiteLeadMetadata,
    PmsLiteLeadStatus,
    UpdateLeadStageRequest,
)


@router.get("/sales/customers")
async def get_sales_customers(
    customer_type: str | None = None,  # vip, corporate, returning, new
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get customer/guest list with filters
    VIP, Corporate, Returning, New customers
    """
    current_user = await get_current_user(credentials)

    # Perf: tüm bookings'i belleğe çekip Python tarafında guest_id'ye gruplamak
    # büyük tenant'larda saniyeler sürüyordu. Aynı agregasyonu MongoDB tarafında
    # tek pipeline ile yapıyoruz; sadece guest başına 1 satır geri geliyor.
    # `booking_source` ($first) ile rezervasyon kanalı korunuyor → corporate
    # sınıflandırması bozulmuyor. $group öncesi `check_in` desc sıralama: en
    # güncel rezervasyona göre kararlı misafir adı/iletişim/booking_source seçer.
    # Legacy `if not guest_id` skipped null **ve** boş string; aggregation'da
    # ikisini de elemek için $nin kullanılıyor.
    #
    # Perf (Faz 4): VIP eşiği/korporat/returning sınıflandırması artık
    # $addFields ile pipeline içinde hesaplanıyor; type filtresi + sıralama +
    # sayfalama + sayımlar tek $facet'te yapılıyor. Böylece TÜM guest satırları
    # belleğe çekilmiyor — sadece `limit` satır + sayım dökümanı dönüyor. Yanıt
    # sözleşmesi (customers/count/vip_count/corporate_count + boşsa örnek veri)
    # birebir korunur; count/vip_count/corporate_count tüm filtreli set üzerinden.
    base_stages: list[dict] = [
        {"$match": {
            "tenant_id": current_user.tenant_id,
            "guest_id": {"$nin": [None, ""]},
        }},
        {"$sort": {"check_in": -1}},
        {"$group": {
            "_id": "$guest_id",
            "guest_name": {"$first": "$guest_name"},
            "email": {"$first": "$guest_email"},
            "phone": {"$first": "$guest_phone"},
            "total_bookings": {"$sum": 1},
            "total_revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}},
            "last_stay": {"$max": "$check_in"},
            "booking_source": {"$first": "$booking_source"},
        }},
        {"$addFields": {
            "is_vip": {"$gt": ["$total_revenue", 50000]},
            "is_corporate": {"$eq": ["$booking_source", "corporate"]},
        }},
    ]

    # customer_type filtresi orijinal Python davranışını birebir korur:
    # vip/corporate/returning/new -> ilgili computed koşul. Bilinmeyen bir tip
    # -> hiçbir kayıt eşleşmez (orijinalde "type not in list" tüm müşterileri
    # eler -> boş sonuç -> örnek veri fallback). `_id` her $group dökümanında
    # daima vardır, dolayısıyla `{"_id": {"$exists": False}}` hiçbir şeyi seçmez.
    type_match: dict | None = None
    if customer_type:
        if customer_type == 'vip':
            type_match = {"is_vip": True}
        elif customer_type == 'corporate':
            type_match = {"is_corporate": True}
        elif customer_type == 'returning':
            type_match = {"total_bookings": {"$gt": 1}}
        elif customer_type == 'new':
            type_match = {"total_bookings": {"$lte": 1}}
        else:
            type_match = {"_id": {"$exists": False}}

    page_stages = list(base_stages)
    stats_stages = list(base_stages)
    if type_match is not None:
        page_stages.append({"$match": type_match})
        stats_stages.append({"$match": type_match})

    page_stages += [
        {"$sort": {"total_revenue": -1}},
        {"$limit": int(limit)},
        {"$project": {
            "_id": 0,
            "guest_id": "$_id",
            "guest_name": 1, "email": 1, "phone": 1,
            "total_bookings": 1, "total_revenue": 1, "last_stay": 1,
            "is_vip": 1, "is_corporate": 1,
        }},
    ]
    stats_stages.append({"$group": {
        "_id": None,
        "count": {"$sum": 1},
        "vip_count": {"$sum": {"$cond": ["$is_vip", 1, 0]}},
        "corporate_count": {"$sum": {"$cond": ["$is_corporate", 1, 0]}},
    }})

    facet_docs = await db.bookings.aggregate(
        [{"$facet": {"page": page_stages, "stats": stats_stages}}],
        allowDiskUse=True,
    ).to_list(1)
    facet = facet_docs[0] if facet_docs else {}
    page_rows = facet.get('page') or []
    stats_list = facet.get('stats') or []
    stats = stats_list[0] if stats_list else {}
    count = int(stats.get('count') or 0)
    vip_count = int(stats.get('vip_count') or 0)
    corporate_count = int(stats.get('corporate_count') or 0)

    customers = []
    for row in page_rows:
        is_vip = bool(row.get('is_vip'))
        is_corporate = bool(row.get('is_corporate'))
        total_bookings = int(row.get('total_bookings') or 0)
        customer_type_list = []
        if is_vip:
            customer_type_list.append('vip')
        if is_corporate:
            customer_type_list.append('corporate')
        if total_bookings > 1:
            customer_type_list.append('returning')
        else:
            customer_type_list.append('new')
        customers.append({
            'guest_id': row.get('guest_id'),
            'guest_name': row.get('guest_name') or 'Unknown',
            'email': row.get('email') or '',
            'phone': row.get('phone') or '',
            'total_bookings': total_bookings,
            'total_revenue': row.get('total_revenue') or 0,
            'last_stay': row.get('last_stay'),
            'is_vip': is_vip,
            'is_corporate': is_corporate,
            'customer_type': customer_type_list,
        })

    # Sample data if empty
    if count == 0:
        customers = [
            {
                'guest_id': str(uuid.uuid4()),
                'guest_name': 'Ahmet Yılmaz',
                'email': 'ahmet.yilmaz@company.com',
                'phone': '+90 532 123 4567',
                'total_bookings': 12,
                'total_revenue': 48000,
                'last_stay': (datetime.now() - timedelta(days=15)).isoformat(),
                'is_vip': False,
                'is_corporate': True,
                'customer_type': ['corporate', 'returning']
            },
            {
                'guest_id': str(uuid.uuid4()),
                'guest_name': 'Ayşe Demir',
                'email': 'ayse.demir@email.com',
                'phone': '+90 533 987 6543',
                'total_bookings': 25,
                'total_revenue': 125000,
                'last_stay': (datetime.now() - timedelta(days=5)).isoformat(),
                'is_vip': True,
                'is_corporate': False,
                'customer_type': ['vip', 'returning']
            }
        ]
        # Boş sonuç -> örnek veri: sayımlar legacy ile birebir (count=2,
        # vip_count=1, corporate_count=1) kalsın diye örnek listeden hesaplanır.
        count = len(customers)
        vip_count = len([c for c in customers if c['is_vip']])
        corporate_count = len([c for c in customers if c['is_corporate']])

    return {
        'customers': customers[:limit],
        'count': count,
        'vip_count': vip_count,
        'corporate_count': corporate_count,
    }


# GET /api/sales/leads — MOVED to domains/sales/router.py


# 3. GET /api/sales/ota-pricing - OTA price comparison


@router.get("/sales/ota-pricing")
async def get_ota_pricing(
    date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    OTA price tracking - Booking.com, Expedia, Agoda comparison
    """
    await get_current_user(credentials)

    target_date = date if date else datetime.now().date().isoformat()

    # Sample OTA pricing data
    ota_prices = [
        {
            'date': target_date,
            'room_type': 'Standard Room',
            'our_rate': 1200,
            'booking_com': 1250,
            'expedia': 1280,
            'agoda': 1230,
            'hotels_com': 1260,
            'lowest_competitor': 1230,
            'price_position': 'lowest',  # lowest, competitive, highest
            'parity_status': 'good'  # good, warning, violation
        },
        {
            'date': target_date,
            'room_type': 'Deluxe Room',
            'our_rate': 1800,
            'booking_com': 1750,
            'expedia': 1820,
            'agoda': 1780,
            'hotels_com': 1800,
            'lowest_competitor': 1750,
            'price_position': 'competitive',
            'parity_status': 'good'
        },
        {
            'date': target_date,
            'room_type': 'Suite',
            'our_rate': 3000,
            'booking_com': 2800,
            'expedia': 2850,
            'agoda': 2900,
            'hotels_com': 2820,
            'lowest_competitor': 2800,
            'price_position': 'highest',
            'parity_status': 'warning'
        }
    ]

    return {
        'ota_prices': ota_prices,
        'date': target_date,
        'parity_violations': len([p for p in ota_prices if p['parity_status'] == 'violation']),
        'avg_our_rate': sum(p['our_rate'] for p in ota_prices) / len(ota_prices),
        'avg_market_rate': sum(p['lowest_competitor'] for p in ota_prices) / len(ota_prices)
    }


# 4. POST /api/sales/lead - Create new lead


@router.post("/sales/lead")
async def create_lead(
    request: CreateLeadRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_sales")),  # v92 DW
):
    """
    Create new sales lead
    """
    current_user = await get_current_user(credentials)

    lead = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_name': request.guest_name,
        'email': request.email,
        'phone': request.phone,
        'company': request.company,
        'stage': request.stage.value,
        'source': request.source,
        'notes': request.notes,
        'expected_checkin': request.expected_checkin,
        'expected_revenue': request.expected_revenue,
        'created_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat(),
        'updated_at': datetime.now(UTC).isoformat()
    }

    await db.leads.insert_one(lead)

    return {
        'message': 'Lead created',
        'lead_id': lead['id'],
        'stage': lead['stage']
    }


# 5. PUT /api/sales/lead/{lead_id}/stage - Update lead stage


@router.put("/sales/lead/{lead_id}/stage")
async def update_lead_stage(
    lead_id: str,
    request: UpdateLeadStageRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_sales")),  # v92 DW
):
    """
    Update lead pipeline stage
    """
    current_user = await get_current_user(credentials)

    lead = await db.leads.find_one({
        'id': lead_id,
        'tenant_id': current_user.tenant_id
    })

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await db.leads.update_one(
        {'id': lead_id},
        {
            '$set': {
                'stage': request.stage.value,
                'notes': request.notes,
                'updated_at': datetime.now(UTC).isoformat(),
                'updated_by': current_user.name
            }
        }
    )

    return {
        'message': 'Lead stage updated',
        'lead_id': lead_id,
        'new_stage': request.stage.value
    }


# ========== PMS LITE MARKETING LEADS ==========



@router.post("/leads")
async def create_public_pms_lite_lead(request: PmsLiteLeadCreateRequest, user_agent: str | None = Header(None), x_forwarded_for: str | None = Header(None)):
    """Public endpoint for PMS Lite landing leads (no auth).

    Idempotent for same phone within 5 minutes.
    """
    from datetime import timedelta

    phone = request.contact.phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")

    now = datetime.now(UTC)
    five_minutes_ago = now - timedelta(minutes=5)

    # Reuse same lead if same phone + property_name + source in last 5 minutes
    existing = await db.leads.find_one(
        {
            "contact.phone": phone,
            "hotel.property_name": request.hotel.property_name.strip(),
            "source": "pms_lite_landing",
            "created_at": {"$gte": five_minutes_ago.isoformat()},
        }
    )
    if existing:
        return {
            "ok": True,
            "lead_id": existing.get("lead_id") or existing.get("id"),
            "deduped": True,
        }

    lead_uuid = str(uuid.uuid4())

    meta = request.metadata or PmsLiteLeadMetadata()
    # Fill headers if not provided
    if user_agent and not meta.user_agent:
        meta.user_agent = user_agent
    if x_forwarded_for and not meta.ip:
        meta.ip = x_forwarded_for.split(",")[0].strip()

    doc = {
        "id": lead_uuid,
        "lead_id": lead_uuid,
        "created_at": now.isoformat(),
        "source": "pms_lite_landing",
        "status": PmsLiteLeadStatus.NEW.value,
        "note": None,
        "contact": request.contact.model_dump(),
        "hotel": request.hotel.model_dump(),
        "metadata": meta.model_dump(),
    }

    from security.search_normalize import apply_collection_normalized_fields
    apply_collection_normalized_fields(doc, collection="leads")
    await db.leads.insert_one(doc)

    return {"ok": True, "lead_id": lead_uuid, "deduped": False}


@router.get("/sales/follow-ups")
async def get_follow_ups(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get follow-up reminders for leads
    """
    current_user = await get_current_user(credentials)

    # Get leads that need follow-up (warm and hot stages)
    leads = []
    async for lead in db.leads.find({
        'tenant_id': current_user.tenant_id,
        'stage': {'$in': ['warm', 'hot']}
    }):
        updated_at = datetime.fromisoformat(lead['updated_at'].replace('Z', '+00:00'))
        days_since_update = (datetime.now(UTC) - updated_at).days

        if days_since_update > 3:  # Needs follow-up if no update in 3 days
            leads.append({
                'id': lead['id'],
                'guest_name': lead['guest_name'],
                'company': lead.get('company'),
                'stage': lead['stage'],
                'days_since_update': days_since_update,
                'expected_revenue': lead.get('expected_revenue', 0),
                'urgency': 'high' if days_since_update > 7 else 'medium'
            })

    leads.sort(key=lambda x: x['days_since_update'], reverse=True)

    return {
        'follow_ups': leads,
        'count': len(leads),
        'high_urgency': len([l for l in leads if l['urgency'] == 'high'])
    }


# ============================================================================
# RATE & DISCOUNT MANAGEMENT MOBILE
# ============================================================================



@router.get("/corporate/contracts")
async def get_corporate_contracts(
    status: str | None = None,  # active, expiring, expired
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get corporate contracts list
    """
    await get_current_user(credentials)

    today = datetime.now().date()

    contracts = [
        {
            'id': str(uuid.uuid4()),
            'company_name': 'Tech Solutions Ltd.',
            'contract_type': 'volume_based',
            'start_date': (today - timedelta(days=180)).isoformat(),
            'end_date': (today + timedelta(days=185)).isoformat(),
            'room_nights_committed': 500,
            'room_nights_used': 342,
            'contracted_rate': 1500,
            'discount_percentage': 25,
            'special_amenities': ['Free WiFi', 'Late Checkout', 'Meeting Room'],
            'contact_person': 'Ahmet Yilmaz',
            'contact_email': 'ahmet@techsolutions.com',
            'status': 'active',
            'days_until_expiry': 185
        },
        {
            'id': str(uuid.uuid4()),
            'company_name': 'Finance Corp',
            'contract_type': 'fixed_rate',
            'start_date': (today - timedelta(days=90)).isoformat(),
            'end_date': (today + timedelta(days=45)).isoformat(),
            'room_nights_committed': 200,
            'room_nights_used': 156,
            'contracted_rate': 1800,
            'discount_percentage': 20,
            'special_amenities': ['Breakfast', 'Airport Transfer'],
            'contact_person': 'Zeynep Kara',
            'contact_email': 'zeynep@financecorp.com',
            'status': 'expiring_soon',
            'days_until_expiry': 45
        }
    ]

    # Filter by status
    if status:
        if status == 'active':
            contracts = [c for c in contracts if c['days_until_expiry'] > 60]
        elif status == 'expiring':
            contracts = [c for c in contracts if 0 < c['days_until_expiry'] <= 60]
        elif status == 'expired':
            contracts = [c for c in contracts if c['days_until_expiry'] <= 0]

    return {
        'contracts': contracts,
        'count': len(contracts),
        'expiring_soon': len([c for c in contracts if 0 < c['days_until_expiry'] <= 30])
    }


# 2. GET /api/corporate/customers - Corporate customers


@router.get("/corporate/customers")
async def get_corporate_customers(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get corporate customer list
    """
    await get_current_user(credentials)

    customers = [
        {
            'company_name': 'Tech Solutions Ltd.',
            'total_bookings': 342,
            'total_revenue': 513000,
            'contract_status': 'active',
            'last_booking': (datetime.now() - timedelta(days=5)).isoformat()[:10],
            'contact_person': 'Ahmet Yılmaz',
            'vip_status': True
        },
        {
            'company_name': 'Finance Corp',
            'total_bookings': 156,
            'total_revenue': 280800,
            'contract_status': 'expiring_soon',
            'last_booking': (datetime.now() - timedelta(days=12)).isoformat()[:10],
            'contact_person': 'Zeynep Kara',
            'vip_status': True
        }
    ]

    return {
        'corporate_customers': customers,
        'count': len(customers),
        'total_revenue': sum(c['total_revenue'] for c in customers)
    }


# 4. GET /api/corporate/contracts/utilization - contract usage vs commitment


@router.get("/corporate/contracts/utilization")
async def get_corporate_contract_utilization(
    current_user: User = Depends(get_current_user)
):
    """Compute contract utilization metrics per corporate company

    - Uses companies collection (room_nights_commitment, contracted_rate)
    - Aggregates bookings by company_id
    - Returns list with commitment, actual room nights, revenue & utilization %
    """
    tenant_id = current_user.tenant_id

    # Fetch active companies with a commitment
    companies = await db.companies.find({
        'tenant_id': tenant_id,
        'status': CompanyStatus.ACTIVE,
        'room_nights_commitment': {'$gt': 0}
    }, {'_id': 0}).to_list(1000)

    if not companies:
        return {
            'contracts': [],
            'summary': {
                'total_companies': 0,
                'total_committed_nights': 0,
                'total_actual_nights': 0,
                'total_revenue': 0.0,
                'avg_utilization_pct': 0.0,
            }
        }

    company_ids = [c['id'] for c in companies]

    # Aggregate bookings per company
    pipeline = [
        {
            '$match': {
                'tenant_id': tenant_id,
                'company_id': {'$in': company_ids},
                'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}
            }
        },
        {
            '$project': {
                '_id': 0,
                'company_id': 1,
                # Night count per booking
                'nights': {
                    '$max': [
                        1,
                        {
                            '$dateDiff': {
                                'startDate': {'$toDate': '$check_in'},
                                'endDate': {'$toDate': '$check_out'},
                                'unit': 'day'
                            }
                        }
                    ]
                },
                'total_amount': 1,
            }
        },
        {
            '$group': {
                '_id': '$company_id',
                'room_nights': {'$sum': '$nights'},
                'revenue': {'$sum': '$total_amount'},
                'bookings_count': {'$sum': 1}
            }
        }
    ]

    agg_results = await db.bookings.aggregate(pipeline).to_list(1000)
    metrics_by_company = {item['_id']: item for item in agg_results}

    contracts = []
    total_committed = 0
    total_actual = 0
    total_revenue = 0.0

    for c in companies:
        comp_id = c['id']
        commit = c.get('room_nights_commitment', 0) or 0
        metrics = metrics_by_company.get(comp_id, {})
        actual_nights = int(metrics.get('room_nights', 0))
        revenue = float(metrics.get('revenue', 0.0))
        bookings_count = int(metrics.get('bookings_count', 0))

        utilization = 0.0
        if commit > 0:
            utilization = round((actual_nights / commit) * 100, 1)

        total_committed += commit
        total_actual += actual_nights
        total_revenue += revenue

        contracts.append({
            'company_id': comp_id,
            'company_name': c.get('name'),
            'corporate_code': c.get('corporate_code'),
            'contact_person': c.get('contact_person'),
            'contact_email': c.get('contact_email'),
            'room_nights_commitment': commit,
            'actual_room_nights': actual_nights,
            'bookings_count': bookings_count,
            'revenue': round(revenue, 2),
            'utilization_pct': utilization,
            'status': 'under_utilized' if utilization < 70 and commit > 0 else 'healthy'
        })

    if total_committed > 0:
        round((total_actual / total_committed) * 100, 1)


@router.get("/corporate/rates")
async def get_corporate_rates(
    company: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get corporate contract rates
    """
    await get_current_user(credentials)

    rates = [
        {
            'company': 'Tech Solutions Ltd.',
            'room_type': 'Standard',
            'rack_rate': 2000,
            'contract_rate': 1500,
            'discount_pct': 25,
            'min_nights': 1,
            'blackout_dates': []
        },
        {
            'company': 'Tech Solutions Ltd.',
            'room_type': 'Deluxe',
            'rack_rate': 2800,
            'contract_rate': 2100,
            'discount_pct': 25,
            'min_nights': 1,
            'blackout_dates': []
        },
        {
            'company': 'Finance Corp',
            'room_type': 'Standard',
            'rack_rate': 2000,
            'contract_rate': 1600,
            'discount_pct': 20,
            'min_nights': 2,
            'blackout_dates': ['2025-12-24', '2025-12-31']
        }
    ]

    if company:
        rates = [r for r in rates if r['company'] == company]

    return {
        'contract_rates': rates,
        'count': len(rates)
    }




@router.get("/corporate/rate-plans")
async def get_corporate_rate_plans(
    company_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get corporate rate plans - REAL DATA from database"""
    # Get rate plans from database
    query = {'tenant_id': current_user.tenant_id}
    if company_id:
        query['company_id'] = company_id

    rate_plans = await db.corporate_rate_plans.find(query, {'_id': 0}).to_list(100)

    # If no data in DB, return empty
    return {
        'rate_plans': rate_plans,
        'count': len(rate_plans)
    }


# 4. GET /api/corporate/alerts - Contract expiry alerts


@router.get("/corporate/alerts")
async def get_corporate_alerts(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get contract expiry and renewal alerts
    """
    await get_current_user(credentials)

    alerts = [
        {
            'id': str(uuid.uuid4()),
            'alert_type': 'contract_expiring',
            'severity': 'high',
            'company': 'Finance Corp',
            'message': 'Contract expires in 45 days',
            'days_remaining': 45,
            'action_required': 'Schedule renewal meeting',
            'contact_person': 'Zeynep Kara',
            'created_at': datetime.now().isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'alert_type': 'volume_milestone',
            'severity': 'medium',
            'company': 'Tech Solutions Ltd.',
            'message': '68% of committed room nights have been used',
            'days_remaining': 185,
            'action_required': 'Track usage',
            'contact_person': 'Ahmet Yilmaz',
            'created_at': datetime.now().isoformat()
        }
    ]

    return {
        'alerts': alerts,
        'count': len(alerts),
        'high_priority': len([a for a in alerts if a['severity'] == 'high'])
    }

