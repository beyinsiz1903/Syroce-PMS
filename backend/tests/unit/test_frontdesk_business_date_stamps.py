from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from common.context import OperationContext
from domains.pms import frontdesk_service as module


def collection(found=None, rows=()):
    return SimpleNamespace(find_one=AsyncMock(return_value=found),
        find=Mock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=list(rows)))),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1, matched_count=1)), insert_one=AsyncMock())


@pytest.fixture
def service(monkeypatch):
    from core import folio_checkout_reconciliation
    from routers.finance import konaklama_vergisi_core

    monkeypatch.setattr(module, "_enqueue_kbs_after_frontdesk_transition", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "enforce_business_date_transition", AsyncMock(return_value=(date(2026, 10, 3), date(2026, 10, 3))))
    monkeypatch.setattr(folio_checkout_reconciliation, "reconcile_unposted_room_charge", AsyncMock())
    monkeypatch.setattr(konaklama_vergisi_core, "load_tax_config", AsyncMock(return_value={"active": False}))
    instance = module.FrontdeskService.__new__(module.FrontdeskService)
    instance._db = SimpleNamespace(bookings=collection({"id": "b", "tenant_id": "hotel", "status": "confirmed",
        "room_id": "r", "total_amount": 0, "check_in": "2026-10-01", "check_out": "2026-10-03"}),
        rooms=collection({"id": "r", "status": "available", "room_number": "101"}), folios=collection(),
        folio_charges=collection(), payments=collection(), extra_charges=collection(), housekeeping_tasks=collection())
    return instance


@pytest.mark.asyncio
async def test_checkin_keeps_wall_clock_and_distinct_authoritative_business_day(service):
    result = await module.FrontdeskService.checkin.__wrapped__(service, OperationContext("hotel", "actor"), "b", create_folio=False)
    assert result.ok
    change = service._db.bookings.update_one.call_args.args[1]["$set"]
    assert change["checked_in_business_date"] == "2026-10-03"
    assert "T" in change["checked_in_at"]


@pytest.mark.asyncio
async def test_checkout_stamps_business_day_without_replacing_audit_timestamp(service):
    service._db.bookings.find_one.return_value["status"] = "checked_in"
    result = await module.FrontdeskService.checkout.__wrapped__(service, OperationContext("hotel", "actor"), "b")
    assert result.ok
    change = service._db.bookings.update_one.call_args.args[1]["$set"]
    assert change["checked_out_business_date"] == "2026-10-03"
    assert "T" in change["checked_out_at"]


@pytest.mark.asyncio
async def test_zero_balance_does_not_bypass_checkout_business_date_guard(service, monkeypatch):
    service._db.bookings.find_one.return_value["status"] = "checked_in"
    monkeypatch.setattr(module, "enforce_business_date_transition", AsyncMock(side_effect=ValueError("Future departure")))
    result = await module.FrontdeskService.checkout.__wrapped__(service, OperationContext("hotel", "actor"), "b")
    assert not result.ok and result.code == "BUSINESS_DATE_MISMATCH"
    service._db.bookings.update_one.assert_not_awaited()
    service._db.rooms.update_one.assert_not_awaited()
