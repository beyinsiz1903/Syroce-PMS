"""Maintenance sweep for stress-test outbox + reconciliation residue.

Background
----------
Stress runs in the dedicated stress tenant emit guest lifecycle SXI events
(``guest.checked_in.v1`` / ``guest.checked_out.v1``) into ``outbox_events``.
Nothing in the stress tenant consumes them, so they accumulate as PENDING
forever (observed: 30k+ rows stuck since the first stress wave, no ``attempts``
field, never delivered). The platform-wide outbox monitoring then runs
``count_documents({status: "pending"})`` every minute and the dispatcher
pollers ``find({status: ...})`` — both scan the entire dead backlog, which is
exactly what trips the Atlas "Query Targeting: Scanned/Returned > 1000" alert.
Stress runs also leave ``channel_reconciliation_cases`` rows in the stress
tenant.

The sibling sweeps ``cleanup_e2e_pilot_residue.py`` (pilot bookings/guests/
folio_charges) and ``cleanup_stress_crm_residue.py`` (stress
corporate_contracts/mice_accounts) do NOT cover the outbox or reconciliation
collections. This script is that missing safety net, scoped strictly to the
stress tenant.

What it deletes (stress tenant only, older than ``--hours``)
-----------------------------------------------------------
* ``outbox_events``:
    - PENDING rows of the no-consumer event types
      (``guest.checked_in.v1`` / ``guest.checked_out.v1``) — the dead backlog.
    - TERMINAL rows (``processed`` / ``failed`` / ``parked``) — old residue.
  PENDING rows of OTHER event types are deliberately left alone so a genuine
  stuck-delivery condition is never masked. (Going forward, terminal rows for
  ALL tenants are pruned by the ``outbox_terminal_retention_task`` Celery beat
  job; this stress sweep clears the existing pile immediately.)
* ``channel_reconciliation_cases``: rows in the stress tenant older than the
  cutoff.

Why delete (not soft-deactivate)
--------------------------------
These are throwaway stress fixtures in a dedicated stress tenant and the dead
PENDING rows are the direct cause of the query-targeting alert; only physically
removing them restores cheap monitoring/poller scans.

Safety contract (identical to cleanup_stress_crm_residue.py)
------------------------------------------------------------
* ``E2E_STRESS_TENANT_ID`` env var **must** be set (fail-closed; cross-tenant
  blast radius = 0).
* The resolved tenant **must not** equal the pilot tenant — both
  ``PILOT_TENANT_ID`` (if set) and the known pilot UUID are blocked
  (``pilot_drift = 0``).
* ``--apply`` requires ``E2E_ALLOW_STRESS_CLEANUP=true`` (fail-closed). The
  default is dry-run; the destructive path is opt-in twice (CLI flag + env).
* Only rows older than ``--hours`` (default 24h) are touched — the age guard
  prevents racing an in-flight stress run.
* Every delete query is tenant-scoped, so the blast radius can never reach
  another tenant's rows.

Usage
-----
    # Default: dry-run, list residue, no writes
    E2E_STRESS_TENANT_ID=<uuid> python -m scripts.cleanup_stress_outbox_residue

    # Apply (requires E2E_ALLOW_STRESS_CLEANUP=true)
    E2E_STRESS_TENANT_ID=<uuid> E2E_ALLOW_STRESS_CLEANUP=true \
        python -m scripts.cleanup_stress_outbox_residue --apply

    # Custom age window (default 24h)
    E2E_STRESS_TENANT_ID=<uuid> python -m scripts.cleanup_stress_outbox_residue --hours 12

Operational metric
------------------
Every run inserts a summary doc into ``stress_outbox_residue_scans`` with
counts. A row with ``found_total > 0`` after the next nightly run signals the
stress outbox backlog is rebuilding (the query-targeting risk is returning).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.database import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cleanup_stress_outbox_residue")

# Known pilot tenant UUID. The pilot is a live demo tenant and must never be
# touched by a stress-residue sweep, even if E2E_STRESS_TENANT_ID is somehow
# misconfigured to point at it.
PILOT_TENANT_UUID = "5bad4a34-6ee3-4566-9053-741b7375a9cf"

OUTBOX_COLL = "outbox_events"
RECON_COLL = "channel_reconciliation_cases"

# PENDING event types with no consumer in the stress tenant (the dead backlog)
# + the terminal states, single-sourced in ``core.outbox_residue`` so this
# manual sweep and the nightly teardown auto-clean
# (``domains/admin/router/stress.py``) can never drift apart. PENDING rows of
# any OTHER type are NOT swept — don't mask a real stuck-delivery condition.
from core.outbox_residue import (  # noqa: E402
    DEAD_PENDING_EVENT_TYPES,
    outbox_age_cutoff_match,
    stress_outbox_residue_query,
)

MAX_TIME_MS = 60000


def outbox_query(tenant_id: str, cutoff: datetime) -> dict:
    # Single-sourced in core.outbox_residue so this manual sweep and the nightly
    # Celery beat (stress_outbox_residue_sweep_task) build the identical filter.
    return stress_outbox_residue_query(tenant_id, cutoff)


def recon_query(tenant_id: str, cutoff: datetime) -> dict:
    return {"tenant_id": tenant_id, "$and": [outbox_age_cutoff_match(cutoff)]}


async def scan(tenant_id: str, hours: int) -> dict:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    oq = outbox_query(tenant_id, cutoff)
    rq = recon_query(tenant_id, cutoff)
    # Use count_documents (not a full to_list) — the dead backlog can be tens of
    # thousands of rows, and materialising them all just to count would be
    # wasteful. A small sample is fetched separately for the metric row.
    outbox_count = await db[OUTBOX_COLL].count_documents(oq, maxTimeMS=MAX_TIME_MS)
    recon_count = await db[RECON_COLL].count_documents(rq, maxTimeMS=MAX_TIME_MS)
    outbox_sample = await db[OUTBOX_COLL].find(oq, {"_id": 0, "id": 1, "event_type": 1, "status": 1}).limit(10).to_list(10)
    recon_sample = await db[RECON_COLL].find(rq, {"_id": 0, "id": 1, "status": 1, "case_type": 1}).limit(10).to_list(10)
    return {
        "cutoff": cutoff.isoformat(),
        "outbox_query": oq,
        "recon_query": rq,
        "counts": {OUTBOX_COLL: outbox_count, RECON_COLL: recon_count},
        "outbox_sample": outbox_sample,
        "recon_sample": recon_sample,
    }


async def apply(found: dict) -> dict:
    """Delete residue with the (tenant-scoped) scan queries directly.

    The scan query already constrains ``tenant_id`` + age + status, so a direct
    ``delete_many`` can never reach another tenant and scales to the large dead
    backlog without materialising tens of thousands of ids in a giant ``$in``.
    """
    out_res = await db[OUTBOX_COLL].delete_many(found["outbox_query"])
    rec_res = await db[RECON_COLL].delete_many(found["recon_query"])
    return {
        OUTBOX_COLL: int(getattr(out_res, "deleted_count", 0) or 0),
        RECON_COLL: int(getattr(rec_res, "deleted_count", 0) or 0),
    }


async def record_scan(summary: dict) -> None:
    """Persist a summary row so admin dashboards / alerts can poll it."""
    try:
        await db.stress_outbox_residue_scans.insert_one(summary)
    except Exception as e:  # pragma: no cover — best-effort metric
        logger.warning("[stress-outbox-residue] metric insert failed: %s", e)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Stress tenant outbox + reconciliation residue sweep.")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Yaş eşiği (saat). Bu süreden eski kayıtlar hedeflenir.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Bulduklarını uygula (sil). Aksi halde dry-run.",
    )
    args = parser.parse_args()

    if args.hours <= 0:
        logger.error("--hours pozitif bir tam sayı olmalı; age guard kazara bypass edilemez — fail-closed.")
        return 2

    tenant_id = os.environ.get("E2E_STRESS_TENANT_ID", "").strip()
    if not tenant_id:
        logger.error("E2E_STRESS_TENANT_ID env var tanımlı değil — fail-closed; production guard tetiklendi.")
        return 2

    # Pilot exclusion guard: refuse if the resolved tenant is the pilot, via
    # either the PILOT_TENANT_ID env or the known pilot UUID (pilot_drift=0).
    pilot_tid = os.environ.get("PILOT_TENANT_ID", "").strip()
    if tenant_id == PILOT_TENANT_UUID or (pilot_tid and tenant_id == pilot_tid):
        logger.error(
            "E2E_STRESS_TENANT_ID pilot tenant'a (%s) eşit — fail-closed; stress residue sweep pilot'a dokunamaz.",
            tenant_id,
        )
        return 2

    if args.apply and os.environ.get("E2E_ALLOW_STRESS_CLEANUP", "").lower() != "true":
        logger.error("--apply için E2E_ALLOW_STRESS_CLEANUP=true gerekli — fail-closed.")
        return 2

    logger.info(
        "[stress-outbox-residue] tenant=%s hours=%d mode=%s",
        tenant_id,
        args.hours,
        "APPLY" if args.apply else "DRY-RUN",
    )

    found = await scan(tenant_id, args.hours)
    counts = found["counts"]
    total = sum(counts.values())

    applied = {OUTBOX_COLL: 0, RECON_COLL: 0}
    if args.apply and total > 0:
        applied = await apply(found)

    summary = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "hours": args.hours,
        "mode": "apply" if args.apply else "dry_run",
        "cutoff": found["cutoff"],
        "found": counts,
        "found_total": total,
        "applied": applied,
        "sample_outbox_ids": [d.get("id") for d in found["outbox_sample"]],
        "sample_recon_ids": [d.get("id") for d in found["recon_sample"]],
    }
    await record_scan(summary)

    print("=" * 60)
    print(f"Stress outbox/recon residue sweep ({'APPLY' if args.apply else 'DRY-RUN'}) tenant={tenant_id}")
    print("=" * 60)
    for k, v in counts.items():
        print(f"  {k:30s} -> {v}")
    print(f"  {'TOPLAM':30s} -> {total}")
    if args.apply:
        print("  -- applied (deleted) --")
        for k, v in applied.items():
            print(f"  {k:30s} -> {v}")
    print(f"  metric row -> stress_outbox_residue_scans @ {summary['scanned_at']}")

    if total > 0:
        logger.warning(
            "[stress-outbox-residue] %d artık kayıt bulundu (outbox=%d recon=%d) — stress backlog birikiyor, query-targeting riski geri dönebilir.",
            total,
            counts[OUTBOX_COLL],
            counts[RECON_COLL],
        )
        # Non-zero exit when residue exists in dry-run mode so cron/CI can alert.
        # When --apply succeeds we still exit 0 (the residue was handled).
        if not args.apply:
            return 1
    else:
        logger.info("[stress-outbox-residue] residue=0, stress tenant temiz.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
