import inspect
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import (
    NilveraApiError,
    NilveraAuthError,
    NilveraNotFoundError,
    NilveraServerError,
    NilveraTimeoutError,
    NilveraValidationError,
)
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome
from scripts.nilvera_sandbox_selector import (
    INCOMING_FIXTURE_TARGET,
    RECONCILIATION_TARGET,
    SANDBOX_FILE,
    select_test_target,
)
from tests.nilvera_sandbox_fixture import (
    AMBIGUOUS_WRITE,
    DEFINITIVE_REJECTION,
    FIELD_MISSING,
    FIELD_PRESENT,
    FORMAT_VALID,
    FOUND,
    MATCH_COUNT_ONE,
    MATCH_COUNT_ZERO,
    NOT_FOUND_OR_NOT_VISIBLE,
    PAGE_COUNT_ONE,
    PAGE_COUNT_TWO_TO_FIVE,
    RECONCILIATION_MAX_PAGES,
    TOTAL_MISMATCH,
    ReadOnlySandboxClient,
    SandboxFixtureBlocked,
    SandboxFixtureFailed,
    build_fixture_identity,
    build_fixture_payload,
    classify_fixture_payload_contract,
    ensure_fixture_invoice_date,
    ensure_fixture_payload_contract,
    fixture_correlation_label,
    parse_pilot_invoice_date,
    pilot_invoice_datetime,
    prepare_incoming_commercial_fixture,
    reconcile_incoming_commercial_fixture,
)

SENDER_KEY = "sender-sandbox-key-value"
RECEIVER_KEY = "receiver-sandbox-key-value"
HMAC_KEY = "fixture-correlation-key-is-at-least-32-bytes"
SELLER_TAX_NUMBER = "1111111111"
BUYER_TAX_NUMBER = "2222222222"
RUN_ID = "31000000000"
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
PILOT_DATE = "2026-08-06"
PROVIDER_UUID = "123e4567-e89b-12d3-a456-426614174000"


def test_workflow_sandbox_modes_are_mutually_exclusive():
    workflow = (Path(__file__).parents[3] / ".github/workflows/nilvera-sandbox-e2e.yml").read_text()

    assert "run_outgoing_contract:" in workflow
    assert "run_incoming_fixture:" in workflow
    assert "run_reconciliation:" in workflow
    assert "reconciliation_source_timestamp:" in workflow
    assert "default: false" in workflow
    assert "scripts/nilvera_sandbox_selector.py" in workflow
    assert (
        "NILVERA_PILOT_INVOICE_DATE: ${{ secrets.NILVERA_PILOT_INVOICE_DATE }}"
        in workflow
    )
    assert "BLOCKED_INVALID_OR_MISSING_PILOT_INVOICE_DATE" in workflow
    assert "BLOCKED_EXACT_HEAD_NOT_APPROVED" in workflow
    assert "BLOCKED_PROVIDER_WRITE_NOT_CONFIRMED" in workflow
    assert "BLOCKED_TEST_ACCOUNT_NOT_ATTESTED" in workflow
    assert "WORKFLOW_RUN_ATTEMPT: ${{ github.run_attempt }}" in workflow
    with pytest.raises(ValueError, match="BLOCKED_MUTUALLY_EXCLUSIVE_SANDBOX_MODES"):
        select_test_target(run_incoming_fixture=True, run_incoming_answer=True, run_reconciliation=False)
    with pytest.raises(ValueError, match="BLOCKED_MUTUALLY_EXCLUSIVE_SANDBOX_MODES"):
        select_test_target(run_incoming_fixture=False, run_incoming_answer=True, run_reconciliation=True)
    with pytest.raises(ValueError, match="BLOCKED_MUTUALLY_EXCLUSIVE_SANDBOX_MODES"):
        select_test_target(
            run_outgoing_contract=True,
            run_incoming_fixture=True,
            run_incoming_answer=False,
        )
    with pytest.raises(ValueError, match="BLOCKED_SANDBOX_MODE_REQUIRED"):
        select_test_target(
            run_incoming_fixture=False,
            run_incoming_answer=False,
            run_reconciliation=False,
        )
    assert (
        select_test_target(
            run_outgoing_contract=True,
            run_incoming_fixture=False,
            run_incoming_answer=False,
        )
        == SANDBOX_FILE
    )
    assert select_test_target(run_incoming_fixture=True, run_incoming_answer=False) == INCOMING_FIXTURE_TARGET
    assert select_test_target(run_incoming_fixture=False, run_incoming_answer=False, run_reconciliation=True) == RECONCILIATION_TARGET


async def test_read_only_client_blocks_non_get_methods_before_provider_access():
    delegate = SimpleNamespace(
        get=AsyncMock(return_value={"ok": True}),
        post=AsyncMock(),
        put=AsyncMock(),
        patch=AsyncMock(),
        delete=AsyncMock(),
        last_http_status=200,
    )
    client = ReadOnlySandboxClient(delegate)

    assert await client.get("/read") == {"ok": True}
    for method in (client.post, client.put, client.patch, client.delete):
        with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_RECONCILIATION_NON_GET_METHOD"):
            await method("/blocked")

    delegate.get.assert_awaited_once_with("/read", retryable=False)
    delegate.post.assert_not_awaited()
    delegate.put.assert_not_awaited()
    delegate.patch.assert_not_awaited()
    delegate.delete.assert_not_awaited()
    assert client.exact_http_status == 200


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
    assert payload.EInvoice.InvoiceInfo.LineExtensionAmount == Decimal("1.00")
    assert payload.EInvoice.InvoiceInfo.GeneralKDV20Total == Decimal("0.20")
    assert payload.EInvoice.InvoiceInfo.GeneralAllowanceTotal == Decimal("0.00")
    assert payload.EInvoice.InvoiceInfo.PayableAmount == Decimal("1.20")
    assert payload.EInvoice.InvoiceInfo.KdvTotal == Decimal("0.20")
    assert fixture_correlation_label(identity, HMAC_KEY) != identity
    assert len(fixture_correlation_label(identity, HMAC_KEY)) == 12


@pytest.mark.parametrize("value", [None, "", "2026-8-06", "2026-02-30", "2026-08-06T00:00:00Z", " 2026-08-06"])
def test_pilot_invoice_date_missing_or_invalid_is_blocked(value):
    expected_code = "BLOCKED_MISSING_PILOT_INVOICE_DATE" if value in (None, "") else "BLOCKED_INVALID_PILOT_INVOICE_DATE"
    with pytest.raises(SandboxFixtureBlocked, match=expected_code):
        parse_pilot_invoice_date(value)


def test_pilot_invoice_date_is_exact_utc_midnight_without_timezone_shift():
    parsed = pilot_invoice_datetime(PILOT_DATE)

    assert parsed == datetime(2026, 8, 6, 0, 0, tzinfo=UTC)
    assert parsed.date().isoformat() == PILOT_DATE
    assert "datetime.now" not in inspect.getsource(prepare_incoming_commercial_fixture)


def test_fixture_date_preflight_rejects_timezone_shifted_dto():
    identity = build_fixture_identity(year=2026, run_id=RUN_ID, hmac_key=HMAC_KEY)
    shifted = datetime(2026, 8, 6, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    payload = build_fixture_payload(
        fixture_identity=identity,
        seller_tax_number=SELLER_TAX_NUMBER,
        buyer_tax_number=BUYER_TAX_NUMBER,
        buyer_alias="urn:mail:defaultpk@sandbox.invalid",
        issue_date=shifted,
    )

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_DATE_MISMATCH"):
        ensure_fixture_invoice_date(payload, parse_pilot_invoice_date(PILOT_DATE))


def test_fixture_payload_matches_official_send_model_contract_shape():
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)
    payload = build_fixture_payload(
        fixture_identity=identity,
        seller_tax_number=SELLER_TAX_NUMBER,
        buyer_tax_number=BUYER_TAX_NUMBER,
        buyer_alias="urn:mail:defaultpk@sandbox.invalid",
        issue_date=NOW,
    )
    serialized = payload.model_dump(mode="json", by_alias=True)
    classes = classify_fixture_payload_contract(payload)

    assert set(serialized) == {"EInvoice", "CustomerAlias"}
    assert set(serialized["EInvoice"]) == {"InvoiceInfo", "CompanyInfo", "CustomerInfo", "InvoiceLines"}
    assert set(serialized["EInvoice"]["InvoiceInfo"]) == {
        "UUID",
        "IssueDate",
        "InvoiceType",
        "InvoiceProfile",
        "InvoiceSerieOrNumber",
        "CurrencyCode",
        "ExchangeRate",
        "LineExtensionAmount",
        "GeneralKDV1Total",
        "GeneralKDV8Total",
        "GeneralKDV10Total",
        "GeneralKDV18Total",
        "GeneralKDV20Total",
        "GeneralAllowanceTotal",
        "PayableAmount",
        "KdvTotal",
    }
    assert classes["InvoiceInfo"] == FIELD_PRESENT
    assert classes["Scenario"] == FIELD_MISSING
    assert classes["TaxTotal"] == FIELD_MISSING
    assert classes["WithholdingTaxTotal"] == FIELD_MISSING
    assert classes["LegalMonetaryTotal"] == FIELD_MISSING
    assert classes["SenderAlias"] == FIELD_MISSING
    assert classes["ReceiverAlias"] == FIELD_PRESENT
    assert all(
        classes[field] == FORMAT_VALID
        for field in (
            "InvoiceType",
            "InvoiceProfile",
            "CurrencyCode",
            "IssueDate",
            "InvoiceSerieOrNumber",
        )
    )


def test_fixture_payload_monetary_totals_are_consistent():
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)
    payload = build_fixture_payload(
        fixture_identity=identity,
        seller_tax_number=SELLER_TAX_NUMBER,
        buyer_tax_number=BUYER_TAX_NUMBER,
        buyer_alias="urn:mail:defaultpk@sandbox.invalid",
        issue_date=NOW,
    )
    classes = classify_fixture_payload_contract(payload)

    assert all(
        classes[field] == FORMAT_VALID
        for field in (
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
        )
    )

    payload.EInvoice.InvoiceInfo.PayableAmount = Decimal("1.21")
    assert classify_fixture_payload_contract(payload)["PayableAmount"] == TOTAL_MISMATCH
    with pytest.raises(SandboxFixtureFailed, match="FIXTURE_PAYLOAD_CONTRACT_FAILED"):
        ensure_fixture_payload_contract(payload)


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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
        )

    sender_client.get.assert_not_awaited()
    sender_client.post.assert_not_awaited()
    receiver_client.get.assert_not_awaited()


@pytest.mark.parametrize("pilot_date", [None, "", "2026-02-30", "2026-08-06T00:00:00Z"])
async def test_invalid_pilot_date_blocks_before_provider_access(pilot_date):
    sender_client = SimpleNamespace(get=AsyncMock(), post=AsyncMock())
    receiver_client = SimpleNamespace(get=AsyncMock())

    with pytest.raises(SandboxFixtureBlocked):
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
            pilot_invoice_date=pilot_date,
            workflow_run_attempt=1,
        )

    sender_client.get.assert_not_awaited()
    sender_client.post.assert_not_awaited()
    receiver_client.get.assert_not_awaited()


async def test_duplicate_workflow_attempt_blocks_before_provider_access():
    sender_client = SimpleNamespace(get=AsyncMock(), post=AsyncMock())
    receiver_client = SimpleNamespace(get=AsyncMock())

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_DUPLICATE_FIXTURE_RUN_ATTEMPT"):
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=2,
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
        fetch_incoming_invoice_detail=AsyncMock(
            return_value=SimpleNamespace(
                invoice_number=identity,
                invoice_profile="TICARIFATURA",
                invoice_type="SATIS",
            )
        ),
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
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
    assert kwargs["stage"] == "SEND_MODEL"
    assert kwargs["json"]["EInvoice"]["InvoiceInfo"]["IssueDate"].startswith(PILOT_DATE)
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
            sleeper=AsyncMock(),
        )

    assert exc_info.value.provider_write_count == 1
    assert exc_info.value.failure_stage == "SEND_MODEL"
    assert exc_info.value.http_status_class is None
    assert exc_info.value.exception_type == "NilveraTimeoutError"
    assert exc_info.value.write_disposition == AMBIGUOUS_WRITE
    sender_client.post.assert_awaited_once()


async def test_fixture_validation_rejection_is_definitive_and_sanitized():
    error = NilveraValidationError(
        "provider rejected fixture",
        http_status=400,
        provider_code="MODEL_VALIDATION_FAILED",
    )
    sender_client, receiver_client = _clients(post_side_effect=error)

    with pytest.raises(SandboxFixtureFailed, match="FIXTURE_VALIDATION_REJECTED") as exc_info:
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
            sleeper=AsyncMock(),
        )

    assert exc_info.value.provider_write_count == 1
    assert exc_info.value.failure_stage == "SEND_MODEL"
    assert exc_info.value.http_status_class == "4xx"
    assert exc_info.value.provider_code == "MODEL_VALIDATION_FAILED"
    assert exc_info.value.exception_type == "NilveraValidationError"
    assert exc_info.value.write_disposition == DEFINITIVE_REJECTION
    sender_client.post.assert_awaited_once()


async def test_fixture_422_code_2004_is_definitive_with_safe_validation_issue_and_no_retry():
    support_detail = (
        "Fatura Veritabanına Kaydedilemedi. Hata: TEST-INVOICE Numaralı Fatura "
        "'2026-03-23 | 2026-03-23 Tarihleri Arasında Olmalıdır.'"
    )
    error = NilveraValidationError(
        "provider rejected fixture",
        http_status=422,
        provider_code="2004",
        description="Kayıt Başarısız.",
        detail=support_detail,
    )
    sender_client, receiver_client = _clients(post_side_effect=error)

    with pytest.raises(SandboxFixtureFailed, match="FIXTURE_VALIDATION_REJECTED") as exc_info:
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
            sleeper=AsyncMock(),
        )

    assert exc_info.value.http_status == 422
    assert exc_info.value.provider_code == "2004"
    assert exc_info.value.validation_issue == "FIELD=InvoiceInfo.IssueDate;REASON=DATE_OUT_OF_RANGE"
    assert exc_info.value.validation_detail == (
        "FIELD=InvoiceInfo.IssueDate;REASON=DATE_OUT_OF_RANGE;"
        "WINDOW_START=2026-03-23;WINDOW_END=2026-03-23"
    )
    assert exc_info.value.classification == "VALIDATION_REJECTED"
    assert exc_info.value.write_disposition == DEFINITIVE_REJECTION
    assert exc_info.value.provider_write_count == 1
    sender_client.post.assert_awaited_once()


async def test_fixture_date_mismatch_blocks_with_zero_provider_writes():
    sender_client, receiver_client = _clients()
    identity = build_fixture_identity(year=2026, run_id=RUN_ID, hmac_key=HMAC_KEY)
    mismatched_payload = build_fixture_payload(
        fixture_identity=identity,
        seller_tax_number=SELLER_TAX_NUMBER,
        buyer_tax_number=BUYER_TAX_NUMBER,
        buyer_alias="urn:mail:defaultpk@sandbox.invalid",
        issue_date=pilot_invoice_datetime("2026-08-07"),
    )

    with (
        patch("tests.nilvera_sandbox_fixture.build_fixture_payload", return_value=mismatched_payload),
        pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_DATE_MISMATCH") as exc_info,
    ):
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
        )

    assert exc_info.value.provider_write_count == 0
    sender_client.post.assert_not_awaited()


async def test_fixture_drops_unsafe_provider_code_from_diagnostics():
    error = NilveraValidationError(
        "provider rejected fixture",
        http_status=422,
        provider_code="unsafe provider detail",
    )
    sender_client, receiver_client = _clients(post_side_effect=error)

    with pytest.raises(SandboxFixtureFailed) as exc_info:
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
            sleeper=AsyncMock(),
        )

    assert exc_info.value.provider_code is None
    assert exc_info.value.http_status_class == "4xx"


@pytest.mark.parametrize(
    "error, expected_type, expected_status_class",
    [
        (NilveraServerError("provider unavailable", http_status=500), "NilveraServerError", "5xx"),
        (NilveraApiError("invalid response"), "NilveraApiError", None),
    ],
)
async def test_fixture_ambiguous_send_failure_does_not_retry(error, expected_type, expected_status_class):
    sender_client, receiver_client = _clients(post_side_effect=error)

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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
            sleeper=AsyncMock(),
        )

    assert exc_info.value.provider_write_count == 1
    assert exc_info.value.http_status_class == expected_status_class
    assert exc_info.value.exception_type == expected_type
    assert exc_info.value.write_disposition == AMBIGUOUS_WRITE
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
            pilot_invoice_date=PILOT_DATE,
            workflow_run_attempt=1,
            outgoing_delays=(0,),
            sleeper=AsyncMock(),
        )

    sender_client.post.assert_awaited_once()


async def test_fixture_not_visible_on_receiver_is_blocked():
    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_NOT_VISIBLE") as exc_info:
        await _prepare(visible=False)

    assert exc_info.value.provider_write_count == 1


async def test_read_only_reconciliation_finds_exact_outgoing_and_incoming_fixture():
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)

    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        if path == NilveraEndpoints.LIST_SALE_INVOICES:
            return {"Content": [{"UUID": PROVIDER_UUID, "InvoiceNumber": identity}]}
        if path == NilveraEndpoints.GET_SALE_INVOICE_STATUS.format(uuid=PROVIDER_UUID):
            return {"Status": "SUCCESS"}
        if path == NilveraEndpoints.GET_SALE_INVOICE_DETAIL.format(uuid=PROVIDER_UUID):
            return {
                "InvoiceNumber": identity,
                "InvoiceProfile": "TICARIFATURA",
                "InvoiceType": "SATIS",
            }
        raise AssertionError("unexpected sender read")

    async def receiver_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": BUYER_TAX_NUMBER}
        return {"Content": [{"UUID": PROVIDER_UUID, "InvoiceNumber": identity}]}

    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get))
    receiver_client = SimpleNamespace(get=AsyncMock(side_effect=receiver_get))
    incoming_service = _incoming_service(visible=True)

    with patch("tests.nilvera_sandbox_fixture.NilveraIncomingService", return_value=incoming_service):
        result = await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )

    assert result.outgoing_result == FOUND
    assert result.provider_write_count == 0
    assert result.sender_match is True
    assert result.receiver_match is True
    assert result.match_count_class == MATCH_COUNT_ONE
    assert result.outgoing_outcome == ProviderInvoiceOutcome.ACCEPTED
    assert result.outgoing_detail_match is True
    assert result.receiver_visibility == FOUND
    assert result.receiver_detail_match is True
    assert result.receiver_status_ready is True
    assert result.sender_page_count_class == PAGE_COUNT_ONE
    assert result.receiver_page_count_class == PAGE_COUNT_ONE
    assert not hasattr(sender_client, "post")
    assert not hasattr(receiver_client, "post")
    sale_list_call = next(call for call in sender_client.get.await_args_list if call.args[0] == NilveraEndpoints.LIST_SALE_INVOICES)
    assert sale_list_call.kwargs["params"]["StartDate"].startswith("2026-08-03")
    assert sale_list_call.kwargs["params"]["EndDate"].startswith("2026-08-09")
    assert sale_list_call.kwargs["params"]["DateFilterType"] == "CreatedDate"


async def test_read_only_reconciliation_blocks_company_mismatch_before_list_queries():
    sender_client = SimpleNamespace(get=AsyncMock(return_value={"TaxNumber": SELLER_TAX_NUMBER}))
    receiver_client = SimpleNamespace(get=AsyncMock(return_value={"TaxNumber": "3333333333"}))

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_SANDBOX_COMPANY_MISMATCH") as exc_info:
        await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )

    assert exc_info.value.sender_match is True
    assert exc_info.value.receiver_match is False
    sender_client.get.assert_awaited_once_with(NilveraEndpoints.GET_COMPANY)
    receiver_client.get.assert_awaited_once_with(NilveraEndpoints.GET_COMPANY)


async def test_read_only_reconciliation_reports_only_safe_query_failure_metadata():
    error = NilveraValidationError(
        "provider rejected query",
        http_status=400,
        provider_code="QUERY_RANGE_INVALID",
    )

    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        raise error

    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get))
    receiver_client = SimpleNamespace(get=AsyncMock(return_value={"TaxNumber": BUYER_TAX_NUMBER}))

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_RECONCILIATION_QUERY") as exc_info:
        await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )

    assert exc_info.value.failure_stage == "SENDER_SALE_LIST"
    assert exc_info.value.http_status == 400
    assert exc_info.value.http_status_class == "4xx"
    assert exc_info.value.provider_code == "QUERY_RANGE_INVALID"
    assert exc_info.value.exception_type == "NilveraValidationError"
    assert exc_info.value.sender_match is True
    assert exc_info.value.receiver_match is True


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, NilveraValidationError),
        (401, NilveraAuthError),
        (403, NilveraAuthError),
        (404, NilveraNotFoundError),
    ],
)
async def test_receiver_purchase_error_preserves_exact_safe_classification(status_code, error_type):
    error = error_type(
        "provider rejected receiver purchase query",
        http_status=status_code,
        provider_code="SAFE_PROVIDER_CODE",
    )

    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        return {"Content": []}

    async def receiver_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": BUYER_TAX_NUMBER}
        raise error

    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get))
    receiver_client = SimpleNamespace(get=AsyncMock(side_effect=receiver_get))

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_RECONCILIATION_QUERY") as exc_info:
        await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )

    assert exc_info.value.failure_stage == "RECEIVER_PURCHASE_LIST"
    assert exc_info.value.http_status == status_code
    assert exc_info.value.http_status_class == "4xx"
    assert exc_info.value.provider_code == "SAFE_PROVIDER_CODE"
    assert exc_info.value.exception_type == error_type.__name__
    assert exc_info.value.sender_match is True
    assert exc_info.value.receiver_match is True


async def test_read_only_reconciliation_reports_not_found_without_claiming_absence():
    async def sender_get(path, **kwargs):
        return {"TaxNumber": SELLER_TAX_NUMBER} if path == NilveraEndpoints.GET_COMPANY else {"Content": []}

    async def receiver_get(path, **kwargs):
        return {"TaxNumber": BUYER_TAX_NUMBER} if path == NilveraEndpoints.GET_COMPANY else {"Content": []}

    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get))
    receiver_client = SimpleNamespace(get=AsyncMock(side_effect=receiver_get))

    result = await reconcile_incoming_commercial_fixture(
        sender_client=sender_client,
        receiver_client=receiver_client,
        sender_key=SENDER_KEY,
        receiver_key=RECEIVER_KEY,
        hmac_key=HMAC_KEY,
        run_id=RUN_ID,
        seller_tax_number=SELLER_TAX_NUMBER,
        buyer_tax_number=BUYER_TAX_NUMBER,
        reference_time=NOW,
    )

    assert result.outgoing_result == NOT_FOUND_OR_NOT_VISIBLE
    assert result.provider_write_count == 0
    assert result.match_count_class == MATCH_COUNT_ZERO
    assert result.outgoing_outcome is None
    assert result.receiver_visibility == NOT_FOUND_OR_NOT_VISIBLE
    assert result.receiver_status_ready is None
    assert sender_client.get.await_count == 2
    assert receiver_client.get.await_count == 2
    purchase_call = next(call for call in receiver_client.get.await_args_list if call.args[0] == NilveraEndpoints.LIST_PURCHASE_INVOICES)
    assert set(purchase_call.kwargs["params"]) == {
        "StartDate",
        "EndDate",
        "DateFilterType",
        "SortColumn",
        "SortType",
        "Page",
        "PageSize",
    }
    assert purchase_call.kwargs["params"]["Page"] == "1"
    assert purchase_call.kwargs["params"]["PageSize"] == "100"


async def test_read_only_reconciliation_stops_on_multiple_exact_matches():
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)
    second_uuid = "223e4567-e89b-12d3-a456-426614174000"

    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        return {
            "Content": [
                {"UUID": PROVIDER_UUID, "InvoiceNumber": identity},
                {"UUID": second_uuid, "InvoiceNumber": identity},
            ]
        }

    async def receiver_get(path, **kwargs):
        return {"TaxNumber": BUYER_TAX_NUMBER} if path == NilveraEndpoints.GET_COMPANY else {"Content": []}

    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get))
    receiver_client = SimpleNamespace(get=AsyncMock(side_effect=receiver_get))

    with pytest.raises(SandboxFixtureBlocked, match="CONFLICT_FIXTURE_RECONCILIATION"):
        await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )


async def test_read_only_reconciliation_scans_all_pages_to_find_exact_fixture():
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)

    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        if path == NilveraEndpoints.LIST_SALE_INVOICES:
            page = int(kwargs["params"]["Page"])
            content = [{"UUID": PROVIDER_UUID, "InvoiceNumber": identity}] if page == 2 else []
            return {"TotalPages": 2, "Content": content}
        if path == NilveraEndpoints.GET_SALE_INVOICE_DETAIL.format(uuid=PROVIDER_UUID):
            return {
                "InvoiceNumber": identity,
                "InvoiceProfile": "TICARIFATURA",
                "InvoiceType": "SATIS",
            }
        if path == NilveraEndpoints.GET_SALE_INVOICE_STATUS.format(uuid=PROVIDER_UUID):
            return {"Status": "SUCCESS"}
        raise AssertionError("unexpected sender read")

    async def receiver_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": BUYER_TAX_NUMBER}
        page = int(kwargs["params"]["Page"])
        content = [{"UUID": PROVIDER_UUID, "InvoiceNumber": identity}] if page == 3 else []
        return {"TotalPages": 3, "Content": content}

    sender_delegate = SimpleNamespace(get=AsyncMock(side_effect=sender_get), last_http_status=200)
    receiver_delegate = SimpleNamespace(get=AsyncMock(side_effect=receiver_get), last_http_status=200)
    sender_client = ReadOnlySandboxClient(sender_delegate)
    receiver_client = ReadOnlySandboxClient(receiver_delegate)

    with patch("tests.nilvera_sandbox_fixture.NilveraIncomingService", return_value=_incoming_service(visible=True)):
        result = await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )

    assert result.match_count_class == MATCH_COUNT_ONE
    assert result.receiver_visibility == FOUND
    assert result.sender_page_count_class == PAGE_COUNT_TWO_TO_FIVE
    assert result.receiver_page_count_class == PAGE_COUNT_TWO_TO_FIVE
    assert result.http_status == 200
    sender_pages = [
        call.kwargs["params"]["Page"]
        for call in sender_delegate.get.await_args_list
        if call.args[0] == NilveraEndpoints.LIST_SALE_INVOICES
    ]
    receiver_pages = [
        call.kwargs["params"]["Page"]
        for call in receiver_delegate.get.await_args_list
        if call.args[0] == NilveraEndpoints.LIST_PURCHASE_INVOICES
    ]
    assert sender_pages == ["1", "2"]
    assert receiver_pages == ["1", "2", "3"]


async def test_read_only_reconciliation_uses_narrowed_detail_fallback_when_tag_field_is_absent():
    identity = build_fixture_identity(year=NOW.year, run_id=RUN_ID, hmac_key=HMAC_KEY)

    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        if path == NilveraEndpoints.LIST_SALE_INVOICES:
            return {
                "Content": [
                    {
                        "UUID": PROVIDER_UUID,
                        "InvoiceProfile": "TICARIFATURA",
                        "InvoiceType": "SATIS",
                        "BuyerTaxNumber": BUYER_TAX_NUMBER,
                    }
                ]
            }
        if path == NilveraEndpoints.GET_SALE_INVOICE_DETAIL.format(uuid=PROVIDER_UUID):
            return {
                "InvoiceNumber": identity,
                "InvoiceProfile": "TICARIFATURA",
                "InvoiceType": "SATIS",
            }
        if path == NilveraEndpoints.GET_SALE_INVOICE_STATUS.format(uuid=PROVIDER_UUID):
            return {"Status": "SUCCESS"}
        raise AssertionError("unexpected sender read")

    async def receiver_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": BUYER_TAX_NUMBER}
        return {
            "Content": [
                {
                    "UUID": PROVIDER_UUID,
                    "InvoiceProfile": "TICARIFATURA",
                    "InvoiceType": "SATIS",
                    "SenderTaxNumber": SELLER_TAX_NUMBER,
                }
            ]
        }

    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get))
    receiver_client = SimpleNamespace(get=AsyncMock(side_effect=receiver_get))
    incoming_service = _incoming_service(visible=True)

    with patch("tests.nilvera_sandbox_fixture.NilveraIncomingService", return_value=incoming_service):
        result = await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )

    assert result.match_count_class == MATCH_COUNT_ONE
    assert result.receiver_visibility == FOUND
    incoming_service.fetch_incoming_invoice_detail.assert_awaited_once_with(PROVIDER_UUID)
    assert all(call.args[0] != NilveraEndpoints.SEND_ANSWER for call in sender_client.get.await_args_list)
    assert all(call.args[0] != NilveraEndpoints.SEND_ANSWER for call in receiver_client.get.await_args_list)


async def test_read_only_reconciliation_blocks_before_partial_scan_exceeds_page_limit():
    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        return {"TotalPages": RECONCILIATION_MAX_PAGES + 1, "Content": []}

    sender_delegate = SimpleNamespace(get=AsyncMock(side_effect=sender_get), last_http_status=200)
    receiver_delegate = SimpleNamespace(
        get=AsyncMock(return_value={"TaxNumber": BUYER_TAX_NUMBER}),
        last_http_status=200,
    )

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_RECONCILIATION_PAGE_LIMIT") as exc_info:
        await reconcile_incoming_commercial_fixture(
            sender_client=ReadOnlySandboxClient(sender_delegate),
            receiver_client=ReadOnlySandboxClient(receiver_delegate),
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )

    assert exc_info.value.sender_page_count_class == PAGE_COUNT_ONE
    assert exc_info.value.receiver_page_count_class is None
    assert exc_info.value.http_status == 200
    assert sender_delegate.get.await_count == 2


async def test_read_only_reconciliation_treats_malformed_candidate_detail_as_blocked():
    async def sender_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": SELLER_TAX_NUMBER}
        if path == NilveraEndpoints.LIST_SALE_INVOICES:
            return {
                "Content": [
                    {
                        "UUID": PROVIDER_UUID,
                        "InvoiceProfile": "TICARIFATURA",
                        "InvoiceType": "SATIS",
                        "BuyerTaxNumber": BUYER_TAX_NUMBER,
                    }
                ]
            }
        return {"unexpected": "detail-shape"}

    async def receiver_get(path, **kwargs):
        if path == NilveraEndpoints.GET_COMPANY:
            return {"TaxNumber": BUYER_TAX_NUMBER}
        return {"Content": []}

    sender_client = SimpleNamespace(get=AsyncMock(side_effect=sender_get))
    receiver_client = SimpleNamespace(get=AsyncMock(side_effect=receiver_get))

    with pytest.raises(SandboxFixtureBlocked, match="BLOCKED_FIXTURE_RECONCILIATION_PARSE"):
        await reconcile_incoming_commercial_fixture(
            sender_client=sender_client,
            receiver_client=receiver_client,
            sender_key=SENDER_KEY,
            receiver_key=RECEIVER_KEY,
            hmac_key=HMAC_KEY,
            run_id=RUN_ID,
            seller_tax_number=SELLER_TAX_NUMBER,
            buyer_tax_number=BUYER_TAX_NUMBER,
            reference_time=NOW,
        )
