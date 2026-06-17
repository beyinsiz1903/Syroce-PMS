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
