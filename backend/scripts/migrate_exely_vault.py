"""
Migration: Move plaintext Exely connection credentials into the SecretsManager
vault and scrub them from the connection document.

Idempotent: only migrates rows that still carry plaintext `username`/`password`
on `exely_connections`. Safe to run multiple times.

Usage:
    python -m scripts.migrate_exely_vault          # dry-run by default
    python -m scripts.migrate_exely_vault --apply  # perform writes
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
# core.database expects MONGO_URL; alias from MONGO_ATLAS_URI when only the latter is provided
if not os.environ.get("MONGO_URL") and os.environ.get("MONGO_ATLAS_URI"):
    os.environ["MONGO_URL"] = os.environ["MONGO_ATLAS_URI"]
os.environ.setdefault("DB_NAME", "syroce-pms")

from core.database import db
from core.secrets import get_secrets_manager

logger = logging.getLogger("migrate_exely_vault")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def migrate(apply: bool) -> dict:
    sm = get_secrets_manager()
    await sm.ensure_indexes()

    migrated = 0
    skipped = 0
    failed = 0

    cursor = db.exely_connections.find(
        {
            "username": {"$exists": True, "$nin": [None, ""]},
            "password": {"$exists": True, "$nin": [None, ""]},
        }
    )
    async for conn in cursor:
        tenant_id = conn.get("tenant_id")
        hotel_code = conn.get("hotel_code")
        username = conn.get("username")
        password = conn.get("password")
        endpoint_url = conn.get("endpoint_url", "")

        if not tenant_id or not hotel_code:
            skipped += 1
            continue

        try:
            existing = await sm.get_provider_credentials(tenant_id, "exely", hotel_code)
            if existing and existing.get("username") and existing.get("password"):
                logger.info("[skip] vault already populated for %s/%s", tenant_id, hotel_code)
                if apply:
                    await db.exely_connections.update_one(
                        {"_id": conn["_id"]},
                        {"$unset": {"username": "", "password": ""}, "$set": {"vault_migrated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()}},
                    )
                skipped += 1
                continue

            if apply:
                await sm.store_provider_credentials(
                    tenant_id=tenant_id,
                    provider="exely",
                    property_id=hotel_code,
                    credentials={
                        "username": username,
                        "password": password,
                        "endpoint_url": endpoint_url,
                    },
                    actor="migration:exely_vault",
                )
                await db.exely_connections.update_one(
                    {"_id": conn["_id"]},
                    {"$unset": {"username": "", "password": ""}, "$set": {"vault_migrated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()}},
                )
            logger.info("[%s] %s/%s", "migrated" if apply else "would-migrate", tenant_id, hotel_code)
            migrated += 1
        except Exception as exc:
            failed += 1
            logger.exception("[fail] %s/%s: %s", tenant_id, hotel_code, exc)

    return {"migrated": migrated, "skipped": skipped, "failed": failed, "applied": apply}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    args = ap.parse_args()

    if not os.environ.get("MONGO_ATLAS_URI") and not os.environ.get("MONGO_URL"):
        raise SystemExit("MONGO_ATLAS_URI or MONGO_URL must be set")

    summary = asyncio.run(migrate(args.apply))
    logger.info("Migration summary: %s", summary)


if __name__ == "__main__":
    main()
