import asyncio
import os
import sys

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

PROD_URL = os.environ.get("PROD_MONGO_URL")
PROD_DB = os.environ.get("PROD_DB_NAME")
STAGING_URL = os.environ.get("STAGING_MONGO_URL")
STAGING_DB = os.environ.get("STAGING_DB_NAME")

async def copy_collection(prod_db, staging_db, coll_name):
    print(f"Copying {coll_name}...")
    docs = await prod_db[coll_name].find({}).to_list(None)
    if not docs:
        print(f"  {coll_name} is empty in prod.")
        return
    await staging_db[coll_name].drop()
    await staging_db[coll_name].insert_many(docs)
    print(f"  Copied {len(docs)} documents to {coll_name}.")

async def main():
    if not all([PROD_URL, PROD_DB, STAGING_URL, STAGING_DB]):
        print("ERROR: Missing environment variables.")
        print("Please set PROD_MONGO_URL, PROD_DB_NAME, STAGING_MONGO_URL, STAGING_DB_NAME")
        sys.exit(1)

    kw_prod = {"tlsCAFile": certifi.where()} if PROD_URL.startswith("mongodb+srv://") else {}
    prod_client = AsyncIOMotorClient(PROD_URL, serverSelectionTimeoutMS=5000, **kw_prod)

    kw_staging = {"tlsCAFile": certifi.where()} if STAGING_URL.startswith("mongodb+srv://") else {}
    staging_client = AsyncIOMotorClient(STAGING_URL, serverSelectionTimeoutMS=5000, **kw_staging)

    pdb = prod_client[PROD_DB]
    sdb = staging_client[STAGING_DB]

    print(f"Connected to PROD: {pdb.name}")
    print(f"Connected to STAGING: {sdb.name}")

    for coll in ["provider_secrets", "credential_vault", "_dev_secrets"]:
        await copy_collection(pdb, sdb, coll)

    prod_client.close()
    staging_client.close()
    print("Copy complete.")

if __name__ == "__main__":
    asyncio.run(main())
