"""
Channel Manager — Runtime Service
Orchestrates drift detection, reconciliation, sync scheduling,
provider health, and credential management. No FastAPI dependencies.
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from common.context import OperationContext
from common.result import ServiceResult


class CMRuntimeService:
    """Business logic for channel manager runtime operations."""

    def __init__(self):
        from domains.channel_manager.drift_detector import drift_detector
        from domains.channel_manager.reconciliation_engine import reconciliation_engine
        from domains.channel_manager.sync_scheduler import sync_scheduler
        from domains.channel_manager.provider_failover import provider_failover
        from domains.channel_manager.runtime_status import cm_runtime_status
        from domains.channel_manager.encryption import encrypt_credential, mask_credential
        self._drift = drift_detector
        self._recon = reconciliation_engine
        self._sync = sync_scheduler
        self._failover = provider_failover
        self._status = cm_runtime_status
        self._encrypt = encrypt_credential
        self._mask = mask_credential

    async def get_runtime_status(self, ctx: OperationContext) -> ServiceResult:
        data = await self._status.get_status(ctx.tenant_id)
        return ServiceResult.success(data)

    async def trigger_drift_scan(self, ctx: OperationContext) -> ServiceResult:
        result = await self._drift.scan_drift(ctx.tenant_id)
        return ServiceResult.success(result)

    async def get_drift_issues(self, ctx: OperationContext, limit: int = 20) -> ServiceResult:
        history = await self._drift.get_drift_history(ctx.tenant_id, limit=limit)
        return ServiceResult.success({
            "tenant_id": ctx.tenant_id,
            "scans": history,
            "count": len(history),
        })

    async def run_reconciliation(self, ctx: OperationContext, auto_fix: bool = True) -> ServiceResult:
        result = await self._recon.reconcile(ctx.tenant_id, auto_fix=auto_fix)
        return ServiceResult.success(result)

    async def get_reconciliation_history(self, ctx: OperationContext, limit: int = 20) -> ServiceResult:
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
        return ServiceResult.success({
            "status": "reset",
            "provider": provider,
            "circuit_state": self._failover.get_breaker(provider).get_status(),
        })

    async def encrypt_credential(
        self, ctx: OperationContext,
        connection_id: str, credential_key: str, credential_value: str,
    ) -> ServiceResult:
        from core.database import db
        encrypted = self._encrypt(credential_value)
        await db.channel_connections.update_one(
            {"id": connection_id, "tenant_id": ctx.tenant_id},
            {"$set": {
                f"encrypted_credentials.{credential_key}": encrypted,
                "credentials_encrypted": True,
                "credentials_updated_at": datetime.now(timezone.utc).isoformat(),
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
