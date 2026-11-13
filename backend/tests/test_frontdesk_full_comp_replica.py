"""The quick folio must honor the same full-comp policy as department charges."""
import pytest

from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("scope,complimentary,expected", [
    ("full", True, 0), ("accommodation_only", True, 25), ("full", False, 25),
])
@pytest.mark.parametrize("charge_type", ["food", "laundry", "minibar", "spa", "phone", "other"])
async def test_quick_charge_comp_policy_and_durable_retry(acceptance, scope, complimentary, expected, charge_type):
    a = acceptance
    await a.db.folio_charges.delete_many({})
    await a.db.folios.update_one({"id": "synthetic-folio"}, {"$set": {"balance": 0}})
    await a.db.bookings.update_one({"id": "synthetic-stay"}, {"$set": {
        "total_amount": 0, "is_complimentary": complimentary, "complimentary_scope": scope,
    }})
    url = "/api/frontdesk/folio/synthetic-stay/charge"
    body = {"charge_type": charge_type, "description": "Synthetic included service", "amount": 12.5, "quantity": 2}
    headers = {"Idempotency-Key": "full-comp-breakfast"}
    first = await a.api.post(url, json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["total"] == expected
    assert first.json()["tax_amount"] == 0
    assert first.json()["currency"] == "USD"
    if complimentary and scope == "full":
        assert first.json()["is_complimentary"] is True
        assert first.json()["complimentary_original_amount"] == 25
        assert first.json()["amount"] == first.json()["unit_price"] == 0
    replay = await a.api.post(url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
    assert await a.db.folio_charges.count_documents({}) == 1
    assert (await a.db.folios.find_one({"id": "synthetic-folio"}))["balance"] == expected
    snapshot = await a.api.get("/api/frontdesk/folio/synthetic-stay")
    assert snapshot.json()["balance"] == expected
    assert await a.db.payments.count_documents({}) == 0


async def test_full_comp_does_not_route_included_consumption_to_a_company_account(acceptance, monkeypatch):
    from domains.pms import frontdesk_router

    async def must_not_route(*_args, **_kwargs):
        pytest.fail("Full-comp consumption must stay on its guest account")

    monkeypatch.setattr(frontdesk_router, "_resolve_routing_allocations", must_not_route)
    await acceptance.db.bookings.update_one({"id": "synthetic-stay"}, {"$set": {
        "is_complimentary": True, "complimentary_scope": "full", "routing_rules": [{"category": "food"}],
    }})
    response = await acceptance.api.post("/api/frontdesk/folio/synthetic-stay/charge", json={
        "charge_type": "food", "description": "Synthetic included dinner", "amount": 25,
    })
    assert response.status_code == 200, response.text
    assert response.json()["folio_id"] == "synthetic-folio"
    assert response.json()["total"] == 0
    assert (await acceptance.db.folios.find_one({"id": "synthetic-folio"}))["balance"] == 560
