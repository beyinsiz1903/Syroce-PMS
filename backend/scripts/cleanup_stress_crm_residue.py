"""Maintenance sweep for stress-test CRM residue in the stress tenant.

Background
----------
Stress runs (F8C and friends) create real ``corporate_contracts`` and
``mice_accounts`` rows in the dedicated stress tenant with an
``E2E_STRESS_<ts>_`` / ``E2E_`` label prefix. The uniqueness backstops behind
the CRM duplicate guards — ``uniq_corp_contract_rate_code`` /
``uniq_corp_contract_contact_email`` for contracts and
``uniq_mice_acc_client_taxno`` / ``uniq_mice_acc_client_email`` for client
accounts — are *global* unique indexes: duplicate residue in ANY tenant makes
the build fail, which silently turns the "no duplicate billing contact / tax
number" safeguard OFF for every hotel until the residue is cleaned (this is
exactly what Task #232 had to fix by hand after 87 duplicate corporate-contract
rows piled up).

The sibling sweep ``cleanup_e2e_pilot_residue.py`` handles
bookings/guests/folio_charges in the *pilot* tenant but does NOT cover the CRM
collections or the *stress* tenant. This script is that missing safety net: a
periodic sweep that lists (and optionally deletes) ``E2E_`` prefixed CRM rows
older than 24 hours, scoped strictly to the stress tenant.

Why delete (not soft-deactivate)
--------------------------------
The pilot residue sweep soft-cancels/voids rows because the pilot is a live
demo tenant. Here the goal is different: the colliding ``rate_code`` /
``contact_email`` / ``tax_no`` / ``email`` *values* are what block the global
unique index from building. Only physically removing the residue rows frees
those values so the backstop can self-heal on its next ``create_index``
attempt. The rows are throwaway stress fixtures in a dedicated stress tenant,
so a hard delete is the correct and safe action.

Safety contract
---------------
* ``E2E_STRESS_TENANT_ID`` env var **must** be set. The script refuses to scan
  or mutate anything without it (fail-closed; cross-tenant blast radius = 0).
* The resolved tenant **must not** equal the pilot tenant. Both
  ``PILOT_TENANT_ID`` (if set) and the known pilot UUID are blocked
  (``pilot_drift = 0``).
* ``--apply`` requires ``E2E_ALLOW_STRESS_CLEANUP=true`` (fail-closed). The
  default is dry-run; the destructive path is opt-in twice (CLI flag + env).
* Only rows whose name/label/description starts with ``E2E_`` AND are older
  than ``--hours`` (default 24h) are touched. The age guard prevents racing an
  in-flight stress run.

Usage
-----
    # Default: dry-run, list residue, no writes
    E2E_STRESS_TENANT_ID=<uuid> python -m scripts.cleanup_stress_crm_residue

    # Apply (requires E2E_ALLOW_STRESS_CLEANUP=true)
    E2E_STRESS_TENANT_ID=<uuid> E2E_ALLOW_STRESS_CLEANUP=true \
        python -m scripts.cleanup_stress_crm_residue --apply

    # Custom age window (default 24h)
    E2E_STRESS_TENANT_ID=<uuid> python -m scripts.cleanup_stress_crm_residue --hours 12

Operational metric
------------------
Every run inserts a summary doc into ``stress_crm_residue_scans`` with
timestamp, mode, counts per collection, and applied counts. The admin
dashboard / alerting can poll this collection: any row with ``found_total > 0``
after the next nightly run is an actionable signal that stress residue is
accumulating and the CRM uniqueness backstop is at risk of being disabled.
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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("cleanup_stress_crm_residue")

E2E_PREFIX_REGEX = r"^E2E_"

# Known pilot tenant UUID. The pilot is a live demo tenant and must never be
# touched by a stress-residue sweep, even if E2E_STRESS_TENANT_ID is somehow
# misconfigured to point at it.
PILOT_TENANT_UUID = "5bad4a34-6ee3-4566-9053-741b7375a9cf"

# Prefix-bearing text fields per collection. A row counts as residue if ANY of
# these start with ``E2E_``. ``stress_prefix`` is the explicit marker the stress
# seeder writes; the text fields catch contracts created via the live API by
# stress specs (which carry the prefix in their content but no marker).
CONTRACT_FIELDS = ("company_name", "rate_code", "contact_email", "notes")
MICE_ACCOUNT_FIELDS = ("name", "tax_no", "email", "notes", "stress_prefix")


def _prefix_or(fields: tuple[str, ...]) -> dict:
    return {"$or": [{f: {"$regex": E2E_PREFIX_REGEX}} for f in fields]}


async def _scan_kind(
    coll_name: str,
    tenant_id: str,
    cutoff: datetime,
    fields: tuple[str, ...],
) -> list[dict]:
    """Find E2E-prefixed rows older than ``cutoff`` for this tenant.

    The age guard checks both ``created_at`` and ``createdAt`` (legacy field
    name still present in some collections) and accepts either ISO strings or
    BSON datetime values — corporate contracts persist ``created_at`` as a BSON
    datetime, the stress seeder writes ISO strings.
    """
    cutoff_iso = cutoff.isoformat()
    q: dict = {
        "tenant_id": tenant_id,
        "$and": [
            _prefix_or(fields),
            {
                "$or": [
                    {"created_at": {"$lte": cutoff_iso}},
                    {"created_at": {"$lte": cutoff}},
                    {"createdAt": {"$lte": cutoff_iso}},
                    {"createdAt": {"$lte": cutoff}},
                ]
            },
        ],
    }
    # Stream the full result set rather than capping with to_list(length=N): a
    # leaking stress run can plausibly produce far more than a few thousand
    # residue rows, and silent truncation would make the cleanup permanently
    # fall behind on every nightly run.
    cursor = db[coll_name].find(q, {"_id": 0}).max_time_ms(60000)
    out: list[dict] = []
    async for doc in cursor:
        out.append(doc)
    return out


async def scan(tenant_id: str, hours: int) -> dict:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    contracts = await _scan_kind(
        "corporate_contracts", tenant_id, cutoff, CONTRACT_FIELDS
    )
    accounts = await _scan_kind(
        "mice_accounts", tenant_id, cutoff, MICE_ACCOUNT_FIELDS
    )
    return {
        "cutoff": cutoff.isoformat(),
        "corporate_contracts": contracts,
        "mice_accounts": accounts,
    }


async def apply(tenant_id: str, found: dict) -> dict:
    """Hard-delete the residue rows so the global unique index can rebuild.

    Every delete is re-scoped to ``tenant_id`` so a stale id list can never
    reach another tenant's rows.
    """
    deleted = {"corporate_contracts": 0, "mice_accounts": 0}
    for coll_name in ("corporate_contracts", "mice_accounts"):
        ids = [d.get("id") for d in found[coll_name] if d.get("id")]
        if ids:
            res = await db[coll_name].delete_many(
                {"tenant_id": tenant_id, "id": {"$in": ids}}
            )
            deleted[coll_name] = res.deleted_count
    return deleted


async def record_scan(summary: dict) -> None:
    """Persist a summary row so admin dashboards / alerts can poll it."""
    try:
        await db.stress_crm_residue_scans.insert_one(summary)
    except Exception as e:  # pragma: no cover — best-effort metric
        logger.warning("[stress-crm-residue] metric insert failed: %s", e)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stress tenant CRM residue sweep (corporate_contracts + "
                    "mice_accounts)."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Yaş eşiği (saat). Bu süreden eski E2E_ prefix'li kayıtlar hedeflenir.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Bulduklarını uygula (sil). Aksi halde dry-run.",
    )
    args = parser.parse_args()

    tenant_id = os.environ.get("E2E_STRESS_TENANT_ID", "").strip()
    if not tenant_id:
        logger.error(
            "E2E_STRESS_TENANT_ID env var tanımlı değil — fail-closed; "
            "production guard tetiklendi."
        )
        return 2

    # Pilot exclusion guard: refuse if the resolved tenant is the pilot, via
    # either the PILOT_TENANT_ID env or the known pilot UUID (pilot_drift=0).
    pilot_tid = os.environ.get("PILOT_TENANT_ID", "").strip()
    if tenant_id == PILOT_TENANT_UUID or (pilot_tid and tenant_id == pilot_tid):
        logger.error(
            "E2E_STRESS_TENANT_ID pilot tenant'a (%s) eşit — fail-closed; "
            "stress residue sweep pilot'a dokunamaz.",
            tenant_id,
        )
        return 2

    if args.apply and os.environ.get("E2E_ALLOW_STRESS_CLEANUP", "").lower() != "true":
        logger.error(
            "--apply için E2E_ALLOW_STRESS_CLEANUP=true gerekli — fail-closed."
        )
        return 2

    logger.info(
        "[stress-crm-residue] tenant=%s hours=%d mode=%s",
        tenant_id,
        args.hours,
        "APPLY" if args.apply else "DRY-RUN",
    )

    found = await scan(tenant_id, args.hours)
    counts = {
        "corporate_contracts": len(found["corporate_contracts"]),
        "mice_accounts": len(found["mice_accounts"]),
    }
    total = sum(counts.values())

    applied = {"corporate_contracts": 0, "mice_accounts": 0}
    if args.apply and total > 0:
        applied = await apply(tenant_id, found)

    summary = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "hours": args.hours,
        "mode": "apply" if args.apply else "dry_run",
        "cutoff": found["cutoff"],
        "found": counts,
        "found_total": total,
        "applied": applied,
        "sample_contract_ids": [
            c.get("id") for c in found["corporate_contracts"][:10]
        ],
        "sample_account_ids": [
            a.get("id") for a in found["mice_accounts"][:10]
        ],
    }
    await record_scan(summary)

    print("=" * 60)
    print(
        f"Stress CRM residue sweep "
        f"({'APPLY' if args.apply else 'DRY-RUN'}) tenant={tenant_id}"
    )
    print("=" * 60)
    for k, v in counts.items():
        print(f"  {k:20s} -> {v}")
    print(f"  {'TOPLAM':20s} -> {total}")
    if args.apply:
        print("  -- applied (deleted) --")
        for k, v in applied.items():
            print(f"  {k:20s} -> {v}")
    print(f"  metric row          -> stress_crm_residue_scans @ {summary['scanned_at']}")

    if total > 0:
        logger.warning(
            "[stress-crm-residue] %d artık CRM kaydı bulundu "
            "(corporate_contracts=%d mice_accounts=%d) — uniqueness backstop "
            "riski; stress cleanup'ı kontrol et.",
            total,
            counts["corporate_contracts"],
            counts["mice_accounts"],
        )
        # Non-zero exit when residue exists in dry-run mode so cron/CI can alert.
        # When --apply succeeds we still exit 0 (the residue was handled).
        if not args.apply:
            return 1
    else:
        logger.info("[stress-crm-residue] residue=0, stress tenant temiz.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
