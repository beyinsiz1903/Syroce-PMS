"""Active test quarantine manifest.

Historical entries were removed in September 2026 after verifying the current
CI JUnit report: the referenced node IDs no longer existed, while the restored
test files were already running from ``tests/``. Keep both names for backwards
compatibility with tooling, but do not add entries without a current failing
node ID, owner, and expiry date.
"""

QUARANTINE_SKIP_MAP: dict[str, dict[str, str]] = {}
QUARANTINED_TESTS: dict[str, str] = {}
