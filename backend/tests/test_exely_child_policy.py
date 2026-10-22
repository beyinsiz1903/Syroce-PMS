"""Child ages, arrival-date boundaries and operator-attested Exely pricing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from domains.channel_manager import unified_rate_manager_router as rates
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.pms_lifecycle import _booking_fields
from domains.channel_manager.providers.exely.response_parser import parse_read_rs
from models.schemas.bookings import BookingCreate


def reservation(counts, *, arrival="2030-07-01", guests=""):
    xml = f'''<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>
    <OTA_ResRetrieveRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/>
    <ReservationsList><HotelReservation ResStatus="Commit" CreateDateTime="2030-01-01T00:00:00Z" LastModifyDateTime="2030-01-02T00:00:00Z">
    <UniqueID Type="14" ID="synthetic-family"/><RoomStays><RoomStay IndexNumber="0">
    <RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes><RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans>
    <GuestCounts>{counts}</GuestCounts><TimeSpan Start="{arrival}T14:00:00" End="2030-07-03T12:00:00"/>
    <Total AmountAfterTax="440" CurrencyCode="EUR"/></RoomStay></RoomStays>{guests}
    <ResGlobalInfo><Total AmountAfterTax="440" CurrencyCode="EUR"/></ResGlobalInfo>
    </HotelReservation></ReservationsList></OTA_ResRetrieveRS></s:Body></s:Envelope>'''
    return parse_read_rs(xml.encode())["reservations"][0]


def booking(raw):
    canonical = normalize_reservation(raw)
    return _booking_fields(
        tenant_id="tenant-a", property_id="synthetic-property",
        reservation={**raw, "external_id": raw["reservation_id"]},
        version_doc={"provider_version_key": "2030-01-02T00:00:00Z"},
        room=canonical["rooms"][0], mapping={"pms_room_type": "Standard"},
        slot=0, guest_id="guest-a", booking_id="booking-a",
    )


def test_multiple_child_ages_survive_parser_canonical_and_pms_without_repricing():
    raw = reservation('''<GuestCount AgeQualifyingCode="10" Count="2"/>
        <GuestCount AgeQualifyingCode="8" Count="1" Age="0"/>
        <GuestCount AgeQualifyingCode="8" Count="2" Age="7"/>
        <GuestCount AgeQualifyingCode="8" Count="1" Age="17"/>''')
    assert raw["total_guests"] == 6
    result = booking(raw)
    assert result["adults"] == 2 and result["children"] == 4
    assert result["children_ages"] == [0, 7, 7, 17]
    assert result["children_ages_complete"] is True
    assert result["total_amount"] == 440 and result["currency"] == "EUR"
    assert result["paid_amount"] == 0  # An age/policy is not evidence of payment.


@pytest.mark.parametrize("arrival,age", [("2030-06-30", 6), ("2030-07-01", 7), ("2030-07-02", 7)])
def test_birthday_uses_completed_years_on_arrival_not_booking_today_or_checkout(arrival, age):
    guests = '''<ResGuests><ResGuest ResGuestRPH="child-1"><Profiles><ProfileInfo><Profile>
      <Customer BirthDate="2023-07-01"/></Profile></ProfileInfo></Profiles></ResGuest></ResGuests>'''
    raw = reservation('<GuestCount AgeQualifyingCode="10" Count="2"/><GuestCount AgeQualifyingCode="8" Count="1" ResGuestRPH="child-1"/>', arrival=arrival, guests=guests)
    assert booking(raw)["children_ages"] == [age]


@pytest.mark.parametrize("age", ["", "7.5", "-1", "18", "unknown"])
def test_absent_or_invalid_child_age_is_unknown_not_zero(age):
    raw = reservation(f'<GuestCount AgeQualifyingCode="10" Count="2"/><GuestCount AgeQualifyingCode="8" Count="1" Age="{age}"/>')
    result = booking(raw)
    assert result["children"] == 1
    assert result["children_ages"] == []
    assert result["children_ages_complete"] is False
    assert result["total_amount"] == 440


def test_one_child_profile_cannot_supply_an_age_for_two_unidentified_children():
    guests = '''<ResGuests><ResGuest ResGuestRPH="child-1"><Profiles><ProfileInfo><Profile>
      <Customer BirthDate="2023-07-01"/></Profile></ProfileInfo></Profiles></ResGuest></ResGuests>'''
    result = booking(reservation('<GuestCount AgeQualifyingCode="8" Count="2" ResGuestRPH="child-1"/>', guests=guests))
    assert result["adults"] == 0 and result["children"] == 2
    assert result["children_ages"] == []
    assert result["children_ages_complete"] is False


def test_payload_without_any_guest_counts_retains_the_legacy_adult_fallback():
    result = booking(reservation(""))
    assert result["adults"] == 1 and result["children"] == 0


def test_provider_bed_label_uses_explicit_age_without_guessing_a_label_mapping():
    result = booking(reservation('<GuestCount AgeQualifyingCode="AdultBed" Count="2"/><GuestCount AgeQualifyingCode="ChildBed" Age="8" Count="1"/>'))
    assert result["adults"] == 2 and result["children"] == 1
    assert result["children_ages"] == [8]


@pytest.mark.parametrize("age", [0, 2, 3, 6, 7, 17])
def test_explicit_child_age_is_preserved_even_in_an_adult_bed(age):
    result = booking(reservation(f'<GuestCount AgeQualifyingCode="AdultBed" Count="2"/><GuestCount AgeQualifyingCode="AdultBed" Age="{age}" Count="1"/>'))
    assert result["adults"] == 2 and result["children"] == 1
    assert result["children_ages"] == [age]
    assert result["guests_count"] == 3
    assert result["total_amount"] == 440


def test_conflicting_demographic_adult_code_and_explicit_child_age_is_held():
    with pytest.raises(RuntimeError, match="EXELY_GUEST_COUNT_CODE_UNSUPPORTED"):
        booking(reservation('<GuestCount AgeQualifyingCode="10" Age="6" Count="1"/>'))


def test_unknown_guest_count_code_without_age_cannot_silently_lose_a_guest_and_ack():
    raw = reservation('<GuestCount AgeQualifyingCode="AdultBed" Count="2"/><GuestCount AgeQualifyingCode="unrecognized-bed" Count="1"/>')
    with pytest.raises(RuntimeError, match="EXELY_GUEST_COUNT_CODE_UNSUPPORTED"):
        booking(raw)


def test_adult_only_payload_shape_is_unchanged_for_existing_dedup_hashes():
    raw = reservation('<GuestCount AgeQualifyingCode="AdultBed" Count="2"/>')
    assert "children_ages" not in raw["rooms"][0]
    assert "children_ages" not in normalize_reservation(raw)["rooms"][0]
    assert "unrecognized_guest_count_codes" not in normalize_reservation(raw)["rooms"][0]


def test_child_payload_without_new_age_evidence_keeps_its_existing_dedup_shape():
    raw = reservation('<GuestCount AgeQualifyingCode="AdultBed" Count="2"/><GuestCount AgeQualifyingCode="8" Count="1"/>')
    assert "children_ages" not in raw["rooms"][0]
    assert booking(raw)["children_ages_complete"] is False


@pytest.mark.parametrize("age", [True, 6.5, -1, 18])
def test_preview_and_policy_api_reject_invalid_ages_before_coercion(age):
    with pytest.raises(ValidationError):
        rates.OccupancyPricePreviewRequest(room_type_code="STD", base_nightly_rate=100, children_ages=[age])
    with pytest.raises(ValidationError):
        rates.ChildAgeBandItem(min_age=0, max_age=age, pricing_mode="free")
    with pytest.raises(ValidationError):
        BookingCreate(guest_id="guest-a", room_id="room-a", check_in="2030-07-01", check_out="2030-07-03", guests_count=3, children=1, children_ages=[age], total_amount=100)


def test_guest_age_metadata_cannot_expand_an_unbounded_provider_count():
    with pytest.raises(ValueError, match="EXELY_GUEST_COUNT_LIMIT"):
        reservation('<GuestCount AgeQualifyingCode="8" Age="7" Count="2147483647"/>')


async def test_invalid_later_child_policy_cannot_partially_save_a_batch(monkeypatch):
    store = SimpleNamespace(find_one=AsyncMock(), update_one=AsyncMock())
    class DB:
        def __getitem__(self, name): return store
    monkeypatch.setattr(rates, "db", DB())
    monkeypatch.setattr(rates, "_detect_active_provider", AsyncMock(return_value={"provider": "exely"}))
    request = rates.PricingSettingsRequest(settings=[
        rates.PricingSettingItem(room_type_code="STD", pricing_type="per_person", currency="TRY"),
        rates.PricingSettingItem(room_type_code="FAMILY", pricing_type="per_person", currency="TRY", child_age_bands=[
            rates.ChildAgeBandItem(min_age=0, max_age=6, pricing_mode="free"),
            rates.ChildAgeBandItem(min_age=6, max_age=17, pricing_mode="fixed", value=50),
        ]),
    ])
    with pytest.raises(HTTPException) as error:
        await rates.update_pricing_settings(request, current_user=SimpleNamespace(tenant_id="tenant-a", id="user-a"), _perm=None)
    assert error.value.status_code == 400
    store.find_one.assert_not_awaited()
    store.update_one.assert_not_awaited()


def test_legacy_auto_verified_exely_record_is_not_operator_verification():
    doc = {"room_type_code": "STD", "pricing_type": "per_person", "provider_pricing_verified": True}
    _, rules = rates._pricing_payload([doc], provider="exely")
    assert rules["STD"]["provider_pricing_verified"] is False
    assert rules["STD"]["provider_sync_state"] == "MANUAL_CONFIGURATION_REQUIRED"
    _, confirmed = rates._pricing_payload([{**doc, "provider_pricing_verification_source": "operator"}], provider="exely")
    assert confirmed["STD"]["provider_pricing_verified"] is True


@pytest.mark.parametrize("verified", [False, True])
async def test_saving_an_exely_policy_does_not_invent_a_provider_confirmation(monkeypatch, verified):
    store = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
    class DB:
        def __getitem__(self, name):
            assert name == "pricing_settings"
            return store
    monkeypatch.setattr(rates, "db", DB())
    monkeypatch.setattr(rates, "_detect_active_provider", AsyncMock(return_value={"provider": "exely"}))
    monkeypatch.setattr(rates, "log_audit_event", AsyncMock())
    request = rates.PricingSettingsRequest(settings=[rates.PricingSettingItem(
        room_type_code="STD", pricing_type="per_person", currency="TRY", provider_pricing_verified=verified,
    )])
    await rates.update_pricing_settings(request, current_user=SimpleNamespace(tenant_id="tenant-a", id="user-a"), _perm=None)
    query, update = store.update_one.await_args.args
    assert query == {"tenant_id": "tenant-a", "room_type_code": "STD"}
    assert update["$set"]["provider_pricing_verified"] is verified
    assert update["$set"]["provider_pricing_verification_source"] == ("operator" if verified else None)


def test_exely_person_policy_gate_accepts_only_explicit_parity_and_resolves_mapping_aliases():
    mapping = [{"pms_room_type": "Standard", "exely_room_code": "ARI-STD", "pms_api_room_code": "API-STD"}]
    rule = {"room_type_code": "ARI-STD", "pricing_type": "per_person", "provider_pricing_verified": True}
    assert rates._unsafe_exely_room_types(["API-STD"], mapping, [rule]) == ["API-STD"]
    assert rates._unsafe_exely_room_types(["API-STD"], mapping, [{**rule, "provider_pricing_verification_source": "operator"}]) == []
    assert rates._unsafe_exely_room_types(["API-STD"], mapping, [{**rule, "pricing_type": "per_room"}]) == []


def test_invalid_stored_child_policy_cannot_turn_into_a_verified_free_default():
    doc = {"room_type_code": "STD", "pricing_type": "per_person", "child_free_age_max": 6.5,
           "provider_pricing_verified": True, "provider_pricing_verification_source": "operator"}
    _, rules = rates._pricing_payload([doc], provider="exely")
    assert rules["STD"]["policy_invalid"] is True
    assert rules["STD"]["provider_pricing_verified"] is False
    assert rules["STD"]["provider_sync_state"] == "INVALID_POLICY"
    assert rates._unsafe_exely_room_types(["STD"], [], [doc]) == ["STD"]


async def test_unverified_child_policy_blocks_unified_rate_write_before_local_or_remote_mutation(monkeypatch):
    class Cursor:
        def __init__(self, rows): self.rows = rows
        async def to_list(self, _limit): return self.rows
    docs = [{"room_type_code": "STD", "pricing_type": "per_person", "provider_pricing_verified": True}]
    database = SimpleNamespace(
        pricing_settings=SimpleNamespace(find=lambda *_args: Cursor(docs)),
        exely_room_mappings=SimpleNamespace(find=lambda *_args: Cursor([
            {"exely_room_code": "STD", "exely_rate_plan_code": "BAR", "pms_room_type": "STD"},
        ])),
    )
    monkeypatch.setattr(rates, "db", database)
    monkeypatch.setattr(rates, "_detect_active_provider", AsyncMock(return_value={"provider": "exely", "connection": {"room_types": [{"code": "STD"}]}}))
    monkeypatch.setattr(rates, "require_tenant_module", AsyncMock())
    monkeypatch.setattr(rates, "_ari_write_block_for_targets", lambda *_args: "")
    push = AsyncMock()
    monkeypatch.setattr(rates, "_push_to_exely", push)
    request = rates.UnifiedBulkUpdateRequest(room_type_codes=["STD"], rate_plan_codes=["BAR"], start_date="2030-07-01", end_date="2030-07-02", rate=100, update_fields=["rate"])
    with pytest.raises(HTTPException) as error:
        await rates.unified_bulk_grid_update(request, current_user=SimpleNamespace(tenant_id="tenant-a", id="user-a"), _perm=None)
    assert error.value.status_code == 409
    push.assert_not_awaited()
