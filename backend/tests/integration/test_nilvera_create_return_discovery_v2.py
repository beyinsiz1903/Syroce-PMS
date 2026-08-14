"""Corrected Nilvera CreateReturn Sandbox discovery contract.

This test is provider-mutating and MUST only run under the existing explicit
Sandbox write gates. It performs exactly one CreateReturn POST, persists no
provider values to logs, and verifies the returned UUID only through the
official draft model endpoint.
"""

import os
from datetime import datetime
from unittest.mock import patch

import pytest

from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.return_adapter import NilveraReturnAdapter
from tests.integration.test_nilvera_sandbox_e2e import new_sandbox_client
from tests.nilvera_sandbox_fixture import (
    FOUND,
    ReadOnlySandboxClient,
    SandboxFixtureError,
    build_fixture_identity,
    build_fixture_request_uuid,
    pilot_invoice_datetime,
    reconcile_incoming_commercial_fixture,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.nilvera_sandbox]


@pytest.mark.external
@pytest.mark.side_effect
async def test_sandbox_create_return_contract_discovery_v2(record_property):
    """Create one return draft and verify the exact returned UUID as a draft."""
    if os.environ.get("NILVERA_E2E_CREATE_RETURN_ALLOWED", "false").lower() != "true":
        pytest.skip("CreateReturn discovery requires explicit Sandbox authorization")

    sender_key = os.environ.get("NILVERA_E2E_SENDER_SANDBOX_KEY", "")
    receiver_key = os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY", "")
    hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY", "")
    source_run_id = os.environ.get("NILVERA_E2E_SOURCE_RUN_ID", "")
    source_timestamp = os.environ.get("NILVERA_E2E_SOURCE_RUN_TIMESTAMP", "")
    seller_tax_number = os.environ.get("NILVERA_E2E_SELLER_VKN", "")
    buyer_tax_number = os.environ.get("NILVERA_E2E_BUYER_VKN", "")
    provider_write_count = 0

    try:
        reference_time = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            raise ValueError
        fixture_time = pilot_invoice_datetime(os.environ.get("NILVERA_PILOT_INVOICE_DATE"))
        if fixture_time.year != reference_time.year:
            raise ValueError
        identity = build_fixture_identity(year=fixture_time.year, run_id=source_run_id, hmac_key=hmac_key)
        source_provider_uuid = str(build_fixture_request_uuid(identity, hmac_key))
    except (SandboxFixtureError, ValueError):
        pytest.fail("BLOCKED_INVALID_CREATE_RETURN_FIXTURE_SOURCE", pytrace=False)

    sender_client = new_sandbox_client(sender_key)
    receiver_client = new_sandbox_client(receiver_key)
    try:
        async with sender_client as sender, receiver_client as receiver:
            reconciliation = await reconcile_incoming_commercial_fixture(
                sender_client=ReadOnlySandboxClient(sender),
                receiver_client=ReadOnlySandboxClient(receiver),
                sender_key=sender_key,
                receiver_key=receiver_key,
                hmac_key=hmac_key,
                run_id=source_run_id,
                seller_tax_number=seller_tax_number,
                buyer_tax_number=buyer_tax_number,
                reference_time=reference_time,
                delivery_diagnostics=True,
            )
            answer_states = {
                reconciliation.receiver_status_answer_state,
                reconciliation.receiver_detail_answer_state,
            }
            source_terminal = bool(answer_states & {"APPROVED", "ANSWERED_AUTOMATICALLY"}) or (
                reconciliation.receiver_answered_automatically is True
            )
            source_ready = (
                reconciliation.match_count_class == "ONE"
                and reconciliation.receiver_visibility == FOUND
                and reconciliation.receiver_status_ready is True
                and reconciliation.receiver_alias_match is True
                and source_terminal
            )
            record_property("source_fixture_ready", str(source_ready).lower())
            if not source_ready:
                pytest.fail("BLOCKED_CREATE_RETURN_SOURCE_NOT_READY", pytrace=False)

            adapter = NilveraReturnAdapter(receiver)
            with patch.object(receiver, "post", wraps=receiver.post) as provider_post:
                try:
                    created = await adapter.create_return(
                        source_provider_uuid,
                        correlation_id=reconciliation.correlation_label,
                    )
                except Exception as exc:
                    provider_write_count = provider_post.await_count
                    http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
                    pytest.fail(
                        f"CreateReturn discovery failed (error_type={type(exc).__name__}, "
                        f"http_status={http_status}, write_count={provider_write_count})",
                        pytrace=False,
                    )
                provider_write_count = provider_post.await_count

            if provider_write_count != 1:
                pytest.fail(
                    f"CreateReturn provider write count is invalid (write_count={provider_write_count})",
                    pytrace=False,
                )

            try:
                await adapter.verify_return_draft(
                    str(created.provider_uuid),
                    correlation_id=reconciliation.correlation_label,
                )
            except Exception as exc:
                http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
                pytest.fail(
                    f"CreateReturn draft verification failed (error_type={type(exc).__name__}, "
                    f"http_status={http_status}, write_count={provider_write_count})",
                    pytrace=False,
                )

            record_property("provider_write_count", "1")
            record_property("response_uuid_present", "true")
            record_property("created_document_found", "true")
            record_property("verification_contract", "DRAFT_MODEL")
    except SandboxFixtureError as exc:
        record_property("provider_write_count", str(provider_write_count))
        pytest.fail(exc.safe_code, pytrace=False)
