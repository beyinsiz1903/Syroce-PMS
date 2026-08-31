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
        self.pipelines = []

    def find(self, query, _projection=None):
        self.queries.append(query)
        return FakeCursor(self.rows)

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        return FakeCursor([])


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
    assert {
        "kbs_reported": True,
        "kbs_test": {"$ne": True},
        "kbs_reported_at": {
            "$gte": "2026-08-29T00:00:00",
            "$lte": "2026-08-29T23:59:59",
        },
    } in bookings.queries[0]["$or"]
    assert {
        "kbs_checkout_reported": True,
        "kbs_checkout_test": {"$ne": True},
        "kbs_checkout_reported_at": {
            "$gte": "2026-08-29T00:00:00",
            "$lte": "2026-08-29T23:59:59",
        },
    } in bookings.queries[0]["$or"]


@pytest.mark.asyncio
async def test_kbs_queue_hides_obsolete_checkin_after_verified_delivery(monkeypatch):
    from routers import kbs

    reports = FakeCollection([
        {
            "_kind": kbs.QUEUE_KIND,
            "id": "job-old-dead",
            "tenant_id": "tenant-1",
            "booking_id": "booking-109",
            "action": "checkin",
            "status": "dead",
            "payload": {"guest_name": "Burak Emiroğlu", "room_number": "109"},
            "created_at": "2026-08-30T14:33:23+00:00",
        }
    ])
    bookings = FakeCollection([
        {
            "id": "booking-109",
            "tenant_id": "tenant-1",
            "kbs_reported": True,
            "kbs_test": False,
        }
    ])
    monkeypatch.setattr(
        kbs,
        "db",
        SimpleNamespace(bookings=bookings, kbs_reports=reports),
    )

    result = await kbs.kbs_queue_list(
        status="pending,in_progress,failed,dead",
        booking_id=None,
        date_from=None,
        date_to=None,
        limit=200,
        current_user=SimpleNamespace(tenant_id="tenant-1"),
        _perm=None,
    )

    assert result["jobs"] == []
    assert result["total"] == 0
    assert bookings.queries[0]["id"] == {"$in": ["booking-109"]}
    stats_pipeline = reports.pipelines[0]
    assert any("$lookup" in stage for stage in stats_pipeline)
    assert "kbs_reported" in str(stats_pipeline)


@pytest.mark.asyncio
async def test_kbs_guests_keep_checkin_and_checkout_receipts_as_separate_sent_rows(monkeypatch):
    from routers import kbs

    bookings = FakeCollection([
        {
            "id": "booking-109",
            "guest_id": "guest-109",
            "guest_name": "Burak Emiroğlu",
            "room_number": "109",
            "check_in": "2026-08-29T14:00:00",
            "check_out": "2026-08-30T12:00:00",
            "status": "checked_out",
            "kbs_reported": True,
            "kbs_reported_at": "2026-08-29T14:05:00+00:00",
            "kbs_reference": "JANDARMA-GIRIS-109",
            "kbs_checkout_reported": True,
            "kbs_checkout_reported_at": "2026-08-30T12:10:00+00:00",
            "kbs_checkout_reference": "JANDARMA-CIKIS-109",
        }
    ])
    guests = FakeCollection([
        {
            "id": "guest-109",
            "nationality": "TR",
            "id_number": "12345678901",
            "birth_date": "",
        }
    ])
    monkeypatch.setattr(
        kbs,
        "db",
        SimpleNamespace(bookings=bookings, guests=guests, kbs_reports=FakeCollection([])),
    )
    monkeypatch.setattr(
        kbs,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2026-08-30"}),
    )

    result = await kbs.kbs_guest_list(
        date=None,
        status=None,
        limit=200,
        current_user=SimpleNamespace(tenant_id="tenant-1"),
    )

    assert [(row["id"], row["booking_id"], row["kbs_action"]) for row in result["guests"]] == [
        ("booking-109", "booking-109", "checkin"),
        ("booking-109:checkout", "booking-109", "checkout"),
    ]
    assert [row["kbs_reference"] for row in result["guests"]] == [
        "JANDARMA-GIRIS-109",
        "JANDARMA-CIKIS-109",
    ]


@pytest.mark.asyncio
async def test_kbs_queue_hides_obsolete_checkout_after_verified_delivery(monkeypatch):
    from routers import kbs

    reports = FakeCollection([
        {
            "_kind": kbs.QUEUE_KIND,
            "id": "job-old-checkout",
            "tenant_id": "tenant-1",
            "booking_id": "booking-109",
            "action": "checkout",
            "status": "dead",
            "payload": {"guest_name": "Burak Emiroğlu", "room_number": "109"},
            "created_at": "2026-08-30T15:00:00+00:00",
        }
    ])
    bookings = FakeCollection([
        {
            "id": "booking-109",
            "tenant_id": "tenant-1",
            "kbs_checkout_reported": True,
            "kbs_checkout_test": False,
        }
    ])
    monkeypatch.setattr(kbs, "db", SimpleNamespace(bookings=bookings, kbs_reports=reports))

    result = await kbs.kbs_queue_list(
        status="pending,in_progress,failed,dead",
        booking_id=None,
        date_from=None,
        date_to=None,
        limit=200,
        current_user=SimpleNamespace(tenant_id="tenant-1"),
        _perm=None,
    )

    assert result["jobs"] == []
    assert result["total"] == 0
