"""Fail-safe reconciliation backstop for open-folio balances (Task #390).

Background
----------
POS folio charges are applied asynchronously by the Outbox/Compensation
"B" path (``core.pos_folio_consumer``): the hot path durably writes the
order + an outbox event, and a worker later inserts the ``folio_charges``
row(s) and recomputes ``folio.balance``. That async gap leaves a narrow
inconsistency window: between an event being applied and the balance
recalc, or if an event lands in a permanent-failure class, or if a
consumer misses a corner case, ``folio.balance`` (a cached value) can drift
from the authoritative ledger total.

Authoritative source of truth
-----------------------------
``folio.balance`` is a CACHE. The authoritative balance is the SAME formula
the B path itself uses to set it — ``core.utils.calculate_folio_balance`` /
``pos_folio_consumer._recalc_folio_balance``:

    SUM(folio_charges.total||amount  WHERE voided == False)
  - SUM(payments.amount             WHERE voided == False)

It is NOT the immutable ``folio_ledger`` audit stream: the POS B path never
writes to ``folio_ledger``, so reconciling against the ledger would MISS the
exact drift this backstop exists to catch (and double-count entries the
ledger records via a different path). The existing
``ReconciliationEngine`` (ledger vs ``folio.balance``) is a complementary
audit-integrity check; this backstop is the operational B-path safety net.

This is a per-tenant scheduled backstop: for every open folio it recomputes
the authoritative balance, reports drifting folios (id + difference, no
PII), and in apply mode repairs ``folio.balance`` from the authoritative
total. dry-run is the default; apply is gated twice (CLI flag + env). When
B is healthy this routinely reports ``found_total == 0``; sustained drift is
a regression signal in B.

Safety contract
---------------
* dry-run by default — no mutation, report only.
* ``--apply`` requires ``FOLIO_RECON_ALLOW_APPLY=true`` (fail-closed). The
  destructive path is opt-in twice (CLI flag + env).
* Pilot is never repaired (``pilot_drift = 0``): both the known pilot UUID
  and ``PILOT_TENANT_ID`` (if set) are excluded from apply. Targeting the
  pilot explicitly with ``--apply`` is refused (rc 2). In an all-tenant
  apply run the pilot is still scanned/reported but never mutated.
* Tenant-scoped end to end: every read and every repair update is filtered
  by ``tenant_id`` (cross-tenant blast radius = 0). Repairs are additionally
  re-scoped to ``status == open`` so a folio closed mid-run is left alone.
* A small grace window (``FOLIO_RECON_GRACE_MINUTES``, default 5) skips
  folios touched within the last few minutes so an in-flight async apply is
  not mis-flagged as drift.
* Repair only RECOMPUTES the cached balance from the authoritative ledger;
  it never invents, voids, or moves money, so B's idempotency/guarantees are
  untouched.

Usage
-----
    # Default: dry-run, all tenants with open folios, no writes
    python -m scripts.reconcile_folio_balances

    # Single tenant
    python -m scripts.reconcile_folio_balances --tenant <uuid>

    # Apply (requires FOLIO_RECON_ALLOW_APPLY=true)
    FOLIO_RECON_ALLOW_APPLY=true \
        python -m scripts.reconcile_folio_balances --apply

Operational metric
------------------
Every tenant scanned inserts a summary doc into
``folio_balance_recon_scans`` (timestamp, mode, checked/drift/repaired
counts, sample drifting folio ids + differences — no PII). Any row with
``found_total > 0`` after a run is an actionable signal that B is leaking.
In dry-run, a non-zero ``found_total`` makes the process exit 1 so cron/CI
can alert.
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

from core.tenant_db import get_system_db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reconcile_folio_balances")

# Known pilot tenant UUID — a live demo tenant that must never be mutated by
# this backstop, even if PILOT_TENANT_ID is unset/misconfigured.
PILOT_TENANT_UUID = "5bad4a34-6ee3-4566-9053-741b7375a9cf"

# Money tolerance: differences below this are floating-point noise, not drift.
TOLERANCE = 0.01

DEFAULT_GRACE_MINUTES = int(os.environ.get("FOLIO_RECON_GRACE_MINUTES", "5"))


def pilot_tenant_ids() -> set[str]:
    """Tenant ids the apply path must never touch (pilot_drift = 0)."""
    ids = {PILOT_TENANT_UUID}
    env_pilot = os.environ.get("PILOT_TENANT_ID", "").strip()
    if env_pilot:
        ids.add(env_pilot)
    return ids


def _parse_dt(value) -> datetime | None:
    """Best-effort parse of an ISO string or BSON datetime to aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


async def list_open_folio_tenants() -> list[str]:
    """Distinct tenant ids that currently have at least one open folio."""
    db = get_system_db()
    try:
        ids = await db.folios.distinct("tenant_id", {"status": "open"})
    except Exception as exc:  # pragma: no cover — defensive
        logger.error("[folio-recon] distinct tenant scan failed: %s", exc)
        return []
    return [t for t in ids if t]


async def _authoritative_balances(tenant_id: str, folio_ids: list[str]) -> dict[str, float]:
    """Bulk authoritative balance per folio.

    Mirrors ``core.utils.calculate_folio_balance`` /
    ``pos_folio_consumer._recalc_folio_balance`` EXACTLY (same ``voided ==
    False`` match, same ``total||amount`` fallback) so the recomputed value
    reproduces what the B path would have written.
    """
    if not folio_ids:
        return {}
    db = get_system_db()
    ch_pipe = [
        {
            "$match": {
                "tenant_id": tenant_id,
                "folio_id": {"$in": folio_ids},
                "voided": False,
            }
        },
        {
            "$group": {
                "_id": "$folio_id",
                "total": {"$sum": {"$ifNull": ["$total", "$amount"]}},
            }
        },
    ]
    pay_pipe = [
        {
            "$match": {
                "tenant_id": tenant_id,
                "folio_id": {"$in": folio_ids},
                "voided": False,
            }
        },
        {"$group": {"_id": "$folio_id", "total": {"$sum": "$amount"}}},
    ]
    ch_rows = await db.folio_charges.aggregate(ch_pipe).to_list(len(folio_ids))
    pay_rows = await db.payments.aggregate(pay_pipe).to_list(len(folio_ids))
    charges = {r["_id"]: float(r["total"] or 0.0) for r in ch_rows}
    payments = {r["_id"]: float(r["total"] or 0.0) for r in pay_rows}
    out: dict[str, float] = {}
    for fid in folio_ids:
        out[fid] = round(charges.get(fid, 0.0) - payments.get(fid, 0.0), 2)
    return out


async def scan_tenant(tenant_id: str, grace_minutes: int) -> dict:
    """Find open folios whose cached balance drifts from the authoritative.

    Returns ``{"checked": int, "skipped_fresh": int, "drifts": [...]}`` where
    each drift carries only non-PII identifiers and the numeric difference.
    """
    db = get_system_db()
    open_folios = await db.folios.find(
        {"tenant_id": tenant_id, "status": "open"},
        {"_id": 0, "id": 1, "booking_id": 1, "balance": 1, "updated_at": 1},
    ).to_list(100000)

    cutoff = datetime.now(UTC) - timedelta(minutes=max(0, grace_minutes))
    fresh_skipped = 0
    candidates: list[dict] = []
    for f in open_folios:
        if not f.get("id"):
            continue
        updated = _parse_dt(f.get("updated_at"))
        if updated is not None and updated > cutoff:
            # Touched within the grace window — an in-flight async apply may
            # still be settling; don't mis-flag it as drift.
            fresh_skipped += 1
            continue
        candidates.append(f)

    folio_ids = [f["id"] for f in candidates]
    authoritative = await _authoritative_balances(tenant_id, folio_ids)

    drifts: list[dict] = []
    for f in candidates:
        fid = f["id"]
        auth = authoritative.get(fid, 0.0)
        cached = round(float(f.get("balance", 0.0) or 0.0), 2)
        difference = round(auth - cached, 2)
        if abs(difference) >= TOLERANCE:
            drifts.append(
                {
                    "folio_id": fid,
                    "booking_id": f.get("booking_id", ""),
                    "cached_balance": cached,
                    "authoritative_balance": auth,
                    "difference": difference,
                }
            )
    return {
        "checked": len(candidates),
        "skipped_fresh": fresh_skipped,
        "drifts": drifts,
    }


async def apply_tenant(tenant_id: str, drifts: list[dict]) -> int:
    """Repair drifting folios: recompute the cached balance from authority.

    Each repair is re-scoped to ``tenant_id`` AND ``status == open`` and the
    authoritative balance is recomputed fresh (not the stale scan value) so a
    folio mutated/closed between scan and apply is handled correctly. Returns
    the number of folios whose balance was rewritten.
    """
    db = get_system_db()
    repaired = 0
    now_iso = datetime.now(UTC).isoformat()
    for d in drifts:
        fid = d.get("folio_id")
        if not fid:
            continue
        fresh = await _authoritative_balances(tenant_id, [fid])
        auth = fresh.get(fid, 0.0)
        res = await db.folios.update_one(
            {"tenant_id": tenant_id, "id": fid, "status": "open"},
            {"$set": {"balance": auth, "updated_at": now_iso}},
        )
        if res.modified_count:
            repaired += 1
    return repaired


async def record_scan(summary: dict) -> None:
    """Persist a summary row so admin dashboards / alerts can poll it."""
    db = get_system_db()
    try:
        await db.folio_balance_recon_scans.insert_one(summary)
    except Exception as e:  # pragma: no cover — best-effort metric
        logger.warning("[folio-recon] metric insert failed: %s", e)


async def reconcile_tenant(
    tenant_id: str,
    do_apply: bool,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> dict:
    """Scan one tenant, optionally repair, write a metric row, return summary.

    ``do_apply`` is honored only for non-pilot tenants; the pilot is always
    scanned/reported but never mutated (pilot_drift = 0).
    """
    is_pilot = tenant_id in pilot_tenant_ids()
    effective_apply = do_apply and not is_pilot

    result = await scan_tenant(tenant_id, grace_minutes)
    drifts = result["drifts"]
    found_total = len(drifts)

    repaired = 0
    if effective_apply and found_total > 0:
        repaired = await apply_tenant(tenant_id, drifts)

    summary = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "mode": "apply" if effective_apply else "dry_run",
        "grace_minutes": grace_minutes,
        "folios_checked": result["checked"],
        "skipped_fresh": result["skipped_fresh"],
        "found_total": found_total,
        "repaired": repaired,
        "pilot_skipped_apply": bool(do_apply and is_pilot),
        # Sample drifts: identifiers + numeric difference only — never PII.
        "sample_drifts": [
            {
                "folio_id": d["folio_id"],
                "booking_id": d["booking_id"],
                "cached_balance": d["cached_balance"],
                "authoritative_balance": d["authoritative_balance"],
                "difference": d["difference"],
            }
            for d in drifts[:20]
        ],
    }
    await record_scan(summary)

    if found_total > 0:
        logger.warning(
            "[folio-recon] tenant=%s drift folios=%d repaired=%d mode=%s",
            tenant_id,
            found_total,
            repaired,
            summary["mode"],
        )
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser(description="Open-folio balance reconciliation backstop (Task #390).")
    parser.add_argument(
        "--tenant",
        default="",
        help="Tek tenant'a kapsa. Boşsa açık folyosu olan TÜM tenant'lar.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Sapan folyo bakiyelerini otorite toplamdan onar. Aksi halde dry-run.",
    )
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=DEFAULT_GRACE_MINUTES,
        help="Son N dakikada dokunulan folyoları atla (in-flight apply'ı yanlış pozitif saymamak için).",
    )
    args = parser.parse_args()

    if args.apply and os.environ.get("FOLIO_RECON_ALLOW_APPLY", "").lower() != "true":
        logger.error("--apply için FOLIO_RECON_ALLOW_APPLY=true gerekli — fail-closed.")
        return 2

    target_tenant = args.tenant.strip()
    # Explicitly targeting the pilot with --apply is a loud operator error.
    if args.apply and target_tenant and target_tenant in pilot_tenant_ids():
        logger.error(
            "--tenant pilot tenant'a (%s) eşit ve --apply verildi — fail-closed; mutabakat backstop'u pilot'a dokunamaz.",
            target_tenant,
        )
        return 2

    if target_tenant:
        tenants = [target_tenant]
    else:
        tenants = await list_open_folio_tenants()

    logger.info(
        "[folio-recon] tenants=%d mode=%s grace=%dm",
        len(tenants),
        "APPLY" if args.apply else "DRY-RUN",
        args.grace_minutes,
    )

    grand_found = 0
    grand_repaired = 0
    grand_checked = 0
    summaries: list[dict] = []
    for tid in tenants:
        summary = await reconcile_tenant(tid, args.apply, args.grace_minutes)
        summaries.append(summary)
        grand_found += summary["found_total"]
        grand_repaired += summary["repaired"]
        grand_checked += summary["folios_checked"]

    print("=" * 60)
    print(f"Folio balance reconciliation ({'APPLY' if args.apply else 'DRY-RUN'}) tenants={len(tenants)}")
    print("=" * 60)
    for s in summaries:
        line = f"  tenant={s['tenant_id']} checked={s['folios_checked']} drift={s['found_total']} repaired={s['repaired']}"
        if s.get("pilot_skipped_apply"):
            line += " (pilot: apply skipped)"
        print(line)
    print("-" * 60)
    print(f"  TOPLAM checked={grand_checked} drift={grand_found} repaired={grand_repaired}")
    print("  metric rows -> folio_balance_recon_scans")

    if grand_found > 0:
        logger.warning(
            "[folio-recon] %d sapan folyo bulundu (checked=%d repaired=%d) — B (POS->folio) yolunu kontrol et.",
            grand_found,
            grand_checked,
            grand_repaired,
        )
        # Non-zero exit when drift remains unhandled (dry-run) so cron/CI can
        # alert. Apply that repaired everything still exits 0.
        if not args.apply or grand_repaired < grand_found:
            return 1
    else:
        logger.info("[folio-recon] drift=0, açık folyolar mutabık.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
