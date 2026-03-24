"""
Secret Migration Script — Migrates legacy credentials to the new secrets manager.

Handles:
  1. provider_secrets collection (Exely XOR-encrypted credentials)
  2. hotelrunner_connections (plaintext token/hr_id)
  3. cm_connectors (channel_manager infra vault credentials)

Usage:
  cd /app/backend
  python -m scripts.migrate_secrets [--dry-run] [--tenant TENANT_ID]

Safety:
  - Never logs plaintext secrets
  - Marks migrated records with migration metadata
  - Supports dry-run mode
  - Idempotent: skip already-migrated records
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_secrets")


async def migrate_provider_secrets(sm, db, tenant_filter: str, dry_run: bool) -> dict:
    """Migrate provider_secrets (Exely credentials)."""
    from domains.channel_manager.credential_vault import get_decrypted_credentials

    query = {}
    if tenant_filter:
        query["tenant_id"] = tenant_filter

    records = await db.provider_secrets.find(query, {"_id": 0}).to_list(1000)
    stats = {"found": len(records), "migrated": 0, "skipped": 0, "errors": 0}

    for rec in records:
        tenant_id = rec.get("tenant_id", "")
        provider = rec.get("provider", "")
        property_id = rec.get("property_id", "")

        if rec.get("migrated_to_secrets_manager"):
            stats["skipped"] += 1
            continue

        try:
            creds = await get_decrypted_credentials(tenant_id, provider, property_id)
            if not creds:
                logger.warning("No decryptable credentials for %s/%s/%s", tenant_id, provider, property_id)
                stats["skipped"] += 1
                continue

            if dry_run:
                logger.info("[DRY-RUN] Would migrate: %s/%s/%s (fields: %s)",
                            tenant_id, provider, property_id, list(creds.keys()))
                stats["migrated"] += 1
                continue

            await sm.store_provider_credentials(
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                credentials=creds,
                actor="migration_script",
            )

            # Mark as migrated
            await db.provider_secrets.update_one(
                {"id": rec["id"]},
                {"$set": {
                    "migrated_to_secrets_manager": True,
                    "migrated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            stats["migrated"] += 1
            logger.info("Migrated: %s/%s/%s", tenant_id, provider, property_id)

        except Exception as e:
            stats["errors"] += 1
            logger.error("Failed to migrate %s/%s/%s: %s", tenant_id, provider, property_id, type(e).__name__)

    return stats


async def migrate_hotelrunner_connections(sm, db, tenant_filter: str, dry_run: bool) -> dict:
    """Migrate plaintext HotelRunner tokens to secrets manager."""
    query = {"is_active": True}
    if tenant_filter:
        query["tenant_id"] = tenant_filter

    records = await db.hotelrunner_connections.find(query, {"_id": 0}).to_list(1000)
    stats = {"found": len(records), "migrated": 0, "skipped": 0, "errors": 0}

    for rec in records:
        tenant_id = rec.get("tenant_id", "")
        token = rec.get("token", "")
        hr_id = rec.get("hr_id", "")

        if rec.get("credentials_ref", "").startswith("secrets_manager::"):
            stats["skipped"] += 1
            continue

        if not token:
            stats["skipped"] += 1
            continue

        try:
            creds = {"token": token, "hr_id": hr_id}

            if dry_run:
                logger.info("[DRY-RUN] Would migrate HotelRunner: %s/hr_id=%s", tenant_id, hr_id)
                stats["migrated"] += 1
                continue

            await sm.store_provider_credentials(
                tenant_id=tenant_id,
                provider="hotelrunner",
                property_id=hr_id or "default",
                credentials=creds,
                actor="migration_script",
            )

            # Remove plaintext token, add credentials_ref
            await db.hotelrunner_connections.update_one(
                {"tenant_id": tenant_id, "hr_id": hr_id},
                {
                    "$set": {
                        "credentials_ref": f"secrets_manager::hotelrunner::{hr_id}",
                        "migrated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "$unset": {"token": ""},
                },
            )
            stats["migrated"] += 1
            logger.info("Migrated HotelRunner: %s/%s", tenant_id, hr_id)

        except Exception as e:
            stats["errors"] += 1
            logger.error("Failed to migrate HotelRunner %s/%s: %s", tenant_id, hr_id, type(e).__name__)

    return stats


async def run_migration(tenant_filter: str, dry_run: bool):
    """Main migration entry point."""
    from dotenv import load_dotenv
    load_dotenv()

    from core.database import db
    from core.secrets import get_secrets_manager

    sm = get_secrets_manager()

    logger.info("=" * 60)
    logger.info("SECRET MIGRATION STARTED%s", " [DRY-RUN]" if dry_run else "")
    logger.info("Provider: %s", os.environ.get("SECRETS_PROVIDER", "local_dev"))
    logger.info("=" * 60)

    # 1. Migrate provider_secrets (Exely)
    logger.info("\n--- Phase 1: provider_secrets (Exely) ---")
    ps_stats = await migrate_provider_secrets(sm, db, tenant_filter, dry_run)
    logger.info("provider_secrets: %s", ps_stats)

    # 2. Migrate HotelRunner connections
    logger.info("\n--- Phase 2: hotelrunner_connections ---")
    hr_stats = await migrate_hotelrunner_connections(sm, db, tenant_filter, dry_run)
    logger.info("hotelrunner_connections: %s", hr_stats)

    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION COMPLETE%s", " [DRY-RUN]" if dry_run else "")
    logger.info("provider_secrets: %s", ps_stats)
    logger.info("hotelrunner:      %s", hr_stats)
    logger.info("=" * 60)

    return {"provider_secrets": ps_stats, "hotelrunner": hr_stats}


def main():
    parser = argparse.ArgumentParser(description="Migrate legacy secrets to new secrets manager")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--tenant", type=str, default="", help="Filter by tenant_id")
    args = parser.parse_args()

    asyncio.run(run_migration(args.tenant, args.dry_run))


if __name__ == "__main__":
    main()
