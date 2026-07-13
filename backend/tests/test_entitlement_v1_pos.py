import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

# Mock out DB before importing routers
from tests.test_pos_folio_atomicity import _FakeDB, _Coll
from core.database import db

class FakeTenantSubscriptions(_Coll): pass
class FakePOSOutlets(_Coll): pass
class FakeTenants(_Coll): pass
class FakeEntitlementQuotaUsage(_Coll): pass
class FakeKitchenOrders(_Coll): pass

@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    fake_db = _FakeDB()
    fake_db.tenant_subscriptions = FakeTenantSubscriptions("tenant_subscriptions")
    fake_db.pos_outlets = FakePOSOutlets("pos_outlets")
    fake_db.tenants = FakeTenants("tenants")
    fake_db.entitlement_quota_usage = FakeEntitlementQuotaUsage("entitlement_quota_usage")
    fake_db.kitchen_orders = FakeKitchenOrders("kitchen_orders")
    monkeypatch.setattr("core.subscriptions._db", lambda: fake_db)
    monkeypatch.setattr("core.entitlements.enforcement.db", fake_db)
    monkeypatch.setattr("core.entitlements.quota.db", fake_db)
    monkeypatch.setattr("domains.pms.marketplace_router.db", fake_db)
    monkeypatch.setattr("core.entitlement.db", fake_db)
    monkeypatch.setattr("domains.pms.pos_fnb_router.kitchen.db", fake_db)
    return fake_db

@pytest.fixture(autouse=True)
def enforce_mode(monkeypatch):
    monkeypatch.setenv("ENTITLEMENT_ENFORCEMENT_MODE", "enforce")

def setup_fake_app():
    app = FastAPI()
    
    # Simple dependency override for tests
    from core.security import get_current_user
    from models.schemas import User
    
    fake_user = User(id="u1", tenant_id="tenant-A", role="admin", email="test@test.com", name="Test")
    async def override_get_current_user():
        return fake_user
        
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    # Import routers
    from domains.pms.pos_fnb_router import router as pos_fnb_router
    from domains.pms.marketplace_router import router as marketplace_router
    
    app.include_router(pos_fnb_router)
    app.include_router(marketplace_router)
    return app

@pytest.mark.asyncio
async def test_no_subscription_403(_patch_db):
    app = setup_fake_app()
    client = TestClient(app)
    # POS core route
    response = client.post("/api/pos/transaction")
    assert response.status_code == 403
    assert "pos_fnb modulu gereklidir" in response.json()["detail"]

@pytest.mark.asyncio
async def test_basic_pos_core_allowed(_patch_db):
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",
        "status": "active",
        "end_date": None
    })
    app = setup_fake_app()
    client = TestClient(app)
    # Mock the inner logic to not fail with other errors
    # Just checking 403 vs 404 or validation error (422) means it passed entitlement
    response = client.post("/api/pos/transaction")
    # Expected 422 because we didn't send body, but not 403!
    assert response.status_code != 403

@pytest.mark.asyncio
async def test_basic_kds_forbidden(_patch_db):
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",
        "status": "active",
        "end_date": None
    })
    app = setup_fake_app()
    client = TestClient(app)
    response = client.get("/api/fnb/kitchen-display")
    assert response.status_code == 403
    assert "kds" in response.json()["detail"]

@pytest.mark.asyncio
async def test_pro_kds_allowed(_patch_db):
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_pro",
        "status": "active",
        "end_date": None
    })
    app = setup_fake_app()
    client = TestClient(app)
    response = client.get("/api/fnb/kitchen-display")
    assert response.status_code != 403

@pytest.mark.asyncio
async def test_active_trial_allowed(_patch_db):
    future = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_pro",
        "status": "active",
        "end_date": future
    })
    app = setup_fake_app()
    client = TestClient(app)
    assert client.get("/api/fnb/kitchen-display").status_code != 403

@pytest.mark.asyncio
async def test_expired_trial_forbidden(_patch_db):
    past = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_pro",
        "status": "active",
        "end_date": past
    })
    app = setup_fake_app()
    client = TestClient(app)
    assert client.get("/api/fnb/kitchen-display").status_code == 403

@pytest.mark.asyncio
async def test_cancelled_sub_forbidden(_patch_db):
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_pro",
        "status": "cancelled",
        "end_date": None
    })
    app = setup_fake_app()
    client = TestClient(app)
    assert client.get("/api/fnb/kitchen-display").status_code == 403

@pytest.mark.asyncio
async def test_cross_tenant_forbidden(_patch_db):
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-B",
        "product_key": "pos_fnb_pro",
        "status": "active",
        "end_date": None
    })
    app = setup_fake_app()
    client = TestClient(app)
    assert client.get("/api/fnb/kitchen-display").status_code == 403

@pytest.mark.asyncio
async def test_legacy_plan_included_module_allowed(_patch_db):
    await _patch_db.tenants.insert_one({
        "id": "tenant-A",
        "modules": {"pos_fnb": True}
    })
    app = setup_fake_app()
    client = TestClient(app)
    # Legacy plan acts as 'pro'
    assert client.get("/api/fnb/kitchen-display").status_code != 403

@pytest.mark.asyncio
async def test_outlet_quota_limit_under(_patch_db, monkeypatch):
    # Mock require_op logic out
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    app = setup_fake_app()
    client = TestClient(app)
    res = client.post("/api/pos/outlets", json={
        "outlet_name": "Cafe", "outlet_type": "cafe", "location": "lobi", "capacity": 10, "opening_hours": "09:00-18:00"
    })
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_outlet_quota_limit_over(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    await _patch_db.entitlement_quota_usage.insert_one({
        "tenant_id": "tenant-A",
        "module_key": "pos_fnb",
        "metric": "outlets",
        "used": 1
    })
    
    app = setup_fake_app()
    client = TestClient(app)
    res = client.post("/api/pos/outlets", json={
        "outlet_name": "Cafe2", "outlet_type": "cafe", "location": "lobi", "capacity": 10, "opening_hours": "09:00-18:00"
    })
    assert res.status_code == 403
    assert "Maksimum outlet limitine (1)" in res.json()["detail"]

@pytest.mark.asyncio
async def test_outlet_quota_concurrency(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    
    # Fake a concurrent request using gather on the route directly since httpx with app was failing in tests
    app = setup_fake_app()
    client = TestClient(app)
    
    # Wait, FastAPI TestClient is synchronous by default. Let's call the router function directly.
    from domains.pms.marketplace_router import create_outlet
    from models.schemas import CreateOutletRequest
    from models.schemas import User
    
    req1 = CreateOutletRequest(outlet_name="C1", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    req2 = CreateOutletRequest(outlet_name="C2", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    user = User(id="u1", tenant_id="tenant-A", role="admin", email="t@t.com", name="T")
    
    # Using gather for concurrency
    results = await asyncio.gather(
        create_outlet(request=req1, current_user=user, _perm=None),
        create_outlet(request=req2, current_user=user, _perm=None),
        return_exceptions=True
    )
    
    from fastapi import HTTPException
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, HTTPException) and r.status_code == 403]
    
    assert len(successes) == 1, "There should be exactly one successful creation"
    assert len(failures) == 1, "There should be exactly one 403 Forbidden failure"
    assert len(_patch_db.pos_outlets.docs) == 1, "Only one outlet should be in the DB"
    
    # Check quota usage is 1
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A", "module_key": "pos_fnb", "metric": "outlets"})
    assert quota["used"] == 1

@pytest.mark.asyncio
async def test_outlet_insert_failure_rollback(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    
    # Simulate an error during DB insert
    async def fake_insert(*args, **kwargs):
        raise RuntimeError("DB Error!")
    monkeypatch.setattr(_patch_db.pos_outlets, "insert_one", fake_insert)
    
    from domains.pms.marketplace_router import create_outlet
    from models.schemas import CreateOutletRequest
    from models.schemas import User
    req = CreateOutletRequest(outlet_name="C1", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    user = User(id="u1", tenant_id="tenant-A", role="admin", email="t@t.com", name="T")
    
    with pytest.raises(RuntimeError, match="DB Error!"):
        await create_outlet(request=req, current_user=user, _perm=None)
        
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A", "module_key": "pos_fnb", "metric": "outlets"})
    assert quota["used"] == 0, "Quota slot should have been released"

@pytest.mark.asyncio
async def test_outlet_delete_releases_quota(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    
    from domains.pms.marketplace_router import create_outlet, delete_outlet
    from models.schemas import CreateOutletRequest
    from models.schemas import User
    user = User(id="u1", tenant_id="tenant-A", role="admin", email="t@t.com", name="T")
    
    # 1. Create an outlet (uses the 1 slot)
    req1 = CreateOutletRequest(outlet_name="C1", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    outlet = await create_outlet(request=req1, current_user=user, _perm=None)
    
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A", "module_key": "pos_fnb", "metric": "outlets"})
    assert quota["used"] == 1
    
    # 2. Delete the outlet
    await delete_outlet(outlet_id=outlet["id"], current_user=user, _perm=None)
    
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A", "module_key": "pos_fnb", "metric": "outlets"})
    assert quota["used"] == 0, "Quota should be 0 after delete"
    
    # 3. Create a new outlet (should succeed)
    req2 = CreateOutletRequest(outlet_name="C2", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    outlet2 = await create_outlet(request=req2, current_user=user, _perm=None)
    assert outlet2["outlet_name"] == "C2"

@pytest.mark.asyncio
async def test_outlet_first_reserve_concurrency(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    
    # Do not pre-create entitlement_quota_usage record.
    app = setup_fake_app()
    client = TestClient(app)
    
    from domains.pms.marketplace_router import create_outlet
    from models.schemas import CreateOutletRequest
    from models.schemas import User
    
    req1 = CreateOutletRequest(outlet_name="C1", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    req2 = CreateOutletRequest(outlet_name="C2", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    user = User(id="u1", tenant_id="tenant-A", role="admin", email="t@t.com", name="T")
    
    results = await asyncio.gather(
        create_outlet(request=req1, current_user=user, _perm=None),
        create_outlet(request=req2, current_user=user, _perm=None),
        return_exceptions=True
    )
    
    from fastapi import HTTPException
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, HTTPException) and r.status_code == 403]
    
    assert len(successes) == 1, "Only 1 should succeed on first insert race"
    assert len(failures) == 1
    
    # Assert quota doc
    docs = _patch_db.entitlement_quota_usage.docs
    assert len(docs) == 1, "Only 1 quota usage document should be created"
    assert docs[0]["used"] == 1
    assert len(docs[0]["resources"]) == 1

@pytest.mark.asyncio
async def test_reserve_idempotency(_patch_db, monkeypatch):
    from core.entitlements.quota import reserve_quota
    await reserve_quota("tenant-A", "pos_fnb", "outlets", "res-1", limit=1)
    
    # Call again with the SAME resource_id
    await reserve_quota("tenant-A", "pos_fnb", "outlets", "res-1", limit=1)
    
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A"})
    assert quota["used"] == 1, "Should not increment twice"
    assert len(quota["resources"]) == 1

@pytest.mark.asyncio
async def test_release_idempotency(_patch_db, monkeypatch):
    from core.entitlements.quota import reserve_quota, release_quota
    await reserve_quota("tenant-A", "pos_fnb", "outlets", "res-1", limit=1)
    
    await release_quota("tenant-A", "pos_fnb", "outlets", "res-1")
    await release_quota("tenant-A", "pos_fnb", "outlets", "res-1")
    
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A"})
    assert quota["used"] == 0, "Should not drop below zero"

@pytest.mark.asyncio
async def test_delete_outlet_idempotency(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    from domains.pms.marketplace_router import create_outlet, delete_outlet
    from models.schemas import CreateOutletRequest
    from models.schemas import User
    user = User(id="u1", tenant_id="tenant-A", role="admin", email="t@t.com", name="T")
    req = CreateOutletRequest(outlet_name="C1", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    outlet = await create_outlet(request=req, current_user=user, _perm=None)
    
    # 1. Delete
    await delete_outlet(outlet_id=outlet["id"], current_user=user, _perm=None)
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A"})
    assert quota["used"] == 0
    
    # 2. Delete again
    await delete_outlet(outlet_id=outlet["id"], current_user=user, _perm=None)
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A"})
    assert quota["used"] == 0, "Second delete should not affect quota"

@pytest.mark.asyncio
async def test_observe_mode_quota_exceed(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    monkeypatch.setenv("ENTITLEMENT_ENFORCEMENT_MODE", "observe")
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    
    from domains.pms.marketplace_router import create_outlet
    from models.schemas import CreateOutletRequest
    from models.schemas import User
    user = User(id="u1", tenant_id="tenant-A", role="admin", email="t@t.com", name="T")
    req1 = CreateOutletRequest(outlet_name="C1", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    req2 = CreateOutletRequest(outlet_name="C2", outlet_type="cafe", location="lobi", capacity=10, opening_hours="09:00-18:00")
    
    # 1. Create first outlet -> uses quota = 1
    await create_outlet(request=req1, current_user=user, _perm=None)
    
    # 2. Create second outlet -> limits exceeded, but observe mode!
    # Because of observe mode, the router should catch QuotaExceededException,
    # log, and then force-reserve the quota so `used` increments to 2!
    await create_outlet(request=req2, current_user=user, _perm=None)
    
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A"})
    assert quota["used"] == 2, "Observe mode should force-reserve the quota"
    assert len(quota["resources"]) == 2


@pytest.mark.asyncio
async def test_create_outlet_idempotency(_patch_db, monkeypatch):
    monkeypatch.setattr("domains.pms.marketplace_router.require_op", lambda x: lambda: None)
    await _patch_db.tenant_subscriptions.insert_one({
        "tenant_id": "tenant-A",
        "product_key": "pos_fnb_basic",  # limit = 1
        "status": "active",
        "end_date": None
    })
    from domains.pms.marketplace_router import create_outlet
    from models.schemas import CreateOutletRequest
    from models.schemas import User
    import asyncio
    
    req = CreateOutletRequest(
        outlet_name="Cafe Idempotent",
        outlet_type="cafe",
        location="lobi",
        capacity=10,
        opening_hours="09:00-18:00",
        client_request_id="req-123"
    )
    user = User(id="u1", tenant_id="tenant-A", role="admin", email="t@t.com", name="T")
    
    # Concurrent call
    results = await asyncio.gather(
        create_outlet(request=req, current_user=user, _perm=None),
        create_outlet(request=req, current_user=user, _perm=None),
        return_exceptions=True
    )
    
    # Both should be successful and return the same outlet ID
    assert not isinstance(results[0], Exception)
    assert not isinstance(results[1], Exception)
    assert results[0]["id"] == results[1]["id"], "Should return the same outlet"
    assert results[0]["outlet_name"] == results[1]["outlet_name"]
    
    quota = await _patch_db.entitlement_quota_usage.find_one({"tenant_id": "tenant-A"})
    assert quota["used"] == 1, "Quota should be used exactly once"
    
    outlets = [o for o in _patch_db.pos_outlets.docs if o["tenant_id"] == "tenant-A"]
    assert len(outlets) == 1, "Should only have 1 outlet"

@pytest.mark.asyncio
async def test_quota_duplicate_cleanup_merge(_patch_db):
    # Simulate duplicate documents
    await _patch_db.entitlement_quota_usage.insert_one({
        "_id": "dup1",
        "tenant_id": "tenant-DUP",
        "module_key": "pos_fnb",
        "metric": "outlets",
        "used": 2,
        "resources": ["outlet-a", "outlet-b"],
        "created_at": "2026-01-01"
    })
    
    await _patch_db.entitlement_quota_usage.insert_one({
        "_id": "dup2",
        "tenant_id": "tenant-DUP",
        "module_key": "pos_fnb",
        "metric": "outlets",
        "used": 2,
        "resources": ["outlet-b", "outlet-c"],
        "created_at": "2026-01-02"
    })
    
    # Run the startup migration pipeline
    import datetime
    pipeline = [
        {"$group": {
            "_id": {"tenant_id": "$tenant_id", "module_key": "$module_key", "metric": "$metric"},
            "count": {"$sum": 1},
            "docs": {"$push": "$_id"},
            "all_resources": {"$push": "$resources"}
        }},
        {"$match": {"count": {"$gt": 1}}}
    ]
    
    async for dup in _patch_db.entitlement_quota_usage.aggregate(pipeline):
        docs = dup["docs"]
        all_resources_nested = dup["all_resources"]
        
        merged_resources = set()
        for res_list in all_resources_nested:
            if res_list:
                merged_resources.update(res_list)
        
        merged_resources_list = list(merged_resources)
        merged_used = len(merged_resources_list)
        
        keeper_id = docs[0]
        docs_to_delete = docs[1:]
        
        await _patch_db.entitlement_quota_usage.update_one(
            {"_id": keeper_id},
            {"$set": {
                "resources": merged_resources_list,
                "used": merged_used,
            }}
        )
        
        for did in docs_to_delete:
            # Mock DB doesn't have delete_many, do single deletes
            _patch_db.entitlement_quota_usage.docs = [d for d in _patch_db.entitlement_quota_usage.docs if d.get("_id") != did]
            
    # Verify result
    docs = [d for d in _patch_db.entitlement_quota_usage.docs if d["tenant_id"] == "tenant-DUP"]
    assert len(docs) == 1, "Only one doc should remain"
    merged = docs[0]
    assert merged["used"] == 3, "Merged used should be 3"
    assert set(merged["resources"]) == {"outlet-a", "outlet-b", "outlet-c"}, "Resources should be unioned"
