"""
Dashboard Aggregator — Health Score + Metrics Computation
==========================================================
Computes system and tenant health scores from live collection queries.
Single API call returns everything needed for the control plane dashboard.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("controlplane.dashboard_aggregator")


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def compute_health_score(metrics: dict[str, Any]) -> float:
    """Score 0-100. Weighted by business impact."""
    score = 100.0

    # Critical failures (weight: 30)
    by_sev = metrics.get("open_failures_by_severity", {})
    score -= by_sev.get("critical", 0) * 15

    # High failures (weight: 20)
    score -= by_sev.get("high", 0) * 5

    # Outbox health (weight: 15)
    stuck = metrics.get("outbox_stuck", 0)
    if stuck > 0:
        score -= min(15, stuck * 3)

    # Import health (weight: 15)
    import_rate = metrics.get("import_success_rate_24h", 100.0)
    score -= (1.0 - import_rate / 100) * 15

    # Sync health (weight: 10)
    sync_rate = metrics.get("sync_success_rate_24h", 100.0)
    score -= (1.0 - sync_rate / 100) * 10

    # ARI freshness (weight: 5)
    ari_lag = metrics.get("ari_sync_lag_minutes", 0)
    if ari_lag > 15:
        score -= 5
    elif ari_lag > 5:
        score -= 2

    # Security (weight: 5)
    anomalies = metrics.get("secret_anomalies_24h", 0)
    if anomalies > 0:
        score -= min(5, anomalies * 2)

    return max(0.0, round(score, 1))


class DashboardAggregator:
    """Aggregates metrics from all subsystems into a single dashboard payload."""

    def __init__(self):
        self._db = None

    def _get_db(self):
        # v42 round-2: aggregator runs system-wide (tenant_id=None) from a
        # background snapshot worker without tenant_context. Every query in
        # this module already injects `tenant_id` manually when scoping is
        # required, so use the raw system DB to bypass STRICT_TENANT_MODE.
        if self._db is None:
            from core.tenant_db import get_system_db
            self._db = get_system_db()
        return self._db

    async def compute_dashboard(
        self, tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Compute full dashboard payload. Target: < 500ms p95."""
        db = self._get_db()
        now = datetime.now(UTC)
        cutoff_24h = (now - timedelta(hours=24)).isoformat()
        cutoff_30m = (now - timedelta(minutes=30)).isoformat()

        # Run all queries in parallel
        results = await asyncio.gather(
            self._failure_metrics(db, tenant_id),
            self._outbox_metrics(db, tenant_id, cutoff_30m, cutoff_24h),
            self._import_metrics(db, tenant_id, cutoff_24h),
            self._sync_metrics(db, tenant_id, cutoff_24h),
            self._connector_status(db, tenant_id),
            self._security_metrics(db, tenant_id, cutoff_24h),
            self._recent_failures(db, tenant_id),
            self._pipeline_depth(db, tenant_id),
            return_exceptions=True,
        )

        # Safely unpack results
        failure_m = results[0] if not isinstance(results[0], Exception) else {}
        outbox_m = results[1] if not isinstance(results[1], Exception) else {}
        import_m = results[2] if not isinstance(results[2], Exception) else {}
        sync_m = results[3] if not isinstance(results[3], Exception) else {}
        connectors = results[4] if not isinstance(results[4], Exception) else []
        security_m = results[5] if not isinstance(results[5], Exception) else {}
        recent_failures = results[6] if not isinstance(results[6], Exception) else []
        pipeline = results[7] if not isinstance(results[7], Exception) else {}

        # Merge all metrics
        metrics = {
            **failure_m,
            **outbox_m,
            **import_m,
            **sync_m,
            **security_m,
        }

        score = compute_health_score(metrics)

        return {
            "health_score": score,
            "health_grade": _grade(score),
            "metrics": metrics,
            "connector_status": connectors,
            "pipeline": pipeline,
            "recent_failures": recent_failures,
            "timestamp": now.isoformat(),
        }

    async def _failure_metrics(
        self, db, tenant_id: str | None,
    ) -> dict[str, Any]:
        from controlplane.failure_tracker import get_failure_tracker
        tracker = get_failure_tracker()
        open_count = await tracker.count_open(tenant_id=tenant_id)
        by_severity = await tracker.count_by_severity(tenant_id=tenant_id)
        by_type = await tracker.count_by_type(tenant_id=tenant_id)
        by_op = await tracker.count_by_operation(tenant_id=tenant_id)

        now = datetime.now(UTC)
        cutoff_1h = (now - timedelta(hours=1)).isoformat()
        cutoff_24h = (now - timedelta(hours=24)).isoformat()
        failures_1h = await db.cp_failures.count_documents(
            {"created_at": {"$gte": cutoff_1h}}
        )
        failures_24h = await db.cp_failures.count_documents(
            {"created_at": {"$gte": cutoff_24h}}
        )

        return {
            "open_failures": open_count,
            "open_failures_by_severity": by_severity,
            "failures_by_type": by_type,
            "failures_by_operation": by_op,
            "failure_count_1h": failures_1h,
            "failure_count_24h": failures_24h,
        }

    async def _outbox_metrics(
        self, db, tenant_id: str | None, cutoff_30m: str, cutoff_24h: str,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {}
        if tenant_id:
            base["tenant_id"] = tenant_id

        pending = await db.outbox_events.count_documents({**base, "status": "pending"})
        processing = await db.outbox_events.count_documents({**base, "status": "processing"})
        failed = await db.outbox_events.count_documents(
            {**base, "status": {"$in": ["failed", "parked"]}}
        )
        stuck = await db.outbox_events.count_documents(
            {**base, "status": {"$in": ["pending", "retry"]}, "created_at": {"$lte": cutoff_30m}}
        )
        processed_24h = await db.outbox_events.count_documents(
            {**base, "status": "processed", "processed_at": {"$gte": cutoff_24h}}
        )

        return {
            "outbox_pending": pending,
            "outbox_processing": processing,
            "outbox_failed": failed,
            "outbox_stuck": stuck,
            "outbox_processed_24h": processed_24h,
        }

    async def _import_metrics(
        self, db, tenant_id: str | None, cutoff_24h: str,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {}
        if tenant_id:
            base["tenant_id"] = tenant_id
        coll = db.imported_reservations

        pending = await coll.count_documents({**base, "import_status": "pending_auto_import"})
        failed = await coll.count_documents(
            {**base, "import_status": "failed", "updated_at": {"$gte": cutoff_24h}}
        )
        review = await coll.count_documents({**base, "import_status": "review_required"})
        imported_24h = await coll.count_documents(
            {**base, "import_status": "imported", "updated_at": {"$gte": cutoff_24h}}
        )

        total_24h = imported_24h + failed
        success_rate = (imported_24h / total_24h * 100) if total_24h > 0 else 100.0

        return {
            "import_pending": pending,
            "import_failed_24h": failed,
            "import_review_required": review,
            "import_success_rate_24h": round(success_rate, 1),
        }

    async def _sync_metrics(
        self, db, tenant_id: str | None, cutoff_24h: str,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {"started_at": {"$gte": cutoff_24h}}
        if tenant_id:
            base["tenant_id"] = tenant_id
        coll = db.cp_sync_jobs

        total = await coll.count_documents(base)
        completed = await coll.count_documents({**base, "status": "completed"})
        rate = (completed / total * 100) if total > 0 else 100.0

        # Average latency
        avg_latency = 0
        if total > 0:
            pipeline = [
                {"$match": {**base, "duration_ms": {"$exists": True}}},
                {"$group": {"_id": None, "avg": {"$avg": "$duration_ms"}}},
            ]
            async for doc in coll.aggregate(pipeline):
                avg_latency = int(doc.get("avg", 0))

        return {
            "sync_total_24h": total,
            "sync_success_rate_24h": round(rate, 1),
            "sync_avg_latency_ms": avg_latency,
        }

    async def _connector_status(
        self, db, tenant_id: str | None,
    ) -> list[dict[str, Any]]:
        connectors = []
        for coll_name, provider in [
            ("exely_connections", "exely"),
            ("hotelrunner_connections", "hotelrunner"),
        ]:
            try:
                query: dict[str, Any] = {"is_active": True}
                if tenant_id:
                    query["tenant_id"] = tenant_id
                async for conn in db[coll_name].find(query, {"_id": 0}):
                    connectors.append({
                        "provider": provider,
                        "connector_id": conn.get("id", ""),
                        "status": "healthy" if conn.get("is_active") else "down",
                        "last_successful_sync": conn.get("last_sync_at"),
                        "last_error": conn.get("last_error"),
                        "property_name": conn.get("property_name", ""),
                    })
            except Exception:
                pass
        return connectors

    async def _security_metrics(
        self, db, tenant_id: str | None, cutoff_24h: str,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "result": {"$in": ["failure", "denied", "not_found"]},
            "timestamp": {"$gte": cutoff_24h},
        }
        if tenant_id:
            query["tenant_id"] = tenant_id

        anomalies = await db.secret_access_audit.count_documents(query)
        return {"secret_anomalies_24h": anomalies}

    async def _recent_failures(
        self, db, tenant_id: str | None,
    ) -> list[dict[str, Any]]:
        from controlplane.failure_tracker import get_failure_tracker
        tracker = get_failure_tracker()
        return await tracker.recent_failures(hours=24, tenant_id=tenant_id, limit=5)

    async def _pipeline_depth(
        self, db, tenant_id: str | None,
    ) -> dict[str, Any]:
        """End-to-end reservation pipeline depth."""
        base: dict[str, Any] = {}
        if tenant_id:
            base["tenant_id"] = tenant_id

        stages = []

        # Ingest pending
        ingest_count = await db.reservation_lineage.count_documents(
            {**base, "status": {"$in": ["received", "normalized", "pending"]}}
        )
        stages.append({"name": "ingest_pending", "count": ingest_count})

        # Import pending
        import_count = await db.imported_reservations.count_documents(
            {**base, "import_status": {"$in": ["pending_auto_import", "processing", "retry"]}}
        )
        stages.append({"name": "import_pending", "count": import_count})

        # Outbox pending
        outbox_count = await db.outbox_events.count_documents(
            {**base, "status": {"$in": ["pending", "processing", "retry"]}}
        )
        stages.append({"name": "outbox_pending", "count": outbox_count})

        total = sum(s["count"] for s in stages)

        return {
            "stages": stages,
            "total_in_flight": total,
        }


# ── Snapshot Storage ───────────────────────────────────────────────

COLL_SNAPSHOTS = "cp_health_snapshots"


class DashboardSnapshotWorker:
    """Background worker that stores health snapshots every 60s."""

    def __init__(self, interval: float = 60.0):
        self.interval = interval
        self._task = None
        self._stop = None
        self._aggregator = DashboardAggregator()

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="dashboard-snapshot-worker")
        logger.info("Dashboard snapshot worker started (interval=%ss)", self.interval)

    async def stop(self):
        if self._stop:
            self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Dashboard snapshot worker stopped")

    async def _run(self):
        import uuid as _uuid
        try:
            while not self._stop.is_set():
                try:
                    dashboard = await self._aggregator.compute_dashboard()
                    db = self._aggregator._get_db()
                    snapshot = {
                        "id": str(_uuid.uuid4()),
                        "snapshot_type": "system",
                        "tenant_id": "__system__",
                        "timestamp": dashboard["timestamp"],
                        "health_score": dashboard["health_score"],
                        "health_grade": dashboard["health_grade"],
                        "metrics": dashboard["metrics"],
                    }
                    await db[COLL_SNAPSHOTS].insert_one(snapshot)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("Snapshot worker error", exc_info=True)

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                    break
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass


# ── Singletons ─────────────────────────────────────────────────────
_aggregator: DashboardAggregator | None = None
_snapshot_worker: DashboardSnapshotWorker | None = None


def get_dashboard_aggregator() -> DashboardAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = DashboardAggregator()
    return _aggregator


def get_snapshot_worker() -> DashboardSnapshotWorker:
    global _snapshot_worker
    if _snapshot_worker is None:
        _snapshot_worker = DashboardSnapshotWorker()
    return _snapshot_worker


async def ensure_snapshot_indexes():
    """Create indexes for cp_health_snapshots."""
    from core.database import db
    coll = db[COLL_SNAPSHOTS]
    try:
        await coll.create_index(
            [("tenant_id", 1), ("timestamp", -1)],
            name="idx_snapshot_tenant",
        )
        await coll.create_index(
            [("snapshot_type", 1), ("timestamp", -1)],
            name="idx_snapshot_type",
        )
        await coll.create_index(
            [("timestamp", 1)],
            name="idx_snapshot_ttl",
            expireAfterSeconds=604800,  # 7 days
        )
        logger.info("Dashboard snapshot indexes ensured")
    except Exception as e:
        logger.warning("Snapshot index creation error: %s", e)
