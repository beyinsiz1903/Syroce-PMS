#!/usr/bin/env python3
"""
Staging Migration Job — Option A (corrected)

DESIGN
------
Runs a full dry-run → migrate → verify → restore cycle against a STAGING
database while reading the production CM_MASTER_KEY_CURRENT in-process as
the PREVIOUS key — without ever copying or logging the secret value.

KEY PRINCIPLE
-------------
This script does NOT import `core.database`. It builds its own Motor client
using STAGING_MONGO_URL + STAGING_DB_NAME so that production MONGO_URL and
DB_NAME environment variables are never touched, even when this job runs
inside the same App Platform component as production.

REQUIRED ENV VARS
-----------------
Set only in the job/console component, NOT in app-level env:

  STAGING_MONGO_URL       MongoDB Atlas URL for the STAGING database.
  STAGING_DB_NAME         Staging database name (must contain "staging" or
                          "rehearsal" and must NOT be a production DB name).
  STAGING_NEW_MASTER_KEY  Freshly generated key for v2 (>= 32 bytes).
                          Generate with: openssl rand -hex 32
  STAGING_NEW_KEY_VERSION Version label for the new key (e.g. "v2").

  From existing app-level env (no change needed there):
  CM_MASTER_KEY_CURRENT   Existing production key — read in-process as PREVIOUS.
  CM_KEY_VERSION_CURRENT  Preferred version alias. Falls back to CM_KEY_VERSION.
  CRYPTO_V2_ENABLED       Must be "true".

USAGE
-----
  # Safe — no DB writes:
  python scripts/staging_migration_job.py --dry-run

  # Full rehearsal (dry-run + migrate + restore):
  python scripts/staging_migration_job.py --run-migration

DO NOT
------
  * Copy CM_MASTER_KEY_CURRENT into any other component manually.
  * Run with STAGING_DB_NAME pointing at a production database.
  * Merge this script to main before a successful --dry-run PASS.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import tempfile
from datetime import UTC, datetime

import certifi

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("staging_migration_job")

# ── Constants ─────────────────────────────────────────────────────────────────

PRODUCTION_FORBIDDEN_DB_NAMES = frozenset(
    {
        "syroce-pms",
        "syroce_production",
        "hotel_pms",
        "hotel_pms_production",
        "production",
    }
)

STAGING_SAFE_KEYWORDS = ("staging", "rehearsal", "test", "migration")
MIN_KEY_BYTES = 32

ALLOWED_COLLECTIONS = {"provider_secrets", "credential_vault", "_dev_secrets"}


# ── Pre-flight ────────────────────────────────────────────────────────────────


def _abort(msg: str) -> None:
    logger.error("PREFLIGHT FAIL: %s", msg)
    sys.exit(1)


def _preflight() -> dict:
    """
    Validate all required environment variables.
    Returns a dict of resolved config values (no secret values included).
    Exits with code 1 on any violation.
    """
    errors = []

    # --- STAGING_MONGO_URL ---
    staging_url = os.environ.get("STAGING_MONGO_URL", "")
    if not staging_url:
        errors.append("STAGING_MONGO_URL is not set.")

    # --- STAGING_DB_NAME ---
    staging_db = os.environ.get("STAGING_DB_NAME", "")
    if not staging_db:
        errors.append("STAGING_DB_NAME is not set.")
    else:
        if staging_db in PRODUCTION_FORBIDDEN_DB_NAMES:
            errors.append(
                f"STAGING_DB_NAME='{staging_db}' is a FORBIDDEN production database name."
            )
        if not any(kw in staging_db.lower() for kw in STAGING_SAFE_KEYWORDS):
            errors.append(
                f"STAGING_DB_NAME='{staging_db}' must contain one of: "
                f"{STAGING_SAFE_KEYWORDS}. This is a safety guard."
            )

    # --- Existing production key (becomes PREVIOUS in-process) ---
    old_key = os.environ.get("CM_MASTER_KEY_CURRENT", "")
    if not old_key:
        errors.append("CM_MASTER_KEY_CURRENT is not set (needed as in-process PREVIOUS key).")

    # CM_KEY_VERSION_CURRENT preferred; fall back to CM_KEY_VERSION
    old_version = os.environ.get("CM_KEY_VERSION_CURRENT") or os.environ.get("CM_KEY_VERSION", "")
    if not old_version:
        errors.append(
            "Neither CM_KEY_VERSION_CURRENT nor CM_KEY_VERSION is set. "
            "Cannot determine the existing key version."
        )

    # --- New staging key ---
    new_key = os.environ.get("STAGING_NEW_MASTER_KEY", "")
    if not new_key:
        errors.append("STAGING_NEW_MASTER_KEY is not set.")
    elif len(new_key.encode("utf-8")) < MIN_KEY_BYTES:
        errors.append(
            f"STAGING_NEW_MASTER_KEY is too short "
            f"({len(new_key.encode('utf-8'))} bytes, minimum {MIN_KEY_BYTES})."
        )

    new_version = os.environ.get("STAGING_NEW_KEY_VERSION", "")
    if not new_version:
        errors.append("STAGING_NEW_KEY_VERSION is not set.")
    elif old_version and new_version == old_version:
        errors.append(
            f"STAGING_NEW_KEY_VERSION='{new_version}' must differ from "
            f"the existing version='{old_version}'."
        )

    # --- CRYPTO_V2_ENABLED ---
    if os.environ.get("CRYPTO_V2_ENABLED", "").lower() != "true":
        errors.append("CRYPTO_V2_ENABLED must be 'true'.")

    if errors:
        for e in errors:
            logger.error("PREFLIGHT FAIL: %s", e)
        sys.exit(1)

    logger.info("Pre-flight OK.")
    logger.info("  STAGING_DB_NAME       : %s", staging_db)
    logger.info("  old_version (PREVIOUS): %s", old_version)
    logger.info("  new_version (CURRENT) : %s", new_version)
    logger.info("  CM_MASTER_KEY_CURRENT : SET (value hidden)")
    logger.info("  STAGING_NEW_MASTER_KEY: SET (value hidden)")

    return {
        "staging_url": staging_url,
        "staging_db": staging_db,
        "old_key": old_key,
        "old_version": old_version,
        "new_key": new_key,
        "new_version": new_version,
    }


# ── In-process key rotation ───────────────────────────────────────────────────


def _rotate_keys_in_process(cfg: dict) -> None:
    """
    Re-map environment variables in this process only.

    After this call:
      CM_MASTER_KEY_PREVIOUS = old production key
      CM_KEY_VERSION_PREVIOUS = old version
      CM_MASTER_KEY_CURRENT   = new staging key
      CM_KEY_VERSION_CURRENT  = new version
      CM_KEY_VERSION          = new version (legacy alias)

    No value is ever written to a log.
    """
    # Remove staging-specific vars so they don't leak into crypto service init
    os.environ.pop("STAGING_NEW_MASTER_KEY", None)
    os.environ.pop("STAGING_NEW_KEY_VERSION", None)
    os.environ.pop("STAGING_MONGO_URL", None)

    # Assign PREVIOUS from the existing production key (already in RAM)
    os.environ["CM_MASTER_KEY_PREVIOUS"] = cfg["old_key"]
    os.environ["CM_KEY_VERSION_PREVIOUS"] = cfg["old_version"]

    # Assign new CURRENT
    os.environ["CM_MASTER_KEY_CURRENT"] = cfg["new_key"]
    os.environ["CM_KEY_VERSION_CURRENT"] = cfg["new_version"]
    os.environ["CM_KEY_VERSION"] = cfg["new_version"]

    logger.info("In-process key rotation complete.")
    logger.info("  PREVIOUS kid: %s", cfg["old_version"])
    logger.info("  CURRENT  kid: %s", cfg["new_version"])


# ── Staging DB client ─────────────────────────────────────────────────────────


async def _build_staging_db(staging_url: str, staging_db: str):
    """Build a Motor client pointed exclusively at the staging database."""
    from motor.motor_asyncio import AsyncIOMotorClient

    tls_kwargs = {}
    if staging_url.startswith("mongodb+srv://"):
        tls_kwargs["tlsCAFile"] = certifi.where()

    client = AsyncIOMotorClient(
        staging_url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=20000,
        retryWrites=True,
        **tls_kwargs,
    )

    # Identity / connectivity check — logs DB name, never secrets
    try:
        info = await client.admin.command("ping")
        logger.info("Staging DB ping OK: %s", info)
    except Exception as e:
        logger.error("Cannot connect to staging DB: %s", e)
        sys.exit(1)

    db = client[staging_db]

    # Double-check the actual database name we are connected to
    actual_name = db.name
    logger.info("Connected staging database name: %s", actual_name)
    if actual_name in PRODUCTION_FORBIDDEN_DB_NAMES:
        logger.error(
            "SAFETY ABORT: Connected database '%s' is in the production forbidden list.",
            actual_name,
        )
        sys.exit(1)
    if not any(kw in actual_name.lower() for kw in STAGING_SAFE_KEYWORDS):
        logger.error(
            "SAFETY ABORT: Connected database '%s' does not contain a safe keyword %s.",
            actual_name,
            STAGING_SAFE_KEYWORDS,
        )
        sys.exit(1)

    return db


# ── Migration helpers (self-contained, no core.database import) ───────────────


def _log_stats(label: str, s: dict) -> None:
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


async def _run_phase(db, svc, dry_run: bool) -> tuple[dict, list]:
    """
    Collect records and execute migration (or dry-run).
    Returns (stats_snapshot, records_list).
    """
    from scripts.migrate_crypto import (
        ALLOWED_COLLECTIONS,
        collect_records,
        execute_migration,
        stats,
    )

    # Reset the global stats counter for this phase
    for k in list(stats.keys()):
        stats[k] = 0

    records = await collect_records(db, svc, ALLOWED_COLLECTIONS)
    await execute_migration(db, svc, records, dry_run=dry_run)
    return dict(stats), records


async def _create_and_write_backup(db, svc, records) -> str:
    """Write a 0600 backup file. Returns the filename."""
    from scripts.migrate_crypto import create_backup_file

    backup_file = create_backup_file(db, svc, records)
    logger.info("Backup created: %s (content hidden)", backup_file)
    return backup_file


async def _run_restore(db, backup_file: str) -> None:
    from scripts.migrate_crypto import run_restore

    await run_restore(db, backup_file)


# ── Main flow ─────────────────────────────────────────────────────────────────


async def main_async(cfg: dict, run_migration: bool) -> None:
    # Step 1: Rotate keys in-process BEFORE importing crypto modules
    _rotate_keys_in_process(cfg)

    # Step 2: Build staging-only DB connection (no core.database import)
    db = await _build_staging_db(cfg["staging_url"], cfg["staging_db"])

    # Step 3: Initialize crypto service (now sees rotated env vars)
    from core.crypto.service import get_crypto_service

    try:
        svc = get_crypto_service()
    except Exception as e:
        logger.error("Crypto service init failed: %s", e)
        sys.exit(1)

    health = svc.health()
    logger.info(
        "Crypto service: v2=%s bypass=%s kid=%s has_previous=%s",
        health.get("v2_enabled"),
        health.get("bypass_active"),
        health.get("current_kid"),
        health.get("has_previous_key"),
    )

    if not health.get("has_previous_key"):
        logger.error("Crypto service has no previous key. In-process rotation may have failed.")
        sys.exit(1)

    # ── Step 4: Dry-run (mandatory, always first) ──────────────────────────
    logger.info(">>> STEP 1/5: DRY-RUN <<<")
    dry_stats, _ = await _run_phase(db, svc, dry_run=True)
    _log_stats("DRY-RUN RESULT", dry_stats)

    if dry_stats.get("failed", 0) > 0 or dry_stats.get("unknown_kid_records", 0) > 0:
        logger.error("Dry-run found failures or unknown kids. Halting.")
        sys.exit(1)

    # ── Meaningfulness guard ───────────────────────────────────────────────
    total = dry_stats.get("total_records", 0)
    old_kid = dry_stats.get("old_kid_records", 0)
    if total == 0 or old_kid == 0:
        if run_migration:
            logger.error(
                "REHEARSAL NOT MEANINGFUL: total_records=%d, old_kid_records=%d. "
                "The staging DB has no records that need migration. "
                "Populate staging DB with real encrypted records before running --run-migration.",
                total,
                old_kid,
            )
            sys.exit(1)
        else:
            logger.warning(
                "REHEARSAL NOT MEANINGFUL: total_records=%d, old_kid_records=%d. "
                "The staging DB appears empty or already migrated. "
                "Dry-run completed but no real crypto roundtrip was exercised. "
                "Populate staging DB with encrypted records before proceeding to --run-migration.",
                total,
                old_kid,
            )

    if not run_migration:
        logger.info("--dry-run only mode. PASS. Re-run with --run-migration for full rehearsal.")
        return

    # ── Step 5: Real migration ─────────────────────────────────────────────
    logger.info(">>> STEP 2/5: REAL MIGRATION <<<")
    from scripts.migrate_crypto import collect_records, execute_migration, stats

    # Collect records for backup + migration
    for k in list(stats.keys()):
        stats[k] = 0

    records = await collect_records(db, svc, ALLOWED_COLLECTIONS)

    if stats.get("unknown_kid_records", 0) > 0:
        logger.error("unknown_kid_records > 0 during migration collection. Aborting.")
        sys.exit(1)

    # Write backup before any DB writes
    backup_file = await _create_and_write_backup(db, svc, records)

    # Execute migration
    for k in list(stats.keys()):
        stats[k] = 0

    await execute_migration(db, svc, records, dry_run=False)
    mig_stats = dict(stats)
    _log_stats("MIGRATION RESULT", mig_stats)

    if mig_stats.get("failed", 0) > 0:
        logger.error(
            "Migration had %d failures. NOT auto-restoring. Inspect backup: %s",
            mig_stats["failed"],
            backup_file,
        )
        sys.exit(1)

    # ── Step 6: Post-migration dry-run ─────────────────────────────────────
    logger.info(">>> STEP 3/5: POST-MIGRATION DRY-RUN <<<")
    post_stats, _ = await _run_phase(db, svc, dry_run=True)
    _log_stats("POST-MIGRATION DRY-RUN RESULT", post_stats)

    if post_stats.get("old_kid_records", 0) != 0:
        logger.error("old_kid_records still > 0 after migration. Check logs.")
        sys.exit(1)

    # ── Step 7: Restore (rollback rehearsal) ──────────────────────────────
    logger.info(">>> STEP 4/5: RESTORE (ROLLBACK REHEARSAL) <<<")
    await _run_restore(db, backup_file)

    # ── Step 8: Post-restore dry-run ───────────────────────────────────────
    logger.info(">>> STEP 5/5: POST-RESTORE DRY-RUN <<<")
    restore_stats, _ = await _run_phase(db, svc, dry_run=True)
    _log_stats("POST-RESTORE DRY-RUN RESULT", restore_stats)

    expected_old = dry_stats.get("old_kid_records", 0)
    actual_old = restore_stats.get("old_kid_records", 0)
    if actual_old != expected_old:
        logger.error(
            "Post-restore old_kid_records=%d does not match pre-migration=%d.",
            actual_old,
            expected_old,
        )
        sys.exit(1)

    logger.info("STAGING REHEARSAL COMPLETE — ALL STEPS PASSED.")
    logger.info("Summary:")
    logger.info("  Pre-migration old_kid_records : %d", dry_stats.get("old_kid_records", 0))
    logger.info("  Migrated records              : %d", mig_stats.get("migrated", 0))
    logger.info("  Migration failures            : %d", mig_stats.get("failed", 0))
    logger.info("  Post-restore old_kid_records  : %d", restore_stats.get("old_kid_records", 0))
    logger.info("  Backup file (keep until prod rotation): %s", backup_file)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Staging migration rehearsal — Option A in-process key rotation. "
            "Targets STAGING_MONGO_URL only. Never touches production DB."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Run dry-run only. No DB writes.",
    )
    group.add_argument(
        "--run-migration",
        action="store_true",
        help="Full rehearsal: dry-run → migrate → post dry-run → restore → post dry-run.",
    )
    args = parser.parse_args()

    cfg = _preflight()
    asyncio.run(main_async(cfg, run_migration=args.run_migration))


if __name__ == "__main__":
    main()
