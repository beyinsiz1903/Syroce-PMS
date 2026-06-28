"""
CM Observability Check — Outbox backlog + circuit breaker visibility
=====================================================================
Aggregates the existing outbox + provider_failover signals into a
**global ops view** suitable for the readiness validator and the
cron-driven backlog alert script.

Why a separate helper (vs reusing health_check.py / cm_runtime_service):
  * health_check.py is a request-bound endpoint (needs FastAPI Request).
  * cm_runtime_service requires an OperationContext (per-tenant).
  * Readiness + cron alarms are tenant-agnostic and process-local —
    they need a thin, dependency-free helper that hits MongoDB +
    in-process provider_failover.

NEVER returns raw IPs, credentials, tenant_ids, or event payloads —
only counts + verdicts safe for ops dashboards / Sentry / log sinks.
"""

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("infra.cm_observability_check")


# ── Thresholds ────────────────────────────────────────────────────
# Tuned for the HR pilot. Pending+retry combined because retries are
# transient back-pressure, not fresh work — they belong in the same
# bucket from the operator's POV.
OUTBOX_PENDING_DEGRADED = 100  # pending+retry
OUTBOX_PENDING_FAIL = 500
OUTBOX_FAILED_DEGRADED = 50  # status="failed" (terminal)
OUTBOX_FAILED_FAIL = 200
OUTBOX_OLDEST_DEGRADED_SECONDS = 600  # 10 min
OUTBOX_OLDEST_FAIL_SECONDS = 1800  # 30 min
OUTBOX_NO_PROCESSING_DEGRADED_SECONDS = 1800  # 30 min since last success

# Circuit breaker thresholds.
# OPEN==1 → DEGRADED (single provider down, fail-over candidate);
# OPEN>=3 → FAIL (multi-provider blackout, pilot can't push ARI).
CB_OPEN_DEGRADED = 1
CB_OPEN_FAIL = 3


async def get_outbox_status(db) -> dict[str, Any]:
    """Compute outbox queue health for the global ops view.

    Mirrors the per-status counts already in health_check.py:353-414 but
    is tenant-agnostic and requires only a motor db handle. Safe to call
    from cron / readiness — no FastAPI dependency.
    """
    try:
        pending = await db.outbox_events.count_documents({"status": "pending"})
        processing = await db.outbox_events.count_documents({"status": "processing"})
        retry = await db.outbox_events.count_documents({"status": "retry"})
        failed = await db.outbox_events.count_documents({"status": "failed"})

        backlog = pending + retry  # operator-facing back-pressure metric

        # Oldest unfinished event (pending or retry) — created_at is ISO string
        oldest = await db.outbox_events.find_one(
            {"status": {"$in": ["pending", "retry"]}},
            {"_id": 0, "created_at": 1},
            sort=[("created_at", 1)],
        )
        oldest_seconds: float | None = None
        if oldest and oldest.get("created_at"):
            try:
                created = datetime.fromisoformat(oldest["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                oldest_seconds = round((datetime.now(UTC) - created).total_seconds(), 1)
            except Exception:
                oldest_seconds = None

        # Last successful processing — staleness signal independent of
        # backlog (a "0 backlog + 0 throughput in 30 min" state is also bad).
        last_processed = await db.outbox_events.find_one(
            {"status": "processed"},
            {"_id": 0, "processed_at": 1},
            sort=[("processed_at", -1)],
        )
        last_processed_seconds: float | None = None
        if last_processed and last_processed.get("processed_at"):
            try:
                processed = datetime.fromisoformat(last_processed["processed_at"])
                if processed.tzinfo is None:
                    processed = processed.replace(tzinfo=UTC)
                last_processed_seconds = round((datetime.now(UTC) - processed).total_seconds(), 1)
            except Exception:
                last_processed_seconds = None

        # Verdict — descending severity. Score is the readiness contribution.
        verdict = "ok"
        score = 1.0
        reasons: list[str] = []

        if backlog >= OUTBOX_PENDING_FAIL:
            verdict, score = "fail", 0.0
            reasons.append(f"backlog={backlog} ≥ {OUTBOX_PENDING_FAIL}")
        elif backlog >= OUTBOX_PENDING_DEGRADED:
            verdict, score = "degraded", 0.5
            reasons.append(f"backlog={backlog} ≥ {OUTBOX_PENDING_DEGRADED}")

        if failed >= OUTBOX_FAILED_FAIL:
            verdict, score = "fail", 0.0
            reasons.append(f"failed={failed} ≥ {OUTBOX_FAILED_FAIL}")
        elif failed >= OUTBOX_FAILED_DEGRADED and verdict == "ok":
            verdict, score = "degraded", 0.5
            reasons.append(f"failed={failed} ≥ {OUTBOX_FAILED_DEGRADED}")

        if oldest_seconds is not None:
            if oldest_seconds >= OUTBOX_OLDEST_FAIL_SECONDS:
                verdict, score = "fail", 0.0
                reasons.append(f"oldest={oldest_seconds:.0f}s ≥ {OUTBOX_OLDEST_FAIL_SECONDS}s")
            elif oldest_seconds >= OUTBOX_OLDEST_DEGRADED_SECONDS and verdict == "ok":
                verdict, score = "degraded", 0.5
                reasons.append(f"oldest={oldest_seconds:.0f}s ≥ {OUTBOX_OLDEST_DEGRADED_SECONDS}s")

        if backlog > 0 and last_processed_seconds is not None and last_processed_seconds >= OUTBOX_NO_PROCESSING_DEGRADED_SECONDS and verdict == "ok":
            verdict, score = "degraded", 0.5
            reasons.append(f"no_throughput={last_processed_seconds:.0f}s ≥ {OUTBOX_NO_PROCESSING_DEGRADED_SECONDS}s")

        return {
            "status": verdict,
            "score": score,
            "pending": pending,
            "processing": processing,
            "retry": retry,
            "failed": failed,
            "backlog": backlog,
            "oldest_seconds": oldest_seconds,
            "last_processed_seconds": last_processed_seconds,
            "reasons": reasons,
            "thresholds": {
                "backlog_degraded": OUTBOX_PENDING_DEGRADED,
                "backlog_fail": OUTBOX_PENDING_FAIL,
                "failed_degraded": OUTBOX_FAILED_DEGRADED,
                "failed_fail": OUTBOX_FAILED_FAIL,
                "oldest_seconds_degraded": OUTBOX_OLDEST_DEGRADED_SECONDS,
                "oldest_seconds_fail": OUTBOX_OLDEST_FAIL_SECONDS,
            },
        }
    except Exception as e:
        # Never crash readiness because of an outbox sampling error;
        # surface the error_type only (no payload, no IPs).
        logger.warning(f"get_outbox_status failed: {type(e).__name__}: {e}")
        return {
            "status": "unknown",
            "score": 0.5,
            "error_type": type(e).__name__,
        }


async def get_circuit_breaker_status() -> dict[str, Any]:
    """Inspect circuit breakers from provider_failover.

    Returns counts by state — never the per-connection identifiers
    (those leak tenant + connection_id). For the per-connection drill-
    down, the operator hits ``GET /api/channel-manager/unified-rate-
    manager/circuit-breakers`` (RBAC-gated).

    Reads the fleet-wide shared (Redis-backed) view when enabled so a
    breaker tripped on any worker is reflected here; falls back to the
    in-process snapshot when Redis is absent.
    """
    try:
        from domains.channel_manager.provider_failover import provider_failover

        # Public counts API — never touches the underscore-prefixed
        # `_breakers` dict (architect review, May 2026: avoid coupling
        # to private internals so a future thread-safe wrapper or LRU
        # eviction can override get_state_counts() without breaking
        # readiness/alerting).
        counts = await provider_failover.get_state_counts_shared()
        total = counts.get("total", 0)
        open_count = counts.get("open", 0)
        half_open_count = counts.get("half_open", 0)
        closed_count = counts.get("closed", 0)

        verdict = "ok"
        score = 1.0
        reasons: list[str] = []
        if open_count >= CB_OPEN_FAIL:
            verdict, score = "fail", 0.0
            reasons.append(f"open={open_count} ≥ {CB_OPEN_FAIL}")
        elif open_count >= CB_OPEN_DEGRADED:
            verdict, score = "degraded", 0.5
            reasons.append(f"open={open_count} ≥ {CB_OPEN_DEGRADED}")

        # HALF_OPEN is a recovery probe state — informational only,
        # does not degrade the score.
        return {
            "status": verdict,
            "score": score,
            "total": total,
            "open": open_count,
            "half_open": half_open_count,
            "closed": closed_count,
            "reasons": reasons,
            "thresholds": {
                "open_degraded": CB_OPEN_DEGRADED,
                "open_fail": CB_OPEN_FAIL,
            },
        }
    except Exception as e:
        logger.warning(f"get_circuit_breaker_status failed: {type(e).__name__}: {e}")
        return {
            "status": "unknown",
            "score": 0.7,  # in-process breakers should always be readable;
            # if they're not, something deeper is wrong but
            # we don't want to single-handedly fail readiness.
            "error_type": type(e).__name__,
        }


async def get_cm_observability_snapshot(db) -> dict[str, Any]:
    """Convenience aggregator for the cron alarm script + ad-hoc CLI."""
    outbox = await get_outbox_status(db)
    breakers = await get_circuit_breaker_status()

    # Worst-of verdict for the snapshot summary.
    severity_order = {"ok": 0, "unknown": 1, "degraded": 2, "fail": 3}
    worst = max(
        (outbox.get("status", "ok"), breakers.get("status", "ok")),
        key=lambda s: severity_order.get(s, 0),
    )
    return {
        "verdict": worst,
        "checked_at": datetime.now(UTC).isoformat(),
        "outbox": outbox,
        "circuit_breakers": breakers,
    }
