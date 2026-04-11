#!/usr/bin/env python3
"""
TI-003: CI Enforcement — Raw DB Usage Detection
================================================
Scans the codebase for direct `from core.database import db` usage.
Returns exit code 1 if violations are found in non-whitelisted files.

Usage:
    python scripts/check_raw_db.py          # Audit mode (print violations)
    python scripts/check_raw_db.py --strict  # CI mode (exit 1 on violation)
"""
import os
import re
import sys

# Files that legitimately need raw DB access
WHITELISTED_FILES = {
    "core/database.py",          # The source itself
    "core/tenant_db.py",         # Wraps raw DB
    "core/__init__.py",          # Re-exports
    "core/security.py",          # Auth before tenant context
    "startup.py",                # Index creation
    "health_check.py",           # System monitoring
    "server.py",                 # Bootstrap
    "auto_seed.py",              # Seeding
    "seed_data.py",              # Seeding
    "seed_demo_data.py",         # Seeding
    "seed_production_user.py",   # Seeding
    "create_test_data.py",       # Seeding
    "create_test_user.py",       # Seeding
    "create_demo_users.py",      # Seeding
    "create_advanced_demo_data.py",
    "create_comprehensive_demo_data.py",
    "create_comprehensive_demo_all_modules.py",
    "create_finance_demo_data.py",
    "create_fnb_demo_data.py",
    "create_maintenance_demo_data.py",
    "fix_test_user.py",
    "demo_data_generator.py",
    "bootstrap/dependency_container.py",
}

# Patterns that indicate raw DB usage
RAW_DB_PATTERNS = [
    re.compile(r"from\s+core\.database\s+import\s+.*\bdb\b"),
    re.compile(r"from\s+server\s+import\s+.*\bdb\b"),
]


def scan_file(filepath, backend_dir):
    """Scan a file for raw DB usage violations."""
    rel_path = os.path.relpath(filepath, backend_dir)

    # Skip whitelisted files
    if rel_path in WHITELISTED_FILES:
        return []

    # Skip test files
    if "/tests/" in rel_path or rel_path.startswith("tests/") or "test_" in os.path.basename(rel_path):
        return []

    violations = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                for pattern in RAW_DB_PATTERNS:
                    if pattern.search(line):
                        violations.append((rel_path, line_no, line.strip()))
    except OSError:
        pass

    return violations


def main():
    strict = "--strict" in sys.argv
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    all_violations = []

    for root, dirs, files in os.walk(backend_dir):
        # Skip hidden dirs, __pycache__, node_modules
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != "node_modules"]

        for f in files:
            if not f.endswith(".py"):
                continue
            filepath = os.path.join(root, f)
            violations = scan_file(filepath, backend_dir)
            all_violations.extend(violations)

    if all_violations:
        print(f"\n{'='*60}")
        print(f" TI-003 RAW DB USAGE AUDIT: {len(all_violations)} violations found")
        print(f"{'='*60}\n")
        for rel_path, line_no, line in sorted(all_violations):
            print(f"  {rel_path}:{line_no}  →  {line}")
        print(f"\n{'='*60}")
        print("  FIX: Replace 'from core.database import db' with:")
        print("    from core.tenant_db import get_db")
        print("    db = get_db()  # inside function body")
        print(f"{'='*60}\n")

        if strict:
            print("CI CHECK FAILED: Raw DB usage detected in non-whitelisted files.")
            sys.exit(1)
        else:
            print(f"AUDIT MODE: {len(all_violations)} files need migration.")
            print("Run with --strict for CI enforcement.")
    else:
        print("TI-003 CI CHECK PASSED: No raw DB usage violations found.")


if __name__ == "__main__":
    main()
