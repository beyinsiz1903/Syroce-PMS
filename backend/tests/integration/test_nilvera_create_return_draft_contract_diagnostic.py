"""GET-only Nilvera CreateReturn draft-contract metadata diagnostics."""

import hashlib
import hmac
import os
import re
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
_SAFE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_MAX_DEPTH = 6
_MAX_PATHS = 200


def _safe_type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "str"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "other"


def _metadata_signature(payload: object) -> set[str]:
    """Return schema-like key paths and value types, never provider values."""
    paths: set[str] = set()

    def walk(value: object, prefix: tuple[str, ...], depth: int) -> None:
        if depth > _MAX_DEPTH or len(paths) >= _MAX_PATHS:
            return
        if isinstance(value, dict):
            for raw_key, child in value.items():
                if not isinstance(raw_key, str) or not _SAFE_KEY.fullmatch(raw_key):
                    continue
                key = raw_key.casefold()
                path = prefix + (key,)
                paths.add(f"{'.'.join(path)}:{_safe_type_name(child)}")
                walk(child, path, depth + 1)
        elif isinstance(value, list):
            marker = prefix + ("[]",)
            paths.add(f"{'.'.join(marker)}:array_item")
            if value:
                walk(value[0], marker, depth + 1)

    walk(payload, tuple(), 0)
    return paths


@pytest.mark.external
async def test_sandbox_diagnose_create_return_draft_contract_metadata(record_property):
    """Compare two matching return drafts through /Draft/{UUID}/model using GET only."""
    allowed = os.environ.get("NILVERA_E2E_CREATE_RETURN_RECONCILIATION_ALLOWED", "false")
    if allowed.lower() != "true":
        pytest.skip("CreateReturn draft-contract diagnostic requires read-only reconciliation mode")

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
        pytest.fail("BLOCKED_INVALID_CREATE_RETURN_DRAFT_CONTRACT_SOURCE", pytrace=False)

    receiver_client = new_sandbox_client(receiver_key)
    try:
        async with receiver_client as receiver:
            if not await company_identity_matches(receiver, buyer_tax_number):
                pytest.fail("BLOCKED_CREATE_RETURN_RECEIVER_IDENTITY_MISMATCH", pytrace=False)

            source_detail = await receiver.get(
                NilveraEndpoints.GET_PURCHASE_INVOICE_DETAIL.format(uuid=source_provider_uuid),
                correlation_id=correlation_label,
                retryable=False,
                stage="CREATE_RETURN_DRAFT_CONTRACT_SOURCE_DETAIL",
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
                    stage="CREATE_RETURN_DRAFT_CONTRACT_LIST",
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
                        stage="CREATE_RETURN_DRAFT_CONTRACT_MODEL",
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
                    f"BLOCKED_CREATE_RETURN_DRAFT_CONTRACT_EXPECTED_TWO_MATCHES "
                    f"(raw_match_count={raw_match_count}, write_count=0)",
                    pytrace=False,
                )

            signatures = [_metadata_signature(detail) for detail in matches]
            only_left = signatures[0] - signatures[1]
            only_right = signatures[1] - signatures[0]
            differences = sorted(only_left | only_right)
            metadata_equal = not differences
            safe_difference_fields = ",".join(differences[:25]) if differences else "NONE"

            record_property("metadata_signature_equal", str(metadata_equal).lower())
            record_property("metadata_difference_count", str(len(differences)))
            record_property("metadata_difference_fields", safe_difference_fields)
            record_property("provider_write_count", "0")

            diagnostic = (
                f"raw_match_count=2, draft_model_contract_count=2, "
                f"metadata_signature_equal={str(metadata_equal).lower()}, "
                f"metadata_difference_count={len(differences)}, "
                f"metadata_difference_fields={safe_difference_fields}, write_count=0"
            )
            print(f"CREATE_RETURN_DRAFT_CONTRACT_DIAGNOSTIC {diagnostic}")

            if metadata_equal:
                pytest.fail(f"CONFLICT_CREATE_RETURN_DRAFT_METADATA_IDENTICAL ({diagnostic})", pytrace=False)
            pytest.fail(f"BLOCKED_CREATE_RETURN_DRAFT_METADATA_DIFFERENCES_FOUND ({diagnostic})", pytrace=False)

    except Exception as exc:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        pytest.fail(
            f"CreateReturn GET-only draft-contract diagnostic failed "
            f"(error_type={type(exc).__name__}, http_status={http_status}, write_count=0)",
            pytrace=False,
        )
