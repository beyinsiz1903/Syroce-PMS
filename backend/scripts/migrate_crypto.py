#!/usr/bin/env python3
"""
Crypto Migration Script — Re-encrypt legacy credentials to SYR1 envelope format.

Scans all credential collections, detects legacy formats, decrypts with
the original key derivation, and re-encrypts with the new HKDF-derived key.

Usage:
  python scripts/migrate_crypto.py --dry-run           # Preview only
  python scripts/migrate_crypto.py --collection provider_secrets
  python scripts/migrate_crypto.py --all               # Migrate everything
  python scripts/migrate_crypto.py --all --force-v2    # Force SYR1 even if CRYPTO_V2_ENABLED=false

Collections scanned:
  - provider_secrets       (XOR-encrypted per-field credentials)
  - credential_vault       (base64-encoded credentials)
  - _dev_secrets          (AES-GCM encrypted JSON blobs)
  - connector_accounts     (AES-GCM encrypted per-field credentials)

Environment:
  CM_MASTER_KEY_CURRENT   — new master key (required)
  CM_CREDENTIAL_KEY       — legacy key for AES-GCM decryption
  CM_ENCRYPTION_KEY       — legacy key for XOR decryption (optional)
  JWT_SECRET              — fallback for XOR decryption
  CRYPTO_V2_ENABLED=true  — must be true for migration (or use --force-v2)
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_crypto")

_NO_ID = {"_id": 0}

# Stats
stats = {
    "scanned": 0,
    "already_current": 0,
    "migrated": 0,
    "failed": 0,
    "skipped": 0,
}


async def migrate_provider_secrets(db, svc, dry_run: bool):
    """Migrate provider_secrets collection (XOR/AES-GCM per-field)."""
    coll = db["provider_secrets"]
    cursor = coll.find({}, _NO_ID)
    async for doc in cursor:
        stats["scanned"] += 1
        secret_id = doc.get("id", "?")
        tenant = doc.get("tenant_id", "")
        provider = doc.get("provider", "")
        prop = doc.get("property_id", "")
        payload = doc.get("encrypted_payload", {})

        if not payload:
            stats["skipped"] += 1
            continue

        all_current = all(svc.is_current_format(v) for v in payload.values() if isinstance(v, str) and v)
        if all_current:
            stats["already_current"] += 1
            continue

        try:
            from core.crypto import AADContext

            aad = AADContext(
                tenant_id=tenant,
                provider=provider,
                property_id=prop,
                environment=os.environ.get("APP_ENV", "development"),
                context_type="credential",
            )
            new_payload = svc.re_encrypt_dict(payload, aad=aad)

            if not dry_run:
                await coll.update_one(
                    {"id": secret_id},
                    {
                        "$set": {
                            "encrypted_payload": new_payload,
                            "key_version": svc._keyring.current_kid,
                            "migrated_at": datetime.now(UTC).isoformat(),
                        }
                    },
                )
            stats["migrated"] += 1
            logger.info(
                "%s provider_secrets/%s (%s/%s)",
                "WOULD MIGRATE" if dry_run else "MIGRATED",
                secret_id,
                provider,
                prop,
            )
        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED provider_secrets/%s: %s", secret_id, type(e).__name__)


async def migrate_credential_vault(db, svc, dry_run: bool):
    """Migrate credential_vault collection (base64-encoded)."""
    coll = db["credential_vault"]
    cursor = coll.find({"status": "active"}, _NO_ID)
    async for doc in cursor:
        stats["scanned"] += 1
        cred_id = doc.get("id", "?")
        tenant = doc.get("tenant_id", "")
        cred_type = doc.get("credential_type", "")
        cred_key = doc.get("credential_key", "")

        # Check if already migrated
        if doc.get("credential_encrypted") and svc.is_current_format(doc.get("credential_encrypted", "")):
            stats["already_current"] += 1
            continue

        encoded = doc.get("credential_value_encoded", "")
        if not encoded:
            stats["skipped"] += 1
            continue

        try:
            from core.crypto import AADContext

            plaintext = svc.decrypt_legacy_base64(encoded)
            aad = AADContext(
                tenant_id=tenant,
                provider=cred_type,
                property_id=cred_key,
                environment=os.environ.get("APP_ENV", "development"),
                context_type="credential",
            )
            encrypted = svc.encrypt(plaintext, aad=aad)

            if not dry_run:
                await coll.update_one(
                    {"id": cred_id},
                    {
                        "$set": {
                            "credential_encrypted": encrypted,
                            "key_version": svc._keyring.current_kid,
                            "credential_value_encoded": None,
                            "credential_value_hash": None,
                            "migrated_at": datetime.now(UTC).isoformat(),
                        }
                    },
                )
            stats["migrated"] += 1
            logger.info(
                "%s credential_vault/%s (%s/%s)",
                "WOULD MIGRATE" if dry_run else "MIGRATED",
                cred_id,
                cred_type,
                cred_key,
            )
        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED credential_vault/%s: %s", cred_id, type(e).__name__)


async def migrate_dev_secrets(db, svc, dry_run: bool):
    """Migrate _dev_secrets collection (AES-GCM JSON blobs)."""
    coll = db["_dev_secrets"]
    cursor = coll.find({}, _NO_ID)
    async for doc in cursor:
        stats["scanned"] += 1
        path = doc.get("path", "?")
        encrypted = doc.get("encrypted_payload", "")

        if not encrypted:
            stats["skipped"] += 1
            continue

        if svc.is_current_format(encrypted):
            stats["already_current"] += 1
            continue

        try:
            from core.crypto import AADContext

            parts = path.split("/")
            aad = AADContext(
                tenant_id=parts[3] if len(parts) > 3 else "",
                provider=parts[4] if len(parts) > 4 else "",
                property_id=parts[5] if len(parts) > 5 else "",
                environment=os.environ.get("APP_ENV", "development"),
                context_type="secret",
            )
            new_encrypted = svc.re_encrypt(encrypted, aad=aad)

            if not dry_run:
                await coll.update_one(
                    {"path": path},
                    {
                        "$set": {
                            "encrypted_payload": new_encrypted,
                            "key_version": svc._keyring.current_kid,
                            "migrated_at": datetime.now(UTC).isoformat(),
                        }
                    },
                )
            stats["migrated"] += 1
            logger.info(
                "%s _dev_secrets/%s",
                "WOULD MIGRATE" if dry_run else "MIGRATED",
                path,
            )
        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED _dev_secrets/%s: %s", path, type(e).__name__)


async def run_migration(args):
    from core.crypto import get_crypto_service
    from core.database import db

    svc = get_crypto_service()
    health = svc.health()
    logger.info("Crypto service: %s", health)

    if not health["v2_enabled"] and not args.force_v2:
        logger.error("CRYPTO_V2_ENABLED=false — migration requires V2 or --force-v2 flag")
        return

    if args.force_v2:
        os.environ["CRYPTO_V2_ENABLED"] = "true"
        from core.crypto.service import reset_crypto_service

        reset_crypto_service()
        svc = get_crypto_service()
        logger.info("Forced V2 mode for migration")

    target = args.collection or ("all" if args.all else None)
    if not target:
        logger.error("Specify --collection <name> or --all")
        return

    if target in ("all", "provider_secrets"):
        await migrate_provider_secrets(db, svc, args.dry_run)

    if target in ("all", "credential_vault"):
        await migrate_credential_vault(db, svc, args.dry_run)

    if target in ("all", "_dev_secrets"):
        await migrate_dev_secrets(db, svc, args.dry_run)

    logger.info("=" * 60)
    logger.info("Migration %s", "DRY RUN" if args.dry_run else "COMPLETE")
    logger.info("  Scanned:         %d", stats["scanned"])
    logger.info("  Already current: %d", stats["already_current"])
    logger.info("  Migrated:        %d", stats["migrated"])
    logger.info("  Failed:          %d", stats["failed"])
    logger.info("  Skipped:         %d", stats["skipped"])

    if stats["failed"] > 0:
        logger.warning("Some records failed — investigate before proceeding")


def main():
    parser = argparse.ArgumentParser(description="Crypto migration: legacy → SYR1 envelope")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--collection", help="Specific collection to migrate")
    parser.add_argument("--all", action="store_true", help="Migrate all collections")
    parser.add_argument("--force-v2", action="store_true", help="Force V2 mode")
    args = parser.parse_args()

    asyncio.run(run_migration(args))


if __name__ == "__main__":
    main()
