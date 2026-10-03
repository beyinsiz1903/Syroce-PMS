import pytest

from common.context import OperationContext
from ops.production_load_validation_service import ProductionLoadValidationService


class _Runs:
    def __init__(self):
        self.inserted = []

    async def insert_one(self, value):
        self.inserted.append(value)
        value["_id"] = "generated-id"


class _Database:
    def __init__(self):
        self.production_load_runs = _Runs()


@pytest.mark.asyncio
async def test_unconfigured_load_runner_never_creates_a_synthetic_pass(monkeypatch):
    monkeypatch.delenv("PRODUCTION_LOAD_RUNNER_URL", raising=False)
    service = object.__new__(ProductionLoadValidationService)
    service._db = _Database()
    context = OperationContext(tenant_id="tenant-a", actor_id="operator", actor_role="super_admin")

    result = await service.run_scenario(context, "ota_reservation_burst")

    assert result.ok is True
    assert result.data["status"] == "not_run"
    assert result.data["evidence_status"] == "not_configured"
    assert result.data["metrics"] == []
    assert "not a passed" in result.data["message"]


@pytest.mark.asyncio
async def test_load_scenarios_disclose_that_external_measurement_is_required(monkeypatch):
    monkeypatch.delenv("PRODUCTION_LOAD_RUNNER_URL", raising=False)
    service = object.__new__(ProductionLoadValidationService)

    result = await service.get_scenarios()

    assert result.ok is True
    assert result.data["runner_configured"] is False
    assert {item["evidence_status"] for item in result.data["scenarios"]} == {"not_configured"}
