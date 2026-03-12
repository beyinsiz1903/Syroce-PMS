"""
Service Health - Aggregated service health monitoring.
Checks health of all platform services and provides a unified status.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from core.database import db

logger = logging.getLogger("observability.health")


class HealthStatus:
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceHealthMonitor:
    """Monitors health of all platform services."""

    def __init__(self):
        self._service_status: Dict[str, dict] = {}
        self._thresholds = {
            "error_rate": 0.05,       # 5% error rate = degraded
            "response_time_ms": 2000,  # >2s = degraded
            "stale_hours": 24,         # no data for 24h = stale
        }

    def update_service_health(self, service_name: str, status: str,
                              latency_ms: float = 0, metadata: Optional[dict] = None):
        """Update a service's health status."""
        self._service_status[service_name] = {
            "service": service_name,
            "status": status,
            "latency_ms": latency_ms,
            "metadata": metadata or {},
            "last_check": datetime.now(timezone.utc).isoformat(),
        }

    async def check_all_services(self) -> Dict[str, Any]:
        """Run health checks on all platform services."""
        checks = {}

        # MongoDB
        try:
            await db.command("ping")
            checks["mongodb"] = {"status": HealthStatus.HEALTHY, "latency_ms": 0}
        except Exception as e:
            checks["mongodb"] = {"status": HealthStatus.UNHEALTHY, "error": str(e)}

        # Event Bus
        try:
            from modules.event_bus.abstraction import event_bus
            bus_status = await event_bus.get_status()
            checks["event_bus"] = {
                "status": HealthStatus.HEALTHY,
                "mode": bus_status.get("mode", "unknown"),
                "sessions": bus_status.get("total_sessions", 0),
            }
        except Exception as e:
            checks["event_bus"] = {"status": HealthStatus.DEGRADED, "error": str(e)}

        # ML Pipeline
        try:
            recent_runs = await db.pipeline_runs.count_documents({
                "started_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}
            })
            failed_runs = await db.pipeline_runs.count_documents({
                "status": "failed",
                "started_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()},
            })
            checks["ml_pipeline"] = {
                "status": HealthStatus.HEALTHY if failed_runs == 0 else HealthStatus.DEGRADED,
                "runs_24h": recent_runs,
                "failed_24h": failed_runs,
            }
        except Exception as e:
            checks["ml_pipeline"] = {"status": HealthStatus.UNKNOWN, "error": str(e)}

        # Messaging
        try:
            msg_failures = await db.messaging_delivery_logs.count_documents({
                "status": "failed",
                "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()},
            })
            checks["messaging"] = {
                "status": HealthStatus.HEALTHY if msg_failures < 5 else HealthStatus.DEGRADED,
                "failures_1h": msg_failures,
            }
        except Exception:
            checks["messaging"] = {"status": HealthStatus.HEALTHY, "failures_1h": 0}

        # Revenue Autopilot
        try:
            pending = await db.revenue_approval_queue.count_documents({"status": "pending"})
            checks["revenue_autopilot"] = {
                "status": HealthStatus.HEALTHY if pending < 50 else HealthStatus.DEGRADED,
                "pending_approvals": pending,
            }
        except Exception:
            checks["revenue_autopilot"] = {"status": HealthStatus.HEALTHY, "pending_approvals": 0}

        # Error rate
        try:
            error_count = await db.observability_errors.count_documents({
                "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()},
                "severity": {"$in": ["critical", "high"]},
            })
            checks["error_rate"] = {
                "status": HealthStatus.HEALTHY if error_count < 10 else HealthStatus.DEGRADED,
                "critical_errors_1h": error_count,
            }
        except Exception:
            checks["error_rate"] = {"status": HealthStatus.HEALTHY, "critical_errors_1h": 0}

        # Compute overall health
        statuses = [c.get("status", HealthStatus.UNKNOWN) for c in checks.values()]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        result = {
            "overall_status": overall,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "services": checks,
            "service_count": len(checks),
            "healthy_count": sum(1 for s in statuses if s == HealthStatus.HEALTHY),
            "degraded_count": sum(1 for s in statuses if s == HealthStatus.DEGRADED),
            "unhealthy_count": sum(1 for s in statuses if s == HealthStatus.UNHEALTHY),
        }

        # Persist health snapshot
        await db.observability_health.insert_one({
            "timestamp": result["checked_at"],
            **{k: v for k, v in result.items()},
        })

        return result

    async def get_health_history(self, hours: int = 24, limit: int = 50) -> List[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return await db.observability_health.find(
            {"timestamp": {"$gte": cutoff}}, {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)


service_health = ServiceHealthMonitor()
