"""Boundary coverage for the legacy agency portal's occupied-room queries."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "routers" / "agency_portal.py"


def _overlap_helper():
    tree = ast.parse(SOURCE.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_active_stay_overlap_filter")
    scope = {"__name__": "test_agency_portal_checkout_exclusive"}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["_active_stay_overlap_filter"]


def _matches(query, booking):
    """Small evaluator for the exact query shape used in portal counters."""
    if not booking["check_in"] < query["check_in"]["$lt"]:
        return False
    expression, requested_start = query["$expr"]["$gt"]
    assert expression == {"$substrBytes": ["$check_out", 0, 10]}
    return booking["check_out"][:10] > requested_start


def test_same_day_checkout_is_not_an_overlap():
    query = _overlap_helper()("2027-01-15", "2027-01-16")
    assert not _matches(query, {"check_in": "2027-01-12T14:00:00", "check_out": "2027-01-15T11:00:00"})


def test_all_real_night_overlaps_are_still_counted():
    query = _overlap_helper()("2027-01-15", "2027-01-18")
    assert _matches(query, {"check_in": "2027-01-14T14:00:00", "check_out": "2027-01-16T11:00:00"})
    assert _matches(query, {"check_in": "2027-01-15T14:00:00", "check_out": "2027-01-18T11:00:00"})
    assert _matches(query, {"check_in": "2027-01-16T14:00:00", "check_out": "2027-01-17T11:00:00"})
    assert not _matches(query, {"check_in": "2027-01-18T14:00:00", "check_out": "2027-01-19T11:00:00"})


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


def test_helper_uses_date_not_operational_checkout_hour():
    source = ast.unparse(next(n for n in ast.parse(SOURCE.read_text()).body
                              if isinstance(n, ast.FunctionDef) and n.name == "_active_stay_overlap_filter"))
    assert "$substrBytes" in source
    assert "check_out + 'T00:00:00'" in source
    assert "check_in + 'T00:00:00'" not in source
