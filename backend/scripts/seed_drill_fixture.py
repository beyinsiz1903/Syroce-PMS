"""Seed fake multi-tenant fixture for tenant restore drill smoke test.

Phase 2 supporting tool. Sandbox-only: refuses Atlas URLs.

Creates a small but realistic 3-tenant dataset across 7 collections so that
mongodump → tenant-scoped restore → prune → validation can be exercised
end-to-end without touching any production data.

Tenants:
    T1 — restore target tenant
    T2 — leak/prune control tenant
    T3 — additional cross-tenant noise

Collections (all carry tenant_id):
    tenants, users, guests, rooms, bookings, folios, payments

Usage:
    python backend/scripts/seed_drill_fixture.py \
        --mongo-url mongodb://127.0.0.1:27018 \
        --db-name syroce_drill_source
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

# Reuse the hardened Atlas-URL detector from tools/tenant_restore_drill.py
# so seed_drill_fixture cannot lag behind the canonical guard
# (architect review: drop_database call must be protected by the SAME
# guard logic used by the drill helper).
_TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from tenant_restore_drill import _is_atlas_url  # noqa: E402

TENANTS = ["T1", "T2", "T3"]
COLLECTIONS = (
    "tenants",
    "users",
    "guests",
    "rooms",
    "bookings",
    "folios",
    "payments",
)


async def seed(mongo_url: str, db_name: str) -> dict:
    if _is_atlas_url(mongo_url):
        raise SystemExit(
            f"REFUSE: Atlas URL detected ({mongo_url[:40]}...). "
            "seed_drill_fixture is sandbox-only."
        )

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=3000)
    # Validate we can ping before destructive drop.
    await client.admin.command("ping")
    await client.drop_database(db_name)
    db = client[db_name]

    summary: dict = {"db": db_name, "tenants": {}}

    for ti, tid in enumerate(TENANTS):
        await db["tenants"].insert_one(
            {"_id": ObjectId(), "tenant_id": tid, "name": f"Hotel {tid}"}
        )

        for u in range(2):
            await db["users"].insert_one(
                {
                    "_id": ObjectId(),
                    "tenant_id": tid,
                    "username": f"user_{tid}_{u}",
                    "role": "front_desk",
                }
            )

        room_ids = []
        for r in range(3):
            rid = ObjectId()
            room_ids.append(rid)
            await db["rooms"].insert_one(
                {
                    "_id": rid,
                    "tenant_id": tid,
                    "room_number": f"{ti+1}0{r+1}",
                }
            )

        guest_ids = []
        for g in range(3):
            gid = ObjectId()
            guest_ids.append(gid)
            await db["guests"].insert_one(
                {"_id": gid, "tenant_id": tid, "name": f"Guest {tid}-{g}"}
            )

        booking_ids = []
        for b in range(2):
            bid = ObjectId()
            booking_ids.append(bid)
            await db["bookings"].insert_one(
                {
                    "_id": bid,
                    "tenant_id": tid,
                    "guest_id": guest_ids[b],
                    "room_id": room_ids[b],
                    "checkin": "2026-05-10",
                    "checkout": "2026-05-12",
                }
            )

        for bid in booking_ids:
            await db["folios"].insert_one(
                {
                    "_id": ObjectId(),
                    "tenant_id": tid,
                    "booking_id": bid,
                    "balance": 1500.0,
                }
            )

        await db["payments"].insert_one(
            {
                "_id": ObjectId(),
                "tenant_id": tid,
                "amount": 1500.0,
                "method": "card",
            }
        )

        per_coll: dict[str, int] = {}
        for coll in COLLECTIONS:
            per_coll[coll] = await db[coll].count_documents({"tenant_id": tid})
        summary["tenants"][tid] = per_coll

    client.close()
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--mongo-url",
        default=os.environ.get("DRILL_MONGO_URL", "mongodb://127.0.0.1:27018"),
    )
    p.add_argument(
        "--db-name",
        default=os.environ.get("DRILL_SOURCE_DB", "syroce_drill_source"),
    )
    args = p.parse_args(argv)

    summary = asyncio.run(seed(args.mongo_url, args.db_name))
    print(json.dumps(summary, indent=2, default=str))
    print(
        f"\nSeeded {len(TENANTS)} tenants × {len(COLLECTIONS)} collections "
        f"into {args.db_name} on {args.mongo_url}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
