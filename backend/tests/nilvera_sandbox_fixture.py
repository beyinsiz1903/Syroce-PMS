"""Fail-closed support for the explicitly gated Nilvera Sandbox fixture test."""

import asyncio
import hashlib
import hmac
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.incoming import NilveraIncomingService
from core.integrations.nilvera.mapper import NilveraEInvoicePayload, NilveraInvoiceMapper, SellerSnapshot
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome
from models.schemas.invoicing import Invoice, InvoiceItem

_FIXTURE_ID_PATTERN = re.compile(r"^TST\d{13}$")
_SAFE_PROVIDER_CODE_PATTERN = re.compile(r"^[A-Z0-9_.-]{1,64}$")
_SAFE_VALIDATION_ISSUE_PATTERN = re.compile(r"^FIELD=[A-Za-z0-9_.]+;REASON=[A-Z0-9_]+(?:\|FIELD=[A-Za-z0-9_.]+;REASON=[A-Z0-9_]+)*$")
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
MATCH_COUNT_ZERO = "ZERO"
MATCH_COUNT_ONE = "ONE"
MATCH_COUNT_MULTIPLE = "MULTIPLE"
RECONCILIATION_WINDOW_DAYS = 3
RECONCILIATION_PAGE_SIZE = 100
RECONCILIATION_MAX_PAGES = 20
RECONCILIATION_MAX_DETAIL_CANDIDATES = 20
PAGE_COUNT_ONE = "ONE"
PAGE_COUNT_TWO_TO_FIVE = "TWO_TO_FIVE"
PAGE_COUNT_SIX_TO_TEN = "SIX_TO_TEN"
PAGE_COUNT_ELEVEN_TO_LIMIT = "ELEVEN_TO_LIMIT"
BLOCKED_NOT_FOUND_AFTER_EXHAUSTIVE_READ = "BLOCKED_NOT_FOUND_AFTER_EXHAUSTIVE_READ"
FIELD_PRESENT = "FIELD_PRESENT"
FIELD_MISSING = "FIELD_MISSING"
FORMAT_VALID = "FORMAT_VALID"
FORMAT_INVALID = "FORMAT_INVALID"
TOTAL_MISMATCH = "TOTAL_MISMATCH"

_CORRELATION_FIELDS = (
    "InvoiceNumber",
    "InvoiceSerieOrNumber",
    "InvoiceNo",
    "DocumentNumber",
)
_PROFILE_FIELDS = ("InvoiceProfile", "DocumentProfile", "Profile")
_TYPE_FIELDS = ("InvoiceType", "DocumentType", "Type")
_OUTGOING_COUNTERPART_FIELDS = ("BuyerTaxNumber", "ReceiverTaxNumber", "TaxNumber")
_INCOMING_COUNTERPART_FIELDS = ("SenderTaxNumber", "SellerTaxNumber", "TaxNumber")


class SandboxFixtureError(RuntimeError):
    def __init__(
        self,
        safe_code: str,
        *,
        provider_write_count: int = 0,
        failure_stage: str | None = None,
        http_status: int | None = None,
        http_status_class: str | None = None,
        provider_code: str | None = None,
        validation_issue: str | None = None,
        exception_type: str | None = None,
        write_disposition: str | None = None,
        sender_match: bool | None = None,
        receiver_match: bool | None = None,
        match_count_class: str | None = None,
        sender_page_count_class: str | None = None,
        receiver_page_count_class: str | None = None,
    ):
        super().__init__(safe_code)
        self.safe_code = safe_code
        self.provider_write_count = provider_write_count
        self.failure_stage = failure_stage
        self.http_status = http_status
        self.http_status_class = http_status_class
        self.provider_code = provider_code
        self.validation_issue = validation_issue
        self.exception_type = exception_type
        self.write_disposition = write_disposition
        self.sender_match = sender_match
        self.receiver_match = receiver_match
        self.match_count_class = match_count_class
        self.sender_page_count_class = sender_page_count_class
        self.receiver_page_count_class = receiver_page_count_class


class SandboxFixtureBlocked(SandboxFixtureError):
    pass


class SandboxFixtureFailed(SandboxFixtureError):
    pass


class ReadOnlySandboxClient:
    """Allow only non-retrying GET requests during reconciliation."""

    def __init__(self, client: Any):
        self._client = client
        self._http_statuses: list[int] = []

    @property
    def exact_http_status(self) -> int | None:
        unique_statuses = set(self._http_statuses)
        if len(unique_statuses) != 1:
            return None
        return next(iter(unique_statuses))

    async def get(self, path: str, **kwargs: Any) -> Any:
        kwargs["retryable"] = False
        try:
            return await self._client.get(path, **kwargs)
        finally:
            status = getattr(self._client, "last_http_status", None)
            if isinstance(status, int) and 100 <= status <= 599:
                self._http_statuses.append(status)

    async def post(self, *_args: Any, **_kwargs: Any) -> Any:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_NON_GET_METHOD")

    async def put(self, *_args: Any, **_kwargs: Any) -> Any:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_NON_GET_METHOD")

    async def patch(self, *_args: Any, **_kwargs: Any) -> Any:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_NON_GET_METHOD")

    async def delete(self, *_args: Any, **_kwargs: Any) -> Any:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_NON_GET_METHOD")


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
    provider_write_count: int
    sender_match: bool
    receiver_match: bool
    match_count_class: str
    outgoing_result: str
    outgoing_outcome: ProviderInvoiceOutcome | None
    outgoing_detail_match: bool | None
    receiver_visibility: str
    receiver_detail_match: bool | None
    receiver_status_ready: bool | None
    sender_page_count_class: str
    receiver_page_count_class: str
    http_status: int | None


@dataclass(frozen=True)
class _ReconciliationPages:
    items: tuple[dict[str, Any], ...]
    page_count: int
    page_count_class: str


@dataclass(frozen=True)
class _ReconciliationCandidates:
    provider_uuids: tuple[str, ...]
    used_detail_fallback: bool


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


def _safe_validation_issue(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if len(normalized) > 512 or _SAFE_VALIDATION_ISSUE_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def _safe_exception_type(exc: Exception) -> str:
    exception_type = type(exc).__name__
    return exception_type if exception_type in _SAFE_EXCEPTION_TYPES else "UnexpectedError"


def _send_failure(exc: NilveraApiError, *, provider_write_count: int) -> SandboxFixtureError:
    validation_issue = "|".join(exc.safe_validation_issues)
    metadata = {
        "provider_write_count": provider_write_count,
        "failure_stage": "SEND_MODEL",
        "http_status": exc.http_status,
        "http_status_class": _http_status_class(exc.http_status),
        "provider_code": _safe_provider_code(exc.provider_code),
        "validation_issue": _safe_validation_issue(validation_issue),
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


def _reconciliation_query_failure(
    exc: Exception,
    *,
    failure_stage: str,
    sender_match: bool,
    receiver_match: bool,
) -> SandboxFixtureBlocked:
    http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
    provider_code = exc.provider_code if isinstance(exc, NilveraApiError) else None
    return SandboxFixtureBlocked(
        "BLOCKED_FIXTURE_RECONCILIATION_QUERY",
        failure_stage=failure_stage,
        http_status=http_status,
        http_status_class=_http_status_class(http_status),
        provider_code=_safe_provider_code(provider_code),
        exception_type=_safe_exception_type(exc),
        sender_match=sender_match,
        receiver_match=receiver_match,
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


def classify_fixture_payload_contract(payload: NilveraEInvoicePayload) -> dict[str, str]:
    """Classify the emitted Send/Model fixture without exposing any field values."""
    einvoice = payload.EInvoice
    info = einvoice.InvoiceInfo
    lines = einvoice.InvoiceLines
    line_extension_sum = sum((line.Quantity * line.Price) - line.AllowanceTotal for line in lines)
    allowance_sum = sum(line.AllowanceTotal for line in lines)
    kdv_sum = sum(line.KDVTotal for line in lines)
    kdv_by_rate = {
        Decimal("1"): Decimal("0"),
        Decimal("8"): Decimal("0"),
        Decimal("10"): Decimal("0"),
        Decimal("18"): Decimal("0"),
        Decimal("20"): Decimal("0"),
    }
    line_kdv_matches = True
    for line in lines:
        if line.KDVPercent in kdv_by_rate:
            kdv_by_rate[line.KDVPercent] += line.KDVTotal
        expected_kdv = (((line.Quantity * line.Price) - line.AllowanceTotal) * line.KDVPercent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_kdv_matches = line_kdv_matches and line.KDVTotal == expected_kdv

    supplier_present = all(
        isinstance(value, str) and bool(value.strip())
        for value in (
            einvoice.CompanyInfo.TaxNumber,
            einvoice.CompanyInfo.Name,
            einvoice.CompanyInfo.Address,
            einvoice.CompanyInfo.City,
            einvoice.CompanyInfo.Country,
        )
    )
    customer_present = all(
        isinstance(value, str) and bool(value.strip())
        for value in (
            einvoice.CustomerInfo.TaxNumber,
            einvoice.CustomerInfo.Name,
            einvoice.CustomerInfo.Address,
            einvoice.CustomerInfo.City,
            einvoice.CustomerInfo.Country,
        )
    )
    identity = info.InvoiceSerieOrNumber
    identity_valid = bool(identity) and ((len(identity) == 3 and identity.isascii() and identity.isalnum()) or (len(identity) == 16 and _FIXTURE_ID_PATTERN.fullmatch(identity) is not None))

    return {
        "InvoiceInfo": FIELD_PRESENT,
        "Scenario": FIELD_MISSING,
        "InvoiceType": FORMAT_VALID if info.InvoiceType == "SATIS" else FORMAT_INVALID,
        "InvoiceProfile": FORMAT_VALID if info.InvoiceProfile == "TICARIFATURA" else FORMAT_INVALID,
        "CurrencyCode": FORMAT_VALID if re.fullmatch(r"[A-Z]{3}", info.CurrencyCode) else FORMAT_INVALID,
        "IssueDate": FORMAT_VALID if info.IssueDate.tzinfo is not None and info.IssueDate.utcoffset() is not None else FORMAT_INVALID,
        "Supplier": FIELD_PRESENT if supplier_present else FIELD_MISSING,
        "Customer": FIELD_PRESENT if customer_present else FIELD_MISSING,
        "TaxTotal": FIELD_MISSING,
        "WithholdingTaxTotal": FIELD_MISSING,
        "LegalMonetaryTotal": FIELD_MISSING,
        "InvoiceLines": FIELD_PRESENT if lines else FIELD_MISSING,
        "LineExtensionAmount": FORMAT_VALID if info.LineExtensionAmount == line_extension_sum else TOTAL_MISMATCH,
        "AllowanceCharge": FIELD_PRESENT if lines else FIELD_MISSING,
        "InvoiceLines.KDVPercent": FORMAT_VALID if all(line.KDVPercent >= 0 for line in lines) else FORMAT_INVALID,
        "InvoiceLines.KDVTotal": FORMAT_VALID if line_kdv_matches else TOTAL_MISMATCH,
        "GeneralKDV1Total": FORMAT_VALID if info.GeneralKDV1Total == kdv_by_rate[Decimal("1")] else TOTAL_MISMATCH,
        "GeneralKDV8Total": FORMAT_VALID if info.GeneralKDV8Total == kdv_by_rate[Decimal("8")] else TOTAL_MISMATCH,
        "GeneralKDV10Total": FORMAT_VALID if info.GeneralKDV10Total == kdv_by_rate[Decimal("10")] else TOTAL_MISMATCH,
        "GeneralKDV18Total": FORMAT_VALID if info.GeneralKDV18Total == kdv_by_rate[Decimal("18")] else TOTAL_MISMATCH,
        "GeneralKDV20Total": FORMAT_VALID if info.GeneralKDV20Total == kdv_by_rate[Decimal("20")] else TOTAL_MISMATCH,
        "GeneralAllowanceTotal": FORMAT_VALID if info.GeneralAllowanceTotal == allowance_sum else TOTAL_MISMATCH,
        "KdvTotal": FORMAT_VALID if info.KdvTotal == kdv_sum else TOTAL_MISMATCH,
        "PayableAmount": FORMAT_VALID if info.PayableAmount == line_extension_sum + kdv_sum else TOTAL_MISMATCH,
        "SenderAlias": FIELD_MISSING,
        "ReceiverAlias": FIELD_PRESENT if bool(payload.CustomerAlias.strip()) else FIELD_MISSING,
        "InvoiceSerieOrNumber": FORMAT_VALID if identity_valid else FORMAT_INVALID,
    }


def ensure_fixture_payload_contract(payload: NilveraEInvoicePayload) -> None:
    classifications = classify_fixture_payload_contract(payload)
    required_present = ("InvoiceInfo", "Supplier", "Customer", "InvoiceLines", "ReceiverAlias")
    required_valid = (
        "InvoiceType",
        "InvoiceProfile",
        "CurrencyCode",
        "IssueDate",
        "LineExtensionAmount",
        "InvoiceLines.KDVPercent",
        "InvoiceLines.KDVTotal",
        "GeneralKDV1Total",
        "GeneralKDV8Total",
        "GeneralKDV10Total",
        "GeneralKDV18Total",
        "GeneralKDV20Total",
        "GeneralAllowanceTotal",
        "KdvTotal",
        "PayableAmount",
        "InvoiceSerieOrNumber",
    )
    if any(classifications[field] != FIELD_PRESENT for field in required_present):
        raise SandboxFixtureFailed("FIXTURE_PAYLOAD_CONTRACT_FAILED")
    if any(classifications[field] != FORMAT_VALID for field in required_valid):
        raise SandboxFixtureFailed("FIXTURE_PAYLOAD_CONTRACT_FAILED")


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
    ensure_fixture_payload_contract(payload)
    return payload


async def company_identity_matches(client: Any, expected_tax_number: str) -> bool:
    try:
        response = await client.get(NilveraEndpoints.GET_COMPANY)
    except Exception as exc:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        provider_code = exc.provider_code if isinstance(exc, NilveraApiError) else None
        raise SandboxFixtureBlocked(
            "BLOCKED_COMPANY_IDENTITY_QUERY",
            http_status=http_status,
            http_status_class=_http_status_class(http_status),
            provider_code=_safe_provider_code(provider_code),
            exception_type=_safe_exception_type(exc),
        ) from None
    if not isinstance(response, dict):
        http_status = _client_exact_http_status(client)
        raise SandboxFixtureBlocked(
            "BLOCKED_COMPANY_IDENTITY_PARSE",
            http_status=http_status,
            http_status_class=_http_status_class(http_status),
            exception_type="NilveraValidationError",
        )
    tax_number = response.get("TaxNumber")
    if not isinstance(tax_number, str) or not tax_number.isdigit() or len(tax_number) not in (10, 11):
        http_status = _client_exact_http_status(client)
        raise SandboxFixtureBlocked(
            "BLOCKED_COMPANY_IDENTITY_PARSE",
            http_status=http_status,
            http_status_class=_http_status_class(http_status),
            exception_type="NilveraValidationError",
        )
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


def _page_count_class(page_count: int) -> str:
    if page_count == 1:
        return PAGE_COUNT_ONE
    if 2 <= page_count <= 5:
        return PAGE_COUNT_TWO_TO_FIVE
    if 6 <= page_count <= 10:
        return PAGE_COUNT_SIX_TO_TEN
    if 11 <= page_count <= RECONCILIATION_MAX_PAGES:
        return PAGE_COUNT_ELEVEN_TO_LIMIT
    raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_PAGE_COUNT")


def _client_exact_http_status(client: Any) -> int | None:
    status = getattr(client, "exact_http_status", None)
    return status if isinstance(status, int) and 100 <= status <= 599 else None


def _combined_exact_http_status(*clients: Any) -> int | None:
    statuses = {_client_exact_http_status(client) for client in clients}
    statuses.discard(None)
    if len(statuses) != 1:
        return None
    return next(iter(statuses))


def _enrich_reconciliation_error(
    exc: SandboxFixtureError,
    *,
    sender_match: bool,
    receiver_match: bool,
    sender_page_count_class: str,
    receiver_page_count_class: str,
    http_status: int | None,
) -> SandboxFixtureError:
    exc.sender_match = sender_match
    exc.receiver_match = receiver_match
    exc.sender_page_count_class = sender_page_count_class
    exc.receiver_page_count_class = receiver_page_count_class
    if exc.http_status is None:
        exc.http_status = http_status
        exc.http_status_class = _http_status_class(http_status)
    return exc


def _page_error_metadata(
    *,
    side: str,
    page_count: int,
    sender_page_count_class: str | None,
) -> dict[str, str | None]:
    current_page_class = _page_count_class(page_count) if page_count else None
    return {
        "sender_page_count_class": current_page_class if side == "sender" else sender_page_count_class,
        "receiver_page_count_class": current_page_class if side == "receiver" else None,
    }


async def _scan_reconciliation_pages(
    *,
    client: Any,
    path: str,
    params: dict[str, str],
    correlation_label: str,
    side: str,
    sender_match: bool,
    receiver_match: bool,
    sender_page_count_class: str | None = None,
) -> _ReconciliationPages:
    items: list[dict[str, Any]] = []
    completed_pages = 0

    for page in range(1, RECONCILIATION_MAX_PAGES + 1):
        page_params = {**params, "Page": str(page), "PageSize": str(RECONCILIATION_PAGE_SIZE)}
        try:
            response = await client.get(
                path,
                params=page_params,
                correlation_id=correlation_label,
            )
        except Exception as exc:
            failure_stage = "SENDER_SALE_LIST" if side == "sender" else "RECEIVER_PURCHASE_LIST"
            blocked = _reconciliation_query_failure(
                exc,
                failure_stage=failure_stage,
                sender_match=sender_match,
                receiver_match=receiver_match,
            )
            metadata = _page_error_metadata(
                side=side,
                page_count=completed_pages,
                sender_page_count_class=sender_page_count_class,
            )
            blocked.sender_page_count_class = metadata["sender_page_count_class"]
            blocked.receiver_page_count_class = metadata["receiver_page_count_class"]
            raise blocked from None

        completed_pages += 1
        metadata = _page_error_metadata(
            side=side,
            page_count=completed_pages,
            sender_page_count_class=sender_page_count_class,
        )
        if not isinstance(response, dict) or not isinstance(response.get("Content"), list):
            raise SandboxFixtureBlocked(
                "BLOCKED_FIXTURE_RECONCILIATION_PARSE",
                failure_stage=f"{side.upper()}_LIST_PARSE",
                http_status=_client_exact_http_status(client),
                http_status_class=_http_status_class(_client_exact_http_status(client)),
                exception_type="NilveraValidationError",
                sender_match=sender_match,
                receiver_match=receiver_match,
                **metadata,
            )

        content = response["Content"]
        if any(not isinstance(item, dict) for item in content):
            raise SandboxFixtureBlocked(
                "BLOCKED_FIXTURE_RECONCILIATION_PARSE",
                failure_stage=f"{side.upper()}_LIST_PARSE",
                http_status=_client_exact_http_status(client),
                http_status_class=_http_status_class(_client_exact_http_status(client)),
                exception_type="NilveraValidationError",
                sender_match=sender_match,
                receiver_match=receiver_match,
                **metadata,
            )
        items.extend(content)

        raw_total_pages = response.get("TotalPages")
        if raw_total_pages is not None:
            if isinstance(raw_total_pages, bool) or not isinstance(raw_total_pages, int) or raw_total_pages < 0:
                raise SandboxFixtureBlocked(
                    "BLOCKED_FIXTURE_RECONCILIATION_PARSE",
                    failure_stage=f"{side.upper()}_PAGINATION_PARSE",
                    http_status=_client_exact_http_status(client),
                    http_status_class=_http_status_class(_client_exact_http_status(client)),
                    exception_type="NilveraValidationError",
                    sender_match=sender_match,
                    receiver_match=receiver_match,
                    **metadata,
                )
            if raw_total_pages > RECONCILIATION_MAX_PAGES:
                raise SandboxFixtureBlocked(
                    "BLOCKED_RECONCILIATION_PAGE_LIMIT",
                    failure_stage=f"{side.upper()}_PAGE_LIMIT",
                    http_status=_client_exact_http_status(client),
                    http_status_class=_http_status_class(_client_exact_http_status(client)),
                    sender_match=sender_match,
                    receiver_match=receiver_match,
                    **metadata,
                )
            if raw_total_pages == 0 and content:
                raise SandboxFixtureBlocked(
                    "BLOCKED_FIXTURE_RECONCILIATION_PARSE",
                    failure_stage=f"{side.upper()}_PAGINATION_PARSE",
                    http_status=_client_exact_http_status(client),
                    http_status_class=_http_status_class(_client_exact_http_status(client)),
                    exception_type="NilveraValidationError",
                    sender_match=sender_match,
                    receiver_match=receiver_match,
                    **metadata,
                )
            if page >= max(raw_total_pages, 1):
                return _ReconciliationPages(tuple(items), completed_pages, _page_count_class(completed_pages))
        elif len(content) < RECONCILIATION_PAGE_SIZE:
            return _ReconciliationPages(tuple(items), completed_pages, _page_count_class(completed_pages))

    raise SandboxFixtureBlocked(
        "BLOCKED_RECONCILIATION_PAGE_LIMIT",
        failure_stage=f"{side.upper()}_PAGE_LIMIT",
        http_status=_client_exact_http_status(client),
        http_status_class=_http_status_class(_client_exact_http_status(client)),
        sender_match=sender_match,
        receiver_match=receiver_match,
        **_page_error_metadata(
            side=side,
            page_count=completed_pages,
            sender_page_count_class=sender_page_count_class,
        ),
    )


def _normalized_item_field(item: dict[str, Any], fields: Sequence[str]) -> str:
    for field in fields:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return _normalize(value)
    return ""


def _parse_candidate_uuid(item: dict[str, Any]) -> str:
    raw_uuid = item.get("UUID") or item.get("Id")
    try:
        return str(uuid.UUID(str(raw_uuid)))
    except (AttributeError, TypeError, ValueError):
        raise SandboxFixtureBlocked("BLOCKED_FIXTURE_RECONCILIATION_PARSE") from None


def _matches_counterpart(
    item: dict[str, Any],
    fields: Sequence[str],
    expected_tax_number: str,
    hmac_key: str,
) -> bool:
    expected_digest = hmac.new(hmac_key.encode(), expected_tax_number.encode(), hashlib.sha256).digest()
    for field in fields:
        value = item.get(field)
        if isinstance(value, str) and value:
            return _matches_fixture(value, expected_digest, hmac_key)
    return False


def _reconciliation_candidates(
    items: Sequence[dict[str, Any]],
    *,
    target_digest: bytes,
    hmac_key: str,
    counterpart_tax_number: str,
    counterpart_fields: Sequence[str],
) -> _ReconciliationCandidates:
    tag_field_seen = False
    exact_matches: set[str] = set()
    for item in items:
        for field in _CORRELATION_FIELDS:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            tag_field_seen = True
            if _matches_fixture(value, target_digest, hmac_key):
                exact_matches.add(_parse_candidate_uuid(item))

    if exact_matches or tag_field_seen:
        return _ReconciliationCandidates(tuple(sorted(exact_matches)), False)

    narrowed: set[str] = set()
    for item in items:
        if _normalized_item_field(item, _PROFILE_FIELDS) != "ticarifatura":
            continue
        if _normalized_item_field(item, _TYPE_FIELDS) != "satis":
            continue
        if not _matches_counterpart(item, counterpart_fields, counterpart_tax_number, hmac_key):
            continue
        narrowed.add(_parse_candidate_uuid(item))

    if len(narrowed) > RECONCILIATION_MAX_DETAIL_CANDIDATES:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_CANDIDATE_LIMIT")
    return _ReconciliationCandidates(tuple(sorted(narrowed)), True)


def _detail_matches_fixture(detail: Any, *, target_digest: bytes, hmac_key: str) -> bool:
    if not isinstance(detail, dict):
        raise SandboxFixtureBlocked("BLOCKED_FIXTURE_RECONCILIATION_PARSE")
    invoice_number = detail.get("InvoiceNumber")
    invoice_profile = detail.get("InvoiceProfile")
    invoice_type = detail.get("InvoiceType")
    if not all(isinstance(value, str) and value.strip() for value in (invoice_number, invoice_profile, invoice_type)):
        raise SandboxFixtureBlocked("BLOCKED_FIXTURE_RECONCILIATION_PARSE")
    return (
        _matches_fixture(invoice_number, target_digest, hmac_key)
        and invoice_profile == "TICARIFATURA"
        and invoice_type == "SATIS"
    )


async def reconcile_incoming_commercial_fixture(
    *,
    sender_client: Any,
    receiver_client: Any,
    sender_key: str,
    receiver_key: str,
    hmac_key: str,
    run_id: str,
    seller_tax_number: str,
    buyer_tax_number: str,
    reference_time: datetime,
) -> SandboxFixtureReconciliationResult:
    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_REFERENCE_TIME")

    ensure_distinct_sandbox_keys(sender_key, receiver_key)
    sender_match = await company_identity_matches(sender_client, seller_tax_number)
    receiver_match = await company_identity_matches(receiver_client, buyer_tax_number)
    if not sender_match or not receiver_match:
        raise SandboxFixtureBlocked(
            "BLOCKED_SANDBOX_COMPANY_MISMATCH",
            sender_match=sender_match,
            receiver_match=receiver_match,
        )

    identity = build_fixture_identity(year=reference_time.year, run_id=run_id, hmac_key=hmac_key)
    correlation_label = fixture_correlation_label(identity, hmac_key)
    target_digest = hmac.new(hmac_key.encode(), identity.encode(), hashlib.sha256).digest()
    params = {
        "StartDate": (reference_time - timedelta(days=RECONCILIATION_WINDOW_DAYS)).isoformat(),
        "EndDate": (reference_time + timedelta(days=RECONCILIATION_WINDOW_DAYS)).isoformat(),
        "DateFilterType": "CreatedDate",
        "SortColumn": "CreatedDate",
        "SortType": "ASC",
    }

    outgoing_pages = await _scan_reconciliation_pages(
        client=sender_client,
        path=NilveraEndpoints.LIST_SALE_INVOICES,
        params=params,
        correlation_label=correlation_label,
        side="sender",
        sender_match=sender_match,
        receiver_match=receiver_match,
    )
    incoming_pages = await _scan_reconciliation_pages(
        client=receiver_client,
        path=NilveraEndpoints.LIST_PURCHASE_INVOICES,
        params=params,
        correlation_label=correlation_label,
        side="receiver",
        sender_match=sender_match,
        receiver_match=receiver_match,
        sender_page_count_class=outgoing_pages.page_count_class,
    )
    exact_http_status = _combined_exact_http_status(sender_client, receiver_client)

    try:
        outgoing_candidates = _reconciliation_candidates(
            outgoing_pages.items,
            target_digest=target_digest,
            hmac_key=hmac_key,
            counterpart_tax_number=buyer_tax_number,
            counterpart_fields=_OUTGOING_COUNTERPART_FIELDS,
        )
        incoming_candidates = _reconciliation_candidates(
            incoming_pages.items,
            target_digest=target_digest,
            hmac_key=hmac_key,
            counterpart_tax_number=seller_tax_number,
            counterpart_fields=_INCOMING_COUNTERPART_FIELDS,
        )
    except SandboxFixtureError as exc:
        raise _enrich_reconciliation_error(
            exc,
            sender_match=sender_match,
            receiver_match=receiver_match,
            sender_page_count_class=outgoing_pages.page_count_class,
            receiver_page_count_class=incoming_pages.page_count_class,
            http_status=exact_http_status,
        ) from None

    if (
        (not outgoing_candidates.used_detail_fallback and len(outgoing_candidates.provider_uuids) > 1)
        or (not incoming_candidates.used_detail_fallback and len(incoming_candidates.provider_uuids) > 1)
    ):
        raise SandboxFixtureBlocked(
            "CONFLICT_FIXTURE_RECONCILIATION",
            sender_match=sender_match,
            receiver_match=receiver_match,
            match_count_class=MATCH_COUNT_MULTIPLE,
            sender_page_count_class=outgoing_pages.page_count_class,
            receiver_page_count_class=incoming_pages.page_count_class,
            http_status=exact_http_status,
            http_status_class=_http_status_class(exact_http_status),
        )

    outgoing_matches: list[str] = []
    outgoing_details: dict[str, Any] = {}
    for provider_uuid in outgoing_candidates.provider_uuids:
        try:
            detail_response = await sender_client.get(
                NilveraEndpoints.GET_SALE_INVOICE_DETAIL.format(uuid=provider_uuid),
                correlation_id=correlation_label,
            )
            detail_matches = _detail_matches_fixture(
                detail_response,
                target_digest=target_digest,
                hmac_key=hmac_key,
            )
        except SandboxFixtureError as exc:
            raise _enrich_reconciliation_error(
                exc,
                sender_match=sender_match,
                receiver_match=receiver_match,
                sender_page_count_class=outgoing_pages.page_count_class,
                receiver_page_count_class=incoming_pages.page_count_class,
                http_status=_combined_exact_http_status(sender_client, receiver_client),
            ) from None
        except Exception as exc:
            blocked = _reconciliation_query_failure(
                exc,
                failure_stage="SENDER_SALE_DETAIL",
                sender_match=sender_match,
                receiver_match=receiver_match,
            )
            raise _enrich_reconciliation_error(
                blocked,
                sender_match=sender_match,
                receiver_match=receiver_match,
                sender_page_count_class=outgoing_pages.page_count_class,
                receiver_page_count_class=incoming_pages.page_count_class,
                http_status=_combined_exact_http_status(sender_client, receiver_client),
            ) from None
        if detail_matches:
            outgoing_matches.append(provider_uuid)
            outgoing_details[provider_uuid] = detail_response

    incoming_matches: list[str] = []
    incoming_details: dict[str, Any] = {}
    incoming_service = NilveraIncomingService(receiver_client)
    for provider_uuid in incoming_candidates.provider_uuids:
        try:
            detail = await incoming_service.fetch_incoming_invoice_detail(provider_uuid)
        except Exception as exc:
            blocked = _reconciliation_query_failure(
                exc,
                failure_stage="RECEIVER_PURCHASE_DETAIL",
                sender_match=sender_match,
                receiver_match=receiver_match,
            )
            raise _enrich_reconciliation_error(
                blocked,
                sender_match=sender_match,
                receiver_match=receiver_match,
                sender_page_count_class=outgoing_pages.page_count_class,
                receiver_page_count_class=incoming_pages.page_count_class,
                http_status=_combined_exact_http_status(sender_client, receiver_client),
            ) from None
        if (
            _matches_fixture(detail.invoice_number, target_digest, hmac_key)
            and detail.invoice_profile == "TICARIFATURA"
            and detail.invoice_type == "SATIS"
        ):
            incoming_matches.append(provider_uuid)
            incoming_details[provider_uuid] = detail

    if outgoing_candidates.provider_uuids and not outgoing_candidates.used_detail_fallback and not outgoing_matches:
        raise SandboxFixtureFailed(
            "FIXTURE_OUTGOING_RECONCILIATION_MISMATCH",
            http_status=_combined_exact_http_status(sender_client, receiver_client),
            http_status_class=_http_status_class(_combined_exact_http_status(sender_client, receiver_client)),
            sender_match=sender_match,
            receiver_match=receiver_match,
            sender_page_count_class=outgoing_pages.page_count_class,
            receiver_page_count_class=incoming_pages.page_count_class,
        )
    if incoming_candidates.provider_uuids and not incoming_candidates.used_detail_fallback and not incoming_matches:
        raise SandboxFixtureFailed(
            "FIXTURE_RECEIVER_RECONCILIATION_MISMATCH",
            http_status=_combined_exact_http_status(sender_client, receiver_client),
            http_status_class=_http_status_class(_combined_exact_http_status(sender_client, receiver_client)),
            sender_match=sender_match,
            receiver_match=receiver_match,
            sender_page_count_class=outgoing_pages.page_count_class,
            receiver_page_count_class=incoming_pages.page_count_class,
        )
    if len(outgoing_matches) > 1 or len(incoming_matches) > 1:
        raise SandboxFixtureBlocked(
            "CONFLICT_FIXTURE_RECONCILIATION",
            sender_match=sender_match,
            receiver_match=receiver_match,
            match_count_class=MATCH_COUNT_MULTIPLE,
            sender_page_count_class=outgoing_pages.page_count_class,
            receiver_page_count_class=incoming_pages.page_count_class,
            http_status=_combined_exact_http_status(sender_client, receiver_client),
            http_status_class=_http_status_class(_combined_exact_http_status(sender_client, receiver_client)),
        )
    match_count_class = MATCH_COUNT_ONE if outgoing_matches else MATCH_COUNT_ZERO

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
        except Exception as exc:
            blocked = _reconciliation_query_failure(
                exc,
                failure_stage="SENDER_SALE_STATUS",
                sender_match=sender_match,
                receiver_match=receiver_match,
            )
            raise _enrich_reconciliation_error(
                blocked,
                sender_match=sender_match,
                receiver_match=receiver_match,
                sender_page_count_class=outgoing_pages.page_count_class,
                receiver_page_count_class=incoming_pages.page_count_class,
                http_status=_combined_exact_http_status(sender_client, receiver_client),
            ) from None
        try:
            outgoing_outcome = parse_sale_outcome(status_response)
        except SandboxFixtureError:
            exact_status = _combined_exact_http_status(sender_client, receiver_client)
            raise SandboxFixtureBlocked(
                "BLOCKED_FIXTURE_RECONCILIATION_PARSE",
                failure_stage="SENDER_SALE_STATUS_PARSE",
                http_status=exact_status,
                http_status_class=_http_status_class(exact_status),
                exception_type="NilveraValidationError",
                sender_match=sender_match,
                receiver_match=receiver_match,
                sender_page_count_class=outgoing_pages.page_count_class,
                receiver_page_count_class=incoming_pages.page_count_class,
            ) from None
        outgoing_detail_match = _detail_matches_fixture(
            outgoing_details[provider_uuid],
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
        try:
            status = await incoming_service.fetch_incoming_invoice_status(provider_uuid)
        except Exception as exc:
            blocked = _reconciliation_query_failure(
                exc,
                failure_stage="RECEIVER_PURCHASE_STATUS",
                sender_match=sender_match,
                receiver_match=receiver_match,
            )
            raise _enrich_reconciliation_error(
                blocked,
                sender_match=sender_match,
                receiver_match=receiver_match,
                sender_page_count_class=outgoing_pages.page_count_class,
                receiver_page_count_class=incoming_pages.page_count_class,
                http_status=_combined_exact_http_status(sender_client, receiver_client),
            ) from None
        detail = incoming_details[provider_uuid]
        receiver_detail_match = (
            _matches_fixture(detail.invoice_number, target_digest, hmac_key)
            and detail.invoice_profile == "TICARIFATURA"
            and detail.invoice_type == "SATIS"
        )
        receiver_status_ready = _normalize(status.status_code) in {"succeed", "success"}
        if not receiver_detail_match:
            raise SandboxFixtureFailed("FIXTURE_RECEIVER_RECONCILIATION_MISMATCH")
        receiver_visibility = FOUND

    return SandboxFixtureReconciliationResult(
        correlation_label=correlation_label,
        provider_write_count=0,
        sender_match=sender_match,
        receiver_match=receiver_match,
        match_count_class=match_count_class,
        outgoing_result=outgoing_result,
        outgoing_outcome=outgoing_outcome,
        outgoing_detail_match=outgoing_detail_match,
        receiver_visibility=receiver_visibility,
        receiver_detail_match=receiver_detail_match,
        receiver_status_ready=receiver_status_ready,
        sender_page_count_class=outgoing_pages.page_count_class,
        receiver_page_count_class=incoming_pages.page_count_class,
        http_status=_combined_exact_http_status(sender_client, receiver_client),
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
