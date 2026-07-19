import os
import uuid

import pytest
from fastapi import HTTPException

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None

import core.database
import core.folio_ledger_service
import routers.folio_ledger
from core.tenant_db import tenant_context
from models.schemas import User
from routers.folio_ledger import (
    ChargeRequest,
    PaymentRequest,
    TransferRequest,
    post_charge,
    post_payment,
    transfer,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TENANT_A = "hotel_a_real"
TENANT_B = "hotel_b_real"
FOLIO_A = "folio_A_test"
BOOKING_A = "booking_A_test"
FOLIO_B = "folio_B_test"
BOOKING_B = "booking_B_test"

USER_A = User(
    id="user_a",
    user_id="user_a",
    email="a@a.com",
    name="User A",
    tenant_id=TENANT_A,
    role="admin",
    is_active=True,
    failed_login_attempts=0,
)
USER_B = User(
    id="user_b",
    user_id="user_b",
    email="b@b.com",
    name="User B",
    tenant_id=TENANT_B,
    role="admin",
    is_active=True,
    failed_login_attempts=0,
)


async def _connect_test_mongo():
    if AsyncIOMotorClient is None:
        raise RuntimeError("motor not installed")
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=1500)
    await client.admin.command("ping")
    return client


@pytest.fixture
async def folio_test_db(monkeypatch):
    client = await _connect_test_mongo()
    db_name = f"test_folio_ownership_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]

    shared_proxy = core.database.db
    old_proxy_target = shared_proxy._db

    old_service_coll = routers.folio_ledger.ledger_service.coll
    old_recon_coll = routers.folio_ledger.recon_engine.ledger.coll

    try:
        await raw_db.folios.insert_many(
            [
                {
                    "id": FOLIO_A,
                    "tenant_id": TENANT_A,
                    "balance": 100.0,
                    "booking_id": BOOKING_A,
                },
                {
                    "id": FOLIO_B,
                    "tenant_id": TENANT_B,
                    "balance": 50.0,
                    "booking_id": BOOKING_B,
                },
            ]
        )

        shared_proxy._db = raw_db
        monkeypatch.setattr(core.folio_ledger_service, "db", shared_proxy)

        routers.folio_ledger.ledger_service.coll = raw_db.folio_ledger
        routers.folio_ledger.recon_engine.ledger.coll = raw_db.folio_ledger

        yield raw_db
    finally:
        shared_proxy._db = old_proxy_target
        routers.folio_ledger.ledger_service.coll = old_service_coll
        routers.folio_ledger.recon_engine.ledger.coll = old_recon_coll

        await client.drop_database(db_name)
        client.close()


async def test_tenant_b_cannot_post_payment_to_tenant_a_folio(folio_test_db):
    req = PaymentRequest(amount=100.0, payment_method="credit_card", currency="TRY")
    with pytest.raises(HTTPException) as exc:
        with tenant_context(USER_B.tenant_id):
            await post_payment(folio_id=FOLIO_A, body=req, current_user=USER_B)
    assert exc.value.status_code == 404

    ledger = await folio_test_db.folio_ledger.find({"folio_id": FOLIO_A}).to_list(10)
    assert len(ledger) == 0


async def test_tenant_b_cannot_post_charge_to_tenant_a_folio(folio_test_db):
    req = ChargeRequest(amount=100.0, description="Test", charge_code="ROOM", currency="TRY", tax_amount=0)
    with pytest.raises(HTTPException) as exc:
        with tenant_context(USER_B.tenant_id):
            await post_charge(folio_id=FOLIO_A, body=req, current_user=USER_B)
    assert exc.value.status_code == 404

    ledger = await folio_test_db.folio_ledger.find({"folio_id": FOLIO_A}).to_list(10)
    assert len(ledger) == 0


async def test_tenant_b_cannot_post_adjustment_to_tenant_a_folio(folio_test_db):
    service = routers.folio_ledger.ledger_service

    with pytest.raises(ValueError) as exc:
        with tenant_context(USER_B.tenant_id):
            await service.post_adjustment(
                tenant_id=USER_B.tenant_id,
                folio_id=FOLIO_A,
                booking_id=BOOKING_A,
                amount=50.0,
                description="Test Adjustment",
            )
    assert "Folio not found" in str(exc.value)

    ledger = await folio_test_db.folio_ledger.find({"folio_id": FOLIO_A}).to_list(10)
    assert len(ledger) == 0


async def test_transfer_source_folio_wrong_tenant(folio_test_db):
    req = TransferRequest(to_folio_id=FOLIO_B, amount=50.0)
    with pytest.raises(HTTPException) as exc:
        with tenant_context(USER_B.tenant_id):
            await transfer(folio_id=FOLIO_A, body=req, current_user=USER_B)
    assert exc.value.status_code == 404


async def test_transfer_target_folio_wrong_tenant(folio_test_db):
    req = TransferRequest(to_folio_id=FOLIO_A, amount=50.0)
    with pytest.raises(HTTPException) as exc:
        with tenant_context(USER_B.tenant_id):
            await transfer(folio_id=FOLIO_B, body=req, current_user=USER_B)
    assert exc.value.status_code == 404


async def test_tenant_a_can_post_payment_to_own_folio(folio_test_db):
    req = PaymentRequest(amount=100.0, payment_method="credit_card", currency="TRY")
    with tenant_context(USER_A.tenant_id):
        result = await post_payment(folio_id=FOLIO_A, body=req, current_user=USER_A)

    assert result["entry_id"] is not None

    ledger = await folio_test_db.folio_ledger.find({"tenant_id": TENANT_A, "folio_id": FOLIO_A}).to_list(10)
    assert len(ledger) == 1
    assert ledger[0]["amount"] == -100.0
