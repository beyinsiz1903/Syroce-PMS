from core.import_bridge_service import _guest_identity_matches, _normalized_guest_name


def test_normalized_guest_name_handles_turkish_case_and_spacing():
    assert _normalized_guest_name("Mustafa Kaan ŞİMŞEK") == _normalized_guest_name(
        "mustafa kaan simsek"
    )


def test_shared_ota_contact_cannot_link_different_guests():
    cengiz = {"id": "guest-cengiz", "first_name": "CENGIZ", "last_name": "DIDIN"}

    assert not _guest_identity_matches(cengiz, "Mustafa Kaan ŞİMŞEK")


def test_matching_guest_can_be_reused_when_names_agree():
    mustafa = {"id": "guest-mustafa", "name": "Mustafa Kaan ŞİMŞEK"}

    assert _guest_identity_matches(mustafa, "mustafa kaan simsek")
