"""F8A tur-13 regression test: /api/pms/rooms must use stable sort for paginated
calls so that delete+insert cycles don't cause docs in the last insertion batch
to be skipped. Root cause of CI run #25 NO-GO (03-room-move setup): seed
inserted 60 extras at end of rooms_docs (after 500 base rooms, in last chunk),
but `find().skip().limit()` without sort returned them in non-stable order →
3-page pagination missed the extras → fetchedExtras=0 → setup precondition
`fetchedExtras>=50` FAIL.

This test simulates the exact CI scenario at small scale: insert 50 base + 10
extras into an isolated tenant, fetch via paginated `find().sort().skip().limit()`
helper that mirrors the endpoint logic, and assert all 10 extras are returned
regardless of pagination boundaries.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture
def db():
    uri = (
        os.environ.get("MONGO_URL")
        or os.environ.get("MONGO_ATLAS_URI")
        or "mongodb://localhost:27017"
    )
    name = os.environ.get("DB_NAME", "hotel_pms")
    cli = AsyncIOMotorClient(uri)
    return cli[name]


async def _seed_split_dataset(db, tenant_id: str, n_base: int, n_extras: int) -> None:
    docs = []
    for i in range(n_base):
        docs.append(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "room_number": f"BASE_{i:04d}",
                "room_type": "standard",
                "status": "available",
                "is_active": True,
                "is_virtual": False,
                "stress_seed": True,
                "stress_prefix": "TEST_TUR13_",
            }
        )
    for k in range(n_extras):
        docs.append(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "room_number": f"MV_{k:04d}",
                "room_type": "deluxe",
                "status": "available",
                "is_active": True,
                "is_virtual": False,
                "stress_seed": True,
                "stress_prefix": "TEST_TUR13_",
                "room_move_target": True,
            }
        )
    await db.rooms.insert_many(docs, ordered=False)


def _projection() -> dict:
    return {
        "_id": 0,
        "id": 1,
        "room_number": 1,
        "room_type": 1,
        "status": 1,
        "tenant_id": 1,
        "stress_seed": 1,
        "stress_prefix": 1,
        "room_move_target": 1,
    }


def _query(tenant_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "$and": [{"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}],
    }


@pytest.mark.asyncio
async def test_paginated_fetch_with_sort_returns_all_extras(db):
    """Repro of CI fail: 50 base + 10 extras, paginated 3×25, must return all 10 extras."""
    tid = f"F8A_TUR13_TEST_{uuid.uuid4().hex[:8]}"
    try:
        await db.rooms.delete_many({"tenant_id": tid})
        await _seed_split_dataset(db, tid, n_base=50, n_extras=10)

        # Simulate fetchAllByPrefix: 3 pages × 25 = 75 capacity for 60 rooms.
        fetched = []
        page_size = 25
        for page in range(3):
            offset = page * page_size
            rows = (
                await db.rooms.find(_query(tid), _projection())
                .sort("_id", 1)
                .skip(offset)
                .limit(page_size)
                .to_list(page_size)
            )
            fetched.extend(rows)
            if len(rows) < page_size:
                break

        assert len(fetched) == 60, f"expected 60 rooms total, got {len(fetched)}"
        extras = [r for r in fetched if r.get("room_move_target") is True]
        assert len(extras) == 10, (
            f"expected 10 extras with room_move_target=True after stable-sort "
            f"pagination, got {len(extras)} — sort('_id', 1) regression"
        )
    finally:
        await db.rooms.delete_many({"tenant_id": tid})


@pytest.mark.asyncio
async def test_pagination_no_duplicates_no_missed_with_sort(db):
    """Stable-sort pagination must produce unique IDs across all pages (no overlap, no skip)."""
    tid = f"F8A_TUR13_TEST_{uuid.uuid4().hex[:8]}"
    try:
        await db.rooms.delete_many({"tenant_id": tid})
        await _seed_split_dataset(db, tid, n_base=100, n_extras=20)

        seen = set()
        page_size = 50
        for page in range(4):
            offset = page * page_size
            rows = (
                await db.rooms.find(_query(tid), _projection())
                .sort("_id", 1)
                .skip(offset)
                .limit(page_size)
                .to_list(page_size)
            )
            for r in rows:
                rid = r["id"]
                assert rid not in seen, f"duplicate {rid} on page {page}"
                seen.add(rid)
            if len(rows) < page_size:
                break

        assert len(seen) == 120, f"expected 120 unique rooms, got {len(seen)}"
    finally:
        await db.rooms.delete_many({"tenant_id": tid})
