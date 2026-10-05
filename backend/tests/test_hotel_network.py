from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import routers.hotel_network as hotel_network
from routers.hotel_network import (
    NetworkContractCreate,
    NetworkRequestCreate,
    _financial_transfer_block_message,
    _post_interhotel_ledger,
    _source_booking_financial_activity,
    _tenant,
)


class InsertManyCollection:
    def __init__(self):
        self.documents = []

    async def insert_many(self, documents):
        self.documents.extend(documents)


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class FinancialCollection:
    def __init__(self, record=None, rows=None):
        self.record = record
        self.rows = rows or []

    def find(self, *_args, **_kwargs):
        return Cursor(self.rows)

    async def find_one(self, *_args, **_kwargs):
        return self.record


@pytest.mark.asyncio
async def test_interhotel_ledger_creates_balanced_pair():
    ledger = InsertManyCollection()
    sysdb = SimpleNamespace(hotel_network_ledger=ledger)
    request = {
        "id": "request-12345678", "source_tenant_id": "hotel-a",
        "target_tenant_id": "hotel-b", "source_booking_id": "source-booking",
        "total_amount": 10_000, "currency": "EUR", "commission_pct": 10,
        "collect_by": "source_hotel",
    }

    rows = await _post_interhotel_ledger(sysdb, request, {"id": "target-booking"})

    assert len(rows) == 2
    assert {row["entry_type"] for row in rows} == {"payable", "receivable"}
    assert {row["amount"] for row in rows} == {9_000}
    assert {row["currency"] for row in rows} == {"EUR"}
    assert len({row["transfer_reference"] for row in rows}) == 1
    assert rows[0]["tenant_id"] == rows[1]["counterparty_tenant_id"]


def test_request_requires_every_child_age():
    with pytest.raises(ValidationError):
        NetworkRequestCreate(
            listing_id="listing", check_in="2026-10-01", check_out="2026-10-02",
            guest_name="Test Guest", adults=2, children=2, child_ages=[7],
        )


def test_contract_rejects_invalid_date_range():
    with pytest.raises(ValidationError):
        NetworkContractCreate(
            partner_tenant_id="hotel-b", valid_from="2026-10-02", valid_to="2026-10-01"
        )


def test_hotel_context_is_required():
    with pytest.raises(Exception) as error:
        _tenant(SimpleNamespace(tenant_id=None))
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_source_booking_financial_activity_detects_posted_charge(monkeypatch):
    monkeypatch.setattr(
        hotel_network,
        "db",
        SimpleNamespace(
            folios=FinancialCollection(rows=[{"id": "folio-1"}]),
            payments=FinancialCollection(),
            folio_charges=FinancialCollection({"id": "charge-1"}),
            invoices=FinancialCollection(),
        ),
    )

    activity = await _source_booking_financial_activity("hotel-a", "booking-a")

    assert activity == ["tahakkuk"]
    assert "tahakkuk bulundu" in _financial_transfer_block_message(activity)
