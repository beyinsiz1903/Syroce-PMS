from collections.abc import Awaitable, Callable

from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_mapper import IncomingInvoicePage


DEFAULT_MAX_DISCOVERY_PAGES = 20


async def fetch_all_incoming_invoice_pages(
    fetch_page: Callable[[int], Awaitable[IncomingInvoicePage]],
    *,
    page_size: int = 100,
    max_pages: int = DEFAULT_MAX_DISCOVERY_PAGES,
) -> IncomingInvoicePage:
    """Aggregate bounded Nilvera Purchase pages for exact fixture discovery.

    The returned object is a synthetic single page containing the complete
    bounded result set. This keeps downstream consumers from re-paginating an
    already aggregated result. The helper remains fail-closed for malformed or
    changing provider pagination and for result sets beyond the safety bound.
    """
    if page_size < 1 or page_size > 100 or max_pages < 1:
        raise NilveraValidationError("Incoming invoice discovery pagination configuration is invalid")

    first = await fetch_page(1)
    total_pages = first.total_pages
    if total_pages < 1:
        if first.items:
            raise NilveraValidationError("Incoming invoice discovery pagination is inconsistent")
        return first
    if total_pages > max_pages:
        raise NilveraValidationError("Incoming invoice discovery exceeds safe page limit")

    items = list(first.items)
    for page_number in range(2, total_pages + 1):
        current = await fetch_page(page_number)
        if current.page != page_number or current.page_size != page_size or current.total_pages != total_pages:
            raise NilveraValidationError("Incoming invoice discovery pagination changed during scan")
        items.extend(current.items)

    return IncomingInvoicePage(
        items=tuple(items),
        page=1,
        page_size=page_size,
        total_count=len(items),
        total_pages=1,
    )
