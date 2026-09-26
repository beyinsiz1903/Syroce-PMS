def _foreign_payload(**changes):
    payload = {
        "guest_name": "Foreign Guest",
        "room_number": "208",
        "check_in": "2026-09-25T14:00:00",
        "nationality": "DE",
        "id_type": "foreign_identity_card",
        "id_number": "99123456789",
        "passport_number": "",
        "birth_date": "1990-01-01",
        "gender": "female",
    }
    payload.update(changes)
    return payload


def test_foreign_identity_card_uses_ykn_without_passport():
    from core.kbs_payload_validation import validate_kbs_payload

    assert validate_kbs_payload(_foreign_payload()) == (True, [])


def test_foreign_identity_card_does_not_require_birth_date_gender_or_name():
    from core.kbs_payload_validation import validate_kbs_payload

    assert validate_kbs_payload(
        _foreign_payload(guest_name="", birth_date="", gender="")
    ) == (True, [])


def test_foreign_identity_card_requires_valid_eleven_digit_ykn():
    from core.kbs_payload_validation import validate_kbs_payload

    ok, missing = validate_kbs_payload(_foreign_payload(id_number="123"))
    assert ok is False
    assert missing == ["id_number_invalid"]


def test_regular_foreign_guest_still_requires_passport():
    from core.kbs_payload_validation import validate_kbs_payload

    ok, missing = validate_kbs_payload(
        _foreign_payload(id_type="passport", id_number="", passport_number="")
    )
    assert ok is False
    assert missing == ["passport_number"]
