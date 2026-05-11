"""Tenant restore DRILL helper — Phase 1 (dry-run + guardrails only).

Pilot Readiness Checklist hard-blocker #3.

Phase 1 scope:
  * Builds a deterministic restore PLAN from a backup archive + classification.
  * Default = dry-run (no writes, no mongorestore invocation).
  * Hard guardrails:
      - --backup-archive, --tenant-id, --target-db all required
      - target-db == production DB ($DB_NAME) is REJECTED unless
        --allow-prod-target is passed
      - GLOBAL_EXCLUDE collections (secret stores, controlplane) are NEVER
        included in the plan, regardless of flags
      - UNKNOWN_REVIEW_REQUIRED collections are surfaced, never auto-included
  * --execute is wired but BLOCK verdict aborts before any subprocess runs.
    Real exercise of mongorestore is Phase 2 work.

Usage:
    # Dry-run (default):
    python tools/tenant_restore_drill.py \
        --backup-archive /var/backups/bk_20260511_020000_xxx \
        --tenant-id 64a1b2c3d4e5f6789abcdef0 \
        --target-db hotel_pms_drill_staging

    # Execute (Phase 2 only — requires real backup + staging DB):
    python tools/tenant_restore_drill.py [...] --execute

Exit codes:
    0 — plan generated (or execute completed successfully)
    1 — guardrail BLOCK (missing args, prod target without flag, no
        TENANT_SCOPED collections, etc.)
    2 — execute-time runtime failure (mongorestore exit != 0, archive missing)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Make backend/scripts/classify_tenant_scope.py importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend" / "scripts"))
import classify_tenant_scope  # noqa: E402


def build_plan(
    *,
    backup_archive: str,
    tenant_id: str,
    target_db: str,
    classification: dict,
) -> dict:
    """Pure function: assemble a restore plan from inputs + classification report."""
    return {
        "source_backup_archive": backup_archive,
        "target_tenant_id": tenant_id,
        "target_database": target_db,
        "collections_discovered": sum(
            len(classification.get(k, []))
            for k in (
                "TENANT_SCOPED",
                "GLOBAL_EXCLUDE",
                "UNKNOWN_REVIEW_REQUIRED",
                "SYSTEM_INTERNAL",
            )
        ),
        "tenant_scoped_collections": [
            e["name"] for e in classification.get("TENANT_SCOPED", [])
        ],
        "excluded_global_collections": [
            e["name"] for e in classification.get("GLOBAL_EXCLUDE", [])
        ],
        "unknown_collections_requiring_review": [
            e["name"] for e in classification.get("UNKNOWN_REVIEW_REQUIRED", [])
        ],
        "system_internal_skipped": [
            e["name"] for e in classification.get("SYSTEM_INTERNAL", [])
        ],
        "planned_restore_strategy": (
            "1) For each TENANT_SCOPED collection: mongorestore --gzip "
            "--nsInclude=<DB>.<col> --nsFrom=<DB>.<col> --nsTo=<TARGET_DB>.<col> "
            "from the backup archive.\n"
            "2) For each restored collection in TARGET_DB: "
            "deleteMany({tenant_id: {$ne: <TENANT_ID>}}) to prune cross-tenant docs.\n"
            "3) Validate per-collection counts (tenant_id == X) match expected; "
            "leak count (tenant_id != X) MUST equal 0.\n"
            "4) Run foreign-key integrity check (booking → guest → folio chain).\n"
            "5) Emit drill report with timestamps, counts, and verdict."
        ),
        "validation_queries": [
            'db.<col>.countDocuments({tenant_id: "<TENANT_ID>"}) > 0',
            'db.<col>.countDocuments({tenant_id: {$ne: "<TENANT_ID>"}}) == 0',
            "db.bookings.aggregate([{$lookup:{from:'guests',localField:'guest_id',"
            "foreignField:'_id',as:'g'}},{$match:{g:{$size:0}}}]).toArray() == []",
        ],
    }


def assess_risk(
    plan: dict,
    *,
    prod_db_name: str | None,
    allow_prod_target: bool,
) -> tuple[str, list[str]]:
    """Return (verdict, findings). verdict ∈ {OK, REVIEW, BLOCK}."""
    blockers: list[str] = []
    warnings: list[str] = []

    if not plan["tenant_scoped_collections"]:
        blockers.append(
            "No TENANT_SCOPED collections discovered — classification likely "
            "failed; refusing to plan an empty restore."
        )

    if plan["unknown_collections_requiring_review"]:
        warnings.append(
            f"{len(plan['unknown_collections_requiring_review'])} collection(s) "
            "are UNKNOWN_REVIEW_REQUIRED — confirm tenant scoping with schema "
            "owners before including them in any future drill."
        )

    if prod_db_name and plan["target_database"] == prod_db_name:
        if not allow_prod_target:
            blockers.append(
                f"target_database '{plan['target_database']}' matches production "
                f"DB_NAME '{prod_db_name}'. Refusing without --allow-prod-target."
            )
        else:
            warnings.append(
                "--allow-prod-target ENABLED: target_database equals production "
                "DB. Restore will mutate live tenant data."
            )

    archive = Path(plan["source_backup_archive"])
    if not archive.exists():
        warnings.append(
            f"backup-archive path does not exist on this host: {archive} "
            "(dry-run can still emit the plan; --execute will fail at runtime)."
        )

    verdict = "BLOCK" if blockers else ("REVIEW" if warnings else "OK")
    return verdict, blockers + warnings


def run_execute(plan: dict, mongo_url: str, db_name: str) -> int:
    """Phase 2 only — actually invoke mongorestore. Faz 1: not exercised in CI."""
    if not mongo_url:
        print("ERROR: MONGO_URL unset — cannot execute restore.", file=sys.stderr)
        return 2
    archive = Path(plan["source_backup_archive"])
    if not archive.exists():
        print(f"ERROR: backup archive missing: {archive}", file=sys.stderr)
        return 2
    src_db = archive / db_name
    if not src_db.exists():
        print(
            f"ERROR: source DB folder missing inside archive: {src_db}",
            file=sys.stderr,
        )
        return 2

    target = plan["target_database"]
    for coll in plan["tenant_scoped_collections"]:
        cmd = [
            "mongorestore",
            "--gzip",
            f"--uri={mongo_url}",
            f"--nsInclude={db_name}.{coll}",
            f"--nsFrom={db_name}.{coll}",
            f"--nsTo={target}.{coll}",
            str(archive),
        ]
        print("RUN:", " ".join(cmd))
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            print(f"ERROR: mongorestore failed for {coll}", file=sys.stderr)
            return 2

    print(
        "NOTE: post-restore prune (deleteMany tenant_id != X) and validation "
        "queries are Phase 2 work; not run by this helper."
    )
    return 0


def _print_text(plan: dict) -> None:
    print("=== Tenant Restore Drill Plan ===")
    print(f"- source backup archive: {plan['source_backup_archive']}")
    print(f"- target tenant_id: {plan['target_tenant_id']}")
    print(f"- target database: {plan['target_database']}")
    print(f"- mode: {plan['mode']}")
    print(f"- collections discovered: {plan['collections_discovered']}")
    print(
        f"- tenant-scoped collections ({len(plan['tenant_scoped_collections'])}): "
        f"{plan['tenant_scoped_collections']}"
    )
    print(
        f"- excluded global collections ({len(plan['excluded_global_collections'])}): "
        f"{plan['excluded_global_collections']}"
    )
    print(
        f"- unknown collections requiring review "
        f"({len(plan['unknown_collections_requiring_review'])}): "
        f"{plan['unknown_collections_requiring_review']}"
    )
    print(
        f"- system internal skipped ({len(plan['system_internal_skipped'])}): "
        f"{plan['system_internal_skipped']}"
    )
    print(f"\n- planned restore strategy:\n{plan['planned_restore_strategy']}")
    print("\n- validation queries:")
    for q in plan["validation_queries"]:
        print(f"    {q}")
    print(f"\n- risk verdict: {plan['risk_verdict']}")
    if plan.get("risk_findings"):
        print("- risk findings:")
        for f in plan["risk_findings"]:
            print(f"    * {f}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--backup-archive", required=True)
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--target-db", required=True)
    p.add_argument(
        "--execute",
        action="store_true",
        help="Phase 2: actually invoke mongorestore. Default = dry-run.",
    )
    p.add_argument(
        "--allow-prod-target",
        action="store_true",
        help="Override: allow target-db to match production DB_NAME.",
    )
    p.add_argument(
        "--prod-db-name",
        default=os.environ.get("DB_NAME"),
        help="Production DB name to guard against (default: $DB_NAME).",
    )
    p.add_argument(
        "--backend-root",
        default=str(_REPO_ROOT / "backend"),
        help="Backend source root for classification scan.",
    )
    p.add_argument("--format", choices=("text", "json"), default="text")
    args = p.parse_args(argv)

    classification = classify_tenant_scope.build_report(Path(args.backend_root))
    plan = build_plan(
        backup_archive=args.backup_archive,
        tenant_id=args.tenant_id,
        target_db=args.target_db,
        classification=classification,
    )
    verdict, findings = assess_risk(
        plan,
        prod_db_name=args.prod_db_name,
        allow_prod_target=args.allow_prod_target,
    )
    plan["risk_verdict"] = verdict
    plan["risk_findings"] = findings
    plan["mode"] = "execute" if args.execute else "dry-run"

    if args.format == "json":
        print(json.dumps(plan, indent=2, default=str))
    else:
        _print_text(plan)

    if verdict == "BLOCK":
        return 1
    if args.execute:
        return run_execute(
            plan,
            os.environ.get("MONGO_URL", ""),
            os.environ.get("DB_NAME", "hotel_pms"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
