"""GET-only source-link diagnostics for ambiguous Nilvera CreateReturn reconciliation."""

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
async def test_sandbox_diagnose_created_return_source_links(record_property):
    """Count source-linked matching return drafts using non-retrying GET requests only."""
    allowed = os.environ.get("NILVERA_E2E_CREATE_RETURN_RECONCILIATION_ALLOWED", "false")
    if allowed.lower() != "true":
        pytest.skip("CreateReturn source-link diagnostics require explicit read-only reconciliation mode")

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
        pytest.fail("BLOCKED_INVALID_CREATE_RETURN_SOURCE_LINK_SOURCE", pytrace=False)

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
                stage="CREATE_RETURN_SOURCE_LINK_SOURCE_DETAIL",
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
                    stage="CREATE_RETURN_SOURCE_LINK_DRAFT_LIST",
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

            matches: list[str] = []
            for candidate_uuid in candidates:
                try:
                    detail = await receiver.get(
                        NilveraEndpoints.GET_DRAFT_INVOICE_MODEL.format(uuid=candidate_uuid),
                        correlation_id=correlation_label,
                        retryable=False,
                        stage="CREATE_RETURN_SOURCE_LINK_DRAFT_MODEL",
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
                    matches.append(candidate_uuid)

            match_set = set(matches)
            linked_match_count = len(match_set & linked_candidates)
            unlinked_match_count = len(match_set - linked_candidates)
            linked_candidate_count = len(linked_candidates)

            record_property("raw_match_count", str(len(matches)))
            record_property("linked_candidate_count", str(linked_candidate_count))
            record_property("linked_match_count", str(linked_match_count))
            record_property("unlinked_match_count", str(unlinked_match_count))
            record_property("provider_write_count", "0")

            diagnostic = (
                f"raw_match_count={len(matches)}, "
                f"linked_candidate_count={linked_candidate_count}, "
                f"linked_match_count={linked_match_count}, "
                f"unlinked_match_count={unlinked_match_count}, write_count=0"
            )
            print(f"CREATE_RETURN_SOURCE_LINK_DIAGNOSTIC {diagnostic}")

            if not matches:
                pytest.fail(f"BLOCKED_CREATE_RETURN_NOT_FOUND ({diagnostic})", pytrace=False)
            if linked_match_count != 1:
                pytest.fail(
                    f"CONFLICT_CREATE_RETURN_SOURCE_LINK_NOT_UNIQUE ({diagnostic})",
                    pytrace=False,
                )

    except Exception as exc:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        pytest.fail(
            f"CreateReturn GET-only source-link diagnostic failed "
            f"(error_type={type(exc).__name__}, http_status={http_status}, write_count=0)",
            pytrace=False,
        )
