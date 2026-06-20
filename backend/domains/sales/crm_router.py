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
    MarketingContactLeadRequest,
    PmsLiteLeadCreateRequest,
    PmsLiteLeadMetadata,
    PmsLiteLeadStatus,
    SupplierLeadRequest,
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

    # Boş sonuçta SAHTE müşteri (Ahmet/Ayşe) üretilmez -> gerçek sonuç (boşsa boş)
    return {
        'customers': customers[:limit],
        'count': count,
        'vip_count': vip_count,
        'corporate_count': corporate_count,
        'data_available': count > 0,
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

    # OTA fiyat takibi: gerçek OTA/kanal fiyat kaynağı yok -> fail-closed (fabrikasyon yok)
    return {
        'ota_prices': [],
        'date': target_date,
        'data_available': False,
        'message': 'OTA fiyat takibi yapılandırılmamış (gerçek OTA/kanal fiyat kaynağı yok).',
        'parity_violations': 0,
        'avg_our_rate': 0,
        'avg_market_rate': 0
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


async def _persist_public_lead(
    *,
    source: str,
    contact: dict,
    hotel: dict,
    note: str | None,
    dedup_query: dict,
    metadata: PmsLiteLeadMetadata | None,
    user_agent: str | None,
    x_forwarded_for: str | None,
) -> dict:
    """Shared writer for public marketing leads (no auth).

    Mirrors create_public_pms_lite_lead: nested contact/hotel doc, normalized
    search fields, 5-minute idempotency. Each public source lands in the same
    super-admin marketing inbox. Never logs request PII.
    """
    now = datetime.now(UTC)
    five_minutes_ago = now - timedelta(minutes=5)

    existing = await db.leads.find_one(
        {**dedup_query, "source": source, "created_at": {"$gte": five_minutes_ago.isoformat()}}
    )
    if existing:
        return {
            "ok": True,
            "lead_id": existing.get("lead_id") or existing.get("id"),
            "deduped": True,
        }

    meta = metadata or PmsLiteLeadMetadata()
    if user_agent and not meta.user_agent:
        meta.user_agent = user_agent
    if x_forwarded_for and not meta.ip:
        meta.ip = x_forwarded_for.split(",")[0].strip()

    lead_uuid = str(uuid.uuid4())
    doc = {
        "id": lead_uuid,
        "lead_id": lead_uuid,
        "created_at": now.isoformat(),
        "source": source,
        "status": PmsLiteLeadStatus.NEW.value,
        "note": note,
        "contact": contact,
        "hotel": hotel,
        "metadata": meta.model_dump(),
    }

    from security.search_normalize import apply_collection_normalized_fields
    apply_collection_normalized_fields(doc, collection="leads")
    await db.leads.insert_one(doc)

    return {"ok": True, "lead_id": lead_uuid, "deduped": False}


@router.post("/leads/contact")
async def create_public_marketing_lead(
    request: MarketingContactLeadRequest,
    user_agent: str | None = Header(None),
    x_forwarded_for: str | None = Header(None),
):
    """Public endpoint for the marketing-site contact form (no auth).

    Persists into the same super-admin marketing inbox as PMS Lite leads,
    tagged source="marketing_contact". Idempotent for same phone + company
    within 5 minutes.
    """
    note_parts = []
    if request.business_type:
        note_parts.append(f"İşletme türü: {request.business_type}")
    if request.message:
        note_parts.append(request.message)
    note = "\n\n".join(note_parts) or None

    contact = {
        "full_name": request.full_name,
        "phone": request.phone,
        "email": str(request.email),
    }
    hotel = {"property_name": request.company, "location": None, "rooms_count": None}

    return await _persist_public_lead(
        source="marketing_contact",
        contact=contact,
        hotel=hotel,
        note=note,
        dedup_query={"contact.phone": request.phone, "hotel.property_name": request.company},
        metadata=request.metadata,
        user_agent=user_agent,
        x_forwarded_for=x_forwarded_for,
    )


@router.post("/leads/supplier")
async def create_public_supplier_lead(
    request: SupplierLeadRequest,
    user_agent: str | None = Header(None),
    x_forwarded_for: str | None = Header(None),
):
    """Public endpoint for the supplier application form (no auth).

    Persists into the same super-admin marketing inbox, tagged
    source="supplier_application". Idempotent for same email + company within
    5 minutes.
    """
    note_parts = ["Tedarikçi başvurusu."]
    if request.tax_no:
        note_parts.append(f"Vergi No: {request.tax_no}")
    note = " ".join(note_parts)

    contact = {
        "full_name": request.company,
        "phone": request.phone,
        "email": str(request.email),
    }
    hotel = {"property_name": request.company, "location": None, "rooms_count": None}

    return await _persist_public_lead(
        source="supplier_application",
        contact=contact,
        hotel=hotel,
        note=note,
        dedup_query={"contact.email": str(request.email), "hotel.property_name": request.company},
        metadata=request.metadata,
        user_agent=user_agent,
        x_forwarded_for=x_forwarded_for,
    )


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
    Get corporate contracts list — gercek corporate_contracts kayitlarindan.
    Uydurma sozlesme (Tech Solutions/Finance Corp) URETME.
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()

    def _to_date(v):
        if v is None:
            return None
        try:
            return v.date() if hasattr(v, 'date') else datetime.fromisoformat(str(v)).date()
        except (ValueError, TypeError):
            return None

    contracts = []
    async for doc in db.corporate_contracts.find(
        {'tenant_id': current_user.tenant_id}, {'_id': 0}
    ).sort('start_date', -1):
        start_d = _to_date(doc.get('start_date'))
        end_d = _to_date(doc.get('end_date'))
        days_until_expiry = (end_d - today).days if end_d is not None else None

        contracts.append({
            'id': doc.get('id'),
            'company_name': doc.get('company_name'),
            'contract_type': doc.get('contract_type'),
            'start_date': start_d.isoformat() if start_d else None,
            'end_date': end_d.isoformat() if end_d else None,
            'room_nights_committed': doc.get('allotment', 0) or 0,
            'room_nights_used': doc.get('total_room_nights', 0) or 0,
            'contracted_rate': doc.get('negotiated_rate'),
            'discount_percentage': doc.get('discount_percentage', 0) or 0,
            'special_amenities': doc.get('special_amenities', []),
            'contact_person': doc.get('contact_person'),
            'contact_email': doc.get('contact_email'),
            'status': doc.get('status'),
            'days_until_expiry': days_until_expiry,
        })

    # Filter by status (days_until_expiry None = bitis tarihi bilinmiyor -> 'active' kabul)
    if status:
        if status == 'active':
            contracts = [c for c in contracts if c['days_until_expiry'] is None or c['days_until_expiry'] > 60]
        elif status == 'expiring':
            contracts = [c for c in contracts if c['days_until_expiry'] is not None and 0 < c['days_until_expiry'] <= 60]
        elif status == 'expired':
            contracts = [c for c in contracts if c['days_until_expiry'] is not None and c['days_until_expiry'] <= 0]

    expiring_soon = len([
        c for c in contracts
        if c['days_until_expiry'] is not None and 0 < c['days_until_expiry'] <= 30
    ])

    return {
        'contracts': contracts,
        'count': len(contracts),
        'expiring_soon': expiring_soon,
        'data_available': len(contracts) > 0,
        'message': None if contracts else 'Kurumsal sozlesme kaydi bulunamadi.',
    }


# 2. GET /api/corporate/customers - Corporate customers


@router.get("/corporate/customers")
async def get_corporate_customers(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get corporate customer list — gercek companies + bookings verisinden.
    Uydurma musteri (Tech Solutions/Finance Corp) URETME.
    """
    current_user = await get_current_user(credentials)
    tenant_id = current_user.tenant_id

    companies = await db.companies.find(
        {'tenant_id': tenant_id, 'status': CompanyStatus.ACTIVE},
        {'_id': 0}
    ).to_list(1000)

    if not companies:
        return {
            'corporate_customers': [],
            'count': 0,
            'total_revenue': 0.0,
            'data_available': False,
            'message': 'Aktif kurumsal musteri kaydi bulunamadi.',
        }

    company_ids = [c['id'] for c in companies]
    agg = await db.bookings.aggregate([
        {'$match': {
            'tenant_id': tenant_id,
            'company_id': {'$in': company_ids},
            'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}
        }},
        {'$group': {
            '_id': '$company_id',
            'total_bookings': {'$sum': 1},
            'total_revenue': {'$sum': '$total_amount'},
            'last_booking': {'$max': '$check_in'},
        }}
    ]).to_list(1000)
    by_company = {a['_id']: a for a in agg}

    customers = []
    grand_total = 0.0
    for c in companies:
        m = by_company.get(c['id'], {})
        revenue = float(m.get('total_revenue', 0) or 0)
        grand_total += revenue
        last_b = m.get('last_booking')
        customers.append({
            'company_name': c.get('name'),
            'total_bookings': int(m.get('total_bookings', 0) or 0),
            'total_revenue': round(revenue, 2),
            'contract_status': c.get('status'),
            'last_booking': str(last_b)[:10] if last_b else None,
            'contact_person': c.get('contact_person'),
            'vip_status': bool(c.get('vip', False)),
        })

    return {
        'corporate_customers': customers,
        'count': len(customers),
        'total_revenue': round(grand_total, 2),
        'data_available': True,
        'message': None,
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
            },
            'data_available': False,
            'message': 'Taahhutlu kurumsal sozlesme bulunamadi.',
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

    avg_utilization = round((total_actual / total_committed) * 100, 1) if total_committed > 0 else 0.0

    return {
        'contracts': contracts,
        'summary': {
            'total_companies': len(companies),
            'total_committed_nights': total_committed,
            'total_actual_nights': total_actual,
            'total_revenue': round(total_revenue, 2),
            'avg_utilization_pct': avg_utilization,
        },
        'data_available': True,
        'message': None,
    }


@router.get("/corporate/rates")
async def get_corporate_rates(
    company: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get corporate contract rates — gercek corporate_rate_plans kayitlarindan.
    Uydurma oran (Tech Solutions/Finance Corp) URETME.
    """
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if company:
        query['company_name'] = company

    rates = await db.corporate_rate_plans.find(query, {'_id': 0}).to_list(500)

    return {
        'contract_rates': rates,
        'count': len(rates),
        'data_available': len(rates) > 0,
        'message': None if rates else 'Kurumsal oran plani bulunamadi.',
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
    Get contract expiry and renewal alerts — gercek corporate_contracts'tan turetilir.
    Uydurma uyari (Finance Corp/Tech Solutions) URETME.
    """
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC).date()

    alerts = []
    async for doc in db.corporate_contracts.find(
        {'tenant_id': current_user.tenant_id}, {'_id': 0}
    ):
        end_date = doc.get('end_date')
        if end_date is None:
            continue
        try:
            end_d = end_date.date() if hasattr(end_date, 'date') else datetime.fromisoformat(str(end_date)).date()
        except (ValueError, TypeError):
            continue
        days_remaining = (end_d - today).days
        if 0 < days_remaining <= 60:
            alerts.append({
                'id': str(uuid.uuid4()),
                'alert_type': 'contract_expiring',
                'severity': 'high' if days_remaining <= 30 else 'medium',
                'company': doc.get('company_name'),
                'message': f'Sozlesme {days_remaining} gun icinde sona eriyor',
                'days_remaining': days_remaining,
                'action_required': 'Yenileme gorusmesi planlayin',
                'contact_person': doc.get('contact_person'),
                'created_at': datetime.now(UTC).isoformat(),
            })

    alerts.sort(key=lambda a: a['days_remaining'])

    return {
        'alerts': alerts,
        'count': len(alerts),
        'high_priority': len([a for a in alerts if a['severity'] == 'high']),
        'data_available': len(alerts) > 0,
        'message': None if alerts else 'Sozlesme suresi yaklasan kayit bulunamadi.',
    }

