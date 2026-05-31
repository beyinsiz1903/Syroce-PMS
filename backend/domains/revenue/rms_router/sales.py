"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from shared_kernel import index_backstops
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


# Task #205/#231: unique-index backstops behind ``_assert_contract_unique``.
_CONTRACT_UNIQUE_BACKSTOPS = (
    ("rate_code", "uniq_corp_contract_rate_code"),
    ("contact_email", "uniq_corp_contract_contact_email"),
)
for _f, _n in _CONTRACT_UNIQUE_BACKSTOPS:
    index_backstops.register_expected(
        _n, collection="corporate_contracts", fields=["tenant_id", _f])


async def _ensure_contract_indexes() -> None:
    """Task #205/#231: DB-level partial unique indexes behind ``_assert_contract_unique``.

    The application-level read-then-insert guard has a race window: two
    near-simultaneous creates with the same rate_code/contact_email can both
    pass ``find_one`` and insert duplicates. The unique index makes the losing
    write fail with ``DuplicateKeyError`` (translated to the same 409). The
    partial filter scopes uniqueness to populated *string* values (``$gt: ""``
    + ``$type``) so blank/missing identifiers never collide — exactly matching
    the app guard which ignores blanks — and legacy null rows do not break the
    build.

    Task #231: each build is retried (subject to the helper's retry throttle)
    until it succeeds instead of caching a "ready" flag after a deferred build.
    The unique index is *global* across tenants, so duplicate rows in ANY hotel
    disable the backstop for everyone; retrying means cleaning that residue
    re-enables the safeguard on the next attempt without a restart. Deferred
    builds are surfaced via a log warning + Prometheus metric and an ops health
    check (see ``shared_kernel.index_backstops``).
    """
    for field, idx_name in _CONTRACT_UNIQUE_BACKSTOPS:
        async def _build(field=field, idx_name=idx_name) -> None:
            await db.corporate_contracts.create_index(
                [("tenant_id", 1), (field, 1)],
                unique=True,
                partialFilterExpression={field: {"$gt": "", "$type": "string"}},
                name=idx_name)

        await index_backstops.attempt_backstop(
            idx_name,
            collection="corporate_contracts",
            fields=["tenant_id", field],
            build=_build)


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
    await _ensure_contract_indexes()
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

    try:
        await db.corporate_contracts.insert_one(corporate_contract)
    except DuplicateKeyError as exc:
        # Lost the read-then-insert race: a concurrent create registered the
        # same rate_code/contact_email first. Surface the identical 409.
        field = "rate_code" if "rate_code" in str(exc) else "contact_email"
        raise HTTPException(
            status_code=409,
            detail=f"Bu {field} ile kayıtlı sözleşme zaten var")

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

    await _ensure_contract_indexes()
    await _assert_contract_unique(
        current_user.tenant_id, contract, exclude_id=contract_id)

    try:
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
    except DuplicateKeyError as exc:
        # Concurrent update raced us to the same rate_code/contact_email — 409.
        field = "rate_code" if "rate_code" in str(exc) else "contact_email"
        raise HTTPException(
            status_code=409,
            detail=f"Bu {field} ile kayıtlı sözleşme zaten var")

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

    if to_status == 'rejected' and not (body.reason or '').strip():
        raise HTTPException(
            status_code=400,
            detail="Reddetme için gerekçe (reason) zorunludur.")

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

    # Notify the contract owner/contact when the contract reaches a terminal
    # approval outcome (approved/rejected). Best-effort: a mail failure must
    # never break the state transition, so we swallow errors here. Rejections
    # include the reason so the owner can act without opening the approvals UI.
    notified = False
    if to_status in {'approved', 'rejected'}:
        notified = await _notify_contract_owner_approval(
            existing,
            to_status=to_status,
            reason=body.reason,
            actor=current_user.username,
        )

    return {
        'message': 'Contract approval transitioned',
        'contract_id': contract_id,
        'from_status': from_status,
        'approval_status': to_status,
        'owner_notified': notified,
    }


async def _notify_contract_owner_approval(
    contract: dict,
    *,
    to_status: str,
    reason: str | None,
    actor: str | None,
) -> bool:
    """Email the corporate-contract owner/contact about an approval outcome.

    Returns True when a provider accepted the message. Never raises: an email
    failure (bad address, provider down, missing key) must not roll back or
    block the approval transition that already committed to the DB.
    """
    try:
        from core.email import _is_valid_email, send_email
        from core.mailing_safe import safe_html_value

        to_addr = (contract.get('contact_email') or '').strip()
        if not _is_valid_email(to_addr):
            return False

        company = contract.get('company_name') or 'Sözleşme'
        contact_person = contract.get('contact_person') or ''
        rate_code = contract.get('rate_code') or '-'

        approved = to_status == 'approved'
        outcome_tr = 'Onaylandı' if approved else 'Reddedildi'
        accent = '#16a34a' if approved else '#dc2626'
        subject = f"Kurumsal sözleşme {outcome_tr.lower()} — {company}"

        greeting = (
            f"Sayın {safe_html_value(contact_person)},"
            if contact_person else "Merhaba,"
        )

        reason_html = ""
        if not approved and (reason or '').strip():
            reason_html = (
                "<p style='margin:0 0 8px;color:#0f172a;'>"
                "<b>Reddetme gerekçesi:</b></p>"
                f"<p style='margin:0 0 16px;color:#334155;'>"
                f"{safe_html_value(reason.strip())}</p>"
            )

        html = (
            "<div style='font-family:Helvetica,Arial,sans-serif;max-width:600px;"
            "margin:0 auto;padding:18px;color:#0f172a;'>"
            f"<h2 style='margin:0 0 8px;'>Kurumsal Sözleşme "
            f"<span style='color:{accent};'>{outcome_tr}</span></h2>"
            f"<p style='margin:0 0 16px;color:#334155;'>{greeting}</p>"
            f"<p style='margin:0 0 8px;color:#334155;'>"
            f"<b>{safe_html_value(company)}</b> firması için kurumsal "
            f"sözleşmeniz <b style='color:{accent};'>{outcome_tr.lower()}</b>."
            "</p>"
            f"<p style='margin:0 0 16px;color:#64748b;'>"
            f"Rate kodu: <b>{safe_html_value(str(rate_code))}</b></p>"
            f"{reason_html}"
            "<p style='font-size:11px;color:#94a3b8;margin-top:18px;'>"
            "Syroce PMS · Otomatik üretilmiş bildirim"
            "</p></div>"
        )

        res = await send_email(to=to_addr, subject=subject, html=html)
        return bool(res.get("sent"))
    except Exception:  # noqa: BLE001 — notification is best-effort
        import logging
        logging.getLogger(__name__).exception(
            "[contract-approval] owner notification failed for %s",
            contract.get('id'),
        )
        return False


@router.get("/sales/corporate-contract/{contract_id}/approval-history")
async def get_corporate_contract_approval_history(
    contract_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Return the approval lifecycle trail for a single corporate contract.

    Surfaces the ``approval_history`` written by
    ``transition_corporate_contract_approval`` (from/to status, reason, who,
    when) so finance/sales can audit who moved a contract through the workflow.
    Tenant-scoped: only the owning tenant can read its history.
    """
    current_user = await get_current_user(credentials)

    contract = await db.corporate_contracts.find_one(
        {'id': contract_id, 'tenant_id': current_user.tenant_id},
        {'id': 1, 'company_name': 1, 'approval_status': 1, 'approval_history': 1},
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    return {
        'contract_id': contract.get('id'),
        'company_name': contract.get('company_name'),
        'approval_status': contract.get('approval_status', 'draft'),
        'approval_history': contract.get('approval_history', []),
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

