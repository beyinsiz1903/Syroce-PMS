"""Screen-level performance budgets built from tenant-scoped request traces."""

from __future__ import annotations

from typing import Any

SCREEN_BUDGETS: tuple[dict[str, Any], ...] = (
    {
        "key": "main_dashboard",
        "name": "Ana ekran",
        "paths": ("/api/pms/dashboard", "/api/dashboard/operational"),
        "p95_target_ms": 800,
        "p95_limit_ms": 1200,
        "error_rate_limit": 0.01,
    },
    {
        "key": "city_ledger",
        "name": "Cari hesaplar",
        "paths": ("/api/cashiering/city-ledger", "/api/reservation-detail/cari-accounts"),
        "p95_target_ms": 900,
        "p95_limit_ms": 1400,
        "error_rate_limit": 0.01,
    },
    {
        "key": "reports",
        "name": "Raporlar",
        "paths": ("/api/reports/", "/api/accounting/reports/"),
        "p95_target_ms": 1200,
        "p95_limit_ms": 2000,
        "error_rate_limit": 0.02,
    },
    {
        "key": "channel_manager",
        "name": "Kanal yöneticisi",
        "paths": ("/api/channel-manager/connections", "/api/channel-manager/sync-history", "/api/channel-manager/monitoring/"),
        "p95_target_ms": 1000,
        "p95_limit_ms": 1600,
        "error_rate_limit": 0.02,
    },
)


def _matches(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


class PerformanceBudgetService:
    """Evaluate product screen budgets without exposing another tenant's traces."""

    def __init__(self, tracing_service=None):
        if tracing_service is None:
            from modules.observability.distributed_tracing import tracing as tracing_service

        self.tracing = tracing_service

    async def get_snapshot(self, tenant_id: str, hours: int = 1) -> dict[str, Any]:
        metrics = await self.tracing.get_path_metrics(hours=hours, tenant_id=tenant_id)
        screens = []
        for budget in SCREEN_BUDGETS:
            relevant = [metric for metric in metrics if _matches(metric["path"], budget["paths"])]
            count = sum(metric["count"] for metric in relevant)
            errors = sum(metric["errors"] for metric in relevant)
            error_rate = errors / count if count else None
            p95_ms = max((metric["p95_ms"] for metric in relevant), default=None)
            max_ms = max((metric["max_ms"] for metric in relevant), default=None)
            if not count:
                status = "unknown"
            elif p95_ms > budget["p95_limit_ms"] or error_rate > budget["error_rate_limit"]:
                status = "breached"
            elif p95_ms > budget["p95_target_ms"]:
                status = "warning"
            else:
                status = "within_budget"
            screens.append(
                {
                    **budget,
                    "status": status,
                    "sample_count": count,
                    "error_count": errors,
                    "error_rate": round(error_rate, 4) if error_rate is not None else None,
                    "p95_ms": p95_ms,
                    "max_ms": max_ms,
                    "observed_paths": [metric["path"] for metric in relevant],
                }
            )
        return {
            "tenant_id": tenant_id,
            "window_hours": hours,
            "screens": screens,
            "summary": {
                "within_budget": sum(row["status"] == "within_budget" for row in screens),
                "warning": sum(row["status"] == "warning" for row in screens),
                "breached": sum(row["status"] == "breached" for row in screens),
                "unknown": sum(row["status"] == "unknown" for row in screens),
            },
        }
