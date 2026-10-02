from routers.reports_pkg.night_audit import _night_audit_charge_query


def test_night_audit_charge_query_scopes_idempotency_to_tenant_folio_and_business_date():
    assert _night_audit_charge_query("tenant-a", "booking-a", "folio-a", "2026-10-02", "room") == {
        "tenant_id": "tenant-a",
        "booking_id": "booking-a",
        "folio_id": "folio-a",
        "business_date": "2026-10-02",
        "charge_category": "room",
        "voided": {"$ne": True},
    }


def test_voided_night_audit_charge_does_not_block_a_correct_reposting():
    query = _night_audit_charge_query("tenant-a", "booking-a", "folio-a", "2026-10-02", "tax")

    assert query["voided"] == {"$ne": True}
    assert query["charge_category"] == "tax"
