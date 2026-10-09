from types import SimpleNamespace

import pytest

from modules.data_intelligence import guest_intelligence as module


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
