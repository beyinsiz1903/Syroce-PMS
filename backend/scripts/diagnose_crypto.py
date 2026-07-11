import asyncio
import os
import sys
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
import glob

# Ensure we can import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.crypto.service import get_crypto_service

PROD_URL = os.environ.get("PROD_MONGO_URL", "")
PROD_DB = os.environ.get("PROD_DB_NAME", "")

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
            print(f"{k}: SET (value hidden, length={len(val)})")
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
        print("\nERROR: PROD_MONGO_URL or PROD_DB_NAME not set. Cannot check database.")
        sys.exit(1)

    kw = {"tlsCAFile": certifi.where()} if PROD_URL.startswith("mongodb+srv://") else {}
    client = AsyncIOMotorClient(PROD_URL, serverSelectionTimeoutMS=5000, **kw)
    db = client[PROD_DB]
    
    print("\n==================================================")
    print("DIAGNOSTIC: credential_vault")
    print("==================================================")
    cv_docs = await db["credential_vault"].find({"status": "active"}).to_list(None)
    
    ok_count = 0
    fail_count = 0
    
    for doc in cv_docs:
        val = doc.get("credential_encrypted") or doc.get("credential_value_encoded")
        if not val:
            continue
            
        doc_id = str(doc.get("_id"))
        tenant_id = doc.get("tenant_id")
        provider = doc.get("service")
        
        aad = tenant_id.encode("utf-8") if tenant_id else None
        
        try:
            svc.decrypt(val, aad=aad)
            ok_count += 1
        except Exception as e:
            fail_count += 1
            print(f"[FAIL] collection=credential_vault, _id={doc_id}, tenant_id={tenant_id}, provider={provider}")
            print(f"       error: {e.__class__.__name__} - {str(e)}")

    print(f"\ncredential_vault Result:")
    print(f"  Total Active: {len(cv_docs)}")
    print(f"  decrypt_ok  : {ok_count}")
    print(f"  failed      : {fail_count}")

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
