#!/usr/bin/env python3
"""Drift guard for the backend requirements split (Phases 4-7).

Verifies two invariants while the legacy aggregate `requirements.txt` and the
new `requirements/{base,api,worker,ml,reports,integrations,dev}.txt` chain
live side-by-side (until Phase 8 deprecates the aggregate):

    1. SET PARITY      : packages(requirements.txt) == packages(requirements/all.txt)
    2. NO DUPLICATES   : no package name appears as a direct (top-level) entry
                         in two or more subset files (base is allowed to be
                         referenced via `-r` from any subset).

Usage:
    python backend/scripts/check_requirements_split_parity.py
    python backend/scripts/check_requirements_split_parity.py --verbose

Exit codes:
    0 : parity ok
    1 : drift detected (set diff or duplicate)
    2 : usage / file not found
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
AGGREGATE = BACKEND_DIR / "requirements.txt"
SPLIT_DIR = BACKEND_DIR / "requirements"
ALL_TXT = SPLIT_DIR / "all.txt"

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


def parse_with_includes(path: Path, _seen: set[Path] | None = None) -> set[str]:
    """Return full transitive package set for *path*, following `-r` includes."""
    if _seen is None:
        _seen = set()
    rp = path.resolve()
    if rp in _seen:
        return set()
    _seen.add(rp)
    if not rp.exists():
        print(f"ERROR: file not found: {rp}", file=sys.stderr)
        sys.exit(2)

    out: set[str] = set()
    for raw in rp.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            ref = line.split(None, 1)[1].strip()
            out |= parse_with_includes(rp.parent / ref, _seen)
            continue
        if line.startswith("-"):
            continue
        name = normalize_pkg_name(line)
        if name:
            out.add(name)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print full package sets even on success.")
    args = parser.parse_args()

    aggregate_set = parse_with_includes(AGGREGATE)
    split_set = parse_with_includes(ALL_TXT)

    missing_in_split = aggregate_set - split_set
    extra_in_split = split_set - aggregate_set

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

    failed = False

    print("=" * 64)
    print("backend requirements split — drift guard")
    print("=" * 64)
    print(f"  aggregate            : {AGGREGATE.relative_to(REPO_ROOT)}")
    print(f"    package count      : {len(aggregate_set)}")
    print(f"  split (all.txt union): {ALL_TXT.relative_to(REPO_ROOT)}")
    print(f"    package count      : {len(split_set)}")
    print()

    if missing_in_split or extra_in_split:
        failed = True
        print("[FAIL] set parity broken")
        if missing_in_split:
            print(f"  in aggregate but NOT in split  ({len(missing_in_split)}):")
            for p in sorted(missing_in_split):
                print(f"    - {p}")
        if extra_in_split:
            print(f"  in split but NOT in aggregate  ({len(extra_in_split)}):")
            for p in sorted(extra_in_split):
                print(f"    + {p}")
    else:
        print(f"[ok]   set parity            : {len(aggregate_set)} == {len(split_set)}")

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
        print("VERDICT: DRIFT DETECTED — fix before merging.")
        return 1
    print("VERDICT: OK — aggregate and split chain are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
