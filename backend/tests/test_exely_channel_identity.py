"""PMSConnect 1.17 pp.72/93: channel IDs are not delivery-ACK IDs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.providers.exely import lifecycle, pms_lifecycle
from domains.channel_manager.providers.exely.lifecycle import _reservation_document
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.pms_lifecycle import _booking_fields
from domains.channel_manager.providers.exely.response_parser import parse_read_rs
from tests.test_exely_reservation_lifecycle import fake_db as fake_db


def envelope(ids, channel='<CompanyName Code="LBR" CodeContext="PMSConnect">Liberty Channel</CompanyName>'):
    return f'''<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body><OTA_ResRetrieveRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>
    <ReservationsList><HotelReservation ResStatus="Commit" CreateDateTime="2030-10-01T11:00:00" LastModifyDateTime="2030-10-01T12:00:00">
    <POS><Source><BookingChannel Type="2">{channel}</BookingChannel></Source></POS>
    {ids}<RoomStays><RoomStay IndexNumber="1">
      <RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes>
      <RoomRates><RoomRate EffectiveDate="2030-11-10" ExpireDate="2030-11-10" RatePlanCode="BAR">
        <Total AmountAfterTax="90" CurrencyCode="USD"/></RoomRate>
      <RoomRate EffectiveDate="2030-11-11" ExpireDate="2030-11-11" RatePlanCode="BAR">
        <Total AmountAfterTax="130" CurrencyCode="USD"/></RoomRate></RoomRates>
      <GuestCounts><GuestCount AgeQualifyingCode="10" Count="1"/></GuestCounts>
      <TimeSpan Start="2030-11-10" End="2030-11-12"/>
      <Total AmountAfterTax="220" CurrencyCode="USD"/>
    </RoomStay></RoomStays>
    <ResGuests><ResGuest><Profiles><ProfileInfo><UniqueID Type="14" ID="not-a-reservation"/>
    <Profile><Customer><PersonName><GivenName>Synthetic</GivenName><Surname>Guest</Surname>
    </PersonName></Customer></Profile></ProfileInfo></Profiles></ResGuest></ResGuests>
    <ResGlobalInfo><Total AmountAfterTax="250" CurrencyCode="USD"/>
    <Guarantee><Comments><Comment Name="PaymentMethodName"><Text>PayOnArrival</Text></Comment>
    </Comments></Guarantee><DepositPayments><GuaranteePayment Type="ReceivedPayment">
    <AmountPercent CurrencyCode="USD" Amount="80"/></GuaranteePayment></DepositPayments>
    </ResGlobalInfo></HotelReservation></ReservationsList></OTA_ResRetrieveRS></s:Body></s:Envelope>'''.encode()


PRIMARY = '<UniqueID Type="14" ID="exely-group" ID_Context="PMSConnect"/>'
EXTERNAL = '<UniqueID Type="14" ID="liberty-booking" ID_Context="External"/>'


@pytest.mark.parametrize('ids', [PRIMARY + EXTERNAL, EXTERNAL + PRIMARY])
def test_provider_and_external_channel_identity_are_order_independent(ids):
    result = parse_read_rs(envelope(ids))
    assert result['success'] is True
    row = result['reservations'][0]
    assert row['reservation_id'] == 'exely-group'
    assert row['reservation_id_context'] == 'PMSConnect'
    assert row['channel_reservation_id'] == 'liberty-booking'
    assert row['channel'] == 'Liberty Channel'
    assert row['channel_code'] == 'LBR'


def test_blank_context_is_a_provider_id_but_external_only_is_not():
    row = parse_read_rs(envelope('<UniqueID Type="14" ID="exely-group"/>' + EXTERNAL))['reservations'][0]
    assert row['reservation_id'] == 'exely-group'
    assert row['reservation_id_context'] == ''
    external_only = parse_read_rs(envelope(EXTERNAL))['reservations'][0]
    assert not external_only['reservation_id']
    assert external_only['channel_reservation_id'] == 'liberty-booking'


def test_conflicting_provider_ids_fail_the_whole_read_not_silently_pick_last():
    result = parse_read_rs(envelope(PRIMARY + '<UniqueID Type="14" ID="different-provider-id"/>'))
    assert result['success'] is False
    assert result['result_class'] == 'MALFORMED'
    assert result['reservations'] == []
    assert 'different-provider-id' not in str(result)


def test_duplicate_identical_provider_ids_are_safe_and_nested_profile_ids_do_not_win():
    row = parse_read_rs(envelope(PRIMARY + PRIMARY + EXTERNAL))['reservations'][0]
    assert row['reservation_id'] == 'exely-group'


def test_unknown_context_is_not_an_ack_identity_and_multiple_external_refs_remain_separate():
    row = parse_read_rs(envelope('<UniqueID Type="14" ID="other" ID_Context="Unknown"/>' +
        EXTERNAL + '<UniqueID Type="14" ID="second-channel-ref" ID_Context="External"/>'))['reservations'][0]
    assert not row['reservation_id']
    assert row['channel_reservation_id'] == ''
    assert row['channel_reservation_ids'] == ['liberty-booking', 'second-channel-ref']


def test_booking_engine_without_company_is_not_channel_type_number():
    row = parse_read_rs(envelope(PRIMARY, channel=''))['reservations'][0]
    assert row['channel'] == 'exely'


def test_channel_lineage_survives_normalization_current_row_and_room_booking():
    raw = parse_read_rs(envelope(PRIMARY + EXTERNAL))['reservations'][0]
    canonical = normalize_reservation({**raw, 'property_id': 'TEST'})
    assert canonical['channel_reservation_id'] == 'liberty-booking'
    current = _reservation_document('tenant-test', canonical, 'event-test', 'hash-test', 'identity-test')
    assert current['provider_reservation_id'] == 'exely-group'
    assert current['channel_reservation_id'] == 'liberty-booking'
    assert current['channel_code'] == 'LBR'
    booking = _booking_fields(
        tenant_id='tenant-test', property_id='TEST', reservation=current,
        version_doc={'provider_version_key': 'version-test'}, room=current['rooms'][0],
        mapping={'pms_room_type': 'Standard'}, slot=0, guest_id='guest-test', booking_id='booking-test')
    assert booking['provider_group_reservation_id'] == 'exely-group'
    assert booking['channel_reservation_id'] == 'liberty-booking'
    assert booking['provider_channel_name'] == 'Liberty Channel'
    assert booking['provider_channel_code'] == 'LBR'
    assert booking['provider_payment_method'] == 'PayOnArrival'
    assert booking['booking_source'] == 'exely'
    # Extra service and provider prepayment do not become accommodation or a PMS receipt.
    assert booking['total_amount'] == 220
    assert booking['paid_amount'] == 0
    assert booking['daily_rates'] == [{'date': '2030-11-10', 'amount': 90}, {'date': '2030-11-11', 'amount': 130}]


def test_zero_accommodation_is_not_replaced_by_an_extra_service_or_provider_deposit():
    booking = _booking_fields(
        tenant_id='tenant-test', property_id='TEST',
        reservation={'external_id': 'free-room-paid-service', 'rooms': [{'amount': 0}], 'total': 30},
        version_doc={'provider_version_key': 'version-test'},
        room={'amount': 0, 'check_in': '2030-11-10', 'check_out': '2030-11-11'},
        mapping={'pms_room_type': 'Standard'}, slot=0, guest_id='guest-test', booking_id='booking-test')
    assert booking['total_amount'] == 0
    assert booking['paid_amount'] == 0


@pytest.mark.asyncio
async def test_full_channel_parse_import_and_ack_use_only_provider_identity_once(fake_db):
    raw = parse_read_rs(envelope(PRIMARY + EXTERNAL))['reservations'][0]
    canonical = normalize_reservation({**raw, 'property_id': 'TEST'})
    await fake_db.exely_room_mappings.insert_one({'id': 'mapping-test', 'tenant_id': 'tenant',
        'exely_room_code': 'STD', 'exely_rate_plan_code': 'BAR', 'pms_room_type': 'Standard'})
    result = await lifecycle.persist_exely_event('tenant', canonical, 'reservation', 'event-test', 'hash-test')
    assert result['action'] == 'created'
    current = await fake_db.exely_reservations.find_one({'tenant_id': 'tenant', 'external_id': 'exely-group'})
    assert (await pms_lifecycle.process_reservation_version('tenant', current))['success'] is True
    current = await fake_db.exely_reservations.find_one({'tenant_id': 'tenant', 'external_id': 'exely-group'})
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    assert (await lifecycle.acknowledge_durable_version(provider, current))['provider_write_count'] == 1
    assert (await lifecycle.acknowledge_durable_version(provider, current))['provider_write_count'] == 0
    provider.confirm_delivery.assert_awaited_once()
    assert provider.confirm_delivery.await_args.args[0] == 'exely-group'
    assert provider.confirm_delivery.await_args.kwargs['provider_id_context'] == 'PMSConnect'
    assert len(fake_db.bookings.documents) == 1
    assert fake_db.bookings.documents[0]['channel_reservation_id'] == 'liberty-booking'
