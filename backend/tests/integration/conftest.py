import pytest

from core.integrations.nilvera.incoming import NilveraIncomingService
from tests.nilvera_incoming_pagination import fetch_all_incoming_invoice_pages


_PAGINATED_DISCOVERY_TESTS = {
    "test_sandbox_incoming_commercial_invoice_answer_contract",
    "test_sandbox_incoming_commercial_invoice_answer_discovery",
}


@pytest.fixture(autouse=True)
def paginate_nilvera_incoming_answer_discovery(request, monkeypatch):
    """Give only the Nilvera answer-discovery tests a bounded multi-page read.

    Provider mutation semantics are untouched; this only replaces the GET list
    discovery call used before any SendAnswer attempt.
    """
    if request.node.name not in _PAGINATED_DISCOVERY_TESTS:
        yield
        return

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

        return await fetch_all_incoming_invoice_pages(
            fetch_page,
            page_size=page_size,
        )

    monkeypatch.setattr(NilveraIncomingService, "fetch_incoming_invoices", paginated)
    yield
