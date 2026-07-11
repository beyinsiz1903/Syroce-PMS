#!/usr/bin/env python3
"""
Staging DB veri kontrol scripti.

Çalıştırma yeri: DigitalOcean App Platform Console (staging env aktifken)
veya STAGING_MONGO_URL ve STAGING_DB_NAME tanımlı güvenli terminal.

Hiçbir secret/URI değeri ekrana yazılmaz.
"""

import asyncio
import os
import sys

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

STAGING_URL = os.environ.get("STAGING_MONGO_URL", "")
STAGING_DB  = os.environ.get("STAGING_DB_NAME", "")

if not STAGING_URL or not STAGING_DB:
    print("ERROR: STAGING_MONGO_URL and STAGING_DB_NAME must be set.")
    sys.exit(1)


async def main():
    kw = {"tlsCAFile": certifi.where()} if STAGING_URL.startswith("mongodb+srv://") else {}
    client = AsyncIOMotorClient(STAGING_URL, serverSelectionTimeoutMS=5000, **kw)

    try:
        await client.admin.command("ping")
    except Exception as e:
        print(f"ERROR: Cannot connect to staging DB: {e}")
        sys.exit(1)

    db = client[STAGING_DB]
    print(f"Connected DB: {db.name}")
    print()

    # ── provider_secrets ──────────────────────────────────────────────────
    # Migration reads: doc["encrypted_payload"] (dict containing per-field ciphertexts)
    ps_total = await db["provider_secrets"].count_documents({})
    ps_with_payload = await db["provider_secrets"].count_documents(
        {"encrypted_payload": {"$exists": True, "$ne": {}}}
    )
    print(f"provider_secrets:")
    print(f"  total                   : {ps_total}")
    print(f"  has encrypted_payload   : {ps_with_payload}")

    # ── credential_vault ──────────────────────────────────────────────────
    # Migration reads: doc["credential_encrypted"] OR doc["credential_value_encoded"]
    # Only active records are scanned.
    cv_total  = await db["credential_vault"].count_documents({})
    cv_active = await db["credential_vault"].count_documents({"status": "active"})
    cv_with_encrypted = await db["credential_vault"].count_documents({
        "status": "active",
        "credential_encrypted": {"$exists": True, "$ne": ""},
    })
    cv_with_encoded = await db["credential_vault"].count_documents({
        "status": "active",
        "credential_value_encoded": {"$exists": True, "$ne": ""},
    })
    print()
    print(f"credential_vault:")
    print(f"  total                   : {cv_total}")
    print(f"  active                  : {cv_active}")
    print(f"  active + credential_encrypted    : {cv_with_encrypted}")
    print(f"  active + credential_value_encoded: {cv_with_encoded}")

    # ── _dev_secrets ──────────────────────────────────────────────────────
    # Migration reads: doc["encrypted_payload"] (same as provider_secrets)
    dev_total        = await db["_dev_secrets"].count_documents({})
    dev_with_payload = await db["_dev_secrets"].count_documents(
        {"encrypted_payload": {"$exists": True, "$ne": ""}}
    )
    print()
    print(f"_dev_secrets:")
    print(f"  total                   : {dev_total}")
    print(f"  has encrypted_payload   : {dev_with_payload}")

    print()
    # ── Verdict ───────────────────────────────────────────────────────────
    meaningful = (ps_with_payload > 0) or (cv_with_encrypted + cv_with_encoded > 0) or (dev_with_payload > 0)
    if meaningful:
        print("VERDICT: Staging DB has encrypted records — dry-run will be MEANINGFUL.")
    else:
        print("VERDICT: REHEARSAL NOT MEANINGFUL — no encrypted records found.")
        print("         Populate staging DB with encrypted records before running --dry-run.")

    client.close()


asyncio.run(main())
