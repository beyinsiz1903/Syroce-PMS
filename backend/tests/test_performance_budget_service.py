import pytest

from modules.observability.distributed_tracing import TracingService
from modules.observability.performance_budget_service import PerformanceBudgetService


class _Tracing:
    def __init__(self, metrics):
        self.metrics = metrics
        self.calls = []

    async def get_path_metrics(self, *, hours, tenant_id):
        self.calls.append((hours, tenant_id))
        return self.metrics


@pytest.mark.asyncio
async def test_screen_budgets_classify_p95_error_and_missing_telemetry():
    tracing = _Tracing(
        [
            {"path": "/api/pms/dashboard", "count": 20, "errors": 0, "p95_ms": 650, "max_ms": 790},
            {"path": "/api/cashiering/city-ledger", "count": 20, "errors": 0, "p95_ms": 950, "max_ms": 1200},
            {"path": "/api/reports/finance-snapshot", "count": 5, "errors": 0, "p95_ms": 2200, "max_ms": 2500},
        ]
    )

    snapshot = await PerformanceBudgetService(tracing).get_snapshot("tenant-a", hours=6)
    screens = {screen["key"]: screen for screen in snapshot["screens"]}

    assert tracing.calls == [(6, "tenant-a")]
    assert screens["main_dashboard"]["status"] == "within_budget"
    assert screens["city_ledger"]["status"] == "warning"
    assert screens["reports"]["status"] == "breached"
    assert screens["channel_manager"]["status"] == "unknown"
    assert snapshot["summary"] == {"within_budget": 1, "warning": 1, "breached": 1, "unknown": 1}


def test_tracing_path_metrics_keep_tenants_isolated_from_local_buffer():
    tracing = TracingService()
    tracing._recent_traces.extend(
        [
            {"trace_id": "one", "tenant_id": "tenant-a", "request_path": "/api/pms/dashboard", "completed_at": "2099-01-01T00:00:00+00:00", "duration_ms": 100, "status_code": 200, "is_slow": False},
            {"trace_id": "two", "tenant_id": "tenant-b", "request_path": "/api/pms/dashboard", "completed_at": "2099-01-01T00:00:00+00:00", "duration_ms": 5000, "status_code": 500, "is_slow": True},
        ]
    )

    assert [trace["trace_id"] for trace in tracing._traces_in_window(1, tenant_id="tenant-a")] == ["one"]
