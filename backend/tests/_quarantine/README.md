# Quarantine Directory
# ====================
# Tests moved here are NOT run in CI. They are reviewed monthly.
#
# Quarantine Rules (from ADR-002):
# - Import errors from refactored modules → fix imports, move back
# - Stale DB fixtures → update seed data, move back
# - Removed/changed API → rewrite or delete
# - Flaky tests → tag [FLAKY], investigate root cause
#
# Format: Each test file moved here should have a header comment:
#   # QUARANTINED: 2026-03-23
#   # REASON: Import error - module X renamed to Y
#   # ORIGINAL: tests/test_some_file.py
