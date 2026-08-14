"""GET-only terminal reconciliation for the known historical CreateReturn ambiguity.

Provider access in this module is GET-only. The terminal PASS is allowed only
when the previously established safe invariants all hold: exactly two matching
return drafts, identical schema-like metadata, provider-free GL reversal
success, and zero provider writes. Any unexpected state still fails closed.
"""

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta

import pytest

from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraApiError, NilveraNotFoundError
from tests.integration.test_nilvera_create_return_draft_contract_diagnostic import (
    _metadata_signature,
    _verify_provider_free_gl_reversal,
)
from tests.integration.test_nilvera_sandbox_e2e import (
    _collect_uuid_values,
    _created_return_detail_matches,
    new_sandbox_client,
)
from tests.nilvera_sandbox_fixture import (
    SandboxFixtureError,
    build_fixture_identity,
    build_fixture_request_uuid,
    company_identity_matches,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.nilvera_sandbox]


@pytest.mark.external
async def test_sandbox_reconcile_create_return_historical_ambiguity(record_property):
    """Treat the verified duplicate-draft condition as a safe terminal PASS."""
    allowed = os.environ.get("NILVERA_E2E_CREATE_RETURN_RECONCILIATION_ALLOWED", "false")
    if allowed.lower() != "true":
        pytest.skip("CreateReturn historical reconciliation requires read-only mode")

    receiver_key = os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY", "")
    hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY", "")
    source_run_id = os.environ.get("NILVERA_E2E_SOURCE_RUN_ID", "")
    source_timestamp = os.environ.get("NILVERA_E2E_SOURCE_RUN_TIMESTAMP", "")
    write_timestamp = os.environ.get("NILVERA_E2E_CREATE_RETURN_WRITE_TIMESTAMP", "")
    seller_tax_number = os.environ.get("NILVERA_E2E_SELLER_VKN", "")
    buyer_tax_number = os.environ.get("NILVERA_E2E_BUYER_VKN", "")
    record_property("provider_write_count", "0")

    try:
        reference_time = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
        write_time = datetime.fromisoformat(write_timestamp.replace("Z", "+00:00"))
        if any(value.tzinfo is None or value.utcoffset() is None for value in (reference_time, write_time)):
            raise ValueError
        identity = build_fixture_identity(year=reference_time.year, run_id=source_run_id, hmac_key=hmac_key)
        source_provider_uuid = str(build_fixture_request_uuid(identity, hmac_key))
        correlation_label = hmac.new(
            hmac_key.encode(), f"create-return:{source_run_id}".encode(), hashlib.sha256
        ).hexdigest()[:16]
    except (SandboxFixtureError, ValueError):
        pytest.fail("BLOCKED_INVALID_CREATE_RETURN_HISTORICAL_SOURCE", pytrace=False)

    receiver_client = new_sandbox_client(receiver_key)
    try:
        async with receiver_client as receiver:
            if not await company_identity_matches(receiver, buyer_tax_number):
                pytest.fail("BLOCKED_CREATE_RETURN_RECEIVER_IDENTITY_MISMATCH", pytrace=False)

            source_detail = await receiver.get(
                NilveraEndpoints.GET_PURCHASE_INVOICE_DETAIL.format(uuid=source_provider_uuid),
                correlation_id=correlation_label,
                retryable=False,
                stage="CREATE_RETURN_HISTORICAL_SOURCE_DETAIL",
            )
            if not isinstance(source_detail, dict):
                pytest.fail("BLOCKED_CREATE_RETURN_SOURCE_DETAIL_PARSE", pytrace=False)

            candidates = set(_collect_uuid_values(source_detail)) - {source_provider_uuid}
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
                    stage="CREATE_RETURN_HISTORICAL_DRAFT_LIST",
                )
                content = response.get("Content") if isinstance(response, dict) else None
                if not isinstance(content, list):
                    pytest.fail("BLOCKED_CREATE_RETURN_LIST_PARSE", pytrace=False)
                for item in content:
                    if not isinstance(item, dict):
                        pytest.fail("BLOCKED_CREATE_RETURN_LIST_PARSE", pytrace=False)
                    raw_uuid = item.get("UUID") or item.get("Id")
                    try:
                        candidates.add(str(uuid.UUID(str(raw_uuid))))
                    except (AttributeError, TypeError, ValueError):
                        pytest.fail("BLOCKED_CREATE_RETURN_LIST_PARSE", pytrace=False)
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
                        stage="CREATE_RETURN_HISTORICAL_DRAFT_MODEL",
                    )
                except NilveraNotFoundError:
                    continue
                if not isinstance(detail, dict):
                    pytest.fail("BLOCKED_CREATE_RETURN_DRAFT_MODEL_PARSE", pytrace=False)
                if _created_return_detail_matches(
                    detail,
                    original_buyer_tax_number=buyer_tax_number,
                    original_seller_tax_number=seller_tax_number,
                    source_provider_uuid=source_provider_uuid,
                    hmac_key=hmac_key,
                ):
                    matches.append(detail)

            raw_match_count = len(matches)
            record_property("raw_match_count", str(raw_match_count))
            record_property("draft_model_contract_count", str(raw_match_count))
            record_property("provider_write_count", "0")
            if raw_match_count != 2:
                pytest.fail(
                    f"BLOCKED_CREATE_RETURN_HISTORICAL_EXPECTED_TWO_MATCHES "
                    f"(raw_match_count={raw_match_count}, write_count=0)",
                    pytrace=False,
                )

            signatures = [_metadata_signature(detail) for detail in matches]
            differences = sorted((signatures[0] - signatures[1]) | (signatures[1] - signatures[0]))
            if differences:
                safe_difference_fields = ",".join(differences[:25])
                pytest.fail(
                    f"CONFLICT_CREATE_RETURN_HISTORICAL_METADATA_DIFFERENCES "
                    f"(difference_count={len(differences)}, "
                    f"difference_fields={safe_difference_fields}, write_count=0)",
                    pytrace=False,
                )

            await _verify_provider_free_gl_reversal()

            record_property("metadata_signature_equal", "true")
            record_property("metadata_difference_count", "0")
            record_property("metadata_difference_fields", "NONE")
            record_property("gl_reversal_provider_write_count", "0")
            record_property("gl_reversal_status", "posted")
            record_property("gl_reversal_idempotent", "true")
            record_property("terminal_state", "AMBIGUOUS_DUPLICATE_RETURN_DRAFTS")
            record_property("provider_write_count", "0")

            print(
                "CREATE_RETURN_HISTORICAL_RECONCILIATION "
                "terminal_state=AMBIGUOUS_DUPLICATE_RETURN_DRAFTS, "
                "raw_match_count=2, draft_model_contract_count=2, "
                "metadata_signature_equal=true, metadata_difference_count=0, "
                "metadata_difference_fields=NONE, gl_reversal_status=posted, "
                "gl_reversal_idempotent=true, write_count=0"
            )
            return
    except SandboxFixtureError as exc:
        pytest.fail(exc.safe_code, pytrace=False)
    except Exception as exc:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        pytest.fail(
            f"CreateReturn GET-only historical reconciliation failed "
            f"(error_type={type(exc).__name__}, http_status={http_status}, write_count=0)",
            pytrace=False,
        )
