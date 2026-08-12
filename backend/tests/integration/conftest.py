import os

import pytest
import pytest_asyncio

from core.integrations.invoice_gl_bridge import reverse_incoming_invoice_gl_for_return
from core.integrations.nilvera.incoming import NilveraIncomingService
from core.integrations.nilvera.return_adapter import NilveraReturnAdapter
from core.tenant_db import get_db_for_tenant
from tests.nilvera_incoming_pagination import (
    fetch_all_incoming_invoice_pages,
    scope_incoming_invoice_page_to_provider_uuid,
)
from tests.nilvera_sandbox_fixture import (
    build_fixture_identity,
    build_fixture_request_uuid,
    pilot_invoice_datetime,
)


_PAGINATED_DISCOVERY_TESTS = {
    "test_sandbox_incoming_commercial_invoice_answer_contract",
    "test_sandbox_incoming_commercial_invoice_answer_discovery",
}
_CREATE_RETURN_TEST = "test_sandbox_create_return_contract_discovery"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


@pytest.fixture(autouse=True)
def paginate_nilvera_incoming_answer_discovery(request, monkeypatch):
    """Give only the Nilvera answer tests a bounded, exact-fixture read.

    The shared Sandbox can contain unrelated incoming documents, including
    profiles Syroce intentionally does not support. Discover all bounded pages,
    then expose only the deterministic approved fixture to the answer test and
    its local synchronization step. Provider mutation semantics are untouched.
    """
    if request.node.name not in _PAGINATED_DISCOVERY_TESTS:
        yield
        return

    hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY", "")
    source_run_id = os.environ.get("NILVERA_E2E_SOURCE_RUN_ID", "")
    fixture_time = pilot_invoice_datetime(os.environ.get("NILVERA_PILOT_INVOICE_DATE"))
    identity = build_fixture_identity(
        year=fixture_time.year,
        run_id=source_run_id,
        hmac_key=hmac_key,
    )
    target_provider_uuid = str(build_fixture_request_uuid(identity, hmac_key))

    original = NilveraIncomingService.fetch_incoming_invoices

    async def paginated(self, start_date, end_date, *, page=1, page_size=100):
        if page != 1 or page_size != 100:
            return await original(
                self,
                start_date,
                end_date,
                page=page,
                page_size=page_size,
            )

        async def fetch_page(page_number: int):
            return await original(
                self,
                start_date,
                end_date,
                page=page_number,
                page_size=page_size,
            )

        aggregated = await fetch_all_incoming_invoice_pages(
            fetch_page,
            page_size=page_size,
        )
        return scope_incoming_invoice_page_to_provider_uuid(
            aggregated,
            target_provider_uuid,
        )

    monkeypatch.setattr(NilveraIncomingService, "fetch_incoming_invoices", paginated)
    yield


@pytest_asyncio.fixture(autouse=True)
async def verify_nilvera_create_return_gl_reversal(request, monkeypatch):
    """Bind the one approved CreateReturn write to a real Mongo GL reversal check.

    The provider test remains the sole owner of the POST and its GET-only
    verification. This fixture only prepares an isolated CI source journal,
    captures the UUID returned by that same POST, and—only when the provider
    test call phase passed—runs Syroce's real GL reversal function twice to
    prove both exact debit/credit reversal and idempotency. No extra provider
    request is made here.
    """
    if request.node.name != _CREATE_RETURN_TEST:
        yield
        return

    tenant_id = "nilvera-sandbox-gl-e2e"
    source_run_id = os.environ.get("NILVERA_E2E_SOURCE_RUN_ID", "")
    source_invoice_id = f"sandbox-fixture-{source_run_id}"
    action_id = f"create-return-{source_run_id}"
    db = get_db_for_tenant(tenant_id)

    await db.gl_journal_entries.delete_many({"tenant_id": tenant_id})
    await db.gl_accounts.delete_many({"tenant_id": tenant_id})
    await db.gl_accounts.insert_many(
        [
            {
                "tenant_id": tenant_id,
                "code": "E2E-PURCHASE",
                "name": "Sandbox Purchase",
                "type": "expense",
                "active": True,
            },
            {
                "tenant_id": tenant_id,
                "code": "E2E-VAT",
                "name": "Sandbox Input VAT",
                "type": "asset",
                "active": True,
            },
            {
                "tenant_id": tenant_id,
                "code": "E2E-PAYABLE",
                "name": "Sandbox Payable",
                "type": "liability",
                "active": True,
            },
        ]
    )
    await db.gl_journal_entries.insert_one(
        {
            "id": "sandbox-source-journal",
            "tenant_id": tenant_id,
            "entry_no": "JE-SANDBOX-SOURCE",
            "date": "2026-08-12",
            "memo": "Nilvera Sandbox source invoice",
            "status": "posted",
            "source": "nilvera_incoming",
            "source_ref": source_invoice_id,
            "idempotency_key": f"nilvera-incoming:{source_invoice_id}",
            "lines": [
                {
                    "account_code": "E2E-PURCHASE",
                    "debit": 100.0,
                    "credit": 0.0,
                    "memo": "base",
                },
                {
                    "account_code": "E2E-VAT",
                    "debit": 20.0,
                    "credit": 0.0,
                    "memo": "vat",
                },
                {
                    "account_code": "E2E-PAYABLE",
                    "debit": 0.0,
                    "credit": 120.0,
                    "memo": "vendor",
                },
            ],
        }
    )

    captured: dict[str, str] = {}
    original_create_return = NilveraReturnAdapter.create_return

    async def capture_create_return(self, source_provider_uuid, *, correlation_id=None):
        result = await original_create_return(
            self,
            source_provider_uuid,
            correlation_id=correlation_id,
        )
        captured["generated_provider_uuid"] = str(result.provider_uuid)
        return result

    monkeypatch.setattr(NilveraReturnAdapter, "create_return", capture_create_return)
    yield

    call_report = getattr(request.node, "rep_call", None)
    if call_report is None or not call_report.passed:
        request.node.user_properties.append(("gl_reversal_status", "not_attempted_provider_test_not_passed"))
        return

    generated_provider_uuid = captured.get("generated_provider_uuid")
    if not generated_provider_uuid:
        pytest.fail("BLOCKED_CREATE_RETURN_GL_UUID_NOT_CAPTURED", pytrace=False)

    first = await reverse_incoming_invoice_gl_for_return(
        tenant_id,
        source_invoice_id,
        action_id=action_id,
        generated_provider_uuid=generated_provider_uuid,
        actor="sandbox-e2e",
    )
    if first is None:
        pytest.fail("BLOCKED_CREATE_RETURN_GL_SOURCE_MISSING", pytrace=False)

    lines = first.get("lines") or []
    expected = [
        ("E2E-PURCHASE", 0.0, 100.0),
        ("E2E-VAT", 0.0, 20.0),
        ("E2E-PAYABLE", 120.0, 0.0),
    ]
    observed = [
        (line.get("account_code"), float(line.get("debit", 0)), float(line.get("credit", 0)))
        for line in lines
    ]
    if observed != expected:
        pytest.fail("BLOCKED_CREATE_RETURN_GL_REVERSAL_MISMATCH", pytrace=False)
    if first.get("nilvera_generated_provider_uuid") != generated_provider_uuid:
        pytest.fail("BLOCKED_CREATE_RETURN_GL_PROVIDER_UUID_MISMATCH", pytrace=False)
    if first.get("reverses_entry_id") != "sandbox-source-journal":
        pytest.fail("BLOCKED_CREATE_RETURN_GL_SOURCE_LINK_MISMATCH", pytrace=False)

    second = await reverse_incoming_invoice_gl_for_return(
        tenant_id,
        source_invoice_id,
        action_id=action_id,
        generated_provider_uuid=generated_provider_uuid,
        actor="sandbox-e2e",
    )
    reversal_count = await db.gl_journal_entries.count_documents(
        {
            "tenant_id": tenant_id,
            "idempotency_key": f"nilvera-return:{action_id}",
        }
    )
    if second is None or second.get("id") != first.get("id") or reversal_count != 1:
        pytest.fail("BLOCKED_CREATE_RETURN_GL_IDEMPOTENCY_MISMATCH", pytrace=False)

    request.node.user_properties.extend(
        [
            ("gl_reversal_status", "posted"),
            ("gl_reversal_idempotent", "true"),
            ("gl_reversal_count", "1"),
        ]
    )
