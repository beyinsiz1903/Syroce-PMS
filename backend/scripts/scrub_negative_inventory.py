"""Task #209 — one-shot scrub for inventory_items with quantity < 0.

Fail-closed guards:
- Pilot tenant is NEVER touched (env-allowlist required).
- Dry-run default; --apply required to write.
- Each clamped row gets a synthetic stock_movements 'adjustment' entry for audit.

Usage:
    python -m scripts.scrub_negative_inventory                 # dry-run, all non-pilot tenants
    python -m scripts.scrub_negative_inventory --apply         # apply changes
    python -m scripts.scrub_negative_inventory --tenant <tid>  # restrict to one tenant
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Scrub negative inventory quantities")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--tenant", default=None, help="Restrict to one tenant_id")
    args = parser.parse_args()

    pilot_tid = os.environ.get("E2E_PILOT_TENANT_ID") or os.environ.get("PILOT_TENANT_ID")
    # Fail-closed: refuse to write unless pilot tenant id is known. Without it
    # we cannot guarantee the pilot exclusion filter below excludes anything.
    if args.apply and not pilot_tid:
        print(
            "REFUSED: --apply requires E2E_PILOT_TENANT_ID or PILOT_TENANT_ID "
            "env var to be set (pilot exclusion guard).",
            file=sys.stderr,
        )
        return 2
    if args.tenant and pilot_tid and args.tenant == pilot_tid:
        print(f"REFUSED: --tenant equals pilot tenant ({pilot_tid}); aborting.", file=sys.stderr)
        return 2

    from core.database import db

    query: dict = {"quantity": {"$lt": 0}}
    if args.tenant:
        query["tenant_id"] = args.tenant
    elif pilot_tid:
        query["tenant_id"] = {"$ne": pilot_tid}

    cursor = db.inventory_items.find(query, {"_id": 0, "id": 1, "tenant_id": 1,
                                              "quantity": 1, "name": 1, "unit_cost": 1})
    rows = await cursor.to_list(100000)
    print(f"Found {len(rows)} inventory_items with quantity < 0")
    by_tenant: dict[str, int] = {}
    for r in rows:
        by_tenant[r.get("tenant_id", "?")] = by_tenant.get(r.get("tenant_id", "?"), 0) + 1
    for tid, n in by_tenant.items():
        marker = " (PILOT — SKIPPED)" if pilot_tid and tid == pilot_tid else ""
        print(f"  tenant={tid} count={n}{marker}")

    if not args.apply:
        print("DRY-RUN — pass --apply to write changes.")
        return 0

    fixed = 0
    for r in rows:
        tid = r.get("tenant_id")
        if pilot_tid and tid == pilot_tid:
            continue  # defense in depth
        item_id = r.get("id")
        old_qty = float(r.get("quantity") or 0)
        if old_qty >= 0:
            continue
        await db.inventory_items.update_one(
            {"id": item_id, "tenant_id": tid},
            {"$set": {"quantity": 0}},
        )
        await db.stock_movements.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "item_id": item_id,
            "movement_type": "adjustment",
            "quantity": 0,
            "unit_cost": float(r.get("unit_cost") or 0),
            "reference": "T209_SCRUB",
            "notes": f"task #209 scrub: clamped from {old_qty} to 0",
            "created_by": "system:scrub_negative_inventory",
            "created_at": datetime.now(UTC).isoformat(),
        })
        fixed += 1
    print(f"Applied: {fixed} rows clamped to 0 (audit entry written for each).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
