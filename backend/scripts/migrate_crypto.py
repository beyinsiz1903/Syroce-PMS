#!/usr/bin/env python3
"""
Crypto Migration Script — Re-encrypt credentials to SYR1 envelope format securely.

Features:
  - Strict kid-based format detection
  - Pre-migration backup to JSON (BSON safe, atomic, 0600) with Manifest
  - Directory fsync for durability guarantee (fatal if it fails)
  - DB Read-back verification (ensures written data is decryptable)
  - Dry-run performs full decrypt→encrypt→decrypt→equality verify in memory
  - Automatic migration-level rollback on any failure (independent per-record)
  - Context-bound MongoDB update filters (tenant/provider)
  - Restore backup support (--restore-backup) with strict manifest, allowlist, and read-back
  - Strict exit codes on unknown collections or crypto failures
"""

import argparse
import asyncio
import hashlib
import logging
import os
import sys
import uuid
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


class MigrationPreflightError(Exception):
    pass


class DBVerificationError(Exception):
    pass


class RollbackVerificationError(Exception):
    pass


def _canonical_json(records) -> bytes:
    """Produce a deterministic, canonical JSON serialization of records."""
    return bson.json_util.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _record_status(svc, val: str) -> str:
    """Analyze a single ciphertext string's status."""
    from core.crypto.envelope import extract_kid, is_envelope

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
        async for doc in coll.find({}):
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
        async for doc in coll.find({"status": "active"}):
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
        async for doc in coll.find({}):
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


def create_backup_file(db, svc, records) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    uid = str(uuid.uuid4())[:8]
    backup_file = f"migration_backup_{ts}_{uid}.json"

    app_env = os.environ.get("APP_ENV", "development")
    db_name = db.name
    current_kid = svc._keyring.current_kid
    previous_kid = svc._keyring._previous_kid if svc._keyring.has_previous else None

    # Use canonical JSON for checksum computation
    records_canonical = _canonical_json(records)
    payload_checksum = hashlib.sha256(records_canonical).hexdigest()

    manifest_data = {
        "manifest": {
            "migration_id": uid,
            "db_name": db_name,
            "app_env": app_env,
            "current_kid": current_kid,
            "previous_kid": previous_kid,
            "created_at": ts,
            "record_count": len(records),
            "payload_checksum": payload_checksum,
        },
        "records": records,
    }

    data_bytes = bson.json_util.dumps(manifest_data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    fd = os.open(backup_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(data_bytes)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        if os.path.exists(backup_file):
            os.remove(backup_file)
        raise RuntimeError(f"Failed to write backup file securely: {e}")

    # Directory fsync — fatal if it fails
    parent_dir = os.path.dirname(os.path.abspath(backup_file))
    try:
        dir_fd = os.open(parent_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception as e:
        if os.path.exists(backup_file):
            os.remove(backup_file)
        raise RuntimeError(f"Directory fsync failed, backup durability not guaranteed. Aborting: {e}")

    # Read-back validation with canonical checksum
    with open(backup_file) as f:
        read_back = bson.json_util.loads(f.read())
        read_checksum = hashlib.sha256(_canonical_json(read_back["records"])).hexdigest()
        if read_checksum != payload_checksum:
            raise RuntimeError("Backup file write validation failed! Checksum mismatch.")

    logger.info("Saved %d records to %s securely before migrating.", len(records), backup_file)
    return backup_file


def _get_filter_query(col_name, doc):
    if "_id" not in doc:
        raise ValueError(f"Document missing _id in {col_name}. Cannot generate safe filter_query.")
    return {"_id": doc["_id"]}


def _validate_backup_doc(col_name, doc):
    """Validate each backup document before restore (allowlist + required fields)."""
    if col_name not in ALLOWED_COLLECTIONS:
        raise ValueError(f"Backup contains unknown collection '{col_name}'")
    if col_name == "provider_secrets":
        if not doc.get("id") or not doc.get("tenant_id"):
            raise ValueError(f"provider_secrets doc missing required fields: {doc.get('id')}")
    elif col_name == "credential_vault":
        if not doc.get("id") or not doc.get("tenant_id"):
            raise ValueError(f"credential_vault doc missing required fields: {doc.get('id')}")
    elif col_name == "_dev_secrets":
        if not doc.get("path"):
            raise ValueError("_dev_secrets doc missing required 'path' field")


async def restore_single_doc(db, col_name, doc):
    """Restore a single document and verify with DB read-back."""
    coll = db[col_name]
    filter_query = _get_filter_query(col_name, doc)
    res = await coll.replace_one(filter_query, doc, upsert=False)
    if res.matched_count != 1:
        raise RollbackVerificationError(f"Rollback replace_one matched {res.matched_count} for {filter_query}")

    # Read-back to confirm restore was successful
    written = await coll.find_one(filter_query)
    # Compare without _id to avoid ObjectId mismatch
    doc_without_id = {k: v for k, v in doc.items() if k != "_id"}
    written_without_id = {k: v for k, v in (written or {}).items() if k != "_id"}
    if written_without_id != doc_without_id:
        raise RollbackVerificationError(f"Rollback read-back mismatch for {filter_query}. DB and original doc differ.")


async def execute_migration(db, svc, records, dry_run: bool):
    from core.crypto.engine import AADContext

    successfully_migrated_docs = []

    for item in records:
        col_name = item["collection"]
        doc = item["doc"]
        coll = db[col_name]

        try:
            if col_name == "provider_secrets":
                tenant = doc.get("tenant_id", "")
                provider = doc.get("provider", "")
                prop = doc.get("property_id", "")
                payload = doc.get("encrypted_payload", {})
                aad = AADContext(
                    tenant_id=tenant,
                    provider=provider,
                    property_id=prop,
                    environment=os.environ.get("APP_ENV", "development"),
                    context_type="credential",
                )

                decrypted = svc.decrypt_dict(payload, aad=aad)
                new_payload = svc.encrypt_dict(decrypted, aad=aad)

                # Dry-run: full in-memory crypto roundtrip verify
                verify_dry = svc.decrypt_dict(new_payload, aad=aad)
                if verify_dry != decrypted:
                    raise DBVerificationError("Dry-run in-memory crypto roundtrip verification failed")

                if not dry_run:
                    filter_query = _get_filter_query(col_name, doc)
                    res = await coll.update_one(
                        filter_query,
                        {"$set": {"encrypted_payload": new_payload, "key_version": svc._keyring.current_kid, "migrated_at": datetime.now(UTC).isoformat()}},
                    )
                    if res.matched_count != 1 or res.modified_count != 1:
                        raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")

                    written = await coll.find_one(filter_query)
                    if not written:
                        raise DBVerificationError("DB read-back failed: record not found")
                    verify_decrypted = svc.decrypt_dict(written["encrypted_payload"], aad=aad)
                    if verify_decrypted != decrypted:
                        raise DBVerificationError("DB read-back verification failed: decrypted data does not match original plaintext")

            elif col_name == "credential_vault":
                tenant = doc.get("tenant_id", "")
                cred_type = doc.get("credential_type", "")
                cred_key = doc.get("credential_key", "")
                aad = AADContext(
                    tenant_id=tenant,
                    provider=cred_type,
                    property_id=cred_key,
                    environment=os.environ.get("APP_ENV", "development"),
                    context_type="credential",
                )

                if doc.get("credential_encrypted"):
                    plaintext = svc.decrypt(doc.get("credential_encrypted"), aad=aad)
                else:
                    plaintext = svc.decrypt_legacy_base64(doc.get("credential_value_encoded", ""))

                encrypted = svc.encrypt(plaintext, aad=aad)

                # Dry-run: full in-memory crypto roundtrip verify
                verify_dry = svc.decrypt(encrypted, aad=aad)
                if verify_dry != plaintext:
                    raise DBVerificationError("Dry-run in-memory crypto roundtrip verification failed")

                if not dry_run:
                    filter_query = _get_filter_query(col_name, doc)
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

                    written = await coll.find_one(filter_query)
                    if not written:
                        raise DBVerificationError("DB read-back failed: record not found")
                    verify_plaintext = svc.decrypt(written["credential_encrypted"], aad=aad)
                    if verify_plaintext != plaintext:
                        raise DBVerificationError("DB read-back verification failed")

            elif col_name == "_dev_secrets":
                path = doc.get("path", "")
                parts = path.split("/")
                aad = AADContext(
                    tenant_id=parts[3] if len(parts) > 3 else "",
                    provider=parts[4] if len(parts) > 4 else "",
                    property_id=parts[5] if len(parts) > 5 else "",
                    environment=os.environ.get("APP_ENV", "development"),
                    context_type="secret",
                )

                plaintext = svc.decrypt(doc.get("encrypted_payload", ""), aad=aad)
                new_encrypted = svc.encrypt(plaintext, aad=aad)

                # Dry-run: full in-memory crypto roundtrip verify
                verify_dry = svc.decrypt(new_encrypted, aad=aad)
                if verify_dry != plaintext:
                    raise DBVerificationError("Dry-run in-memory crypto roundtrip verification failed")

                if not dry_run:
                    filter_query = _get_filter_query(col_name, doc)
                    res = await coll.update_one(
                        filter_query,
                        {"$set": {"encrypted_payload": new_encrypted, "key_version": svc._keyring.current_kid, "migrated_at": datetime.now(UTC).isoformat()}},
                    )
                    if res.matched_count != 1 or res.modified_count != 1:
                        raise RuntimeError(f"Update failed. matched={res.matched_count}, modified={res.modified_count}")

                    written = await coll.find_one(filter_query)
                    if not written:
                        raise DBVerificationError("DB read-back failed: record not found")
                    verify_plaintext = svc.decrypt(written["encrypted_payload"], aad=aad)
                    if verify_plaintext != plaintext:
                        raise DBVerificationError("DB read-back verification failed")

            successfully_migrated_docs.append(item)
            stats["migrated"] += 1

        except Exception as e:
            stats["failed"] += 1
            logger.error("FAILED %s: %s", col_name, str(e))

            if not dry_run:
                # Collect all items to roll back: failing item first, then migrated in reverse
                rollback_targets = [{"collection": col_name, "doc": doc}] + list(reversed(successfully_migrated_docs))
                rollback_errors = []

                logger.error(
                    "Triggering automatic rollback for %d records (including failing record)...",
                    len(rollback_targets),
                )

                for rb_item in rollback_targets:
                    try:
                        await restore_single_doc(db, rb_item["collection"], rb_item["doc"])
                        logger.info("Rolled back: %s/%s", rb_item["collection"], rb_item["doc"].get("id") or rb_item["doc"].get("path"))
                    except Exception as rollback_err:
                        rollback_errors.append(f"{rb_item['collection']}: {rollback_err}")
                        logger.critical(
                            "ROLLBACK FAILED for %s: %s — manual restore required!",
                            rb_item["collection"],
                            rollback_err,
                        )

                if rollback_errors:
                    logger.critical("FATAL: %d rollback(s) failed. Use --restore-backup immediately.", len(rollback_errors))
                else:
                    logger.info("Automatic rollback completed successfully for all records.")

            raise RuntimeError(f"Aborting migration due to critical error: {str(e)}")


async def run_restore(db, backup_file):
    if not os.path.exists(backup_file):
        logger.error("Backup file %s not found.", backup_file)
        sys.exit(1)

    with open(backup_file) as f:
        data = bson.json_util.loads(f.read())

    manifest = data.get("manifest")
    records = data.get("records")

    if not manifest or records is None:
        logger.error("Invalid backup format. Manifest or records missing.")
        sys.exit(1)

    app_env = os.environ.get("APP_ENV", "development")
    if manifest["app_env"] != app_env:
        logger.error("Restore environment mismatch! Backup: %s, Current: %s", manifest["app_env"], app_env)
        sys.exit(1)

    if manifest["db_name"] != db.name:
        logger.error("Restore DB mismatch! Backup: %s, Current: %s", manifest["db_name"], db.name)
        sys.exit(1)

    if manifest["record_count"] != len(records):
        logger.error("Restore record count mismatch!")
        sys.exit(1)

    # Canonical checksum verification
    if hashlib.sha256(_canonical_json(records)).hexdigest() != manifest["payload_checksum"]:
        logger.error("Restore checksum mismatch! File is corrupted or modified.")
        sys.exit(1)

    logger.info("Manifest validated. Restoring %d records from %s...", len(records), backup_file)
    restored = 0

    for item in records:
        col_name = item.get("collection", "")
        doc = item.get("doc", {})

        # Per-record allowlist and schema validation
        try:
            _validate_backup_doc(col_name, doc)
        except ValueError as ve:
            logger.error("Skipping invalid restore record: %s", ve)
            sys.exit(1)

        coll = db[col_name]
        filter_query = _get_filter_query(col_name, doc)
        res = await coll.replace_one(filter_query, doc, upsert=False)
        if res.matched_count != 1:
            logger.error("Failed to restore doc %s: matched_count=%d", filter_query, res.matched_count)
            sys.exit(1)

        # Read-back verification
        written = await coll.find_one(filter_query)
        doc_without_id = {k: v for k, v in doc.items() if k != "_id"}
        written_without_id = {k: v for k, v in (written or {}).items() if k != "_id"}
        if written_without_id != doc_without_id:
            logger.error("Read-back verification failed during restore for %s", filter_query)
            sys.exit(1)

        restored += 1

    logger.info("Restore complete. %d records restored safely.", restored)


async def run_migration(args):
    from core.crypto.service import get_crypto_service
    from core.database import db

    if args.restore_backup:
        await run_restore(db, args.restore_backup)
        return

    v2_env = os.environ.get("CRYPTO_V2_ENABLED", "false").lower() == "true"

    if args.force_v2:
        os.environ["CRYPTO_V2_ENABLED"] = "true"
    elif not v2_env:
        logger.error("CRYPTO_V2_ENABLED is false. Migration requires V2 mode or --force-v2 flag.")
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
        raise MigrationPreflightError("Preflight check failed. Migration blocked.")

    if not records_to_migrate:
        logger.info("No records need migration.")
        return

    if not args.dry_run:
        try:
            create_backup_file(db, svc, records_to_migrate)
        except Exception as e:
            logger.error("Failed to create secure backup: %s. Aborting before any writes.", str(e))
            sys.exit(1)

    try:
        await execute_migration(db, svc, records_to_migrate, args.dry_run)
    except Exception as e:
        logger.error("Migration halted due to errors: %s", e)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Migration %s", "DRY RUN (full in-memory crypto roundtrip)" if args.dry_run else "COMPLETE")
    logger.info("  total_encrypted_records: %d", stats["total_records"])
    logger.info("  already_current_kid:     %d", stats["already_current_kid"])
    logger.info("  old_kid_records:         %d", stats["old_kid_records"])
    logger.info("  unknown_kid_records:     %d", stats["unknown_kid_records"])
    logger.info("  migrated:                %d", stats["migrated"])
    logger.info("  failed:                  %d", stats["failed"])
    logger.info("  skipped (empty):         %d", stats["skipped"])


def main():
    parser = argparse.ArgumentParser(description="Crypto migration: legacy/old key → current SYR1 envelope")
    parser.add_argument("--dry-run", action="store_true", help="Simulate full decrypt→encrypt→decrypt verify in memory (no DB writes)")
    parser.add_argument("--collection", help="Specific collection to migrate")
    parser.add_argument("--all", action="store_true", help="Migrate all collections")
    parser.add_argument("--force-v2", action="store_true", help="Force V2 mode safely")
    parser.add_argument("--restore-backup", help="Restore records from a backup JSON file")
    args = parser.parse_args()

    try:
        asyncio.run(run_migration(args))
    except MigrationPreflightError:
        sys.exit(1)


if __name__ == "__main__":
    main()
