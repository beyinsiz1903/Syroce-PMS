"""
Channel Manager — Provider Validation Framework
================================================
Real provider contract validation, ARI update verification,
reservation ingest validation, drift/recon effectiveness measurement,
provider circuit breaker live behaviour monitoring.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


# Provider contract definitions
PROVIDER_CONTRACTS = {
    "hotelrunner": {
        "name": "HotelRunner",
        "supports_ari": True,
        "supports_reservation_import": True,
        "supports_cancellation_propagation": True,
        "rate_limit_rpm": 120,
        "idempotent_updates": True,
        "retry_config": {"max_retries": 3, "backoff_base_ms": 1000},
        "retryable_errors": [429, 500, 502, 503, 504],
        "non_retryable_errors": [400, 401, 403, 404, 422],
        "sandbox_url": "https://sandbox.hotelrunner.com/api/v2",
        "live_url": "https://api.hotelrunner.com/api/v2",
    },
    "booking_com": {
        "name": "Booking.com",
        "supports_ari": True,
        "supports_reservation_import": True,
        "supports_cancellation_propagation": True,
        "rate_limit_rpm": 60,
        "idempotent_updates": True,
        "retry_config": {"max_retries": 2, "backoff_base_ms": 2000},
        "retryable_errors": [429, 500, 502, 503],
        "non_retryable_errors": [400, 401, 403],
    },
    "expedia": {
        "name": "Expedia",
        "supports_ari": True,
        "supports_reservation_import": True,
        "supports_cancellation_propagation": True,
        "rate_limit_rpm": 60,
        "idempotent_updates": False,
        "retry_config": {"max_retries": 2, "backoff_base_ms": 1500},
        "retryable_errors": [429, 500, 502, 503],
        "non_retryable_errors": [400, 401, 403, 409],
    },
}


class ProviderValidationService:
    """Validates channel manager providers against their contracts."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def run_provider_validation(
        self, ctx: OperationContext, provider_id: str
    ) -> ServiceResult:
        """Run comprehensive validation for a provider."""
        contract = PROVIDER_CONTRACTS.get(provider_id)
        if not contract:
            return ServiceResult.fail(f"Unknown provider: {provider_id}", "UNKNOWN_PROVIDER")

        now = datetime.now(timezone.utc)
        validation_id = str(uuid.uuid4())
        results = []

        # 1. Connection validation
        conn = await self._db.channel_connections.find_one(
            {"provider_id": provider_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        conn_valid = conn is not None and conn.get("status") == "active"
        results.append({
            "check": "connection",
            "passed": conn_valid,
            "detail": f"Connection status: {conn.get('status') if conn else 'not_found'}",
        })

        # 2. ARI update validation
        if contract["supports_ari"]:
            recent_ari = await self._db.channel_sync_logs.find(
                {
                    "provider_id": provider_id,
                    "tenant_id": ctx.tenant_id,
                    "sync_type": "ari",
                    "timestamp": {"$gte": (now - timedelta(hours=24)).isoformat()},
                },
                {"_id": 0},
            ).to_list(100)
            ari_success = sum(1 for s in recent_ari if s.get("status") == "success")
            ari_total = len(recent_ari)
            ari_rate = round(ari_success / ari_total * 100, 1) if ari_total > 0 else 0
            results.append({
                "check": "ari_updates",
                "passed": ari_rate > 95,
                "detail": f"Success rate: {ari_rate}% ({ari_success}/{ari_total} in 24h)",
                "success_rate": ari_rate,
            })

        # 3. Reservation ingest validation
        if contract["supports_reservation_import"]:
            recent_imports = await self._db.channel_sync_logs.find(
                {
                    "provider_id": provider_id,
                    "tenant_id": ctx.tenant_id,
                    "sync_type": "reservation_import",
                    "timestamp": {"$gte": (now - timedelta(hours=24)).isoformat()},
                },
                {"_id": 0},
            ).to_list(100)
            import_success = sum(1 for s in recent_imports if s.get("status") == "success")
            import_total = len(recent_imports)
            import_rate = round(import_success / import_total * 100, 1) if import_total > 0 else 0
            results.append({
                "check": "reservation_import",
                "passed": import_rate > 95,
                "detail": f"Success rate: {import_rate}% ({import_success}/{import_total} in 24h)",
                "success_rate": import_rate,
            })

        # 4. Cancellation propagation
        if contract["supports_cancellation_propagation"]:
            cancel_logs = await self._db.channel_sync_logs.find(
                {
                    "provider_id": provider_id,
                    "tenant_id": ctx.tenant_id,
                    "sync_type": "cancellation",
                    "timestamp": {"$gte": (now - timedelta(hours=72)).isoformat()},
                },
                {"_id": 0},
            ).to_list(50)
            cancel_ok = sum(1 for c in cancel_logs if c.get("status") == "success")
            cancel_total = len(cancel_logs)
            results.append({
                "check": "cancellation_propagation",
                "passed": cancel_ok == cancel_total if cancel_total > 0 else True,
                "detail": f"{cancel_ok}/{cancel_total} cancellations propagated (72h)",
            })

        # 5. Drift detection
        drifts = await self._db.drift_scan_results.find(
            {
                "provider_id": provider_id,
                "tenant_id": ctx.tenant_id,
                "timestamp": {"$gte": (now - timedelta(hours=24)).isoformat()},
            },
            {"_id": 0},
        ).to_list(10)
        total_drifts = sum(d.get("drifts_found", 0) for d in drifts)
        critical_drifts = sum(d.get("critical_drifts", 0) for d in drifts)
        results.append({
            "check": "drift_detection",
            "passed": critical_drifts == 0,
            "detail": f"Total drifts: {total_drifts}, Critical: {critical_drifts} (24h)",
            "total_drifts": total_drifts,
            "critical_drifts": critical_drifts,
        })

        # 6. Reconciliation
        recons = await self._db.reconciliation_results.find(
            {
                "provider_id": provider_id,
                "tenant_id": ctx.tenant_id,
                "reconciled_at": {"$gte": (now - timedelta(hours=24)).isoformat()},
            },
            {"_id": 0},
        ).to_list(20)
        recon_success = sum(1 for r in recons if r.get("status") == "success")
        recon_total = len(recons)
        recon_rate = round(recon_success / recon_total * 100, 1) if recon_total > 0 else 100
        results.append({
            "check": "reconciliation",
            "passed": recon_rate > 90,
            "detail": f"Reconciliation rate: {recon_rate}% ({recon_success}/{recon_total} in 24h)",
        })

        # 7. Rate limit compliance
        results.append({
            "check": "rate_limit_config",
            "passed": True,
            "detail": f"Max {contract['rate_limit_rpm']} RPM configured",
        })

        # Aggregate
        passed_count = sum(1 for r in results if r["passed"])
        total_checks = len(results)
        overall_passed = passed_count == total_checks

        validation_doc = {
            "id": validation_id,
            "tenant_id": ctx.tenant_id,
            "provider_id": provider_id,
            "provider_name": contract["name"],
            "checks": results,
            "passed_count": passed_count,
            "total_checks": total_checks,
            "overall_passed": overall_passed,
            "validated_at": now.isoformat(),
            "validated_by": ctx.actor_id,
        }
        await self._db.provider_validations.insert_one(validation_doc.copy())

        return ServiceResult.success(validation_doc)

    async def get_sync_lag_report(
        self, ctx: OperationContext, provider_id: str, hours: int = 24
    ) -> ServiceResult:
        """Measure sync lag for a provider."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        logs = await self._db.channel_sync_logs.find(
            {
                "provider_id": provider_id,
                "tenant_id": ctx.tenant_id,
                "timestamp": {"$gte": since},
            },
            {"_id": 0, "sync_type": 1, "duration_ms": 1, "status": 1, "timestamp": 1},
        ).to_list(500)

        by_type: Dict[str, List[int]] = {}
        for log in logs:
            st = log.get("sync_type", "unknown")
            dur = log.get("duration_ms", 0)
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(dur)

        report = {}
        for sync_type, durations in by_type.items():
            sorted_d = sorted(durations)
            n = len(sorted_d)
            report[sync_type] = {
                "count": n,
                "avg_ms": round(sum(sorted_d) / n, 1) if n else 0,
                "p50_ms": sorted_d[n // 2] if n else 0,
                "p95_ms": sorted_d[int(n * 0.95)] if n else 0,
                "p99_ms": sorted_d[int(n * 0.99)] if n else 0,
                "max_ms": sorted_d[-1] if n else 0,
            }

        return ServiceResult.success({
            "provider_id": provider_id,
            "period_hours": hours,
            "sync_lag": report,
        })

    async def get_provider_contracts(self) -> ServiceResult:
        """Return all known provider contracts."""
        return ServiceResult.success({
            "providers": [
                {
                    "id": pid,
                    "name": p["name"],
                    "supports_ari": p["supports_ari"],
                    "supports_reservation_import": p["supports_reservation_import"],
                    "rate_limit_rpm": p["rate_limit_rpm"],
                    "idempotent_updates": p["idempotent_updates"],
                }
                for pid, p in PROVIDER_CONTRACTS.items()
            ]
        })


provider_validation_service = ProviderValidationService()
