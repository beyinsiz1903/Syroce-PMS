import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.integrations.invoice_return_repository import (
    CASFailedError,
    PreconditionFailedError,
    ReturnAllocationRequest,
    allocate_return_quantities,
)
from core.integrations.invoice_return_service import (
    ReturnQuantityRequest,
    calculate_full_return_quantities,
    handle_return_action_success,
    handle_return_action_unknown_failure,
    handle_return_action_validation_failure,
    initialize_balances_for_invoice,
    process_return_request,
)
from core.tenant_db import clear_tenant_context, set_tenant_context
from models.enums import ReturnAllocationState

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

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
    db_name = f"test_return_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]

    import core.database
    from core.tenant_db import TenantAwareDBProxy

    proxy_db = TenantAwareDBProxy(raw_db)
    monkeypatch.setattr(core.database, "db", proxy_db)
    monkeypatch.setattr(core.database, "_raw_db", raw_db)
    monkeypatch.setattr(core.database, "client", client)

    yield raw_db

    await client.drop_database(db_name)
    client.close()

@pytest.fixture(autouse=True)
def setup_tenant():
    set_tenant_context("tenant_return_db")
    yield
    clear_tenant_context()

@pytest.fixture
async def migrated_db(live_test_db):
    # Apply V007 migration
    import bootstrap.migrations.versions.v007_f2_create_return_models as mig7
    await mig7.MIGRATION.up(live_test_db)
    yield live_test_db


async def test_initialize_balances_and_full_return(migrated_db):
    tenant_id = "t1"
    invoice_id = "inv_1"
    
    # 1. Insert incoming invoice lines
    lines = [
        {
            "id": "line_1",
            "tenant_id": tenant_id,
            "incoming_invoice_id": invoice_id,
            "line_number": 1,
            "name": "Item 1",
            "quantity": "10.0",
            "unit_code": "C62",
            "unit_price": "100.0",
            "discount_amount": "0.0",
            "line_extension_amount": "1000.0",
            "kdv_rate": "20.0",
            "kdv_amount": "200.0",
            "currency": "TRY",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "version": 1
        },
        {
            "id": "line_2",
            "tenant_id": tenant_id,
            "incoming_invoice_id": invoice_id,
            "line_number": 2,
            "name": "Item 2",
            "quantity": "5.0",
            "unit_code": "C62",
            "unit_price": "50.0",
            "discount_amount": "0.0",
            "line_extension_amount": "250.0",
            "kdv_rate": "20.0",
            "kdv_amount": "50.0",
            "currency": "TRY",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "version": 1
        }
    ]
    
    await migrated_db.incoming_invoice_lines.insert_many(lines)
    
    # 2. Initialize balances
    await initialize_balances_for_invoice(tenant_id, invoice_id)
    
    # Check balances created
    balances = await migrated_db.invoice_return_balances.find({"tenant_id": tenant_id, "source_incoming_invoice_id": invoice_id}).to_list(None)
    assert len(balances) == 2
    
    # 3. Calculate full returns
    full_reqs = await calculate_full_return_quantities(tenant_id, invoice_id)
    assert len(full_reqs) == 2
    assert {r.source_line_id: r.quantity for r in full_reqs} == {"line_1": Decimal("10.0"), "line_2": Decimal("5.0")}
    
    # 4. Process full return
    action_id = "action_1"
    try:
        allocations = await process_return_request(tenant_id, invoice_id, action_id, "FULL")
        assert len(allocations) == 2
        for alloc in allocations:
            assert alloc.state == ReturnAllocationState.RESERVED
    except PreconditionFailedError:
        # Transactions might not be supported on standard standalone mongod in tests
        pytest.skip("MongoDB transactions not supported by test instance")


async def test_partial_return_and_state_transitions(migrated_db):
    tenant_id = "t2"
    invoice_id = "inv_2"
    
    from bson.decimal128 import Decimal128
    line = {
        "id": "line_10",
        "tenant_id": tenant_id,
        "incoming_invoice_id": invoice_id,
        "line_number": 1,
        "name": "Item 10",
        "quantity": "100.0",
        "unit_code": "C62",
        "unit_price": "10.0",
        "discount_amount": "0.0",
        "line_extension_amount": "1000.0",
        "kdv_rate": "20.0",
        "kdv_amount": "200.0",
        "currency": "TRY",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "version": 1
    }
    await migrated_db.incoming_invoice_lines.insert_one(line)
    await initialize_balances_for_invoice(tenant_id, invoice_id)
    
    action_id = "action_partial"
    requests = [ReturnQuantityRequest(source_line_id="line_10", quantity="40.0")]
    
    try:
        allocations = await process_return_request(tenant_id, invoice_id, action_id, "PARTIAL", partial_requests=requests)
        assert len(allocations) == 1
        assert allocations[0].quantity == Decimal("40.0")
        
        # Balance should be reserved
        bal = await migrated_db.invoice_return_balances.find_one({"source_line_id": "line_10"})
        # We need to manually convert Decimal128 back to Decimal to assert
        reserved = bal["reserved_quantity"].to_decimal() if isinstance(bal["reserved_quantity"], Decimal128) else Decimal(bal["reserved_quantity"])
        assert reserved == Decimal("40.0")
        
        # Test transition to PENDING and then CONFIRMED
        await migrated_db.invoice_return_allocations.update_one({"id": allocations[0].id}, {"$set": {"state": "PROVIDER_PENDING"}})
        
        await handle_return_action_success(tenant_id, action_id)
        
        # Check balance after success
        bal2 = await migrated_db.invoice_return_balances.find_one({"source_line_id": "line_10"})
        confirmed = bal2["confirmed_quantity"].to_decimal() if isinstance(bal2["confirmed_quantity"], Decimal128) else Decimal(bal2["confirmed_quantity"])
        reserved2 = bal2["reserved_quantity"].to_decimal() if isinstance(bal2["reserved_quantity"], Decimal128) else Decimal(bal2["reserved_quantity"])
        
        assert confirmed == Decimal("40.0")
        assert reserved2 == Decimal("0.0")
        
        
    except PreconditionFailedError:
        pytest.skip("MongoDB transactions not supported by test instance")


# ==========================================
# API Endpoint Tests
# ==========================================
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from api.routes.incoming_invoice_integrations import require_admin, router
import hashlib
from models.schemas.invoice_lifecycle import InvoiceLifecycleAction

app = FastAPI()
app.include_router(router)

def mock_require_admin():
    class MockUser:
        id = "admin_user_123"
        tenant_id = "tenant_test"
    return MockUser()

app.dependency_overrides[require_admin] = mock_require_admin

async def test_api_missing_header_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/integrations/incoming-invoices/f47ac10b-58cc-4372-a567-0e02b2c3d479/return",
            json={"return_type": "FULL", "request_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}
        )
    # Missing X-Idempotency-Key
    assert response.status_code == 422
    assert "x-idempotency-key" in response.text.lower()

async def test_api_invalid_uuid_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/integrations/incoming-invoices/invalid-uuid/return",
            headers={"X-Idempotency-Key": "key1"},
            json={"return_type": "FULL", "request_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}
        )
    assert response.status_code == 422
    assert "Invalid invoice_id format" in response.text

async def test_api_invoice_not_found_returns_404(migrated_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/integrations/incoming-invoices/f47ac10b-58cc-4372-a567-0e02b2c3d479/return",
            headers={"X-Idempotency-Key": "key1"},
            json={"return_type": "FULL", "request_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}
        )
    assert response.status_code == 404
    assert "Invoice not found" in response.text

async def test_api_duplicate_source_line_returns_422(migrated_db):
    tenant_id = "tenant_test"
    invoice_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    # Create fake invoice
    await migrated_db.invoices.insert_one({"id": invoice_id, "tenant_id": tenant_id})
    # For incoming invoice
    from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
    from models.schemas.invoice_sync import InvoiceProvider
    await migrated_db.incoming_invoices.insert_one({
        "id": invoice_id, "tenant_id": tenant_id, "provider": "NILVERA", "provider_uuid": "123",
        "invoice_number": "ABC", "sender_vkn_tckn": "111", "sender_title": "T",
        "profile": "TICARIFATURA", "answer_status": "PENDING",
        "issue_date": datetime.now(UTC), "received_at": datetime.now(UTC),
        "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC)
    })
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/integrations/incoming-invoices/{invoice_id}/return",
            headers={"X-Idempotency-Key": "key2"},
            json={
                "return_type": "PARTIAL",
                "request_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "lines": [
                    {"source_line_id": "line1", "quantity": "5.0"},
                    {"source_line_id": "line1", "quantity": "10.0"}
                ]
            }
        )
    assert response.status_code == 422
    assert "Duplicate source_line_id" in response.text

async def test_api_provider_contract_unverified_returns_503(migrated_db):
    tenant_id = "tenant_test"
    invoice_id = "f47ac10b-58cc-4372-a567-0e02b2c3d470"
    await migrated_db.incoming_invoices.insert_one({
        "id": invoice_id, "tenant_id": tenant_id, "provider": "NILVERA", "provider_uuid": "123",
        "invoice_number": "ABC", "sender_vkn_tckn": "111", "sender_title": "T",
        "profile": "TICARIFATURA", "answer_status": "PENDING",
        "issue_date": datetime.now(UTC), "received_at": datetime.now(UTC),
        "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC)
    })
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/integrations/incoming-invoices/{invoice_id}/return",
            headers={"X-Idempotency-Key": "key-503-test"},
            json={"return_type": "FULL", "request_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d470"}
        )
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["code"] == "PROVIDER_CONTRACT_NOT_VERIFIED"
    
    # Verify no action or allocation was saved to DB
    action_count = await migrated_db.invoice_lifecycle_actions.count_documents({"idempotency_key": f"{tenant_id}:return:key-503-test"})
    assert action_count == 0
    
async def test_api_idempotency_conflict_returns_409(migrated_db):
    tenant_id = "tenant_test"
    invoice_id = "f47ac10b-58cc-4372-a567-0e02b2c3d471"
    await migrated_db.incoming_invoices.insert_one({
        "id": invoice_id, "tenant_id": tenant_id, "provider": "NILVERA", "provider_uuid": "123",
        "invoice_number": "ABC", "sender_vkn_tckn": "111", "sender_title": "T",
        "profile": "TICARIFATURA", "answer_status": "PENDING",
        "issue_date": datetime.now(UTC), "received_at": datetime.now(UTC),
        "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC)
    })
    
    # Manually insert action with DIFFERENT fingerprint
    from models.schemas.invoice_lifecycle import InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection
    action = InvoiceLifecycleAction(
        id="act_idemp_1",
        tenant_id=tenant_id,
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id=invoice_id,
        source_provider_uuid="123",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, # Doesn't matter
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid="old-uuid",
        idempotency_key=f"{tenant_id}:return:key-conflict",
        request_fingerprint="old-fingerprint",
        requested_by="admin",
        requested_at=datetime.now(UTC)
    )
    await migrated_db.invoice_lifecycle_actions.insert_one(action.model_dump(mode="json"))
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/integrations/incoming-invoices/{invoice_id}/return",
            headers={"X-Idempotency-Key": "key-conflict"},
            json={"return_type": "FULL", "request_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d471"}
        )
    assert response.status_code == 409
    assert "IDEMPOTENCY_CONFLICT" in response.text

async def test_api_idempotency_same_payload_returns_existing(migrated_db):
    tenant_id = "tenant_test"
    invoice_id = "f47ac10b-58cc-4372-a567-0e02b2c3d472"
    request_uuid = "f47ac10b-58cc-4372-a567-0e02b2c3d472"
    await migrated_db.incoming_invoices.insert_one({
        "id": invoice_id, "tenant_id": tenant_id, "provider": "NILVERA", "provider_uuid": "123",
        "invoice_number": "ABC", "sender_vkn_tckn": "111", "sender_title": "T",
        "profile": "TICARIFATURA", "answer_status": "PENDING",
        "issue_date": datetime.now(UTC), "received_at": datetime.now(UTC),
        "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC)
    })
    
    # Calculate exact fingerprint
    fingerprint_raw = f"{tenant_id}:{invoice_id}:FULL::{request_uuid}"
    request_fingerprint = hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()
    
    # Manually insert action with SAME fingerprint
    from models.schemas.invoice_lifecycle import InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection
    action = InvoiceLifecycleAction(
        id="act_idemp_2",
        tenant_id=tenant_id,
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id=invoice_id,
        source_provider_uuid="123",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, 
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid=request_uuid,
        idempotency_key=f"{tenant_id}:return:key-same",
        request_fingerprint=request_fingerprint,
        requested_by="admin",
        requested_at=datetime.now(UTC)
    )
    await migrated_db.invoice_lifecycle_actions.insert_one(action.model_dump(mode="json"))
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/integrations/incoming-invoices/{invoice_id}/return",
            headers={"X-Idempotency-Key": "key-same"},
            json={"return_type": "FULL", "request_uuid": request_uuid}
        )
    # Should not hit 503, should return existing
    assert response.status_code == 200
    data = response.json()
    assert data["return_action_id"] == "act_idemp_2"
    assert data["return_type"] == "FULL"

