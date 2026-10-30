"""HTTP read model must agree with the reservation card and signed refunds."""
import pytest

pytest_plugins = ("tests.test_frontdesk_acceptance_replica",)
pytestmark = pytest.mark.asyncio


async def test_quick_folio_includes_extras_refunds_voids_and_legacy_folio_only_rows(acceptance):
    a = acceptance
    await a.db.extra_charges.insert_many([
        {"tenant_id": "qa", "booking_id": "synthetic-stay", "id": "spa", "total": 40, "currency": "USD", "description": "QA spa", "category": "spa"},
        {"tenant_id": "qa", "booking_id": "synthetic-stay", "total": 999, "voided": True},
        {"tenant_id": "other", "booking_id": "synthetic-stay", "total": 9999},
    ])
    await a.db.folio_charges.insert_many([
        {"tenant_id": "qa", "folio_id": "synthetic-folio", "id": "legacy", "total": 10, "currency": "USD"},
        {"tenant_id": "qa", "booking_id": "synthetic-stay", "total": 999, "voided": True},
    ])
    await a.db.payments.insert_many([
        {"tenant_id": "qa", "booking_id": "synthetic-stay", "id": "dep", "amount": 70, "status": "paid", "idempotency_key": "dep"},
        {"tenant_id": "qa", "booking_id": "synthetic-stay", "id": "retry", "amount": 70, "status": "paid", "idempotency_key": "dep"},
        {"tenant_id": "qa", "folio_id": "synthetic-folio", "id": "refund", "amount": -20, "status": "refunded", "payment_type": "refund"},
        {"tenant_id": "qa", "booking_id": "synthetic-stay", "id": "failed", "amount": 999, "status": "failed"},
    ])
    response = await a.api.get("/api/frontdesk/folio/synthetic-stay")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["total_charges"], data["total_paid"], data["balance"], data["currency"]) == (610, 50, 560, "USD")
    assert {c["id"] for c in data["charges"]} == {"synthetic-room-charge", "legacy", "spa"}


async def test_quick_folio_exposes_unposted_stay_price_instead_of_false_credit(acceptance):
    a = acceptance
    await a.db.folio_charges.delete_many({})
    response = await a.api.get("/api/frontdesk/folio/synthetic-stay")
    assert response.status_code == 200
    assert response.json()["total_charges"] == 0
    assert response.json()["unposted_room_amount"] == response.json()["balance"] == 560
