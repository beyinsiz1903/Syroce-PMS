"""
Migration: Add hotel_id to all tenants and username to all users.
- hotel_id: 6-digit unique numeric string (auto-generated, retry on collision)
- username: derived from email local-part (uniqueness enforced per-tenant)

Idempotent: only sets fields that are missing/empty.
Safe to run multiple times.

Usage: python -m backend.scripts.migrate_hotel_id_username
"""
import asyncio
import os
import random
import re
import sys
from pathlib import Path

# Allow running as: python backend/scripts/migrate_hotel_id_username.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient

DEMO_TENANT_ID = "57986e4f-7977-44c9-bed9-05aadf38853b"
DEMO_HOTEL_ID = "100001"  # Friendly fixed ID for the demo tenant


def _gen_hotel_id() -> str:
    return f"{random.randint(100000, 999999)}"


def _slugify_username(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.split(r"[@\s]+", s)[0]
    s = re.sub(r"[^a-z0-9._-]+", "", s)
    return s or "user"


async def main():
    uri = os.environ.get("MONGO_ATLAS_URI") or os.environ.get("MONGO_URL")
    if not uri:
        raise SystemExit("MONGO_ATLAS_URI not set")
    db_name = os.environ.get("MONGO_DB", "syroce-pms")

    client = AsyncIOMotorClient(uri)
    db = client[db_name]

    # ---------------- Tenants ----------------
    used_ids: set[str] = set()
    async for t in db.tenants.find({"hotel_id": {"$exists": True, "$ne": None, "$ne": ""}}):
        used_ids.add(str(t["hotel_id"]))

    tenant_updates = 0
    async for t in db.tenants.find({}):
        tid = t.get("id")
        existing_hotel_id = t.get("hotel_id")
        if existing_hotel_id:
            continue

        # Demo tenant gets a fixed nice ID
        if tid == DEMO_TENANT_ID and DEMO_HOTEL_ID not in used_ids:
            new_hid = DEMO_HOTEL_ID
        else:
            for _ in range(50):
                cand = _gen_hotel_id()
                if cand not in used_ids:
                    new_hid = cand
                    break
            else:
                raise RuntimeError("Could not allocate a unique hotel_id")

        await db.tenants.update_one({"id": tid}, {"$set": {"hotel_id": new_hid}})
        used_ids.add(new_hid)
        tenant_updates += 1
        print(f"  Tenant {tid[:8]}... → hotel_id={new_hid} ({t.get('property_name','?')})")

    # Ensure unique index on hotel_id (sparse to allow nulls)
    try:
        await db.tenants.create_index("hotel_id", unique=True, sparse=True, name="hotel_id_unique")
    except Exception as e:
        print(f"  (index note) {e}")

    # ---------------- Users ----------------
    # Import decrypt helper (emails may be AES-encrypted in DB)
    try:
        from security.encrypted_lookup import decrypt_user_doc
    except Exception:
        def decrypt_user_doc(d):
            return d

    user_updates = 0
    # Wipe any garbage usernames from a previous bad run (those starting with aes256gcm)
    bad = await db.users.update_many(
        {"username": {"$regex": "^aes256gcm"}},
        {"$unset": {"username": ""}},
    )
    if bad.modified_count:
        print(f"  Cleared {bad.modified_count} garbage username(s) from prior run")

    # Group users per tenant for uniqueness checks
    tenant_to_used: dict[str | None, set[str]] = {}
    async for u in db.users.find({"username": {"$exists": True, "$ne": None, "$ne": ""}}):
        tenant_to_used.setdefault(u.get("tenant_id"), set()).add(str(u["username"]).lower())

    async for u in db.users.find({}):
        if u.get("username"):
            continue
        tenant_id = u.get("tenant_id")
        # Skip guest users (no tenant) — they keep email-based login
        if not tenant_id:
            continue

        # Decrypt email if it's stored encrypted
        u_dec = decrypt_user_doc(dict(u))
        email = u_dec.get("email") or u.get("email") or ""
        base = _slugify_username(email)
        used = tenant_to_used.setdefault(tenant_id, set())
        candidate = base
        n = 1
        while candidate.lower() in used:
            n += 1
            candidate = f"{base}{n}"
        used.add(candidate.lower())

        await db.users.update_one({"id": u.get("id")}, {"$set": {"username": candidate}})
        user_updates += 1
        if tenant_id == DEMO_TENANT_ID:
            print(f"  Demo user → username={candidate} (email was {email})")

    # Compound unique index (tenant_id + username) — partial: only when username exists
    try:
        await db.users.create_index(
            [("tenant_id", 1), ("username", 1)],
            unique=True,
            partialFilterExpression={"username": {"$type": "string"}},
            name="tenant_username_unique",
        )
    except Exception as e:
        print(f"  (index note) {e}")

    print()
    print(f"✅ Migration complete: {tenant_updates} tenant(s), {user_updates} user(s) updated")
    print(f"📋 Demo login: hotel_id={DEMO_HOTEL_ID}  username=demo  password=demo123")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
