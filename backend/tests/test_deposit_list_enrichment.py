from types import SimpleNamespace
from unittest.mock import patch

import pytest

from routers.reservation_detail import list_all_deposits


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


class Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, _projection):
        if "id" in query and isinstance(query["id"], dict):
            ids = set(query["id"]["$in"])
            rows = [row for row in self.rows if row.get("id") in ids and row.get("tenant_id") == query.get("tenant_id")]
        else:
            rows = [row for row in self.rows if row.get("tenant_id") == query.get("tenant_id")]
        return Cursor(rows)


@pytest.mark.asyncio
async def test_deposit_list_uses_canonical_guest_and_preserves_currency():
    fake_db = SimpleNamespace(
        deposits=Collection([
            {"id": "dep-1", "tenant_id": "tenant-1", "booking_id": "book-1", "amount": 100},
        ]),
        bookings=Collection([
            {"id": "book-1", "tenant_id": "tenant-1", "guest_id": "guest-1", "guest_name": "", "room_number": "204", "currency": "eur"},
        ]),
        guests=Collection([
            {"id": "guest-1", "tenant_id": "tenant-1", "name": "Ayşe Yılmaz"},
        ]),
    )

    with patch("routers.reservation_detail.db", fake_db):
        result = await list_all_deposits(SimpleNamespace(tenant_id="tenant-1"))

    assert result["deposits"] == [{
        "id": "dep-1",
        "tenant_id": "tenant-1",
        "booking_id": "book-1",
        "amount": 100,
        "guest_name": "Ayşe Yılmaz",
        "room_number": "204",
        "currency": "EUR",
    }]


@pytest.mark.asyncio
async def test_orphan_deposit_never_returns_blank_guest_or_currency():
    fake_db = SimpleNamespace(
        deposits=Collection([{"id": "dep-2", "tenant_id": "tenant-1", "amount": 50}]),
        bookings=Collection([]),
        guests=Collection([]),
    )

    with patch("routers.reservation_detail.db", fake_db):
        result = await list_all_deposits(SimpleNamespace(tenant_id="tenant-1"))

    assert result["deposits"][0]["guest_name"] == "Walk-in Misafir"
    assert result["deposits"][0]["currency"] == "TRY"
