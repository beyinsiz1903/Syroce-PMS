"""Hotel ↔ agency notifications and PMS-side status sync."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import core.email
from core import agency_notify


def _sysdb(agency=None, ledger=None):
    return SimpleNamespace(
        marketplace_agency_notices=SimpleNamespace(insert_one=AsyncMock()),
        marketplace_agencies=SimpleNamespace(find_one=AsyncMock(return_value=agency)),
        marketplace_bookings=SimpleNamespace(find_one=AsyncMock(return_value=ledger), update_one=AsyncMock()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prefs,emailed", [({}, True), ({"contract_updates": True}, True), ({"contract_updates": False}, False)])
async def test_notice_is_stored_and_email_follows_preference(monkeypatch, prefs, emailed):
    send = AsyncMock(return_value={"sent": True})
    monkeypatch.setattr(core.email, "send_email", send)
    sysdb = _sysdb(agency={"contact_email": "ops@agency.test", "notification_preferences": prefs})

    await agency_notify.notify_agency(
        sysdb, agency_id="a1", kind="contract_decision", title="<b>Onay</b>", message="ok",
        preference=agency_notify.PREF_CONTRACT,
    )

    sysdb.marketplace_agency_notices.insert_one.assert_awaited_once()
    assert send.await_count == (1 if emailed else 0)
    if emailed:
        assert "&lt;b&gt;Onay&lt;/b&gt;" in send.await_args.args[2]


@pytest.mark.asyncio
async def test_notification_failure_never_raises(monkeypatch):
    sysdb = _sysdb()
    sysdb.marketplace_agency_notices.insert_one.side_effect = RuntimeError("db down")
    await agency_notify.notify_agency(sysdb, agency_id="a1", kind="k", title="t", message="m", preference="x")


@pytest.mark.asyncio
async def test_pms_cancellation_updates_ledger_and_notifies_agency(monkeypatch):
    sysdb = _sysdb(ledger={"id": "b1", "confirmation_code": "MKT-1"})
    monkeypatch.setattr("core.tenant_db.get_system_db", lambda: sysdb)
    notify = AsyncMock()
    monkeypatch.setattr(agency_notify, "notify_agency", notify)

    await agency_notify.on_pms_status_change("t1", {"id": "b1", "agency_id": "a1"}, "cancelled", "Overbooking")

    selector, update = sysdb.marketplace_bookings.update_one.await_args.args
    assert selector == {"id": "b1", "agency_id": "a1"}
    assert update["$set"]["status"] == "cancelled"
    kwargs = notify.await_args.kwargs
    assert kwargs["preference"] == agency_notify.PREF_CANCELLATION
    assert "MKT-1" in kwargs["title"] and kwargs["message"] == "Overbooking"


@pytest.mark.asyncio
async def test_legacy_or_direct_booking_is_ignored(monkeypatch):
    sysdb = _sysdb(ledger=None)
    monkeypatch.setattr("core.tenant_db.get_system_db", lambda: sysdb)
    await agency_notify.on_pms_status_change("t1", {"id": "b1", "agency_id": "legacy"}, "cancelled")
    await agency_notify.on_pms_status_change("t1", {"id": "b2"}, "cancelled")
    sysdb.marketplace_bookings.update_one.assert_not_awaited()
