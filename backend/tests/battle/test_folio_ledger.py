"""
Battle Tests: Folio Ledger
===========================
Tests for the immutable folio ledger: charges, payments, voids, transfers, reconciliation.
"""
import os
import uuid

import httpx
import pytest

from core.database import db
from core.tenant_db import tenant_context

TEST_TENANT = "demo-hotel"

@pytest.fixture
async def seed_folio():
    created_folios = []
    async def _seed(folio_id: str, booking_id: str):
        with tenant_context(TEST_TENANT):
            await db.folios.insert_one({
                "id": folio_id,
                "tenant_id": TEST_TENANT,
                "booking_id": booking_id,
                "status": "open",
                "balance": 0.0,
                "property_id": "demo-property"
            })
        created_folios.append(folio_id)
        return folio_id
    yield _seed
    with tenant_context(TEST_TENANT):
        if created_folios:
            await db.folios.delete_many({"id": {"$in": created_folios}})
            await db.folio_ledger.delete_many({"folio_id": {"$in": created_folios}})

API_URL = os.environ.get("VITE_BACKEND_URL", "http://localhost:8001")

_cached_headers = None


async def _get_auth():
    global _cached_headers
    if _cached_headers:
        return _cached_headers
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{API_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        data = resp.json()
        token = data.get("access_token") or data.get("token", "")
        _cached_headers = {"Authorization": f"Bearer {token}"}
        return _cached_headers


@pytest.fixture
async def auth_headers():
    return await _get_auth()


@pytest.fixture
def test_folio_id():
    return f"test-folio-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_booking_id():
    return f"test-booking-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_post_charge_creates_ledger_entry(auth_headers, test_folio_id, test_booking_id, seed_folio):
    await seed_folio(test_folio_id, test_booking_id)
    """Posting a charge should create an immutable ledger entry."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/api/folio-ledger/{test_folio_id}/charge",
            headers=auth_headers,
            json={
                "amount": 150.00,
                "description": "Room Charge - Night 1",
                "charge_code": "ROOM",
                "booking_id": test_booking_id,
                "idempotency_key": f"test-charge-{uuid.uuid4().hex[:8]}",
            },
        )
        assert resp.status_code == 200, f"Charge failed: {resp.text}"
        data = resp.json()
        assert "entry_id" in data
        assert data["new_balance"] == 150.00


@pytest.mark.asyncio
async def test_post_payment_reduces_balance(auth_headers, test_folio_id, test_booking_id, seed_folio):
    """Posting a payment should reduce the folio balance."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Post charge first
        folio_id = f"pay-test-{uuid.uuid4().hex[:8]}"
        await seed_folio(folio_id, test_booking_id)
        charge_resp = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/charge",
            headers=auth_headers,
            json={
                "amount": 200.00,
                "description": "Room Charge",
                "booking_id": test_booking_id,
            },
        )
        assert charge_resp.status_code == 200

        # Post payment
        pay_resp = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/payment",
            headers=auth_headers,
            json={
                "amount": 100.00,
                "payment_method": "card",
                "booking_id": test_booking_id,
            },
        )
        assert pay_resp.status_code == 200
        data = pay_resp.json()
        assert data["new_balance"] == 100.00  # 200 - 100


@pytest.mark.asyncio
async def test_void_entry_reverses_charge(auth_headers, test_booking_id, seed_folio):
    """Voiding a charge should reverse it and update balance."""
    async with httpx.AsyncClient(timeout=15) as client:
        folio_id = f"void-test-{uuid.uuid4().hex[:8]}"
        await seed_folio(folio_id, test_booking_id)

        # Post charge
        charge_resp = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/charge",
            headers=auth_headers,
            json={
                "amount": 300.00,
                "description": "Minibar Charge",
                "charge_code": "MINIBAR",
                "booking_id": test_booking_id,
            },
        )
        assert charge_resp.status_code == 200
        entry_id = charge_resp.json()["entry_id"]

        # Void the charge
        void_resp = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/void/{entry_id}",
            headers=auth_headers,
            json={"reason": "Guest dispute - item not consumed"},
        )
        assert void_resp.status_code == 200
        data = void_resp.json()
        assert data["new_balance"] == 0.00  # 300 - 300


@pytest.mark.asyncio
async def test_double_void_rejected(auth_headers, test_booking_id, seed_folio):
    """Voiding an already voided entry should be rejected."""
    async with httpx.AsyncClient(timeout=15) as client:
        folio_id = f"dvoid-test-{uuid.uuid4().hex[:8]}"
        await seed_folio(folio_id, test_booking_id)

        charge_resp = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/charge",
            headers=auth_headers,
            json={
                "amount": 50.00,
                "description": "SPA charge",
                "booking_id": test_booking_id,
            },
        )
        assert charge_resp.status_code == 200
        entry_id = charge_resp.json()["entry_id"]

        # First void
        await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/void/{entry_id}",
            headers=auth_headers,
            json={"reason": "Error"},
        )

        # Second void — should fail
        resp2 = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/void/{entry_id}",
            headers=auth_headers,
            json={"reason": "Double void attempt"},
        )
        assert resp2.status_code == 404  # Already voided


@pytest.mark.asyncio
async def test_transfer_between_folios(auth_headers, test_booking_id, seed_folio):
    """Transferring between folios should create paired entries."""
    async with httpx.AsyncClient(timeout=15) as client:
        from_folio = f"xfer-from-{uuid.uuid4().hex[:8]}"
        to_folio = f"xfer-to-{uuid.uuid4().hex[:8]}"
        await seed_folio(from_folio, test_booking_id)
        await seed_folio(to_folio, test_booking_id)

        # Charge source folio
        await client.post(
            f"{API_URL}/api/folio-ledger/{from_folio}/charge",
            headers=auth_headers,
            json={
                "amount": 500.00,
                "description": "Room charges",
                "booking_id": test_booking_id,
            },
        )

        # Transfer
        xfer_resp = await client.post(
            f"{API_URL}/api/folio-ledger/{from_folio}/transfer",
            headers=auth_headers,
            json={
                "to_folio_id": to_folio,
                "amount": 200.00,
                "description": "Company pays portion",
                "booking_id": test_booking_id,
            },
        )
        assert xfer_resp.status_code == 200
        data = xfer_resp.json()
        assert "transfer_out_id" in data
        assert "transfer_in_id" in data

        # Verify balances
        from_ledger = await client.get(
            f"{API_URL}/api/folio-ledger/{from_folio}/ledger",
            headers=auth_headers,
        )
        to_ledger = await client.get(
            f"{API_URL}/api/folio-ledger/{to_folio}/ledger",
            headers=auth_headers,
        )
        assert from_ledger.json()["balance"] == 300.00  # 500 - 200
        assert to_ledger.json()["balance"] == 200.00


@pytest.mark.asyncio
async def test_idempotency_prevents_double_charge(auth_headers, test_booking_id, seed_folio):
    """Same idempotency key should not create duplicate entries."""
    async with httpx.AsyncClient(timeout=15) as client:
        folio_id = f"idem-test-{uuid.uuid4().hex[:8]}"
        idem_key = f"idem-{uuid.uuid4().hex[:8]}"
        await seed_folio(folio_id, test_booking_id)

        resp1 = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/charge",
            headers=auth_headers,
            json={
                "amount": 100.00,
                "description": "Room Charge",
                "booking_id": test_booking_id,
                "idempotency_key": idem_key,
            },
        )
        assert resp1.status_code == 200

        resp2 = await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/charge",
            headers=auth_headers,
            json={
                "amount": 100.00,
                "description": "Room Charge",
                "booking_id": test_booking_id,
                "idempotency_key": idem_key,
            },
        )
        assert resp2.status_code == 200

        # Should still be 100 (not 200)
        ledger_resp = await client.get(
            f"{API_URL}/api/folio-ledger/{folio_id}/ledger",
            headers=auth_headers,
        )
        assert ledger_resp.json()["balance"] == 100.00
        assert ledger_resp.json()["entry_count"] == 1


@pytest.mark.asyncio
async def test_reconciliation_run(auth_headers):
    """Reconciliation should run successfully."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/api/folio-ledger/reconciliation/run",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "report_id" in data
        assert "summary" in data


@pytest.mark.asyncio
async def test_get_ledger_entries(auth_headers, test_booking_id, seed_folio):
    """Should return all entries in sequence order."""
    async with httpx.AsyncClient(timeout=15) as client:
        folio_id = f"ledger-view-{uuid.uuid4().hex[:8]}"
        await seed_folio(folio_id, test_booking_id)

        # Create multiple entries
        await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/charge",
            headers=auth_headers,
            json={"amount": 100, "description": "Night 1", "booking_id": test_booking_id},
        )
        await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/charge",
            headers=auth_headers,
            json={"amount": 100, "description": "Night 2", "booking_id": test_booking_id},
        )
        await client.post(
            f"{API_URL}/api/folio-ledger/{folio_id}/payment",
            headers=auth_headers,
            json={"amount": 50, "payment_method": "cash", "booking_id": test_booking_id},
        )

        # Fetch ledger
        resp = await client.get(
            f"{API_URL}/api/folio-ledger/{folio_id}/ledger",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry_count"] == 3
        assert data["balance"] == 150.00  # 100 + 100 - 50

        # Verify sequence order
        entries = data["entries"]
        for i in range(len(entries) - 1):
            assert entries[i]["sequence_number"] < entries[i + 1]["sequence_number"]
