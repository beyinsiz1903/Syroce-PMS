"""No provider I/O: preserve complete selections in authorized coarse batches."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from lxml import etree

from domains.channel_manager import unified_rate_manager_router as rates
from domains.channel_manager.providers.exely import ari_delivery
from domains.channel_manager.providers.exely.ari_delivery import deliver_exely_ari
from domains.channel_manager.providers.exely.batch_policy import category_change_counts, plan_rate_envelopes, price_upload_allowed, single_envelope_error
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import QuotaDecision
from domains.channel_manager.providers.exely.rate_delta import changed_rate_messages
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
    db.pricing_settings = collection([{"room_type_code": room, "pricing_type": "per_room", "base_occupancy": 2}
                                      for room in ("STD", "DLX")])
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
    wait = AsyncMock()
    monkeypatch.setattr(rates, "_wait_exely_batch_slot", wait)
    return SimpleNamespace(conn=conn, save=cal.bulk_write, send=send, wait=wait, mappings=mappings, db=db, collection=collection)


async def publish(plans=("BASE", "NRF", "DYNAMIC"), **overrides):
    req = rates.UnifiedBulkUpdateRequest(**{
        "per_room_values": [rates.RoomTypeValuesItem(room_type_code=f"panel-{room}",
            rate_plan_codes=[f"panel-{p}" for p in plans], rate=amount, rate_number_of_guests=2)
            for room, amount in (("STD", 100), ("DLX", 110))],
        "start_date": "2026-11-05", "end_date": "2028-11-01", "update_fields": ["rate"], **overrides,
    })
    return await rates.unified_bulk_grid_update(req, SimpleNamespace(tenant_id=TENANT, id="synthetic-operator"), None)


async def test_screenshot_six_plan_selection_keeps_whole_period_and_rooms_in_three_plan_groups(editor):
    result = await publish()
    assert result["saved"] == 4368
    assert result["provider_verified"]
    editor.save.assert_awaited_once()
    assert editor.send.await_count == 3
    assert editor.wait.await_count == 2
    identities = set()
    for call, code in zip(editor.send.await_args_list, ("wire-BASE", "wire-NRF", "wire-DYNAMIC"), strict=True):
        tenant, op, payload = call.args
        assert tenant == TENANT and op == "rate_batch"
        identities.add(payload["operation_identity"])
        assert len(payload["value"]) == 2
        assert {row["room_type_code"] for row in payload["value"]} == {"wire-STD", "wire-DLX"}
        assert {row["rate_plan_code"] for row in payload["value"]} == {code}
        assert {row["start_date"] for row in payload["value"]} == {"2026-11-05"}
        assert {row["end_date"] for row in payload["value"]} == {"2028-11-01"}
        assert max(category_change_counts(payload["value"]).values()) == 728
    assert len(identities) == 3
    assert result["provider_delivery"][0]["confirmed_batch_count"] == 3


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


@pytest.mark.parametrize("plans,expected_costs", [(('BASE', 'NRF'), [1456]), (('BASE', 'NRF', 'DYNAMIC'), [728, 728, 728])])
async def test_editor_to_real_quota_checked_provider_builds_complete_price_xmls(editor, monkeypatch, plans, expected_costs):
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    quota = SimpleNamespace(reserve=AsyncMock(return_value=QuotaDecision(True, "QUOTA_RESERVED")))
    provider = ExelyProvider(username="synthetic", password="synthetic", hotel_code="synthetic-property",
                             connection_id="offline-single-price-preflight", quota_guard=quota)
    provider._transport.send_soap = AsyncMock(return_value=(
        b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        b'<OTA_HotelRateAmountNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>'
        b'</OTA_HotelRateAmountNotifRS></s:Body></s:Envelope>'))
    async def deliver(_tenant, operation, payload, *, changed_prices_only=False):
        assert changed_prices_only
        result = await provider.push_ari_operation(operation=operation, room_type_code="", rate_plan_code="",
            start_date="", end_date="", value=payload["value"])
        return ari_delivery.ExelyARIDeliveryResult(result.success, "confirmed", "", "SUCCESS", 1, "synthetic")
    editor.send.side_effect = deliver
    await publish(plans)
    assert [call.kwargs for call in quota.reserve.await_args_list] == [
        {"operation": "ari_mutation", "change_count": cost} for cost in expected_costs]
    assert provider._transport.send_soap.await_count == len(expected_costs)
    rows = []
    for call in provider._transport.send_soap.await_args_list:
        root = etree.fromstring(call.args[0].encode())
        assert len(root.findall('.//ota:RateAmountMessages', NS)) == 1
        rows.extend(root.findall('.//ota:RateAmountMessage', NS))
    assert len(rows) == 2 * len(plans)
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


async def test_editor_sends_only_changed_single_adult_rate_and_retains_full_calendar(editor, monkeypatch):
    monkeypatch.setattr(ari_delivery, "ari_write_block_reason", lambda: "")
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    monkeypatch.setattr(ari_delivery, "claim_idempotency", AsyncMock(return_value={"status": "acquired", "lock_id": "lock"}))
    monkeypatch.setattr(ari_delivery, "release_idempotency", AsyncMock())
    receipts = []

    async def prepare(identity, owner, operation, payload):
        assert operation == "rate_batch"
        receipts.insert(0, {"state": "prepared", "rate_periods": ari_delivery.rate_periods(operation, payload)})
        return True, None

    async def finish(identity, owner, state, *args, **kwargs):
        receipts[0]["state"] = state
        return True

    async def lookup(payload):
        return changed_rate_messages(payload["value"], [row for row in receipts if row["state"] in {"confirmed", "ambiguous"}])

    monkeypatch.setattr(ari_delivery, "_prepare_delivery", prepare)
    monkeypatch.setattr(ari_delivery, "_mark_sending", AsyncMock(return_value=True))
    monkeypatch.setattr(ari_delivery, "_finish", finish)
    monkeypatch.setattr(ari_delivery, "_changed_rate_messages", lookup)
    quota = SimpleNamespace(reserve=AsyncMock(return_value=QuotaDecision(True, "QUOTA_RESERVED")))
    provider = ExelyProvider(username="synthetic", password="synthetic", hotel_code="synthetic-property",
                             connection_id="offline-price-delta", quota_guard=quota)
    success = (b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
               b'<OTA_HotelRateAmountNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>'
               b'</OTA_HotelRateAmountNotifRS></s:Body></s:Envelope>')
    provider._transport.send_soap = AsyncMock(return_value=success)

    async def deliver(tenant, operation, payload, **kwargs):
        return await deliver_exely_ari(tenant, operation, payload, provider=provider, write_enabled=True, **kwargs)

    editor.send.side_effect = deliver

    async def edit(amount, start="2026-11-15", end="2026-11-18"):
        editor.db.pricing_settings = editor.collection([{
            "room_type_code": "STD", "pricing_type": "per_person", "base_occupancy": 2, "currency": "USD",
            "exely_placements_reviewed": True,
            "exely_price_placements": [{"kind": "adult_main", "number_of_guests": 1, "price_mode": "fixed", "value": amount}],
        }])
        return await publish(per_room_values=[{
            "room_type_code": "panel-STD", "rate_plan_codes": ["panel-BASE"], "rate": 100, "rate_number_of_guests": 2,
            "rate_guest_prices": [{"kind": "adult_main", "number_of_guests": 1, "amount": amount},
                                  {"kind": "adult_main", "number_of_guests": 2, "amount": 100}],
        }], start_date=start, end_date=end)

    def wire_prices():
        xml = etree.fromstring(provider._transport.send_soap.await_args.args[0].encode())
        return [(row.get("NumberOfGuests"), row.get("AmountAfterTax"), row.get("CurrencyCode"))
                for row in xml.findall(".//ota:BaseByGuestAmt", NS)]

    assert (await edit(80, "2026-11-06", "2026-11-20"))["provider_verified"]
    assert wire_prices() == [("1", "80.00", "USD"), ("2", "100.00", "USD")]
    changed = await edit(85)
    assert changed["provider_verified"] and changed["saved"] == 4
    assert wire_prices() == [("1", "85.00", "USD")]
    assert quota.reserve.await_args.kwargs["change_count"] == 4
    assert [row["amount"] for row in editor.save.await_args.args[0][0]._doc["$set"]["rate_guest_prices"]] == [85, 100]
    assert [row["amount"] for row in changed["price_guest_prices"]["panel-STD"]] == [85, 100]
    unchanged = await edit(85)
    assert unchanged["provider_delivery_state"] == "UNCHANGED"
    assert unchanged["provider_write_count"] == 0
    assert provider._transport.send_soap.await_count == 2

    provider._transport.send_soap.side_effect = TimeoutError
    unknown = await edit(90)
    assert unknown["provider_delivery_state"] == "UNKNOWN"
    assert (await edit(90))["provider_delivery_state"] == "UNKNOWN"
    assert provider._transport.send_soap.await_count == 3


def test_price_history_splits_at_known_date_boundaries_and_respects_currency_and_guest_type():
    adult = {"kind": "adult_main", "number_of_guests": 2, "amount": 100}
    child = {"kind": "child_without_bed", "min_age": 0, "max_age": 7, "amount": 0}
    current = {**message(start="2026-11-15", end="2026-11-18"), "guest_prices": [adult, child]}
    known = [{"state": "confirmed", "rate_periods": [{**current, "start_date": "2026-11-16", "end_date": "2026-11-17",
               "guest_prices": [adult, {**child, "amount": 15}]}]}]
    rows = changed_rate_messages([current], known)
    assert [(row["start_date"], row["end_date"], row["guest_prices"]) for row in rows] == [
        ("2026-11-15", "2026-11-15", [adult, child]), ("2026-11-16", "2026-11-17", [child]),
        ("2026-11-18", "2026-11-18", [adult, child]),
    ]
    assert changed_rate_messages([{**current, "currency": "EUR"}], known)[0]["guest_prices"] == [adult, child]


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
    assert result["occupancy_pricing_rules"]["panel-STD"]["base_occupancy"] == 2
    assert result["occupancy_pricing_rules"]["panel-STD"]["base_occupancy_explicit"] is True


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


def test_long_multi_placement_ranges_are_coarse_lossless_and_do_not_change_input():
    rows = [{**message(room, plan, end="2028-11-04"), "number_of_guests": 2,
             "guest_prices": [{"kind": "adult_main", "number_of_guests": 1, "amount": 80},
                              {"kind": "adult_main", "number_of_guests": 2, "amount": 100}]}
            for room in ("STD", "DLX") for plan in ("BASE", "NRF", "DYNAMIC")]
    original = deepcopy(rows)
    batches = plan_rate_envelopes(rows)
    assert rows == original
    assert len(batches) == 6  # 3 plans, 730+1 nights, both rooms together
    assert all(single_envelope_error("rate_batch", batch) is None for batch in batches)
    assert all(len(batch) == 2 for batch in batches)
    assert all(len({row["rate_plan_code"] for row in batch}) == 1 for batch in batches)
    assert [part for batch in batches for part in plan_rate_envelopes(batch)] == batches
    for source in rows:
        parts = sorted((row for batch in batches for row in batch
                        if (row["room_type_code"], row["rate_plan_code"]) == (source["room_type_code"], source["rate_plan_code"])),
                       key=lambda row: row["start_date"])
        assert [row["guest_prices"] for row in parts] == [source["guest_prices"]] * 2
        assert [(row["start_date"], row["end_date"]) for row in parts] == [
            ("2026-11-05", "2028-11-03"), ("2028-11-04", "2028-11-04")]
        assert sum(category_change_counts([row])[source["room_type_code"].casefold()] for row in parts) == 1462


async def test_late_invalid_group_blocks_all_calendar_and_provider_writes(editor, monkeypatch):
    prepare = rates._prepare_exely_push
    async def invalid_last(*args, **kwargs):
        plan = await prepare(*args, **kwargs)
        rates_list = next(messages for operation, messages in plan["batches"] if operation == "rate_batch")
        rates_list[-1]["guest_prices"] = []
        return plan
    monkeypatch.setattr(rates, "_prepare_exely_push", invalid_last)
    with pytest.raises(HTTPException) as error:
        await publish()
    assert error.value.detail["error_code"] == "EXELY_ARI_PLACEMENTS_INVALID"
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


@pytest.mark.parametrize("first_success,state,error_code,status,expected,expected_calls", [
    (False, "ambiguous", "EXELY_TIMEOUT", "WRITE_OUTCOME_UNKNOWN", "UNKNOWN", 1),
    (True, "ambiguous", "EXELY_TIMEOUT", "WRITE_OUTCOME_UNKNOWN", "PARTIAL", 2),
    (False, "blocked", "EXELY_ARI_RATE_LIMITED", "RATE_LIMITED", "NOT_SENT", 1),
    (True, "rejected", "EXELY_ARI_RATE_LIMITED", "DEFINITIVE_REJECTION", "PARTIAL", 2),
])
async def test_unknown_or_failed_batch_is_never_retried_or_reported_as_full_success(editor, first_success, state, error_code, status, expected, expected_calls):
    failure = ari_delivery.ExelyARIDeliveryResult(False, state, error_code, status, int(state != "blocked"), "synthetic")
    editor.send.side_effect = ([editor.send.return_value] if first_success else []) + [failure]
    result = await publish()
    assert not result["provider_verified"]
    assert result["provider_delivery_state"] == expected
    assert editor.send.await_count == expected_calls
    assert editor.wait.await_count == expected_calls - 1
    delivery = result["provider_delivery"][0]
    assert delivery["error_codes"] == [error_code]
    assert delivery["confirmed_batch_count"] == int(first_success)


async def test_exception_after_first_batch_preserves_partial_confirmation_without_resend(editor):
    editor.send.side_effect = [editor.send.return_value, RuntimeError("synthetic loss")]
    result = await publish()
    assert result["provider_delivery_state"] == "PARTIAL"
    assert not result["provider_verified"]
    assert editor.send.await_count == 2
    assert result["provider_delivery"][0]["outcome_unknown"]


async def test_batch_slot_waits_longer_than_one_second(monkeypatch):
    wait = AsyncMock()
    monkeypatch.setattr(rates.asyncio, "sleep", wait)
    await rates._wait_exely_batch_slot()
    wait.assert_awaited_once_with(1.05)
