from types import SimpleNamespace

import pytest

from routers import missing_endpoints_compat as central


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class _TenantCollection:
    async def find_one(self, *_args, **_kwargs):
        return {"id": "tenant-a", "chain_id": "chain-1", "hotel_name": "Otel A"}

    def find(self, *_args, **_kwargs):
        return _Cursor(
            [
                {"id": "tenant-a", "chain_id": "chain-1", "hotel_name": "Otel A"},
                {"id": "tenant-b", "chain_id": "chain-1", "hotel_name": "Otel B"},
            ]
        )


class _RowsByTenant:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, *_args, **_kwargs):
        return _Cursor(self.rows.get(query["tenant_id"], []))


class _Counts:
    def __init__(self, counts):
        self.counts = counts

    async def count_documents(self, query):
        return self.counts.get(query["tenant_id"], 0)


@pytest.mark.asyncio
async def test_central_office_dashboard_aggregates_only_chain_properties(monkeypatch):
    database = SimpleNamespace(
        tenants=_TenantCollection(),
        rooms=_RowsByTenant(
            {
                "tenant-a": [{"status": "occupied"}, {"status": "available"}],
                "tenant-b": [{"status": "occupied"}],
            }
        ),
        folio_charges=_RowsByTenant(
            {
                "tenant-a": [{"total": 100}],
                "tenant-b": [{"total": 50}],
            }
        ),
        bookings=_Counts({"tenant-a": 1, "tenant-b": 2}),
        guests=_Counts({"tenant-a": 10, "tenant-b": 20}),
    )
    monkeypatch.setattr(central, "_system_db", database)

    result = await central.central_office_dashboard(
        current_user=SimpleNamespace(tenant_id="tenant-a")
    )

    assert result["chain_kpi"] == {
        "total_properties": 2,
        "total_rooms": 3,
        "chain_occupancy_rate": 66.67,
        "today_checkins": 3,
        "total_guests": 30,
    }
    assert result["kpis"]["total_revenue_mtd"] == 150.0
    assert {row["tenant_id"] for row in result["property_breakdown"]} == {"tenant-a", "tenant-b"}
