from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self._index = 0

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    async def to_list(self, _length):
        return [dict(row) for row in self.rows]

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.rows):
            raise StopAsyncIteration
        row = dict(self.rows[self._index])
        self._index += 1
        return row


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, _projection=None):
        self.queries.append(query)
        return FakeCursor(self.rows)


@pytest.mark.asyncio
async def test_kbs_guests_use_pms_business_date_and_canonical_tc_identity(monkeypatch):
    from routers import kbs

    bookings = FakeCollection([
        {
            "id": "booking-110",
            "guest_id": "guest-110",
            "guest_name": "Abdulhakim Tavlasoğlu",
            "room_number": "110",
            "check_in": "2026-08-28T14:00:00",
            "check_out": "2026-08-30T12:00:00",
            "status": "checked_in",
            "kbs_reported": True,
            "kbs_reported_at": "2026-08-29T12:30:00+00:00",
            "kbs_reference": "JANDARMA-MusteriKimlikNoGiris-123",
        }
    ])
    guests = FakeCollection([
        {
            "id": "guest-110",
            "nationality": "TR",
            "id_number": "12345678901",
            "birth_date": "",
        }
    ])
    reports = FakeCollection([])
    monkeypatch.setattr(
        kbs,
        "db",
        SimpleNamespace(bookings=bookings, guests=guests, kbs_reports=reports),
    )
    monkeypatch.setattr(
        kbs,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2026-08-29"}),
    )

    result = await kbs.kbs_guest_list(
        date=None,
        status=None,
        limit=200,
        current_user=SimpleNamespace(tenant_id="tenant-1"),
    )

    assert result["date"] == "2026-08-29"
    assert result["guests"][0]["id_number"] == "12345678901"
    assert result["guests"][0]["birth_date"] == ""
    assert result["guests"][0]["kbs_ready"] is True
    assert result["guests"][0]["kbs_status"] == "sent"
    assert result["guests"][0]["kbs_sent_at"] == "2026-08-29T12:30:00+00:00"
    assert result["guests"][0]["kbs_reference"] == "JANDARMA-MusteriKimlikNoGiris-123"
    checked_in_window = bookings.queries[0]["$or"][0]
    assert checked_in_window == {
        "status": "checked_in",
        "check_in": {"$lte": "2026-08-29T23:59:59"},
        "check_out": {"$gte": "2026-08-29T00:00:00"},
    }
