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
# ── Current Quarantine Status (2026-03) ──
#
# CI Hard Gate: 391+ tests, 0 failures
# Restored from quarantine: 70+ tests (2026-03-23)
#
# REMAINING IN QUARANTINE (via quarantine_manifest.py):
# ┌─────────────────────────┬───────┬──────────────────────────────────────────┐
# | Category                | Count | Action Required                          |
# ├─────────────────────────┼───────┼──────────────────────────────────────────┤
# | stale_fixtures          | 10    | Rate manager needs room_type seed data   |
# | changed_api             | 10    | Rewrite assertions for current API       |
# | changed_implementation  | 13    | Fix after feature completion             |
# | external_dependency     | 3     | Mock or CI-skip                          |
# | meta-test               | 1     | Update assertion (file restored)         |
# └─────────────────────────┴───────┴──────────────────────────────────────────┘
# Total remaining: ~37 tests (controlled tech debt)
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
