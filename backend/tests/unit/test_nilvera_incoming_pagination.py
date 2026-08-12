from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_mapper import IncomingInvoicePage
from tests.nilvera_incoming_pagination import fetch_all_incoming_invoice_pages


def _page(page, total_pages, items, *, total_count=0, page_size=100):
    return IncomingInvoicePage(
        items=tuple(SimpleNamespace(provider_uuid=item) for item in items),
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
    )


@pytest.mark.asyncio
async def test_discovery_aggregates_all_advertised_pages():
    fetch_page = AsyncMock(
        side_effect=[
            _page(1, 3, ["a"], total_count=3),
            _page(2, 3, ["b"], total_count=3),
            _page(3, 3, ["target"], total_count=3),
        ]
    )

    result = await fetch_all_incoming_invoice_pages(fetch_page)

    assert [item.provider_uuid for item in result.items] == ["a", "b", "target"]
    assert result.page == 1
    assert result.total_pages == 1
    assert result.total_count == 3
    assert [call.args[0] for call in fetch_page.await_args_list] == [1, 2, 3]


@pytest.mark.asyncio
async def test_discovery_single_page_does_not_overfetch():
    fetch_page = AsyncMock(return_value=_page(1, 1, ["target"], total_count=1))

    result = await fetch_all_incoming_invoice_pages(fetch_page)

    assert len(result.items) == 1
    assert result.total_pages == 1
    assert result.total_count == 1
    fetch_page.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_discovery_blocks_when_provider_exceeds_safe_page_limit():
    fetch_page = AsyncMock(return_value=_page(1, 21, ["a"], total_count=2100))

    with pytest.raises(NilveraValidationError, match="safe page limit"):
        await fetch_all_incoming_invoice_pages(fetch_page, max_pages=20)

    fetch_page.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_discovery_blocks_when_pagination_changes_mid_scan():
    fetch_page = AsyncMock(
        side_effect=[
            _page(1, 2, ["a"], total_count=2),
            _page(2, 3, ["target"], total_count=2),
        ]
    )

    with pytest.raises(NilveraValidationError, match="changed during scan"):
        await fetch_all_incoming_invoice_pages(fetch_page)
