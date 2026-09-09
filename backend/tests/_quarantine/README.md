# Quarantine Directory (ADR-002)
# ================================
# Tests moved here are NOT run in CI. They are reviewed monthly.
#
# Structure:
#   _quarantine/
#   └── quarantine_manifest.py    <- Individual test skip markers (loaded by conftest.py)
#
# ── Current Quarantine Status (2026-09) ──
#
# Active manifest entries: **0**.
# Latest audited full-suite JUnit: 6,672 tests, 3 explicitly allowed skips.
# The former "37 remaining" inventory was stale. A September 2026 filesystem
# audit found seven obsolete duplicate files (72 test functions) under this
# directory. Every file already had a maintained counterpart under ``tests/``;
# the duplicates were removed so repository inventory and CI coverage agree.
# Historical source is available in git and must not be kept as executable-looking
# files outside the CI gate.
#
# Monthly Review Process:
# 1. Run quarantined tests: pytest tests/_quarantine/ --tb=short
# 2. Check if root causes are fixed
# 3. Move passing files back to tests/ (never keep a duplicate copy)
# 4. Remove passing tests from quarantine_manifest.py
# 5. Delete tests for permanently removed features
