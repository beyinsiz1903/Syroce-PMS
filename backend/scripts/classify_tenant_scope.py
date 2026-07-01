"""Classify MongoDB collections by tenant-scoping for tenant restore drill safety.

Pilot Readiness Checklist hard-blocker #3 — Faz 1 supporting tool.

Categories:
  TENANT_SCOPED            — code uses this collection together with tenant_id.
                             Safe to filter+restore in a tenant drill.
  GLOBAL_EXCLUDE           — global resources (secret stores, controlplane).
                             MUST NOT be cross-tenant restored. Hard-coded list.
  UNKNOWN_REVIEW_REQUIRED  — needs human review before drill includes it.
                             Default for collections that don't co-occur with
                             tenant_id and aren't in the explicit GLOBAL list.
  SYSTEM_INTERNAL          — MongoDB internal namespaces (system.*, fs.*).

The classifier is a STATIC code scanner — it does not connect to MongoDB and
therefore makes no assumption about which collections actually exist in the
live database. The output is a conservative plan input for tenant_restore_drill.

Usage:
    python backend/scripts/classify_tenant_scope.py
    python backend/scripts/classify_tenant_scope.py --format json
    python backend/scripts/classify_tenant_scope.py --output /tmp/scope.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_BACKEND_DEFAULT = Path(__file__).resolve().parents[1]


# Lists curated by ChatGPT review (Faz 1, May 2026). Keep in sync with
# docs/procedures/TENANT_RESTORE_DRILL.md "Tenant scope classification".
GLOBAL_EXCLUDE: set[str] = {
    "_dev_secrets",
    "credential_vault",
    "provider_secrets",
    "secret_access_audit",
    "cp_deploy_events",
    "drift_alert_events",
    "readiness_state_log",
}

# Channel-manager state collections whose tenant-scoping field is ambiguous —
# default to manual review until the schema authors confirm restore semantics.
UNKNOWN_REVIEW_FORCED: set[str] = {
    "connector_dlq",
    "connector_outbox",
    "connector_metrics",
    "cm_webhook_events",
    "raw_channel_events",
    "reservation_lineage",
}

SYSTEM_INTERNAL_PREFIXES: tuple[str, ...] = ("system.", "fs.", "__")


_COLL_REF_RE = re.compile(r"""db\[['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]\]""")
_GET_COLL_RE = re.compile(r"""get_collection\(['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""")
_TENANT_ID_RE = re.compile(r"\btenant_id\b")


def discover_collections(root: Path) -> dict[str, list[Path]]:
    """Walk *.py under root; map collection name -> source files referencing it."""
    coll_files: dict[str, set[Path]] = defaultdict(set)
    for py in root.rglob("*.py"):
        parts = set(py.parts)
        if "__pycache__" in parts or "tests" in parts or ".venv" in parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _COLL_REF_RE.finditer(text):
            coll_files[m.group(1)].add(py)
        for m in _GET_COLL_RE.finditer(text):
            coll_files[m.group(1)].add(py)
    return {k: sorted(v) for k, v in coll_files.items()}


def has_tenant_id_query(coll: str, files: list[Path]) -> bool:
    """Heuristic: does any referencing file mention tenant_id near the collection ref?

    Window: 5 lines above, 15 lines below. Matches the typical CRUD pattern of:
        col = db["bookings"]
        await col.find_one({"tenant_id": tid, ...})
    """
    pat_coll = re.compile(rf"""(?:db\[['"]|get_collection\(['"]){re.escape(coll)}['"]""")
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines):
            if pat_coll.search(ln):
                window = "\n".join(lines[max(0, i - 5) : i + 16])
                if _TENANT_ID_RE.search(window):
                    return True
    return False


def classify(coll: str, files: list[Path]) -> str:
    if any(coll.startswith(p) for p in SYSTEM_INTERNAL_PREFIXES):
        return "SYSTEM_INTERNAL"
    if coll in GLOBAL_EXCLUDE:
        return "GLOBAL_EXCLUDE"
    if coll in UNKNOWN_REVIEW_FORCED:
        return "UNKNOWN_REVIEW_REQUIRED"
    if has_tenant_id_query(coll, files):
        return "TENANT_SCOPED"
    return "UNKNOWN_REVIEW_REQUIRED"


def build_report(root: Path) -> dict:
    coll_files = discover_collections(root)
    report: dict = {
        "TENANT_SCOPED": [],
        "GLOBAL_EXCLUDE": [],
        "UNKNOWN_REVIEW_REQUIRED": [],
        "SYSTEM_INTERNAL": [],
    }
    for coll, files in sorted(coll_files.items()):
        cat = classify(coll, files)
        report[cat].append(
            {
                "name": coll,
                "ref_count": len(files),
                "ref_files": [str(f.relative_to(root.parent)) for f in files[:3]],
            }
        )
    report["_summary"] = {k: len(v) for k, v in report.items() if not k.startswith("_")}
    return report


def _print_text(report: dict) -> None:
    print("=== Tenant Scope Classification ===")
    for cat in (
        "TENANT_SCOPED",
        "GLOBAL_EXCLUDE",
        "UNKNOWN_REVIEW_REQUIRED",
        "SYSTEM_INTERNAL",
    ):
        entries = report[cat]
        print(f"\n[{cat}] ({len(entries)})")
        for e in entries:
            print(f"  - {e['name']}  (refs={e['ref_count']})")
    print(f"\nSummary: {report['_summary']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", default=str(_BACKEND_DEFAULT), help="Backend source root")
    p.add_argument("--format", choices=("text", "json"), default="text")
    p.add_argument("--output", help="Write JSON report to this path")
    args = p.parse_args(argv)

    report = build_report(Path(args.root))

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        print(f"Wrote JSON report: {args.output}")

    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
