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

_CREATION_KEYS = {
    "createdat",
    "createddate",
    "creationdate",
    "creationdatetime",
    "createdatetime",
    "createdon",
}


def _parse_provider_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _extract_creation_time(payload: object) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key, value in payload.items():
        normalized = "".join(ch for ch in str(key).casefold() if ch.isalnum())
        if normalized in _CREATION_KEYS:
            parsed = _parse_provider_datetime(value)
            if parsed is not None:
                return parsed
    for value in payload.values():
        if isinstance(value, dict):
            parsed = _extract_creation_time(value)
            if parsed is not None:
                return parsed
    return None


def _select_exact_write_window_match(
    matches: list[tuple[str, dict, dict]],
    *,
    write_time: datetime,
    tolerance: timedelta = timedelta(minutes=10),
) -> tuple[str, dict] | None:
    timestamped: list[tuple[str, dict, datetime]] = []
    for candidate_uuid, detail, list_item in matches:
        created_at = _extract_creation_time(list_item) or _extract_creation_time(detail)
        if created_at is None:
            continue
        if abs(created_at - write_time) <= tolerance:
            timestamped.append((candidate_uuid, detail, created_at))

    if len(timestamped) != 1:
        return None
    candidate_uuid, detail, _created_at = timestamped[0]
    return candidate_uuid, detail


@pytest.mark.external
async def test_sandbox_reconcile_created_return_exact_write_window(record_property):
    """GET-only reconciliation that isolates the CreateReturn from the approved write window."""
    allowed = os.environ.get("NILVERA_E2E_CREATE_RETURN_RECONCILIATION_ALLOWED", "false")
    if allowed.lower() != "true":
        pytest.skip("CreateReturn reconciliation requires explicit read-only mode")

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
        pytest.fail("BLOCKED_INVALID_CREATE_RETURN_RECONCILIATION_SOURCE", pytrace=False)

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
                stage="CREATE_RETURN_SOURCE_DETAIL_RECONCILIATION",
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
                    stage="CREATE_RETURN_DRAFT_LIST_RECONCILIATION",
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

            matches: list[tuple[str, dict, dict]] = []
            source_reference_match = False
            for candidate_uuid, list_item in candidates.items():
                try:
                    detail = await receiver.get(
                        NilveraEndpoints.GET_DRAFT_INVOICE_MODEL.format(uuid=candidate_uuid),
                        correlation_id=correlation_label,
                        retryable=False,
                        stage="CREATE_RETURN_DRAFT_MODEL_RECONCILIATION",
                    )
                except NilveraNotFoundError:
                    continue
                if not isinstance(detail, dict):
                    pytest.fail("BLOCKED_CREATE_RETURN_DETAIL_PARSE", pytrace=False)
                if not _created_return_detail_matches(
                    detail,
                    original_buyer_tax_number=buyer_tax_number,
                    original_seller_tax_number=seller_tax_number,
                    source_provider_uuid=source_provider_uuid,
                    hmac_key=hmac_key,
                ):
                    continue
                source_reference_match = source_reference_match or _payload_contains_reference(
                    detail,
                    source_provider_uuid,
                    hmac_key,
                )
                matches.append((candidate_uuid, detail, list_item))

            record_property("raw_match_count", str(len(matches)))
            record_property("source_reference_match", str(source_reference_match).lower())
            if not matches:
                pytest.fail("BLOCKED_CREATE_RETURN_NOT_FOUND", pytrace=False)

            selected = _select_exact_write_window_match(matches, write_time=write_time)
            if selected is None:
                timestamped_match_count = sum(
                    1
                    for _candidate_uuid, detail, list_item in matches
                    if (_extract_creation_time(list_item) or _extract_creation_time(detail)) is not None
                )
                record_property("timestamped_match_count", str(timestamped_match_count))
                pytest.fail("CONFLICT_CREATE_RETURN_WRITE_WINDOW_NOT_UNIQUE", pytrace=False)

            created_uuid, created_detail = selected
            record_property("match_count_class", "ONE")
            record_property("created_document_found", "true")
            record_property("provider_status_class", "DRAFT_CREATED")
            record_property("selected_uuid_present", str(bool(created_uuid)).lower())
            record_property("exact_http_status", str(receiver.last_http_status or "NOT_RECORDED"))
    except Exception as exc:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        pytest.fail(
            f"CreateReturn GET-only exact-window reconciliation failed (error_type={type(exc).__name__}, http_status={http_status}, write_count=0)",
            pytrace=False,
        )
