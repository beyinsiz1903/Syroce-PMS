import asyncio
import glob
import os
import sys

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

# Ensure we can import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.crypto.engine import AADContext
from core.crypto.envelope import extract_kid, is_envelope
from core.crypto.service import get_crypto_service

PROD_URL = os.environ.get("PROD_MONGO_URL") or os.environ.get("MONGO_URL")
PROD_DB = os.environ.get("PROD_DB_NAME") or os.environ.get("DB_NAME")

async def analyze_collection(db, svc, collection_name: str, doc_generator, val_extractor, aad_extractor):
    print(f"\n==================================================")
    print(f"DIAGNOSTIC: {collection_name}")
    print(f"==================================================")

    docs = await doc_generator(db[collection_name])

    ok_count = 0
    fail_count = 0

    for doc in docs:
        val = val_extractor(doc)
        if not val:
            continue

        doc_id = str(doc.get("_id") or doc.get("id") or doc.get("path"))
        tenant_id = doc.get("tenant_id")
        provider = doc.get("service") or doc.get("provider")

        aad = aad_extractor(doc)
        kid = extract_kid(val) if is_envelope(val) else "legacy"

        try:
            svc.decrypt(val, aad=aad)
            ok_count += 1
            # We don't print OK records to keep logs clean
        except Exception as e:
            fail_count += 1
            print(f"[FAIL] col={collection_name} id={doc_id} tenant={tenant_id} provider={provider} kid={kid}")
            print(f"       error: {e.__class__.__name__} - {str(e)}")

    print(f"\n{collection_name} Result:")
    print(f"  Total Checked: {len(docs)}")
    print(f"  decrypt_ok   : {ok_count}")
    print(f"  failed       : {fail_count}")


async def main():
    print("==================================================")
    print("RUNTIME ENV CHECK")
    print("==================================================")
    keys = [
        "CM_MASTER_KEY_CURRENT",
        "CM_MASTER_KEY_PREVIOUS",
        "CM_KEY_VERSION",
        "CM_KEY_VERSION_CURRENT",
        "CM_KEY_VERSION_PREVIOUS"
    ]
    for k in keys:
        val = os.environ.get(k)
        if val:
            if "VERSION" in k:
                print(f"{k}: SET (value: {val})")
            else:
                print(f"{k}: SET")
        else:
            print(f"{k}: NOT SET")

    print("\n==================================================")
    print("CRYPTO SERVICE INITIALIZATION")
    print("==================================================")
    try:
        svc = get_crypto_service()
        print(f"v2_enabled: {svc.v2_enabled}")
        print(f"current_kid: {svc._keyring.current_kid}")
        print(f"has_previous_key: {bool(svc._keyring.previous_master)}")
    except Exception as e:
        print(f"Failed to load crypto service: {e}")
        sys.exit(1)

    if not PROD_URL or not PROD_DB:
        print("\nERROR: Database environment variables (MONGO_URL/DB_NAME) not set.")
        sys.exit(1)

    db_lower = PROD_DB.lower()
    if "staging" in db_lower or "test" in db_lower or "rehearsal" in db_lower:
        print(f"\nERROR: DB_NAME ({PROD_DB}) implies staging/test. This script is intended for PRODUCTION diagnostics.")
        sys.exit(1)

    kw = {"tlsCAFile": certifi.where()} if PROD_URL.startswith("mongodb+srv://") else {}
    client = AsyncIOMotorClient(PROD_URL, serverSelectionTimeoutMS=5000, **kw)
    db = client[PROD_DB]

    print(f"\nConnected to Database: {PROD_DB}")

    # 1. credential_vault
    async def get_cv_docs(coll):
        return await coll.find({"status": "active"}).to_list(None)

    await analyze_collection(
        db, svc, "credential_vault",
        get_cv_docs,
        lambda d: d.get("credential_encrypted") or d.get("credential_value_encoded"),
        lambda d: d.get("tenant_id").encode("utf-8") if d.get("tenant_id") else None
    )

    # 2. provider_secrets
    async def get_ps_docs(coll):
        return await coll.find({}).to_list(None)

    await analyze_collection(
        db, svc, "provider_secrets",
        get_ps_docs,
        lambda d: d.get("credentials_encrypted") or d.get("token_encrypted"),
        lambda d: d.get("tenant_id").encode("utf-8") if d.get("tenant_id") else None
    )

    # 3. _dev_secrets
    async def get_ds_docs(coll):
        return await coll.find({}).to_list(None)

    def extract_ds_aad(doc):
        path = doc.get("path", "")
        parts = path.split("/")
        return AADContext(
            tenant_id=parts[3] if len(parts) > 3 else "",
            provider=parts[4] if len(parts) > 4 else "",
            property_id=parts[5] if len(parts) > 5 else "",
            environment=os.environ.get("APP_ENV", "development"),
            context_type="secret",
        )

    await analyze_collection(
        db, svc, "_dev_secrets",
        get_ds_docs,
        lambda d: d.get("encrypted_payload"),
        extract_ds_aad
    )

    print("\n==================================================")
    print("BACKUP DISCOVERY")
    print("==================================================")
    backups = glob.glob("migration_backup_*.json")
    if backups:
        for b in backups:
            print(f"Found backup: {b}")
    else:
        print("No migration_backup_*.json files found in the current directory.")

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
