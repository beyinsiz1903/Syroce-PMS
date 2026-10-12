from types import SimpleNamespace

import pytest

from modules.data_intelligence import guest_intelligence as module


@pytest.mark.asyncio
async def test_sentry_dict_source_and_room_type_do_not_crash_segmentation():
    result = await module.GuestSegmentationModel().segment_guest("hotel", "guest", bookings=[{
        "status": "checked_out", "total_amount": None,
        "source": {"channel": "booking"}, "room_type": {"name": "Standard"},
        "check_in": "2026-10-01", "check_out": "2026-10-02",
    }])
    assert result["preferred_booking_source"] == "booking"
    assert result["preferred_room_type"] == "Standard"


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, *_args):
        return self

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    async def to_list(self, value):
        return self.rows[:value]


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.find_calls = 0
        self.inserts = []

    def find(self, *_args, **_kwargs):
        self.find_calls += 1
        return Cursor(self.rows)

    async def insert_one(self, document):
        self.inserts.append(document)


@pytest.mark.asyncio
async def test_dashboard_bulk_loads_dependencies_and_browser_read_does_not_write(monkeypatch):
    guests = Collection([{"id": "g1", "name": "Ada", "tags": []}, {"id": "g2", "name": "Grace", "tags": []}])
    bookings = Collection([
        {"guest_id": "g1", "status": "checked_out", "total_amount": 1000, "check_in": "2026-01-01", "check_out": "2026-01-02", "room_type": "Standard"},
        {"guest_id": "g2", "status": "confirmed", "total_amount": 500, "check_in": "2099-01-01", "room_type": "Deluxe"},
    ])
    charges = Collection([{"guest_id": "g1", "amount": 100, "charge_category": "food"}])
    requests = Collection([{"guest_id": "g1"}])
    snapshots = Collection()
    logs = Collection()
    fake_db = SimpleNamespace(
        guests=guests,
        bookings=bookings,
        folio_charges=charges,
        guest_requests=requests,
        guest_intelligence_snapshots=snapshots,
        model_execution_logs=logs,
    )
    monkeypatch.setattr(module, "db", fake_db)

    result = await module.GuestIntelligenceDashboard().get_dashboard("tenant-1", 30)

    assert result["guests_analyzed"] == 2
    assert result["performance"]["strategy"] == "bulk_prefetch"
    assert result["performance"]["database_reads"] == 4
    assert guests.find_calls == bookings.find_calls == charges.find_calls == requests.find_calls == 1
    assert snapshots.inserts == []
    assert logs.inserts == []


@pytest.mark.asyncio
async def test_scheduler_run_can_persist_snapshot(monkeypatch):
    empty = Collection()
    snapshots = Collection()
    logs = Collection()
    monkeypatch.setattr(
        module,
        "db",
        SimpleNamespace(
            guests=empty,
            bookings=Collection(),
            folio_charges=Collection(),
            guest_requests=Collection(),
            guest_intelligence_snapshots=snapshots,
            model_execution_logs=logs,
        ),
    )

    await module.GuestIntelligenceDashboard().get_dashboard("tenant-1", persist_snapshot=True)

    assert len(snapshots.inserts) == 1
    assert len(logs.inserts) == 1


@pytest.mark.parametrize(
    "guest",
    [
        {"name": "QA Test Guest"},
        {"email": "profile@fixture.local"},
        {"name": "Normal Guest", "is_test": True},
    ],
)
def test_suspicious_test_guests_are_reported(guest):
    assert module._looks_like_test_guest(guest) is True


def test_real_guest_is_not_flagged_as_test_data():
    assert module._looks_like_test_guest({"name": "Ada Lovelace", "email": "ada@hotel.com"}) is False
