#!/usr/bin/env python3
"""
Crypto Migration Script — Re-encrypt credentials to SYR1 envelope format securely.

Features:
  - Strict kid-based format detection
  - Pre-migration backup to JSON (BSON safe, atomic, 0600)
  - DB Read-back verification (ensures written data is decryptable)
  - Context-bound MongoDB update filters (tenant/provider)
  - Restore backup support (--restore-backup)
  - Strict exit codes on unknown collections or crypto failures
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime

import bson.json_util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_crypto")

ALLOWED_COLLECTIONS = {"provider_secrets", "credential_vault", "_dev_secrets"}

stats = {
    "total_records": 0,
    "already_current_kid": 0,
    "old_kid_records": 0,
    "unknown_kid_records": 0,
    "migrated": 0,
    "failed": 0,
    "skipped": 0,
}

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

async def collect_records(db, svc, target_collections):
    """Scan the db and return all records that need migration."""
    records_to_migrate = []
    
    if "provider_secrets" in target_collections:
        coll = db["provider_secrets"]
        async for doc in coll.find({}, {"_id": 0}):
            stats["total_records"] += 1
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
                logger.error("provider_secrets/%s has unknown kid formats", doc.get("id"))
                stats["failed"] += 1
                continue
            
            stats["old_kid_records"] += 1
            records_to_migrate.append({"collection": "provider_secrets", "doc": doc})

    if "credential_vault" in target_collections:
        coll = db["credential_vault"]
        async for doc in coll.find({"status": "active"}, {"_id": 0}):
            stats["total_records"] += 1
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
                logger.error("credential_vault/%s has unknown kid", doc.get("id"))
                continue
            
            stats["old_kid_records"] += 1
            records_to_migrate.append({"collection": "credential_vault", "doc": doc})

    if "_dev_secrets" in target_collections:
        coll = db["_dev_secrets"]
        async for doc in coll.find({}, {"_id": 0}):
            stats["total_records"] += 1
            status = _record_status(svc, doc.get("encrypted_payload", ""))
            if status == "skipped":
                stats["skipped"] += 1
                continue
            if status == "already_current_kid":
                stats["already_current_kid"] += 1
                continue
            if status == "unknown_kid_records":
                stats["unknown_kid_records"] += 1
                stats["failed"] += 1
                logger.error("_dev_secrets/%s has unknown kid", doc.get("path"))
                continue
            
            stats["old_kid_records"] += 1
            records_to_migrate.append({"collection": "_dev_secrets", "doc": doc})
            
    return records_to_migrate


def create_backup_file(records) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"migration_backup_{ts}.json"
    
    # 0600 permissions, exclusive creation
    fd = os.open(backup_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        data = bson.json_util.dumps(records)
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
        
    # Read-back verification of backup
    with open(backup_file, "r") as f:
        read_records = bson.json_util.loads(f.read())
        if len(read_records) != len(records):
            raise RuntimeError("Backup file write validation failed! Length mismatch.")
            
    logger.info("Saved %d records to %s securely before migrating.", len(records), backup_file)
    return backup_file


async def execute_migration(db, svc, records, dry_run: bool):
    from core.crypto.engine import AADContext
    
    for item in records:
        col_name = item["collection"]
        doc = item["doc"]
        coll = db[col_name]
        
        try:
            if col_name == "provider_secrets":
                secret_id, tenant, provider, prop = doc.get("id"), doc.get("tenant_id", ""), doc.get("provider", ""), doc.get("property_id", "")
                payload = doc.get("encrypted_payload", {})
                aad = AADContext(tenant_id=tenant, provider=provider, property_id=prop, environment=os.environ.get("APP_ENV", "development"), context_type="credential")
                
                decrypted = svc.decrypt_dict(payload, aad=aad)
                new_payload = svc.encrypt_dict(decrypted, aad=aad)
                
                if not dry_run:
                    filter_query = {"id": secret_id, "tenant_id": tenant, "provider": provider, "property_id": prop}
                    res = await coll.update_one(filter_query, {"$set": {"encrypted_payload": new_payload, "key_version": svc._keyring.current_kid, "migrated_at": datetime.now(UTC).isoformat()}})
                    if res.matched_count != 1 or res.modified_count != 1:
                        raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")
                    
                    # DB Read-back verification
                    written = await coll.find_one(filter_query)
                    if not written:
                        raise RuntimeError("DB read-back failed: record not found")
                    verify_decrypted = svc.decrypt_dict(written["encrypted_payload"], aad=aad)
                    if verify_decrypted != decrypted:
                        raise ValueError("DB read-back verification failed: decrypted data does not match original plaintext")
                        
            elif col_name == "credential_vault":
                cred_id, tenant, cred_type, cred_key = doc.get("id"), doc.get("tenant_id", ""), doc.get("credential_type", ""), doc.get("credential_key", "")
                aad = AADContext(tenant_id=tenant, provider=cred_type, property_id=cred_key, environment=os.environ.get("APP_ENV", "development"), context_type="credential")
                
                if doc.get("credential_encrypted"):
                    plaintext = svc.decrypt(doc.get("credential_encrypted"), aad=aad)
                else:
                    plaintext = svc.decrypt_legacy_base64(doc.get("credential_value_encoded", ""))
                    
                encrypted = svc.encrypt(plaintext, aad=aad)
                
                if not dry_run:
                    filter_query = {"id": cred_id, "tenant_id": tenant, "credential_type": cred_type, "credential_key": cred_key}
                    res = await coll.update_one(filter_query, {"$set": {"credential_encrypted": encrypted, "key_version": svc._keyring.current_kid, "credential_value_encoded": None, "credential_value_hash": None, "migrated_at": datetime.now(UTC).isoformat()}})
                    if res.matched_count != 1 or res.modified_count != 1:
                        raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")
                        
                    # DB Read-back verification
                    written = await coll.find_one(filter_query)
                    verify_plaintext = svc.decrypt(written["credential_encrypted"], aad=aad)
                    if verify_plaintext != plaintext:
                        raise ValueError("DB read-back verification failed")
                        
            elif col_name == "_dev_secrets":
                path = doc.get("path", "")
                parts = path.split("/")
                aad = AADContext(tenant_id=parts[3] if len(parts) > 3 else "", provider=parts[4] if len(parts) > 4 else "", property_id=parts[5] if len(parts) > 5 else "", environment=os.environ.get("APP_ENV", "development"), context_type="secret")
                
                plaintext = svc.decrypt(doc.get("encrypted_payload", ""), aad=aad)
                new_encrypted = svc.encrypt(plaintext, aad=aad)
                
                if not dry_run:
                    filter_query = {"path": path}
                    res = await coll.update_one(filter_query, {"$set": {"encrypted_payload": new_encrypted, "key_version": svc._keyring.current_kid, "migrated_at": datetime.now(UTC).isoformat()}})
                    if res.matched_count != 1 or res.modified_count != 1:
                        raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")
                        
                    # DB Read-back verification
                    written = await coll.find_one(filter_query)
                    verify_plaintext = svc.decrypt(written["encrypted_payload"], aad=aad)
                    if verify_plaintext != plaintext:
                        raise ValueError("DB read-back verification failed")

            stats["migrated"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED %s/%s: %s", col_name, doc.get("id") or doc.get("path"), str(e))
            raise RuntimeError(f"Aborting migration due to critical error on {col_name}: {str(e)}")


async def run_restore(db, backup_file):
    if not os.path.exists(backup_file):
        logger.error("Backup file %s not found.", backup_file)
        sys.exit(1)
        
    with open(backup_file, "r") as f:
        records = bson.json_util.loads(f.read())
        
    logger.info("Restoring %d records from %s...", len(records), backup_file)
    restored = 0
    
    for item in records:
        col_name = item["collection"]
        doc = item["doc"]
        coll = db[col_name]
        
        if col_name == "provider_secrets":
            filter_query = {"id": doc.get("id"), "tenant_id": doc.get("tenant_id"), "provider": doc.get("provider"), "property_id": doc.get("property_id")}
            await coll.replace_one(filter_query, doc)
        elif col_name == "credential_vault":
            filter_query = {"id": doc.get("id"), "tenant_id": doc.get("tenant_id"), "credential_type": doc.get("credential_type"), "credential_key": doc.get("credential_key")}
            await coll.replace_one(filter_query, doc)
        elif col_name == "_dev_secrets":
            filter_query = {"path": doc.get("path")}
            await coll.replace_one(filter_query, doc)
            
        restored += 1
        
    logger.info("Restore complete. %d records restored.", restored)


async def run_migration(args):
    from core.crypto.service import get_crypto_service
    from core.database import db
    
    if args.restore_backup:
        await run_restore(db, args.restore_backup)
        return

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

    try:
        svc = get_crypto_service()
    except Exception as e:
        logger.error("Crypto service failed to initialize: %s", str(e))
        sys.exit(1)
        
    health = svc.health()
    logger.info("Crypto service: %s", health)

    target_collections = set()
    if args.all:
        target_collections = ALLOWED_COLLECTIONS
    elif args.collection:
        if args.collection not in ALLOWED_COLLECTIONS:
            logger.error(f"Invalid collection '{args.collection}'. Allowed: {ALLOWED_COLLECTIONS}")
            sys.exit(1)
        target_collections.add(args.collection)
    else:
        logger.error("Specify --collection <name> or --all")
        sys.exit(1)

    records_to_migrate = await collect_records(db, svc, target_collections)
    
    if stats["failed"] > 0 or stats["unknown_kid_records"] > 0:
        logger.error("Unknown kid formats detected during pre-flight scan. Aborting before any writes.")
        sys.exit(1)
        
    if not records_to_migrate:
        logger.info("No records need migration.")
        return
        
    if not args.dry_run:
        try:
            create_backup_file(records_to_migrate)
        except Exception as e:
            logger.error("Failed to create secure backup: %s. Aborting before any writes.", str(e))
            sys.exit(1)
            
    try:
        await execute_migration(db, svc, records_to_migrate, args.dry_run)
    except Exception:
        logger.error("Migration halted due to errors. Use --restore-backup if needed.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Migration %s", "DRY RUN (Simulated in memory)" if args.dry_run else "COMPLETE")
    logger.info("  total_encrypted_records: %d", stats["total_records"])
    logger.info("  already_current_kid:     %d", stats["already_current_kid"])
    logger.info("  old_kid_records:         %d", stats["old_kid_records"])
    logger.info("  unknown_kid_records:     %d", stats["unknown_kid_records"])
    logger.info("  migrated:                %d", stats["migrated"])
    logger.info("  failed:                  %d", stats["failed"])
    logger.info("  skipped (empty):         %d", stats["skipped"])


def main():
    parser = argparse.ArgumentParser(description="Crypto migration: legacy/old key → current SYR1 envelope")
    parser.add_argument("--dry-run", action="store_true", help="Simulate decrypt/encrypt/verify in memory")
    parser.add_argument("--collection", help="Specific collection to migrate")
    parser.add_argument("--all", action="store_true", help="Migrate all collections")
    parser.add_argument("--force-v2", action="store_true", help="Force V2 mode safely")
    parser.add_argument("--restore-backup", help="Restore records from a backup JSON file")
    args = parser.parse_args()

    asyncio.run(run_migration(args))


if __name__ == "__main__":
    main()
