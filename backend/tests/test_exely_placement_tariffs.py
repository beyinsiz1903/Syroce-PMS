"""Offline Exely 1.17.1 pp35-43: explicit placement -> one XML -> receipt."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from lxml import etree

from domains.channel_manager import unified_rate_manager_router as rates
from domains.channel_manager.providers.exely.ari_delivery import _payload_fingerprint, preview_exely_ari
from domains.channel_manager.providers.exely.batch_policy import category_change_counts
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import QuotaDecision
from domains.channel_manager.providers.exely.rate_placements import compile_guest_prices, normalize_placements, validate_guest_prices
from domains.channel_manager.providers.exely.response_parser import parse_hotel_avail_rs
from domains.channel_manager.providers.exely.soap_builder import build_rate_amount_batch_rq
from tests import test_exely_single_request_price_preflight as editor_cases

TENANT = editor_cases.TENANT
editor = editor_cases.editor

pytestmark = pytest.mark.exely_failure_stress
NS = {"o": "http://www.opentravel.org/OTA/2003/05"}


def policy():
    return {"room_type_code": "STD", "pricing_type": "per_person", "base_occupancy": 2, "currency": "USD",
        "exely_placements_reviewed": True, "exely_price_placements": [
            {"kind": "adult_main", "number_of_guests": 1, "price_mode": "percentage", "value": 90},
            {"kind": "adult_main", "number_of_guests": 3, "price_mode": "percentage", "value": 125},
            {"kind": "child_main", "min_age": 3, "max_age": 6, "price_mode": "fixed", "value": 20},
            {"kind": "adult_extra", "price_mode": "fixed", "value": 30},
            {"kind": "child_extra", "min_age": 3, "max_age": 6, "price_mode": "percentage", "value": 10},
            {"kind": "child_without_bed", "min_age": 0, "max_age": 2, "price_mode": "fixed", "value": 0},
        ]}


def message(prices):
    return {"room_type_code": "wire-STD", "rate_plan_code": "wire-BASE", "start_date": "2030-01-01",
        "end_date": "2030-01-02", "rate_amount": 100, "currency": "USD", "number_of_guests": 2, "guest_prices": prices}


def test_all_placement_types_have_exact_protocol_fields_and_one_envelope():
    prices = compile_guest_prices(policy(), 100, "USD")
    root = etree.fromstring(build_rate_amount_batch_rq("synthetic", "synthetic", "P", [message(prices),
        {**message(prices), "room_type_code": "wire-DLX", "rate_plan_code": "wire-NRF"}]).encode())
    assert len(root.findall('.//o:RateAmountMessages', NS)) == 1
    assert len(root.findall('.//o:RateAmountMessage', NS)) == 2
    node = root.find('.//o:Rate', NS)
    adults = node.findall('o:BaseByGuestAmts/o:BaseByGuestAmt', NS)[:3]
    assert [(p.get("NumberOfGuests"), p.get("AmountAfterTax")) for p in adults] == [("1", "90.00"), ("2", "100.00"), ("3", "125.00")]
    child = node.findall('o:BaseByGuestAmts/o:BaseByGuestAmt', NS)[3]
    assert dict(child.attrib) == {"AmountAfterTax": "20.00", "CurrencyCode": "USD", "MinAge": "3", "MaxAge": "7"}
    extras = node.findall('o:AdditionalGuestAmounts/o:AdditionalGuestAmount', NS)
    assert [dict(p.attrib) for p in extras] == [
        {"AmountAfterTax": "30.00", "CurrencyCode": "USD", "BedRequired": "true"},
        {"AmountAfterTax": "10.00", "CurrencyCode": "USD", "BedRequired": "true", "MinAge": "3", "MaxAge": "7"},
        {"AmountAfterTax": "0.00", "CurrencyCode": "USD", "BedRequired": "false", "MinAge": "0", "MaxAge": "3"},
    ]
    assert not root.findall('.//*[@AgeQualifyingCode="10"]')
    assert category_change_counts([message(prices)]) == {"wire-std": 14}


def test_room_mode_does_not_multiply_price_or_send_dormant_child_tariffs():
    assert compile_guest_prices({**policy(), "pricing_type": "per_room"}, 100, "USD") == [
        {"kind": "adult_main", "number_of_guests": 2, "amount": 100}]


@pytest.mark.parametrize("mutation", [
    {"exely_placements_reviewed": False}, {"currency": "TRY"},
    {"exely_price_placements": [{"kind": "adult_main", "number_of_guests": 2, "price_mode": "fixed", "value": 100}]},
    {"exely_price_placements": [{"kind": "adult_main", "number_of_guests": True, "price_mode": "fixed", "value": 100}]},
    {"exely_price_placements": [{"kind": "adult_main", "number_of_guests": 1, "price_mode": "fixed", "value": 0}]},
    {"exely_price_placements": [{"kind": "child_extra", "min_age": 3, "max_age": 18, "price_mode": "fixed", "value": 10}]},
    {"exely_price_placements": [{"kind": "adult_extra", "price_mode": "fixed", "value": float('nan')}]},
    {"exely_price_placements": [{"kind": "adult_extra", "price_mode": "fixed", "value": True}]},
])
def test_invalid_policy_never_produces_xml(mutation):
    with pytest.raises(ValueError):
        compile_guest_prices({**policy(), **mutation}, 100, "USD")


def test_adjacent_age_bands_not_overlapping_and_zero_not_missing():
    rows = [{"kind": "child_main", "min_age": 0, "max_age": 2, "price_mode": "fixed", "value": 0},
        {"kind": "child_main", "min_age": 3, "max_age": 6, "price_mode": "fixed", "value": 10}]
    assert len(normalize_placements(rows, 2)) == 2
    with pytest.raises(ValueError):
        normalize_placements([rows[0], {**rows[1], "min_age": 2}], 2)


def test_delivery_hash_covers_every_child_bed_and_occupancy_amount():
    payload = {"tenant_id": "T", "property_id": "P", "value": [message(compile_guest_prices(policy(), 100, "USD"))]}
    changed = deepcopy(payload)
    changed["value"][0]["guest_prices"][-1]["amount"] = 1
    assert _payload_fingerprint("rate_batch", payload) != _payload_fingerprint("rate_batch", changed)
    assert preview_exely_ari("rate_batch", payload).error_code == ""
    changed["value"][0]["guest_prices"][-1]["number_of_guests"] = 1  # Contradictory child+adult row.
    assert preview_exely_ari("rate_batch", changed).error_code == "EXELY_ARI_PLACEMENTS_INVALID"
    with pytest.raises(ValueError):
        validate_guest_prices(changed["value"][0]["guest_prices"])


async def submit(editor, requested):
    editor.db.pricing_settings = editor.collection([policy()])
    request = rates.UnifiedBulkUpdateRequest(per_room_values=[{"room_type_code": "panel-STD",
        "rate_plan_codes": ["panel-BASE", "panel-NRF"], "rate": 100, "rate_number_of_guests": 2, "rate_guest_prices": requested}],
        start_date="2030-01-01", end_date="2030-01-02", update_fields=["rate"])
    return await rates.unified_bulk_grid_update(request, SimpleNamespace(tenant_id=TENANT, id="synthetic"), None)


async def test_editor_preserves_all_placements_calendar_receipt_and_single_delivery(editor):
    prices = compile_guest_prices(policy(), 100, "USD")
    result = await submit(editor, prices)
    assert result["provider_verified"]
    assert result["price_guest_prices"] == {"panel-STD": prices}
    editor.send.assert_awaited_once()
    assert len(editor.send.await_args.args[2]["value"]) == 2
    assert all(row["guest_prices"] == prices for row in editor.send.await_args.args[2]["value"])
    assert all(op._doc["$set"]["rate_guest_prices"] == prices for op in editor.save.await_args.args[0])


@pytest.mark.parametrize("requested", [None, [], [{"kind": "adult_main", "number_of_guests": 2, "amount": 100}]])
async def test_stale_or_incomplete_review_cannot_mutate_any_calendar_or_provider(editor, requested):
    with pytest.raises(HTTPException) as error:
        await submit(editor, requested)
    assert error.value.detail["error_code"] == "EXELY_RATE_PLACEMENTS_REVIEW_REQUIRED"
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


async def test_known_provider_capacity_beats_operator_confirmation(editor):
    editor.conn["room_types"] = [{"code": "wire-STD", "main_occupancy_min": 1, "main_occupancy_max": 2}]
    with pytest.raises(HTTPException) as error:
        await submit(editor, compile_guest_prices(policy(), 100, "USD"))
    assert error.value.detail["error_code"] == "EXELY_RATE_PLACEMENT_INVENTORY_MISMATCH"
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


async def test_known_provider_child_boundaries_are_not_guessed_or_trimmed(editor):
    editor.conn["room_types"] = [{"code": "wire-STD", "child_age_ranges": [{"min_age": 0, "max_age": 3}, {"min_age": 3, "max_age": 8}]}]
    with pytest.raises(HTTPException) as error:
        await submit(editor, compile_guest_prices(policy(), 100, "USD"))
    assert error.value.detail["error_code"] == "EXELY_RATE_PLACEMENT_INVENTORY_MISMATCH"
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


def test_discovery_preserves_main_bed_and_child_inventory():
    xml = b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><OTA_HotelAvailRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/><RoomStays><RoomStay><RoomTypes><RoomType RoomTypeCode="R"><Occupancy MinOccupancy="1" MaxOccupancy="3"/><Occupancy MinAge="0" MaxAge="3" AgeBucket="0"/><Occupancy MinAge="3" MaxAge="7" AgeBucket="1"/></RoomType></RoomTypes></RoomStay></RoomStays></OTA_HotelAvailRS></s:Body></s:Envelope>'
    result = parse_hotel_avail_rs(xml)
    assert result["success"]
    assert result["room_types"][0]["main_occupancy_max"] == 3
    assert result["room_types"][0]["child_age_ranges"] == [{"min_age": 0, "max_age": 3}, {"min_age": 3, "max_age": 7}]


async def test_policy_save_reload_preserves_placement_formulas_and_review(editor, monkeypatch):
    collection = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
    editor.db.__getitem__.side_effect = lambda name: collection if name == "pricing_settings" else MagicMock()
    monkeypatch.setattr(rates, "log_audit_event", AsyncMock())
    await rates.update_pricing_settings(rates.PricingSettingsRequest(settings=[policy()]), SimpleNamespace(tenant_id=TENANT, id="synthetic"), None)
    saved = collection.update_one.await_args.args[1]["$set"]
    _modes, rules = rates._pricing_payload([saved], provider="exely")
    assert compile_guest_prices(rules["STD"], 100, "USD") == compile_guest_prices(policy(), 100, "USD")
    assert rules["STD"]["exely_placements_reviewed"] is True


async def test_real_provider_builds_one_xml_and_reserves_each_placement_cost(monkeypatch):
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    quota = SimpleNamespace(reserve=AsyncMock(return_value=QuotaDecision(True, "QUOTA_RESERVED")))
    provider = ExelyProvider(username="synthetic", password="synthetic", hotel_code="P",
        connection_id="offline-placements-only", quota_guard=quota)
    provider._transport.send_soap = AsyncMock(return_value=b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><OTA_HotelRateAmountNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/></OTA_HotelRateAmountNotifRS></s:Body></s:Envelope>')
    prices = compile_guest_prices(policy(), 100, "USD")
    result = await provider.push_ari_operation(operation="rate_batch", room_type_code="", rate_plan_code="",
        start_date="", end_date="", value=[message(prices), {**message(prices), "rate_plan_code": "NRF"}])
    assert result.success
    quota.reserve.assert_awaited_once_with(operation="ari_mutation", change_count=28)
    provider._transport.send_soap.assert_awaited_once()
    xml = etree.fromstring(provider._transport.send_soap.await_args.args[0].encode())
    assert len(xml.findall('.//o:RateAmountMessages', NS)) == 1
    assert len(xml.findall('.//o:BaseByGuestAmt', NS)) == 8
    assert len(xml.findall('.//o:AdditionalGuestAmount', NS)) == 6
