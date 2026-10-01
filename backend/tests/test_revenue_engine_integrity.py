from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from domains.revenue import central_pricing_router
from modules.revenue_management import revenue_engine


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _length):
        return self.rows


class _Collection:
    def __init__(self, rows=None, count=0):
        self.rows = rows or []
        self.count = count

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)

    async def count_documents(self, *_args, **_kwargs):
        return self.count


@pytest.mark.asyncio
async def test_rate_suggestion_fails_closed_without_configured_price(monkeypatch):
    fake_db = SimpleNamespace(
        rate_plans=_Collection(),
        room_types=_Collection(),
        rooms=_Collection(),
        bookings=_Collection(),
    )
    monkeypatch.setattr(revenue_engine, "db", fake_db)
    engine = revenue_engine.RevenueManagementEngine()
    target = (date.today() + timedelta(days=2)).isoformat()
    monkeypatch.setattr(
        engine,
        "get_occupancy_forecast",
        lambda *_args, **_kwargs: _async_value({"forecast": [{"date": target, "occupancy_pct": 0}]}),
    )

    result = await engine.calculate_ideal_adr("tenant-a", target)

    assert result["data_available"] is False
    assert result["ideal_adr"] is None
    assert result["recommendation"] == "unavailable"


@pytest.mark.asyncio
async def test_rate_suggestion_uses_target_day_occupancy(monkeypatch):
    fake_db = SimpleNamespace(
        rate_plans=_Collection([{"base_rate": 1000}]),
        room_types=_Collection(),
        rooms=_Collection(),
        bookings=_Collection(),
    )
    monkeypatch.setattr(revenue_engine, "db", fake_db)
    engine = revenue_engine.RevenueManagementEngine()
    target = (date.today() + timedelta(days=2)).isoformat()
    monkeypatch.setattr(
        engine,
        "get_occupancy_forecast",
        lambda *_args, **_kwargs: _async_value(
            {
                "forecast": [
                    {"date": date.today().isoformat(), "occupancy_pct": 0},
                    {"date": target, "occupancy_pct": 90},
                ]
            }
        ),
    )

    result = await engine.calculate_ideal_adr("tenant-a", target)

    assert result["data_available"] is True
    assert result["current_occupancy_pct"] == 90
    assert result["ideal_adr"] == 1350


@pytest.mark.asyncio
async def test_central_pricing_resolves_ids_and_merges_case_variants(monkeypatch):
    room_type_id = "b3c7bb47-4a8a-4210-aaf3-60078ecbe8cc"
    fake_db = SimpleNamespace(
        room_types=_Collection([{"id": room_type_id, "name": "Standart"}]),
        rooms=_Collection(
            [
                {"room_type": room_type_id, "base_price": 5000},
                {"room_type": "standart", "base_price": 5000},
            ]
        ),
        central_pricing_rates=_Collection(),
    )
    monkeypatch.setattr(central_pricing_router, "system_db", fake_db)

    result = await central_pricing_router._property_room_rates(
        "chain-a", {"tenant_id": "tenant-a", "property_name": "Otel A"}
    )

    assert result["data_quality_warnings"] == 0
    assert result["room_rates"] == [
        {
            "room_type": "Standart",
            "base_rate": 5000.0,
            "count": 2,
            "currency": "TRY",
            "effective_from": None,
            "provider_sync_status": "not_requested",
            "data_quality": "ok",
        }
    ]


async def _async_value(value):
    return value
