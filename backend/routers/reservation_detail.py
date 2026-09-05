"""
Reservation Detail Router - Comprehensive reservation management endpoints
Provides full reservation detail view, folio operations, activity logging,
payment processing, cari transfers, room changes, and front office operations.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from bson import ObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import DuplicateKeyError

from core.business_date_service import ensure_business_date_initialized
from core.channel_room_charge_pricing import (
    analyze_legacy_double_tax_charge,
    is_channel_total_tax_inclusive,
)
from core.database import db
from core.reservation_mutability import ensure_reservation_mutable, reservation_is_historical
from core.security import get_current_user
from domains.channel_manager.providers.hotelrunner_notes import resolve_legacy_hotelrunner_note
from models.schemas import User, _ensure_hotel_context
from models.schemas.bookings import BookingCreate
from modules.pms_core.guest_identity import find_existing_guest_by_identity
from modules.pms_core.role_permission_service import (
    RolePermissionService,
    require_op,  # v97 DW
)
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.reservations.services.create_reservation_service import (
    CreateReservationService,
)
from routers.finance.konaklama_vergisi_core import get_accommodation_tax_rate
from security.field_encryption import get_field_encryption_service
from shared_kernel.idempotency import claim_short_window_dedup, release_idempotency

# Bug CP fix — shared role-permission enforcement for financial endpoints
_rps = RolePermissionService()
logger = logging.getLogger(__name__)


def _enforce_perm(role: str, op: str) -> None:
    _rps.enforce_permission(role, op)


def _cari_balance(account: dict) -> float:
    """Resolve legacy cari balance fields without losing posted receivables."""
    values = [float(account.get(field) or 0) for field in ("balance", "current_balance") if field in account]
    return max(values, default=0.0)


def _cari_account_lookup_filters(tenant_id: str, account_id: str) -> list[dict]:
    """Support both current UUID records and legacy Mongo-backed cari records."""
    raw_id = str(account_id or "").strip()
    lookup_values: list[object] = [raw_id]
    # Older cari imports stored otherwise identical identifiers as BSON numbers.
    # The list API serializes every identifier as a string for the browser, so a
    # transfer must restore the numeric candidate when looking the record up.
    if raw_id.isdecimal():
        lookup_values.append(int(raw_id))
    filters = [
        {"tenant_id": tenant_id, field: value}
        for field in ("id", "account_id", "legacy_id", "_id")
        for value in lookup_values
    ]
    if ObjectId.is_valid(raw_id):
        filters.append({"tenant_id": tenant_id, "_id": ObjectId(raw_id)})
    return filters


def _canonical_cari_account_id(account: dict) -> str:
    return str(
        account.get("id")
        or account.get("account_id")
        or account.get("legacy_id")
        or account.get("_id")
        or ""
    )


def _canonical_cari_account_name(account: dict) -> str:
    return str(
        account.get("name")
        or account.get("account_name")
        or account.get("company_name")
        or "Cari Hesap"
    )


def _cari_transfer_lookup_id(account: dict) -> str:
    """Expose the persisted Mongo identity used by the transfer write path."""
    return str(account.get("_id") or _canonical_cari_account_id(account))


async def _find_cari_account(
    tenant_id: str,
    account_id: str,
    *,
    account_name: str | None = None,
    session=None,
):
    """Return account, collection kind and its exact update filter."""
    find_kwargs = {"session": session} if session is not None else {}
    collections = (
        (getattr(db, "cari_accounts", None), False),
        (getattr(db, "city_ledger_accounts", None), True),
    )
    for collection, is_city_ledger in collections:
        if collection is None:
            continue
        for query in _cari_account_lookup_filters(tenant_id, account_id):
            account = await collection.find_one(query, **find_kwargs)
            if account:
                return account, is_city_ledger, query

    # BSON UUID representation settings can make a value query miss even when
    # the same persisted identity was serialized for the browser. On this
    # fallback path, inspect only this tenant's small account set and compare
    # the exact serialized identity exposed by ``list_cari_accounts``. Keep the
    # original ``_id`` object for the subsequent atomic update.
    raw_id = str(account_id or "").strip()
    serialized_matches = []
    for collection, is_city_ledger in collections:
        find = getattr(collection, "find", None) if collection is not None else None
        if find is None:
            continue
        cursor = find({"tenant_id": tenant_id}, **find_kwargs)
        async for account in cursor:
            identities = {
                _cari_transfer_lookup_id(account),
                _canonical_cari_account_id(account),
            }
            if raw_id in identities:
                serialized_matches.append((account, is_city_ledger))

    unique_serialized_matches = {}
    for account, is_city_ledger in serialized_matches:
        persisted_id = account.get("_id")
        identity = (is_city_ledger, type(persisted_id).__name__, repr(persisted_id))
        unique_serialized_matches[identity] = (account, is_city_ledger)
    if len(unique_serialized_matches) == 1:
        account, is_city_ledger = next(iter(unique_serialized_matches.values()))
        return account, is_city_ledger, {
            "tenant_id": tenant_id,
            "_id": account.get("_id"),
        }

    # Some legacy city-ledger rows have had their public and persisted IDs
    # regenerated independently. The account list still knows the row, but an
    # ID round-trip can therefore miss it. Allow the UI to supply the exact
    # displayed account name as a guarded fallback. Refuse ambiguous matches so
    # a financial posting can never be routed to an arbitrary account.
    normalized_name = str(account_name or "").strip()
    if not normalized_name:
        return None, False, None

    matches = []
    name_query = {
        "tenant_id": tenant_id,
        "$or": [
            {"name": normalized_name},
            {"account_name": normalized_name},
            {"company_name": normalized_name},
        ],
    }
    for collection, is_city_ledger in collections:
        if collection is None:
            continue
        account = await collection.find_one(name_query, **find_kwargs)
        if account:
            matches.append((account, is_city_ledger))

    unique_matches = {}
    for account, is_city_ledger in matches:
        identity = _cari_transfer_lookup_id(account)
        unique_matches[identity] = (account, is_city_ledger)
    if len(unique_matches) == 1:
        account, is_city_ledger = next(iter(unique_matches.values()))
        return account, is_city_ledger, {
            "tenant_id": tenant_id,
            "_id": account.get("_id"),
        }
    return None, False, None


def _extra_charge_total(charge: dict) -> float:
    """Resolve heterogeneous extra-charge totals while preserving an explicit zero."""
    for field in ("total", "charge_amount", "amount"):
        value = charge.get(field)
        if value is not None:
            return float(value)
    return 0.0


def _money_cents(value) -> int:
    """Compare money values without float rounding noise."""
    try:
        return int(
            (Decimal(str(value or 0)) * 100).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )
    except (ValueError, TypeError, ArithmeticError):
        return 0


def _room_charge_rate_mismatches(
    charges: list[dict],
    expected_rates_by_date: dict[str, float],
) -> list[dict]:
    """Return posted room charges that no longer equal their nightly gross rate."""
    mismatches: list[dict] = []
    for charge in charges:
        if charge.get("voided"):
            continue
        if charge.get("charge_category") != "room" and charge.get("charge_type") != "room_charge":
            continue
        charge_date = _reservation_calendar_date(charge.get("date"))
        if charge_date is None:
            continue
        date_key = charge_date.isoformat()
        expected = expected_rates_by_date.get(date_key)
        if expected is None:
            continue
        observed = charge.get("total", charge.get("amount", 0))
        if _money_cents(observed) != _money_cents(expected):
            mismatches.append(
                {
                    "date": date_key,
                    "charge_id": charge.get("id"),
                    "expected_total": round(float(expected), 2),
                    "posted_total": round(float(observed or 0), 2),
                }
            )
    return mismatches


async def _posted_room_charge_rate_mismatches(
    tenant_id: str,
    booking_id: str,
    *,
    expected_rates_by_date: dict[str, float] | None = None,
    session=None,
) -> list[dict]:
    """Load the posted-room-rate invariant without blocking legacy rows.

    Old reservations without any daily-rate rows cannot be compared safely.
    Once daily rates exist, however, a room charge must equal the stored gross
    rate before another payment may be accepted.
    """
    if not getattr(db, "daily_rates", None) or not getattr(db, "folio_charges", None):
        return []
    if expected_rates_by_date is None:
        rate_rows = [
            row
            async for row in db.daily_rates.find(
                {"tenant_id": tenant_id, "booking_id": booking_id},
                {"_id": 0, "date": 1, "rate": 1},
                **({"session": session} if session is not None else {}),
            )
        ]
        expected_rates_by_date = {}
        for row in rate_rows:
            rate_date = _reservation_calendar_date(row.get("date"))
            if rate_date is not None:
                expected_rates_by_date[rate_date.isoformat()] = float(row.get("rate", 0) or 0)

    if not expected_rates_by_date:
        return []

    charges = [
        row
        async for row in db.folio_charges.find(
            {
                "tenant_id": tenant_id,
                "booking_id": booking_id,
                "voided": {"$ne": True},
                "$or": [{"charge_category": "room"}, {"charge_type": "room_charge"}],
            },
            {"_id": 0, "id": 1, "date": 1, "amount": 1, "total": 1, "charge_category": 1, "charge_type": 1},
            **({"session": session} if session is not None else {}),
        )
    ]
    return _room_charge_rate_mismatches(charges, expected_rates_by_date)


_create_reservation_service = CreateReservationService()
_field_enc = get_field_encryption_service()


def _build_financial_summary(
    booking: dict,
    charges: list[dict],
    payments: list[dict],
    extra_charges: list[dict],
    deposits: list[dict],
) -> dict:
    """Build reservation and currently-posted folio financial totals.

    A stay can have only some of its nightly room charges posted while a night
    audit is in progress.  Keep the operational folio balance separate from
    the full reservation amount so the UI never makes a partially posted stay
    look as though part of its confirmed price disappeared.
    """
    active_charges = [charge for charge in charges if not charge.get("voided")]
    total_charges = sum(charge.get("total", charge.get("amount", 0)) for charge in active_charges)
    total_payments = sum(payment.get("amount", 0) for payment in payments if not payment.get("voided"))
    total_extra = sum(_extra_charge_total(charge) for charge in extra_charges if not charge.get("voided"))
    total_deposits = sum(
        max(
            0,
            float(deposit.get("amount", 0) or 0) - float(deposit.get("refunded_amount", 0) or 0),
        )
        for deposit in deposits
        if deposit.get("status") != "refunded"
    )

    room_charge_total = sum(
        charge.get("total", charge.get("amount", 0))
        for charge in active_charges
        if charge.get("charge_type") == "room_charge" or charge.get("charge_category") == "room"
    )
    # Accommodation taxes are generated together with the nightly room
    # charge.  They are not a receptionist-entered extra service, so they
    # must participate in the same agreed-price reconciliation.  Otherwise a
    # tax row created after a rate update is incorrectly presented as a new
    # guest debt even when the confirmed reservation total was paid in full.
    accommodation_tax_total = sum(
        charge.get("total", charge.get("amount", 0))
        for charge in active_charges
        if charge.get("charge_type") == "tax" or charge.get("charge_category") == "tax"
    )
    reservation_price_component_total = room_charge_total + accommodation_tax_total
    room_charge_posted = room_charge_total > 0
    unposted_room_total = 0 if room_charge_posted else booking.get("total_amount", 0)
    balance = unposted_room_total + total_charges + total_extra - total_payments
    folio_balance = total_charges + total_extra - total_payments
    # The confirmed stay total remains collectible even before every night is
    # posted to the folio.  ``max`` protects legacy bookings where the posted
    # room charge is already larger than the booking total (for example when a
    # separately-posted tax is excluded from the original total).
    reservation_total_due = (
        max(float(booking.get("total_amount", 0) or 0), float(reservation_price_component_total or 0))
        + (total_charges - reservation_price_component_total)
        + total_extra
        - total_payments
    )
    # A posted accommodation amount above the confirmed reservation total is
    # a pricing reconciliation problem, not an amount the receptionist should
    # collect.  This includes system-generated accommodation-tax rows.
    pricing_reconciliation_difference = round(
        max(0, float(reservation_price_component_total or 0) - float(booking.get("total_amount", 0) or 0)),
        2,
    )

    return {
        "total_amount": booking.get("total_amount", 0),
        "total_charges": round(total_charges, 2),
        "total_payments": round(total_payments, 2),
        "total_extra": round(total_extra, 2),
        "accommodation_tax_total": round(accommodation_tax_total, 2),
        "total_deposits": round(total_deposits, 2),
        "balance": round(balance, 2),
        "folio_balance": round(folio_balance, 2),
        "unposted_room_amount": round(max(0, float(booking.get("total_amount", 0) or 0) - float(room_charge_total or 0)), 2),
        "reservation_total_due": round(reservation_total_due, 2),
        "pricing_reconciliation_required": pricing_reconciliation_difference > 0.01,
        "pricing_reconciliation_difference": pricing_reconciliation_difference,
        "paid_amount": booking.get("paid_amount", 0),
    }


def _build_channel_pricing_issue(
    booking: dict,
    charges: list[dict],
    payments: list[dict],
    *,
    accommodation_tax_rate: float,
) -> dict | None:
    """Summarize only the exact, safely repairable legacy double-tax shape."""
    issues = [
        issue
        for charge in charges
        if (
            issue := analyze_legacy_double_tax_charge(
                booking,
                charge,
                accommodation_tax_rate=accommodation_tax_rate,
            )
        )
        is not None
    ]
    if not issues:
        return None
    has_payments = any(
        not payment.get("voided") and float(payment.get("amount", 0) or 0) > 0
        for payment in payments
    )
    return {
        "code": "CHANNEL_TOTAL_TAXED_TWICE",
        "charge_count": len(issues),
        "observed_total": round(sum(issue["observed_total"] for issue in issues), 2),
        "expected_total": round(sum(issue["expected_total"] for issue in issues), 2),
        "overcharge": round(sum(issue["overcharge"] for issue in issues), 2),
        "repairable": not has_payments,
        "blocked_reason": "payment_exists" if has_payments else None,
    }


async def _reservation_outstanding_balance(
    tenant_id: str,
    booking: dict,
    *,
    session=None,
) -> float:
    """Return the same booking-scoped balance shown by reservation detail."""
    query = {"booking_id": booking["id"], "tenant_id": tenant_id}

    async def collect(collection) -> list[dict]:
        kwargs = {"session": session} if session is not None else {}
        return [document async for document in collection.find(query, {"_id": 0}, **kwargs)]

    charges = await collect(db.folio_charges)
    payments = await collect(db.payments)
    extra_charges = await collect(db.extra_charges)
    deposits = await collect(db.deposits)
    summary = _build_financial_summary(
        booking,
        charges,
        payments,
        extra_charges,
        deposits,
    )
    return float(summary["balance"])


async def _run_reservation_financial_transaction(
    *,
    tenant_id: str,
    booking_id: str,
    resources: list[tuple[str, str]],
    callback,
):
    """Serialize and atomically commit a reservation financial mutation."""
    from core.booking_atomicity import with_resource_locks
    from core.database import client

    return await with_resource_locks(
        client=client,
        db=db,
        tenant_id=tenant_id,
        locks_collection="reservation_financial_locks",
        resources=[("booking", booking_id), *resources],
        callback=callback,
    )


async def _run_post_commit_hook(hook, *, operation: str) -> None:
    """Keep non-authoritative cache/audit hooks from obscuring a durable commit."""
    try:
        await hook()
    except Exception:
        logger.warning(
            "reservation financial post-commit hook failed",
            extra={"operation": operation},
        )


async def _release_dedup_safely(lock_id: str | None, *, operation: str) -> None:
    if not lock_id:
        return
    try:
        await release_idempotency(db, lock_id=lock_id)
    except Exception:
        logger.warning(
            "reservation financial dedup release failed",
            extra={"operation": operation},
        )


async def _refresh_cached_folio_balance(tenant_id: str, folio_id: str) -> float:
    """Keep the operational checkout cache aligned with durable folio rows."""
    from core.utils import calculate_folio_balance

    balance = await calculate_folio_balance(folio_id, tenant_id)
    await db.folios.update_one(
        {"id": folio_id, "tenant_id": tenant_id},
        {"$set": {"balance": balance}},
    )
    return balance


async def _ensure_reservation_folio(
    tenant_id: str,
    booking: dict,
    *,
    preferred_folio_id: str | None = None,
    session=None,
) -> dict:
    """Resolve the reservation folio used by deposits and their refunds.

    Deposits are payments, not room-price adjustments. They therefore need
    the same concrete folio link as regular payments so folio history and the
    cached outstanding balance stay in sync. ``preferred_folio_id`` keeps a
    refund on the original folio even when that folio has since been closed.
    """
    query = {"tenant_id": tenant_id}
    if preferred_folio_id:
        query["id"] = preferred_folio_id
    else:
        query.update({"booking_id": booking["id"], "status": "open"})

    kwargs = {"session": session} if session is not None else {}
    folio = await db.folios.find_one(query, {"_id": 0}, **kwargs)
    if folio:
        return folio

    # A legacy deposit may not have a folio_id. Reuse the reservation's open
    # folio before creating one so the guest never gets parallel folios.
    if preferred_folio_id:
        folio = await db.folios.find_one(
            {
                "tenant_id": tenant_id,
                "booking_id": booking["id"],
                "status": "open",
            },
            {"_id": 0},
            **kwargs,
        )
        if folio:
            return folio

    from core.utils import generate_folio_number

    now = datetime.now(UTC).isoformat()
    folio = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "booking_id": booking["id"],
        "folio_number": await generate_folio_number(tenant_id),
        "folio_type": "guest",
        "status": "open",
        "guest_id": booking.get("guest_id"),
        "balance": 0.0,
        "created_at": now,
        "updated_at": now,
    }
    await db.folios.insert_one({**folio}, **kwargs)
    return folio


# ── Group bookings cache (TTL 30s) ─────────────────────────────
# /pms/group-bookings list endpoint'i her grup için bookings.find()
# çağırıyordu (N+1). Single-query bucket pattern'a geçirdikten sonra
# tek tenant başına 30s'lik bir snapshot tutmak yeterli; mutasyon
# yapan endpoint'ler (create/check-in-all/check-out-all/add-room)
# tenant cache'ini düşürür.
from cache_manager import cache as _gb_cache  # noqa: E402

_GROUP_BOOKINGS_CACHE_TTL = 30
_GROUP_BOOKINGS_CACHE_PREFIX = "group_bookings_list"


def _gb_cache_key(tenant_id: str) -> str:
    return f"cache:{tenant_id}:{_GROUP_BOOKINGS_CACHE_PREFIX}"


def _invalidate_group_bookings_cache(tenant_id: str) -> None:
    _gb_cache.safe_invalidate(tenant_id, _GROUP_BOOKINGS_CACHE_PREFIX)


def _request_with_idempotency_key(req: Request, key: str) -> Request:
    """Aynı HTTP isteği içinde N alt-rezervasyon yaratırken her birine
    benzersiz Idempotency-Key enjekte eden ince sarmalayıcı."""
    headers = [(k, v) for k, v in req.scope["headers"] if k.lower() != b"idempotency-key"]
    headers.append((b"idempotency-key", key.encode()))
    new_scope = {**req.scope, "headers": headers}
    return Request(new_scope, req.receive)


router = APIRouter(prefix="/api/pms", tags=["reservation-detail"])


# ── Request/Response Models ──


class PaymentRecord(BaseModel):
    # Bug CP fix — financial input validation (positive amounts, sane bounds)
    amount: float = Field(..., gt=0, le=1e9)
    method: str = Field(..., min_length=1, max_length=50)  # cash, card, bank_transfer, online
    payment_type: str = Field("interim", max_length=50)  # prepayment, deposit, interim, final
    reference: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=2000)


class ChannelPricingRepairRequest(BaseModel):
    reason: str = Field(
        "Nihai rezervasyon tutarına mükerrer vergi eklenmesinin düzeltilmesi",
        min_length=10,
        max_length=500,
    )


class CariTransfer(BaseModel):
    amount: float = Field(..., gt=0, le=1e9)
    cari_account_id: str
    cari_account_name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)


class AgencyPaymentRecord(BaseModel):
    amount: float = Field(..., gt=0, le=1e9)
    agency_name: str | None = Field(None, max_length=200)
    reference: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=2000)


class ChargeSplit(BaseModel):
    charge_id: str
    target_folio_id: str | None = None
    target_booking_id: str | None = None
    split_amount: float = Field(..., gt=0, le=1e9)
    reason: str | None = Field(None, max_length=2000)


class NoteCreate(BaseModel):
    content: str
    note_type: str = "general"  # general, important, internal, guest_request


class RoomChangeRequest(BaseModel):
    new_room_id: str
    reason: str
    transfer_folio: bool = True


class EarlyCheckinRequest(BaseModel):
    checkin_time: str | None = None
    extra_charge: float = Field(0.0, ge=0, le=1e9)


class LateCheckoutRequest(BaseModel):
    checkout_time: str | None = None
    extra_charge: float = Field(0.0, ge=0, le=1e9)


class DepositRecord(BaseModel):
    amount: float = Field(..., gt=0, le=1e9)
    method: str = Field("cash", max_length=50)
    reference: str | None = Field(None, max_length=200)


class DailyRateEntry(BaseModel):
    # Bug CP Round-3 — typed entries prevent untyped/negative rates bypassing override gate
    date: str = Field(..., min_length=8, max_length=32)
    rate: float = Field(..., gt=0, le=1e9)


class DailyRateUpdate(BaseModel):
    rates: list[DailyRateEntry] = Field(..., min_length=1, max_length=400)


class CariAccountCreate(BaseModel):
    name: str
    account_type: str = "company"  # company, agency, individual
    company_id: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    credit_limit: float = 0.0
    payment_terms_days: int = 30


class ExtraChargeAdd(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field("other", max_length=50)  # room, food, beverage, minibar, spa, laundry, other
    amount: float = Field(..., gt=0, le=1e9)
    quantity: float = Field(1.0, gt=0, le=1e6)


class GuestUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    id_number: str | None = None
    nationality: str | None = None
    vip_status: bool | None = None


class NewGroupBookingRow(BaseModel):
    """Grup oluştururken aynı anda yaratılacak yeni rezervasyon."""

    guest_name: str
    room_id: str
    check_in: str
    check_out: str
    total_amount: float
    adults: int = 1
    children: int = 0


class GroupBookingCreate(BaseModel):
    group_name: str
    booking_ids: list[str] = []
    # Yeni: aynı dialog'tan toplu rezervasyon yaratıp gruba bağlama
    new_bookings: list[NewGroupBookingRow] = []


class GroupBookingAddRoom(BaseModel):
    booking_id: str


class CommunicationLogCreate(BaseModel):
    channel: str = "email"  # email, sms, phone, whatsapp
    direction: str = "outbound"  # inbound, outbound
    subject: str | None = None
    content: str
    recipient: str | None = None


class DepositRefund(BaseModel):
    deposit_id: str
    refund_amount: float = Field(..., gt=0, le=1e9)
    refund_method: str = Field("cash", max_length=50)
    reason: str | None = Field(None, max_length=2000)


# ── Helper ──


def _clean_doc(doc):
    """Remove MongoDB _id from document."""
    if doc and "_id" in doc:
        del doc["_id"]
    return doc


def _clean_docs(docs):
    """Remove MongoDB _id from list of documents."""
    return [_clean_doc(d) for d in docs]


def _reservation_calendar_date(value) -> date | None:
    """Best-effort calendar date parsing for legacy/provider reservations.

    Full-detail must remain readable even when an old imported reservation has
    a malformed date. Returning ``None`` simply suppresses generated daily-rate
    rows; it must not turn the entire reservation detail endpoint into a 500.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(normalized[:10])
        except ValueError:
            logger.warning("Invalid reservation date in full-detail response: %r", value)
            return None


async def _log_activity(tenant_id: str, booking_id: str, action: str, actor: str, details: dict = None):
    """Log an activity for a reservation."""
    log_entry = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "action": action,
        "actor": actor,
        "details": details or {},
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.reservation_activity_log.insert_one(log_entry)
    return log_entry


# ── Endpoints ──


@router.get("/reservations/{booking_id}/full-detail")
async def get_reservation_full_detail(booking_id: str, current_user: User = Depends(get_current_user), target_tenant: str | None = Header(None, alias="X-Tenant-ID")):
    """Get comprehensive reservation detail with all related data."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    is_cross_tenant = False
    if target_tenant and target_tenant != current_user.tenant_id:
        if current_user.role != "super_admin":
            # For non-super_admins, pretend the resource doesn't exist to prevent leakage
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        tid = target_tenant
        is_cross_tenant = True

    from core.tenant_db import tenant_context

    with tenant_context(tid):
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
        if not booking:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

        # Fetch related data in parallel-like fashion
        guest = None
        if booking.get("guest_id"):
            guest = await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0})

        room = None
        if booking.get("room_id"):
            room = await db.rooms.find_one({"id": booking["room_id"], "tenant_id": tid}, {"_id": 0})

        # Folios
        folios = []
        async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
            folios.append(f)

        # Charges per folio
        charges = []
        async for c in db.folio_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
            charges.append(c)

        # Payments per folio
        payments = []
        async for p in db.payments.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
            payments.append(p)

        # Extra charges
        extra_charges = []
        async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
            extra_charges.append(ec)

        # Notes
        notes = []
        async for n in db.reservation_notes.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
            notes.append(n)
        if not any(note.get("source") == "hotelrunner" for note in notes):
            provider_note = await resolve_legacy_hotelrunner_note(
                db,
                tenant_id=tid,
                booking=booking,
            )
            if provider_note and not any(
                str(note.get("content") or "").strip() == provider_note["content"]
                for note in notes
            ):
                notes.append(provider_note)
                notes.sort(key=lambda note: str(note.get("created_at") or ""), reverse=True)

        # Activity log / history
        history = []
        async for h in db.reservation_activity_log.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
            history.append(h)

        # Room move history
        room_moves = []
        async for rm in db.room_move_history.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("moved_at", -1):
            room_moves.append(rm)

        # Daily rates
        daily_rates = []
        async for dr in db.daily_rates.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("date", 1):
            daily_rates.append(dr)

        # If no daily rates exist, generate from booking
        if not daily_rates and booking.get("check_in") and booking.get("check_out"):
            ci = _reservation_calendar_date(booking["check_in"])
            co = _reservation_calendar_date(booking["check_out"])
            if ci is not None and co is not None:
                nights = max((co - ci).days, 1)
                nightly_rate = round(booking.get("total_amount", 0) / nights, 2) if nights > 0 else 0
                current = ci
                for _ in range(nights):
                    daily_rates.append(
                        {
                            "date": current.isoformat(),
                            "rate": nightly_rate,
                            "generated": True,
                        }
                    )
                    current = current + timedelta(days=1)

        # Guests associated with this booking
        guests_list = []
        if guest:
            guests_list.append(guest)
        # Also check for additional guests
        ag_links = await db.booking_guests.find(
            {"booking_id": booking_id, "tenant_id": tid},
            {"_id": 0},
        ).to_list(100)
        ag_ids = [
            link["guest_id"]
            for link in ag_links
            if link.get("guest_id") and link.get("guest_id") != booking.get("guest_id")
        ]
        if ag_ids:
            async for ag in db.guests.find({"id": {"$in": ag_ids}, "tenant_id": tid}, {"_id": 0}):
                guests_list.append(ag)
        # Older additional-guest records embedded the guest payload directly in
        # booking_guests. Keep them readable while all new writes use guest_id.
        known_guest_ids = {item.get("id") for item in guests_list if item.get("id")}
        for link in ag_links:
            if link.get("guest_id") or not link.get("name"):
                continue
            legacy_guest = {key: value for key, value in link.items() if key not in {"booking_id", "tenant_id"}}
            legacy_id = legacy_guest.get("id")
            if legacy_id and legacy_id in known_guest_ids:
                continue
            guests_list.append(legacy_guest)
            if legacy_id:
                known_guest_ids.add(legacy_id)

        # Company info
        company = None
        if booking.get("company_id"):
            company = await db.companies.find_one({"id": booking["company_id"], "tenant_id": tid}, {"_id": 0})

        # Communication logs
        communication_logs = []
        async for cl in db.communication_logs.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
            communication_logs.append(cl)

        # Deposits
        deposits = []
        async for dep in db.deposits.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
            deposits.append(dep)

        business_date = await ensure_business_date_initialized(db, tid)
        accommodation_tax_rate = await get_accommodation_tax_rate(
            tid,
            booking.get("check_in") or business_date["business_date"],
        )
        read_only = reservation_is_historical(booking, business_date["business_date"])

    summary = _build_financial_summary(booking, charges, payments, extra_charges, deposits)
    summary["channel_pricing_issue"] = _build_channel_pricing_issue(
        booking,
        charges,
        payments,
        accommodation_tax_rate=accommodation_tax_rate,
    )

    # Decrypt PII fields for authorized response (KVKK: only after auth/perm checks)
    try:
        if booking:
            booking = _field_enc.decrypt_document(booking, collection="bookings")
        if guest:
            guest = _field_enc.decrypt_document(guest, collection="guests")
        guests_list = [_field_enc.decrypt_document(g, collection="guests") for g in guests_list]
    except Exception:
        # Fail-open on decrypt errors: API still works, audit handled in service
        pass

    if is_cross_tenant:
        # Execute outside of the with block so it logs to the Super Admin's tenant
        with tenant_context(current_user.tenant_id):
            await db.audit_logs.insert_one(
                {"event_type": "super_admin_cross_tenant_access", "user_id": current_user.id, "resource": f"booking:{booking_id}", "target_tenant": target_tenant, "tenant_id": current_user.tenant_id}
            )

    return {
        "booking": booking,
        "guest": guest,
        "room": room,
        "company": company,
        "folios": folios,
        "charges": charges,
        "payments": payments,
        "extra_charges": extra_charges,
        "notes": notes,
        "history": history,
        "room_moves": room_moves,
        "daily_rates": daily_rates,
        "guests": guests_list,
        "communication_logs": communication_logs,
        "deposits": deposits,
        "summary": summary,
        "read_only": read_only,
        "business_date": business_date["business_date"],
    }


@router.post("/reservations/{booking_id}/repair-channel-pricing")
async def repair_channel_pricing(
    booking_id: str,
    data: ChannelPricingRepairRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("void_charge")),
):
    """Repair an exact legacy gross-total double-tax posting in place.

    The reservation, provider reference, folio, and room-charge ID are kept.
    Only an unpaid/uninvoiced night-audit charge matching the deterministic
    double-tax signature can be corrected. The before value is retained on the
    charge and in both reservation and tamper-evident audit streams.
    """
    _enforce_perm(current_user.role, "void_charge")
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": tid},
        {"_id": 0},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    accommodation_tax_rate = await get_accommodation_tax_rate(
        tid,
        booking.get("check_in"),
    )
    folios = [
        folio
        async for folio in db.folios.find(
            {"booking_id": booking_id, "tenant_id": tid},
            {"_id": 0, "id": 1},
        )
    ]
    resources = [("folio", folio["id"]) for folio in folios if folio.get("id")]

    async def _repair(session):
        locked_booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tid},
            {"_id": 0},
            session=session,
        )
        if not locked_booking:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

        charges = [
            charge
            async for charge in db.folio_charges.find(
                {"booking_id": booking_id, "tenant_id": tid},
                {"_id": 0},
                session=session,
            )
        ]
        issues = [
            (charge, issue)
            for charge in charges
            if (
                issue := analyze_legacy_double_tax_charge(
                    locked_booking,
                    charge,
                    accommodation_tax_rate=accommodation_tax_rate,
                )
            )
            is not None
        ]
        if not issues:
            return {
                "success": True,
                "already_repaired": True,
                "booking_id": booking_id,
                "message": "Rezervasyon fiyatı zaten doğru",
            }

        folio_ids = sorted({str(issue["folio_id"]) for _, issue in issues if issue.get("folio_id")})
        active_payment = await db.payments.find_one(
            {
                "tenant_id": tid,
                "$or": [
                    {"booking_id": booking_id},
                    {"folio_id": {"$in": folio_ids}},
                ],
                "voided": {"$ne": True},
                "amount": {"$gt": 0},
            },
            {"_id": 0, "id": 1},
            session=session,
        )
        if active_payment:
            raise HTTPException(
                status_code=409,
                detail="Ödeme bulunan rezervasyon otomatik düzeltilemez; finans onayı gerekir",
            )

        issued_invoice = await db.invoices.find_one(
            {
                "tenant_id": tid,
                "$or": [
                    {"booking_id": booking_id},
                    {"folio_id": {"$in": folio_ids}},
                ],
                "status": {"$nin": ["draft", "cancelled", "voided"]},
            },
            {"_id": 0, "id": 1},
            session=session,
        )
        if issued_invoice:
            raise HTTPException(
                status_code=409,
                detail="Faturalanmış rezervasyon otomatik düzeltilemez; iade/düzeltme belgesi gerekir",
            )

        now = datetime.now(UTC).isoformat()
        repaired_rows = []
        for charge, issue in issues:
            corrected = issue["corrected"]
            before = {
                "amount": charge.get("amount"),
                "unit_price": charge.get("unit_price"),
                "tax_rate": charge.get("tax_rate"),
                "tax_amount": charge.get("tax_amount"),
                "tax_breakdown": charge.get("tax_breakdown"),
                "total": charge.get("total"),
            }
            updated = await db.folio_charges.update_one(
                {
                    "id": charge["id"],
                    "tenant_id": tid,
                    "booking_id": booking_id,
                    "voided": {"$ne": True},
                    "total": charge.get("total"),
                },
                {
                    "$set": {
                        "amount": corrected["amount"],
                        "unit_price": corrected["unit_price"],
                        "tax_rate": corrected["tax_rate"],
                        "tax_amount": corrected["tax_amount"],
                        "tax_breakdown": corrected["tax_breakdown"],
                        "tax_inclusive": True,
                        "total": corrected["total"],
                        "pricing_repaired": True,
                        "pricing_repair_reason": data.reason,
                        "pricing_repair_before": before,
                        "pricing_repaired_at": now,
                        "pricing_repaired_by": current_user.id,
                    }
                },
                session=session,
            )
            if updated.modified_count != 1:
                raise HTTPException(
                    status_code=409,
                    detail="Folyo satırı eşzamanlı değişti; yenileyip tekrar deneyin",
                )
            repaired_rows.append(
                {
                    "charge_id": charge["id"],
                    "folio_id": charge.get("folio_id"),
                    "before_total": issue["observed_total"],
                    "after_total": issue["expected_total"],
                    "difference": issue["overcharge"],
                }
            )

        # Keep the cached operational balances aligned inside the same commit.
        for folio_id in folio_ids:
            active_charges = [
                row
                async for row in db.folio_charges.find(
                    {"folio_id": folio_id, "tenant_id": tid, "voided": {"$ne": True}},
                    {"_id": 0, "total": 1, "amount": 1},
                    session=session,
                )
            ]
            active_payments = [
                row
                async for row in db.payments.find(
                    {"folio_id": folio_id, "tenant_id": tid, "voided": {"$ne": True}},
                    {"_id": 0, "amount": 1},
                    session=session,
                )
            ]
            balance = round(
                sum(float(row.get("total", row.get("amount", 0)) or 0) for row in active_charges)
                - sum(float(row.get("amount", 0) or 0) for row in active_payments),
                2,
            )
            await db.folios.update_one(
                {"id": folio_id, "tenant_id": tid},
                {"$set": {"balance": balance, "updated_at": now}},
                session=session,
            )

        fallback_source = (
            "channel_manager"
            if is_channel_total_tax_inclusive(locked_booking)
            else "manual"
        )
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tid},
            {
                "$set": {
                    "pricing_tax_inclusive": True,
                    "pricing_source": locked_booking.get("pricing_source") or fallback_source,
                    "pricing_repaired_at": now,
                    "updated_at": now,
                }
            },
            session=session,
        )
        audit_details = {
            "reason": data.reason,
            "repairs": repaired_rows,
            "provider_reference": (
                locked_booking.get("external_confirmation")
                or locked_booking.get("external_reservation_id")
            ),
        }
        await db.reservation_activity_log.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "booking_id": booking_id,
                "action": "channel_pricing_repaired",
                "actor": current_user.name,
                "details": audit_details,
                "created_at": now,
            },
            session=session,
        )
        await db.pms_audit_trail.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "entity_type": "booking",
                "entity_id": booking_id,
                "action": "channel_pricing_repaired",
                "performed_by": current_user.id,
                "metadata": audit_details,
                "created_at": now,
            },
            session=session,
        )
        return {
            "success": True,
            "already_repaired": False,
            "booking_id": booking_id,
            "repaired_charges": repaired_rows,
            "total_reduction": round(sum(row["difference"] for row in repaired_rows), 2),
            "new_booking_balance": round(
                sum(
                    float(row.get("total", row.get("amount", 0)) or 0)
                    for row in charges
                    if not row.get("voided")
                )
                - sum(row["difference"] for row in repaired_rows),
                2,
            ),
        }

    return await _run_reservation_financial_transaction(
        tenant_id=tid,
        booking_id=booking_id,
        resources=resources,
        callback=_repair,
    )


@router.post("/reservations/{booking_id}/record-payment")
async def record_payment(
    booking_id: str,
    data: PaymentRecord,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Record a payment on the reservation's folio."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP fix
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    pricing_mismatches = await _posted_room_charge_rate_mismatches(tid, booking_id)
    if pricing_mismatches:
        raise HTTPException(
            status_code=409,
            detail="Oda tahakkuku ile günlük fiyat uyuşmuyor; finansal mutabakat tamamlanmadan ödeme alınamaz",
        )

    # Task #184 — Idempotency: aynı (tenant_id, booking_id, reference) ile gelen
    # retry/double-click/network-replay isteği misafiri çift kreditlememeli.
    # Bu kontrol folio create'ten ÖNCE yapılır; aksi halde idempotent retry
    # boş bir folio yaratır (yan-etki). Reference verilmişse önce mevcut
    # non-voided satırı ara; payload uyuşuyorsa orijinali döndür, farklıysa
    # 409 at. Race fast-path kaybederse insert sırasındaki DuplicateKeyError
    # partial-unique index garantisiyle yakalanır
    # (bkz. bootstrap/phases/perf_indexes.py uniq_payment_reference_active).
    ref_key = (data.reference or "").strip()
    if ref_key:
        existing = await db.payments.find_one(
            {"tenant_id": tid, "booking_id": booking_id, "reference": ref_key, "voided": False},
            {"_id": 0},
        )
        if existing:
            if (
                round(float(existing.get("amount") or 0), 2) != round(float(data.amount), 2)
                or (existing.get("method") or "") != data.method
                or (existing.get("payment_type") or "") != data.payment_type
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Duplicate payment reference with different payload",
                )
            await _refresh_cached_folio_balance(tid, existing["folio_id"])
            return {"success": True, "payment": existing, "idempotent": True}

    # No explicit reference -> server-side short-window guard so a double-click
    # (same booking + amount + method + type, seconds apart) cannot double-credit
    # the guest. Rejected (409), not replayed: without a client reference there
    # is no verifiable intent for a deliberate identical second payment.
    auto_lock_id = None
    if not ref_key:
        dedup = await claim_short_window_dedup(
            db,
            tenant_id=tid,
            scope=f"auto_payment_dedup:booking:{booking_id}",
            fingerprint=f"{round(float(data.amount), 2)}|{data.method}|{data.payment_type}",
        )
        if dedup["status"] == "duplicate":
            raise HTTPException(
                status_code=409,
                detail="Olası çift ödeme: aynı tutar saniyeler içinde tekrar gönderildi",
            )
        auto_lock_id = dedup["lock_id"]

    # Find or create folio. If this fails before the payment becomes durable,
    # free the auto-dedup slot so a legitimate retry is not blocked for the
    # whole window.
    try:
        folio = await db.folios.find_one({"booking_id": booking_id, "tenant_id": tid, "status": "open"}, {"_id": 0})
        if not folio:
            from core.utils import generate_folio_number

            folio_id = str(uuid.uuid4())
            folio = {
                "id": folio_id,
                "tenant_id": tid,
                "booking_id": booking_id,
                "folio_number": await generate_folio_number(tid),
                "folio_type": "guest",
                "status": "open",
                "guest_id": booking.get("guest_id"),
                "balance": 0.0,
                "created_at": datetime.now(UTC).isoformat(),
            }
            await db.folios.insert_one({**folio})
    except Exception:
        if auto_lock_id:
            await release_idempotency(db, lock_id=auto_lock_id)
        raise

    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "amount": data.amount,
        "method": data.method,
        "payment_type": data.payment_type,
        "status": "paid",
        "reference": ref_key or None,
        "notes": data.notes,
        "processed_by": current_user.name,
        "processed_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    try:
        await db.payments.insert_one({**payment})
    except Exception as exc:
        from pymongo.errors import DuplicateKeyError

        if isinstance(exc, DuplicateKeyError) and ref_key:
            existing = await db.payments.find_one(
                {"tenant_id": tid, "booking_id": booking_id, "reference": ref_key, "voided": False},
                {"_id": 0},
            )
            if existing:
                await _refresh_cached_folio_balance(tid, existing["folio_id"])
                return {"success": True, "payment": existing, "idempotent": True}
            raise HTTPException(status_code=409, detail="Duplicate payment reference") from exc
        # Payment never became durable -> free the auto-dedup slot for a retry.
        if auto_lock_id:
            await release_idempotency(db, lock_id=auto_lock_id)
        raise

    # Update booking paid_amount
    new_paid = (booking.get("paid_amount", 0) or 0) + data.amount
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"paid_amount": round(new_paid, 2)}},
    )
    await _refresh_cached_folio_balance(tid, folio["id"])

    await _log_activity(
        tid,
        booking_id,
        "payment_recorded",
        current_user.name,
        {
            "amount": data.amount,
            "method": data.method,
            "payment_type": data.payment_type,
        },
    )

    # Acente webhook: rezervasyon güncellendi (ödeme alındı → bakiye değişti)
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    schedule_emit_reservation_updated(
        tid,
        booking_id,
        "payment_added",
        {"payment_id": payment["id"], "amount": data.amount, "method": data.method, "payment_type": data.payment_type},
    )

    payment.pop("_id", None)
    return {"success": True, "payment": payment}


@router.post("/reservations/{booking_id}/complete-pending-room-charge")
async def complete_pending_room_charge(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Repair a historical folio credit caused by a missing final room charge.

    Normal checkout performs this automatically.  The endpoint is deliberately
    limited to an already checked-out reservation so it cannot be used as a
    substitute for nightly posting on an active stay.
    """
    _enforce_perm(current_user.role, "checkout")
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    if booking.get("status") != "checked_out":
        raise HTTPException(status_code=409, detail="Tahakkuk tamamlama yalnızca çıkışı yapılmış rezervasyonlarda kullanılabilir")

    from core.folio_checkout_reconciliation import reconcile_unposted_room_charge

    try:
        result = await reconcile_unposted_room_charge(
            db,
            tenant_id=tid,
            booking=booking,
            posted_by=f"historical_checkout_repair:{current_user.name}",
            allow_closed_folio=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if result["posted"]:
        await _log_activity(
            tid,
            booking_id,
            "pending_room_charge_completed",
            current_user.name,
            {"amount": result["amount"], "charge_id": result["charge_id"]},
        )
    return {"success": True, **result}


@router.get("/cari-transfer-resolution")
async def diagnose_cari_transfer_resolution(
    booking_id: str,
    account_id: str,
    account_name: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),
):
    """Read-only check for the identities required by a cari transfer."""
    _enforce_perm(current_user.role, "post_payment")
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": tid},
        {"_id": 0, "id": 1},
    )
    account, is_city_ledger, _ = await _find_cari_account(
        tid,
        account_id,
        account_name=account_name,
    )
    return {
        "booking_found": bool(booking),
        "account_found": bool(account),
        "account_collection": "city_ledger_accounts" if account and is_city_ledger else "cari_accounts" if account else None,
        "canonical_account_id": _canonical_cari_account_id(account) if account else None,
        "transfer_id": _cari_transfer_lookup_id(account) if account else None,
        "persisted_id_type": type(account.get("_id")).__name__ if account else None,
    }


@router.post("/reservations/{booking_id}/transfer-to-cari")
async def transfer_to_cari(
    booking_id: str,
    data: CariTransfer,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Transfer an amount from reservation folio to a cari (account receivable) account."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP fix
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(
            status_code=409,
            detail="Cari aktarımı için rezervasyon başlangıçta bulunamadı",
        )

    outstanding_balance = await _reservation_outstanding_balance(tid, booking)
    if outstanding_balance <= 0:
        raise HTTPException(status_code=409, detail="Cariye aktarılacak açık bakiye bulunmuyor")
    if data.amount - outstanding_balance > 0.005:
        raise HTTPException(status_code=409, detail="Cari aktarım tutarı açık bakiyeyi aşamaz")

    cari, resolved_is_city_ledger, resolved_cari_filter = await _find_cari_account(
        tid,
        data.cari_account_id,
        account_name=data.cari_account_name,
    )
    if not cari:
        raise HTTPException(
            status_code=409,
            detail="Cari aktarımı için seçilen cari başlangıçta çözümlenemedi",
        )

    folio = await db.folios.find_one(
        {"booking_id": booking_id, "tenant_id": tid, "status": "open"},
        {"_id": 0},
    )
    prepared_folio_number = None
    if not folio:
        from core.utils import generate_folio_number

        prepared_folio_number = await generate_folio_number(tid)

    dedup = await claim_short_window_dedup(
        db,
        tenant_id=tid,
        scope=f"cari_transfer:booking:{booking_id}",
        fingerprint=f"{round(float(data.amount), 2)}|{data.cari_account_id}",
    )
    if dedup["status"] == "duplicate":
        raise HTTPException(
            status_code=409,
            detail="Olası çift cari aktarımı: aynı işlem saniyeler içinde tekrar gönderildi",
        )
    dedup_lock_id = dedup["lock_id"]

    now = datetime.now(UTC).isoformat()
    transaction_id = str(uuid.uuid4())
    payment_id = str(uuid.uuid4())
    commit_stage = {"name": "transaction başlangıcı"}

    async def _commit(session):
        commit_stage["name"] = "rezervasyon yeniden okuma"
        current_booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tid},
            {"_id": 0},
            session=session,
        )
        if not current_booking:
            raise HTTPException(
                status_code=409,
                detail="Cari aktarım transaction'ında rezervasyon yeniden okunamadı",
            )

        commit_stage["name"] = "cari hesabı yeniden okuma"
        current_is_city_ledger = resolved_is_city_ledger
        current_cari_filter = resolved_cari_filter
        current_cari_collection = (
            db.city_ledger_accounts if current_is_city_ledger else db.cari_accounts
        )
        current_cari = await current_cari_collection.find_one(
            current_cari_filter,
            session=session,
        )
        if not current_cari:
            raise HTTPException(
                status_code=409,
                detail="Cari aktarım transaction'ında çözümlenen cari yeniden okunamadı",
            )
        canonical_account_id = _canonical_cari_account_id(current_cari)

        commit_stage["name"] = "açık bakiye doğrulama"
        current_outstanding = await _reservation_outstanding_balance(
            tid,
            current_booking,
            session=session,
        )
        if current_outstanding <= 0:
            raise HTTPException(status_code=409, detail="Cariye aktarılacak açık bakiye bulunmuyor")
        if data.amount - current_outstanding > 0.005:
            raise HTTPException(status_code=409, detail="Cari aktarım tutarı açık bakiyeyi aşamaz")

        commit_stage["name"] = "folyo hazırlama"
        current_folio = await db.folios.find_one(
            {"booking_id": booking_id, "tenant_id": tid, "status": "open"},
            {"_id": 0},
            session=session,
        )
        if not current_folio:
            current_folio = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "booking_id": booking_id,
                "folio_number": prepared_folio_number,
                "folio_type": "guest",
                "status": "open",
                "guest_id": current_booking.get("guest_id"),
                "balance": 0.0,
                "created_at": now,
            }
            await db.folios.insert_one({**current_folio}, session=session)

        commit_stage["name"] = "cari hareketi oluşturma"
        transaction = {
            "id": transaction_id,
            "tenant_id": tid,
            "booking_id": booking_id,
            "transaction_type": "charge",
            "amount": data.amount,
            "description": data.description or f"Rezervasyon {booking_id} - Cariye aktarım",
            "posted_by": current_user.name,
            "created_at": now,
        }
        if current_is_city_ledger:
            transaction["account_id"] = canonical_account_id
            transaction["transaction_date"] = now
            await db.city_ledger_transactions.insert_one({**transaction}, session=session)
        else:
            transaction["cari_account_id"] = canonical_account_id
            await db.cari_transactions.insert_one({**transaction}, session=session)

        commit_stage["name"] = "folyo ödemesi oluşturma"
        payment = {
            "id": payment_id,
            "tenant_id": tid,
            "folio_id": current_folio["id"],
            "booking_id": booking_id,
            "amount": data.amount,
            "method": "city_ledger",
            "payment_type": "city_ledger_transfer",
            "status": "paid",
            "reference": f"cari-transfer:{transaction_id}",
            "cari_account_id": canonical_account_id,
            "notes": data.description,
            "processed_by": current_user.name,
            "processed_at": now,
            "voided": False,
        }
        await db.payments.insert_one({**payment}, session=session)

        commit_stage["name"] = "cari bakiyesi güncelleme"
        if current_is_city_ledger:
            new_cari_balance = float(current_cari.get("current_balance", 0.0) or 0) + data.amount
            await db.city_ledger_accounts.update_one(
                current_cari_filter,
                {"$set": {"current_balance": new_cari_balance}},
                session=session,
            )
        else:
            new_cari_balance = _cari_balance(current_cari) + data.amount
            await db.cari_accounts.update_one(
                current_cari_filter,
                {
                    "$set": {
                        "balance": new_cari_balance,
                        "current_balance": new_cari_balance,
                    }
                },
                session=session,
            )

        commit_stage["name"] = "rezervasyon ödenen tutarı güncelleme"
        new_paid = float(current_booking.get("paid_amount", 0) or 0) + data.amount
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tid},
            {"$set": {"paid_amount": round(new_paid, 2)}},
            session=session,
        )

        transaction.pop("_id", None)
        payment.pop("_id", None)
        return {
            "success": True,
            "transaction": transaction,
            "payment": payment,
            "folio_id": current_folio["id"],
            "cari_account_id": canonical_account_id,
            "cari_name": _canonical_cari_account_name(current_cari),
            "remaining_balance": round(max(0.0, current_outstanding - data.amount), 2),
        }

    try:
        result = await _run_reservation_financial_transaction(
            tenant_id=tid,
            booking_id=booking_id,
            resources=[("cari_account", data.cari_account_id)],
            callback=_commit,
        )
    except DuplicateKeyError:
        await _release_dedup_safely(dedup_lock_id, operation="transfer_to_cari")
        raise HTTPException(
            status_code=409,
            detail="Cari aktarımı eşzamanlı veya tekrarlanan işlem nedeniyle tamamlanamadı",
        ) from None
    except HTTPException:
        await _release_dedup_safely(dedup_lock_id, operation="transfer_to_cari")
        raise
    except Exception:
        await _release_dedup_safely(dedup_lock_id, operation="transfer_to_cari")
        logger.exception(
            "cari transfer transaction failed",
            extra={"stage": commit_stage["name"]},
        )
        raise HTTPException(
            status_code=409,
            detail=f"Cari aktarımı {commit_stage['name']} aşamasında tamamlanamadı",
        ) from None

    await _run_post_commit_hook(
        lambda: _refresh_cached_folio_balance(tid, result["folio_id"]),
        operation="transfer_to_cari_cache",
    )

    await _run_post_commit_hook(
        lambda: _log_activity(
            tid,
            booking_id,
            "transferred_to_cari",
            current_user.name,
            {
                "amount": data.amount,
                "cari_account": result["cari_name"],
                "cari_account_id": result["cari_account_id"],
            },
        ),
        operation="transfer_to_cari_activity",
    )

    result.pop("folio_id", None)
    result.pop("cari_name", None)
    return result


@router.post("/reservations/{booking_id}/record-agency-payment")
async def record_agency_payment(
    booking_id: str,
    data: AgencyPaymentRecord,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Record a payment made by an agency."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP fix
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    pricing_mismatches = await _posted_room_charge_rate_mismatches(tid, booking_id)
    if pricing_mismatches:
        raise HTTPException(
            status_code=409,
            detail="Oda tahakkuku ile günlük fiyat uyuşmuyor; finansal mutabakat tamamlanmadan ödeme alınamaz",
        )

    folio = await db.folios.find_one({"booking_id": booking_id, "tenant_id": tid, "status": "open"}, {"_id": 0})
    if not folio:
        from core.utils import generate_folio_number

        folio_id = str(uuid.uuid4())
        folio = {
            "id": folio_id,
            "tenant_id": tid,
            "booking_id": booking_id,
            "folio_number": await generate_folio_number(tid),
            "folio_type": "agency",
            "status": "open",
            "guest_id": booking.get("guest_id"),
            "balance": 0.0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.folios.insert_one({**folio})

    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "amount": data.amount,
        "method": "agency",
        "payment_type": "agency_payment",
        "status": "paid",
        "reference": data.reference,
        "notes": data.notes,
        "agency_name": data.agency_name or booking.get("source_channel", ""),
        "processed_by": current_user.name,
        "processed_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    await db.payments.insert_one({**payment})

    new_paid = (booking.get("paid_amount", 0) or 0) + data.amount
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"paid_amount": round(new_paid, 2)}},
    )

    await _log_activity(
        tid,
        booking_id,
        "agency_payment_recorded",
        current_user.name,
        {
            "amount": data.amount,
            "agency_name": data.agency_name,
        },
    )

    payment.pop("_id", None)
    return {"success": True, "payment": payment}


@router.post("/reservations/{booking_id}/split-charge")
async def split_charge(
    booking_id: str,
    data: ChargeSplit,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v97 DW
):
    """Split a charge from one folio to another (e.g., transfer part of a meal to another room)."""
    _enforce_perm(current_user.role, "split_folio")  # Bug CP fix
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Find the original charge
    charge = await db.folio_charges.find_one({"id": data.charge_id, "tenant_id": tid}, {"_id": 0})
    if not charge:
        # Also check extra_charges
        charge = await db.extra_charges.find_one({"id": data.charge_id, "tenant_id": tid}, {"_id": 0})
        if not charge:
            raise HTTPException(status_code=404, detail="Masraf bulunamadı")

    original_amount = charge.get("total", charge.get("amount", charge.get("charge_amount", 0)))
    if data.split_amount > original_amount:
        raise HTTPException(status_code=400, detail="Bölünecek tutar orijinal tutardan büyük olamaz")

    # Determine target
    target_booking_id = data.target_booking_id
    target_folio_id = data.target_folio_id

    if target_booking_id:
        target_booking = await db.bookings.find_one({"id": target_booking_id, "tenant_id": tid}, {"_id": 0})
        if not target_booking:
            raise HTTPException(status_code=404, detail="Hedef rezervasyon bulunamadı")

        target_folio = await db.folios.find_one({"booking_id": target_booking_id, "tenant_id": tid, "status": "open"}, {"_id": 0})
        if not target_folio:
            from core.utils import generate_folio_number

            target_folio = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "booking_id": target_booking_id,
                "folio_number": await generate_folio_number(tid),
                "folio_type": "guest",
                "status": "open",
                "guest_id": target_booking.get("guest_id"),
                "balance": 0.0,
                "created_at": datetime.now(UTC).isoformat(),
            }
            await db.folios.insert_one({**target_folio})
        target_folio_id = target_folio["id"]

    # Create the split charge on target
    new_charge = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": target_folio_id,
        "booking_id": target_booking_id or charge.get("booking_id"),
        "charge_category": charge.get("charge_category", charge.get("category", "other")),
        "description": f"[Aktarım] {charge.get('description', charge.get('charge_name', ''))}",
        "unit_price": data.split_amount,
        "quantity": 1.0,
        "amount": data.split_amount,
        "tax_amount": 0.0,
        "total": data.split_amount,
        "date": datetime.now(UTC).isoformat(),
        "posted_by": current_user.name,
        "voided": False,
        "split_from_charge_id": data.charge_id,
        "split_from_booking_id": booking_id,
    }
    await db.folio_charges.insert_one({**new_charge})

    # Update original charge amount
    new_original_amount = original_amount - data.split_amount
    collection = "folio_charges" if "folio_id" in charge else "extra_charges"
    amount_field = "total" if "total" in charge else ("amount" if "amount" in charge else "charge_amount")
    await getattr(db, collection).update_one(
        {"id": data.charge_id, "tenant_id": tid},
        {"$set": {amount_field: round(new_original_amount, 2)}},
    )

    # Log split operation
    split_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "operation_type": "split",
        "from_folio_id": charge.get("folio_id"),
        "to_folio_id": target_folio_id,
        "from_booking_id": booking_id,
        "to_booking_id": target_booking_id,
        "charge_ids": [data.charge_id],
        "amount": data.split_amount,
        "reason": data.reason or "Masraf bölme",
        "performed_by": current_user.name,
        "performed_at": datetime.now(UTC).isoformat(),
    }
    await db.folio_operations.insert_one({**split_log})

    await _log_activity(
        tid,
        booking_id,
        "charge_split",
        current_user.name,
        {
            "charge_id": data.charge_id,
            "split_amount": data.split_amount,
            "target_booking_id": target_booking_id,
            "reason": data.reason,
        },
    )

    new_charge.pop("_id", None)
    return {"success": True, "new_charge": new_charge, "remaining_amount": round(new_original_amount, 2)}


@router.post("/reservations/{booking_id}/ensure-folio")
async def ensure_folio(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v97 DW
):
    """Idempotently ensure an OPEN guest folio exists for the reservation.

    Folyo Böl akışı için: bir rezervasyonda masraf (örn. restoran) bulunsa bile
    folio belgesi yalnızca ödeme/bölme anında tembel oluşturulduğu için
    `db.folios` boş kalabilir. Bu uç nokta, aynı record-payment / split-charge
    yollarındaki "find or create folio" desenini izleyerek:
      - Zaten AÇIK bir folio varsa onu olduğu gibi döndürür (mutasyon yok).
      - Aksi halde yeni bir açık misafir folyosu oluşturur ve YALNIZCA bu
        booking kapsamındaki orphan masrafları (folio_id boş veya bu booking'e
        ait hiçbir folioya işaret etmeyen) yeni folioya bağlar (orphan backfill).
    Geniş/pilot mutasyon yapılmaz; yalnızca ilgili booking'in masrafları işlenir.

    Kapsam kararı (Task #425): `extra_charges` (booking kapsamlı, folio_id'siz
    ekstra masraflar) burada KASITLI olarak migrate EDİLMEZ. Bunlar
    `calculate_folio_balance`'a dâhil değildir; ensure-folio'da topluca
    folio_charges'a çevirmek, split yapılmasa bile her booking için folio
    bakiyesi semantiğini değiştirirdi. Bunun yerine ekstra masraflar split
    motoru tarafından talep üzerine (yalnızca seçilenler) hedef folioya
    normalize edilip taşınır (bkz. FolioHardeningService.split_folio).
    """
    _enforce_perm(current_user.role, "split_folio")  # Bug CP fix
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    # Zaten açık folio varsa onu döndür — yeni oluşturma / mutasyon yok.
    existing = await db.folios.find_one({"booking_id": booking_id, "tenant_id": tid, "status": "open"}, {"_id": 0})
    if existing:
        return {"success": True, "folio": existing, "created": False, "bound_charges": 0}

    # Bu booking'e ait TÜM folio id'lerini topla (örn. kapanmış folyolar) ki
    # kapalı bir folyoya bağlı masrafları yanlışlıkla yeniden bağlamayalım.
    existing_folio_ids: set[str] = set()
    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0, "id": 1}):
        if f.get("id"):
            existing_folio_ids.add(f["id"])

    # Yeni açık misafir folyosu oluştur.
    from core.utils import generate_folio_number

    folio_id = str(uuid.uuid4())
    folio = {
        "id": folio_id,
        "tenant_id": tid,
        "booking_id": booking_id,
        "folio_number": await generate_folio_number(tid),
        "folio_type": "guest",
        "status": "open",
        "guest_id": booking.get("guest_id"),
        "balance": 0.0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.folios.insert_one({**folio})

    # Orphan backfill — yalnızca bu booking kapsamında: folio_id boş veya bu
    # booking'e ait mevcut hiçbir folioya işaret etmeyen masrafları bağla.
    bound = 0
    async for c in db.folio_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0, "id": 1, "folio_id": 1}):
        fid = c.get("folio_id")
        if not fid or fid not in existing_folio_ids:
            await db.folio_charges.update_one(
                {"id": c["id"], "tenant_id": tid},
                {"$set": {"folio_id": folio_id}},
            )
            bound += 1

    # Yeni folyonun bakiyesini bağlanan masraflardan yeniden hesapla.
    try:
        from modules.pms_core.folio_hardening_service import FolioHardeningService

        await FolioHardeningService()._recalculate_folio_balance(tid, folio_id)
        refreshed = await db.folios.find_one({"id": folio_id, "tenant_id": tid}, {"_id": 0})
        if refreshed:
            folio = refreshed
    except Exception:
        # Bakiye hesaplaması başarısız olsa bile folio oluştu ve masraflar bağlandı.
        pass

    await _log_activity(
        tid,
        booking_id,
        "folio_ensured",
        current_user.name,
        {
            "folio_id": folio_id,
            "bound_charges": bound,
        },
    )

    folio.pop("_id", None)
    return {"success": True, "folio": folio, "created": True, "bound_charges": bound}


@router.post("/reservations/{booking_id}/add-note")
async def add_reservation_note(
    booking_id: str,
    data: NoteCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Add a note to a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    await ensure_reservation_mutable(db, tid, booking)

    note = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "content": data.content,
        "note_type": data.note_type,
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.reservation_notes.insert_one({**note})

    await _log_activity(
        tid,
        booking_id,
        "note_added",
        current_user.name,
        {
            "note_type": data.note_type,
        },
    )

    note.pop("_id", None)
    return {"success": True, "note": note}


@router.post("/reservations/{booking_id}/room-change")
async def room_change(
    booking_id: str,
    data: RoomChangeRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Change the room for a reservation with full audit trail."""
    _enforce_perm(current_user.role, "edit_booking")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    await ensure_reservation_mutable(db, tid, booking)
    if str(booking.get("status") or "").lower() not in {"pending", "confirmed", "guaranteed", "checked_in"}:
        raise HTTPException(status_code=409, detail="Bu rezervasyon mevcut durumunda oda değişikliğine uygun değil")

    old_room_id = booking.get("room_id")
    old_room = await db.rooms.find_one({"id": old_room_id, "tenant_id": tid}, {"_id": 0})
    new_room = await db.rooms.find_one({"id": data.new_room_id, "tenant_id": tid}, {"_id": 0})

    if not new_room:
        raise HTTPException(status_code=404, detail="Yeni oda bulunamadı")

    # Update booking
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {
            "$set": {
                "room_id": data.new_room_id,
                "room_number": new_room.get("room_number"),
            }
        },
    )

    # Release old room
    if old_room_id:
        await db.rooms.update_one(
            {"id": old_room_id, "tenant_id": tid},
            {"$set": {"status": "dirty", "current_booking_id": None}},
        )

    # Assign new room
    await db.rooms.update_one(
        {"id": data.new_room_id, "tenant_id": tid},
        {"$set": {"status": "occupied", "current_booking_id": booking_id}},
    )

    # Record room move history
    move_record = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "from_room_id": old_room_id,
        "from_room_number": old_room.get("room_number") if old_room else None,
        "to_room_id": data.new_room_id,
        "to_room_number": new_room.get("room_number"),
        "reason": data.reason,
        "moved_by": current_user.name,
        "moved_at": datetime.now(UTC).isoformat(),
    }
    await db.room_move_history.insert_one({**move_record})

    await _log_activity(
        tid,
        booking_id,
        "room_changed",
        current_user.name,
        {
            "from_room": old_room.get("room_number") if old_room else None,
            "to_room": new_room.get("room_number"),
            "reason": data.reason,
        },
    )

    # Acente webhook: rezervasyon güncellendi (oda değişti)
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    schedule_emit_reservation_updated(
        tid,
        booking_id,
        "room_moved",
        {"new_room_id": data.new_room_id, "new_room_number": new_room.get("room_number"), "reason": data.reason},
    )

    move_record.pop("_id", None)
    return {"success": True, "move_record": move_record}


@router.post("/reservations/{booking_id}/early-checkin")
async def early_checkin(
    booking_id: str,
    data: EarlyCheckinRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Process early check-in with optional extra charge — atomic transaction."""
    _enforce_perm(current_user.role, "checkin")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    await ensure_reservation_mutable(db, tid, booking)

    from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic

    extra_fields = {"early_checkin": True}
    if data.checkin_time:
        extra_fields["checked_in_at"] = data.checkin_time

    try:
        result = await check_in_booking_atomic(
            booking_id=booking_id,
            tenant_id=tid,
            actor_id=current_user.id,
            actor_name=current_user.name,
            extra_fields=extra_fields,
        )
    except CheckInError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Add extra charge if any (outside transaction — non-critical)
    if data.extra_charge > 0:
        charge = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "booking_id": booking_id,
            "charge_name": "Erken Giriş Ücreti",
            "charge_amount": data.extra_charge,
            "category": "room",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.extra_charges.insert_one({**charge})

    await _log_activity(
        tid,
        booking_id,
        "early_checkin",
        current_user.name,
        {
            "checkin_time": data.checkin_time or result.get("checked_in_at"),
            "extra_charge": data.extra_charge,
        },
    )

    # Acente webhook: rezervasyon güncellendi (erken check-in yapıldı)
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    schedule_emit_reservation_updated(
        tid,
        booking_id,
        "checked_in",
        {"early_checkin": True, "checkin_time": data.checkin_time or result.get("checked_in_at"), "extra_charge": data.extra_charge},
    )

    return {"success": True, "message": "Erken giriş yapıldı"}


@router.post("/reservations/{booking_id}/late-checkout")
async def late_checkout(
    booking_id: str,
    data: LateCheckoutRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Process late check-out with optional extra charge."""
    _enforce_perm(current_user.role, "checkout")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    if str(booking.get("status") or "").lower() != "checked_in":
        raise HTTPException(status_code=409, detail="Geç çıkış yalnız içerideki rezervasyona uygulanabilir")
    await ensure_reservation_mutable(db, tid, booking)

    updates = {"late_checkout": True}
    if data.checkout_time:
        updates["check_out_time"] = data.checkout_time

    await db.bookings.update_one({"id": booking_id, "tenant_id": tid}, {"$set": updates})

    if data.extra_charge > 0:
        charge = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "booking_id": booking_id,
            "charge_name": "Geç Çıkış Ücreti",
            "charge_amount": data.extra_charge,
            "category": "room",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.extra_charges.insert_one({**charge})

    await _log_activity(
        tid,
        booking_id,
        "late_checkout",
        current_user.name,
        {
            "checkout_time": data.checkout_time,
            "extra_charge": data.extra_charge,
        },
    )

    # Acente webhook: rezervasyon güncellendi (geç çıkış kaydedildi)
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    schedule_emit_reservation_updated(
        tid,
        booking_id,
        "late_checkout_approved",
        {"checkout_time": data.checkout_time, "extra_charge": data.extra_charge},
    )

    return {"success": True, "message": "Geç çıkış kaydedildi"}


@router.post("/reservations/{booking_id}/mark-noshow")
async def mark_noshow(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Mark a reservation as no-show."""
    _enforce_perm(current_user.role, "edit_booking")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    if str(booking.get("status") or "").lower() not in {"pending", "confirmed", "guaranteed"}:
        raise HTTPException(status_code=409, detail="Bu rezervasyon mevcut durumunda no-show yapılamaz")

    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"status": "no_show", "no_show_at": datetime.now(UTC).isoformat()}},
    )

    # Release the physical room only when this reservation still owns it.
    # Historical corrections must never clear a room that has since been
    # assigned to another in-house guest.
    if booking.get("room_id"):
        await db.rooms.update_one(
            {
                "id": booking["room_id"],
                "tenant_id": tid,
                "current_booking_id": booking_id,
            },
            {"$set": {"status": "available", "current_booking_id": None}},
        )

    # Keep durable room-night availability aligned with this state transition.
    from core.atomic_booking import release_booking_nights

    try:
        await release_booking_nights(tid, booking_id, reason="no_show")
    except Exception as exc:
        # The status write is already durable; make the transition retry-safe
        # and surface the stale inventory lock to operations instead of asking
        # the caller to retry a no-longer-eligible no-show action.
        logger.exception("No-show room-night release failed booking=%s: %s", booking_id, exc)

    await _log_activity(tid, booking_id, "marked_noshow", current_user.name, {})

    return {"success": True, "message": "No-show olarak işaretlendi"}


@router.put("/reservations/{booking_id}/vip-status")
async def update_vip_status(
    booking_id: str,
    vip: bool = True,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Toggle VIP status for the guest of a reservation."""
    _enforce_perm(current_user.role, "edit_booking")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    await ensure_reservation_mutable(db, tid, booking)

    if booking.get("guest_id"):
        await db.guests.update_one(
            {"id": booking["guest_id"], "tenant_id": tid},
            {"$set": {"vip_status": vip}},
        )

    await _log_activity(tid, booking_id, "vip_status_changed", current_user.name, {"vip": vip})

    return {"success": True, "vip_status": vip}


@router.post("/reservations/{booking_id}/record-deposit")
async def record_deposit(
    booking_id: str,
    data: DepositRecord,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Record a deposit payment."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP Round-3
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    if booking.get("status") in {"checked_out", "cancelled", "no_show"}:
        raise HTTPException(
            status_code=409,
            detail="Tamamlanmış veya iptal edilmiş rezervasyona depozito alınamaz",
        )

    folio = await _ensure_reservation_folio(tid, booking)

    deposit = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "folio_id": folio["id"],
        "amount": data.amount,
        "method": data.method,
        "reference": data.reference,
        "deposit_type": "deposit",
        "status": "received",
        "recorded_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.deposits.insert_one({**deposit})

    # Also record as payment
    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "deposit_id": deposit["id"],
        "amount": data.amount,
        "method": data.method,
        "payment_type": "deposit",
        "status": "paid",
        "reference": data.reference,
        "processed_by": current_user.name,
        "processed_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    await db.payments.insert_one({**payment})

    new_paid = (booking.get("paid_amount", 0) or 0) + data.amount
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"paid_amount": round(new_paid, 2)}},
    )
    await _refresh_cached_folio_balance(tid, folio["id"])

    await _log_activity(
        tid,
        booking_id,
        "deposit_recorded",
        current_user.name,
        {
            "amount": data.amount,
            "method": data.method,
        },
    )

    # Acente webhook: rezervasyon güncellendi (depozito alındı)
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    schedule_emit_reservation_updated(
        tid,
        booking_id,
        "payment_added",
        {"payment_id": payment["id"], "amount": data.amount, "method": data.method, "payment_type": "deposit"},
    )

    deposit.pop("_id", None)
    return {"success": True, "deposit": deposit}


@router.post("/reservations/{booking_id}/add-extra-charge")
async def add_extra_charge_detail(
    booking_id: str,
    data: ExtraChargeAdd,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v97 DW
):
    """Add an extra charge to a reservation."""
    _enforce_perm(current_user.role, "post_charge")  # Bug CP fix
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    total = round(data.amount * data.quantity, 2)
    charge = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "charge_name": data.description,
        "description": data.description,
        "category": data.category,
        "charge_category": data.category,
        "charge_amount": total,
        "amount": data.amount,
        "quantity": data.quantity,
        "total": total,
        "posted_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    await db.extra_charges.insert_one({**charge})

    await _log_activity(
        tid,
        booking_id,
        "extra_charge_added",
        current_user.name,
        {
            "description": data.description,
            "amount": total,
            "category": data.category,
        },
    )

    # Acente webhook: rezervasyon güncellendi (ek charge → toplam değişti)
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    schedule_emit_reservation_updated(
        tid,
        booking_id,
        "charge_added",
        {"charge_id": charge["id"], "amount": total, "category": data.category, "description": data.description},
    )

    charge.pop("_id", None)
    return {"success": True, "charge": charge}


@router.put("/reservations/{booking_id}/daily-rates")
async def update_daily_rates(
    booking_id: str,
    data: DailyRateUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("override_rate")),  # v97 DW
):
    """Update daily rates for a reservation. Requires override_rate permission."""
    _enforce_perm(current_user.role, "override_rate")  # Bug CP Round-3 — mirror rate-override-panel gate
    _ensure_hotel_context(current_user)

    tid = current_user.tenant_id

    from core.security import _is_super_admin
    from core.tenant_db import get_system_db, tenant_context

    if _is_super_admin(current_user):
        # Super admin: use system db (no tenant scoping) to find which tenant this booking belongs to
        sys_db = get_system_db()
        lookup = await sys_db.bookings.find_one({"id": booking_id}, {"tenant_id": 1})
        if lookup:
            tid = lookup.get("tenant_id", current_user.tenant_id)

    is_cross_tenant_update = tid != current_user.tenant_id
    new_total = 0.0
    with tenant_context(tid):
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
        if not booking:
            raise HTTPException(status_code=400, detail="Rezervasyon bulunamadı.")

        await ensure_reservation_mutable(db, tid, booking)

        business_state = await ensure_business_date_initialized(db, tid)
        current_business_date = str(business_state["business_date"])[:10]
        check_in = _reservation_calendar_date(booking.get("check_in"))
        check_out = _reservation_calendar_date(booking.get("check_out"))
        if check_in is None or check_out is None or check_out <= check_in:
            raise HTTPException(status_code=409, detail="Rezervasyonun geçerli bir konaklama aralığı yok")

        stay_dates: list[str] = []
        current = check_in
        while current < check_out:
            stay_dates.append(current.isoformat())
            current += timedelta(days=1)

        submitted_rates: dict[str, float] = {}
        for rate_entry in data.rates:
            rate_date = _reservation_calendar_date(rate_entry.date)
            if rate_date is None:
                raise HTTPException(status_code=422, detail=f"Geçersiz günlük fiyat tarihi: {rate_entry.date}")
            date_key = rate_date.isoformat()
            if date_key in submitted_rates:
                raise HTTPException(status_code=422, detail=f"{date_key} için birden fazla günlük fiyat gönderildi")
            submitted_rates[date_key] = round(float(rate_entry.rate), 2)

        expected_dates = set(stay_dates)
        if set(submitted_rates) != expected_dates:
            missing = sorted(expected_dates - set(submitted_rates))
            outside = sorted(set(submitted_rates) - expected_dates)
            detail = "Günlük fiyatlar check-in dahil, check-out hariç her geceyi tam olarak bir kez içermelidir"
            if missing:
                detail += f". Eksik: {', '.join(missing)}"
            if outside:
                detail += f". Aralık dışı: {', '.join(outside)}"
            raise HTTPException(status_code=422, detail=detail)

        existing_rate_rows = [
            row
            async for row in db.daily_rates.find(
                {"booking_id": booking_id, "tenant_id": tid},
                {"_id": 0, "date": 1, "rate": 1},
            )
        ]
        existing_rates: dict[str, dict] = {}
        for row in existing_rate_rows:
            rate_date = _reservation_calendar_date(row.get("date"))
            if rate_date is None:
                raise HTTPException(status_code=409, detail="Geçersiz tarihli mevcut günlük fiyat kaydı bulundu; düzeltme gerekir")
            date_key = rate_date.isoformat()
            if date_key in existing_rates:
                raise HTTPException(status_code=409, detail=f"{date_key} için yinelenen günlük fiyat kaydı bulundu; düzeltme gerekir")
            existing_rates[date_key] = row

        # Bug Fix: If daily_rates are missing in DB, they were generated on-the-fly for the frontend.
        # We must recreate them here to allow the frontend to submit the locked unchanged rates without triggering a 409.
        if not existing_rates:
            nights = len(stay_dates)
            nightly_rate = round(float(booking.get("total_amount", 0) or 0) / nights, 2)
            existing_rates = {date_key: {"date": date_key, "rate": nightly_rate} for date_key in stay_dates}

        for rate_date, rate in submitted_rates.items():
            if rate_date < current_business_date:
                existing = existing_rates.get(rate_date)
                if existing is None or _money_cents(existing.get("rate")) != _money_cents(rate):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"{rate_date} iş günü Night Audit ile kapatıldığı için "
                            "oda fiyatı değiştirilemez"
                        ),
                    )

        # Sync an already-posted room charge only. Future nights must remain
        # unposted: Night Audit reads daily_rates and posts them exactly once.
        # Night-Audit-closed days (rate_date < current_business_date) are skipped —
        # their charges are historical records and must not be modified.
        folio = await db.folios.find_one(
            {"booking_id": booking_id, "tenant_id": tid, "folio_type": "guest", "status": "open"},
            {"_id": 0, "id": 1},
        )
        rate_changed_dates = {
            rate_date
            for rate_date, rate in submitted_rates.items()
            if _money_cents(existing_rates.get(rate_date, {}).get("rate")) != _money_cents(rate)
        }
        posted_rate_mismatches = await _posted_room_charge_rate_mismatches(
            tid,
            booking_id,
            expected_rates_by_date=submitted_rates,
        )
        mismatched_dates = {row["date"] for row in posted_rate_mismatches}
        historical_mismatches = sorted(date_key for date_key in mismatched_dates if date_key < current_business_date)
        if historical_mismatches:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Night Audit ile kapanmış oda tahakkuku günlük fiyatla uyuşmuyor; "
                    f"manuel finans mutabakatı gerekir ({', '.join(historical_mismatches)})"
                ),
            )

        # Pricing after a payment or an issued invoice must be an explicit,
        # audited financial adjustment.  A normal daily-rate save must never
        # change either future room revenue or a drifted posted room charge.
        if folio and (rate_changed_dates or mismatched_dates):
            active_payment = await db.payments.find_one(
                {"tenant_id": tid, "folio_id": folio["id"], "voided": {"$ne": True}, "amount": {"$gt": 0}},
                {"_id": 0, "id": 1},
            )
            issued_invoice = await db.invoices.find_one(
                {"tenant_id": tid, "folio_id": folio["id"], "status": {"$nin": ["draft", "cancelled", "voided"]}},
                {"_id": 0, "id": 1},
            )
            if active_payment or issued_invoice:
                raise HTTPException(
                    status_code=409,
                    detail="Ödeme veya düzenlenmiş fatura bulunan rezervasyonda fiyat/tahakkuk mutabakatı finans onayı olmadan değiştirilemez",
                )

        affected_folio_ids: set[str] = set()

        # Resolve tax rates once — same approach as Night Audit service.
        from core.channel_room_charge_pricing import calculate_room_charge
        accommodation_tax_rate = await get_accommodation_tax_rate(tid, booking.get("check_in"))

        async with await db.client.start_session() as session:
            async with session.start_transaction():
                for rate_date, rate in submitted_rates.items():
                    existing = existing_rates.get(rate_date, {})
                    try:
                        await db.daily_rates.update_one(
                            {"booking_id": booking_id, "tenant_id": tid, "date": existing.get("date", rate_date)},
                            {
                                "$set": {
                                    "date": rate_date,
                                    "rate": rate,
                                    # Partial unique index: new/touched rows are
                                    # protected without making a rollout fail on
                                    # an as-yet-unremediated legacy duplicate.
                                    "daily_rate_key": f"{booking_id}:{rate_date}",
                                    "updated_by": current_user.name,
                                    "updated_at": datetime.now(UTC).isoformat(),
                                }
                            },
                            upsert=True,
                            session=session,
                        )
                    except DuplicateKeyError as exc:
                        raise HTTPException(
                            status_code=409,
                            detail=f"{rate_date} için eşzamanlı günlük fiyat güncellemesi tespit edildi; lütfen yeniden deneyin",
                        ) from exc

                # Recalculate total
                new_total = round(sum(submitted_rates.values()), 2)
                await db.bookings.update_one(
                    {"id": booking_id, "tenant_id": tid},
                    {"$set": {"total_amount": new_total}},
                    session=session,
                )

                for rate_date, rate in submitted_rates.items():
                    if rate_date < current_business_date:
                        # Closed by Night Audit — do not touch folio charges for this day.
                        continue

                    if rate_date not in rate_changed_dates and rate_date not in mismatched_dates:
                        # Amount unchanged — nothing to sync.
                        continue

                    # Find active room charges for this booking on this date
                    existing_room_charges = [
                        c async for c in db.folio_charges.find(
                            {
                                "booking_id": booking_id,
                                "tenant_id": tid,
                                "charge_category": "room",
                                "voided": {"$ne": True},
                                "date": {"$gte": rate_date, "$lt": rate_date + "T99"},
                            },
                            {"_id": 0},
                            session=session,
                        )
                    ]

                    if not existing_room_charges:
                        continue
                    if len(existing_room_charges) != 1:
                        raise HTTPException(status_code=409, detail=f"{rate_date} için birden fazla aktif oda folyo satırı bulundu; manuel düzeltme gerekir")
                    if not folio or existing_room_charges[0].get("folio_id") != folio["id"]:
                        raise HTTPException(status_code=409, detail=f"{rate_date} oda ücreti açık misafir folyasında değil; manuel düzeltme gerekir")

                    old_charge = existing_room_charges[0]
                    await db.folio_charges.update_one(
                        {"id": old_charge["id"], "tenant_id": tid, "voided": {"$ne": True}},
                        {"$set": {"voided": True, "voided_at": datetime.now(UTC).isoformat(), "voided_by": current_user.name, "void_reason": f"Günlük fiyat güncellendi: {old_charge.get('total', old_charge.get('amount', 0))} TL → {rate} TL"}},
                        session=session,
                    )
                    single_night_booking = {
                            **booking,
                            "total_amount": rate,
                            "provider_total_amount": None,
                            "total_price": None,
                            "check_in": rate_date,
                            "check_out": rate_date,  # same day → nights=1 inside _nightly_gross
                    }
                    pricing = calculate_room_charge(
                            single_night_booking,
                            rate_date,
                            vat_rate=0.10,
                            accommodation_tax_rate=accommodation_tax_rate,
                    )
                    if _money_cents(pricing["total"]) != _money_cents(rate):
                        raise HTTPException(
                            status_code=409,
                            detail=f"{rate_date} için oda tahakkuku günlük fiyatla mutabık oluşturulamadı",
                        )
                    new_charge = {
                            "id": str(uuid.uuid4()),
                            "tenant_id": tid,
                            "folio_id": old_charge["folio_id"],
                            "booking_id": booking_id,
                            "charge_category": "room",
                            "description": old_charge.get("description") or f"Room charge - {rate_date}",
                            "date": old_charge.get("date") or rate_date,
                            "quantity": 1,
                            "unit_price": pricing["unit_price"],
                            "amount": pricing["amount"],
                            "tax_rate": pricing["tax_rate"],
                            "tax_amount": pricing["tax_amount"],
                            "total": pricing["total"],
                            "tax_breakdown": pricing["tax_breakdown"],
                            "tax_inclusive": pricing["tax_inclusive"],
                            "posted_at": datetime.now(UTC).isoformat(),
                            "posted_by": current_user.name,
                            "reposted_from_charge_id": old_charge["id"],
                            "voided": False,
                    }
                    for field in ("business_date", "night_audit_date", "charge_type", "audit_id"):
                        if old_charge.get(field) is not None:
                            new_charge[field] = old_charge[field]
                    await db.folio_charges.insert_one(new_charge, session=session)
                    affected_folio_ids.add(old_charge["folio_id"])

        # Recalculate folio balance for all affected folios (must be outside transaction to see committed charges)
        for folio_id in affected_folio_ids:
            await _refresh_cached_folio_balance(tid, folio_id)

        await _log_activity(
            tid,
            booking_id,
            "daily_rates_updated",
            current_user.name,
            {
                "rates_count": len(submitted_rates),
                "business_date": current_business_date,
                "folio_charges_synced": len(affected_folio_ids) > 0,
                "cross_tenant_update": is_cross_tenant_update,
                "original_actor_tenant": current_user.tenant_id,
            },
        )

    if is_cross_tenant_update:
        with tenant_context(current_user.tenant_id):
            await db.audit_logs.insert_one(
                {
                    "event_type": "super_admin_cross_tenant_daily_rates_updated",
                    "actor_id": current_user.id,
                    "actor_name": current_user.name,
                    "actor_tenant_id": current_user.tenant_id,
                    "target_tenant_id": tid,
                    "resource": f"booking:{booking_id}",
                    "rates_count": len(submitted_rates),
                    "new_total": new_total,
                    "tenant_id": current_user.tenant_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )

    return {"success": True, "new_total": round(new_total, 2)}


@router.put("/reservations/{booking_id}/update-guest")
async def update_reservation_guest(
    booking_id: str,
    data: GuestUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Update guest information for a reservation."""
    _enforce_perm(current_user.role, "edit_booking")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    await ensure_reservation_mutable(db, tid, booking)

    if not booking.get("guest_id"):
        raise HTTPException(status_code=400, detail="Misafir bilgisi bulunamadı")

    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    # User-facing field names captured BEFORE companions/encryption so the audit
    # log never records internal `_hash_*` / `_enc_*` / `*_lower` keys.
    _logged_fields = list(updates.keys())
    if updates:
        from routers.pms_guests import _encrypt_guest
        from security.search_ngram import (
            NGRAM_SOURCE_FIELDS,
            ngram_set_for_update_merged,
        )
        from security.search_normalize import normalized_set_for_update

        existing_guest = await db.guests.find_one(
            {"id": booking["guest_id"], "tenant_id": tid},
            {"_id": 0},
        )

        # Search companions are computed from the PLAINTEXT update BEFORE
        # encryption — name fields are NOT encrypted. name_lower keeps renames
        # prefix-searchable.
        _norm = normalized_set_for_update(updates, collection="guests")
        # Combined _ng_name must reflect ALL name fields, not just the changed
        # subset, or a name-only edit drops first/last-name infix trigrams.
        if any(f in updates for f in NGRAM_SOURCE_FIELDS.get("guests", [])):
            _norm.update(ngram_set_for_update_merged(existing_guest, updates, collection="guests"))
        # KVKK: encrypt PII fields at rest (email / phone / id_number) and write
        # their `_hash_<field>` blind-index tokens. Without this, editing a guest
        # from the reservation screen stored PII as PLAINTEXT and left encrypted
        # search unable to find them. `name` is not an encrypted field, so it
        # stays plaintext for the booking guest_name sync below.
        _plain_name = updates.get("name")
        updates = _encrypt_guest(updates)
        updates.update(_norm)

        # Detay ekranındaki düzenleme rezervasyona aittir. Aynı CRM misafir
        # kaydı birden fazla rezervasyona bağlıysa onu yerinde güncellemek,
        # diğer odadaki misafirin de adını/iletişimini değiştiriyordu. Bu
        # durumda yalnızca bu rezervasyon için bir kopya oluşturup ilişkiyi
        # yeni kayda taşıyoruz; diğer rezervasyonların misafiri değişmez.
        shared_guest_booking = await db.bookings.find_one(
            {
                "tenant_id": tid,
                "guest_id": booking["guest_id"],
                "id": {"$ne": booking_id},
                "status": {"$nin": ["cancelled", "no_show"]},
            },
            {"_id": 0, "id": 1},
        )
        if shared_guest_booking and existing_guest:
            isolated_guest_id = str(uuid.uuid4())
            isolated_guest = {
                **existing_guest,
                **updates,
                "id": isolated_guest_id,
                "tenant_id": tid,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "source": "reservation_guest_edit",
            }
            await db.guests.insert_one(isolated_guest)
            booking_updates = {"guest_id": isolated_guest_id}
            if _plain_name is not None:
                booking_updates.update({
                    "guest_name": _plain_name,
                    **normalized_set_for_update({"guest_name": _plain_name}, collection="bookings"),
                })
            await db.bookings.update_one(
                {"id": booking_id, "tenant_id": tid},
                {"$set": booking_updates},
            )
        else:
            await db.guests.update_one({"id": booking["guest_id"], "tenant_id": tid}, {"$set": updates})

            if _plain_name is not None:
                _bnorm = normalized_set_for_update({"guest_name": _plain_name}, collection="bookings")
                await db.bookings.update_one(
                    {"id": booking_id, "tenant_id": tid},
                    {"$set": {"guest_name": _plain_name, **_bnorm}},
                )

    await _log_activity(tid, booking_id, "guest_updated", current_user.name, {"fields": _logged_fields})

    return {"success": True}


# ── Cari Account Endpoints ──


@router.get("/cari-accounts")
async def list_cari_accounts(current_user: User = Depends(get_current_user)):
    """List all cari (account receivable) accounts, including city ledger accounts."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    accounts = []
    seen_account_ids = set()
    # Eski cari_accounts koleksiyonu
    async for acc in db.cari_accounts.find({"tenant_id": tid}).sort("name", 1):
        account_id = _canonical_cari_account_id(acc)
        if not account_id or account_id in seen_account_ids:
            continue
        seen_account_ids.add(account_id)
        normalized = {key: value for key, value in acc.items() if key != "_id"}
        normalized["id"] = account_id
        normalized["transfer_id"] = _cari_transfer_lookup_id(acc)
        normalized["name"] = _canonical_cari_account_name(acc)
        normalized["balance"] = _cari_balance(acc)
        accounts.append(normalized)

    # City Ledger hesaplarını da ekle (folyo dropdown'ında görünsün)
    async for acc in db.city_ledger_accounts.find({"tenant_id": tid, "is_active": {"$ne": False}}).sort("account_name", 1):
        account_id = _canonical_cari_account_id(acc)
        if not account_id or account_id in seen_account_ids:
            continue
        seen_account_ids.add(account_id)
        # cari_accounts formatıyla uyumlu hale getir
        accounts.append({
            "id": account_id,
            "transfer_id": _cari_transfer_lookup_id(acc),
            "name": _canonical_cari_account_name(acc),
            "company_name": acc.get("company_name"),
            "account_type": "city_ledger",
            "balance": acc.get("current_balance", 0),
            "credit_limit": acc.get("credit_limit", 0),
            "tenant_id": tid,
        })

    return {"accounts": accounts}


@router.post("/cari-accounts")
async def create_cari_account(
    data: CariAccountCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Create a new cari account."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP Round-4 — financial setup
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    account = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "name": data.name,
        "account_type": data.account_type,
        "company_id": data.company_id,
        "contact_person": data.contact_person,
        "contact_email": data.contact_email,
        "contact_phone": data.contact_phone,
        "credit_limit": data.credit_limit,
        "payment_terms_days": data.payment_terms_days,
        "balance": 0.0,
        "current_balance": 0.0,
        "status": "active",
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.cari_accounts.insert_one({**account})

    account.pop("_id", None)
    return {"success": True, "account": account}


@router.get("/cari-accounts/{account_id}/transactions")
async def get_cari_transactions(
    account_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get transactions for a cari account."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    transactions = []
    async for t in db.cari_transactions.find({"cari_account_id": account_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        transactions.append(t)

    return {"transactions": transactions}


class CariReconciliation(BaseModel):
    # Bug CP Round-4 — financial input validation
    amount: float = Field(..., gt=0, le=1e9)
    description: str | None = Field(None, max_length=2000)


@router.post("/cari-accounts/{account_id}/reconcile")
async def reconcile_cari_account(
    account_id: str,
    data: CariReconciliation,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Reconcile (mahsuplaştır) a cari account - record a payment/offset."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    account = await db.cari_accounts.find_one({"id": account_id, "tenant_id": tid}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")

    current_balance = _cari_balance(account)
    if data.amount > current_balance:
        raise HTTPException(status_code=422, detail="Mahsuplaştırma tutarı cari bakiyeyi aşamaz")

    txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "cari_account_id": account_id,
        "booking_id": None,
        "transaction_type": "payment",
        "amount": data.amount,
        "description": data.description or "Mahsuplaştırma",
        "posted_by": current_user.name or current_user.email,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.cari_transactions.insert_one({**txn})
    txn.pop("_id", None)

    # Update account balance
    await db.cari_accounts.update_one(
        {"id": account_id, "tenant_id": tid},
        {
            "$set": {
                "balance": current_balance - data.amount,
                "current_balance": current_balance - data.amount,
            }
        },
    )

    return {"success": True, "transaction": txn}


@router.post("/cari-accounts/{account_id}/transfer-to-agency")
async def transfer_cari_to_agency(
    account_id: str,
    data: CariTransfer,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Transfer cari balance to an agency cari account."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    if account_id == data.cari_account_id:
        raise HTTPException(status_code=422, detail="Kaynak ve hedef cari hesap farklı olmalı")

    source = await db.cari_accounts.find_one({"id": account_id, "tenant_id": tid}, {"_id": 0})
    if not source:
        raise HTTPException(status_code=404, detail="Kaynak cari hesap bulunamadı")

    target = await db.cari_accounts.find_one({"id": data.cari_account_id, "tenant_id": tid}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Hedef cari hesap bulunamadı")

    source_balance = _cari_balance(source)
    if data.amount > source_balance:
        raise HTTPException(status_code=422, detail="Aktarım tutarı kaynak cari bakiyeyi aşamaz")
    target_balance = _cari_balance(target)

    now = datetime.now(UTC).isoformat()
    actor = current_user.name or current_user.email

    # Debit from source
    debit_txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "cari_account_id": account_id,
        "booking_id": None,
        "transaction_type": "transfer_out",
        "amount": data.amount,
        "description": data.description or f"{target.get('name', '')} hesabina aktarim",
        "posted_by": actor,
        "created_at": now,
    }
    await db.cari_transactions.insert_one({**debit_txn})
    debit_txn.pop("_id", None)

    # Credit to target
    credit_txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "cari_account_id": data.cari_account_id,
        "booking_id": None,
        "transaction_type": "transfer_in",
        "amount": data.amount,
        "description": data.description or f"{source.get('name', '')} hesabindan aktarim",
        "posted_by": actor,
        "created_at": now,
    }
    await db.cari_transactions.insert_one({**credit_txn})
    credit_txn.pop("_id", None)

    # Update balances
    await db.cari_accounts.update_one(
        {"id": account_id, "tenant_id": tid},
        {
            "$set": {
                "balance": source_balance - data.amount,
                "current_balance": source_balance - data.amount,
            }
        },
    )
    await db.cari_accounts.update_one(
        {"id": data.cari_account_id, "tenant_id": tid},
        {
            "$set": {
                "balance": target_balance + data.amount,
                "current_balance": target_balance + data.amount,
            }
        },
    )

    return {"success": True, "debit": debit_txn, "credit": credit_txn}


# ── Available Rooms Endpoint ──


@router.get("/available-rooms")
async def get_available_rooms(
    check_in: str = "",
    check_out: str = "",
    current_user: User = Depends(get_current_user),
):
    """Get available rooms for room change."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    all_rooms = []
    async for r in db.rooms.find({"tenant_id": tid}, {"_id": 0}).sort("room_number", 1):
        all_rooms.append(r)

    if not check_in or not check_out:
        return {"rooms": all_rooms}

    # Validate date format & ordering (her iki tarih varsa)
    try:
        from datetime import date as _date

        ci_d = _date.fromisoformat(check_in[:10])
        co_d = _date.fromisoformat(check_out[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="check_in ve check_out YYYY-MM-DD formatında olmalı")
    if co_d <= ci_d:
        raise HTTPException(status_code=422, detail="check_out tarihi check_in'den sonra olmalı")

    # Find bookings that overlap the date range
    occupied_room_ids = set()
    async for b in db.bookings.find(
        {
            "tenant_id": tid,
            "status": {"$nin": ["cancelled", "no_show", "checked_out"]},
        },
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    ):
        b_ci = str(b.get("check_in", ""))[:10]
        b_co = str(b.get("check_out", ""))[:10]
        if b_ci < check_out and b_co > check_in:
            if b.get("room_id"):
                occupied_room_ids.add(b["room_id"])

    available = [r for r in all_rooms if r.get("id") not in occupied_room_ids]
    return {"rooms": available, "all_rooms": all_rooms}


# ── Group Booking Endpoints ──


@router.post("/group-bookings")
async def create_group_booking(
    data: GroupBookingCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Create a new group booking.

    İki mod desteklenir (ikisi aynı çağrıda birleştirilebilir):
      1) `booking_ids`  — mevcut bireysel rezervasyonları seç ve grupla.
      2) `new_bookings` — grup adıyla aynı anda N adet yeni rezervasyon
         yarat ve gruba bağla. Her satır için (yoksa) misafir kaydı
         placeholder e-posta ile açılır, sonra standart rezervasyon
         servisi (`CreateReservationService`) çağrılır.
    """
    _enforce_perm(current_user.role, "create_booking")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    if not data.group_name.strip():
        raise HTTPException(status_code=400, detail="Grup adı boş olamaz")

    # ── Aşama 1: TÜM girdileri yazma yapmadan önce doğrula ──
    # (Kısmi yazılmış grup oluşturmamak için).
    for idx, row in enumerate(data.new_bookings, start=1):
        if not row.guest_name.strip():
            raise HTTPException(status_code=400, detail=f"{idx}. satır: misafir adı zorunlu")
        if row.total_amount <= 0:
            raise HTTPException(status_code=400, detail=f"{idx}. satır ({row.guest_name}): geçerli bir tutar girin")
        try:
            ci_dt = datetime.fromisoformat(row.check_in.replace("Z", "+00:00"))
            co_dt = datetime.fromisoformat(row.check_out.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{idx}. satır: tarih formatı geçersiz")
        if co_dt <= ci_dt:
            raise HTTPException(status_code=400, detail=f"{idx}. satır: çıkış tarihi giriş tarihinden sonra olmalı")

    # Tüm odaları toplu doğrula (tenant scope)
    requested_room_ids = list({r.room_id for r in data.new_bookings})
    if requested_room_ids:
        valid_room_ids = {r["id"] async for r in db.rooms.find({"id": {"$in": requested_room_ids}, "tenant_id": tid}, {"id": 1})}
        for idx, row in enumerate(data.new_bookings, start=1):
            if row.room_id not in valid_room_ids:
                raise HTTPException(status_code=404, detail=f"{idx}. satır: oda bulunamadı")

    # Mevcut booking_ids'i tenant kapsamında doğrula
    valid_existing_ids: list[str] = []
    if data.booking_ids:
        existing_docs = [
            document
            async for document in db.bookings.find(
                {"id": {"$in": list(set(data.booking_ids))}, "tenant_id": tid},
                {"_id": 0, "id": 1, "status": 1, "check_out": 1},
            )
        ]
        valid_existing_ids = [document["id"] for document in existing_docs]
        missing = set(data.booking_ids) - set(valid_existing_ids)
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Bu rezervasyonlar bulunamadı veya yetkiniz yok: {', '.join(list(missing)[:3])}",
            )
        business_date = await ensure_business_date_initialized(db, tid)
        historical_ids = [
            document["id"]
            for document in existing_docs
            if reservation_is_historical(document, business_date["business_date"])
        ]
        if historical_ids:
            raise HTTPException(
                status_code=409,
                detail=f"Geçmiş rezervasyonlar gruba eklenemez: {', '.join(historical_ids[:3])}",
            )

    if not data.new_bookings and not valid_existing_ids:
        raise HTTPException(status_code=400, detail="Grup için en az 1 rezervasyon gerekli")

    # ── Aşama 2: Yeni rezervasyonları yarat (failure'da geri al) ──
    created_guest_ids: list[str] = []
    new_booking_ids: list[str] = []
    try:
        for idx, row in enumerate(data.new_bookings, start=1):
            guest_id = str(uuid.uuid4())
            from security.guest_write import encrypt_guest_insert

            _guest_doc = encrypt_guest_insert(
                {
                    "id": guest_id,
                    "tenant_id": tid,
                    "name": row.guest_name.strip(),
                    "email": f"group-{guest_id[:8]}@placeholder.local",
                    "phone": "",
                    "id_number": "",
                    "vip_status": False,
                    "loyalty_points": 0,
                    "total_stays": 0,
                    "total_spend": 0.0,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            await db.guests.insert_one(_guest_doc)
            created_guest_ids.append(guest_id)

            booking_data = BookingCreate(
                guest_id=guest_id,
                room_id=row.room_id,
                check_in=row.check_in,
                check_out=row.check_out,
                adults=max(1, row.adults),
                children=max(0, row.children),
                guests_count=max(1, row.adults + row.children),
                total_amount=row.total_amount,
                channel="direct",
                source_channel="direct",
                origin="ui-group",
            )
            sub_request = _request_with_idempotency_key(request, str(uuid.uuid4()))
            result = await _create_reservation_service.create(booking_data, current_user, sub_request)
            bid = result.get("booking_id") or result.get("id") or (result.get("booking") or {}).get("id")
            if not bid:
                raise HTTPException(
                    status_code=500,
                    detail=f"{idx}. satır rezervasyon ID'si alınamadı",
                )
            new_booking_ids.append(bid)
    except Exception as exc:
        # Compensating: önceden yarattıklarını sil
        if new_booking_ids:
            await db.bookings.delete_many({"id": {"$in": new_booking_ids}, "tenant_id": tid})
        if created_guest_ids:
            await db.guests.delete_many({"id": {"$in": created_guest_ids}, "tenant_id": tid})
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Grup oluşturulurken hata: {exc}") from exc

    # Birleştir (tekrarlananları at, var olanları başa al)
    all_booking_ids = list(dict.fromkeys([*valid_existing_ids, *new_booking_ids]))

    # 3) Grubu oluştur
    group_id = str(uuid.uuid4())
    group = {
        "id": group_id,
        "tenant_id": tid,
        "group_name": data.group_name.strip(),
        "booking_ids": all_booking_ids,
        "status": "active",
        "total_rooms": len(all_booking_ids),
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.group_bookings.insert_one({**group})

    # 4) Her bookinge group_booking_id damgala
    for bid in all_booking_ids:
        await db.bookings.update_one(
            {"id": bid, "tenant_id": tid},
            {"$set": {"group_booking_id": group_id}},
        )

    group.pop("_id", None)
    _invalidate_group_bookings_cache(tid)
    return {
        "success": True,
        "group": group,
        "created_booking_ids": new_booking_ids,
    }


@router.get("/group-bookings")
async def list_group_bookings(
    current_user: User = Depends(get_current_user),
    nocache: bool = False,
):
    """List all group bookings (single-query bucket; N+1 yok).

    Önceki sürüm her grup için ayrı bookings.find() yapıyordu (50 grup =
    50 sorgu). Şimdi tüm booking_ids tek bir $in sorgusunda çekilip
    Python tarafında group_id'ye göre bucket'lanır.
    """
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    cache_key = _gb_cache_key(tid)
    if not nocache:
        cached = _gb_cache.get(cache_key)
        if cached is not None:
            return cached

    # 1) Tüm grupları çek
    groups: list[dict] = []
    all_booking_ids: list[str] = []
    async for g in db.group_bookings.find({"tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        bids = g.get("booking_ids") or []
        all_booking_ids.extend(bids)
        groups.append(g)

    # 2) Tüm bookings'i tek $in sorgusunda al
    bookings_by_id: dict[str, dict] = {}
    if all_booking_ids:
        async for b in db.bookings.find({"id": {"$in": all_booking_ids}, "tenant_id": tid}, {"_id": 0}):
            bookings_by_id[b["id"]] = b

    # 3) Bucket: her gruba kendi rezervasyonlarını ata + toplamları hesapla
    for g in groups:
        bks = [bookings_by_id[bid] for bid in (g.get("booking_ids") or []) if bid in bookings_by_id]
        g["bookings"] = bks
        g["total_amount"] = sum(b.get("total_amount", 0) for b in bks)
        g["total_paid"] = sum(b.get("paid_amount", 0) for b in bks)

    payload = {"groups": groups}
    _gb_cache.set(cache_key, payload, ttl=_GROUP_BOOKINGS_CACHE_TTL)
    return payload


@router.get("/group-bookings/{group_id}")
async def get_group_booking_detail(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed group booking info."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup rezervasyon bulunamadi")

    from security.encrypted_lookup import decrypt_booking_doc, decrypt_guest_doc

    bookings_list = []
    async for b in db.bookings.find({"id": {"$in": group.get("booking_ids", [])}, "tenant_id": tid}, {"_id": 0}):
        # PII at-rest: decrypt the booking (guest_email/guest_phone) and the joined
        # guest doc before returning so clients never receive AES envelopes or
        # internal blind-index tokens.
        b = decrypt_booking_doc(b)
        guest = None
        if b.get("guest_id"):
            guest = decrypt_guest_doc(await db.guests.find_one({"id": b["guest_id"], "tenant_id": tid}, {"_id": 0}))
        b["guest_detail"] = guest
        bookings_list.append(b)

    group["bookings"] = bookings_list
    group["total_amount"] = sum(b.get("total_amount", 0) for b in bookings_list)
    group["total_paid"] = sum(b.get("paid_amount", 0) for b in bookings_list)
    return group


@router.post("/group-bookings/{group_id}/add-room")
async def add_room_to_group(
    group_id: str,
    data: GroupBookingAddRoom,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Add a booking/room to a group."""
    _enforce_perm(current_user.role, "create_booking")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    booking = await db.bookings.find_one({"id": data.booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")
    await ensure_reservation_mutable(db, tid, booking)

    existing_ids = group.get("booking_ids", [])
    if data.booking_id not in existing_ids:
        existing_ids.append(data.booking_id)
        await db.group_bookings.update_one(
            {"id": group_id, "tenant_id": tid},
            {"$set": {"booking_ids": existing_ids, "total_rooms": len(existing_ids)}},
        )
        await db.bookings.update_one(
            {"id": data.booking_id, "tenant_id": tid},
            {"$set": {"group_booking_id": group_id}},
        )

    _invalidate_group_bookings_cache(tid)
    return {"success": True}


@router.post("/group-bookings/{group_id}/check-in-all")
async def group_check_in_all(
    group_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Check-in all reservations in a group — each via atomic transaction."""
    _enforce_perm(current_user.role, "checkin")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    group_booking_ids = list(group.get("booking_ids", []))
    group_bookings = {
        item["id"]: item
        async for item in db.bookings.find(
            {"id": {"$in": group_booking_ids}, "tenant_id": tid},
            {"_id": 0, "id": 1, "status": 1, "check_out": 1},
        )
    }
    business_date = await ensure_business_date_initialized(db, tid)
    checked_in = 0
    errors = []
    for bid in group_booking_ids:
        if reservation_is_historical(group_bookings.get(bid, {}), business_date["business_date"]):
            errors.append({"booking_id": bid, "error": "Geçmiş rezervasyon salt okunurdur"})
            continue
        try:
            await check_in_booking_atomic(
                booking_id=bid,
                tenant_id=tid,
                actor_id=current_user.id,
                actor_name=current_user.name,
            )
            checked_in += 1
            # Acente webhook: grup içinden tek tek emit (her booking ayrı agency olabilir)
            schedule_emit_reservation_updated(tid, bid, "checked_in", {"group_id": group_id})
        except CheckInError as e:
            errors.append({"booking_id": bid, "error": str(e)})

    _invalidate_group_bookings_cache(tid)
    return {"success": True, "checked_in_count": checked_in, "errors": errors}


@router.post("/group-bookings/{group_id}/check-out-all")
async def group_check_out_all(
    group_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Check-out all reservations in a group — each via atomic transaction."""
    _enforce_perm(current_user.role, "checkout")  # Bug CP Round-4
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    from core.atomic_checkin_checkout import CheckOutError, check_out_booking_atomic
    from routers.webhook_retry_service import schedule_emit_reservation_updated

    group_booking_ids = list(group.get("booking_ids", []))
    group_bookings = {
        item["id"]: item
        async for item in db.bookings.find(
            {"id": {"$in": group_booking_ids}, "tenant_id": tid},
            {"_id": 0, "id": 1, "status": 1, "check_out": 1},
        )
    }
    business_date = await ensure_business_date_initialized(db, tid)
    checked_out = 0
    errors = []
    for bid in group_booking_ids:
        if reservation_is_historical(group_bookings.get(bid, {}), business_date["business_date"]):
            errors.append({"booking_id": bid, "error": "Geçmiş rezervasyon salt okunurdur"})
            continue
        try:
            await check_out_booking_atomic(
                booking_id=bid,
                tenant_id=tid,
                actor_id=current_user.id,
                actor_name=current_user.name,
                force=True,  # Group checkout forces past balance blockers
            )
            checked_out += 1
            # Acente webhook: grup içinden tek tek emit (her booking ayrı agency olabilir)
            schedule_emit_reservation_updated(tid, bid, "checked_out", {"group_id": group_id})
        except CheckOutError as e:
            errors.append({"booking_id": bid, "error": str(e)})

    _invalidate_group_bookings_cache(tid)
    return {"success": True, "checked_out_count": checked_out, "errors": errors}


# ── Communication Log Endpoints ──


@router.post("/reservations/{booking_id}/communication")
async def add_communication_log(
    booking_id: str,
    data: CommunicationLogCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Add a communication log entry for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    log_entry = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "channel": data.channel,
        "direction": data.direction,
        "subject": data.subject,
        "content": data.content,
        "recipient": data.recipient,
        "sent_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.communication_logs.insert_one({**log_entry})

    await _log_activity(
        tid,
        booking_id,
        "communication_logged",
        current_user.name,
        {
            "channel": data.channel,
            "direction": data.direction,
        },
    )

    log_entry.pop("_id", None)
    return {"success": True, "log": log_entry}


@router.get("/reservations/{booking_id}/communication")
async def get_communication_logs(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get communication log for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    logs = []
    async for entry in db.communication_logs.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        logs.append(entry)

    return {"logs": logs}


# ── Deposit Management Endpoints ──


@router.get("/reservations/{booking_id}/deposits")
async def get_deposits(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get deposits for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    deposits = []
    async for d in db.deposits.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        deposits.append(d)

    return {"deposits": deposits}


@router.post("/reservations/{booking_id}/refund-deposit")
async def refund_deposit(
    booking_id: str,
    data: DepositRefund,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    """Refund a deposit."""
    _enforce_perm(current_user.role, "post_payment")  # Bug CP Round-3 — refund treated as payment-class mutation
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    deposit = await db.deposits.find_one(
        {
            "id": data.deposit_id,
            "booking_id": booking_id,
            "tenant_id": tid,
        },
        {"_id": 0},
    )
    if not deposit:
        raise HTTPException(status_code=404, detail="Depozito bulunamadi")
    if deposit.get("status") == "refunded":
        raise HTTPException(status_code=400, detail="Depozito tamamen iade edilmis")

    deposit_amount = round(float(deposit.get("amount", 0) or 0), 2)
    refunded_before = round(float(deposit.get("refunded_amount", 0) or 0), 2)
    refundable_amount = round(max(0.0, deposit_amount - refunded_before), 2)
    if refundable_amount <= 0:
        raise HTTPException(status_code=400, detail="Depozito tamamen iade edilmis")
    if data.refund_amount > refundable_amount:
        raise HTTPException(
            status_code=400,
            detail="Iade tutari kalan depozito bakiyesinden buyuk olamaz",
        )

    dedup = await claim_short_window_dedup(
        db,
        tenant_id=tid,
        scope=f"deposit_refund:booking:{booking_id}:deposit:{data.deposit_id}",
        fingerprint=f"{round(float(data.refund_amount), 2)}|{data.refund_method}",
    )
    if dedup["status"] == "duplicate":
        raise HTTPException(
            status_code=409,
            detail="Olası çift iade: aynı işlem saniyeler içinde tekrar gönderildi",
        )
    dedup_lock_id = dedup["lock_id"]

    now = datetime.now(UTC).isoformat()
    refund_id = str(uuid.uuid4())
    payment_id = str(uuid.uuid4())

    async def _commit(session):
        current_booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tid},
            {"_id": 0},
            session=session,
        )
        if not current_booking:
            raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

        current_deposit = await db.deposits.find_one(
            {"id": data.deposit_id, "booking_id": booking_id, "tenant_id": tid},
            {"_id": 0},
            session=session,
        )
        if not current_deposit:
            raise HTTPException(status_code=404, detail="Depozito bulunamadi")
        if current_deposit.get("status") == "refunded":
            raise HTTPException(status_code=400, detail="Depozito tamamen iade edilmis")

        current_amount = round(float(current_deposit.get("amount", 0) or 0), 2)
        current_refunded = round(float(current_deposit.get("refunded_amount", 0) or 0), 2)
        current_refundable = round(max(0.0, current_amount - current_refunded), 2)
        if current_refundable <= 0:
            raise HTTPException(status_code=400, detail="Depozito tamamen iade edilmis")
        if data.refund_amount > current_refundable:
            raise HTTPException(
                status_code=400,
                detail="Iade tutari kalan depozito bakiyesinden buyuk olamaz",
            )

        folio = await _ensure_reservation_folio(
            tid,
            current_booking,
            preferred_folio_id=current_deposit.get("folio_id"),
            session=session,
        )

        refund = {
            "id": refund_id,
            "payment_id": payment_id,
            "folio_id": folio["id"],
            "tenant_id": tid,
            "booking_id": booking_id,
            "deposit_id": data.deposit_id,
            "refund_amount": data.refund_amount,
            "refund_method": data.refund_method,
            "reason": data.reason,
            "status": "refunded",
            "refunded_by": current_user.name,
            "refunded_at": now,
        }
        await db.deposit_refunds.insert_one({**refund}, session=session)

        payment = {
            "id": payment_id,
            "tenant_id": tid,
            "folio_id": folio["id"],
            "booking_id": booking_id,
            "deposit_id": data.deposit_id,
            "deposit_refund_id": refund_id,
            "amount": -round(data.refund_amount, 2),
            "method": data.refund_method,
            "payment_type": "refund",
            "status": "refunded",
            "reference": f"deposit-refund:{refund_id}",
            "notes": data.reason,
            "processed_by": current_user.name,
            "processed_at": now,
            "voided": False,
        }
        await db.payments.insert_one({**payment}, session=session)

        refunded_total = round(current_refunded + data.refund_amount, 2)
        remaining = round(max(0.0, current_amount - refunded_total), 2)
        new_status = "refunded" if remaining == 0 else "partially_refunded"
        await db.deposits.update_one(
            {
                "id": data.deposit_id,
                "booking_id": booking_id,
                "tenant_id": tid,
            },
            {"$set": {"status": new_status, "refunded_amount": refunded_total}},
            session=session,
        )

        paid_amount = round(
            max(
                0.0,
                float(current_booking.get("paid_amount", 0) or 0) - data.refund_amount,
            ),
            2,
        )
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tid},
            {"$set": {"paid_amount": paid_amount}},
            session=session,
        )

        refund.pop("_id", None)
        payment.pop("_id", None)
        return {
            "success": True,
            "refund": refund,
            "payment": payment,
            "remaining_amount": remaining,
        }

    try:
        result = await _run_reservation_financial_transaction(
            tenant_id=tid,
            booking_id=booking_id,
            resources=[("deposit", data.deposit_id)],
            callback=_commit,
        )
    except DuplicateKeyError:
        await _release_dedup_safely(dedup_lock_id, operation="refund_deposit")
        raise HTTPException(
            status_code=409,
            detail="Depozito iadesi eşzamanlı veya tekrarlanan işlem nedeniyle tamamlanamadı",
        ) from None
    except Exception:
        await _release_dedup_safely(dedup_lock_id, operation="refund_deposit")
        raise

    await _run_post_commit_hook(
        lambda: _refresh_cached_folio_balance(tid, result["payment"]["folio_id"]),
        operation="refund_deposit_folio_balance",
    )

    await _run_post_commit_hook(
        lambda: _log_activity(
            tid,
            booking_id,
            "deposit_refunded",
            current_user.name,
            {
                "deposit_id": data.deposit_id,
                "refund_amount": data.refund_amount,
            },
        ),
        operation="refund_deposit_activity",
    )

    async def _emit_webhook():
        from routers.webhook_retry_service import schedule_emit_reservation_updated

        schedule_emit_reservation_updated(
            tid,
            booking_id,
            "payment_refunded",
            {
                "payment_id": result["payment"]["id"],
                "amount": data.refund_amount,
                "method": data.refund_method,
                "payment_type": "refund",
            },
        )

    await _run_post_commit_hook(
        _emit_webhook,
        operation="refund_deposit_webhook",
    )
    return result


@router.get("/deposits/all")
async def list_all_deposits(current_user: User = Depends(get_current_user)):
    """List all deposits across all reservations."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    deposits = []
    async for d in db.deposits.find({"tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        # Enrich with booking info
        booking = await db.bookings.find_one({"id": d.get("booking_id"), "tenant_id": tid}, {"_id": 0, "guest_name": 1, "room_number": 1, "check_in": 1, "check_out": 1})
        if booking:
            d["guest_name"] = booking.get("guest_name")
            d["room_number"] = booking.get("room_number")
        deposits.append(d)

    return {"deposits": deposits}


class ReservationGuestCreate(BaseModel):
    """Guest fields accepted when linking another occupant to a reservation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=200)
    email: str = Field("", max_length=320)
    phone: str = Field("", max_length=40)
    id_type: str = Field("tc_kimlik", max_length=40)
    id_number: str = Field("", max_length=80)
    nationality: str = Field("TR", max_length=80)
    date_of_birth: str = Field("", max_length=20)
    gender: str = Field("", max_length=40)
    address: str = Field("", max_length=1000)
    city: str = Field("", max_length=160)
    country: str = Field("", max_length=160)
    notes: str = Field("", max_length=2000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if len(cleaned) < 2:
            raise ValueError("Misafir adı en az 2 karakter olmalıdır")
        return cleaned

    @field_validator(
        "email",
        "phone",
        "id_type",
        "id_number",
        "nationality",
        "date_of_birth",
        "gender",
        "address",
        "city",
        "country",
        "notes",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


@router.post("/reservations/{booking_id}/guests")
async def add_reservation_guest(
    booking_id: str,
    data: ReservationGuestCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    _enforce_perm(current_user.role, "edit_booking")
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    await ensure_reservation_mutable(db, tid, booking)

    from routers.pms_guests import _encrypt_guest

    candidate = data.model_dump()
    if candidate.get("id_type") == "passport" and candidate.get("id_number"):
        candidate["passport_number"] = candidate["id_number"]

    existing_guest = await find_existing_guest_by_identity(db.guests, tid, candidate)
    created = existing_guest is None
    if existing_guest:
        guest_id = existing_guest["id"]
    else:
        guest_id = f"GST-{uuid.uuid4().hex[:8].upper()}"
        guest = {
            **candidate,
            "id": guest_id,
            "tenant_id": tid,
            "created_at": datetime.now(UTC).isoformat(),
            "total_stays": 0,
            "total_spend": 0.0,
        }
        from security.search_normalize import normalized_set_for_update

        normalized = normalized_set_for_update(guest, collection="guests")
        guest = _encrypt_guest(guest)
        guest.update(normalized)
        await db.guests.insert_one(guest)

    already_linked = guest_id == booking.get("guest_id") or bool(
        await db.booking_guests.find_one(
            {"tenant_id": tid, "booking_id": booking_id, "guest_id": guest_id},
            {"_id": 0, "id": 1},
        )
    )
    if already_linked:
        return {
            "status": "ok",
            "guest_id": guest_id,
            "created": created,
            "linked": False,
            "already_linked": True,
        }

    await db.booking_guests.insert_one({
        "id": f"BG-{uuid.uuid4().hex[:8].upper()}",
        "tenant_id": tid,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "created_at": datetime.now(UTC).isoformat(),
    })

    return {
        "status": "ok",
        "guest_id": guest_id,
        "created": created,
        "linked": True,
        "already_linked": False,
    }
