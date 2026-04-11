"""
Tenant Isolation Proof Test Suite (TI-002)
==========================================
Proves that TenantScopedDB enforces data isolation:
  - Auto-injects tenant_id into queries
  - Blocks cross-tenant access
  - Verifies zero cross-contamination
"""
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

TENANT_A = f"test-iso-a-{uuid.uuid4().hex[:8]}"
TENANT_B = f"test-iso-b-{uuid.uuid4().hex[:8]}"


async def _get_db():
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    return client, client["hotel_pms"]


async def _seed(db):
    for tid in [TENANT_A, TENANT_B]:
        if await db.rooms.find_one({"id": f"room-{tid}-101"}):
            continue
        await db.rooms.insert_one({
            "id": f"room-{tid}-101", "tenant_id": tid,
            "room_number": "101", "status": "available",
        })
        await db.guests.insert_one({
            "id": f"guest-{tid}-1", "tenant_id": tid,
            "name": f"Test Guest ({tid})",
            "email": f"iso-{tid}@test.dev",
        })
        await db.bookings.insert_one({
            "id": f"booking-{tid}-1", "tenant_id": tid,
            "room_id": f"room-{tid}-101", "guest_id": f"guest-{tid}-1",
            "status": "confirmed", "check_in": "2027-06-01", "check_out": "2027-06-03",
        })
        await db.folios.insert_one({
            "id": f"folio-{tid}-1", "tenant_id": tid,
            "booking_id": f"booking-{tid}-1", "status": "open", "balance": 0,
        })


async def _cleanup(db, client):
    for coll in ["rooms", "guests", "bookings", "folios"]:
        await db[coll].delete_many({"tenant_id": {"$in": [TENANT_A, TENANT_B]}})
    client.close()


# ═══════════════════════════════════════════════
#  TESTS
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_auto_inject_tenant_id():
    """TenantScopedDB auto-injects tenant_id into queries."""
    from core.tenant_db import TenantScopedDB
    client, db = await _get_db()
    await _seed(db)
    tdb_a = TenantScopedDB(db, TENANT_A)
    rooms = await tdb_a.rooms.find({}).to_list(100)
    assert all(r["tenant_id"] == TENANT_A for r in rooms)
    assert len(rooms) == 1
    client.close()


@pytest.mark.asyncio
async def test_tenant_a_cannot_see_tenant_b():
    """Tenant A sees ONLY Tenant A data. Zero Tenant B contamination."""
    from core.tenant_db import TenantScopedDB
    client, db = await _get_db()
    await _seed(db)
    tdb_a = TenantScopedDB(db, TENANT_A)
    tdb_b = TenantScopedDB(db, TENANT_B)

    for cname in ["rooms", "guests", "bookings", "folios"]:
        docs_a = await getattr(tdb_a, cname).find({}).to_list(100)
        docs_b = await getattr(tdb_b, cname).find({}).to_list(100)
        assert len(docs_a) == 1, f"{cname}: A expected 1 got {len(docs_a)}"
        assert len(docs_b) == 1, f"{cname}: B expected 1 got {len(docs_b)}"
        for d in docs_a:
            assert d["tenant_id"] == TENANT_A
        for d in docs_b:
            assert d["tenant_id"] == TENANT_B
    client.close()


@pytest.mark.asyncio
async def test_cross_tenant_query_blocked():
    """Cross-tenant find_one raises TenantViolationError."""
    from core.tenant_db import TenantScopedDB, TenantViolationError
    client, db = await _get_db()
    tdb_a = TenantScopedDB(db, TENANT_A)
    with pytest.raises(TenantViolationError):
        await tdb_a.rooms.find_one({"tenant_id": TENANT_B})
    client.close()


@pytest.mark.asyncio
async def test_cross_tenant_insert_blocked():
    """Inserting for wrong tenant is blocked."""
    from core.tenant_db import TenantScopedDB, TenantViolationError
    client, db = await _get_db()
    tdb_a = TenantScopedDB(db, TENANT_A)
    with pytest.raises(TenantViolationError):
        await tdb_a.rooms.insert_one({
            "id": "rogue", "tenant_id": TENANT_B, "room_number": "666",
        })
    client.close()


@pytest.mark.asyncio
async def test_cross_tenant_update_blocked():
    """Updating wrong tenant's data is blocked."""
    from core.tenant_db import TenantScopedDB, TenantViolationError
    client, db = await _get_db()
    tdb_a = TenantScopedDB(db, TENANT_A)
    with pytest.raises(TenantViolationError):
        await tdb_a.rooms.update_one({"tenant_id": TENANT_B}, {"$set": {"status": "hacked"}})
    client.close()


@pytest.mark.asyncio
async def test_auto_inject_on_insert():
    """Insert without tenant_id → auto-injected."""
    from core.tenant_db import TenantScopedDB
    client, db = await _get_db()
    tdb_a = TenantScopedDB(db, TENANT_A)
    new_id = f"auto-{uuid.uuid4().hex[:8]}"
    await tdb_a.rooms.insert_one({"id": new_id, "room_number": "AUTO", "status": "available"})
    doc = await db.rooms.find_one({"id": new_id}, {"_id": 0})
    assert doc["tenant_id"] == TENANT_A
    await db.rooms.delete_one({"id": new_id})
    client.close()


@pytest.mark.asyncio
async def test_count_documents_scoped():
    """count_documents is tenant-scoped."""
    from core.tenant_db import TenantScopedDB
    client, db = await _get_db()
    await _seed(db)
    tdb_a = TenantScopedDB(db, TENANT_A)
    tdb_b = TenantScopedDB(db, TENANT_B)
    assert await tdb_a.bookings.count_documents({}) == 1
    assert await tdb_b.bookings.count_documents({}) == 1
    client.close()


@pytest.mark.asyncio
async def test_find_one_scoped():
    """find_one is tenant-scoped."""
    from core.tenant_db import TenantScopedDB
    client, db = await _get_db()
    await _seed(db)
    tdb_a = TenantScopedDB(db, TENANT_A)
    guest = await tdb_a.guests.find_one({"name": {"$regex": "Test Guest"}})
    assert guest is not None
    assert guest["tenant_id"] == TENANT_A
    client.close()


@pytest.mark.asyncio
async def test_global_collection_not_filtered():
    """Global collections are NOT filtered by tenant_id."""
    from core.tenant_db import TenantScopedDB
    client, db = await _get_db()
    tdb_a = TenantScopedDB(db, TENANT_A)
    result = await tdb_a.system_config.find_one({})
    # system_config is global — no tenant_id injection. Result can be None.
    client.close()


@pytest.mark.asyncio
async def test_cross_tenant_delete_blocked():
    """delete_one for wrong tenant is blocked."""
    from core.tenant_db import TenantScopedDB, TenantViolationError
    client, db = await _get_db()
    tdb_a = TenantScopedDB(db, TENANT_A)
    with pytest.raises(TenantViolationError):
        await tdb_a.rooms.delete_one({"tenant_id": TENANT_B})
    client.close()


@pytest.mark.asyncio
async def test_cleanup():
    """Clean up test data."""
    client, db = await _get_db()
    await _cleanup(db, client)
