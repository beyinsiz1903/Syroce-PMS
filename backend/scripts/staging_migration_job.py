#!/usr/bin/env python3
"""
Staging Migration Job — One-shot crypto key rotation rehearsal.

PURPOSE
-------
Runs a full dry-run → migrate → verify → restore cycle against a staging
database WITHOUT exposing any secret values in logs or environment dumps.

DESIGN (Option A — in-process key re-use)
-----------------------------------------
The production CM_MASTER_KEY_CURRENT is read at startup and assigned
in-process as CM_MASTER_KEY_PREVIOUS **before** the crypto service is
initialized. The original environment variable name is then overwritten
with the NEW v2 key. No secret value is ever logged.

SAFETY RULES (enforced in code, not just by convention)
--------------------------------------------------------
1. DB_NAME must NOT match STAGING_FORBIDDEN_DB_NAMES. Hard exit otherwise.
2. CM_MASTER_KEY_CURRENT and CM_KEY_VERSION_CURRENT must be SET at entry.
3. STAGING_NEW_MASTER_KEY must be SET and >= 32 bytes.
4. All output is restricted to numeric counters only — no key values.
5. Backup file is written with 0600 permissions.
6. Dry-run ALWAYS runs first. Real migration is skipped unless --run-migration
   is explicitly passed.

USAGE (on DigitalOcean App Platform console / one-off job)
-----------------------------------------------------------
Required env vars (set in the staging job component only):
  MONGO_URL              = <staging MongoDB URL>
  DB_NAME                = syroce-pms-staging   (must NOT be production DB)
  CRYPTO_V2_ENABLED      = true
  CM_MASTER_KEY_CURRENT  = <existing production key — becomes PREVIOUS in-process>
  CM_KEY_VERSION_CURRENT = v1   (version of the existing production key)
  CM_KEY_VERSION_PREVIOUS= v1   (same, set explicitly for clarity)
  STAGING_NEW_MASTER_KEY = <freshly generated 32-byte key for v2>
  STAGING_NEW_KEY_VERSION= v2

Run dry-run only (safe, no DB writes):
  python scripts/staging_migration_job.py --dry-run

Run full rehearsal (dry-run + migrate + restore):
  python scripts/staging_migration_job.py --run-migration
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("staging_migration_job")

# ── Safety constants ──────────────────────────────────────────────────────────
STAGING_FORBIDDEN_DB_NAMES = {
    "syroce-pms",
    "syroce_production",
    "hotel_pms",
    "hotel_pms_production",
}
MIN_KEY_BYTES = 32


# ── Pre-flight checks ─────────────────────────────────────────────────────────

def _preflight():
    """Validate environment before touching any crypto or DB state."""
    errors = []

    db_name = os.environ.get("DB_NAME", "")
    if not db_name:
        errors.append("DB_NAME is not set.")
    elif db_name in STAGING_FORBIDDEN_DB_NAMES:
        errors.append(
            f"DB_NAME='{db_name}' is a FORBIDDEN production database. "
            "This job MUST target a staging or rehearsal database only."
        )

    if not os.environ.get("CM_MASTER_KEY_CURRENT"):
        errors.append("CM_MASTER_KEY_CURRENT is not set (needed as PREVIOUS key).")

    if not os.environ.get("CM_KEY_VERSION_CURRENT"):
        errors.append("CM_KEY_VERSION_CURRENT is not set.")

    new_key = os.environ.get("STAGING_NEW_MASTER_KEY", "")
    if not new_key:
        errors.append("STAGING_NEW_MASTER_KEY is not set.")
    elif len(new_key.encode()) < MIN_KEY_BYTES:
        errors.append(
            f"STAGING_NEW_MASTER_KEY is too short "
            f"({len(new_key.encode())} bytes, minimum {MIN_KEY_BYTES})."
        )

    if not os.environ.get("STAGING_NEW_KEY_VERSION"):
        errors.append("STAGING_NEW_KEY_VERSION is not set.")

    if errors:
        for e in errors:
            logger.error("PREFLIGHT FAIL: %s", e)
        sys.exit(1)

    logger.info("Pre-flight OK.")
    logger.info("  DB_NAME              : %s", db_name)
    logger.info("  CM_KEY_VERSION_CURRENT (old/previous): %s",
                os.environ.get("CM_KEY_VERSION_CURRENT"))
    logger.info("  STAGING_NEW_KEY_VERSION (new/current): %s",
                os.environ.get("STAGING_NEW_KEY_VERSION"))
    logger.info("  CM_MASTER_KEY_CURRENT: SET (value hidden)")
    logger.info("  STAGING_NEW_MASTER_KEY: SET (value hidden)")


def _rotate_keys_in_process():
    """
    Re-assign environment variables IN-PROCESS so that:
      - The existing production key becomes CM_MASTER_KEY_PREVIOUS / CM_KEY_VERSION_PREVIOUS
      - The new staging key becomes CM_MASTER_KEY_CURRENT / CM_KEY_VERSION_CURRENT

    No key value is ever written to a log or printed.
    """
    existing_key = os.environ.pop("CM_MASTER_KEY_CURRENT")
    existing_version = os.environ.pop("CM_KEY_VERSION_CURRENT")

    os.environ["CM_MASTER_KEY_PREVIOUS"] = existing_key
    os.environ["CM_KEY_VERSION_PREVIOUS"] = existing_version

    os.environ["CM_MASTER_KEY_CURRENT"] = os.environ.pop("STAGING_NEW_MASTER_KEY")
    os.environ["CM_KEY_VERSION_CURRENT"] = os.environ.pop("STAGING_NEW_KEY_VERSION")

    # Also honour the legacy alias if code reads it
    os.environ["CM_KEY_VERSION"] = os.environ["CM_KEY_VERSION_CURRENT"]

    logger.info("In-process key rotation complete.")
    logger.info("  Previous kid (old production): %s", os.environ["CM_KEY_VERSION_PREVIOUS"])
    logger.info("  Current  kid (new staging v2): %s", os.environ["CM_KEY_VERSION_CURRENT"])


# ── Migration helpers ─────────────────────────────────────────────────────────

async def _run_dry_run(db, svc):
    """Run full in-memory dry-run. Returns stats dict."""
    from scripts.migrate_crypto import collect_records, execute_migration, stats, ALLOWED_COLLECTIONS

    # Reset global stats before each run
    for k in stats:
        stats[k] = 0

    records = await collect_records(db, svc, ALLOWED_COLLECTIONS)
    await execute_migration(db, svc, records, dry_run=True)

    return dict(stats), records


async def _run_real_migration(db, svc):
    """Run real migration with backup. Returns (stats, backup_filename)."""
    from scripts.migrate_crypto import (
        collect_records, execute_migration, create_backup_file,
        MigrationPreflightError, stats, ALLOWED_COLLECTIONS,
    )

    for k in stats:
        stats[k] = 0

    records = await collect_records(db, svc, ALLOWED_COLLECTIONS)

    if stats.get("unknown_kid_records", 0) > 0:
        raise MigrationPreflightError("unknown_kid_records > 0, aborting.")

    backup_file = create_backup_file(db, svc, records)
    await execute_migration(db, svc, records, dry_run=False)

    return dict(stats), backup_file


async def _run_restore(db, backup_file: str):
    """Restore from backup file."""
    from scripts.migrate_crypto import run_restore
    await run_restore(db, backup_file)


def _log_stats(label: str, s: dict):
    logger.info("=" * 60)
    logger.info("%s", label)
    logger.info("  total_encrypted_records: %d", s.get("total_records", 0))
    logger.info("  already_current_kid    : %d", s.get("already_current_kid", 0))
    logger.info("  old_kid_records        : %d", s.get("old_kid_records", 0))
    logger.info("  unknown_kid_records    : %d", s.get("unknown_kid_records", 0))
    logger.info("  migrated               : %d", s.get("migrated", 0))
    logger.info("  failed                 : %d", s.get("failed", 0))
    logger.info("  skipped (empty)        : %d", s.get("skipped", 0))
    logger.info("=" * 60)


# ── Main flow ─────────────────────────────────────────────────────────────────

async def main_async(run_migration: bool):
    # Step 1: rotate keys in-process (production key → PREVIOUS, new key → CURRENT)
    _rotate_keys_in_process()

    # Step 2: initialise crypto service and DB (after key rotation)
    from core.crypto.service import get_crypto_service
    from core.database import _raw_db as db  # use raw db, no tenant proxy

    try:
        svc = get_crypto_service()
    except Exception as e:
        logger.error("Crypto service init failed: %s", e)
        sys.exit(1)

    health = svc.health()
    logger.info("Crypto service health: v2=%s bypass=%s kid=%s has_previous=%s",
                health.get("v2_enabled"),
                health.get("bypass_active"),
                health.get("current_kid"),
                health.get("has_previous_key"))

    # Step 3: Dry-run (always runs)
    logger.info(">>> STEP 1: DRY-RUN <<<")
    dry_stats, _ = await _run_dry_run(db, svc)
    _log_stats("DRY-RUN RESULT", dry_stats)

    if dry_stats.get("failed", 0) > 0 or dry_stats.get("unknown_kid_records", 0) > 0:
        logger.error("Dry-run found failures or unknown kids. Halting.")
        sys.exit(1)

    if not run_migration:
        logger.info("--dry-run only mode. Stopping here. Pass --run-migration for full rehearsal.")
        return

    # Step 4: Real migration
    logger.info(">>> STEP 2: REAL MIGRATION <<<")
    mig_stats, backup_file = await _run_real_migration(db, svc)
    _log_stats("MIGRATION RESULT", mig_stats)

    if mig_stats.get("failed", 0) > 0:
        logger.error("Migration had failures. NOT restoring automatically. Inspect backup: %s", backup_file)
        sys.exit(1)

    # Step 5: Post-migration dry-run (must show old_kid_records=0)
    logger.info(">>> STEP 3: POST-MIGRATION DRY-RUN <<<")
    post_stats, _ = await _run_dry_run(db, svc)
    _log_stats("POST-MIGRATION DRY-RUN RESULT", post_stats)

    if post_stats.get("old_kid_records", 0) != 0:
        logger.error("Post-migration dry-run still shows old_kid_records > 0. Check migration output.")
        sys.exit(1)

    # Step 6: Restore (rehearsal only — proves rollback works)
    logger.info(">>> STEP 4: RESTORE (ROLLBACK REHEARSAL) <<<")
    await _run_restore(db, backup_file)

    # Step 7: Post-restore dry-run (must show old_kid_records == pre-migration count)
    logger.info(">>> STEP 5: POST-RESTORE DRY-RUN <<<")
    restore_stats, _ = await _run_dry_run(db, svc)
    _log_stats("POST-RESTORE DRY-RUN RESULT", restore_stats)

    if restore_stats.get("old_kid_records", 0) != dry_stats.get("old_kid_records", 0):
        logger.error(
            "Post-restore old_kid_records=%d does not match pre-migration=%d. "
            "Restore may be incomplete.",
            restore_stats.get("old_kid_records", 0),
            dry_stats.get("old_kid_records", 0),
        )
        sys.exit(1)

    logger.info("STAGING REHEARSAL COMPLETE. All steps PASSED.")
    logger.info("Summary:")
    logger.info("  Pre-migration old_kid_records : %d", dry_stats.get("old_kid_records", 0))
    logger.info("  Migrated records              : %d", mig_stats.get("migrated", 0))
    logger.info("  Migration failures            : %d", mig_stats.get("failed", 0))
    logger.info("  Post-restore old_kid_records  : %d", restore_stats.get("old_kid_records", 0))
    logger.info("  Backup file                   : %s (keep until production rotation completes)", backup_file)


def main():
    parser = argparse.ArgumentParser(
        description="Staging migration rehearsal job (Option A: in-process key rotation)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run dry-run only. No DB writes. Default mode.",
    )
    parser.add_argument(
        "--run-migration",
        action="store_true",
        help="Run full rehearsal: dry-run → migrate → post dry-run → restore → post dry-run.",
    )
    args = parser.parse_args()

    if args.dry_run and args.run_migration:
        print("ERROR: Cannot specify both --dry-run and --run-migration.")
        sys.exit(1)

    if not args.dry_run and not args.run_migration:
        print("ERROR: Specify --dry-run or --run-migration.")
        sys.exit(1)

    _preflight()
    asyncio.run(main_async(run_migration=args.run_migration))


if __name__ == "__main__":
    main()
