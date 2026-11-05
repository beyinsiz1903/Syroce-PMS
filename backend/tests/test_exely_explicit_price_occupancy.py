"""Exely v1.17.1 p41: adult main-bed occupancy must be explicit in editor rates."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from lxml import etree
from pydantic import ValidationError

from domains.channel_manager import unified_rate_manager_router as rates
from domains.channel_manager.ari.delta_compiler import compile_delta_exely
from domains.channel_manager.ari.buffer import _coalescing_key
from domains.channel_manager.ari.events import ARIChangeEvent
from domains.channel_manager.providers.exely.ari_delivery import _payload_fingerprint, preview_exely_ari
from domains.channel_manager.providers.exely.soap_builder import build_rate_amount_batch_rq, build_rate_amount_notif_rq
from tests.test_exely_single_request_price_preflight import editor, publish  # noqa: F401

NS = {"o": "http://www.opentravel.org/OTA/2003/05"}
pytestmark = pytest.mark.exely_failure_stress


@pytest.mark.parametrize("count", [1, 2, 3, 20])
def test_single_xml_price_is_total_for_the_exact_adult_occupancy(count):
    xml = build_rate_amount_notif_rq("synthetic", "synthetic", "P", "R", "B", "2030-01-01", "2030-01-02", 100, "USD", count)
    amount = etree.fromstring(xml.encode()).find('.//o:BaseByGuestAmt', NS)
    assert dict(amount.attrib) == {"AmountAfterTax": "100.00", "CurrencyCode": "USD", "NumberOfGuests": str(count)}
    assert amount.get("MinAge") is None and amount.get("AgeQualifyingCode") is None


def test_batch_keeps_room_plan_period_and_guest_counts_in_one_envelope():
    rows = [{"room_type_code": room, "rate_plan_code": plan, "start_date": "2030-01-01", "end_date": "2030-01-02",
             "rate_amount": amount, "currency": "USD", "number_of_guests": guests}
            for room, amount, guests in [("STD", 100, 1), ("DLX", 120, 3)] for plan in ("BASE", "NRF")]
    root = etree.fromstring(build_rate_amount_batch_rq("synthetic", "synthetic", "P", rows).encode())
    assert len(root.findall('.//o:RateAmountMessages', NS)) == 1
    for row, source in zip(root.findall('.//o:RateAmountMessage', NS), rows, strict=True):
        price = row.find('.//o:BaseByGuestAmt', NS)
        assert price.get("NumberOfGuests") == str(source["number_of_guests"])
        assert price.get("AmountAfterTax") == f"{source['rate_amount']:.2f}"


@pytest.mark.parametrize("count", [True, 0, -1, 1.5, "2", 21])
def test_invalid_occupancy_is_rejected_not_coerced(count):
    with pytest.raises(ValidationError):
        rates.RoomTypeValuesItem(room_type_code="STD", rate_plan_codes=["BASE"], rate_number_of_guests=count)
    with pytest.raises(ValueError):
        build_rate_amount_notif_rq("synthetic", "synthetic", "P", "R", "B", "2030-01-01", "2030-01-02", 100, "USD", count)
    update = dict(tenant_id="T", property_id="P", room_type_code="R", rate_plan_code="B", start_date="2030-01-01",
                  end_date="2030-01-02", value=100, currency="USD", number_of_guests=count)
    assert preview_exely_ari("rate", update).error_code == "EXELY_ARI_OCCUPANCY_INVALID"
    row = {key: update[key] for key in ("room_type_code", "rate_plan_code", "start_date", "end_date", "currency", "number_of_guests")}
    assert preview_exely_ari("rate_batch", {**update, "value": [{**row, "rate_amount": 100}]}).error_code == "EXELY_ARI_OCCUPANCY_INVALID"


def test_optional_protocol_default_stays_backward_compatible_but_is_not_called_single_occupancy():
    root = etree.fromstring(build_rate_amount_notif_rq("synthetic", "synthetic", "P", "R", "B", "2030-01-01", "2030-01-02", 100).encode())
    assert root.find('.//o:BaseByGuestAmt', NS).get("NumberOfGuests") is None


def test_delivery_dedup_distinguishes_same_price_for_different_occupancies():
    payload = dict(tenant_id="T", property_id="P", value=100, currency="USD")
    assert len({_payload_fingerprint("rate", {**payload, **extra}) for extra in ({}, {"number_of_guests": 1}, {"number_of_guests": 2})}) == 3


def test_alias_conflict_and_missing_or_stale_review_fail_without_defaulting_to_two():
    mapping = [{"pms_room_type": "STD", "exely_room_code": "panel", "pms_api_room_code": "wire"}]
    assert rates._exely_price_occupancy("panel", mapping, [{"room_type_code": "STD", "base_occupancy": 3}], 3) == 3
    for docs, requested in [([], 2), ([{"room_type_code": "STD"}], 2),
        ([{"room_type_code": "STD", "base_occupancy": 3}], 2),
        ([{"room_type_code": "STD", "base_occupancy": 2}, {"room_type_code": "wire", "base_occupancy": 3}], 2)]:
        with pytest.raises(HTTPException):
            rates._exely_price_occupancy("panel", mapping, docs, requested)


async def test_missing_saved_occupancy_blocks_before_calendar_and_provider_writes(editor):
    editor.db.pricing_settings = editor.collection([])
    with pytest.raises(HTTPException) as error:
        await publish(("BASE", "NRF"))
    assert error.value.detail["error_code"] == "EXELY_RATE_OCCUPANCY_REQUIRED"
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


async def test_confirmed_delivery_carries_reviewed_occupancy_and_preserves_calendar_semantics(editor):
    result = await publish(("BASE", "NRF"))
    assert result["price_occupancies"] == {"panel-STD": 2, "panel-DLX": 2}
    assert all(row["number_of_guests"] == 2 for row in editor.send.await_args.args[2]["value"])
    assert all(op._doc["$set"]["rate_number_of_guests"] == 2 for op in editor.save.await_args.args[0])


async def test_stale_count_cannot_write_local_prices(editor):
    req = rates.UnifiedBulkUpdateRequest(per_room_values=[dict(room_type_code="panel-STD", rate_plan_codes=["panel-BASE"],
        rate=100, rate_number_of_guests=1)], start_date="2030-01-01", end_date="2030-01-02", update_fields=["rate"])
    with pytest.raises(HTTPException) as error:
        await rates.unified_bulk_grid_update(req, SimpleNamespace(tenant_id="synthetic-price-preflight", id="synthetic"), None)
    assert error.value.detail["error_code"] == "EXELY_RATE_OCCUPANCY_REVIEW_REQUIRED"
    editor.save.assert_not_awaited()
    editor.send.assert_not_awaited()


def test_outbox_compiler_preserves_occupancy_and_hash_scope():
    change = dict(tenant_id="T", property_id="P", room_type_code="R", rate_plan_code="B", date_from="2030-01-01",
                  date_to="2030-01-02", change_scope="rate", compacted_payload={"base_rate": 100, "currency": "USD", "number_of_guests": 2})
    delta = compile_delta_exely(change)
    assert delta.payload["number_of_guests"] == 2
    other = deepcopy(change)
    other["compacted_payload"]["number_of_guests"] = 1
    assert compile_delta_exely(other).provider_delta_hash != delta.provider_delta_hash


def test_two_adult_occupancies_do_not_overwrite_one_another_in_the_debounce_buffer():
    def event(count):
        return ARIChangeEvent(tenant_id="T", property_id="P", room_type_code="R", rate_plan_code="B",
            date_from="2030-01-01", date_to="2030-01-02", source_service="synthetic", event_type="rate", target_provider="exely",
            payload={"operation": "rate", "base_rate": 100, "number_of_guests": count})
    assert _coalescing_key(event(1)) != _coalescing_key(event(2))
