"""Fail-closed support for the explicitly gated Nilvera Sandbox fixture test."""

import asyncio
import hashlib
import hmac
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.incoming import NilveraIncomingService
from core.integrations.nilvera.mapper import NilveraEInvoicePayload, NilveraInvoiceMapper, SellerSnapshot
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome
from models.schemas.invoicing import Invoice, InvoiceItem

_FIXTURE_ID_PATTERN = re.compile(r"^TST\d{13}$")
_SAFE_PROVIDER_CODE_PATTERN = re.compile(r"^[A-Z0-9_.-]{1,64}$")
_SAFE_EXCEPTION_TYPES = {
    "NilveraApiError",
    "NilveraAuthError",
    "NilveraBusinessRuleError",
    "NilveraDuplicateError",
    "NilveraNotFoundError",
    "NilveraRateLimitError",
    "NilveraServerError",
    "NilveraTimeoutError",
    "NilveraValidationError",
}
_ACCEPTED_STATUSES = {"accepted", "basarili", "başarılı", "onaylandi", "onaylandı", "succeed", "success"}
_REJECTED_STATUSES = {"cancelled", "canceled", "error", "failed", "hatali", "hatalı", "rejected", "reddedildi"}
_PENDING_STATUSES = {"pending", "processing", "waiting", "isleniyor", "işleniyor", "kuyrukta"}
DEFINITIVE_REJECTION = "DEFINITIVE_REJECTION"
AMBIGUOUS_WRITE = "AMBIGUOUS_WRITE"
FOUND = "FOUND"
NOT_FOUND_OR_NOT_VISIBLE = "NOT_FOUND_OR_NOT_VISIBLE"


class SandboxFixtureError(RuntimeError):
    def __init__(
        self,
        safe_code: str,
        *,
        provider_write_count: int = 0,
        failure_stage: str | None = None,
        http_status_class: str | None = None,
        provider_code: str | None = None,
        exception_type: str | None = None,
        write_disposition: str | None = None,
    ):
        super().__init__(safe_code)
        self.safe_code = safe_code
        self.provider_write_count = provider_write_count
        self.failure_stage = failure_stage
        self.http_status_class = http_status_class
        self.provider_code = provider_code
        self.exception_type = exception_type
        self.write_disposition = write_disposition


class SandboxFixtureBlocked(SandboxFixtureError):
    pass


class SandboxFixtureFailed(SandboxFixtureError):
    pass


@dataclass(frozen=True)
class SandboxFixtureResult:
    correlation_label: str
    provider_write_count: int
    sender_match: bool
    receiver_match: bool
    provider_outcome: ProviderInvoiceOutcome
    receiver_visible: bool


@dataclass(frozen=True)
class SandboxFixtureReconciliationResult:
    correlation_label: str
    outgoing_result: str
    outgoing_outcome: ProviderInvoiceOutcome | None
    outgoing_detail_match: bool | None
    receiver_visibility: str
    receiver_detail_match: bool | None
    receiver_status_ready: bool | None


def ensure_distinct_sandbox_keys(sender_key: str, receiver_key: str) -> None:
    if not sender_key or not receiver_key:
        raise SandboxFixtureBlocked("BLOCKED_MISSING_SANDBOX_KEY")
    if hmac.compare_digest(sender_key.encode(), receiver_key.encode()):
        raise SandboxFixtureBlocked("BLOCKED_IDENTICAL_SANDBOX_KEYS")


def _http_status_class(status: int | None) -> str | None:
    if status is None or status < 100 or status > 599:
        return None
    return f"{status // 100}xx"


def _safe_provider_code(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if _SAFE_PROVIDER_CODE_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def _safe_exception_type(exc: Exception) -> str:
    exception_type = type(exc).__name__
    return exception_type if exception_type in _SAFE_EXCEPTION_TYPES else "UnexpectedError"


def _send_failure(exc: NilveraApiError, *, provider_write_count: int) -> SandboxFixtureError:
    metadata = {
        "provider_write_count": provider_write_count,
        "failure_stage": "SEND_MODEL",
        "http_status_class": _http_status_class(exc.http_status),
        "provider_code": _safe_provider_code(exc.provider_code),
        "exception_type": _safe_exception_type(exc),
    }
    if exc.http_status in {400, 422}:
        return SandboxFixtureFailed(
            "FIXTURE_VALIDATION_REJECTED",
            write_disposition=DEFINITIVE_REJECTION,
            **metadata,
        )
    return SandboxFixtureBlocked(
        "BLOCKED_FIXTURE_WRITE_OUTCOME_UNKNOWN",
        write_disposition=AMBIGUOUS_WRITE,
        **metadata,
    )


def build_fixture_identity(*, year: int, run_id: str, hmac_key: str) -> str:
    if year < 2000 or year > 9999 or not run_id.isdigit() or len(hmac_key) < 32:
        raise SandboxFixtureBlocked("BLOCKED_INVALID_FIXTURE_ID_INPUT")
    digest = hmac.new(hmac_key.encode(), f"nilvera-fixture:{year}:{run_id}".encode(), hashlib.sha256).digest()
    run9 = int.from_bytes(digest[:8], "big") % 1_000_000_000
    identity = f"TST{year}{run9:09d}"
    if len(identity) != 16 or _FIXTURE_ID_PATTERN.fullmatch(identity) is None:
        raise SandboxFixtureFailed("FIXTURE_ID_CONTRACT_FAILED")
    return identity


def fixture_correlation_label(identity: str, hmac_key: str) -> str:
    digest = hmac.new(hmac_key.encode(), identity.encode(), hashlib.sha256).hexdigest()
    return digest[:12]


def build_fixture_payload(
    *,
    fixture_identity: str,
    seller_tax_number: str,
    buyer_tax_number: str,
    buyer_alias: str,
    issue_date: datetime,
) -> NilveraEInvoicePayload:
    if len(fixture_identity) != 16 or _FIXTURE_ID_PATTERN.fullmatch(fixture_identity) is None:
        raise SandboxFixtureFailed("FIXTURE_ID_CONTRACT_FAILED")

    seller = SellerSnapshot(
        tax_number=seller_tax_number,
        name="NILVERA SANDBOX FIXTURE SENDER",
        tax_office="SANDBOX",
        country="TURKIYE",
        city="ANKARA",
        district="CANKAYA",
        address="SANDBOX FIXTURE ADDRESS",
    )
    invoice = Invoice(
        id=str(uuid.uuid4()),
        tenant_id="nilvera-sandbox-fixture",
        document_kind="E_INVOICE",
        invoice_number="LOCAL_VALUE_MUST_NOT_BE_USED",
        invoice_type="SATIS",
        profile="TICARIFATURA",
        series=fixture_identity,
        currency="TRY",
        exchange_rate=Decimal("1.0"),
        issue_date=issue_date,
        buyer_tax_number=buyer_tax_number,
        buyer_legal_name="NILVERA SANDBOX FIXTURE RECEIVER",
        buyer_country_name="TURKIYE",
        buyer_city="ISTANBUL",
        buyer_district="SISLI",
        buyer_address="SANDBOX FIXTURE ADDRESS",
        payable_total=Decimal("1.20"),
        line_extension_total=Decimal("1.00"),
        kdv_total=Decimal("0.20"),
        other_tax_total=Decimal("0.00"),
        discount_total=Decimal("0.00"),
        items=[
            InvoiceItem(
                description="Nilvera Sandbox Fixture",
                quantity=Decimal("1.0"),
                tax_quantity=Decimal("1.0"),
                unit_code="C62",
                unit_price=Decimal("1.00"),
                tax_unit_price=Decimal("1.00"),
                discount_amount=Decimal("0.00"),
                line_extension_amount=Decimal("1.00"),
                kdv_rate=Decimal("20.0"),
                kdv_amount=Decimal("0.20"),
                total=Decimal("1.20"),
            )
        ],
    )
    payload = NilveraInvoiceMapper.map_to_nilvera(invoice, seller, buyer_alias, uuid.uuid4())
    if payload.EInvoice.InvoiceInfo.InvoiceSerieOrNumber != fixture_identity:
        raise SandboxFixtureFailed("FIXTURE_ID_TRANSFER_FAILED")
    if payload.EInvoice.InvoiceInfo.InvoiceProfile != "TICARIFATURA" or payload.EInvoice.InvoiceInfo.InvoiceType != "SATIS":
        raise SandboxFixtureFailed("FIXTURE_DOCUMENT_CONTRACT_FAILED")
    return payload


async def company_identity_matches(client: Any, expected_tax_number: str) -> bool:
    try:
        response = await client.get(NilveraEndpoints.GET_COMPANY)
    except Exception:
        raise SandboxFixtureBlocked("BLOCKED_COMPANY_IDENTITY_QUERY") from None
    if not isinstance(response, dict):
        raise SandboxFixtureBlocked("BLOCKED_COMPANY_IDENTITY_PARSE")
    tax_number = response.get("TaxNumber")
    if not isinstance(tax_number, str) or not tax_number.isdigit() or len(tax_number) not in (10, 11):
        raise SandboxFixtureBlocked("BLOCKED_COMPANY_IDENTITY_PARSE")
    return hmac.compare_digest(tax_number.encode(), expected_tax_number.encode())


def _normalize(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value.strip().lower() if character.isalnum())


def parse_sale_outcome(response: Any) -> ProviderInvoiceOutcome:
    item: Any
    if isinstance(response, list) and response:
        item = response[0]
    elif isinstance(response, dict):
        item = response
    else:
        raise SandboxFixtureFailed("FIXTURE_SALE_STATUS_PARSE_FAILED", provider_write_count=1)
    if not isinstance(item, dict):
        raise SandboxFixtureFailed("FIXTURE_SALE_STATUS_PARSE_FAILED", provider_write_count=1)

    invoice_status = item.get("InvoiceStatus")
    raw_status = invoice_status.get("Code") if isinstance(invoice_status, dict) else item.get("Status")
    normalized = _normalize(raw_status)
    if normalized in {_normalize(value) for value in _ACCEPTED_STATUSES}:
        return ProviderInvoiceOutcome.ACCEPTED
    if normalized in {_normalize(value) for value in _REJECTED_STATUSES}:
        return ProviderInvoiceOutcome.REJECTED
    if normalized in {_normalize(value) for value in _PENDING_STATUSES}:
        return ProviderInvoiceOutcome.PENDING
    return ProviderInvoiceOutcome.UNKNOWN


def _matches_fixture(candidate: str, target_digest: bytes, hmac_key: str) -> bool:
    candidate_digest = hmac.new(hmac_key.encode(), candidate.encode(), hashlib.sha256).digest()
    return hmac.compare_digest(candidate_digest, target_digest)


def _matching_provider_uuids(
    response: Any,
    *,
    target_digest: bytes,
    hmac_key: str,
    parse_error_code: str,
) -> tuple[str, ...]:
    if not isinstance(response, dict) or not isinstance(response.get("Content"), list):
        raise SandboxFixtureFailed(parse_error_code)

    matches: set[str] = set()
    for item in response["Content"]:
        if not isinstance(item, dict):
            raise SandboxFixtureFailed(parse_error_code)
        invoice_number = item.get("InvoiceNumber")
        if not isinstance(invoice_number, str) or not _matches_fixture(invoice_number, target_digest, hmac_key):
            continue
        try:
            matches.add(str(uuid.UUID(item.get("UUID", ""))))
        except (AttributeError, TypeError, ValueError):
            raise SandboxFixtureFailed(parse_error_code) from None
    return tuple(matches)


def _detail_matches_fixture(detail: Any, *, target_digest: bytes, hmac_key: str) -> bool:
    if not isinstance(detail, dict):
        return False
    invoice_number = detail.get("InvoiceNumber")
    return isinstance(invoice_number, str) and _matches_fixture(invoice_number, target_digest, hmac_key) and detail.get("InvoiceProfile") == "TICARIFATURA" and detail.get("InvoiceType") == "SATIS"


async def reconcile_incoming_commercial_fixture(
    *,
    sender_client: Any,
    receiver_client: Any,
    hmac_key: str,
    run_id: str,
    reference_time: datetime,
) -> SandboxFixtureReconciliationResult:
    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_REFERENCE_TIME")

    identity = build_fixture_identity(year=reference_time.year, run_id=run_id, hmac_key=hmac_key)
    correlation_label = fixture_correlation_label(identity, hmac_key)
    target_digest = hmac.new(hmac_key.encode(), identity.encode(), hashlib.sha256).digest()
    params = {
        "Search": identity,
        "StartDate": (reference_time - timedelta(days=1)).isoformat(),
        "EndDate": (reference_time + timedelta(days=1)).isoformat(),
        "Page": "1",
        "PageSize": "100",
    }

    try:
        outgoing_page = await sender_client.get(
            NilveraEndpoints.LIST_SALE_INVOICES,
            params=params,
            correlation_id=correlation_label,
        )
        incoming_page = await receiver_client.get(
            NilveraEndpoints.LIST_PURCHASE_INVOICES,
            params=params,
            correlation_id=correlation_label,
        )
    except Exception:
        raise SandboxFixtureBlocked("BLOCKED_FIXTURE_RECONCILIATION_QUERY") from None

    outgoing_matches = _matching_provider_uuids(
        outgoing_page,
        target_digest=target_digest,
        hmac_key=hmac_key,
        parse_error_code="FIXTURE_OUTGOING_RECONCILIATION_PARSE_FAILED",
    )
    incoming_matches = _matching_provider_uuids(
        incoming_page,
        target_digest=target_digest,
        hmac_key=hmac_key,
        parse_error_code="FIXTURE_INCOMING_RECONCILIATION_PARSE_FAILED",
    )
    if len(outgoing_matches) > 1 or len(incoming_matches) > 1:
        raise SandboxFixtureBlocked("CONFLICT_FIXTURE_RECONCILIATION")

    outgoing_result = NOT_FOUND_OR_NOT_VISIBLE
    outgoing_outcome = None
    outgoing_detail_match = None
    if outgoing_matches:
        provider_uuid = outgoing_matches[0]
        try:
            status_response = await sender_client.get(
                NilveraEndpoints.GET_SALE_INVOICE_STATUS.format(uuid=provider_uuid),
                correlation_id=correlation_label,
            )
            detail_response = await sender_client.get(
                NilveraEndpoints.GET_SALE_INVOICE_DETAIL.format(uuid=provider_uuid),
                correlation_id=correlation_label,
            )
        except Exception:
            raise SandboxFixtureBlocked("BLOCKED_FIXTURE_OUTGOING_RECONCILIATION_QUERY") from None
        outgoing_outcome = parse_sale_outcome(status_response)
        outgoing_detail_match = _detail_matches_fixture(
            detail_response,
            target_digest=target_digest,
            hmac_key=hmac_key,
        )
        if outgoing_outcome == ProviderInvoiceOutcome.UNKNOWN or not outgoing_detail_match:
            raise SandboxFixtureFailed("FIXTURE_OUTGOING_RECONCILIATION_MISMATCH")
        outgoing_result = FOUND

    receiver_visibility = NOT_FOUND_OR_NOT_VISIBLE
    receiver_detail_match = None
    receiver_status_ready = None
    if incoming_matches:
        provider_uuid = incoming_matches[0]
        incoming_service = NilveraIncomingService(receiver_client)
        try:
            detail = await incoming_service.fetch_incoming_invoice_detail(provider_uuid)
            status = await incoming_service.fetch_incoming_invoice_status(provider_uuid)
        except Exception:
            raise SandboxFixtureBlocked("BLOCKED_FIXTURE_RECEIVER_RECONCILIATION_QUERY") from None
        receiver_detail_match = _matches_fixture(detail.invoice_number, target_digest, hmac_key) and detail.invoice_profile == "TICARIFATURA" and detail.invoice_type == "SATIS"
        receiver_status_ready = _normalize(status.status_code) in {"succeed", "success"}
        if not receiver_detail_match:
            raise SandboxFixtureFailed("FIXTURE_RECEIVER_RECONCILIATION_MISMATCH")
        receiver_visibility = FOUND

    return SandboxFixtureReconciliationResult(
        correlation_label=correlation_label,
        outgoing_result=outgoing_result,
        outgoing_outcome=outgoing_outcome,
        outgoing_detail_match=outgoing_detail_match,
        receiver_visibility=receiver_visibility,
        receiver_detail_match=receiver_detail_match,
        receiver_status_ready=receiver_status_ready,
    )


async def prepare_incoming_commercial_fixture(
    *,
    sender_client: Any,
    receiver_client: Any,
    sender_key: str,
    receiver_key: str,
    hmac_key: str,
    run_id: str,
    seller_tax_number: str,
    buyer_tax_number: str,
    buyer_alias: str,
    now: datetime | None = None,
    outgoing_delays: Sequence[float] = (1, 2, 4, 5, 5, 5),
    incoming_delays: Sequence[float] = (1, 2, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5),
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SandboxFixtureResult:
    ensure_distinct_sandbox_keys(sender_key, receiver_key)
    sender_match = await company_identity_matches(sender_client, seller_tax_number)
    receiver_match = await company_identity_matches(receiver_client, buyer_tax_number)
    if not sender_match or not receiver_match:
        raise SandboxFixtureBlocked("BLOCKED_SANDBOX_COMPANY_MISMATCH")

    current_time = now or datetime.now(UTC)
    identity = build_fixture_identity(year=current_time.year, run_id=run_id, hmac_key=hmac_key)
    correlation_label = fixture_correlation_label(identity, hmac_key)
    payload = build_fixture_payload(
        fixture_identity=identity,
        seller_tax_number=seller_tax_number,
        buyer_tax_number=buyer_tax_number,
        buyer_alias=buyer_alias,
        issue_date=current_time,
    )

    provider_write_count = 1
    try:
        response = await sender_client.post(
            NilveraEndpoints.SEND_INVOICE_MODEL,
            json=payload.model_dump(mode="json", by_alias=True),
            correlation_id=correlation_label,
            retryable=False,
        )
    except NilveraApiError as exc:
        raise _send_failure(exc, provider_write_count=provider_write_count) from None
    except Exception as exc:
        raise SandboxFixtureBlocked(
            "BLOCKED_FIXTURE_WRITE_OUTCOME_UNKNOWN",
            provider_write_count=provider_write_count,
            failure_stage="SEND_MODEL",
            exception_type=_safe_exception_type(exc),
            write_disposition=AMBIGUOUS_WRITE,
        ) from None

    if not isinstance(response, dict):
        raise SandboxFixtureBlocked(
            "BLOCKED_FIXTURE_SEND_RESPONSE_PARSE",
            provider_write_count=provider_write_count,
            failure_stage="SEND_RESPONSE_PARSE",
            exception_type="ResponseParseError",
            write_disposition=AMBIGUOUS_WRITE,
        )
    try:
        provider_uuid = str(uuid.UUID(response.get("UUID", "")))
    except (AttributeError, TypeError, ValueError):
        raise SandboxFixtureBlocked(
            "BLOCKED_FIXTURE_SEND_RESPONSE_PARSE",
            provider_write_count=provider_write_count,
            failure_stage="SEND_RESPONSE_PARSE",
            exception_type="ResponseParseError",
            write_disposition=AMBIGUOUS_WRITE,
        ) from None

    provider_outcome = ProviderInvoiceOutcome.PENDING
    for delay in outgoing_delays:
        await sleeper(delay)
        try:
            status_response = await sender_client.get(
                NilveraEndpoints.GET_SALE_INVOICE_STATUS.format(uuid=provider_uuid),
                correlation_id=correlation_label,
            )
        except Exception:
            raise SandboxFixtureFailed("FIXTURE_SALE_STATUS_QUERY_FAILED", provider_write_count=provider_write_count) from None
        provider_outcome = parse_sale_outcome(status_response)
        if provider_outcome == ProviderInvoiceOutcome.ACCEPTED:
            break
        if provider_outcome in {ProviderInvoiceOutcome.REJECTED, ProviderInvoiceOutcome.CANCELLED}:
            raise SandboxFixtureFailed("FIXTURE_PROVIDER_REJECTED", provider_write_count=provider_write_count)
        if provider_outcome == ProviderInvoiceOutcome.UNKNOWN:
            raise SandboxFixtureFailed("FIXTURE_SALE_STATUS_PARSE_FAILED", provider_write_count=provider_write_count)
    else:
        raise SandboxFixtureBlocked("BLOCKED_FIXTURE_SALE_STATUS_PENDING", provider_write_count=provider_write_count)

    target_digest = hmac.new(hmac_key.encode(), identity.encode(), hashlib.sha256).digest()
    incoming_service = NilveraIncomingService(receiver_client)
    end_date = current_time
    start_date = end_date - timedelta(days=31)
    for delay in incoming_delays:
        await sleeper(delay)
        try:
            page = await incoming_service.fetch_incoming_invoices(start_date, end_date, page=1, page_size=100)
        except Exception:
            raise SandboxFixtureFailed("FIXTURE_RECEIVER_LIST_QUERY_FAILED", provider_write_count=provider_write_count) from None
        for summary in page.items:
            if not _matches_fixture(summary.invoice_number, target_digest, hmac_key):
                continue
            try:
                detail = await incoming_service.fetch_incoming_invoice_detail(summary.provider_uuid)
                status = await incoming_service.fetch_incoming_invoice_status(summary.provider_uuid)
            except Exception:
                raise SandboxFixtureFailed("FIXTURE_RECEIVER_VERIFICATION_FAILED", provider_write_count=provider_write_count) from None
            if detail.invoice_profile != "TICARIFATURA" or detail.invoice_type != "SATIS":
                raise SandboxFixtureFailed("FIXTURE_RECEIVER_DOCUMENT_MISMATCH", provider_write_count=provider_write_count)
            if _normalize(status.status_code) not in {"succeed", "success"}:
                raise SandboxFixtureBlocked("BLOCKED_FIXTURE_RECEIVER_NOT_READY", provider_write_count=provider_write_count)
            return SandboxFixtureResult(
                correlation_label=correlation_label,
                provider_write_count=provider_write_count,
                sender_match=sender_match,
                receiver_match=receiver_match,
                provider_outcome=provider_outcome,
                receiver_visible=True,
            )

    raise SandboxFixtureBlocked("BLOCKED_FIXTURE_NOT_VISIBLE", provider_write_count=provider_write_count)
