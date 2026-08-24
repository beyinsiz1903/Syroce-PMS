from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from domains.revenue import central_pricing_router as module


class FakeCursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


def _matches(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(row, option) for option in expected):
                return False
            continue
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
        elif actual != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = [dict(row) for row in rows or []]

    async def find_one(self, query, _projection=None):
        return next((dict(row) for row in self.rows if _matches(row, query)), None)

    def find(self, query, _projection=None):
        return FakeCursor(row for row in self.rows if _matches(row, query))

    async def update_one(self, query, update, upsert=False):
        row = next((row for row in self.rows if _matches(row, query)), None)
        if row is None and upsert:
            row = dict(query)
            row.update(update.get("$setOnInsert", {}))
            self.rows.append(row)
        if row is not None:
            row.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=1 if row else 0)

    async def insert_one(self, row):
        self.rows.append(dict(row))
        return SimpleNamespace(inserted_id=row.get("id"))


class FakeSystemDB:
    def __init__(self):
        self.tenants = FakeCollection([
            {"tenant_id": "hotel-a", "chain_id": "chain-1", "hotel_name": "Otel A"},
            {"tenant_id": "hotel-b", "chain_id": "chain-1", "hotel_name": "Otel B"},
            {"tenant_id": "hotel-c", "chain_id": "chain-2", "hotel_name": "Otel C"},
        ])
        self.rooms = FakeCollection([
            {"tenant_id": "hotel-a", "room_type": "Standard", "base_price": 100, "is_active": True},
            {"tenant_id": "hotel-b", "room_type": "Standard", "base_price": 200, "is_active": True},
            {"tenant_id": "hotel-c", "room_type": "Standard", "base_price": 999, "is_active": True},
        ])
        self.central_pricing_rates = FakeCollection([])
        self.central_pricing_history = FakeCollection([])
        self.central_pricing_templates = FakeCollection([])
        self.audit_logs = FakeCollection([])


@pytest.mark.asyncio
async def test_bulk_update_is_chain_scoped_persistent_audited_and_provider_safe(monkeypatch):
    fake_db = FakeSystemDB()
    audits = []

    async def fake_audit(**kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(module, "system_db", fake_db)
    monkeypatch.setattr(module, "log_audit_event", fake_audit)
    body = module.BulkRateUpdate(
        room_type="Standard",
        new_rate=10,
        adjustment_type="percentage",
        effective_from=date(2026, 9, 1),
        reason="Sonbahar fiyat stratejisi",
    )

    result = await module.bulk_update_rates(
        body,
        current_user=SimpleNamespace(tenant_id="hotel-a", id="revenue-1", role="admin", is_chain_headquarters=True),
        _permission=None,
    )

    assert result["total_updated"] == 2
    assert result["provider_write"] is False
    assert sorted(row["new_rate"] for row in result["updates"]) == [110.0, 220.0]
    assert {row["tenant_id"] for row in fake_db.central_pricing_rates.rows} == {"hotel-a", "hotel-b"}
    assert all(row["provider_sync_status"] == "not_requested" for row in fake_db.central_pricing_rates.rows)
    assert len(fake_db.central_pricing_history.rows) == 2
    assert audits[0]["action"] == "central_pricing.bulk_updated"


def test_fixed_rate_cannot_be_negative_and_reason_is_required():
    with pytest.raises(ValidationError):
        module.BulkRateUpdate(
            room_type="Standard",
            new_rate=-1,
            adjustment_type="fixed",
            effective_from=date(2026, 9, 1),
            reason="Test",
        )
    with pytest.raises(ValidationError):
        module.BulkRateUpdate(
            room_type="Standard",
            new_rate=100,
            adjustment_type="fixed",
            effective_from=date(2026, 9, 1),
            reason="  ",
        )


@pytest.mark.asyncio
async def test_non_headquarters_property_cannot_read_chain_prices(monkeypatch):
    fake_db = FakeSystemDB()
    monkeypatch.setattr(module, "system_db", fake_db)
    with pytest.raises(Exception) as error:
        await module.get_central_rates(
            SimpleNamespace(tenant_id="hotel-b", id="user-2", role="admin", is_chain_headquarters=False)
        )
    assert getattr(error.value, "status_code", None) == 403
