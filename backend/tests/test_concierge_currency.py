from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms import operations_router


@pytest.mark.asyncio
async def test_concierge_request_defaults_to_tenant_currency(monkeypatch):
    inserted = {}

    async def insert_one(doc):
        inserted.update(doc)

    monkeypatch.setattr(operations_router, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))
    monkeypatch.setattr(
        operations_router.db,
        "bookings",
        SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(
        operations_router.db,
        "concierge_requests",
        SimpleNamespace(insert_one=insert_one),
    )

    result = await operations_router.create_concierge_request(
        body={"type": "spa", "room_number": "101", "amount": 25},
        current_user=SimpleNamespace(tenant_id="tenant-eur", email="user@example.com"),
        _perm=None,
    )

    assert inserted["currency"] == "EUR"
    assert result["currency"] == "EUR"


def test_concierge_currency_normalizes_legacy_tl_code():
    assert operations_router._normalize_currency("TL", "EUR") == "TRY"
    assert operations_router._normalize_currency(None, "USD") == "USD"
