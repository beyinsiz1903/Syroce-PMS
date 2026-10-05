from domains.channel_manager.ingest.normalizer import normalize_hotelrunner
from routers.hotel_services_pkg.invoices import (
    _agency_reservation_reference_from_sources,
    _invoice_note_with_agency_reference,
)


def test_hotelrunner_normalizer_keeps_agency_reservation_number():
    canonical = normalize_hotelrunner(
        {
            "hr_number": "R541873154",
            "provider_number": "5939348",
            "rooms": [],
        }
    )

    assert canonical["external_reservation_id"] == "R541873154"
    assert canonical["agency_reservation_number"] == "5939348"


def test_provider_number_wins_for_legacy_booking_reference():
    booking = {
        "external_reservation_id": "R541873154",
        "external_confirmation": "R541873154",
    }

    reference = _agency_reservation_reference_from_sources(
        booking,
        raw_payload={"provider_number": "5939348"},
    )

    assert reference == "5939348"


def test_agency_reference_is_added_once_to_invoice_note():
    assert _invoice_note_with_agency_reference(None, "5939348") == (
        "Acente rezervasyon no: 5939348"
    )
    assert _invoice_note_with_agency_reference("Özel not", "5939348") == (
        "Acente rezervasyon no: 5939348\nÖzel not"
    )
    assert _invoice_note_with_agency_reference(
        "Acente rezervasyon no: 5939348", "5939348"
    ) == "Acente rezervasyon no: 5939348"
