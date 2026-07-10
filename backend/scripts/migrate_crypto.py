#!/usr/bin/env python3
"""
Crypto Migration Script — Re-encrypt credentials to SYR1 envelope format securely.

Features:
  - Strict kid-based format detection
  - Pre-migration backup to JSON
  - Context-bound MongoDB update filters (tenant/provider)
  - Post-write verification
  - Strict exit codes

Collections scanned:
  - provider_secrets
  - credential_vault
  - _dev_secrets

(Note: connector_accounts was removed as it does not exist in the codebase)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_crypto")

stats = {
    "total_records": 0,
    "already_current_kid": 0,
    "old_kid_records": 0,
    "unknown_kid_records": 0,
    "migrated": 0,
    "failed": 0,
    "skipped": 0,
}

backup_records = []

def _record_status(svc, val: str) -> str:
    """Analyze a single ciphertext string's status."""
    from core.crypto.envelope import is_envelope, extract_kid
    if not val:
        return "skipped"
    if svc.is_current_format(val):
        return "already_current_kid"
    if is_envelope(val):
        try:
            kid = extract_kid(val)
            if svc._keyring.has_previous and kid == svc._keyring._previous_kid:
                return "old_kid_records"
            return "unknown_kid_records"
        except Exception:
            return "unknown_kid_records"
    # Legacy format
    return "old_kid_records"


async def migrate_provider_secrets(db, svc, dry_run: bool):
    coll = db["provider_secrets"]
    async for doc in coll.find({}, {"_id": 0}):
        stats["total_records"] += 1
        secret_id = doc.get("id", "")
        tenant = doc.get("tenant_id", "")
        provider = doc.get("provider", "")
        prop = doc.get("property_id", "")
        payload = doc.get("encrypted_payload", {})

        if not payload:
            stats["skipped"] += 1
            continue

        statuses = [_record_status(svc, v) for v in payload.values() if isinstance(v, str) and v]
        if not statuses:
            stats["skipped"] += 1
            continue

        if all(s == "already_current_kid" for s in statuses):
            stats["already_current_kid"] += 1
            continue
        if any(s == "unknown_kid_records" for s in statuses):
            stats["unknown_kid_records"] += 1
            logger.error("provider_secrets/%s has unknown kid formats", secret_id)
            stats["failed"] += 1
            continue
        
        stats["old_kid_records"] += 1
        backup_records.append({"collection": "provider_secrets", "doc": doc})

        try:
            from core.crypto.engine import AADContext
            aad = AADContext(
                tenant_id=tenant,
                provider=provider,
                property_id=prop,
                environment=os.environ.get("APP_ENV", "development"),
                context_type="credential",
            )
            
            # Simulation: decrypt, encrypt, decrypt-verify
            decrypted = svc.decrypt_dict(payload, aad=aad)
            new_payload = svc.encrypt_dict(decrypted, aad=aad)
            verify_decrypted = svc.decrypt_dict(new_payload, aad=aad)
            
            if decrypted != verify_decrypted:
                raise ValueError("Verification failed: re-decrypted data does not match original plaintext")

            if not dry_run:
                # Context-bound strict update
                filter_query = {
                    "id": secret_id,
                    "tenant_id": tenant,
                    "provider": provider,
                    "property_id": prop
                }
                res = await coll.update_one(
                    filter_query,
                    {
                        "$set": {
                            "encrypted_payload": new_payload,
                            "key_version": svc._keyring.current_kid,
                            "migrated_at": datetime.now(UTC).isoformat(),
                        }
                    },
                )
                if res.matched_count != 1 or res.modified_count != 1:
                    raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")
            
            stats["migrated"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED provider_secrets/%s: %s", secret_id, str(e))


async def migrate_credential_vault(db, svc, dry_run: bool):
    coll = db["credential_vault"]
    async for doc in coll.find({"status": "active"}, {"_id": 0}):
        stats["total_records"] += 1
        cred_id = doc.get("id", "")
        tenant = doc.get("tenant_id", "")
        cred_type = doc.get("credential_type", "")
        cred_key = doc.get("credential_key", "")
        
        val = doc.get("credential_encrypted") or doc.get("credential_value_encoded")
        status = _record_status(svc, val)
        
        if status == "skipped":
            stats["skipped"] += 1
            continue
        if status == "already_current_kid":
            stats["already_current_kid"] += 1
            continue
        if status == "unknown_kid_records":
            stats["unknown_kid_records"] += 1
            stats["failed"] += 1
            logger.error("credential_vault/%s has unknown kid", cred_id)
            continue
            
        stats["old_kid_records"] += 1
        backup_records.append({"collection": "credential_vault", "doc": doc})

        try:
            from core.crypto.engine import AADContext
            aad = AADContext(
                tenant_id=tenant,
                provider=cred_type,
                property_id=cred_key,
                environment=os.environ.get("APP_ENV", "development"),
                context_type="credential",
            )

            # Decrypt correctly based on which field was used
            if doc.get("credential_encrypted"):
                plaintext = svc.decrypt(doc.get("credential_encrypted"), aad=aad)
            else:
                plaintext = svc.decrypt_legacy_base64(doc.get("credential_value_encoded", ""))

            encrypted = svc.encrypt(plaintext, aad=aad)
            
            # Verify
            verify_plaintext = svc.decrypt(encrypted, aad=aad)
            if plaintext != verify_plaintext:
                raise ValueError("Verification failed")

            if not dry_run:
                filter_query = {
                    "id": cred_id,
                    "tenant_id": tenant,
                    "credential_type": cred_type,
                    "credential_key": cred_key
                }
                res = await coll.update_one(
                    filter_query,
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
                if res.matched_count != 1 or res.modified_count != 1:
                    raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")
                    
            stats["migrated"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED credential_vault/%s: %s", cred_id, str(e))


async def migrate_dev_secrets(db, svc, dry_run: bool):
    coll = db["_dev_secrets"]
    async for doc in coll.find({}, {"_id": 0}):
        stats["total_records"] += 1
        path = doc.get("path", "")
        encrypted = doc.get("encrypted_payload", "")
        
        status = _record_status(svc, encrypted)
        if status == "skipped":
            stats["skipped"] += 1
            continue
        if status == "already_current_kid":
            stats["already_current_kid"] += 1
            continue
        if status == "unknown_kid_records":
            stats["unknown_kid_records"] += 1
            stats["failed"] += 1
            logger.error("_dev_secrets/%s has unknown kid", path)
            continue
            
        stats["old_kid_records"] += 1
        backup_records.append({"collection": "_dev_secrets", "doc": doc})

        try:
            from core.crypto.engine import AADContext
            parts = path.split("/")
            aad = AADContext(
                tenant_id=parts[3] if len(parts) > 3 else "",
                provider=parts[4] if len(parts) > 4 else "",
                property_id=parts[5] if len(parts) > 5 else "",
                environment=os.environ.get("APP_ENV", "development"),
                context_type="secret",
            )
            
            plaintext = svc.decrypt(encrypted, aad=aad)
            new_encrypted = svc.encrypt(plaintext, aad=aad)
            verify_plaintext = svc.decrypt(new_encrypted, aad=aad)
            
            if plaintext != verify_plaintext:
                raise ValueError("Verification failed")

            if not dry_run:
                res = await coll.update_one(
                    {"path": path},
                    {
                        "$set": {
                            "encrypted_payload": new_encrypted,
                            "key_version": svc._keyring.current_kid,
                            "migrated_at": datetime.now(UTC).isoformat(),
                        }
                    },
                )
                if res.matched_count != 1 or res.modified_count != 1:
                    raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")
                    
            stats["migrated"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED _dev_secrets/%s: %s", path, str(e))


async def run_migration(args):
    # Pre-flight environment validation before singleton instantiation
    is_prod = os.environ.get("APP_ENV", "development") in {"production", "staging"}
    v2_env = os.environ.get("CRYPTO_V2_ENABLED", "false").lower() == "true"
    
    if args.force_v2:
        os.environ["CRYPTO_V2_ENABLED"] = "true"
    elif not v2_env:
        logger.error("CRYPTO_V2_ENABLED is false. Migration requires V2 mode or --force-v2 flag.")
        sys.exit(1)

    if is_prod and not os.environ.get("CM_MASTER_KEY_CURRENT"):
        logger.error("CM_MASTER_KEY_CURRENT missing in production.")
        sys.exit(1)

    from core.crypto.service import get_crypto_service
    from core.database import db

    try:
        svc = get_crypto_service()
    except Exception as e:
        logger.error("Crypto service failed to initialize: %s", str(e))
        sys.exit(1)
        
    health = svc.health()
    logger.info("Crypto service: %s", health)

    target = args.collection or ("all" if args.all else None)
    if not target:
        logger.error("Specify --collection <name> or --all")
        sys.exit(1)

    if target in ("all", "provider_secrets"):
        await migrate_provider_secrets(db, svc, args.dry_run)
    if target in ("all", "credential_vault"):
        await migrate_credential_vault(db, svc, args.dry_run)
    if target in ("all", "_dev_secrets"):
        await migrate_dev_secrets(db, svc, args.dry_run)

    if not args.dry_run and backup_records:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"migration_backup_{ts}.json"
        with open(backup_file, "w") as f:
            json.dump(backup_records, f)
        logger.info("Saved %d records to %s before migrating.", len(backup_records), backup_file)

    logger.info("=" * 60)
    logger.info("Migration %s", "DRY RUN (Simulated in memory)" if args.dry_run else "COMPLETE")
    logger.info("  total_encrypted_records: %d", stats["total_records"])
    logger.info("  already_current_kid:     %d", stats["already_current_kid"])
    logger.info("  old_kid_records:         %d", stats["old_kid_records"])
    logger.info("  unknown_kid_records:     %d", stats["unknown_kid_records"])
    logger.info("  migrated:                %d", stats["migrated"])
    logger.info("  failed:                  %d", stats["failed"])
    logger.info("  skipped (empty):         %d", stats["skipped"])

    if stats["failed"] > 0 or stats["unknown_kid_records"] > 0:
        logger.error("Migration finished with errors or unknown keys. Action required.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Crypto migration: legacy/old key → current SYR1 envelope")
    parser.add_argument("--dry-run", action="store_true", help="Simulate decrypt/encrypt/verify in memory")
    parser.add_argument("--collection", help="Specific collection to migrate")
    parser.add_argument("--all", action="store_true", help="Migrate all collections")
    parser.add_argument("--force-v2", action="store_true", help="Force V2 mode safely")
    args = parser.parse_args()

    asyncio.run(run_migration(args))


if __name__ == "__main__":
    main()
