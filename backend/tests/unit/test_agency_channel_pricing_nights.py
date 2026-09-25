"""Regression coverage for calendar-night totals and agency commission.

Execute the actual arithmetic from each handler without loading DB services.
This intentionally does not claim to test persistence or HTTP wiring.
"""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("relative_path,function_name", [
    ("routers/agency_portal.py", "agency_portal_create_reservation"),
    ("routers/marketplace_b2b.py", "agency_create_reservation"),
    ("routers/b2b_api/booking_engine.py", "_b2b_create_reservation_impl"),
])
@pytest.mark.parametrize("arrival,departure,nights", [
    ("2026-09-19", "2026-09-20", 1),
    ("2026-09-19", "2026-09-21", 2),
    ("2026-09-19", "2026-09-26", 7),
    ("2028-02-28", "2028-03-01", 2),
    ("2026-12-31", "2027-01-02", 2),
])
def test_calendar_nights_total_and_commission(relative_path, function_name, arrival, departure, nights):
    source = Path(__file__).resolve().parents[2] / relative_path
    tree = ast.parse(source.read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
              and node.name == function_name)
    names = {"nights", "public_unit_price", "server_total", "total", "commission_amount", "net_to_hotel"}
    expressions = sorted([
        node for node in ast.walk(fn) if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
    ], key=lambda node: node.lineno)
    scope = {
        "ci": datetime.fromisoformat(arrival + "T14:00:00+00:00"),
        "co": datetime.fromisoformat(departure + "T11:00:00+00:00"),
        "data": SimpleNamespace(total_amount=0),
        "available_room": {"base_price": 1500},
        "ci_date": datetime.fromisoformat(arrival).date(),
        "co_date": datetime.fromisoformat(departure).date(),
        "rooms": [{"base_price": 1500}],
        "commission_rate": 10, "commission_pct": 10,
    }
    exec(compile(ast.Module(body=expressions, type_ignores=[]), str(source), "exec"), scope)
    assert scope["nights"] == nights
    assert scope["total"] == nights * 1500
    assert scope["commission_amount"] == nights * 150
    if "net_to_hotel" in scope:
        assert scope["net_to_hotel"] == nights * 1350
