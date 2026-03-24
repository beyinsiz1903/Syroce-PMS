#!/usr/bin/env python3
"""
Import boundary guard.

Ensures that domain modules respect import boundaries:
  - domains/* must NOT import from other domains/*
  - workers/* must NOT import from routers/*
  - routers/* must NOT import from workers/*

Usage:
    python scripts/check_import_boundaries.py
    (exit 0 = clean, exit 1 = boundary violation detected)
"""
import pathlib
import re
import sys

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Rules: (source_pattern, forbidden_import_pattern, description)
BOUNDARY_RULES = [
    (
        "domains/*/",
        r"from domains\.(?!__)",
        "Domain module importing from another domain (cross-domain coupling)",
    ),
    (
        "workers/",
        r"from routers\.",
        "Worker importing from router (layer violation)",
    ),
    (
        "routers/",
        r"from workers\.",
        "Router importing from worker (layer violation)",
    ),
]

# Known exceptions: existing cross-boundary imports tracked for future cleanup
KNOWN_EXCEPTIONS = frozenset({
    ("domains/channel_manager/router.py", 30),  # imports BlockStatus from domains.pms
    ("domains/revenue/analytics_router.py", 505),  # imports BookingAdapter from domains.pms
    ("routers/system_health_normalized.py", 98),  # imports worker_runtime_service from workers
})

DOMAIN_SELF_IMPORT = re.compile(r"from domains\.(\w+)")


def check_file(filepath: pathlib.Path, source_pattern: str, forbidden_re: str, desc: str) -> list:
    violations = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    rel = filepath.relative_to(BACKEND_ROOT)
    parts = rel.parts

    for lineno, line in enumerate(content.splitlines(), 1):
        line_stripped = line.strip()
        if not line_stripped.startswith(("import ", "from ")):
            continue
        if re.search(forbidden_re, line_stripped):
            # Allow self-imports within the same domain
            if "domains" in source_pattern:
                m = DOMAIN_SELF_IMPORT.search(line_stripped)
                if m and len(parts) >= 2 and m.group(1) == parts[1]:
                    continue
            violations.append((str(rel), lineno, line_stripped, desc))

    return violations


def is_known_exception(rel_path: str, lineno: int) -> bool:
    """Check if a violation is a known exception."""
    return (rel_path, lineno) in KNOWN_EXCEPTIONS


def main() -> int:
    all_violations = []

    for source_pattern, forbidden_re, desc in BOUNDARY_RULES:
        glob_pattern = source_pattern + "**/*.py"
        for filepath in BACKEND_ROOT.glob(glob_pattern):
            if "__pycache__" in str(filepath) or "_legacy" in str(filepath):
                continue
            violations = check_file(filepath, source_pattern, forbidden_re, desc)
            all_violations.extend(violations)

    if all_violations:
        new_violations = [v for v in all_violations if not is_known_exception(v[0], v[1])]
        known = len(all_violations) - len(new_violations)

        if new_violations:
            print(f"FAIL: {len(new_violations)} NEW import boundary violation(s):")
            for path, lineno, line, desc in new_violations:
                print(f"  {path}:{lineno}: {desc}")
                print(f"    {line}")
            if known:
                print(f"\n  ({known} known exception(s) suppressed)")
            return 1

        print(f"OK: No new import boundary violations. ({known} known exception(s) tracked)")
        return 0

    print("OK: No import boundary violations detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
