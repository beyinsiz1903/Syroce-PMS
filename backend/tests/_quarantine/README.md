# Quarantine Directory (ADR-002)
# ================================
# Tests moved here are NOT run in CI. They are reviewed monthly.
#
# Structure:
#   _quarantine/
#   ├── quarantine_manifest.py    <- Individual test skip markers (loaded by conftest.py)
#   ├── stale_fixtures/           <- Tests failing due to missing/outdated seed data
#   ├── stale_room_locks/         <- RESTORED (2026-03-23) — copies kept for reference
#   └── stale_dates/              <- RESTORED (2026-03-23) — copies kept for reference
#
# ── Current Quarantine Status (2026-09) ──
#
# Active manifest entries: **0**.
# Latest audited full-suite JUnit: 6,672 tests, 3 explicitly allowed skips.
# The former "37 remaining" rows referenced test node IDs that no longer
# existed and were never active because the manifest export name had changed.
# They were stale inventory, not skipped CI coverage.
#
# Note: stale_room_locks/ and stale_dates/ subdirectories contain original copies
# of files that have been fixed and restored to tests/. They are kept for reference
# only and are NOT executed.
#
# Monthly Review Process:
# 1. Run quarantined tests: pytest tests/_quarantine/ --tb=short
# 2. Check if root causes are fixed
# 3. Move passing files back to tests/
# 4. Remove passing tests from quarantine_manifest.py
# 5. Delete tests for permanently removed features
