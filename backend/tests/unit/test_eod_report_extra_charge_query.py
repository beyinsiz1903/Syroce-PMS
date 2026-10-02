"""EOD extra-charge selection must follow the PMS accounting day."""

from routers.eod_report import _active_extra_charge_query


def test_eod_extra_charge_query_excludes_voided_rows_and_uses_business_date():
    query = _active_extra_charge_query("tenant-1", "2026-10-02")

    assert query["tenant_id"] == "tenant-1"
    assert query["voided"] == {"$ne": True}
    assert query["$or"][0] == {"business_date": "2026-10-02"}


def test_eod_extra_charge_query_uses_timestamps_only_for_legacy_rows():
    query = _active_extra_charge_query("tenant-1", "2026-10-02")
    legacy_clause = query["$or"][1]

    assert {"business_date": {"$exists": False}} in legacy_clause["$and"][0]["$or"]
    assert {"created_at": {"$regex": "^2026-10-02"}} in legacy_clause["$and"][1]["$or"]
