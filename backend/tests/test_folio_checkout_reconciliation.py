from types import SimpleNamespace

import pytest

from core.folio_checkout_reconciliation import reconcile_unposted_room_charge


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.inserted = []
        self.updates = []

    def find(self, *_args, **_kwargs):
        return Cursor(self.rows)

    async def find_one(self, query, *_args, **_kwargs):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None

    async def insert_one(self, row, **_kwargs):
        self.rows.append(dict(row))
        self.inserted.append(dict(row))

    async def update_one(self, query, update, **_kwargs):
        self.updates.append((query, update))


def database(charges=(), payments=(), folios=()):
    return SimpleNamespace(
        folio_charges=Collection(charges),
        payments=Collection(payments),
        folios=Collection(folios),
    )


@pytest.mark.asyncio
async def test_checkout_reconciliation_posts_only_the_unposted_room_remainder():
    db = database(
        charges=[
            {
                "id": "night-1",
                "charge_type": "room_charge",
                "charge_category": "room",
                "total": 5833.34,
                "tax_amount": 625.0,
                "voided": False,
            }
        ],
        payments=[{"amount": 7500.0, "voided": False}],
        folios=[{"id": "folio-1", "tenant_id": "tenant-1", "booking_id": "booking-1", "status": "open"}],
    )

    result = await reconcile_unposted_room_charge(
        db,
        tenant_id="tenant-1",
        booking={"id": "booking-1", "total_amount": 7500.0, "check_out": "2026-09-04"},
        posted_by="checkout:operator",
    )

    assert result["posted"] is True
    assert result["amount"] == 1666.66
    posted = db.folio_charges.inserted[0]
    assert posted["total"] == 1666.66
    assert posted["source"] == "checkout_room_reconciliation"
    assert posted["folio_id"] == "folio-1"
    assert db.folios.updates[-1][1] == {"$set": {"balance": 0.0}}


@pytest.mark.asyncio
async def test_checkout_reconciliation_is_idempotent():
    key = "checkout-room-reconciliation:tenant-1:booking-1"
    db = database(
        charges=[{"id": "existing", "idempotency_key": key, "total": 1666.66, "voided": False}],
        folios=[{"id": "folio-1", "tenant_id": "tenant-1", "booking_id": "booking-1", "status": "open"}],
    )

    result = await reconcile_unposted_room_charge(
        db,
        tenant_id="tenant-1",
        booking={"id": "booking-1", "total_amount": 7500.0},
        posted_by="checkout:operator",
    )

    assert result == {"posted": False, "idempotent": True, "charge_id": "existing", "amount": 1666.66}
    assert db.folio_charges.inserted == []
