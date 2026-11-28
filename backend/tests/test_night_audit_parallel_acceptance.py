"""Real engine race acceptance on a disposable local transaction-capable DB."""
import asyncio

import pytest

from core import night_audit_hardened as audit
from tests.test_night_audit_hardening import BD, BD_NEXT, PROPERTY, TENANT, _seed_booking
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("parallel_attempts", [10, 25, 50])
async def test_simultaneous_real_closes_post_once_and_advance_once(db, monkeypatch, parallel_attempts):  # noqa: F811
    monkeypatch.setattr(audit, "db", db)
    monkeypatch.setattr(audit, "client", db.client)
    await audit.ensure_night_audit_indexes()
    booking = await _seed_booking(db, room_rate=2500)
    await db.tenant_settings.insert_one({"tenant_id": TENANT, "business_date": BD})
    start = asyncio.Event()

    async def close(i):
        await start.wait()
        return await audit.start_night_audit(TENANT, PROPERTY, BD, "manual", {"id": f"isolated-{i}"})

    attempts = [asyncio.create_task(close(i)) for i in range(parallel_attempts)]
    start.set()
    results = await asyncio.gather(*attempts, return_exceptions=True)
    assert not any(isinstance(result, Exception) for result in results), results
    assert sum(result.get("success") is True for result in results) == 1, results
    assert all(result.get("success") or result.get("code") in {"ALREADY_RUNNING", "ALREADY_COMPLETED"} for result in results), results
    assert await db.night_audit_runs.count_documents({"tenant_id": TENANT, "business_date": BD}) == 1
    assert await db.folio_charges.count_documents({"tenant_id": TENANT, "booking_id": booking["booking_id"]}) == 1
    assert (await db.folios.find_one({"id": booking["folio_id"]}))["balance"] == 2500
    assert (await db.tenant_settings.find_one({"tenant_id": TENANT}))["business_date"] == BD_NEXT
