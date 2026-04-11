#!/usr/bin/env python3
"""
Orphan-file regression guard.

Enforces that no NEW top-level .py files appear in /backend without
being explicitly registered in the allow-list.

Usage:
    python scripts/check_orphan_files.py
    (exit 0 = clean, exit 1 = new orphan(s) detected)

Add new legitimate root files to ALLOWED_ROOT_FILES below.
"""
import pathlib
import sys

# ── Allow-list: files that are EXPECTED at /backend/*.py ─────────
ALLOWED_ROOT_FILES = frozenset({
    "__init__.py",
    "advanced_cache.py",
    "apm_middleware.py",
    "app.py",
    "auto_seed.py",
    "cache_manager.py",
    "cache_warmer.py",
    "celery_app.py",
    "celery_tasks.py",
    "conftest.py",
    "data_archival.py",
    "demo_data_generator.py",
    "health_check.py",
    "materialized_views.py",
    "ml_data_generators.py",
    "ml_trainers.py",
    "optimization_endpoints.py",
    "redis_cache.py",
    "server.py",
    "startup.py",
    "websocket_server.py",
})

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    actual = {
        p.name
        for p in BACKEND_ROOT.glob("*.py")
        if p.is_file()
    }
    orphans = sorted(actual - ALLOWED_ROOT_FILES)
    if orphans:
        print(f"FAIL: {len(orphans)} orphan file(s) in backend root:")
        for f in orphans:
            print(f"  - {f}")
        print()
        print("Fix: Move into the appropriate subdirectory, or add to")
        print("     ALLOWED_ROOT_FILES in scripts/check_orphan_files.py")
        return 1

    print(f"OK: {len(actual)} root file(s), all in allow-list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
