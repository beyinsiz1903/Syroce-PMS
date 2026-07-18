import os
import uuid
from datetime import UTC, datetime

import pytest

from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.tenant_db import clear_tenant_context, set_tenant_context
from models.schemas.invoice_lifecycle import (
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)

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
    db_name = f"test_lifecycle_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]

    import core.database
    from core.tenant_db import TenantAwareDBProxy

    proxy_db = TenantAwareDBProxy(raw_db)
    monkeypatch.setattr(core.database, "db", proxy_db)
    monkeypatch.setattr(core.database, "_raw_db", raw_db)

    yield raw_db

    await client.drop_database(db_name)
    client.close()

@pytest.fixture(autouse=True)
def setup_tenant():
    set_tenant_context("tenant_realdb")
    yield
    clear_tenant_context()

@pytest.fixture
async def migrated_db(live_test_db):
    import bootstrap.migrations.versions.v005_incoming_invoice_lifecycle as mig5
    import bootstrap.migrations.versions.v006_incoming_invoice_answer_atomicity as mig6
    await mig5.MIGRATION.up(live_test_db)
    await mig6.MIGRATION.up(live_test_db)
    yield live_test_db

async def test_repo_tenant_isolation(migrated_db):
    tenant_1 = "tenant_1"
    tenant_2 = "tenant_2"
    action_id = str(uuid.uuid4())

    action = InvoiceLifecycleAction(
        id=action_id,
        tenant_id=tenant_1,
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_1",
        source_provider_uuid="uuid-1",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid="req-1",
        idempotency_key=f"{tenant_1}:inv_1:ACCEPT:req-1",
        request_fingerprint="fingerprint-1",
        requested_by="admin",
        requested_at=datetime.now(UTC)
    )

    await InvoiceLifecycleRepository.create_action(action)

    # tenant 1 sees it
    assert await InvoiceLifecycleRepository.get_by_id(tenant_1, action_id) is not None
    # tenant 2 does not see it
    assert await InvoiceLifecycleRepository.get_by_id(tenant_2, action_id) is None

    # test lease isolation
    claimed_t2 = await InvoiceLifecycleRepository.claim_action_lease(tenant_2, action_id, "worker", 60)
    assert claimed_t2 is None

    claimed_t1 = await InvoiceLifecycleRepository.claim_action_lease(tenant_1, action_id, "worker", 60)
    assert claimed_t1 is not None
    assert claimed_t1.id == action_id

    # cross-tenant update should fail
    updated_t2 = await InvoiceLifecycleRepository.update_action_result(tenant_2, action_id, "worker", {"state": InvoiceLifecycleActionState.SUCCEEDED.value})
    assert not updated_t2

    # correct tenant update should succeed
    updated_t1 = await InvoiceLifecycleRepository.update_action_result(tenant_1, action_id, "worker", {"state": InvoiceLifecycleActionState.SUCCEEDED.value})
    assert updated_t1

async def test_repo_concurrent_workers_and_stale_lease(migrated_db):
    tenant_id = "tenant_1"
    action_id = str(uuid.uuid4())

    action = InvoiceLifecycleAction(
        id=action_id,
        tenant_id=tenant_id,
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_2",
        source_provider_uuid="uuid-2",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid="req-2",
        idempotency_key=f"{tenant_id}:inv_2:ACCEPT:req-2",
        request_fingerprint="fingerprint-2",
        requested_by="admin",
        requested_at=datetime.now(UTC)
    )
    await InvoiceLifecycleRepository.create_action(action)

    # Worker 1 claims it
    w1_lease = await InvoiceLifecycleRepository.claim_action_lease(tenant_id, action_id, "worker_1", 1) # 1 second lease
    assert w1_lease is not None

    # Worker 2 tries to claim it concurrently
    w2_lease = await InvoiceLifecycleRepository.claim_action_lease(tenant_id, action_id, "worker_2", 60)
    assert w2_lease is None # Cannot claim!

    import asyncio
    await asyncio.sleep(1.5) # Wait for lease to become stale

    # Worker 2 tries again -> stale lease recovery
    w2_lease_recovered = await InvoiceLifecycleRepository.claim_action_lease(tenant_id, action_id, "worker_2", 60)
    assert w2_lease_recovered is not None
    assert w2_lease_recovered.lifecycle_lease_owner == "worker_2"
    assert w2_lease_recovered.state == InvoiceLifecycleActionState.PROCESSING

async def test_cross_tenant_incoming_invoice_get_returns_none(migrated_db):
    from datetime import UTC, datetime

    from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
    from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
    from models.schemas.invoice_sync import InvoiceProvider

    invoice = IncomingInvoice(
        id="inv_cross", tenant_id="tenant_A", provider=InvoiceProvider.NILVERA, provider_uuid="1111",
        invoice_number="ABC", sender_vkn_tckn="111", sender_title="Test", profile=IncomingInvoiceProfile.COMMERCIAL,
        answer_status=IncomingInvoiceAnswerStatus.PENDING, issue_date=datetime.now(UTC), received_at=datetime.now(UTC),
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
    )
    await IncomingInvoiceRepository.save(invoice)

    # Try to get from tenant_B
    result = await IncomingInvoiceRepository.get_by_id("tenant_B", "inv_cross")
    assert result is None

    # Get from tenant_A should work
    result_a = await IncomingInvoiceRepository.get_by_id("tenant_A", "inv_cross")
    assert result_a is not None

async def test_cross_tenant_incoming_invoice_update_fails(migrated_db):
    from datetime import UTC, datetime

    from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
    from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
    from models.schemas.invoice_sync import InvoiceProvider

    invoice = IncomingInvoice(
        id="inv_cross_upd", tenant_id="tenant_A", provider=InvoiceProvider.NILVERA, provider_uuid="2222",
        invoice_number="ABC", sender_vkn_tckn="111", sender_title="Test", profile=IncomingInvoiceProfile.COMMERCIAL,
        answer_status=IncomingInvoiceAnswerStatus.PENDING, issue_date=datetime.now(UTC), received_at=datetime.now(UTC),
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
    )
    await IncomingInvoiceRepository.save(invoice)

    # Try to update from tenant_B
    updated = await IncomingInvoiceRepository.update_answer_status("tenant_B", "inv_cross_upd", IncomingInvoiceAnswerStatus.APPROVED)
    assert updated is False

    # Check it wasn't updated
    doc = await IncomingInvoiceRepository.get_by_id("tenant_A", "inv_cross_upd")
    assert doc.answer_status == IncomingInvoiceAnswerStatus.PENDING

async def test_repo_answer_guard_atomicity(migrated_db):
    from datetime import UTC, datetime

    from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
    from models.schemas.invoice_lifecycle import (
        ActionCreationResult,
        InvoiceLifecycleAction,
        InvoiceLifecycleActionState,
        InvoiceLifecycleActionType,
        InvoiceLifecycleDirection,
    )

    tenant_id = "tenant_atomic"
    action1 = InvoiceLifecycleAction(
        id="act_atomic_1", tenant_id=tenant_id, direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_atomic", source_provider_uuid="p_uuid", action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
        state=InvoiceLifecycleActionState.REQUESTED, request_uuid="req_1", idempotency_key="key_1", request_fingerprint="f_1",
        answer_guard_key="inv_atomic", requested_by="u1", requested_at=datetime.now(UTC)
    )

    action2 = InvoiceLifecycleAction(
        id="act_atomic_2", tenant_id=tenant_id, direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_atomic", source_provider_uuid="p_uuid", action_type=InvoiceLifecycleActionType.REJECT_INCOMING,
        state=InvoiceLifecycleActionState.REQUESTED, request_uuid="req_2", idempotency_key="key_2", request_fingerprint="f_2",
        answer_guard_key="inv_atomic", requested_by="u1", requested_at=datetime.now(UTC)
    )

    # First creation should succeed
    created1 = await InvoiceLifecycleRepository.create_action(action1)
    assert created1 == ActionCreationResult.SUCCESS

    # Second creation with the same answer_guard_key should fail with GUARD_CONFLICT
    created2 = await InvoiceLifecycleRepository.create_action(action2)
    assert created2 == ActionCreationResult.GUARD_CONFLICT

    # If we clear the guard key (simulate FAILED), we should be able to create again
    await InvoiceLifecycleRepository.update_action_result(
        tenant_id, "act_atomic_1", action1.lifecycle_lease_owner,
        {"state": InvoiceLifecycleActionState.FAILED.value},
        unset_fields={"answer_guard_key": ""}
    )

    # Now action2 should succeed
    created2_retry = await InvoiceLifecycleRepository.create_action(action2)
    assert created2_retry == ActionCreationResult.SUCCESS

async def test_duplicate_guard_detected_from_key_pattern():
    from unittest.mock import patch

    from pymongo.errors import DuplicateKeyError

    from models.schemas.invoice_lifecycle import ActionCreationResult

    action = InvoiceLifecycleAction(
        id="a1", tenant_id="t1", direction="INCOMING", source_invoice_id="i1",
        source_provider_uuid="p1", action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, state="REQUESTED",
        request_uuid="r1", idempotency_key="id1", request_fingerprint="f1",
        requested_by="user1", requested_at=datetime.now(UTC)
    )

    with patch("core.integrations.invoice_lifecycle_repository.get_db_for_tenant") as mock_get_db:
        mock_db = mock_get_db.return_value
        err = DuplicateKeyError("E11000 duplicate key error", 11000, {"keyPattern": {"answer_guard_key": 1}})
        mock_db.invoice_lifecycle_actions.insert_one.side_effect = err

        result = await InvoiceLifecycleRepository.create_action(action)
        assert result == ActionCreationResult.GUARD_CONFLICT

async def test_duplicate_idempotency_detected_from_key_pattern():
    from unittest.mock import patch

    from pymongo.errors import DuplicateKeyError

    from models.schemas.invoice_lifecycle import ActionCreationResult

    action = InvoiceLifecycleAction(
        id="a1", tenant_id="t1", direction="INCOMING", source_invoice_id="i1",
        source_provider_uuid="p1", action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, state="REQUESTED",
        request_uuid="r1", idempotency_key="id1", request_fingerprint="f1",
        requested_by="user1", requested_at=datetime.now(UTC)
    )

    with patch("core.integrations.invoice_lifecycle_repository.get_db_for_tenant") as mock_get_db:
        mock_db = mock_get_db.return_value
        err = DuplicateKeyError("E11000 duplicate key error", 11000, {"keyPattern": {"idempotency_key": 1}})
        mock_db.invoice_lifecycle_actions.insert_one.side_effect = err

        result = await InvoiceLifecycleRepository.create_action(action)
        assert result == ActionCreationResult.IDEMPOTENCY_CONFLICT
