"""Task #215 — one-off dedupe so the Task #205 CRM unique indexes can build.

Background
----------
Task #205 added DB-level partial unique indexes that close the read-then-insert
race in the application-level duplicate guards:

* ``mice_accounts``      → ``uniq_mice_acc_client_taxno`` /
  ``uniq_mice_acc_client_email`` (partial filter
  ``{account_type: "client", <field>: {$gt: "", $type: "string"}}``)
* ``corporate_contracts``→ ``uniq_corp_contract_rate_code`` /
  ``uniq_corp_contract_contact_email`` (partial filter
  ``{<field>: {$gt: "", $type: "string"}}``)

Each ``create_index`` is wrapped in its own ``try/except`` (see
``_ensure_indexes`` in ``routers/mice.py`` and ``_ensure_contract_indexes`` in
``domains/revenue/rms_router/sales.py``). So if a tenant already holds
pre-existing duplicate rows, the build fails *silently* and that one race
backstop stays disabled forever — the app-level guard still runs, but the
race-proof DB backstop never activates for that collection.

This script is the one-off remediation: it finds the existing duplicates that
would block each index and (with ``--apply``) retires the non-canonical rows to
a safe, reversible state so the unique indexes build cleanly.

Dedupe strategy (canonical = oldest by ``created_at``, tiebreak ``id``)
----------------------------------------------------------------------
* ``mice_accounts``: the index partial filter keys on ``account_type ==
  "client"``. Non-canonical client duplicates are retired by flipping
  ``account_type`` ``"client" -> "client_merged"``. This removes them from
  *both* unique indexes **and** from the CRM client list (``list_accounts``
  shows only ``account_type`` missing/``"client"``) and from the app guard
  (``_CLIENT_ACCT_FILTER``) — without deleting any data. Fully reversible.
* ``corporate_contracts``: the index partial filter has no discriminator field,
  so the only way to drop a row from the partial index without deleting it is
  to make the conflicting field fall outside ``{$gt: "", $type: "string"}``.
  Non-canonical duplicates get the conflicting field backed up under
  ``dedupe_backup.<field>`` and the live field set to ``""`` (empty string is
  excluded by ``$gt: ""`` *and* ignored by the app guard, which skips blanks).

Both strategies are idempotent: a second run finds nothing because retired rows
no longer match the duplicate scan (``account_type != "client"`` / blank field).

Safety contract (fail-closed)
-----------------------------
* Dry-run is the default. ``--apply`` requires ``ALLOW_CRM_DEDUPE=true``.
* The pilot tenant (``E2E_PILOT_TENANT_ID`` or ``PILOT_TENANT_ID``) is NEVER
  mutated unless ``ALLOW_PILOT_CRM_DEDUPE=true`` is *also* set. In apply mode
  without that opt-in, pilot duplicates are reported but skipped.
* ``--apply`` refuses to run unless a pilot tenant id is known (so the pilot
  exclusion guard can actually exclude something) — unless ``--tenant`` pins a
  single non-pilot tenant explicitly.
* ``--tenant`` restricts the whole run to one tenant.

Usage
-----
    # Default: dry-run, report duplicates across all tenants
    python -m scripts.dedupe_crm_uniqueness

    # Restrict to one tenant
    python -m scripts.dedupe_crm_uniqueness --tenant <tid>

    # Apply (requires ALLOW_CRM_DEDUPE=true; pilot skipped unless opted in)
    ALLOW_CRM_DEDUPE=true python -m scripts.dedupe_crm_uniqueness --apply

    # Also attempt to build the unique indexes afterwards and report results
    ALLOW_CRM_DEDUPE=true python -m scripts.dedupe_crm_uniqueness --apply \
        --build-indexes

Exit codes
----------
* ``0`` — no remaining (un-skipped) duplicate groups; the indexes can build.
* ``1`` — duplicate groups remain (dry-run, or pilot skipped without opt-in).
* ``2`` — refused (fail-closed guard tripped).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("dedupe_crm_uniqueness")

DEDUPE_REASON = "task #215 CRM uniqueness dedupe"

# (collection, fields, base_match, strategy) — base_match mirrors each unique
# index's partialFilterExpression so the scan finds exactly the rows that would
# block the build.
MICE_COLL = "mice_accounts"
MICE_FIELDS = ("tax_no", "email")
MICE_BASE_MATCH = {"account_type": "client"}

CONTRACT_COLL = "corporate_contracts"
CONTRACT_FIELDS = ("rate_code", "contact_email")
CONTRACT_BASE_MATCH: dict = {}

# Unique index definitions (kept in lockstep with the app code) for --build-indexes.
MICE_INDEXES = [
    ("tax_no", "uniq_mice_acc_client_taxno"),
    ("email", "uniq_mice_acc_client_email"),
]
CONTRACT_INDEXES = [
    ("rate_code", "uniq_corp_contract_rate_code"),
    ("contact_email", "uniq_corp_contract_contact_email"),
]


def _canonical_sort_key(doc: dict) -> tuple:
    """Oldest ``created_at`` wins; rows without one sort last. Tiebreak ``id``.

    ``created_at`` is a datetime in ``corporate_contracts`` and an ISO string in
    ``mice_accounts``; normalize both to a comparable ISO string.
    """
    ca = doc.get("created_at")
    if ca is None:
        return (1, "", str(doc.get("id", "")))
    if isinstance(ca, datetime):
        ca = ca.isoformat()
    return (0, str(ca), str(doc.get("id", "")))


async def _find_groups(
    db, coll_name: str, fields: tuple[str, ...], base_match: dict,
    tenant: str | None,
) -> list[dict]:
    """Return duplicate groups that block the partial unique indexes.

    A group = rows sharing the same (tenant_id, <field>) where <field> is a
    non-empty string and the base_match (index partial filter) holds, with
    count > 1.
    """
    groups: list[dict] = []
    for field in fields:
        match: dict = {**base_match, field: {"$type": "string", "$gt": ""}}
        if tenant:
            match["tenant_id"] = tenant
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": {"tenant_id": "$tenant_id", "value": f"${field}"},
                "docs": {"$push": {"id": "$id", "created_at": "$created_at"}},
                "count": {"$sum": 1},
            }},
            {"$match": {"count": {"$gt": 1}}},
        ]
        async for g in db[coll_name].aggregate(pipeline):
            docs = sorted(g["docs"], key=_canonical_sort_key)
            canonical = docs[0]
            losers = docs[1:]
            groups.append({
                "field": field,
                "tenant_id": g["_id"]["tenant_id"],
                "value": g["_id"]["value"],
                "count": g["count"],
                "canonical_id": canonical.get("id"),
                "loser_ids": [d.get("id") for d in losers if d.get("id")],
            })
    return groups


def _partition_pilot(groups: list[dict], pilot_tid: str | None,
                     allow_pilot: bool) -> tuple[list[dict], list[dict]]:
    """Split groups into actionable vs pilot-skipped (when not opted in)."""
    if not pilot_tid or allow_pilot:
        return groups, []
    actionable = [g for g in groups if g["tenant_id"] != pilot_tid]
    skipped = [g for g in groups if g["tenant_id"] == pilot_tid]
    return actionable, skipped


async def _apply_mice(db, groups: list[dict]) -> int:
    """Retire non-canonical mice client duplicates by flipping account_type."""
    now_iso = datetime.now(UTC).isoformat()
    retired = 0
    # A row can lose on both tax_no and email; collect per (tenant, id) so we
    # flip account_type exactly once and record every conflict field.
    per_row: dict[tuple[str, str], dict] = {}
    for g in groups:
        for lid in g["loser_ids"]:
            key = (g["tenant_id"], lid)
            entry = per_row.setdefault(
                key, {"fields": [], "canonical": {}})
            entry["fields"].append(g["field"])
            entry["canonical"][g["field"]] = g["canonical_id"]
    for (tid, lid), entry in per_row.items():
        res = await db[MICE_COLL].update_one(
            {"tenant_id": tid, "id": lid, "account_type": "client"},
            {"$set": {
                "account_type": "client_merged",
                "dedupe_status": "merged",
                "dedupe_conflict_fields": entry["fields"],
                "dedupe_canonical": entry["canonical"],
                "dedupe_merged_at": now_iso,
                "dedupe_reason": DEDUPE_REASON,
            }},
        )
        retired += res.modified_count
    return retired


async def _apply_contracts(db, groups: list[dict]) -> int:
    """Retire non-canonical contract duplicates by backing up + blanking field."""
    now_iso = datetime.now(UTC).isoformat()
    blanked = 0
    for g in groups:
        field = g["field"]
        value = g["value"]
        for lid in g["loser_ids"]:
            res = await db[CONTRACT_COLL].update_one(
                {"tenant_id": g["tenant_id"], "id": lid,
                 field: {"$type": "string", "$gt": ""}},
                {"$set": {
                    f"dedupe_backup.{field}": value,
                    field: "",
                    f"dedupe_canonical.{field}": g["canonical_id"],
                    "dedupe_status": "superseded",
                    "dedupe_merged_at": now_iso,
                    "dedupe_reason": DEDUPE_REASON,
                }},
            )
            blanked += res.modified_count
    return blanked


async def _build_indexes(db, coll_name: str, defs: list[tuple[str, str]],
                         partial_extra: dict) -> list[tuple[str, bool, str]]:
    """Attempt to create each unique index; report per-index result.

    Mirrors the app-code definitions exactly. Index creation is collection-wide
    (not tenant scoped), so a build only succeeds if *every* tenant is clean.
    """
    results: list[tuple[str, bool, str]] = []
    for field, idx_name in defs:
        pfe = {**partial_extra, field: {"$gt": "", "$type": "string"}}
        try:
            await db[coll_name].create_index(
                [("tenant_id", 1), (field, 1)],
                unique=True, partialFilterExpression=pfe, name=idx_name,
            )
            results.append((idx_name, True, "built"))
        except Exception as exc:  # noqa: BLE001
            results.append((idx_name, False, str(exc)))
    return results


def _print_groups(title: str, groups: list[dict]) -> None:
    print(f"  {title}: {len(groups)} duplicate group(s)")
    for g in groups:
        # Avoid printing raw PII (email/tax_no) values; show counts only.
        print(
            f"    tenant={g['tenant_id']} field={g['field']} "
            f"count={g['count']} keep={g['canonical_id']} "
            f"retire={len(g['loser_ids'])}"
        )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dedupe CRM client accounts / corporate contracts so the "
                    "Task #205 unique indexes can build (Task #215)."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Write changes (default: dry-run).")
    parser.add_argument("--tenant", default=None,
                        help="Restrict to one tenant_id.")
    parser.add_argument("--build-indexes", action="store_true",
                        help="After dedupe, attempt to build the unique "
                             "indexes and report per-index result.")
    args = parser.parse_args()

    pilot_tid = (os.environ.get("E2E_PILOT_TENANT_ID")
                 or os.environ.get("PILOT_TENANT_ID") or "").strip() or None
    allow = os.environ.get("ALLOW_CRM_DEDUPE", "").lower() == "true"
    allow_pilot = os.environ.get("ALLOW_PILOT_CRM_DEDUPE", "").lower() == "true"

    if args.tenant and pilot_tid and args.tenant == pilot_tid and not allow_pilot:
        print(
            f"REFUSED: --tenant equals pilot tenant ({pilot_tid}); set "
            "ALLOW_PILOT_CRM_DEDUPE=true to opt in.",
            file=sys.stderr,
        )
        return 2

    if args.apply:
        if not allow:
            print("REFUSED: --apply requires ALLOW_CRM_DEDUPE=true "
                  "(fail-closed).", file=sys.stderr)
            return 2
        # Need to know the pilot id so the exclusion guard can exclude it —
        # unless a single explicit (non-pilot) tenant is pinned.
        if not pilot_tid and not args.tenant:
            print(
                "REFUSED: --apply requires E2E_PILOT_TENANT_ID or "
                "PILOT_TENANT_ID to be set (pilot exclusion guard), or pin a "
                "single tenant with --tenant.",
                file=sys.stderr,
            )
            return 2

    from core.tenant_db import get_system_db
    db = get_system_db()

    mode = "APPLY" if args.apply else "DRY-RUN"
    scope = f"tenant={args.tenant}" if args.tenant else "all tenants"
    logger.info("[crm-dedupe] mode=%s scope=%s pilot=%s allow_pilot=%s",
                mode, scope, pilot_tid or "(unset)", allow_pilot)

    mice_groups = await _find_groups(
        db, MICE_COLL, MICE_FIELDS, MICE_BASE_MATCH, args.tenant)
    contract_groups = await _find_groups(
        db, CONTRACT_COLL, CONTRACT_FIELDS, CONTRACT_BASE_MATCH, args.tenant)

    mice_do, mice_skip = _partition_pilot(mice_groups, pilot_tid, allow_pilot)
    ct_do, ct_skip = _partition_pilot(contract_groups, pilot_tid, allow_pilot)

    print("=" * 64)
    print(f"CRM uniqueness dedupe ({mode}) — {scope}")
    print("=" * 64)
    _print_groups("mice_accounts (client)", mice_do)
    if mice_skip:
        _print_groups("mice_accounts (PILOT — SKIPPED)", mice_skip)
    _print_groups("corporate_contracts", ct_do)
    if ct_skip:
        _print_groups("corporate_contracts (PILOT — SKIPPED)", ct_skip)

    applied = {"mice_retired": 0, "contracts_blanked": 0}
    if args.apply:
        applied["mice_retired"] = await _apply_mice(db, mice_do)
        applied["contracts_blanked"] = await _apply_contracts(db, ct_do)
        print("  -- applied --")
        print(f"    mice client rows retired   -> {applied['mice_retired']}")
        print(f"    contract fields blanked    -> {applied['contracts_blanked']}")

    # Post-apply re-scan: confirm nothing blocks the build any more (within the
    # scanned scope). In dry-run this just echoes the found groups.
    remaining_total = 0
    if args.apply:
        mice_after = await _find_groups(
            db, MICE_COLL, MICE_FIELDS, MICE_BASE_MATCH, args.tenant)
        ct_after = await _find_groups(
            db, CONTRACT_COLL, CONTRACT_FIELDS, CONTRACT_BASE_MATCH, args.tenant)
        m_do, _ = _partition_pilot(mice_after, pilot_tid, allow_pilot)
        c_do, _ = _partition_pilot(ct_after, pilot_tid, allow_pilot)
        remaining_total = len(m_do) + len(c_do)
        print(f"  re-scan remaining (actionable) -> {remaining_total}")
    else:
        remaining_total = len(mice_do) + len(ct_do)

    if args.build_indexes:
        if not args.apply:
            print("  --build-indexes ignored in dry-run (no changes written).")
        else:
            print("  -- build-indexes --")
            for idx_name, ok, msg in await _build_indexes(
                    db, MICE_COLL, MICE_INDEXES, {"account_type": "client"}):
                print(f"    {idx_name:30s} -> {'OK' if ok else 'FAIL: ' + msg}")
            for idx_name, ok, msg in await _build_indexes(
                    db, CONTRACT_COLL, CONTRACT_INDEXES, {}):
                print(f"    {idx_name:30s} -> {'OK' if ok else 'FAIL: ' + msg}")

    skipped_total = len(mice_skip) + len(ct_skip)
    if not args.apply and remaining_total > 0:
        logger.warning(
            "[crm-dedupe] %d duplicate group(s) block the indexes — run with "
            "--apply (ALLOW_CRM_DEDUPE=true) to remediate.", remaining_total)
        return 1
    if skipped_total > 0:
        logger.warning(
            "[crm-dedupe] %d pilot duplicate group(s) skipped — set "
            "ALLOW_PILOT_CRM_DEDUPE=true to remediate them.", skipped_total)
        return 1
    if args.apply and remaining_total > 0:
        logger.error(
            "[crm-dedupe] %d duplicate group(s) STILL remain after apply.",
            remaining_total)
        return 1
    logger.info("[crm-dedupe] no blocking duplicates remain in scope.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
