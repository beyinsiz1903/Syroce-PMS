#!/usr/bin/env python3
"""Subset duplicate guard for the backend requirements split (Phase 8.2+).

Phase 8.2 (May 2026) of the requirements split refactor removed the legacy
aggregate `backend/requirements.txt`. The script's prior "set parity"
invariant (packages(requirements.txt) == packages(requirements/all.txt))
no longer applies — there is no aggregate left to compare against. The
remaining and still-valuable invariant is:

    NO DUPLICATES : no package name appears as a direct (top-level) entry
                    in two or more canonical subset files. `base.txt` is
                    allowed to be referenced via `-r` from any subset
                    (those are includes, not direct entries).

The canonical subset names are pinned in `SUBSET_NAMES`. Compose files
(`all.txt`, `api-runtime.txt`, `worker-runtime.txt`) are intentionally
NOT included in the duplicate check — they are aggregators by design and
re-list packages via `-r` includes; checking them would produce false
positives.

The CI step that invokes this script (`.github/workflows/ci-cd.yml`)
keeps its existing name; the script filename (`check_requirements_split_parity.py`)
is preserved to avoid an OAuth-scoped workflow patch. The "parity" word
in the filename is a historical artifact of Phases 4-7 and now refers to
intra-split duplicate parity, not aggregate-vs-split parity.

See docs/backend_refactors/requirements-split.run.md Phase 8.2 for the
full surgery log.

Usage:
    python backend/scripts/check_requirements_split_parity.py
    python backend/scripts/check_requirements_split_parity.py --verbose

Exit codes:
    0 : no duplicates
    1 : duplicates detected
    2 : usage / file not found
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SPLIT_DIR = BACKEND_DIR / "requirements"

SUBSET_NAMES = ("base", "api", "worker", "ml", "reports", "integrations", "dev")

NAME_SPLIT_RE = re.compile(r"[<>=!~\[;\s]")


def normalize_pkg_name(spec: str) -> str:
    """Extract canonical lowercase package name from a requirement spec line."""
    spec = spec.strip()
    if not spec or spec.startswith("#"):
        return ""
    if spec.startswith("-"):
        return ""
    name = NAME_SPLIT_RE.split(spec, 1)[0].strip().lower()
    return name.replace("_", "-")


def parse_direct(path: Path) -> set[str]:
    """Return set of direct package names in *path* (no `-r` recursion)."""
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = normalize_pkg_name(line)
        if name:
            out.add(name)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print full per-subset counts even on success.")
    args = parser.parse_args()

    direct_per_subset: dict[str, set[str]] = {
        name: parse_direct(SPLIT_DIR / f"{name}.txt") for name in SUBSET_NAMES
    }

    duplicates: dict[str, list[str]] = {}
    pkg_to_files: dict[str, list[str]] = {}
    for fname, pkgs in direct_per_subset.items():
        for pkg in pkgs:
            pkg_to_files.setdefault(pkg, []).append(fname)
    for pkg, files in pkg_to_files.items():
        if len(files) > 1:
            duplicates[pkg] = sorted(files)

    print("=" * 64)
    print("backend requirements split — subset duplicate guard")
    print("=" * 64)
    print(f"  split tree           : {SPLIT_DIR.relative_to(REPO_ROOT)}")
    print(f"  canonical subsets    : {', '.join(SUBSET_NAMES)}")
    total = sum(len(p) for p in direct_per_subset.values())
    print(f"    total direct refs  : {total}")
    print()

    failed = False
    if duplicates:
        failed = True
        print(f"[FAIL] {len(duplicates)} duplicate package(s) across subset direct entries:")
        for pkg, files in sorted(duplicates.items()):
            print(f"  - {pkg!r} appears in: {', '.join(files)}")
    else:
        print(f"[ok]   no duplicates         : 0 cross-subset top-level repeats")

    if args.verbose:
        print()
        print("--- per-subset direct (non-recursive) counts ---")
        for name in SUBSET_NAMES:
            print(f"  {name:>13s} : {len(direct_per_subset[name]):3d}")

    print()
    if failed:
        print("VERDICT: DUPLICATES DETECTED — fix before merging.")
        return 1
    print("VERDICT: OK — canonical subsets have no cross-subset duplicates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
