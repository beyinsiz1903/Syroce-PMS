"""Non-destructive classification of local legacy/demo agency cards.

Names alone are never enough to classify a real partner as demo data.
Old seeded cards predate is_demo: require their complete seed fingerprint.
"""

import re

LEGACY_DEMO_IDENTITIES = {
    ("Antalya Sun Tours", "mehmet@antsunsuntours.com", "+905551001001", "Premium partner since 2020"),
    ("Blue Horizon Travel", "elena@bluehorizon.eu", "+442071234567", "UK market specialist"),
    ("Deutsche Reisen GmbH", "mueller@deutschereisen.de", "+4930123456", "German market, high volume"),
    ("Orient Express Tours", "ayse@orientexpress.com.tr", "+905552002002", "Domestic tours, corporate groups"),
    ("Riviera Holiday Agency", "pierre@rivieraholiday.fr", "+33142123456", "French Riviera clientele"),
}


def test_or_demo(agency: dict) -> bool:
    fingerprint = tuple(str(agency.get(key) or "") for key in ("name", "contact_email", "contact_phone", "notes"))
    return (agency.get("is_test") is True or agency.get("is_demo") is True
            or agency.get("record_source") == "demo_seed" or fingerprint in LEGACY_DEMO_IDENTITIES
            or bool(re.match(r"^\s*[=+@-]|^TEST_", str(agency.get("name") or ""), re.IGNORECASE)))


def archived_agency(agency: dict) -> bool:
    return agency.get("status") in {"inactive", "disabled", "deleted", "migrated"} or test_or_demo(agency)


def readonly_finance(agency: dict) -> bool:
    # Inactive real partners must still be able to settle historical debt.
    return agency.get("status") in {"deleted", "migrated"} or test_or_demo(agency)
