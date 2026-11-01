"""PMSConnect 1.17 pp.88-91,145: service totals are separate from room rates."""

from copy import deepcopy

import pytest
from test_exely_reservation_lifecycle import _add_mapping, fake_db  # noqa: F401, F811

from domains.channel_manager.providers.exely import lifecycle, pms_lifecycle
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.response_parser import parse_hotel_avail_rs, parse_read_rs


def payload(services=None, room_refs='<ServiceRPH RPH="1"/>', second_room=""):
    services = (
        services
        if services is not None
        else """<Service ServiceRPH="1" ID="5001517" Inclusive="false" Quantity="2" ServicePricingType="Per person per night">
      <ServiceDetails><TimeSpan Start="2030-11-10T00:00:00" Duration="1"/>
      <Comments><Comment Name="Breakfast"><Text/></Comment></Comments>
      <Total AmountAfterTax="300.00" CurrencyCode="USD"/></ServiceDetails></Service>"""
    )
    return f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>
    <OTA_ResRetrieveRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/><ReservationsList>
    <HotelReservation ResStatus="Commit" CreateDateTime="2030-01-01T09:00:00Z" LastModifyDateTime="2030-01-01T10:00:00Z">
    <UniqueID Type="14" ID="provider-reservation"/><RoomStays><RoomStay IndexNumber="1">
    <RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes><RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans>
    <GuestCounts><GuestCount AgeQualifyingCode="10" Count="2"/></GuestCounts>
    <TimeSpan Start="2030-11-10" End="2030-11-11"/><Total AmountAfterTax="100" CurrencyCode="USD"/>
    <BasicPropertyInfo HotelCode="property"/><ServiceRPHs>{room_refs}</ServiceRPHs></RoomStay>{second_room}</RoomStays>
    <ResGlobalInfo><Total AmountAfterTax="400" CurrencyCode="USD"/></ResGlobalInfo>
    <Services>{services}</Services></HotelReservation></ReservationsList></OTA_ResRetrieveRS></s:Body></s:Envelope>""".encode()


def canonical(xml=None):
    parsed = parse_read_rs(xml or payload())
    assert parsed["success"], parsed
    raw = parsed["reservations"][0]
    raw["hotel_code"] = "property"
    return normalize_reservation(raw)


def test_breakfast_is_preserved_without_multiplying_provider_total_by_quantity():
    item = canonical()
    assert item["financial"]["total_amount"] == 400
    assert item["rooms"][0]["amount"] == 100
    service = item["rooms"][0]["services"][0]
    assert service["provider_id"] == "5001517"
    assert service["name"] == "Breakfast"
    assert (service["amount"], service["currency"], service["quantity"]) == (300, "USD", 2)
    assert service["start_date"] == "2030-11-10"
    assert service["duration"] == 1


def test_service_free_raw_payload_keeps_existing_version_hash_shape():
    row = parse_read_rs(payload(services="", room_refs=""))["reservations"][0]
    assert "services" not in row
    assert "service_references" not in row["rooms"][0]


def test_channel_service_without_any_api_or_pms_code_is_valid():
    xml = payload().replace(b' ID="5001517"', b"")
    service = canonical(xml)["rooms"][0]["services"][0]
    assert service["provider_id"] == ""
    assert service["name"] == "Breakfast"
    assert service["amount"] == 300


def test_service_currency_and_exact_provider_service_time_are_not_rewritten():
    xml = payload().replace(b'Start="2030-11-10T00:00:00"', b'Start="2030-11-10T12:15:00"')
    xml = xml.replace(b'300.00" CurrencyCode="USD"', b'300.00" CurrencyCode="EUR"')
    service = canonical(xml)["rooms"][0]["services"][0]
    assert service["currency"] == "EUR"
    assert service["source_start"] == "2030-11-10T12:15:00"


def test_service_without_own_date_uses_its_referenced_room_not_first_rooms_arrival():
    second = """<RoomStay IndexNumber="2"><RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes>
    <RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans><TimeSpan Start="2030-11-12" End="2030-11-13"/>
    <Total AmountAfterTax="100" CurrencyCode="USD"/><ServiceRPHs><ServiceRPH RPH="1"/></ServiceRPHs></RoomStay>"""
    xml = payload(room_refs="", second_room=second).replace(b'Start="2030-11-10T00:00:00" ', b"")
    item = canonical(xml)
    assert item["rooms"][1]["services"][0]["start_date"] == "2030-11-12"


@pytest.mark.parametrize("replacement", [b"NaN", b"Infinity", b"-1", b"unknown"])
def test_invalid_service_money_cannot_be_silently_acknowledged(replacement):
    result = parse_read_rs(payload().replace(b"300.00", replacement))
    assert result["success"] is False
    assert result["reservations"] == []


def test_unknown_room_reference_and_duplicate_service_rph_block_batch():
    assert not parse_read_rs(payload(room_refs='<ServiceRPH RPH="missing"/>'))["success"]
    xml = payload()
    service = xml[xml.index(b"<Service ServiceRPH") : xml.index(b"</Services>")]
    assert not parse_read_rs(xml.replace(b"</Services>", service + b"</Services>"))["success"]


def test_included_zero_service_legacy_date_and_daily_prices_are_retained():
    xml = payload().replace(b'Inclusive="false"', b'Inclusive="true"').replace(b"300.00", b"0.00")
    xml = xml.replace(b'Start="2030-11-10T00:00:00"', b'Start="10.11.2030 0:00:00"')
    xml = xml.replace(b"</ServiceDetails>", b'<ServiceRates><ServiceRate EffectiveDate="2030-11-10" AmountAfterTax="0"/></ServiceRates></ServiceDetails>')
    service = canonical(xml)["rooms"][0]["services"][0]
    assert service["inclusive"] is True
    assert service["amount"] == 0
    assert service["start_date"] == "2030-11-10"
    assert service["daily_rates"] == [{"date": "2030-11-10", "amount": 0.0}]


def test_shared_and_unreferenced_group_services_have_one_owner_not_two_charges():
    second = """<RoomStay IndexNumber="2"><RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes>
    <RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans><TimeSpan Start="2030-11-10" End="2030-11-11"/>
    <Total AmountAfterTax="100" CurrencyCode="USD"/><ServiceRPHs><ServiceRPH RPH="1"/></ServiceRPHs></RoomStay>"""
    item = canonical(payload(second_room=second))
    assert sum(len(room["services"]) for room in item["rooms"]) == 1
    assert item["rooms"][0]["services"][0]["room_stay_indexes"] == ["1", "2"]
    item = canonical(payload(room_refs="", second_room=second.replace('<ServiceRPH RPH="1"/>', "")))
    assert sum(len(room["services"]) for room in item["rooms"]) == 1
    assert item["rooms"][0]["services"][0]["scope"] == "reservation"


def test_discovery_distinguishes_exely_id_and_optional_pms_service_code():
    xml = b"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>
    <OTA_HotelAvailRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>
    <Services><Service ID="5001517" ServiceInventoryCode="BREAKFAST" Type="Meal">
    <ServiceDetails><Comments><Comment Name="ServiceName"><Text>Breakfast</Text></Comment></Comments></ServiceDetails>
    </Service><Service ID="5001518" Type="Common"/></Services></OTA_HotelAvailRS></s:Body></s:Envelope>"""
    services = parse_hotel_avail_rs(xml)["services"]
    assert services[0]["provider_id"] == "5001517"
    assert services[0]["pms_code"] == "BREAKFAST"
    assert services[1]["pms_code"] == ""


@pytest.mark.asyncio
async def test_services_survive_durable_import_retry_modification_and_ack_readback(fake_db):  # noqa: F811
    await _add_mapping(fake_db)
    item = canonical()
    item["property_id"] = "property"
    await lifecycle.persist_exely_event("tenant", item, "reservation", "event", "first")
    current = fake_db.exely_reservations.documents[0]
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert result["success"]
    booking = fake_db.bookings.documents[0]
    assert booking["total_amount"] == 100
    assert booking["paid_amount"] == 0
    assert booking["provider_services"][0]["amount"] == 300
    assert (await pms_lifecycle.process_reservation_version("tenant", current))["success"]
    assert len(fake_db.bookings.documents) == 1
    original = deepcopy(booking["provider_services"])
    booking["provider_services"] = []
    assert not (await pms_lifecycle.process_reservation_version("tenant", current))["success"]
    version = fake_db.exely_reservation_versions.documents[0]
    assert not await lifecycle._durable_readback(version)
    booking["provider_services"] = original
    assert await lifecycle._durable_readback(version)
    item["provider_last_modified_at"] = "2030-01-01T11:00:00Z"
    item["rooms"][0]["services"] = []
    item["services"] = []
    await lifecycle.persist_exely_event("tenant", item, "modification", "second-event", "second")
    assert (await pms_lifecycle.process_reservation_version("tenant", fake_db.exely_reservations.documents[0]))["success"]
    assert fake_db.bookings.documents[0]["provider_services"] == []
