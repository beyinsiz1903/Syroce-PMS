import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers.hotel_services_pkg import invoices
from routers.hotel_services_pkg._common import InvoiceItemSelection


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    def __aiter__(self):
        self._iter = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Collection:
    def __init__(self, rows=None, find_one_result=None):
        self.rows = rows or []
        self.find_one_result = find_one_result
        self.find_queries = []
        self.inserts = []

    def find(self, query, *_args):
        self.find_queries.append(query)
        return _Cursor(self.rows)

    async def find_one(self, *_args):
        return self.find_one_result

    async def insert_one(self, document):
        self.inserts.append(document)
        return SimpleNamespace(inserted_id="invoice-a")


def _fake_db():
    return SimpleNamespace(
        bookings=_Collection(
            find_one_result={
                "id": "booking-a",
                "tenant_id": "tenant-a",
                "guest_name": "Test Guest",
                "total_amount": 100.0,
                "check_in": "2026-08-15",
                "check_out": "2026-08-16",
            }
        ),
        folio_charges=_Collection(
            rows=[
                {
                    "id": "folio-charge-a",
                    "booking_id": "booking-a",
                    "tenant_id": "tenant-a",
                    "description": "Erken giris",
                    "charge_amount": 12.0,
                    "charge_category": "room_service",
                    "created_at": "2026-08-15T10:00:00Z",
                    "voided": False,
                },
                {
                    "id": "voided-charge",
                    "amount": 999.0,
                    "voided": True,
                },
            ]
        ),
        extra_charges=_Collection(
            rows=[
                {
                    "id": "extra-charge-a",
                    "booking_id": "booking-a",
                    "tenant_id": "tenant-a",
                    "description": "Minibar",
                    "total": 8.0,
                    "category": "minibar",
                    "created_at": "2026-08-15T11:00:00Z",
                    "voided": False,
                },
                {
                    "id": "folio-charge-a",
                    "description": "Duplicate migration row",
                    "amount": 12.0,
                    "voided": False,
                },
            ]
        ),
        hotel_settings=_Collection(
            find_one_result={
                "hotel_name": "Test Hotel",
                "currency_symbol": "TL",
            }
        ),
        payments=_Collection(
            rows=[
                {
                    "id": "payment-a",
                    "booking_id": "booking-a",
                    "tenant_id": "tenant-a",
                    "amount": 20.0,
                    "method": "cash",
                    "created_at": "2026-08-15T12:00:00Z",
                    "voided": False,
                },
                {
                    "id": "voided-payment",
                    "booking_id": "booking-a",
                    "tenant_id": "tenant-a",
                    "amount": 500.0,
                    "method": "cash",
                    "created_at": "2026-08-15T12:05:00Z",
                    "voided": True,
                },
            ]
        ),
        tenants=_Collection(),
        guests=_Collection(),
        invoices=_Collection(),
    )


def _user():
    return SimpleNamespace(
        id="user-a",
        tenant_id="tenant-a",
        role="manager",
        name="Test Operator",
    )


@pytest.mark.asyncio
async def test_invoice_charge_list_uses_durable_charge_collections(monkeypatch):
    database = _fake_db()
    monkeypatch.setattr(invoices, "db", database)

    result = await invoices.get_invoice_charges("booking-a", current_user=_user())

    assert [item["id"] for item in result["charges"]] == [
        "accommodation",
        "folio-charge-a",
        "extra-charge-a",
    ]
    assert [item["amount"] for item in result["charges"]] == [100.0, 12.0, 8.0]
    assert database.folio_charges.find_queries[0]["tenant_id"] == "tenant-a"
    assert database.folio_charges.find_queries[0]["voided"] == {"$ne": True}


@pytest.mark.asyncio
async def test_generated_invoice_total_matches_selected_durable_charges(monkeypatch):
    database = _fake_db()
    monkeypatch.setattr(invoices, "db", database)

    result = await invoices.generate_custom_invoice(
        "booking-a",
        InvoiceItemSelection(selected_charge_ids=["folio-charge-a", "extra-charge-a"]),
        current_user=_user(),
        _perm=None,
    )

    assert result["success"] is True
    assert result["total"] == 20.0
    assert "Erken giris" in result["invoice_html"]
    assert "Minibar" in result["invoice_html"]
    assert "Duplicate migration row" not in result["invoice_html"]
    assert database.invoices.inserts[0]["item_count"] == 2


@pytest.mark.asyncio
async def test_invoice_pdf_excludes_voided_payments(monkeypatch):
    database = _fake_db()
    monkeypatch.setattr(invoices, "db", database)

    result = await invoices.generate_invoice_pdf(
        "booking-a",
        current_user=_user(),
    )

    assert result["total_payments"] == 20.0
    assert result["balance"] == 100.0
    assert "500.00" not in result["invoice_html"]
