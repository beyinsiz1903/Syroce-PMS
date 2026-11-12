"""Tax detail must reconcile immutable department and room snapshots."""

from copy import deepcopy

import pytest

from domains.pms.pos_fnb.folio_lines import checkout_lines
from modules.pms_core.folio_detail_service import FolioDetailService


def test_merged_pos_sale_shows_vat_once_without_mutating_source():
    charges = checkout_lines({
        "amount": 132, "tax_amount": 12,
        "order_items": [
            {"item_name": "Su", "quantity": 1, "total": 40, "tax_rate": .1},
            {"item_name": "Su", "quantity": 2, "total": 80, "tax_rate": .1},
        ],
    })
    for row in charges:
        row["currency"] = "TRY"
    original = deepcopy(charges)

    result = FolioDetailService()._calculate_line_tax_breakdown(charges)

    assert result["totals"] == {"net": 120, "tax": 12, "gross": 132}
    assert [line["tax_amount"] for line in result["lines"]] == [4, 8]
    assert result["by_tax_rate"]["10%"] == {
        "rate": 10, "net": 120, "tax": 12, "gross": 132, "count": 2,
    }
    assert all(line["currency"] == "TRY" for line in result["lines"])
    assert charges == original


@pytest.mark.parametrize("tax_fields", [
    {"tax_amount": 12},  # legacy aggregate
    {"vat_amount": 10, "tax_amount": 2},  # separate VAT/other tax
    {"vat_amount": 10, "tax_amount": 2, "tax_breakdown": {"vat": 10, "accommodation_tax": 2}},
    {"vat_amount": 10, "tax_amount": 12, "tax_breakdown": {"vat": 10, "accommodation_tax": 2}},
    {"tax_amount": 12, "tax_breakdown": {"vat": 10, "accommodation_tax": 2}},
])
def test_room_and_department_tax_schemas_do_not_double_count(tax_fields):
    result = FolioDetailService()._calculate_line_tax_breakdown([
        {"amount": 100, "total": 112, "tax_rate": .12, **tax_fields},
        {"amount": 20, "total": 22, "vat_amount": 2, "tax_amount": 0, "voided": True},
    ])
    assert result["totals"] == {"net": 100, "tax": 12, "gross": 112}
    assert result["lines"][0]["tax_rate"] == 12
    assert len(result["lines"]) == 1


def test_spa_service_comp_and_refund_keep_signed_snapshot_tax():
    result = FolioDetailService()._calculate_line_tax_breakdown([
        {"amount": 1250, "total": 1500, "vat_amount": 250, "tax_amount": 0, "tax_breakdown": {"vat": 250}},
        {"amount": 0, "total": 0, "vat_amount": 0, "tax_amount": 0, "tax_breakdown": {"vat": 0}},
        {"amount": -100, "total": -120, "vat_amount": -20, "tax_amount": 0, "tax_breakdown": {"vat": -20}},
    ])
    assert result["totals"] == {"net": 1150, "tax": 230, "gross": 1380}
    assert result["by_tax_rate"]["20%"]["tax"] == 230
    assert result["lines"][1]["tax_rate"] == 0
