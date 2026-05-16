"""Nightly orphan-data sweep for E2E test residue in the pilot tenant.

Background
----------
Task #175 enabled business-flow E2E suites (`frontend/e2e-business/`) that
write real `bookings` / `guests` / `folio_charges` rows into the pilot tenant
with an ``E2E_<ts>_<KIND>`` label prefix. The ``20-recap`` spec normally
cancels/voids that residue at the end of each run, but if a test times out
or the recap itself fails, the rows linger and pollute pilot
performance/reports.

This maintenance script is the safety net: a periodic sweep that lists (and
optionally cancels/voids) ``E2E_`` prefixed rows older than 24 hours, scoped
strictly to the pilot tenant.

Safety contract
---------------
* ``E2E_PILOT_TENANT_ID`` env var **must** be set. The script refuses to
  scan or mutate anything without it (fail-closed; cross-tenant blast
  radius = 0).
* ``--apply`` requires ``E2E_ALLOW_PILOT_CLEANUP=true`` (fail-closed). The
  default is dry-run; the destructive path is opt-in twice (CLI flag + env).
* Only rows whose label/name/description starts with ``E2E_`` AND are older
  than ``--hours`` (default 24h) are touched. The age guard prevents racing
  an in-flight test run.
* Bookings: status flipped to ``cancelled`` (mirrors
  ``/api/pms-core/cancel``); inventory release is left to the standard
  cancel pipeline on next ARI sync.
* Charges: ``voided=true`` (mirrors ``/api/pms-core/folio/void-charge``);
  folio totals are not recomputed by this script — the next folio fetch
  resolves them.
* Guests are reported but never auto-deleted: they may be referenced by
  surviving booking/folio rows and the cost of leaving them is low.

Usage
-----
    # Default: dry-run, list residue, no writes
    python -m scripts.cleanup_e2e_pilot_residue

    # Apply (requires E2E_ALLOW_PILOT_CLEANUP=true)
    python -m scripts.cleanup_e2e_pilot_residue --apply

    # Custom age window (default 24h)
    python -m scripts.cleanup_e2e_pilot_residue --hours 12

Operational metric
------------------
Every run inserts a summary doc into ``e2e_residue_scans`` with timestamp,
mode, counts per kind, and applied counts. The admin dashboard / alerting
can poll this collection: any row with ``found_total > 0`` after the next
nightly run is an actionable signal that the recap spec is leaking.
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
logger = logging.getLogger("cleanup_e2e_pilot_residue")

E2E_PREFIX_REGEX = r"^E2E_"

BOOKING_FIELDS = ("guest_name", "label", "notes", "special_requests")
GUEST_FIELDS = ("first_name", "last_name")
CHARGE_FIELDS = ("description", "note", "label")


def _prefix_or(fields: tuple[str, ...]) -> dict:
    return {"$or": [{f: {"$regex": E2E_PREFIX_REGEX}} for f in fields]}


async def _scan_kind(
    coll_name: str,
    tenant_id: str,
    cutoff: datetime,
    fields: tuple[str, ...],
    extra_filter: dict | None = None,
) -> list[dict]:
    """Find E2E-prefixed rows older than ``cutoff`` for this tenant.

    The age guard checks both ``created_at`` and ``createdAt`` (legacy field
    name still present in some collections) and accepts either ISO strings
    or BSON datetime values.
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
    if extra_filter:
        q["$and"].append(extra_filter)
    # Stream the full result set rather than capping with to_list(length=N):
    # an in-flight test storm or a stuck recap can plausibly produce more
    # than a few thousand residue rows, and silent truncation would make
    # the cleanup permanently fall behind on every nightly run.
    cursor = db[coll_name].find(q, {"_id": 0}).max_time_ms(60000)
    out: list[dict] = []
    async for doc in cursor:
        out.append(doc)
    return out


async def scan(tenant_id: str, hours: int) -> dict:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    bookings = await _scan_kind(
        "bookings",
        tenant_id,
        cutoff,
        BOOKING_FIELDS,
        extra_filter={"status": {"$nin": ["cancelled", "no_show"]}},
    )
    guests = await _scan_kind("guests", tenant_id, cutoff, GUEST_FIELDS)
    charges = await _scan_kind(
        "folio_charges",
        tenant_id,
        cutoff,
        CHARGE_FIELDS,
        extra_filter={"voided": {"$ne": True}},
    )
    return {
        "cutoff": cutoff.isoformat(),
        "bookings": bookings,
        "guests": guests,
        "folio_charges": charges,
    }


async def apply(tenant_id: str, found: dict) -> dict:
    now_iso = datetime.now(UTC).isoformat()
    cancelled = 0
    voided = 0

    booking_ids = [b.get("id") for b in found["bookings"] if b.get("id")]
    if booking_ids:
        res = await db.bookings.update_many(
            {
                "tenant_id": tenant_id,
                "id": {"$in": booking_ids},
                "status": {"$nin": ["cancelled", "no_show"]},
            },
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": now_iso,
                    "cancellation_reason": "E2E pilot residue sweep",
                    "updated_at": now_iso,
                }
            },
        )
        cancelled = res.modified_count

    charge_ids = [c.get("id") for c in found["folio_charges"] if c.get("id")]
    if charge_ids:
        res = await db.folio_charges.update_many(
            {
                "tenant_id": tenant_id,
                "id": {"$in": charge_ids},
                "voided": {"$ne": True},
            },
            {
                "$set": {
                    "voided": True,
                    "voided_at": now_iso,
                    "void_reason": "E2E pilot residue sweep",
                    "updated_at": now_iso,
                }
            },
        )
        voided = res.modified_count

    return {"bookings_cancelled": cancelled, "charges_voided": voided}


async def record_scan(tenant_id: str, summary: dict) -> None:
    """Persist a summary row so admin dashboards / alerts can poll it."""
    try:
        await db.e2e_residue_scans.insert_one(summary)
    except Exception as e:  # pragma: no cover — best-effort metric
        logger.warning("[e2e-residue] metric insert failed: %s", e)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pilot tenant E2E residue sweep (Task #178)."
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
        help="Bulduklarını uygula (cancel/void). Aksi halde dry-run.",
    )
    args = parser.parse_args()

    tenant_id = os.environ.get("E2E_PILOT_TENANT_ID", "").strip()
    if not tenant_id:
        logger.error(
            "E2E_PILOT_TENANT_ID env var tanımlı değil — fail-closed; "
            "production guard tetiklendi."
        )
        return 2

    if args.apply and os.environ.get("E2E_ALLOW_PILOT_CLEANUP", "").lower() != "true":
        logger.error(
            "--apply için E2E_ALLOW_PILOT_CLEANUP=true gerekli — fail-closed."
        )
        return 2

    logger.info(
        "[e2e-residue] tenant=%s hours=%d mode=%s",
        tenant_id,
        args.hours,
        "APPLY" if args.apply else "DRY-RUN",
    )

    found = await scan(tenant_id, args.hours)
    counts = {
        "bookings": len(found["bookings"]),
        "guests": len(found["guests"]),
        "folio_charges": len(found["folio_charges"]),
    }
    total = sum(counts.values())

    applied = {"bookings_cancelled": 0, "charges_voided": 0}
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
        "sample_booking_ids": [b.get("id") for b in found["bookings"][:10]],
        "sample_charge_ids": [c.get("id") for c in found["folio_charges"][:10]],
        "sample_guest_ids": [g.get("id") for g in found["guests"][:10]],
    }
    await record_scan(tenant_id, summary)

    print("=" * 60)
    print(
        f"E2E pilot residue sweep "
        f"({'APPLY' if args.apply else 'DRY-RUN'}) tenant={tenant_id}"
    )
    print("=" * 60)
    for k, v in counts.items():
        print(f"  {k:18s} -> {v}")
    print(f"  {'TOPLAM':18s} -> {total}")
    if args.apply:
        print("  -- applied --")
        for k, v in applied.items():
            print(f"  {k:18s} -> {v}")
    print(f"  metric row     -> e2e_residue_scans @ {summary['scanned_at']}")

    if total > 0:
        logger.warning(
            "[e2e-residue] %d artık kayıt bulundu (bookings=%d guests=%d charges=%d) — "
            "recap cleanup'ı kontrol et.",
            total,
            counts["bookings"],
            counts["guests"],
            counts["folio_charges"],
        )
        # Non-zero exit when residue exists in dry-run mode so cron/CI can alert.
        # When --apply succeeds we still exit 0 (the residue was handled).
        if not args.apply:
            return 1
    else:
        logger.info("[e2e-residue] residue=0, pilot temiz.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
