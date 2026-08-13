"""GET-only structural fingerprint diagnostics for ambiguous Nilvera CreateReturn drafts."""

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta

import pytest

from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraApiError, NilveraNotFoundError
from tests.integration.test_nilvera_sandbox_e2e import (
    _collect_uuid_values,
    _created_return_detail_matches,
    _payload_contains_reference,
    new_sandbox_client,
)
from tests.nilvera_sandbox_fixture import (
    SandboxFixtureError,
    build_fixture_identity,
    build_fixture_request_uuid,
    company_identity_matches,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.nilvera_sandbox]


def _nested_value(payload: object, *paths: tuple[str, ...]) -> object | None:
    for path in paths:
        value = payload
        for part in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if value is not None:
            return value
    return None


def _list_length(payload: object, *paths: tuple[str, ...]) -> int | None:
    value = _nested_value(payload, *paths)
    return len(value) if isinstance(value, list) else None


def _return_fingerprint(detail: dict, *, source_provider_uuid: str, hmac_key: str) -> dict[str, object]:
    """Build a non-sensitive structural fingerprint; never return raw provider values."""
    invoice_number = _nested_value(
        detail,
        ("InvoiceNumber",),
        ("InvoiceInfo", "InvoiceNumber"),
        ("EInvoice", "InvoiceInfo", "InvoiceNumber"),
    )
    issue_date = _nested_value(
        detail,
        ("IssueDate",),
        ("InvoiceInfo", "IssueDate"),
        ("EInvoice", "InvoiceInfo", "IssueDate"),
    )
    currency = _nested_value(
        detail,
        ("Currency",),
        ("DocumentCurrencyCode",),
        ("InvoiceInfo", "Currency"),
        ("EInvoice", "InvoiceInfo", "Currency"),
    )
    payable_total = _nested_value(
        detail,
        ("PayableAmount",),
        ("PayableTotal",),
        ("LegalMonetaryTotal", "PayableAmount"),
        ("EInvoice", "LegalMonetaryTotal", "PayableAmount"),
    )
    line_count = _list_length(
        detail,
        ("InvoiceLines",),
        ("Lines",),
        ("InvoiceInfo", "InvoiceLines"),
        ("EInvoice", "InvoiceLines"),
    )
    return {
        "invoice_number_present": isinstance(invoice_number, str) and bool(invoice_number.strip()),
        "issue_date_present": issue_date is not None,
        "currency_present": currency is not None,
        "payable_total_present": payable_total is not None,
        "line_count": line_count,
        "source_reference_present": _payload_contains_reference(detail, source_provider_uuid, hmac_key),
    }


def _fingerprint_difference_labels(left: dict[str, object], right: dict[str, object]) -> list[str]:
    return sorted(key for key in left if left.get(key) != right.get(key))


@pytest.mark.external
async def test_sandbox_diagnose_created_return_fingerprints(record_property):
    """Compare safe structural fingerprints for matching return drafts using GET requests only."""
    allowed = os.environ.get("NILVERA_E2E_CREATE_RETURN_RECONCILIATION_ALLOWED", "false")
    if allowed.lower() != "true":
        pytest.skip("CreateReturn fingerprint diagnostics require explicit read-only reconciliation mode")

    receiver_key = os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY", "")
    hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY", "")
    source_run_id = os.environ.get("NILVERA_E2E_SOURCE_RUN_ID", "")
    source_timestamp = os.environ.get("NILVERA_E2E_SOURCE_RUN_TIMESTAMP", "")
    write_timestamp = os.environ.get("NILVERA_E2E_CREATE_RETURN_WRITE_TIMESTAMP", "")
    seller_tax_number = os.environ.get("NILVERA_E2E_SELLER_VKN", "")
    buyer_tax_number = os.environ.get("NILVERA_E2E_BUYER_VKN", "")
    record_property("provider_write_count", "0")

    try:
        fixture_reference_time = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
        write_time = datetime.fromisoformat(write_timestamp.replace("Z", "+00:00"))
        if any(value.tzinfo is None or value.utcoffset() is None for value in (fixture_reference_time, write_time)):
            raise ValueError
        identity = build_fixture_identity(
            year=fixture_reference_time.year,
            run_id=source_run_id,
            hmac_key=hmac_key,
        )
        source_provider_uuid = str(build_fixture_request_uuid(identity, hmac_key))
        correlation_label = hmac.new(
            hmac_key.encode(),
            f"create-return:{source_run_id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
    except (SandboxFixtureError, ValueError):
        pytest.fail("BLOCKED_INVALID_CREATE_RETURN_FINGERPRINT_SOURCE", pytrace=False)

    receiver_client = new_sandbox_client(receiver_key)
    try:
        async with receiver_client as receiver:
            receiver_match = await company_identity_matches(receiver, buyer_tax_number)
            record_property("receiver_match", str(receiver_match).lower())
            if not receiver_match:
                pytest.fail("BLOCKED_CREATE_RETURN_RECEIVER_IDENTITY_MISMATCH", pytrace=False)

            source_detail = await receiver.get(
                NilveraEndpoints.GET_PURCHASE_INVOICE_DETAIL.format(uuid=source_provider_uuid),
                correlation_id=correlation_label,
                retryable=False,
                stage="CREATE_RETURN_FINGERPRINT_SOURCE_DETAIL",
            )
            if not isinstance(source_detail, dict):
                pytest.fail("BLOCKED_CREATE_RETURN_SOURCE_DETAIL_PARSE", pytrace=False)

            linked_candidates = _collect_uuid_values(source_detail) - {source_provider_uuid}
            candidates: dict[str, dict] = {candidate_uuid: {} for candidate_uuid in linked_candidates}
            params = {
                "StartDate": (write_time - timedelta(days=1)).isoformat(),
                "EndDate": (write_time + timedelta(days=1)).isoformat(),
                "PageSize": 100,
            }
            for page_number in range(1, 6):
                response = await receiver.get(
                    NilveraEndpoints.LIST_DRAFT_INVOICES,
                    params={**params, "Page": page_number},
                    correlation_id=correlation_label,
                    retryable=False,
                    stage="CREATE_RETURN_FINGERPRINT_DRAFT_LIST",
                )
                content = response.get("Content") if isinstance(response, dict) else None
                if not isinstance(content, list):
                    pytest.fail("BLOCKED_CREATE_RETURN_LIST_PARSE", pytrace=False)
                for item in content:
                    if not isinstance(item, dict):
                        pytest.fail("BLOCKED_CREATE_RETURN_LIST_PARSE", pytrace=False)
                    raw_uuid = item.get("UUID") or item.get("Id")
                    try:
                        candidate_uuid = str(uuid.UUID(str(raw_uuid)))
                    except (AttributeError, TypeError, ValueError):
                        pytest.fail("BLOCKED_CREATE_RETURN_LIST_PARSE", pytrace=False)
                    candidates[candidate_uuid] = item
                total_pages = response.get("TotalPages")
                if isinstance(total_pages, int) and page_number >= max(total_pages, 1):
                    break
                if len(content) < 100:
                    break

            if len(candidates) > 100:
                pytest.fail("BLOCKED_CREATE_RETURN_CANDIDATE_LIMIT", pytrace=False)

            matches: list[dict] = []
            for candidate_uuid in candidates:
                try:
                    detail = await receiver.get(
                        NilveraEndpoints.GET_DRAFT_INVOICE_MODEL.format(uuid=candidate_uuid),
                        correlation_id=correlation_label,
                        retryable=False,
                        stage="CREATE_RETURN_FINGERPRINT_DRAFT_MODEL",
                    )
                except NilveraNotFoundError:
                    continue
                if not isinstance(detail, dict):
                    pytest.fail("BLOCKED_CREATE_RETURN_DETAIL_PARSE", pytrace=False)
                if _created_return_detail_matches(
                    detail,
                    original_buyer_tax_number=buyer_tax_number,
                    original_seller_tax_number=seller_tax_number,
                    source_provider_uuid=source_provider_uuid,
                    hmac_key=hmac_key,
                ):
                    matches.append(detail)

            record_property("raw_match_count", str(len(matches)))
            record_property("provider_write_count", "0")
            if len(matches) != 2:
                pytest.fail(
                    f"BLOCKED_CREATE_RETURN_FINGERPRINT_EXPECTED_TWO_MATCHES "
                    f"(raw_match_count={len(matches)}, write_count=0)",
                    pytrace=False,
                )

            fingerprints = [
                _return_fingerprint(detail, source_provider_uuid=source_provider_uuid, hmac_key=hmac_key)
                for detail in matches
            ]
            differences = _fingerprint_difference_labels(fingerprints[0], fingerprints[1])
            same_fingerprint = not differences
            difference_labels = ",".join(differences) if differences else "NONE"

            record_property("fingerprint_equal", str(same_fingerprint).lower())
            record_property("fingerprint_difference_count", str(len(differences)))
            record_property("fingerprint_difference_fields", difference_labels)
            record_property("provider_write_count", "0")

            diagnostic = (
                f"raw_match_count=2, fingerprint_equal={str(same_fingerprint).lower()}, "
                f"fingerprint_difference_count={len(differences)}, "
                f"fingerprint_difference_fields={difference_labels}, write_count=0"
            )
            print(f"CREATE_RETURN_FINGERPRINT_DIAGNOSTIC {diagnostic}")

            if same_fingerprint:
                pytest.fail(
                    f"CONFLICT_CREATE_RETURN_FINGERPRINT_IDENTICAL ({diagnostic})",
                    pytrace=False,
                )

            pytest.fail(
                f"BLOCKED_CREATE_RETURN_FINGERPRINT_DIFFERENCES_FOUND ({diagnostic})",
                pytrace=False,
            )

    except Exception as exc:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        pytest.fail(
            f"CreateReturn GET-only fingerprint diagnostic failed "
            f"(error_type={type(exc).__name__}, http_status={http_status}, write_count=0)",
            pytrace=False,
        )
