from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.schemas import PreventiveMaintenancePlan


@pytest.mark.asyncio
async def test_create_plan_rejects_unknown_tenant_asset(monkeypatch):
    import domains.pms.maintenance_router as maintenance

    class Assets:
        async def find_one(self, query, projection):
            assert query == {"tenant_id": "tenant-A", "id": "missing-asset"}
            return None

    monkeypatch.setattr(maintenance, "db", SimpleNamespace(maintenance_assets=Assets()))
    user = SimpleNamespace(tenant_id="tenant-A", id="user-A")
    plan = PreventiveMaintenancePlan(
        asset_id="missing-asset",
        frequency_type="months",
        frequency_value=1,
        next_due_date=datetime.now(UTC) + timedelta(days=30),
    )

    with pytest.raises(HTTPException) as exc:
        await maintenance.create_preventive_plan(data=plan, current_user=user)

    assert exc.value.status_code == 400
    assert exc.value.detail == "MAINTENANCE_ASSET_NOT_FOUND"


@pytest.mark.asyncio
async def test_scheduler_skips_plan_with_missing_asset(monkeypatch):
    import domains.pms.maintenance_router as maintenance

    class PlansCursor:
        def __init__(self):
            self.items = iter([
                {
                    "id": "plan-1",
                    "asset_id": "missing-asset",
                    "frequency_type": "months",
                    "frequency_value": 1,
                    "is_active": True,
                }
            ])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.items)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class Plans:
        def find(self, query, projection):
            return PlansCursor()

    class Assets:
        async def find_one(self, query, projection):
            return None

    class WorkOrders:
        async def insert_one(self, payload):
            raise AssertionError("missing-asset plan must not create a work order")

    monkeypatch.setattr(
        maintenance,
        "db",
        SimpleNamespace(
            maintenance_assets=Assets(),
            maintenance_plans=Plans(),
            maintenance_work_orders=WorkOrders(),
        ),
    )
    user = SimpleNamespace(tenant_id="tenant-A", id="user-A", role="super_admin")

    result = await maintenance.run_preventive_maintenance_scheduler(current_user=user)

    assert result["created_count"] == 0
    assert result["skipped_count"] == 1
