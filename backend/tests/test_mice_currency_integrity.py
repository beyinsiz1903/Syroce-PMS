from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import function_space_router
from routers import mice, sales_catering


class _CatalogCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *_args, **_kwargs):
        return next(
            (
                doc
                for doc in self.docs
                if doc.get("id") == query.get("id") and doc.get("tenant_id") == query.get("tenant_id")
            ),
            None,
        )


class _EventCollection(_CatalogCollection):
    def __init__(self, docs=None):
        super().__init__(docs)
        self.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))


def _event_input(**overrides):
    data = {
        "name": "EUR Kongresi",
        "client_name": "Örnek A.Ş.",
        "currency": "eur",
        "start_date": date(2027, 1, 1),
        "end_date": date(2027, 1, 2),
    }
    data.update(overrides)
    return mice.EventIn(**data)


def test_event_contract_preserves_currency():
    assert _event_input().currency == "eur"


@pytest.mark.asyncio
async def test_catalog_and_sales_defaults_follow_tenant_currency(monkeypatch):
    tenant_currency = AsyncMock(return_value=("EUR", "€"))
    monkeypatch.setattr(mice, "get_tenant_currency", tenant_currency)
    monkeypatch.setattr(sales_catering, "get_tenant_currency", tenant_currency)

    menu = await mice._currency_payload(mice.MenuPackageIn(name="Kongre Menüsü"), "tenant-1")
    opportunity = await sales_catering._currency_payload(
        sales_catering.OpportunityIn(title="Avrupa Kongresi"),
        "tenant-1",
    )

    assert menu["currency"] == "EUR"
    assert opportunity["currency"] == "EUR"


@pytest.mark.asyncio
async def test_function_space_defaults_to_tenant_currency(monkeypatch):
    collection = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(
        function_space_router,
        "get_system_db",
        lambda: SimpleNamespace(function_rooms=collection),
    )
    monkeypatch.setattr(
        function_space_router,
        "get_tenant_currency",
        AsyncMock(return_value=("EUR", "€")),
    )

    room = await function_space_router.create_room(
        function_space_router.FunctionRoom(name="Avrupa Salonu", capacity=100),
        SimpleNamespace(tenant_id="tenant-1", email="test@example.com"),
    )

    assert room["currency"] == "EUR"
    assert collection.insert_one.await_args.args[0]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_resource_catalog_rejects_mixed_currency(monkeypatch):
    fake_db = SimpleNamespace(
        mice_menus=_CatalogCollection(
            [
                {
                    "id": "menu-usd",
                    "tenant_id": "tenant-1",
                    "name": "USD Menü",
                    "price_per_person": 25,
                    "currency": "USD",
                }
            ]
        ),
        mice_resources=_CatalogCollection(),
    )
    monkeypatch.setattr(mice, "get_system_db", lambda: fake_db)

    with pytest.raises(HTTPException) as exc:
        await mice._expand_resource_prices(
            "tenant-1",
            [{"menu_id": "menu-usd", "name": "USD Menü", "quantity": 1}],
            20,
            "EUR",
            "EUR",
        )

    assert exc.value.status_code == 409
    assert "USD" in exc.value.detail
    assert "EUR" in exc.value.detail


@pytest.mark.asyncio
async def test_resource_catalog_carries_event_currency(monkeypatch):
    fake_db = SimpleNamespace(
        mice_menus=_CatalogCollection(
            [
                {
                    "id": "menu-eur",
                    "tenant_id": "tenant-1",
                    "name": "Kongre Menüsü",
                    "price_per_person": 30,
                    "currency": "EUR",
                }
            ]
        ),
        mice_resources=_CatalogCollection(),
    )
    monkeypatch.setattr(mice, "get_system_db", lambda: fake_db)

    lines = await mice._expand_resource_prices(
        "tenant-1",
        [{"menu_id": "menu-eur", "name": "", "quantity": 1}],
        10,
        "EUR",
        "EUR",
    )

    assert lines[0]["currency"] == "EUR"
    assert lines[0]["unit_price"] == 30
    assert lines[0]["quantity"] == 10


def test_beo_print_uses_event_currency_instead_of_lira_symbol():
    html = mice._beo_html(
        {
            "event": {
                "name": "Avrupa Kongresi",
                "currency": "EUR",
                "totals": {"space_total": 100, "resources_total": 50, "grand_total": 150},
            }
        }
    )

    assert "150.00 EUR" in html
    assert "₺" not in html


@pytest.mark.asyncio
async def test_foreign_beo_gl_post_requires_rate(monkeypatch):
    event = {
        "id": "event-1",
        "tenant_id": "tenant-1",
        "status": "confirmed",
        "end_date": "2027-01-02",
        "currency": "EUR",
        "totals": {"grand_total": 100},
    }
    fake_db = SimpleNamespace(mice_events=_EventCollection([event]))
    monkeypatch.setattr(mice, "get_system_db", lambda: fake_db)
    monkeypatch.setattr(mice, "require_finance", lambda _user: None)
    monkeypatch.setattr(mice, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))

    with pytest.raises(HTTPException) as exc:
        await mice.post_beo_to_folio(
            "event-1",
            payload=None,
            current_user=SimpleNamespace(tenant_id="tenant-1", id="user-1"),
            _perm=None,
        )

    assert exc.value.status_code == 409
    assert "TRY muhasebe kuru" in exc.value.detail


@pytest.mark.asyncio
async def test_foreign_beo_gl_post_preserves_foreign_metadata(monkeypatch):
    event = {
        "id": "event-1",
        "tenant_id": "tenant-1",
        "status": "confirmed",
        "end_date": "2027-01-02",
        "currency": "EUR",
        "totals": {"grand_total": 100},
    }
    fake_db = SimpleNamespace(mice_events=_EventCollection([event]))
    posted = AsyncMock(return_value={"id": "journal-1"})
    monkeypatch.setattr(mice, "get_system_db", lambda: fake_db)
    monkeypatch.setattr(mice, "require_finance", lambda _user: None)
    monkeypatch.setattr(mice, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))
    monkeypatch.setattr(mice, "post_journal_entry", posted)

    result = await mice.post_beo_to_folio(
        "event-1",
        payload=mice.BeoGLPostIn(exchange_rate=40),
        current_user=SimpleNamespace(tenant_id="tenant-1", id="user-1"),
        _perm=None,
    )

    lines = posted.await_args.kwargs["lines"]
    assert lines[0]["debit"] == 4000
    assert lines[0]["currency"] == "EUR"
    assert lines[0]["foreign_amount"] == 100
    assert lines[0]["exchange_rate"] == 40
    assert result["base_amount_try"] == 4000
