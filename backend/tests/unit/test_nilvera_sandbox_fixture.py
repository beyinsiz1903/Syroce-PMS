from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraTimeoutError
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome
from scripts.nilvera_sandbox_selector import INCOMING_FIXTURE_TARGET, select_test_target
from tests.nilvera_sandbox_fixture import (
    SandboxFixtureBlocked,
    SandboxFixtureFailed,
    build_fixture_identity,
    build_fixture_payload,
    fixture_correlation_label,
    prepare_incoming_commercial_fixture,
)

SENDER_KEY = "sender-sandbox-key-value"
RECEIVER_KEY = "receiver-sandbox-key-value"
HMAC_KEY = "fixture-correlation-key-is-at-least-32-bytes"
SELLER_TAX_NUMBER = "1111111111"
BUYER_TAX_NUMBER = "2222222222"
RUN_ID = "31000000000"
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
PROVIDER_UUID = "123e4567-e89b-12d3-a456-426614174000"


def test_workflow_fixture_mode_is_mutually_exclusive_with_incoming_answer():
    workflow = (Path(__file__).parents[3] / ".github/workflows/nilvera-sandbox-e2e.yml").read_text()

    assert "run_incoming_fixture:" in workflow
    assert "default: false" in workflow
    assert "scripts/nilvera_sandbox_selector.py" in workflow
    with pytest.raises(ValueError, match="BLOCKED_MUTUALLY_EXCLUSIVE_SANDBOX_WRITES"):
        select_test_target(run_incoming_fixture=True, run_incoming_answer=True)
    assert select_test_target(run_incoming_fixture=True, run_incoming_answer=False) == INCOMING_FIXTURE_TARGET


def test_fixture_identity_is_transferred_to_invoice_serie_or_number():
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)

    payload = build_fixture_payload(
        fixture_identity=identity,
        seller_tax_number=SELLER_TAX_NUMBER,
        buyer_tax_number=BUYER_TAX_NUMBER,
        buyer_alias="urn:mail:defaultpk@sandbox.invalid",
        issue_date=NOW,
    )

    assert len(identity) == 16
    assert identity.startswith("TST2026")
    assert payload.EInvoice.InvoiceInfo.InvoiceSerieOrNumber == identity
    assert payload.EInvoice.InvoiceInfo.InvoiceSerieOrNumber != "LOCAL_VALUE_MUST_NOT_BE_USED"
    assert fixture_correlation_label(identity, HMAC_KEY) != identity
    assert len(fixture_correlation_label(identity, HMAC_KEY)) == 12


async def test_identical_sender_and_receiver_keys_block_before_provider_access():
    sender_client = SimpleNamespace(get=AsyncMock(), post=AsyncMock())
    receiver_client = SimpleNamespace(get=AsyncMock())

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_IDENTICAL_SANDBOX_KEYS"):
        await prepare_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=SENDER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            buyer_alias="urn:mail:defaultpk@sandbox.invalid",
            now=NOW,
        )

    sender_client.get.assert_not_awaited()
    sender_client.post.assert_not_awaited()
    receiver_client.get.assert_not_awaited()


def _clients(*, sale_status: str = "SUCCESS", post_side_effect=None):
    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        return {"Status": sale_status}

    sender_post = AsyncMock(
        return_value={"UUID": PROVIDER_UUID} if post_side_effect is None else None,
        side_effect=post_side_effect,
    )
    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get), post=sender_post)
    receiver_client = SimpleNamespace(get=AsyncMock(return_value={"TaxNumber": BUYER_TAX_NUMBER}))
    return sender_client, receiver_client


def _incoming_service(*, visible: bool):
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)
    items = (SimpleNamespace(invoice_number=identity, provider_uuid=PROVIDER_UUID),) if visible else ()
    return SimpleNamespace(
        fetch_incoming_invoices=AsyncMock(return_value=SimpleNamespace(items=items)),
        fetch_incoming_invoice_detail=AsyncMock(return_value=SimpleNamespace(invoice_profile="TICARIFATURA", invoice_type="SATIS")),
        fetch_incoming_invoice_status=AsyncMock(return_value=SimpleNamespace(status_code="SUCCEED")),
    )


async def _prepare(*, sale_status: str = "SUCCESS", visible: bool = True, post_side_effect=None):
    sender_client, receiver_client = _clients(sale_status=sale_status, post_side_effect=post_side_effect)
    incoming_service = _incoming_service(visible=visible)
    with patch("tests.nilvera_sandbox_fixture.NilveraIncomingService", return_value=incoming_service):
        result = await prepare_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            buyer_alias="urn:mail:defaultpk@sandbox.invalid",
            now=NOW,
            outgoing_delays=(0,),
            incoming_delays=(0,),
            sleeper=AsyncMock(),
        )
    return result, sender_client, incoming_service


async def test_fixture_sends_at_most_one_provider_write():
    result, sender_client, _ = await _prepare()

    assert result.provider_write_count == 1
    assert result.provider_outcome == ProviderInvoiceOutcome.ACCEPTED
    sender_client.post.assert_awaited_once()
    _, kwargs = sender_client.post.await_args
    assert kwargs["retryable"] is False
    assert kwargs["json"]["EInvoice"]["InvoiceInfo"]["InvoiceProfile"] == "TICARIFATURA"
    assert kwargs["json"]["EInvoice"]["InvoiceInfo"]["InvoiceType"] == "SATIS"


async def test_fixture_timeout_does_not_retry_provider_write():
    sender_client, receiver_client = _clients(post_side_effect=NilveraTimeoutError("provider timeout"))

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_WRITE_OUTCOME_UNKNOWN") as exc_info:
        await prepare_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            buyer_alias="urn:mail:defaultpk@sandbox.invalid",
            now=NOW,
            sleeper=AsyncMock(),
        )

    assert exc_info.value.provider_write_count == 1
    sender_client.post.assert_awaited_once()


async def test_fixture_rejected_result_is_failure():
    sender_client, receiver_client = _clients(sale_status="REJECTED")

    with pytest.raises(SandboxFixtureFailed, match="FIXTURE_PROVIDER_REJECTED"):
        await prepare_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            buyer_alias="urn:mail:defaultpk@sandbox.invalid",
            now=NOW,
            outgoing_delays=(0,),
            sleeper=AsyncMock(),
        )

    sender_client.post.assert_awaited_once()


async def test_fixture_not_visible_on_receiver_is_blocked():
    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_NOT_VISIBLE") as exc_info:
        await _prepare(visible=False)

    assert exc_info.value.provider_write_count == 1
