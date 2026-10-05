from core.kbs_payload_validation import validate_kbs_payload


def _snapshot(**overrides):
    payload = {
        "guest_name": "Test Misafir",
        "room_number": "109",
        "birth_date": "1990-01-01",
        "check_in": "2026-08-23T14:00:00+03:00",
        "check_out": "2026-08-24T11:00:00+03:00",
        "nationality": "TC",
        "id_number": "10000000146",
        "passport_number": "",
    }
    payload.update(overrides)
    return payload


def test_turkish_nationality_aliases_use_identity_number():
    for nationality in ("TC", "TR", "TUR", "Türkiye", "TURKIYE"):
        ok, missing = validate_kbs_payload(_snapshot(nationality=nationality))
        assert ok, (nationality, missing)


def test_turkish_guest_with_valid_identity_number_does_not_require_birth_date():
    ok, missing = validate_kbs_payload(_snapshot(birth_date=""))

    assert ok
    assert "birth_date" not in missing


def test_room_number_is_required_before_enqueue():
    ok, missing = validate_kbs_payload(_snapshot(room_number=""))

    assert not ok
    assert "room_number" in missing


def test_foreign_guest_requires_passport():
    ok, missing = validate_kbs_payload(
        _snapshot(
            nationality="DE",
            id_number="",
            passport_number="",
            gender="female",
            birth_place="Berlin",
        )
    )
    assert not ok
    assert "passport_number" in missing


def test_foreign_guest_still_requires_birth_date():
    ok, missing = validate_kbs_payload(
        _snapshot(
            nationality="DE",
            id_number="",
            passport_number="C01X",
            birth_date="",
            gender="female",
            birth_place="Berlin",
        )
    )

    assert not ok
    assert "birth_date" in missing


def test_foreign_checkin_requires_gender_but_not_birth_place():
    ok, missing = validate_kbs_payload(
        _snapshot(
            nationality="DE",
            id_number="",
            passport_number="C01X",
            gender="",
            birth_place="",
        )
    )
    assert not ok
    assert "gender" in missing
    assert "birth_place" not in missing


def test_turkish_checkin_matches_official_contract_without_name_or_checkout():
    ok, missing = validate_kbs_payload(
        _snapshot(guest_name="", check_out=""),
        "checkin",
    )

    assert ok, missing


def test_checkout_only_requires_identity_and_checkout_time():
    ok, missing = validate_kbs_payload(
        _snapshot(guest_name="", room_number="", check_in=""),
        "checkout",
    )

    assert ok, missing


def test_foreign_checkout_does_not_require_entry_only_fields():
    ok, missing = validate_kbs_payload(
        _snapshot(
            nationality="DE",
            id_number="",
            passport_number="C01X",
            guest_name="",
            room_number="",
            check_in="",
            birth_date="",
            gender="",
            birth_place="",
        ),
        "checkout",
    )

    assert ok, missing


def test_checkout_requires_actual_checkout_time():
    ok, missing = validate_kbs_payload(_snapshot(check_out=""), "checkout")

    assert not ok
    assert "check_out" in missing
