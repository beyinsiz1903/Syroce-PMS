"""
Channel Manager — Runtime Service
Real production-grade logic: aggregates drift, reconciliation, sync scheduler,
provider health, circuit breaker states, and credential status from live data sources.
"""
import logging
from datetime import UTC, datetime, timedelta

from common.context import OperationContext
from common.result import ServiceResult
from core.database import db

logger = logging.getLogger(__name__)


class CMRuntimeService:
    """Production CM runtime: all data from real DB/subsystem queries."""

    def __init__(self):
        self._drift = None
        self._recon = None
        self._sync = None
        self._failover = None
        self._status = None
        self._encrypt = None
        self._mask = None

        try:
            from domains.channel_manager.drift_detector import drift_detector
            self._drift = drift_detector
        except Exception:
            logger.warning("drift_detector unavailable")

        try:
            from domains.channel_manager.reconciliation_engine import reconciliation_engine
            self._recon = reconciliation_engine
        except Exception:
            logger.warning("reconciliation_engine unavailable")

        try:
            from domains.channel_manager.sync_scheduler import sync_scheduler
            self._sync = sync_scheduler
        except Exception:
            logger.warning("sync_scheduler unavailable")

        try:
            from domains.channel_manager.provider_failover import provider_failover
            self._failover = provider_failover
        except Exception:
            logger.warning("provider_failover unavailable")

        try:
            from domains.channel_manager.runtime_status import cm_runtime_status
            self._status = cm_runtime_status
        except Exception:
            logger.warning("cm_runtime_status unavailable")

        try:
            from domains.channel_manager.encryption import encrypt_credential, mask_credential
            self._encrypt = encrypt_credential
            self._mask = mask_credential
        except Exception:
            logger.warning("encryption module unavailable")

    # ── Full aggregated runtime status ──────────────────────────────

    async def get_runtime_status(self, ctx: OperationContext) -> ServiceResult:
        """Aggregate real runtime data across all CM subsystems."""
        try:
            now = datetime.now(UTC)
            tid = ctx.tenant_id

            # Provider health aggregation
            provider_health = await self._status.get_provider_health(tid)
            circuit_states = self._failover.get_all_status()
            healthy_providers = sum(1 for p in provider_health if p.get("circuit_state", {}).get("state") != "open")
            degraded_providers = sum(1 for p in provider_health if p.get("circuit_state", {}).get("state") == "half_open")
            total_providers = len(provider_health)

            # Drift latest results
            drift_scans = await db.drift_scan_results.find(
                {"tenant_id": tid}, {"_id": 0}
            ).sort("timestamp", -1).limit(5).to_list(5)
            latest_drift = drift_scans[0] if drift_scans else None
            active_drift_count = latest_drift.get("drifts_found", 0) if latest_drift else 0
            critical_drift_count = latest_drift.get("critical_drifts", 0) if latest_drift else 0

            # Reconciliation summary
            recon_results = await db.reconciliation_results.find(
                {"tenant_id": tid}, {"_id": 0, "status": 1, "auto_fixed": 1, "manual_review": 1, "reconciled_at": 1}
            ).sort("timestamp", -1).limit(5).to_list(5)
            latest_recon = recon_results[0] if recon_results else None

            # Sync stats (last 24h)
            last_24h = (now - timedelta(hours=24)).isoformat()
            total_syncs_24h = await db.channel_sync_logs.count_documents({
                "tenant_id": tid, "timestamp": {"$gte": last_24h}
            })
            failed_syncs_24h = await db.channel_sync_logs.count_documents({
                "tenant_id": tid, "timestamp": {"$gte": last_24h}, "status": "error"
            })

            # Last successful / failed sync
            last_success = await db.channel_sync_logs.find_one(
                {"tenant_id": tid, "status": {"$in": ["success", "completed"]}},
                {"_id": 0, "timestamp": 1, "connection_id": 1},
                sort=[("timestamp", -1)]
            )
            last_failure = await db.channel_sync_logs.find_one(
                {"tenant_id": tid, "status": "error"},
                {"_id": 0, "timestamp": 1, "error": 1, "connection_id": 1},
                sort=[("timestamp", -1)]
            )

            # Sync lag (time since last successful sync)
            sync_lag_seconds = None
            if last_success and last_success.get("timestamp"):
                try:
                    last_ts = datetime.fromisoformat(str(last_success["timestamp"]).replace("Z", "+00:00"))
                    sync_lag_seconds = int((now - last_ts).total_seconds())
                except (ValueError, TypeError):
                    pass

            # Active connections
            active_connections = await db.channel_connections.count_documents({
                "tenant_id": tid, "status": "active"
            })

            # Retry backlog (pending sync jobs)
            retry_backlog = await db.channel_sync_logs.count_documents({
                "tenant_id": tid, "status": "pending"
            })

            # Health calculation
            health = "healthy"
            severity = "info"
            issues = []

            if critical_drift_count > 0:
                health = "critical"
                severity = "critical"
                issues.append(f"{critical_drift_count} critical drift(s) detected")
            elif active_drift_count > 0:
                health = "degraded"
                severity = "warning"
                issues.append(f"{active_drift_count} drift issue(s) open")

            open_circuits = [p for p in circuit_states if isinstance(p, dict) and p.get("state") == "open"]
            if open_circuits:
                if health == "healthy":
                    health = "degraded"
                severity = max(severity, "warning", key=lambda s: ["info", "warning", "critical"].index(s))
                issues.append(f"{len(open_circuits)} provider circuit(s) open")

            if failed_syncs_24h > 5:
                if health == "healthy":
                    health = "degraded"
                severity = "warning"
                issues.append(f"{failed_syncs_24h} failed syncs in 24h")

            if sync_lag_seconds and sync_lag_seconds > 86400:
                severity = "critical"
                health = "critical"
                issues.append(f"Sync lag: {sync_lag_seconds // 3600}h")

            return ServiceResult.success({
                "tenant_id": tid,
                "health": health,
                "severity": severity,
                "issues": issues,
                "active_connections": active_connections,
                "providers": {
                    "total": total_providers,
                    "healthy": healthy_providers,
                    "degraded": degraded_providers,
                },
                "sync_stats": {
                    "total_24h": total_syncs_24h,
                    "failed_24h": failed_syncs_24h,
                    "success_rate": round((1 - failed_syncs_24h / max(total_syncs_24h, 1)) * 100, 1),
                    "last_sync": last_success.get("timestamp") if last_success else None,
                    "last_failed_sync": last_failure.get("timestamp") if last_failure else None,
                    "sync_lag_seconds": sync_lag_seconds,
                    "retry_backlog": retry_backlog,
                },
                "drift": {
                    "active_drifts": active_drift_count,
                    "critical_drifts": critical_drift_count,
                    "last_scan_at": latest_drift.get("scanned_at") if latest_drift else None,
                },
                "reconciliation": {
                    "status": latest_recon.get("status", "no_data") if latest_recon else "no_data",
                    "auto_fixed": latest_recon.get("auto_fixed", 0) if latest_recon else 0,
                    "manual_review": latest_recon.get("manual_review", 0) if latest_recon else 0,
                    "last_run_at": latest_recon.get("reconciled_at") if latest_recon else None,
                },
                "circuit_breakers": circuit_states,
                "checked_at": now.isoformat(),
            })
        except Exception as e:
            logger.error(f"CMRuntimeService.get_runtime_status error: {e}")
            return ServiceResult.success({
                "health": "unknown",
                "severity": "warning",
                "issues": [f"Status collection error: {str(e)[:100]}"],
                "checked_at": datetime.now(UTC).isoformat(),
            })

    async def trigger_drift_scan(self, ctx: OperationContext) -> ServiceResult:
        result = await self._drift.scan_drift(ctx.tenant_id)
        # Emit websocket event
        try:
            from websocket_server import broadcast_system_health_event
            severity = "critical" if result.get("critical_drifts", 0) > 0 else (
                "warning" if result.get("drifts_found", 0) > 0 else "info"
            )
            await broadcast_system_health_event(
                "drift_detected", result, tenant_id=ctx.tenant_id, severity=severity
            )
        except Exception:
            pass
        return ServiceResult.success(result)

    async def get_drift_issues(self, ctx: OperationContext, limit: int = 20) -> ServiceResult:
        history = await self._drift.get_drift_history(ctx.tenant_id, limit=limit)
        return ServiceResult.success({
            "tenant_id": ctx.tenant_id,
            "scans": history,
            "count": len(history),
        })

    async def run_reconciliation(self, ctx: OperationContext, auto_fix: bool = True) -> ServiceResult:
        if not self._recon:
            return ServiceResult.success({
                "status": "unavailable",
                "message": "Reconciliation engine not initialized",
                "tenant_id": ctx.tenant_id,
            })
        result = await self._recon.reconcile(ctx.tenant_id, auto_fix=auto_fix)
        try:
            from websocket_server import broadcast_system_health_event
            await broadcast_system_health_event(
                "reconciliation_completed", result, tenant_id=ctx.tenant_id, severity="info"
            )
        except Exception:
            pass
        return ServiceResult.success(result)

    async def get_reconciliation_history(self, ctx: OperationContext, limit: int = 20) -> ServiceResult:
        if not self._recon:
            return ServiceResult.success({
                "tenant_id": ctx.tenant_id,
                "results": [],
                "count": 0,
            })
        history = await self._recon.get_reconciliation_history(ctx.tenant_id, limit=limit)
        return ServiceResult.success({
            "tenant_id": ctx.tenant_id,
            "results": history,
            "count": len(history),
        })

    async def get_sync_schedule(self, ctx: OperationContext) -> ServiceResult:
        return ServiceResult.success({
            "running": self._sync._running,
            "interval_seconds": self._sync._interval_seconds,
            "tenant_id": ctx.tenant_id,
        })

    async def trigger_sync(self, ctx: OperationContext, event_type: str = "manual") -> ServiceResult:
        results = await self._sync.trigger_event_sync(
            ctx.tenant_id, event_type, {"triggered_by": ctx.actor_id}
        )
        return ServiceResult.success({"status": "triggered", "results": results})

    async def get_providers_health(self, ctx: OperationContext) -> ServiceResult:
        provider_health = await self._status.get_provider_health(ctx.tenant_id)
        return ServiceResult.success({
            "tenant_id": ctx.tenant_id,
            "providers": provider_health,
            "circuit_breakers": self._failover.get_all_status(),
        })

    async def reset_provider_circuit(self, ctx: OperationContext, provider: str) -> ServiceResult:
        self._failover.reset_breaker(provider)
        try:
            from websocket_server import broadcast_system_health_event
            await broadcast_system_health_event(
                "provider_circuit_reset", {"provider": provider}, tenant_id=ctx.tenant_id, severity="info"
            )
        except Exception:
            pass
        return ServiceResult.success({
            "status": "reset",
            "provider": provider,
            "circuit_state": self._failover.get_breaker(provider).get_status(),
        })

    async def encrypt_credential(
        self, ctx: OperationContext,
        connection_id: str, credential_key: str, credential_value: str,
    ) -> ServiceResult:
        encrypted = self._encrypt(credential_value)
        await db.channel_connections.update_one(
            {"id": connection_id, "tenant_id": ctx.tenant_id},
            {"$set": {
                f"encrypted_credentials.{credential_key}": encrypted,
                "credentials_encrypted": True,
                "credentials_updated_at": datetime.now(UTC).isoformat(),
                "credentials_updated_by": ctx.actor_id,
            }},
        )
        return ServiceResult.success({
            "status": "encrypted",
            "connection_id": connection_id,
            "credential_key": credential_key,
            "masked_value": self._mask(credential_value),
        })


cm_runtime_service = CMRuntimeService()
