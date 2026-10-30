"""Real, isolated local-Mongo contracts; never connects to a live property."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import mice
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401

USER = SimpleNamespace(tenant_id="A", username="test", id="u", role="admin", roles=["admin"])


@pytest.fixture
def wired(ledger_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mice, "get_system_db", lambda: ledger_db)
    monkeypatch.setattr(mice, "_ensure_indexes", AsyncMock())
    monkeypatch.setattr(mice, "_tenant_currency_code", AsyncMock(return_value="TRY"))
    monkeypatch.setattr(mice, "log_audit_event", AsyncMock())
    monkeypatch.setattr(mice, "release_quota", AsyncMock())
    return ledger_db


def booking(start="10:00", end="12:00"):
    return {"space_id": "hall", "starts_at": f"2026-10-21T{start}", "ends_at": f"2026-10-21T{end}"}


@pytest.mark.asyncio
async def test_cross_tenant_catalog_ids_are_not_accepted(wired):
    await wired.mice_menus.insert_one({"tenant_id": "B", "id": "foreign", "name": "Secret", "price_per_person": 100})
    with pytest.raises(HTTPException) as error:
        await mice._expand_resource_prices("A", [{"menu_id": "foreign", "name": "Unknown", "quantity": 1}], 10, "TRY", "TRY")
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_stock_peak_and_zero_inventory_on_real_database(wired):
    await wired.mice_resources.insert_one({"tenant_id": "A", "id": "projector", "name": "Projector", "total_stock": 2})
    await wired.mice_events.insert_many([
        {"tenant_id": "A", "id": "morning", "status": "confirmed", "space_bookings": [booking("09:00", "10:00")], "resources": [{"inventory_id": "projector", "quantity": 1}]},
        {"tenant_id": "A", "id": "noon", "status": "confirmed", "space_bookings": [booking("12:00", "13:00")], "resources": [{"inventory_id": "projector", "quantity": 1}]},
        {"tenant_id": "B", "id": "other-hotel", "status": "confirmed", "space_bookings": [booking("09:00", "18:00")], "resources": [{"inventory_id": "projector", "quantity": 100}]},
    ])
    assert await mice._check_resource_inventory_conflict("A", [{"inventory_id": "projector", "quantity": 1}], [booking("09:00", "18:00")]) is None
    await wired.mice_resources.update_one({"tenant_id": "A", "id": "projector"}, {"$set": {"total_stock": 0}})
    assert await mice._check_resource_inventory_conflict("A", [{"inventory_id": "projector", "quantity": 1}], [booking()])


@pytest.mark.asyncio
async def test_mark_paid_cas_does_not_mark_a_different_milestone(wired):
    item = {"due_date": "2026-10-21", "label": "Deposit", "amount": 100, "paid": False}
    await wired.mice_events.insert_one({"tenant_id": "A", "id": "event", "status": "definite", "payment_schedule": [item, {**item, "label": "Balance"}]})
    await mice.mark_payment_paid("event", 0, "bank-test-ref", USER)
    result = await wired.mice_events.find_one({"tenant_id": "A", "id": "event"})
    assert result["payment_schedule"][0]["paid"]
    assert result["payment_schedule"][0]["reference"] == "bank-test-ref"
    assert result["payment_schedule"][1]["paid"] is False
    retry = await mice.mark_payment_paid("event", 0, "different-ref", USER)
    assert retry["already_paid"]
    assert retry["item"]["reference"] == "bank-test-ref"


@pytest.mark.asyncio
async def test_competing_terminal_transitions_have_only_one_winner(wired, monkeypatch):
    await wired.mice_events.insert_one({"tenant_id": "A", "id": "event", "status": "confirmed", "name": "Conference", "space_bookings": [], "resources": []})
    gate = asyncio.Event()
    arrived = 0
    real = wired.mice_events

    class Events:
        async def find_one(self, *args, **kwargs):
            nonlocal arrived
            row = await real.find_one(*args, **kwargs)
            if arrived < 2:
                arrived += 1
                if arrived == 2: gate.set()
                await gate.wait()
            return row

        async def update_one(self, *args, **kwargs):
            return await real.update_one(*args, **kwargs)

    monkeypatch.setattr(mice, "get_system_db", lambda: SimpleNamespace(mice_events=Events()))
    results = await asyncio.gather(
        mice.change_status("event", mice.StatusUpdate(status="completed"), USER),
        mice.change_status("event", mice.StatusUpdate(status="cancelled", reason="Customer cancelled the event"), USER),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1


@pytest.mark.asyncio
async def test_ops_sheet_contains_only_the_selected_days_functions(wired):
    await wired.mice_events.insert_one({"tenant_id": "A", "id": "event", "name": "Two days", "status": "confirmed", "start_date": "2026-10-21", "end_date": "2026-10-22", "space_bookings": [booking(), {**booking(), "starts_at": "2026-10-22T10:00", "ends_at": "2026-10-22T12:00"}]})
    report = await mice.ops_sheet("2026-10-21", USER)
    assert report["count"] == 1
    assert report["rows"][0]["starts_at"].startswith("2026-10-21")


@pytest.mark.asyncio
async def test_competitor_positioning_never_compares_eur_to_usd(wired, monkeypatch):
    from routers import banquet_competitor
    monkeypatch.setattr(banquet_competitor, "get_system_db", lambda: wired)
    monkeypatch.setattr(banquet_competitor, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await wired.mice_accounts.insert_one({"tenant_id": "A", "id": "competitor", "account_type": "banquet_competitor", "competitor_rates": [
        {"event_type": "wedding", "per_pax_price": 100, "currency": "EUR"},
        {"event_type": "wedding", "per_pax_price": 900, "currency": "USD"},
    ]})
    await wired.mice_events.insert_one({"tenant_id": "A", "id": "ours", "event_type": "wedding", "status": "confirmed", "expected_pax": 10, "currency": "EUR", "totals": {"grand_total": 1000}})
    rows = {r["currency"]: r for r in (await banquet_competitor.positioning(USER))["rows"]}
    assert rows["EUR"]["position"] == "in_band"
    assert rows["EUR"]["competitor_avg"] == 100
    assert rows["USD"]["position"] == "no_data"
    assert rows["USD"]["competitor_avg"] == 900


@pytest.mark.asyncio
async def test_completion_handoff_failure_restores_operational_status(wired, monkeypatch):
    await wired.mice_events.insert_one({"tenant_id": "A", "id": "event", "status": "confirmed", "space_bookings": [], "resources": []})
    monkeypatch.setattr(mice, "_post_event_to_folio", AsyncMock(side_effect=RuntimeError("simulated posting failure")))
    with pytest.raises(RuntimeError): await mice.change_status("event", mice.StatusUpdate(status="completed"), USER)
    restored = await wired.mice_events.find_one({"tenant_id": "A", "id": "event"})
    assert restored["status"] == "confirmed"
    assert "completed_at" not in restored
    mice.release_quota.assert_not_awaited()


@pytest.mark.asyncio
async def test_parallel_folio_handoffs_create_one_charge(wired, monkeypatch):
    import integrations.xchange.bus as exchange_bus
    monkeypatch.setattr(exchange_bus, "bus", SimpleNamespace(publish=AsyncMock()))
    from core import audit_chain
    monkeypatch.setattr(audit_chain, "_system_db", lambda: wired)
    # A real persisted source and open folio are required, not an arbitrary
    # bus payload. Verify the canonical receivable as well as the integration row.
    for collection in ("mice_events", "folio_locks", "folios", "bookings", "folio_charges", "folio_postings", "audit_logs", "audit_chain_state"):
        if collection not in await wired.list_collection_names():
            await wired.create_collection(collection)
    await wired.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-26"})
    await wired.bookings.insert_one({"tenant_id": "A", "id": "synthetic-booking", "currency": "EUR", "status": "checked_in"})
    await wired.folios.insert_one({"tenant_id": "A", "id": "folio", "booking_id": "synthetic-booking", "currency": "EUR", "status": "open"})
    event = {"tenant_id": "A", "id": "event", "status": "completed", "currency": "EUR", "reservation_id": "synthetic-booking", "totals": {"grand_total": 100}}
    await wired.mice_events.insert_one(dict(event))
    await asyncio.gather(mice._post_event_to_folio("A", event), mice._post_event_to_folio("A", event))
    assert await wired.folio_postings.count_documents({"tenant_id": "A", "reference": "event"}) == 1
    assert await wired.folio_charges.count_documents({"tenant_id": "A", "source_mice_event_id": "event"}) == 1
    assert (await wired.folios.find_one({"tenant_id": "A", "id": "folio"}))["balance"] == 100


@pytest.mark.asyncio
async def test_concurrent_same_venue_is_serialized_or_fails_closed(wired, monkeypatch):
    monkeypatch.setattr(mice, "get_tenant_limit", AsyncMock(return_value=None))
    monkeypatch.setenv("ALLOW_STANDALONE_BOOKING_FALLBACK", "0")
    await wired.mice_spaces.insert_one({"tenant_id": "A", "id": "hall", "name": "Synthetic Hall", "active": True, "currency": "TRY", "capacity_theatre": 100})
    await wired.mice_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    # Pre-create the shared lock so the test exercises WriteConflict retries,
    # not the unrelated first-upsert unique-key race.
    await wired.mice_locks.insert_one({"tenant_id": "A", "kind": "space", "resource_id": "hall"})
    def body(name):
        return mice.EventIn(name=name, client_name="Synthetic Customer", status="tentative", expected_pax=20, start_date="2026-10-21", end_date="2026-10-21", space_bookings=[booking()])
    results = await asyncio.gather(mice.create_event(body("A"), USER), mice.create_event(body("B"), USER), return_exceptions=True)
    replica = (await wired.client.admin.command("hello")).get("setName")
    if replica:
        assert sum(isinstance(r, dict) for r in results) == 1, results
        assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1, results
        assert await wired.mice_events.count_documents({"tenant_id": "A"}) == 1
    else:
        assert all(isinstance(r, HTTPException) and r.status_code == 503 for r in results), results
        assert await wired.mice_events.count_documents({"tenant_id": "A"}) == 0


@pytest.mark.asyncio
async def test_catalog_cannot_invalidate_active_space_or_stock_allocations(wired, monkeypatch):
    async def lock(_db, _tenant, _kind, _id, callback):
        return await callback(None)
    monkeypatch.setattr(mice, "_catalog_lock", lock)
    await wired.mice_events.insert_one({"id": "event", "tenant_id": "A", "status": "confirmed", "currency": "TRY", "space_bookings": [{**booking(), "expected_pax": 50}], "resources": [{"inventory_id": "stock", "quantity": 2}]})
    await wired.mice_spaces.insert_one({"id": "hall", "tenant_id": "A", "capacity_theatre": 100})
    await wired.mice_resources.insert_one({"id": "stock", "tenant_id": "A", "total_stock": 2})
    with pytest.raises(HTTPException) as error:
        await mice.update_space("hall", mice.FunctionSpaceIn(name="Hall", capacity_theatre=40, currency="TRY"), USER)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await mice.update_resource("stock", mice.ResourceInventoryIn(name="Projector", total_stock=1, currency="TRY"), USER)
    assert error.value.status_code == 409
    assert (await wired.mice_resources.find_one({"id": "stock"}))["total_stock"] == 2
    with pytest.raises(HTTPException): await mice.delete_resource("stock", USER)
    assert await wired.mice_resources.count_documents({"id": "stock"}) == 1
