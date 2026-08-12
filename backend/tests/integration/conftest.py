import os

import pytest

from core.integrations.nilvera.incoming import NilveraIncomingService
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
