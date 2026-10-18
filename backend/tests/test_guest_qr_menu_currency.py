import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from domains.pms.pos_fnb_router import guest_menu


def _cursor(rows):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    return cursor


def _guest_menu_db(items, *, outlet=True, table=True):
    """Create the minimal public QR menu datastore with outlet/table ownership."""
    outlets = MagicMock()
    outlets.find_one = AsyncMock(return_value={"id": "outlet-1"} if outlet else None)
    tables = MagicMock()
    tables.find_one = AsyncMock(return_value={"id": "table-1"} if table else None)
    rules = MagicMock()
    rules.find.return_value.sort.return_value = _cursor([])
    return SimpleNamespace(pos_menu_items=items, pos_outlets=outlets, table_layouts=tables,
                           pos_happy_hour_rules=rules)


@pytest.mark.asyncio
async def test_public_menu_exposes_tenant_currency_and_enriches_legacy_items(monkeypatch):
    items = MagicMock()
    items.find.return_value = _cursor(
        [
            {
                "id": "coffee",
                "item_name": "Kahve",
                "category": "İçecek",
                "unit_price": 4,
            }
        ]
    )
    monkeypatch.setattr(guest_menu, "db", _guest_menu_db(items))
    monkeypatch.setattr(
        guest_menu,
        "get_tenant_currency",
        AsyncMock(return_value=("EUR", "€")),
    )

    result = await guest_menu.get_guest_menu("tenant-eur", "outlet-1")

    assert result["currency"] == "EUR"
    assert result["categories"][0]["items"][0]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_empty_public_menu_still_exposes_tenant_currency(monkeypatch):
    items = MagicMock()
    items.find.return_value = _cursor([])
    monkeypatch.setattr(guest_menu, "db", _guest_menu_db(items))
    monkeypatch.setattr(
        guest_menu,
        "get_tenant_currency",
        AsyncMock(return_value=("USD", "$")),
    )

    result = await guest_menu.get_guest_menu("tenant-usd", "outlet-1")

    assert result == {"categories": [], "currency": "USD"}


@pytest.mark.asyncio
async def test_public_menu_does_not_relabel_foreign_currency_items(monkeypatch):
    items = MagicMock()
    items.find.return_value = _cursor(
        [
            {"id": "coffee", "item_name": "Kahve", "unit_price": 4, "currency": "EUR"},
            {"id": "tea", "item_name": "Çay", "unit_price": 5, "currency": "USD"},
        ]
    )
    monkeypatch.setattr(guest_menu, "db", _guest_menu_db(items))
    monkeypatch.setattr(
        guest_menu,
        "get_tenant_currency",
        AsyncMock(return_value=("EUR", "€")),
    )

    result = await guest_menu.get_guest_menu('tenant-eur', 'outlet-1')
    assert [item['id'] for category in result['categories'] for item in category['items']] == ['coffee']
