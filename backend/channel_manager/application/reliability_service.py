"""
Connector Reliability Monitoring Service — Phase 4.

Metrics: uptime, MTTR, MTBF, sync success rate, ack success rate, retry rate,
         provider latency, error frequency, mapping validation rate, recon frequency.
Analysis: failure pattern detection, unstable/degraded classification, outage windows.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db

from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.reliability")


class ReliabilityService:
    """Calculates reliability metrics for each connector."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    async def get_reliability(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Get comprehensive reliability metrics for a connector."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector not found"}

        jobs = await self._repo.get_sync_jobs(tenant_id, connector_id, limit=200)
        total_jobs = len(jobs)
        succeeded = [j for j in jobs if j.get("status") == "succeeded"]
        failed = [j for j in jobs if j.get("status") == "failed"]

        # ─── Basic Rates ───
        sync_success_rate = round(len(succeeded) / max(total_jobs, 1) * 100, 1)
        retry_jobs = [j for j in jobs if j.get("retry_count", 0) > 0]
        retry_rate = round(len(retry_jobs) / max(total_jobs, 1) * 100, 1)

        # ─── ACK rate ───
        total_imports = await db.cm_imported_reservations.count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id}
        )
        ack_sent = await db.cm_imported_reservations.count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id, "ack_status": "ack_sent"}
        )
        ack_success_rate = round(ack_sent / max(total_imports, 1) * 100, 1)

        # ─── Mapping rate ───
        mappings = await self._repo.get_mappings(tenant_id, connector_id)
        valid_mappings = sum(1 for m in mappings if m.get("validation_status") != "invalid")
        mapping_rate = round(valid_mappings / max(len(mappings), 1) * 100, 1)

        # ─── MTBF & MTTR ───
        mtbf, mttr = self._calculate_mtbf_mttr(jobs)

        # ─── Uptime ───
        uptime = self._calculate_uptime(connector, jobs)

        # ─── Failure Patterns ───
        patterns = self._detect_failure_patterns(jobs)

        # ─── Recon frequency ───
        recon_summary = await self._repo.get_reconciliation_summary(tenant_id, connector_id)

        # ─── Reservation Import Metrics ───
        import_total = await db.cm_imported_reservations.count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id}
        )
        import_failed = await db.cm_imported_reservations.count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id, "import_status": "failed"}
        )
        import_review = await db.cm_imported_reservations.count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id, "import_status": {"$in": ["review", "conflict", "out_of_order"]}}
        )
        import_success_rate = round(
            (import_total - import_failed - import_review) / max(import_total, 1) * 100, 1
        )

        # ─── Classification ───
        classification = self._classify_connector(sync_success_rate, uptime, mttr, len(failed), import_success_rate)

        return {
            "connector_id": connector_id,
            "property_id": connector.get("property_id", ""),
            "provider": connector.get("provider", ""),
            "display_name": connector.get("display_name", ""),
            "status": connector.get("status", ""),
            "uptime_percentage": uptime,
            "mtbf_hours": mtbf,
            "mttr_hours": mttr,
            "sync_success_rate": sync_success_rate,
            "ack_success_rate": ack_success_rate,
            "retry_rate": retry_rate,
            "mapping_validation_rate": mapping_rate,
            "total_sync_jobs": total_jobs,
            "total_succeeded": len(succeeded),
            "total_failed": len(failed),
            "total_retries": len(retry_jobs),
            "recon_open_issues": recon_summary.get("total_open", 0),
            "import_total": import_total,
            "import_failed": import_failed,
            "import_review": import_review,
            "import_success_rate": import_success_rate,
            "failure_patterns": patterns,
            "classification": classification,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_all_reliability(self, tenant_id: str) -> Dict[str, Any]:
        """Get reliability metrics for all connectors."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        results = []
        for c in connectors:
            r = await self.get_reliability(tenant_id, c["id"])
            results.append(r)

        # Summary
        classifications = {}
        for r in results:
            cls = r.get("classification", "unknown")
            classifications[cls] = classifications.get(cls, 0) + 1

        avg_uptime = round(
            sum(r.get("uptime_percentage", 0) for r in results) / max(len(results), 1), 1
        )

        return {
            "connectors": results,
            "count": len(results),
            "average_uptime": avg_uptime,
            "classifications": classifications,
        }

    async def get_reliability_by_property(self, tenant_id: str, property_id: str) -> Dict[str, Any]:
        """Get reliability for connectors of a specific property."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        property_connectors = [c for c in connectors if c.get("property_id") == property_id]
        results = []
        for c in property_connectors:
            r = await self.get_reliability(tenant_id, c["id"])
            results.append(r)
        return {"connectors": results, "count": len(results), "property_id": property_id}

    # ─── MTBF / MTTR Calculation ───────────────────────────────────────

    @staticmethod
    def _calculate_mtbf_mttr(jobs: List[Dict]) -> tuple:
        """Calculate Mean Time Between Failures and Mean Time To Recovery."""
        if not jobs:
            return 0.0, 0.0

        sorted_jobs = sorted(jobs, key=lambda j: j.get("created_at", ""))
        recovery_times = []
        last_failure = None

        for job in sorted_jobs:
            status = job.get("status", "")
            created = job.get("created_at", "")
            if status == "failed":
                if last_failure is None:
                    last_failure = created
            elif status == "succeeded" and last_failure:
                recovery_times.append((created, last_failure))
                last_failure = None

        # MTBF: average time between failure starts
        failure_starts = [j.get("created_at", "") for j in sorted_jobs if j.get("status") == "failed"]
        if len(failure_starts) >= 2:
            intervals = []
            for i in range(1, len(failure_starts)):
                try:
                    t1 = datetime.fromisoformat(failure_starts[i - 1].replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(failure_starts[i].replace("Z", "+00:00"))
                    intervals.append((t2 - t1).total_seconds() / 3600)
                except (ValueError, TypeError):
                    pass
            mtbf = round(sum(intervals) / max(len(intervals), 1), 1) if intervals else 0.0
        else:
            mtbf = 0.0

        # MTTR: average recovery time
        if recovery_times:
            ttr_values = []
            for recovery, failure in recovery_times:
                try:
                    t_fail = datetime.fromisoformat(failure.replace("Z", "+00:00"))
                    t_rec = datetime.fromisoformat(recovery.replace("Z", "+00:00"))
                    ttr_values.append((t_rec - t_fail).total_seconds() / 3600)
                except (ValueError, TypeError):
                    pass
            mttr = round(sum(ttr_values) / max(len(ttr_values), 1), 1) if ttr_values else 0.0
        else:
            mttr = 0.0

        return mtbf, mttr

    @staticmethod
    def _calculate_uptime(connector: Dict, jobs: List[Dict]) -> float:
        """Calculate uptime percentage based on job history."""
        if not jobs:
            return 100.0 if connector.get("status") == "active" else 0.0

        total = len(jobs)
        failed = sum(1 for j in jobs if j.get("status") == "failed")
        return round((total - failed) / max(total, 1) * 100, 1)

    @staticmethod
    def _detect_failure_patterns(jobs: List[Dict]) -> List[Dict]:
        """Detect recurring failure patterns."""
        patterns = []
        sorted_jobs = sorted(jobs, key=lambda j: j.get("created_at", ""))
        failed_jobs = [j for j in sorted_jobs if j.get("status") == "failed"]

        if not failed_jobs:
            return patterns

        # Pattern: consecutive failures
        consecutive = 0
        max_consecutive = 0
        for j in sorted_jobs:
            if j.get("status") == "failed":
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

        if max_consecutive >= 3:
            patterns.append({
                "pattern": "consecutive_failures",
                "severity": "critical" if max_consecutive >= 5 else "warning",
                "detail": f"Max {max_consecutive} consecutive failures detected",
                "count": max_consecutive,
            })

        # Pattern: recurring time windows
        hours = {}
        for j in failed_jobs:
            try:
                dt = datetime.fromisoformat(j.get("created_at", "").replace("Z", "+00:00"))
                h = dt.hour
                hours[h] = hours.get(h, 0) + 1
            except (ValueError, TypeError):
                pass

        for h, count in hours.items():
            if count >= 3:
                patterns.append({
                    "pattern": "time_window_failures",
                    "severity": "warning",
                    "detail": f"{count} failures around hour {h}:00",
                    "hour": h,
                    "count": count,
                })

        # Pattern: error type concentration
        error_types = {}
        for j in failed_jobs:
            err = j.get("last_error") or "unknown"
            err = err[:50] if err else "unknown"
            error_types[err] = error_types.get(err, 0) + 1

        for err, count in error_types.items():
            if count >= 3:
                patterns.append({
                    "pattern": "repeated_error",
                    "severity": "warning",
                    "detail": f"'{err}' occurred {count} times",
                    "error": err,
                    "count": count,
                })

        return patterns

    @staticmethod
    def _classify_connector(success_rate: float, uptime: float, mttr: float, failed_count: int, import_success_rate: float = 100.0) -> str:
        """Classify connector reliability including import health."""
        combined_rate = (success_rate * 0.6 + import_success_rate * 0.4)
        if combined_rate >= 95 and uptime >= 98:
            return "stable"
        elif combined_rate >= 80 and uptime >= 90:
            return "healthy"
        elif combined_rate >= 50 or uptime >= 70:
            return "degraded"
        else:
            return "unstable"


    async def record_validation_event(
        self, tenant_id: str, connector_id: str,
        success: bool, details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a validation result for reliability tracking."""
        await db["cm_validation_events"].insert_one({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "success": success,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
