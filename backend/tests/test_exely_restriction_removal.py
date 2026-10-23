"""Explicit LOS removal is Exely-only and never a zero-length Set operation."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from lxml import etree
from pydantic import ValidationError

from domains.channel_manager.providers.exely.ari_delivery import preview_exely_ari
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.soap_builder import build_ari_update_rq, build_restriction_batch_rq
from domains.channel_manager.unified_rate_manager_router import UnifiedBulkUpdateRequest, _validate_los_updates

pytestmark = pytest.mark.exely_failure_stress
NS = {"s": "http://schemas.xmlsoap.org/soap/envelope/", "o": "http://www.opentravel.org/OTA/2003/05"}
BASE = {"room_type_code": "R", "rate_plan_code": "RP", "start_date": "2030-01-01", "end_date": "2030-01-01"}
OPS = [("min_los", "min_stay", "RemoveMinLOS"), ("min_los_arrival", "min_los_arrival", "RemoveMinLOS"), ("max_los", "max_stay", "RemoveMaxLOS")]


@pytest.mark.parametrize("operation,field,expected", OPS)
def test_single_and_batch_removal_use_wsdl_remove_not_set(operation, field, expected):
    xmls = [
        build_ari_update_rq("u", "p", "H", "R", "RP", BASE["start_date"], BASE["end_date"], **{field: 0}),
        build_restriction_batch_rq("u", "p", "H", [{**BASE, "operation": operation, "value": 0}]),
    ]
    # Validate against the checked-in vendor WSDL, not a hand-written schema.
    wsdl = etree.parse(str(Path(__file__).resolve().parents[2] / "wsdl.xml"))
    schema_node = wsdl.find(".//{http://www.w3.org/2001/XMLSchema}schema")
    schema = etree.XMLSchema(schema_node)
    for xml in xmls:
        root = etree.fromstring(xml.encode())
        request = root.find("s:Body/o:OTA_HotelAvailNotifRQ", NS)
        schema.assertValid(request)
        los = request.find(".//o:LengthOfStay", NS)
        assert los.attrib == {"MinMaxMessageType": expected}
        container = request.find(".//o:LengthsOfStay", NS)
        assert container.get("ArrivalDateBased") == ("true" if operation == "min_los_arrival" else None)


@pytest.mark.parametrize("operation,field,expected", OPS)
@pytest.mark.parametrize("value", [0, 2])
def test_preview_allows_explicit_zero_and_positive_lengths(operation, field, expected, value):
    update = {**BASE, "tenant_id": "t", "property_id": "H", "value": value}
    assert not preview_exely_ari(operation, update).error_code
    update["value"] = [{**BASE, "operation": operation, "value": value}]
    assert not preview_exely_ari("restriction_batch", update).error_code


@pytest.mark.parametrize("value", [-1, True, 0.5, "0", None])
def test_invalid_lengths_still_rejected(value):
    update = {**BASE, "tenant_id": "t", "property_id": "H", "value": value}
    assert preview_exely_ari("min_los", update).error_code
    update["value"] = [{**BASE, "operation": "min_los", "value": value}]
    assert preview_exely_ari("restriction_batch", update).error_code


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_clear_reaches_one_transport_write(batch):
    provider = ExelyProvider(username="u", password="p", hotel_code="H", max_retries=0)
    provider._transport.send_soap = AsyncMock(return_value=b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/></OTA_HotelAvailNotifRS></s:Body></s:Envelope>')
    result = await provider.push_ari_operation(
        operation="restriction_batch" if batch else "max_los",
        **BASE,
        value=[{**BASE, "operation": "max_los", "value": 0}] if batch else 0,
    )
    assert result.success
    provider._transport.send_soap.assert_awaited_once()
    assert 'MinMaxMessageType="RemoveMaxLOS"' in provider._transport.send_soap.await_args.args[0]


@pytest.mark.parametrize("provider,agencies_only,agency_ids", [("hotelrunner", False, None), ("agency", True, ["a"]), ("exely", False, ["a"])])
def test_clear_is_blocked_for_other_targets_before_mutations(provider, agencies_only, agency_ids):
    request = UnifiedBulkUpdateRequest(start_date="2030-01-01", end_date="2030-01-01", update_fields=["max_stay"], max_stay=0, agencies_only=agencies_only, agency_ids=agency_ids)
    with pytest.raises(HTTPException) as error:
        _validate_los_updates(request, provider)
    assert error.value.status_code == 422


def test_zero_is_clear_not_a_min_max_comparison_failure():
    request = UnifiedBulkUpdateRequest(start_date="2030-01-01", end_date="2030-01-01", update_fields=["min_stay", "max_stay"], min_stay=3, max_stay=0)
    _validate_los_updates(request, "exely")


def test_per_room_negative_is_blocked_and_disabled_fields_are_ignored():
    request = UnifiedBulkUpdateRequest(start_date="2030-01-01", end_date="2030-01-01", update_fields=["max_stay"], per_room_values=[{"room_type_code": "R", "rate_plan_codes": ["RP"], "max_stay": -1}])
    with pytest.raises(HTTPException):
        _validate_los_updates(request, "exely")
    request.update_fields = ["availability"]
    _validate_los_updates(request, "exely")


@pytest.mark.parametrize("value", [False, True, 0.5, "0"])
def test_unified_request_never_coerces_false_into_a_clear_command(value):
    base = {"start_date": "2030-01-01", "end_date": "2030-01-01", "update_fields": ["min_stay"]}
    with pytest.raises(ValidationError):
        UnifiedBulkUpdateRequest(**base, min_stay=value)
    with pytest.raises(ValidationError):
        UnifiedBulkUpdateRequest(**base, per_room_values=[{"room_type_code": "R", "rate_plan_codes": ["RP"], "min_stay": value}])
