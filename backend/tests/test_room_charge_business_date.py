"""Legacy room charges must stay reconcilable using their posting date."""

from routers.reservation_detail import _room_charge_business_date


def test_room_charge_business_date_prefers_accounting_dates():
    assert _room_charge_business_date(
        {
            "business_date": "2026-10-02",
            "night_audit_date": "2026-10-01",
            "date": "2026-09-30T23:00:00+00:00",
        }
    ).isoformat() == "2026-10-02"


def test_room_charge_business_date_falls_back_to_legacy_posting_date():
    assert _room_charge_business_date({"date": "2026-10-02T08:30:00+00:00"}).isoformat() == "2026-10-02"
