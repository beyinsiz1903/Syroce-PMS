"""
Control Plane — MongoDB Index Definitions
==========================================
All indexes required for control plane collections.
Called during startup to ensure query performance.
"""

import logging

logger = logging.getLogger("controlplane.indexes")

COLL_FAILURES = "cp_failures"
COLL_SYNC_JOBS = "cp_sync_jobs"
COLL_SECRET_AUDIT = "secret_access_audit"


async def ensure_controlplane_indexes(db) -> None:
    """Create all required indexes for control plane collections."""
    logger.info("Ensuring control plane indexes...")

    # ── cp_failures ────────────────────────────────────────────────
    failures = db[COLL_FAILURES]

    await failures.create_index(
        [("tenant_id", 1), ("status", 1), ("created_at", -1)],
        name="idx_cp_failures_tenant_status",
    )
    await failures.create_index(
        [("status", 1), ("severity", 1), ("last_seen_at", -1)],
        name="idx_cp_failures_status_severity",
    )
    await failures.create_index(
        [("provider", 1), ("failure_type", 1), ("status", 1)],
        name="idx_cp_failures_provider_type",
    )
    await failures.create_index(
        [("operation_type", 1), ("status", 1), ("created_at", -1)],
        name="idx_cp_failures_operation",
    )
    await failures.create_index(
        [("correlation_id", 1)],
        name="idx_cp_failures_correlation",
    )
    await failures.create_index(
        "id",
        unique=True,
        name="idx_cp_failures_id",
    )

    # ── cp_sync_jobs ───────────────────────────────────────────────
    sync_jobs = db[COLL_SYNC_JOBS]

    await sync_jobs.create_index(
        [("tenant_id", 1), ("status", 1), ("started_at", -1)],
        name="idx_cp_sync_tenant_status",
    )
    await sync_jobs.create_index(
        [("provider", 1), ("job_type", 1), ("status", 1)],
        name="idx_cp_sync_provider_type",
    )
    await sync_jobs.create_index(
        "id",
        unique=True,
        name="idx_cp_sync_id",
    )

    # ── secret_access_audit (extend existing) ──────────────────────
    audit = db[COLL_SECRET_AUDIT]

    await audit.create_index(
        [("tenant_id", 1), ("provider", 1), ("timestamp", -1)],
        name="idx_secret_audit_tenant_provider",
    )
    await audit.create_index(
        [("result", 1), ("timestamp", -1)],
        name="idx_secret_audit_result",
    )
    await audit.create_index(
        [("actor", 1), ("timestamp", -1)],
        name="idx_secret_audit_actor",
    )

    logger.info("Control plane indexes ensured.")
