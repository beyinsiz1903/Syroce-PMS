"""Sanitized shapes observed in hotel 501694 certification on 2026-09-19."""

from domains.channel_manager.providers.exely.response_parser import parse_read_rs
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.pms_lifecycle import _booking_fields


def test_pmsconnect_adult_beds_dated_totals_and_room_guest_references():
    xml = b'''<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body><OTA_ResRetrieveRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>
    <ReservationsList><HotelReservation ResStatus="Commit">
    <UniqueID Type="14" ID="test-group"/>
    <RoomStays><RoomStay IndexNumber="0">
      <RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes>
      <RoomRates><RoomRate EffectiveDate="2030-11-10" ExpireDate="2030-11-10" RatePlanCode="BAR">
        <Total AmountAfterTax="100.0000" CurrencyCode="USD"/>
      </RoomRate><RoomRate EffectiveDate="2030-11-11" ExpireDate="2030-11-11" RatePlanCode="BAR">
        <Total AmountAfterTax="100.0000" CurrencyCode="USD"/>
      </RoomRate></RoomRates>
      <GuestCounts><GuestCount AgeQualifyingCode="AdultBed" Count="1" ResGuestRPH="1"/>
        <GuestCount AgeQualifyingCode="AdultBed" Count="1"/></GuestCounts>
      <TimeSpan Start="2030-11-10T14:00:00" End="2030-11-12T12:00:00"/>
      <Total AmountAfterTax="200" CurrencyCode="USD"/>
    </RoomStay><RoomStay IndexNumber="1">
      <RoomTypes><RoomType RoomTypeCode="DLX"/></RoomTypes>
      <RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans>
      <GuestCounts><GuestCount AgeQualifyingCode="AdultBed" Count="1" ResGuestRPH="2"/>
        <GuestCount AgeQualifyingCode="AdultBed" Count="2"/></GuestCounts>
      <TimeSpan Start="2030-11-10T14:00:00" End="2030-11-12T12:00:00"/>
      <Total AmountAfterTax="240" CurrencyCode="USD"/>
    </RoomStay></RoomStays>
    <ResGuests><ResGuest ResGuestRPH="1"><Profiles><ProfileInfo><Profile><Customer>
      <PersonName><GivenName>First</GivenName><Surname>Guest</Surname></PersonName>
    </Customer></Profile></ProfileInfo></Profiles></ResGuest>
    <ResGuest ResGuestRPH="2"><Profiles><ProfileInfo><Profile><Customer>
      <PersonName><GivenName>Second</GivenName><Surname>Guest</Surname></PersonName>
    </Customer></Profile></ProfileInfo></Profiles></ResGuest></ResGuests>
    <ResGlobalInfo><Total AmountAfterTax="440" CurrencyCode="USD"/></ResGlobalInfo>
    </HotelReservation></ReservationsList></OTA_ResRetrieveRS></s:Body></s:Envelope>'''
    parsed = parse_read_rs(xml)
    assert parsed['success']
    raw = parsed['reservations'][0]
    assert [r['adults'] for r in raw['rooms']] == [2, 3]
    assert raw['total_guests'] == 5
    assert raw['guest_name'] == 'First Guest'
    assert [r['guest_name'] for r in raw['rooms']] == ['First Guest', 'Second Guest']
    assert raw['rooms'][0]['amount'] == 200
    assert raw['rooms'][0]['daily_rates'] == [
        {'date': '2030-11-10', 'amount': 100}, {'date': '2030-11-11', 'amount': 100}]
    canonical = normalize_reservation(raw)
    assert canonical['rooms'][1]['guest_name'] == 'Second Guest'

    booking = _booking_fields(
        tenant_id='test', property_id='test',
        reservation={**raw, 'external_id': 'test-group'},
        version_doc={'provider_version_key': 'test-version'}, room=canonical['rooms'][0],
        mapping={'pms_room_type': 'Standard'}, slot=0, guest_id='test-guest', booking_id='test-booking')
    assert booking['adults'] == 2
    assert booking['currency'] == 'USD'
    assert booking['daily_rates'] == raw['rooms'][0]['daily_rates']
    assert booking['total_amount'] == 200


def test_numeric_ota_guest_counts_remain_supported_and_accumulate():
    xml = b'''<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body><OTA_ResRetrieveRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>
    <ReservationsList><HotelReservation><RoomStays><RoomStay>
    <RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes>
    <GuestCounts><GuestCount AgeQualifyingCode="10" Count="1"/>
    <GuestCount AgeQualifyingCode="10" Count="2"/><GuestCount AgeQualifyingCode="8" Count="1"/>
    <GuestCount AgeQualifyingCode="8" Count="2"/></GuestCounts>
    </RoomStay></RoomStays></HotelReservation></ReservationsList>
    </OTA_ResRetrieveRS></s:Body></s:Envelope>'''
    room = parse_read_rs(xml)['reservations'][0]['rooms'][0]
    assert (room['adults'], room['children']) == (3, 3)
