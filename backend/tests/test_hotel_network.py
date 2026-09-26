from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from routers.hotel_network import (
    NetworkContractCreate,
    NetworkRequestCreate,
    _post_interhotel_ledger,
    _tenant,
)


class InsertManyCollection:
    def __init__(self):
        self.documents = []

    async def insert_many(self, documents):
        self.documents.extend(documents)


@pytest.mark.asyncio
async def test_interhotel_ledger_creates_balanced_pair():
    ledger = InsertManyCollection()
    sysdb = SimpleNamespace(hotel_network_ledger=ledger)
    request = {
        "id": "request-12345678", "source_tenant_id": "hotel-a",
        "target_tenant_id": "hotel-b", "source_booking_id": "source-booking",
        "total_amount": 10_000, "commission_pct": 10, "collect_by": "source_hotel",
    }

    rows = await _post_interhotel_ledger(sysdb, request, {"id": "target-booking"})

    assert len(rows) == 2
    assert {row["entry_type"] for row in rows} == {"payable", "receivable"}
    assert {row["amount"] for row in rows} == {9_000}
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
