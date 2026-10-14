"""Boundary coverage for the legacy agency portal's occupied-room queries."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "routers" / "agency_portal.py"


def _overlap_helper():
    from core.stay_overlap import stay_overlap_filter

    return stay_overlap_filter


def _prefix(value):
    return str(value)[:10]


def _matches(query, booking):
    """Small evaluator for the exact query shape built by core.stay_overlap."""
    if not (booking["check_in"] < query["check_in"]["$lt"] and booking["check_out"] > query["check_out"]["$gt"]):
        return False
    arrival, departure = query["$expr"]["$and"]
    return _prefix(booking["check_in"]) < arrival["$lt"][1] and _prefix(booking["check_out"]) > departure["$gt"][1]


def test_same_day_checkout_is_not_an_overlap():
    query = _overlap_helper()("2027-01-15", "2027-01-16")
    assert not _matches(query, {"check_in": "2027-01-12T14:00:00", "check_out": "2027-01-15T11:00:00"})
    assert not _matches(query, {"check_in": "2027-01-12", "check_out": "2027-01-15"})


def test_pms_and_date_only_formats_follow_the_same_night_rule():
    query = _overlap_helper()("2026-10-15", "2026-10-17")
    for stored_in, stored_out in [
        ("2026-10-13T14:00:00+00:00", "2026-10-15T12:00:00+00:00"),
        ("2026-10-13T14:00:00", "2026-10-15T11:00:00"),
        ("2026-10-13", "2026-10-15"),
    ]:
        assert not _matches(query, {"check_in": stored_in, "check_out": stored_out})
        assert _matches(_overlap_helper()("2026-10-14", "2026-10-16"), {"check_in": stored_in, "check_out": stored_out})
    assert _matches(query, {"check_in": "2026-10-16", "check_out": "2026-10-18"})
    assert not _matches(query, {"check_in": "2026-10-17", "check_out": "2026-10-18"})


def test_all_real_night_overlaps_are_still_counted():
    query = _overlap_helper()("2027-01-15", "2027-01-18")
    assert _matches(query, {"check_in": "2027-01-14T14:00:00", "check_out": "2027-01-16T11:00:00"})
    assert _matches(query, {"check_in": "2027-01-15T14:00:00", "check_out": "2027-01-18T11:00:00"})
    assert _matches(query, {"check_in": "2027-01-16T14:00:00", "check_out": "2027-01-17T11:00:00"})
    assert not _matches(query, {"check_in": "2027-01-18T14:00:00", "check_out": "2027-01-19T11:00:00"})
    assert not _matches(query, {"check_in": "2027-01-18", "check_out": "2027-01-19"})


def test_every_legacy_portal_counter_uses_the_shared_half_open_helper():
    tree = ast.parse(SOURCE.read_text())
    targets = {
        "agency_portal_availability": 2,  # public availability + agency allotment
        "agency_portal_create_reservation": 2,  # room selection + write-time allotment
    }
    for endpoint_name, expected in targets.items():
        endpoint = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == endpoint_name)
        calls = [n for n in ast.walk(endpoint) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "_active_stay_overlap_filter"]
        assert len(calls) == expected


def test_helper_delegates_to_the_shared_date_based_filter():
    source = ast.unparse(next(n for n in ast.parse(SOURCE.read_text()).body
                              if isinstance(n, ast.FunctionDef) and n.name == "_active_stay_overlap_filter"))
    assert "stay_overlap_filter(check_in, check_out)" in source
    assert "T00:00:00" not in source
