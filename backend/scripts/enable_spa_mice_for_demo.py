"""
One-shot migration: enable Spa & MICE add-on modules for the Syroce Demo
tenant so its existing mice_menus / spa data keeps working after the
add-on gating is introduced (v106 follow-up — Yol 2).

Run once:
    cd backend && python -m scripts.enable_spa_mice_for_demo

Idempotent — safe to re-run.
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

DEMO_TENANT_ID = "5bad4a34-6ee3-4566-9053-741b7375a9cf"


async def main() -> int:
    mongo = os.environ.get("MONGO_ATLAS_URI") or os.environ.get("MONGO_URL")
    if not mongo:
        print("ERROR: MONGO_ATLAS_URI / MONGO_URL not set", file=sys.stderr)
        return 1

    client = AsyncIOMotorClient(mongo)
    db = client["syroce-pms"]

    tenant = await db.tenants.find_one({"id": DEMO_TENANT_ID}, {"_id": 0, "name": 1, "modules": 1})
    if not tenant:
        print(f"ERROR: tenant {DEMO_TENANT_ID} not found", file=sys.stderr)
        return 2

    current_modules = tenant.get("modules") or {}
    already_on = current_modules.get("spa") is True and current_modules.get("mice") is True
    if already_on:
        print(f"OK: tenant '{tenant.get('name')}' already has spa & mice enabled — nothing to do.")
        return 0

    res = await db.tenants.update_one(
        {"id": DEMO_TENANT_ID},
        {"$set": {"modules.spa": True, "modules.mice": True}},
    )
    print(
        f"Demo tenant '{tenant.get('name')}': spa & mice add-ons enabled "
        f"(matched={res.matched_count}, modified={res.modified_count})."
    )

    # Sanity check downstream impact
    spa_count = await db.spa_services.count_documents({"tenant_id": DEMO_TENANT_ID})
    mice_count = await db.mice_menus.count_documents({"tenant_id": DEMO_TENANT_ID})
    print(f"Existing data preserved — spa_services={spa_count}, mice_menus={mice_count}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
