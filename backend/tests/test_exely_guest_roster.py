"""Named occupants must survive SOAP ingestion and safe REST completion."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.providers.exely import demographics, guest_roster, lifecycle, pms_lifecycle
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.read_reservation import ReadReservationError
from domains.channel_manager.providers.exely.response_parser import parse_read_rs
from tests.test_exely_connection_controls import local_mongo as local_mongo
from tests.test_exely_read_demographics import CONNECTION
from tests.test_exely_read_demographics import scenario as scenario
from tests.test_exely_reservation_lifecycle import _add_mapping, _canonical, _persist
from tests.test_exely_reservation_lifecycle import fake_db as fake_db

pytestmark = pytest.mark.exely_failure_stress


def _person(rph, first):
    return {"source_rph": rph, "guest_firstname": first, "guest_lastname": "Example", "guest_name": f"{first} Example"}


def _xml(second_ref="2", duplicate=False, separate_refs=False):
    refs = ('<GuestCount AgeQualifyingCode="AdultBed" Count="2"/>' if separate_refs else
            f'<GuestCount AgeQualifyingCode="AdultBed" Count="1" ResGuestRPH="1"/><GuestCount AgeQualifyingCode="AdultBed" Count="1" ResGuestRPH="{second_ref}"/>')
    extra_refs = f'<ResGuestRPHs><ResGuestRPH RPH="1"/><ResGuestRPH RPH="{second_ref}"/></ResGuestRPHs>' if separate_refs else ""
    people = "".join(f'<ResGuest ResGuestRPH="{rph}"><Profiles><ProfileInfo><Profile><Customer><PersonName><GivenName>{name}</GivenName><Surname>Example</Surname></PersonName></Customer></Profile></ProfileInfo></Profiles></ResGuest>' for rph, name in [("1", "Sam"), ("1" if duplicate else "2", "Robin"), ("3", "Morgan")])
    return f'''<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>
    <OTA_ResRetrieveRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/><ReservationsList>
    <HotelReservation ResStatus="Commit" CreateDateTime="2030-01-01T09:00:00Z" LastModifyDateTime="2030-01-01T10:00:00Z">
    <UniqueID Type="14" ID="synthetic-roster"/><RoomStays>
    <RoomStay IndexNumber="1"><RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes><RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans>
    <GuestCounts>{refs}</GuestCounts>{extra_refs}<TimeSpan Start="2030-01-01" End="2030-01-03"/><Total AmountAfterTax="100" CurrencyCode="USD"/></RoomStay>
    <RoomStay IndexNumber="2"><RoomTypes><RoomType RoomTypeCode="DLX"/></RoomTypes><RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans>
    <GuestCounts><GuestCount AgeQualifyingCode="AdultBed" Count="1" ResGuestRPH="3"/></GuestCounts>
    <TimeSpan Start="2030-01-01" End="2030-01-03"/><Total AmountAfterTax="120" CurrencyCode="USD"/></RoomStay></RoomStays>
    <ResGuests>{people}</ResGuests><ResGlobalInfo><HotelReservationIDs><HotelReservationID ResID_Value="synthetic-roster"/></HotelReservationIDs>
    <Total AmountAfterTax="220" CurrencyCode="USD"/><Profiles><ProfileInfo><Profile><Customer><PersonName><GivenName>Booking</GivenName><Surname>Contact</Surname></PersonName></Customer></Profile></ProfileInfo></Profiles></ResGlobalInfo>
    </HotelReservation></ReservationsList></OTA_ResRetrieveRS></s:Body></s:Envelope>'''.encode()


@pytest.mark.parametrize("separate_refs", [False, True])
def test_all_room_occupants_survive_normalization_without_contact_or_other_room_leakage(separate_refs):
    parsed = parse_read_rs(_xml(separate_refs=separate_refs))
    assert parsed["success"]
    normalized = normalize_reservation(parsed["reservations"][0])
    assert normalized["guest"]["name"] == "Booking Contact"
    assert [[p["guest_name"] for p in room["guests"]] for room in normalized["rooms"]] == [["Sam Example", "Robin Example"], ["Morgan Example"]]
    assert normalized["total_guests"] == 3
    assert set(normalized["rooms"][0]["guests"][1]) == {"source_rph", "guest_firstname", "guest_lastname", "guest_name"}


def test_roster_provenance_does_not_retain_extra_contact_payloads():
    raw = parse_read_rs(_xml())["reservations"][0]
    raw["rooms"][0]["guests"][1].update(guest_email="synthetic@example.invalid", guest_phone="synthetic-private-phone", passport_number="not-a-document")
    normalized = normalize_reservation(raw)
    assert set(normalized["rooms"][0]["guests"][1]) == {"source_rph", "guest_firstname", "guest_lastname", "guest_name"}


@pytest.mark.parametrize("kwargs", [{"second_ref": "missing"}, {"duplicate": True}])
def test_invalid_source_references_hold_the_entire_batch(kwargs):
    parsed = parse_read_rs(_xml(**kwargs))
    assert parsed["success"] is False and parsed["result_class"] == "MALFORMED"
    assert parsed["reservations"] == []


async def _seed(database, booking_id="room-a", primary="Sam", total=2):
    booking = {"id": booking_id, "tenant_id": "tenant-a", "property_id": "501694", "provider_version_key": "2030-01-01T10:00:00Z",
               "provider_group_reservation_id": "synthetic-roster", "booking_source": "exely", "status": "confirmed",
               "guest_id": f"primary-{booking_id}", "guests_count": total, "total_amount": 100, "currency": "USD",
               "check_in": "2030-01-01", "check_out": "2030-01-03", "updated_at": "original", "_version": 0}
    await database.bookings.insert_one(deepcopy(booking))
    await database.guests.insert_one({"tenant_id": "tenant-a", "id": booking["guest_id"], "first_name": primary, "last_name": "Example", "name": f"{primary} Example"})
    return booking


@pytest.mark.live_mongo
async def test_real_mongo_roster_creates_additional_profile_link_and_search_fields_once(local_mongo):
    booking = await _seed(local_mongo)
    original = deepcopy(booking)
    first = await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    fresh = await local_mongo.bookings.find_one({"id": booking["id"]})
    again = await guest_roster.sync_room_roster(local_mongo, "tenant-a", fresh, [_person("1", "Sam"), _person("2", "Robin")])
    assert first == again and await guest_roster.roster_readback(local_mongo, "tenant-a", booking["id"], first)
    assert await local_mongo.guests.count_documents({}) == 2
    assert await local_mongo.booking_guests.count_documents({}) == 1
    added = await local_mongo.guests.find_one({"first_name": "Robin"})
    assert added["name_lower"] == "robin example" and added["_ng_name"]
    assert fresh["guest_id"] == original["guest_id"]
    for key in ("status", "total_amount", "currency", "guests_count", "check_in", "check_out"):
        assert fresh[key] == original[key]
    for collection in ("payments", "folios", "kbs_jobs", "exely_ari_outbox"):
        assert await local_mongo[collection].count_documents({}) == 0


@pytest.mark.live_mongo
async def test_real_mongo_room_scope_isolates_same_provider_guest_references(local_mongo):
    one, two = await _seed(local_mongo), await _seed(local_mongo, "room-b", "Morgan")
    for booking, primary in [(one, "Sam"), (two, "Morgan")]:
        await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", primary), _person("2", "Robin")])
    links = await local_mongo.booking_guests.find({}).to_list(10)
    assert len({link["guest_id"] for link in links}) == 2
    assert {link["booking_id"] for link in links} == {"room-a", "room-b"}


@pytest.mark.live_mongo
@pytest.mark.parametrize("drift", ["tenant", "version", "status", "manual_link", "primary", "too_many"])
async def test_roster_rejects_stale_or_ambiguous_targets_without_partial_writes(local_mongo, drift):
    booking = await _seed(local_mongo)
    roster = [_person("1", "Sam"), _person("2", "Robin")]
    tenant = "tenant-a"
    if drift == "tenant":
        tenant = "tenant-b"
    elif drift in {"version", "status"}:
        await local_mongo.bookings.update_one({"id": booking["id"]}, {"$set": {"provider_version_key" if drift == "version" else "status": "changed"}})
    elif drift == "manual_link":
        await local_mongo.booking_guests.insert_one({"tenant_id": tenant, "booking_id": booking["id"], "guest_id": "manual-guest"})
    elif drift == "primary":
        await local_mongo.guests.update_one({"id": booking["guest_id"]}, {"$set": {"first_name": "Edited"}})
    elif drift == "too_many":
        roster.append(_person("3", "Morgan"))
    before = await local_mongo.bookings.find_one({"id": booking["id"]})
    with pytest.raises(ReadReservationError):
        await guest_roster.sync_room_roster(local_mongo, tenant, booking, roster)
    assert await local_mongo.guests.count_documents({}) == 1
    assert await local_mongo.bookings.find_one({"id": booking["id"]}) == before


@pytest.mark.live_mongo
async def test_failure_after_secondary_creation_rolls_back_membership_and_profiles(local_mongo, monkeypatch):
    booking = await _seed(local_mongo, total=3)
    calls = 0
    original = guest_roster.encrypt_guest_insert
    def fail_second_insert(doc):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated storage failure")
        return original(doc)
    monkeypatch.setattr(guest_roster, "encrypt_guest_insert", fail_second_insert)
    with pytest.raises(RuntimeError, match="simulated storage"):
        await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin"), _person("3", "Morgan")])
    assert await local_mongo.guests.count_documents({}) == 1
    assert await local_mongo.booking_guests.count_documents({}) == 0
    assert not (await local_mongo.bookings.find_one({"id": booking["id"]})).get("exely_guest_roster")


@pytest.mark.live_mongo
async def test_provider_modification_retires_only_owned_link_and_preserves_guest_record(local_mongo):
    booking = await _seed(local_mongo)
    manifest = await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    booking = await local_mongo.bookings.find_one({"id": booking["id"]})
    await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam")])
    assert await local_mongo.booking_guests.count_documents({}) == 0
    assert await local_mongo.guests.find_one({"id": manifest["members"][1]["guest_id"]})


@pytest.mark.live_mongo
async def test_secondary_manual_name_edit_is_preserved_and_not_acknowledged(local_mongo):
    booking = await _seed(local_mongo)
    manifest = await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    await local_mongo.guests.update_one({"id": manifest["members"][1]["guest_id"]}, {"$set": {"first_name": "ReceptionEdit"}})
    booking = await local_mongo.bookings.find_one({"id": booking["id"]})
    with pytest.raises(ReadReservationError, match="GUEST_EDITED"):
        await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    assert not await guest_roster.roster_readback(local_mongo, "tenant-a", booking["id"], manifest)


@pytest.mark.live_mongo
async def test_rest_completion_reuses_profiles_across_reference_namespaces(local_mongo):
    booking = await _seed(local_mongo)
    first = await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    primary = await local_mongo.guests.find_one({"id": booking["guest_id"]})
    rest = guest_roster.rest_roster([{"firstName": "Robin", "lastName": "Example"}, {"firstName": "Sam", "lastName": "Example"}], primary)
    booking = await local_mongo.bookings.find_one({"id": booking["id"]})
    second = await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, rest, source="read_reservation_v1")
    assert [p["guest_id"] for p in first["members"]] == [p["guest_id"] for p in second["members"]]
    assert await guest_roster.roster_readback(local_mongo, "tenant-a", booking["id"], first)
    assert await local_mongo.guests.count_documents({}) == 2


@pytest.mark.live_mongo
async def test_existing_acked_reservation_is_repaired_from_two_reads_without_source_or_financial_mutation(local_mongo, scenario, monkeypatch):
    database, reservation, booking, remote = scenario
    for collection in ("exely_connections", "exely_reservations", "exely_reservation_versions", "exely_room_mappings", "bookings"):
        await local_mongo[collection].insert_many(deepcopy(getattr(database, collection).documents))
    await local_mongo.bookings.update_one({"id": booking["id"]}, {"$set": {"guest_id": "original-primary"}})
    await local_mongo.guests.insert_one({"id": "original-primary", "tenant_id": "tenant-a", "first_name": "Sam", "last_name": "Example"})
    remote["roomStays"][0]["guests"] = [{"firstName": "Sam", "lastName": "Example"}, {"firstName": "Robin", "lastName": "Example"}]
    monkeypatch.setattr(demographics, "db", local_mongo)
    client = SimpleNamespace(booking=AsyncMock(return_value=remote))
    before = await local_mongo.bookings.find_one({"id": booking["id"]})
    source = await local_mongo.exely_reservations.find_one({"external_id": reservation["external_id"]})
    result = await guest_roster.reconcile_guest_roster(local_mongo, "tenant-a", CONNECTION, reservation["external_id"], client)
    assert result["status"] == "roster_verified" and result["rooms"] == [{"booking_id": booking["id"], "named_guests": 2}]
    assert client.booking.await_count == 2 and result["provider_write_count"] == 0
    after = await local_mongo.bookings.find_one({"id": booking["id"]})
    assert {k: v for k, v in after.items() if k not in {"exely_guest_roster", "_version"}} == before
    assert await local_mongo.exely_reservations.find_one({"external_id": reservation["external_id"]}) == source
    await guest_roster.reconcile_guest_roster(local_mongo, "tenant-a", CONNECTION, reservation["external_id"], client)
    assert await local_mongo.booking_guests.count_documents({}) == 1


async def test_pms_import_does_not_ack_when_roster_persistence_fails(fake_db, monkeypatch):
    await _add_mapping(fake_db)
    canonical = _canonical()
    canonical["rooms"][0].update(guest_name="Sam Example", guest_firstname="Sam", guest_lastname="Example", guests=[_person("1", "Sam"), _person("2", "Robin")])
    _, current = await _persist(fake_db, canonical)
    persist = AsyncMock(side_effect=ReadReservationError("EXELY_ROSTER_READBACK_FAILED"))
    monkeypatch.setattr(guest_roster, "sync_room_roster", persist)
    ack = AsyncMock()
    monkeypatch.setattr(pms_lifecycle, "acknowledge_durable_version", ack)
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert not result["success"]
    assert persist.await_count == 1
    ack.assert_not_awaited()


@pytest.mark.live_mongo
async def test_full_parser_normalizer_pms_durability_and_reordered_guest_references(local_mongo, monkeypatch):
    for module in (lifecycle, pms_lifecycle):
        monkeypatch.setattr(module, "db", local_mongo)
    async def create_booking(*, tenant_id, booking_doc):
        await local_mongo.bookings.insert_one(dict(booking_doc))
        return booking_doc
    monkeypatch.setattr("core.atomic_booking.create_booking_atomic", create_booking)
    await _add_mapping(local_mongo)
    await _add_mapping(local_mongo, "DLX", "BAR", "Deluxe")
    canonical = normalize_reservation(parse_read_rs(_xml())["reservations"][0])
    canonical.update(property_id="property", external_id="provider-reservation", provider_reservation_id="provider-reservation")
    persisted, current = await _persist(local_mongo, canonical)
    assert current is not None, persisted
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert result["success"] and len(result["pms_booking_ids"]) == 2
    assert await local_mongo.guests.count_documents({}) == 3
    assert await local_mongo.booking_guests.count_documents({}) == 1
    version = await local_mongo.exely_reservation_versions.find_one({"version_identity": current["provider_version_identity"]})
    assert version["processing_state"] == "PMS_DURABLE" and version["ack_state"] == lifecycle.ACK_PENDING
    assert await pms_lifecycle._readback_expectations("tenant", current["provider_version_key"], version["durable_expectations"])
    assert await lifecycle._durable_readback(version)
    sam = await local_mongo.guests.find_one({"first_name": "Sam"})
    robin = await local_mongo.guests.find_one({"first_name": "Robin"})
    canonical["rooms"][0]["guests"].reverse()
    canonical["rooms"][0]["guest_email"] = "other-occupant@example.invalid"
    canonical["provider_last_modified_at"] = "2030-01-01T11:00:00Z"
    _, current = await _persist(local_mongo, canonical, payload_hash="new-room-roster-order")
    assert (await pms_lifecycle.process_reservation_version("tenant", current))["success"]
    assert await local_mongo.guests.count_documents({}) == 3
    assert await local_mongo.booking_guests.count_documents({}) == 1
    link = await local_mongo.booking_guests.find_one({})
    booking = await local_mongo.bookings.find_one({"id": link["booking_id"]})
    assert booking["guest_id"] == sam["id"] and link["guest_id"] == robin["id"]
    assert (await local_mongo.guests.find_one({"id": sam["id"]})).get("email") == sam.get("email")
    # Losing the secondary profile after durable import must block an ACK retry.
    version = await local_mongo.exely_reservation_versions.find_one({"version_identity": current["provider_version_identity"]})
    await local_mongo.guests.delete_one({"id": robin["id"]})
    assert not await lifecycle._durable_readback(version)


@pytest.mark.live_mongo
async def test_manual_removal_of_imported_link_requires_review(local_mongo):
    booking = await _seed(local_mongo)
    await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    await local_mongo.booking_guests.delete_many({})
    booking = await local_mongo.bookings.find_one({"id": booking["id"]})
    with pytest.raises(ReadReservationError, match="MANUAL_MEMBERSHIP_REVIEW"):
        await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    assert await local_mongo.booking_guests.count_documents({}) == 0


@pytest.mark.live_mongo
async def test_rest_completion_cannot_rename_an_existing_soap_occupant(local_mongo):
    booking = await _seed(local_mongo)
    manifest = await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Robin")])
    booking = await local_mongo.bookings.find_one({"id": booking["id"]})
    with pytest.raises(ReadReservationError, match="SOURCE_CONFLICT"):
        await guest_roster.sync_room_roster(local_mongo, "tenant-a", booking, [_person("1", "Sam"), _person("2", "Morgan")], source="read_reservation_v1")
    assert await guest_roster.roster_readback(local_mongo, "tenant-a", booking["id"], manifest)
