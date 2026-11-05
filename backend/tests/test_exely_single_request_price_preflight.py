"""No provider I/O: price plans must fit one complete, authorized envelope."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from lxml import etree

from domains.channel_manager import unified_rate_manager_router as rates
from domains.channel_manager.providers.exely import ari_delivery
from domains.channel_manager.providers.exely.batch_policy import category_change_counts, price_upload_allowed, single_envelope_error
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import QuotaDecision
from domains.channel_manager.providers.exely.response_parser import parse_hotel_avail_rs

pytestmark = pytest.mark.exely_failure_stress
TENANT = "synthetic-price-preflight"
NS = {"ota": "http://www.opentravel.org/OTA/2003/05"}


def discovery(flags):
    plans = ''.join(f'<RatePlan RatePlanCode="P" {flag}><RatePlanDescription Name="Plan"/></RatePlan>' for flag in flags)
    return ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            '<OTA_HotelAvailRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>'
            f'<RoomStays><RoomStay><RatePlans>{plans}</RatePlans></RoomStay></RoomStays>'
            '</OTA_HotelAvailRS></s:Body></s:Envelope>').encode()


@pytest.mark.parametrize("flag,expected", [('true', True), ('1', True), ('false', False), ('0', False)])
def test_provider_price_upload_capability_is_preserved(flag, expected):
    result = parse_hotel_avail_rs(discovery([f'PriceUploadIsAllowed="{flag}"']))
    assert result["success"]
    assert result["rate_plans"][0]["price_upload_is_allowed"] is expected


@pytest.mark.parametrize("flags", [
    ['', 'PriceUploadIsAllowed="false"'],
    ['PriceUploadIsAllowed="false"', 'PriceUploadIsAllowed="true"'],
    ['PriceUploadIsAllowed="true"', 'PriceUploadIsAllowed="false"'],
])
def test_duplicate_rate_metadata_never_overrides_a_prohibition(flags):
    assert parse_hotel_avail_rs(discovery(flags))["rate_plans"][0]["price_upload_is_allowed"] is False


def test_absent_optional_flag_is_not_invented_from_the_plan_name():
    result = parse_hotel_avail_rs(discovery(['']))
    assert result["rate_plans"] == [{"code": "P", "name": "Plan"}]
    assert price_upload_allowed({"rate_plans": result["rate_plans"]}, "P") is None
    assert not parse_hotel_avail_rs(discovery(['PriceUploadIsAllowed="maybe"']))["success"]


def test_wire_alias_prohibition_wins_over_display_alias_permission():
    conn = {"rate_plans": [{"code": "panel", "price_upload_is_allowed": True},
                            {"code": "wire", "price_upload_is_allowed": False}]}
    assert price_upload_allowed(conn, "panel", "wire") is False


def message(room="STD", plan="BASE", start="2026-11-05", end="2028-11-01"):
    return {"room_type_code": room, "rate_plan_code": plan, "start_date": start, "end_date": end,
            "rate_amount": 100, "currency": "USD"}


def test_category_cost_is_not_discounted_by_xml_compression_or_other_rooms():
    rows = [message(room, plan) for room in ("STD", "DLX") for plan in ("BASE", "NRF", "DYNAMIC")]
    assert category_change_counts(rows) == {"std": 2184, "dlx": 2184}
    assert single_envelope_error("rate_batch", rows)["category_change_count"] == 2184
    assert single_envelope_error("rate_batch", rows[:2]) is None  # 1456, not 4368
    assert single_envelope_error("rate_batch", [message("STD"), message("DLX")]) is None


@pytest.fixture
def editor(monkeypatch):
    mappings = [{"pms_room_type": room, "exely_room_code": f"panel-{room}", "exely_rate_plan_code": f"panel-{plan}",
                 "pms_api_room_code": f"wire-{room}", "pms_api_rate_plan_code": f"wire-{plan}",
                 "sync_price": True, "sync_availability": plan == "BASE", "sync_restrictions": True}
                for room in ("STD", "DLX") for plan in ("BASE", "NRF", "DYNAMIC")]
    def collection(rows):
        def find(query, _projection):
            assert query["tenant_id"] == TENANT
            return SimpleNamespace(to_list=AsyncMock(side_effect=lambda _limit: deepcopy(rows)))
        return SimpleNamespace(find=MagicMock(side_effect=find))
    cal = SimpleNamespace(bulk_write=AsyncMock())
    db = MagicMock()
    db.exely_room_mappings = collection(mappings)
    db.room_mappings = collection([])
    db.pricing_settings = collection([])
    db.hotelrunner_connections = SimpleNamespace(find_one=AsyncMock(return_value=None))
    db.__getitem__.side_effect = lambda key: cal if key == "rate_calendar" else (_ for _ in ()).throw(AssertionError(key))
    conn = {"hotel_code": "synthetic-property", "ari_write_enabled": True, "currency": "USD", "rate_plans": []}
    monkeypatch.setattr(rates, "db", db)
    monkeypatch.setattr(rates, "_detect_active_provider", AsyncMock(return_value={"provider": "exely", "connection": conn}))
    monkeypatch.setattr(rates, "require_tenant_module", AsyncMock())
    monkeypatch.setattr(rates, "_ari_write_block_for_targets", lambda _: "")
    monkeypatch.setattr(rates, "get_tenant_currency", AsyncMock(return_value=("USD", {})))
    send = AsyncMock(return_value=ari_delivery.ExelyARIDeliveryResult(True, "confirmed", "", "SUCCESS", 1, "synthetic"))
    monkeypatch.setattr(ari_delivery, "deliver_exely_ari", send)
    return SimpleNamespace(conn=conn, save=cal.bulk_write, send=send, mappings=mappings, db=db, collection=collection)


async def publish(plans=("BASE", "NRF", "DYNAMIC"), **overrides):
    req = rates.UnifiedBulkUpdateRequest(**{
        "per_room_values": [rates.RoomTypeValuesItem(room_type_code=f"panel-{room}",
            rate_plan_codes=[f"panel-{p}" for p in plans], rate=amount)
            for room, amount in (("STD", 100), ("DLX", 110))],
        "start_date": "2026-11-05", "end_date": "2028-11-01", "update_fields": ["rate"], **overrides,
    })
    return await rates.unified_bulk_grid_update(req, SimpleNamespace(tenant_id=TENANT, id="synthetic-operator"), None)


async def test_screenshot_six_plan_selection_is_rejected_before_any_calendar_or_delivery_write(editor):
    with pytest.raises(HTTPException) as error:
        await publish()
    assert error.value.status_code == 422
    assert error.value.detail["error_code"] == "EXELY_SINGLE_REQUEST_CHANGE_LIMIT"
    assert error.value.detail["category_change_count"] == 2184
    assert error.value.detail["provider_write_count"] == 0
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


async def test_derived_tariff_is_not_silently_dropped_or_relabelled_as_success(editor):
    editor.conn["rate_plans"] = [{"code": "wire-DYNAMIC", "price_upload_is_allowed": False}]
    with pytest.raises(HTTPException) as error:
        await publish()
    assert error.value.detail["error_code"] == "EXELY_RATE_PLAN_PRICE_UPLOAD_DISABLED"
    assert error.value.detail["rate_plan_codes"] == ["panel-DYNAMIC"]
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


async def test_explicitly_selected_writable_plans_keep_both_rooms_and_whole_period_in_one_delivery(editor):
    result = await publish(("BASE", "NRF"))
    assert result["saved"] == 2912
    assert result["provider_verified"]
    editor.save.assert_awaited_once()
    editor.send.assert_awaited_once()
    _tenant, op, payload = editor.send.await_args.args
    assert op == "rate_batch" and len(payload["value"]) == 4
    assert {row["room_type_code"] for row in payload["value"]} == {"wire-STD", "wire-DLX"}
    assert {row["rate_plan_code"] for row in payload["value"]} == {"wire-BASE", "wire-NRF"}
    assert {row["start_date"] for row in payload["value"]} == {"2026-11-05"}
    assert {row["end_date"] for row in payload["value"]} == {"2028-11-01"}


async def test_editor_to_real_quota_checked_provider_builds_one_complete_price_xml(editor, monkeypatch):
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    quota = SimpleNamespace(reserve=AsyncMock(return_value=QuotaDecision(True, "QUOTA_RESERVED")))
    provider = ExelyProvider(username="synthetic", password="synthetic", hotel_code="synthetic-property",
                             connection_id="offline-single-price-preflight", quota_guard=quota)
    provider._transport.send_soap = AsyncMock(return_value=(
        b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        b'<OTA_HotelRateAmountNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>'
        b'</OTA_HotelRateAmountNotifRS></s:Body></s:Envelope>'))
    async def deliver(_tenant, operation, payload):
        result = await provider.push_ari_operation(operation=operation, room_type_code="", rate_plan_code="",
            start_date="", end_date="", value=payload["value"])
        return ari_delivery.ExelyARIDeliveryResult(result.success, "confirmed", "", "SUCCESS", 1, "synthetic")
    editor.send.side_effect = deliver
    await publish(("BASE", "NRF"))
    quota.reserve.assert_awaited_once_with(operation="ari_mutation", change_count=1456)
    provider._transport.send_soap.assert_awaited_once()
    root = etree.fromstring(provider._transport.send_soap.await_args.args[0].encode())
    assert len(root.findall('.//ota:RateAmountMessages', NS)) == 1
    rows = root.findall('.//ota:RateAmountMessage', NS)
    assert len(rows) == 4
    for row in rows:
        interval = row.find('ota:Rates/ota:Rate', NS)
        assert (date.fromisoformat(interval.get('End')) - date.fromisoformat(interval.get('Start'))).days + 1 == 728


async def test_selected_weekdays_remain_one_envelope_without_filling_excluded_dates(editor):
    result = await publish(selected_days=[1], end_date="2027-02-01")
    assert result["provider_verified"]
    editor.send.assert_awaited_once()
    rows = editor.send.await_args.args[2]["value"]
    assert len(rows) < 200
    assert all(date.fromisoformat(row["start_date"]).isoweekday() == 1 for row in rows)


def test_more_than_200_periods_is_not_automatically_split():
    assert single_envelope_error("rate_batch", [message(start="2026-11-05", end="2026-11-05")] * 201)["error_code"] == "EXELY_SINGLE_REQUEST_MESSAGE_LIMIT"


async def test_grid_translates_wire_capability_to_panel_codes_and_room_sync_flags(editor, monkeypatch):
    editor.conn["rate_plans"] = [{"code": "wire-DYNAMIC", "name": "Derived", "price_upload_is_allowed": False}]
    editor.mappings[0]["sync_price"] = False
    editor.db.rate_calendar = editor.collection([])
    monkeypatch.setattr(rates, "_get_room_counts", AsyncMock(return_value=({}, {})))
    monkeypatch.setattr(rates, "_get_active_bookings", AsyncMock(return_value=[]))
    monkeypatch.setattr(rates, "lock_adjusted_capacities", AsyncMock(return_value={}))
    result = await rates._build_exely_grid(TENANT, editor.conn, "2026-11-05", "2026-11-06")
    plans = {row["code"]: row for row in result["rate_plans"]}
    assert plans["panel-DYNAMIC"]["price_upload_is_allowed"] is False
    assert plans["panel-DYNAMIC"]["name"] == "Derived"
    assert plans["panel-BASE"]["price_sync_by_room"] == {"panel-STD": False, "panel-DLX": True}


async def test_three_independent_plans_are_preserved_when_the_selected_period_fits(editor):
    result = await publish(end_date="2027-11-04")
    assert result["provider_verified"]
    assert result["saved"] == 2190
    editor.send.assert_awaited_once()
    assert len(editor.send.await_args.args[2]["value"]) == 6


async def test_invalid_provider_amount_is_rejected_before_local_write(editor):
    editor.conn["currency"] = "invalid"
    with pytest.raises(HTTPException) as error:
        await publish(("BASE",))
    assert error.value.detail["error_code"] == "EXELY_ARI_CURRENCY_INVALID"
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()
