"""Exercise the portal's fallback pricing without importing live DB services."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "arrival,departure,expected_nights",
    [
        ("2026-09-19", "2026-09-20", 1),
        ("2026-09-19", "2026-09-21", 2),
        ("2026-09-19", "2026-09-26", 7),
        ("2028-02-28", "2028-03-01", 2),
        ("2026-12-31", "2027-01-02", 2),
    ],
)
@pytest.mark.parametrize("quoted_total", [0, 12345])
def test_portal_calendar_nights_and_existing_quote(arrival, departure, expected_nights, quoted_total):
    source = Path(__file__).resolve().parents[2] / "routers" / "agency_portal.py"
    tree = ast.parse(source.read_text())
    endpoint = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "agency_portal_create_reservation"
    )
    pricing = [
        node for node in endpoint.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id in {"nights", "total"}
                for target in node.targets)
    ]
    assert len(pricing) == 2
    scope = {
        "ci": datetime.fromisoformat(arrival + "T14:00:00+00:00"),
        "co": datetime.fromisoformat(departure + "T11:00:00+00:00"),
        "data": SimpleNamespace(total_amount=quoted_total),
        "available_room": {"base_price": 1500},
    }
    exec(compile(ast.Module(body=pricing, type_ignores=[]), str(source), "exec"), scope)
    assert scope["nights"] == expected_nights
    assert scope["total"] == (quoted_total or expected_nights * 1500)
