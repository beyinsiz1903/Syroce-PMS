"""Only the explicitly selected LOCAL replica; never production writes."""
# ruff: noqa: F811
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import tenant_currency
from domains.pms import operations_router as ops
from tests.test_pos_final_consistency_replica import db  # noqa: F401
from tests.test_revenue_control_settings import DAY, HURDLE, USER, WALK, patch


@pytest.mark.asyncio
async def test_sections_reload_conflict_and_tenant_isolation(db, monkeypatch):
    monkeypatch.setattr(ops, "db", db)
    await db.rooms.insert_many([{"id": "r1", "tenant_id": USER.tenant_id, "room_type": "Junior Suite"},
                               {"id": "r2", "tenant_id": "other", "room_type": "Foreign"}])
    original = await ops.get_revenue_settings(current_user=USER)
    await ops.save_revenue_settings(patch(), current_user=USER)
    await ops.save_revenue_settings(patch("day_pricing", DAY), current_user=USER)
    saved = await ops.get_revenue_settings(current_user=USER)
    assert saved["hurdle_rates"] == HURDLE and saved["day_pricing"] == DAY
    assert await db.revenue_settings.count_documents({"tenant_id": USER.tenant_id}) == 1
    assert saved["section_revisions"]["overbooking"] == original["section_revisions"]["overbooking"]
    with pytest.raises(HTTPException) as exc:
        await ops.save_revenue_settings(patch(), current_user=USER)
    assert exc.value.status_code == 409
    foreign = SimpleNamespace(id="other-actor", email="other@example.invalid", tenant_id="other")
    assert (await ops.get_revenue_settings(current_user=foreign))["hurdle_rates"] == {}
    assert (await db.revenue_settings.find_one({"tenant_id": USER.tenant_id}))["updated_by_id"] == USER.id


@pytest.mark.asyncio
async def test_concurrent_same_section_allows_one_writer(db, monkeypatch):
    monkeypatch.setattr(ops, "db", db)
    await db.rooms.insert_one({"tenant_id": USER.tenant_id, "room_type": "Junior Suite"})
    # Existing document path and initial deterministic insert path both tested.
    for existing in (False, True):
        if existing:
            current = await ops.get_revenue_settings(current_user=USER)
            doc = {key: current[key] for key in ("hurdle_rates", "day_pricing", "overbooking")}
        else:
            doc = None
        values = [deepcopy(HURDLE), deepcopy(HURDLE)]
        for i, value in enumerate(values):
            value["Junior Suite"]["bar"] = 200 + i + (10 if existing else 0)
        results = await asyncio.gather(*(ops.save_revenue_settings(patch(value=v, doc=doc), current_user=USER) for v in values), return_exceptions=True)
        assert sum(isinstance(result, dict) for result in results) == 1
        assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    assert await db.revenue_settings.count_documents({}) == 1


@pytest.mark.asyncio
async def test_walk_record_retry_exactly_one_and_no_financial_or_booking_effect(db, monkeypatch):
    monkeypatch.setattr(ops, "db", db)
    await db.rooms.insert_one({"tenant_id": USER.tenant_id, "room_type": "Junior Suite"})
    # Real helper signature and configured currency, not a permissive mock.
    monkeypatch.setattr(tenant_currency, "db", db)
    monkeypatch.setattr(tenant_currency, "_CACHE", {})
    await db.hotel_settings.insert_one({"tenant_id": USER.tenant_id, "currency": "EUR"})
    results = await asyncio.gather(*(ops.process_walk_out(WALK, current_user=USER) for _ in range(2)))
    assert {result["replayed"] for result in results} == {False, True}
    assert len({result["id"] for result in results}) == 1
    assert all(result["record_only"] and not result["financial_posting"] for result in results)
    row = await db.walk_out_records.find_one({"tenant_id": USER.tenant_id})
    assert row["currency"] == "EUR" and row["compensation_amount"] == 12.34 and row["processed_by_id"] == USER.id
    assert await db.walk_out_records.count_documents({}) == 1
    with pytest.raises(HTTPException) as exc:
        await ops.process_walk_out({**WALK, "compensation_amount": 12.35}, current_user=USER)
    assert exc.value.status_code == 409
    for name in ("bookings", "folio_charges", "payments", "financial_transactions", "outbox_events"):
        assert await db[name].count_documents({}) == 0
