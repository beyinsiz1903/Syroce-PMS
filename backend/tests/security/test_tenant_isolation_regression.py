import pytest
import os
import uuid
from fastapi import HTTPException
from unittest.mock import patch

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None

from core.tenant_db import TenantAwareDBProxy
from models.schemas import User

from routers.reservation_detail import get_reservation_full_detail
from routers.folio_ledger import post_payment, ChargeRequest
from routers.pms_guests import update_guest

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "hotel_pms")

TENANT_A = "hotel_a_real"
TENANT_B = "hotel_b_real"

BOOKING_A = "booking_A_test"
GUEST_A = "guest_A_test"
FOLIO_A = "folio_A_test"

USER_B = User(id="user_b", user_id="user_b", email="b@b.com", name="User B", tenant_id=TENANT_B, role="admin", is_active=True, failed_login_attempts=0)
USER_A = User(id="user_a", user_id="user_a", email="a@a.com", name="User A", tenant_id=TENANT_A, role="admin", is_active=True, failed_login_attempts=0)
SUPER_ADMIN_A = User(id="sa_a", user_id="sa_a", email="sa@a.com", name="Super Admin A", tenant_id=TENANT_A, role="super_admin", is_active=True, failed_login_attempts=0)

async def _mongo_or_skip():
    if AsyncIOMotorClient is None:
        pytest.skip("motor not installed")
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=1500)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"MongoDB unreachable ({MONGO_URL})")
    return client

@pytest.fixture
async def live_test_db(monkeypatch):
    client = await _mongo_or_skip()
    db_name = f"test_isolation_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]
    
    # Insert Tenant A data directly into raw_db
    await raw_db.bookings.insert_one({"id": BOOKING_A, "tenant_id": TENANT_A, "guest_id": GUEST_A, "status": "confirmed"})
    await raw_db.guests.insert_one({"id": GUEST_A, "tenant_id": TENANT_A, "name": "Tenant A Guest"})
    await raw_db.folios.insert_one({"id": FOLIO_A, "tenant_id": TENANT_A, "balance": 100.0, "booking_id": BOOKING_A})
    
    # We patch the GLOBAL db object in all relevant modules so they use our throwaway DB.
    # Note: the endpoints use `from core.database import db` directly.
    import core.database
    import routers.reservation_detail
    import routers.folio_ledger
    import routers.pms_guests
    import core.folio_ledger_service
    
    # Create the proxy wrapping our test raw_db
    proxy_db = TenantAwareDBProxy(raw_db)
    
    monkeypatch.setattr(core.database, "db", proxy_db)
    monkeypatch.setattr(routers.reservation_detail, "db", proxy_db)
    monkeypatch.setattr(routers.pms_guests, "db", proxy_db)
    
    # FolioLedgerService stores db on init. We just mock its db.
    monkeypatch.setattr(core.folio_ledger_service, "db", proxy_db)
    
    yield raw_db
    
    await client.drop_database(db_name)
    client.close()

async def test_reservation_full_detail_tenant_isolation(live_test_db):
    """User B cannot access User A's reservation (returns 404)."""
    with pytest.raises(HTTPException) as exc:
        await get_reservation_full_detail(booking_id=BOOKING_A, current_user=USER_B)
    assert exc.value.status_code == 404
    
    # User A CAN access it
    res = await get_reservation_full_detail(booking_id=BOOKING_A, current_user=USER_A)
    assert res is not None

async def test_reservation_payment_tenant_isolation(live_test_db):
    """User B cannot post a payment to User A's folio (returns 404)."""
    req = ChargeRequest(amount=100.0, description="Test", charge_code="PAYMENT", currency="TRY", tax_amount=0)
    with pytest.raises(HTTPException) as exc:
        await post_payment(folio_id=FOLIO_A, body=req, current_user=USER_B)
    assert exc.value.status_code == 404

async def test_guest_update_tenant_isolation(live_test_db):
    """User B cannot update User A's guest profile (returns 404)."""
    update_req = {"name": "Hacked"}
    with pytest.raises(HTTPException) as exc:
        await update_guest(guest_id=GUEST_A, data=update_req, current_user=USER_B)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_super_admin_cross_tenant_access(live_test_db):
    """
    Super Admin in tenant A tries to access hotel_B's reservation.
    For this test, let's create a booking_B in tenant_B.
    """
    BOOKING_B = "booking_B_test"
    await live_test_db.bookings.insert_one({"id": BOOKING_B, "tenant_id": TENANT_B, "status": "confirmed"})
    
    # Assuming there's a mechanism like target_tenant parameter or it automatically falls back
    # The application currently doesn't support this parameter, but we test the behavior we want to implement.
    # We will just pass the target booking and expect it to return 200 for a super admin.
    
    # Currently, this will fail because the endpoint doesn't accept target_tenant and get_current_user
    # assigns TENANT_A to SUPER_ADMIN_A, causing the db query to scope to TENANT_A.
    # To fix this, we will later modify the endpoint to check role and log audit.
    
    # Now pass the target_tenant explicitly (as the endpoint expects)
    res = await get_reservation_full_detail(booking_id=BOOKING_B, current_user=SUPER_ADMIN_A, target_tenant=TENANT_B)
    assert res is not None
    
    # Verify audit log was written
    audit_log = await live_test_db.audit_logs.find_one({
        "user_id": SUPER_ADMIN_A.id, 
        "event_type": "super_admin_cross_tenant_access"
    })
    assert audit_log is not None
    assert audit_log["target_tenant"] == TENANT_B
    assert audit_log["resource"] == f"booking:{BOOKING_B}"

@pytest.mark.asyncio
async def test_invoice_sync_tenant_isolation(live_test_db):
    """Ensure that invoice_sync blocks cross-tenant access via TenantAwareDBProxy."""
    from core.tenant_db import get_db, set_tenant_context, TenantViolationError

    # We should have a tenant context
    set_tenant_context(TENANT_A)
    db = get_db()

    # This should be allowed and scoped to TENANT_A
    await db.invoice_sync.insert_one({"id": "disp_A", "tenant_id": TENANT_A, "state": "PREPARED"})

    # Cannot insert for TENANT_B while in TENANT_A context
    with pytest.raises(TenantViolationError):
        await db.invoice_sync.insert_one({"id": "disp_B", "tenant_id": TENANT_B, "state": "PREPARED"})

    # Reads should only return TENANT_A docs
    docs = await db.invoice_sync.find({}).to_list(100)
    assert len(docs) == 1
    assert docs[0]["tenant_id"] == TENANT_A
