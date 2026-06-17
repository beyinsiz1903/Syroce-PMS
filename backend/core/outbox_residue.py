"""Single source of truth for stress-tenant outbox residue classification.

Background
----------
Stress runs in the dedicated stress tenant emit guest-lifecycle SXI events
(``guest.checked_in.v1`` / ``guest.checked_out.v1``) into ``outbox_events`` via
the production outbox path. Nothing in the stress tenant consumes them, so they
accumulate as PENDING forever and the platform-wide outbox monitor's per-minute
``count_documents({status: "pending"})`` scans the whole dead backlog — exactly
what trips the Atlas "Query Targeting: Scanned/Returned > 1000" alert.

Two cleanup surfaces share this classification and MUST never drift apart:
  * ``scripts/cleanup_stress_outbox_residue.py`` — the manual operator sweep
    (dry-run by default, age-guarded, fail-closed env gates).
  * ``domains/admin/router/stress.py`` ``/admin/stress/cleanup`` — the nightly
    e2e-stress teardown auto-clean.

Keep this module import-side-effect free (no logging config, no DB import) so it
is safe to import from both a router and a standalone script.
"""
from __future__ import annotations

from datetime import datetime

# PENDING outbox event types that have NO consumer in the stress tenant and
# therefore pile up forever. PENDING rows of any OTHER type are deliberately
# never swept, so a genuine stuck-delivery condition is never masked.
DEAD_PENDING_EVENT_TYPES: tuple[str, ...] = (
    "guest.checked_in.v1",
    "guest.checked_out.v1",
)

# Terminal outbox states — safe to prune once delivered / failed / parked.
# (Going forward these are pruned for ALL tenants by the
# ``outbox_terminal_retention_task`` Celery beat; the manual sweep clears any
# existing pile immediately.)
TERMINAL_OUTBOX_STATUSES: tuple[str, ...] = ("processed", "failed", "parked")

# The collection that holds the residue.
OUTBOX_COLLECTION = "outbox_events"

# Default age threshold (hours): a row younger than this is left alone so a
# sweep never races the fresh events of an in-flight stress run. Shared by the
# manual operator script and the nightly Celery beat so the age guard can't
# drift between them.
STRESS_OUTBOX_SWEEP_AGE_HOURS_DEFAULT: int = 24


def outbox_age_cutoff_match(cutoff: datetime) -> dict:
    """Match ``created_at`` older-or-equal than ``cutoff`` in EITHER stored form.

    ``outbox_events`` persists ``created_at`` as an ISO-8601 UTC string; a few
    legacy rows may carry a BSON datetime. Match either (lexicographic ISO
    compare == chronological for UTC ISO strings) so neither is missed.
    """
    return {
        "$or": [
            {"created_at": {"$lte": cutoff.isoformat()}},
            {"created_at": {"$lte": cutoff}},
        ]
    }


def stress_outbox_residue_query(tenant_id: str, cutoff: datetime) -> dict:
    """Single-source query for sweepable stress outbox residue.

    Scoped to ``tenant_id`` and older than ``cutoff``, it matches:
      * PENDING rows of the no-consumer event types (the dead backlog), and
      * rows in any terminal status (``processed`` / ``failed`` / ``parked``).

    PENDING rows of any OTHER type are deliberately excluded so a genuine
    stuck-delivery condition is never masked. Both the manual sweep
    (``scripts/cleanup_stress_outbox_residue.py``) and the nightly beat
    (``celery_tasks.stress_outbox_residue_sweep_task``) build their delete
    filter from this one function so the two can never drift apart.
    """
    return {
        "tenant_id": tenant_id,
        "$and": [
            outbox_age_cutoff_match(cutoff),
            {
                "$or": [
                    {
                        "status": "pending",
                        "event_type": {"$in": list(DEAD_PENDING_EVENT_TYPES)},
                    },
                    {"status": {"$in": list(TERMINAL_OUTBOX_STATUSES)}},
                ]
            },
        ],
    }
