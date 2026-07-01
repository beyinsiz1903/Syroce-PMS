"""Tenant restore DRILL helper — Phase 1 + Phase 2.

Pilot Readiness Checklist hard-blocker #3.

Phase 1 (May 2026):
  * Builds a deterministic restore PLAN from a backup archive + classification.
  * Default = dry-run (no writes, no mongorestore invocation).
  * Hard guardrails (see assess_risk).

Phase 2 (May 2026):
  * --execute path: real mongorestore subprocess + post-restore prune
    (motor) + validation (count/leak/FK) + drill report writer.
  * Sandbox-only by enforcement: Atlas URLs (mongodb+srv:// or
    .mongodb.net hostnames) trigger BLOCK verdict that --allow-prod-target
    cannot bypass.

Usage:
    # Dry-run (default):
    python tools/tenant_restore_drill.py \
        --backup-archive /var/backups/bk_20260511_020000_xxx \
        --tenant-id T1 \
        --target-db hotel_pms_drill_staging

    # Sandbox execute (requires local Mongo + mongodb-tools):
    python tools/tenant_restore_drill.py [...] --execute

Exit codes:
    0 — plan generated (or execute completed successfully + verdict PASS)
    1 — guardrail BLOCK (missing args, prod/Atlas target, no
        TENANT_SCOPED collections, etc.)
    2 — execute-time runtime failure (mongorestore exit != 0, archive
        missing, validation FAIL — leak count > 0 or FK orphans)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make backend/scripts/classify_tenant_scope.py importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend" / "scripts"))
import classify_tenant_scope  # noqa: E402

DEFAULT_REPORT_DIR = _REPO_ROOT / "docs" / "drill_reports"


_ATLAS_PATTERNS: tuple[re.Pattern[str], ...] = (
    # SRV scheme always implies a managed/lookup-driven cluster — fail-closed.
    re.compile(r"^mongodb\+srv://", re.IGNORECASE),
    # Atlas standard hostname suffixes (case-insensitive). Trailing-dot
    # FQDN forms (`cluster.mongodb.net.`) are also matched.
    re.compile(r"\.mongodb\.net\.?(?:[:/?,]|$)", re.IGNORECASE),
    re.compile(r"\.mongodb-dev\.net\.?(?:[:/?,]|$)", re.IGNORECASE),
    re.compile(r"\.mongodbgov\.net\.?(?:[:/?,]|$)", re.IGNORECASE),
)


def _is_atlas_url(url: str | None) -> bool:
    """Detect MongoDB Atlas connection strings (sandbox drill must refuse).

    Matches case-insensitively against:
      * scheme `mongodb+srv://` (any case),
      * any host containing `.mongodb.net`, `.mongodb-dev.net`,
        `.mongodbgov.net` (any case, anywhere in URI).

    Comma-separated multi-host URLs are covered because the substring match
    inspects the full URI. Custom DNS/CNAME aliases that do NOT include an
    Atlas suffix cannot be detected via string heuristics — operators must
    not point sandbox drill at such hosts (see runbook rule #7).
    """
    if not url:
        return False
    for pat in _ATLAS_PATTERNS:
        if pat.search(url):
            return True
    return False


_TENANT_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug_tenant(tid: str) -> str:
    """Filename-safe slug for tenant_id (caps length, strips path chars)."""
    s = _TENANT_SLUG_RE.sub("_", str(tid)).strip("._-")
    return s[:64] or "tenant"


def build_plan(
    *,
    backup_archive: str,
    tenant_id: str,
    target_db: str,
    classification: dict,
) -> dict:
    """Pure function: assemble a restore plan from inputs + classification."""
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
    mongo_url: str | None = None,
) -> tuple[str, list[str]]:
    """Return (verdict, findings). verdict ∈ {OK, REVIEW, BLOCK}.

    Atlas-host BLOCK is HARD: --allow-prod-target cannot bypass it. This
    enforces the sandbox-only rule for Phase 2 execute path.
    """
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

    if mongo_url is not None and _is_atlas_url(mongo_url):
        # Hard block; cannot be overridden by --allow-prod-target.
        blockers.append(
            f"MONGO_URL points to MongoDB Atlas ({mongo_url[:40]}...). "
            "Tenant restore drill is sandbox-only and refuses to operate "
            "against Atlas/production hosts."
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


# ── Phase 2: async post-restore prune + validation ──────────────────────


async def prune_cross_tenant(
    mongo_url: str, target_db: str, tenant_id: str, collections: list[str]
) -> dict[str, int]:
    """Delete docs where tenant_id is set AND != target.

    Safety: requires `$exists: true` so docs missing the `tenant_id` field
    are NEVER deleted (architect review: defends against over-delete on
    type-mismatch / partial restores). Also performs a sample-doc type
    check up-front: if a sampled tenant_id is not the same Python type as
    the supplied target tenant_id, raises RuntimeError without mutating.

    Returns per-collection delete counts.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[target_db]
    deleted: dict[str, int] = {}
    try:
        # Phase 1: scan EVERY collection for tenant_id type heterogeneity
        # BEFORE any mutation. Refuses to start prune if any collection
        # has multiple tenant_id BSON types or a type mismatching CLI input.
        for coll in collections:
            seen_types: set[type] = set()
            cursor = db[coll].find(
                {"tenant_id": {"$exists": True}}, {"tenant_id": 1}
            ).limit(100)
            async for doc in cursor:
                seen_types.add(type(doc["tenant_id"]))
                if len(seen_types) > 1:
                    raise RuntimeError(
                        f"heterogeneous tenant_id types in '{coll}': "
                        f"{sorted(t.__name__ for t in seen_types)}. "
                        "Refusing to prune."
                    )
            if seen_types:
                only_type = next(iter(seen_types))
                # Strict identity check: bool subclass of int is rejected,
                # ObjectId vs str is rejected.
                if only_type is not type(tenant_id):
                    raise RuntimeError(
                        f"tenant_id type mismatch in collection '{coll}': "
                        f"CLI supplied {type(tenant_id).__name__} "
                        f"({tenant_id!r}); DB stores {only_type.__name__}. "
                        "Refusing to prune to avoid over-delete."
                    )
        # Phase 2: only after ALL collections passed the safety scan,
        # perform delete_many. This guarantees no partial-mutation on
        # mismatch.
        for coll in collections:
            res = await db[coll].delete_many(
                {"tenant_id": {"$exists": True, "$ne": tenant_id}}
            )
            deleted[coll] = res.deleted_count
    finally:
        client.close()
    return deleted


async def validate_restore(
    mongo_url: str, target_db: str, tenant_id: str, collections: list[str]
) -> dict:
    """Validate per-collection counts + leak == 0 + FK integrity."""
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[target_db]
    per_coll: dict[str, dict] = {}
    fk_orphans: dict[str, list[str]] = {}
    untagged_total = 0
    try:
        for coll in collections:
            target_count = await db[coll].count_documents(
                {"tenant_id": tenant_id}
            )
            # Leak = explicit tenant_id present AND != target. Docs without
            # tenant_id are reported separately as `untagged` (not leaks,
            # but require operator review).
            leak_count = await db[coll].count_documents(
                {"tenant_id": {"$exists": True, "$ne": tenant_id}}
            )
            untagged = await db[coll].count_documents(
                {"tenant_id": {"$exists": False}}
            )
            untagged_total += untagged
            per_coll[coll] = {
                "target_count": target_count,
                "leak_count": leak_count,
                "untagged_count": untagged,
                "ok": leak_count == 0 and target_count > 0 and untagged == 0,
            }

        # FK integrity: booking.guest_id, booking.room_id, folio.booking_id
        if "bookings" in collections and "guests" in collections:
            async for b in db["bookings"].find({"tenant_id": tenant_id}):
                gid = b.get("guest_id")
                if gid is not None:
                    g = await db["guests"].find_one({"_id": gid})
                    if g is None:
                        fk_orphans.setdefault("booking_orphan_guest", []).append(
                            str(b["_id"])
                        )
        if "bookings" in collections and "rooms" in collections:
            async for b in db["bookings"].find({"tenant_id": tenant_id}):
                rid = b.get("room_id")
                if rid is not None:
                    r = await db["rooms"].find_one({"_id": rid})
                    if r is None:
                        fk_orphans.setdefault("booking_orphan_room", []).append(
                            str(b["_id"])
                        )
        if "folios" in collections and "bookings" in collections:
            async for f in db["folios"].find({"tenant_id": tenant_id}):
                bid = f.get("booking_id")
                if bid is not None:
                    b = await db["bookings"].find_one({"_id": bid})
                    if b is None:
                        fk_orphans.setdefault("folio_orphan_booking", []).append(
                            str(f["_id"])
                        )
    finally:
        client.close()

    leak_total = sum(c["leak_count"] for c in per_coll.values())
    fk_total = sum(len(v) for v in fk_orphans.values())
    counts_ok = all(c["ok"] for c in per_coll.values())
    verdict = (
        "PASS"
        if leak_total == 0 and fk_total == 0 and untagged_total == 0 and counts_ok
        else "FAIL"
    )
    return {
        "per_collection": per_coll,
        "fk_orphans": fk_orphans,
        "leak_total": leak_total,
        "untagged_total": untagged_total,
        "fk_orphan_total": fk_total,
        "verdict": verdict,
    }


def write_drill_report(
    *,
    report_dir: Path,
    plan: dict,
    restore_results: list[dict],
    prune_results: dict[str, int],
    validation: dict,
    started_at: str,
    completed_at: str,
    duration_s: float,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = started_at.replace(":", "").replace("-", "")[:15]
    tenant_slug = _slug_tenant(plan["target_tenant_id"])
    fname = f"{ts}_{tenant_slug}_drill.md"
    path = report_dir / fname
    # Defense-in-depth: refuse if path resolves outside report_dir.
    if path.resolve().parent != report_dir.resolve():
        raise RuntimeError(
            f"Refusing to write report outside report_dir: {path}"
        )
    lines = [
        f"# Tenant Restore Drill Report — {started_at}",
        "",
        f"- Backup archive: `{plan['source_backup_archive']}`",
        f"- Target tenant_id: `{plan['target_tenant_id']}`",
        f"- Target database: `{plan['target_database']}`",
        f"- Started: {started_at}",
        f"- Completed: {completed_at}",
        f"- Duration: {duration_s:.2f}s",
        f"- Tenant-scoped collections planned: {len(plan['tenant_scoped_collections'])}",
        f"- Excluded global collections: {len(plan['excluded_global_collections'])}",
        f"- Unknown review-required: {len(plan['unknown_collections_requiring_review'])}",
        "",
        "## Restore subprocess results",
        "",
        "| Collection | mongorestore exit | stderr (head) |",
        "|---|---|---|",
    ]
    for r in restore_results:
        stderr = (r.get("stderr") or "").splitlines()
        head = stderr[0] if stderr else ""
        lines.append(f"| `{r['collection']}` | {r['returncode']} | {head[:80]} |")

    lines += [
        "",
        "## Post-restore prune (cross-tenant deletion)",
        "",
        "| Collection | Pruned docs |",
        "|---|---|",
    ]
    for coll, n in prune_results.items():
        lines.append(f"| `{coll}` | {n} |")

    lines += [
        "",
        "## Validation",
        "",
        "| Collection | Target count | Leak count | OK |",
        "|---|---|---|---|",
    ]
    for coll, v in validation["per_collection"].items():
        ok = "✅" if v["ok"] else "❌"
        lines.append(
            f"| `{coll}` | {v['target_count']} | {v['leak_count']} | {ok} |"
        )

    lines += [
        "",
        f"- Total leak docs: **{validation['leak_total']}** (must be 0)",
        f"- Total untagged docs (missing tenant_id): "
        f"**{validation.get('untagged_total', 0)}** (must be 0)",
        f"- Total FK orphans: **{validation['fk_orphan_total']}** (must be 0)",
        "",
        "## FK orphan details",
        "",
    ]
    if validation["fk_orphans"]:
        for k, ids in validation["fk_orphans"].items():
            lines.append(f"- {k}: {len(ids)} → {ids[:5]}{'...' if len(ids) > 5 else ''}")
    else:
        lines.append("None.")

    lines += [
        "",
        f"## Verdict: **{validation['verdict']}**",
        "",
    ]
    # Atomic write: unique temp file (UUID suffix) + rename to avoid
    # half-written reports AND avoid collisions with concurrent drills
    # writing to the same report_dir at the same second/tenant.
    import uuid

    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return path


def run_execute(
    plan: dict,
    mongo_url: str,
    db_name: str,
    *,
    report_dir: Path,
) -> int:
    """Phase 2 execute path: real mongorestore + prune + validate + report."""
    if not mongo_url:
        print("ERROR: MONGO_URL unset — cannot execute restore.", file=sys.stderr)
        return 2
    if _is_atlas_url(mongo_url):
        # Belt-and-suspenders: assess_risk should already have blocked.
        print(
            f"ERROR: refusing to execute against Atlas URL ({mongo_url[:40]}...).",
            file=sys.stderr,
        )
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
    started = datetime.now(timezone.utc)
    started_iso = started.isoformat(timespec="seconds")

    restore_results: list[dict] = []
    for coll in plan["tenant_scoped_collections"]:
        coll_bson = src_db / f"{coll}.bson.gz"
        if not coll_bson.exists():
            # Source collection may legitimately not exist in the archive;
            # skip rather than fail.
            print(f"SKIP {coll}: not present in source archive")
            continue
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
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        restore_results.append(
            {
                "collection": coll,
                "returncode": proc.returncode,
                "stderr": proc.stderr,
            }
        )
        if proc.returncode != 0:
            print(
                f"ERROR: mongorestore failed for {coll}\n{proc.stderr}",
                file=sys.stderr,
            )
            return 2

    restored_colls = [r["collection"] for r in restore_results]
    if not restored_colls:
        print("ERROR: no collections restored from archive.", file=sys.stderr)
        return 2

    prune_results = asyncio.run(
        prune_cross_tenant(mongo_url, target, plan["target_tenant_id"], restored_colls)
    )
    validation = asyncio.run(
        validate_restore(mongo_url, target, plan["target_tenant_id"], restored_colls)
    )
    completed = datetime.now(timezone.utc)
    duration = (completed - started).total_seconds()

    report_path = write_drill_report(
        report_dir=report_dir,
        plan=plan,
        restore_results=restore_results,
        prune_results=prune_results,
        validation=validation,
        started_at=started_iso,
        completed_at=completed.isoformat(timespec="seconds"),
        duration_s=duration,
    )
    print(f"\n=== Drill verdict: {validation['verdict']} ===")
    print(f"Drill report: {report_path}")
    print(f"Leak total: {validation['leak_total']}")
    print(f"Untagged total: {validation.get('untagged_total', 0)}")
    print(f"FK orphans: {validation['fk_orphan_total']}")

    return 0 if validation["verdict"] == "PASS" else 2


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
        help=(
            "Override: allow target-db to match production DB_NAME. "
            "Does NOT bypass Atlas-host BLOCK guard."
        ),
    )
    p.add_argument(
        "--prod-db-name",
        default=os.environ.get("DB_NAME"),
        help="Production DB name to guard against (default: $DB_NAME).",
    )
    p.add_argument(
        "--mongo-url",
        default=os.environ.get("MONGO_URL"),
        help="Mongo URL for guard check + execute (default: $MONGO_URL).",
    )
    p.add_argument(
        "--source-db-name",
        default=os.environ.get("DB_NAME", "hotel_pms"),
        help=(
            "DB name inside the backup archive (mongodump folder name). "
            "Default: $DB_NAME."
        ),
    )
    p.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory for drill reports (default: docs/drill_reports/).",
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
        mongo_url=args.mongo_url if args.execute else None,
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
            args.mongo_url or "",
            args.source_db_name,
            report_dir=Path(args.report_dir),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
