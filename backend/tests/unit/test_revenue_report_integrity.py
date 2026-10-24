from datetime import date
from decimal import Decimal

import pytest

from modules.pms_core.report_room_types import RoomTypeLabels
from modules.pms_core.revenue_categories import charge_category, revenue_department
from modules.pms_core.revenue_report import build_revenue_report, charge_breakdown

DAY = date(2026, 9, 5)


def row(**changes):
    return {"id": "charge", "report_source": "folio", "business_date": DAY.isoformat(), "charge_category": "room", "currency": "TRY", **changes}


@pytest.mark.parametrize("fields", [
    {"amount": 100, "vat_amount": 10, "tax_amount": 2, "total": 112},
    {"amount": 100, "tax_amount": 12, "tax_breakdown": {"vat": 10, "accommodation_tax": 2}, "total": 112},
])
def test_manual_and_night_audit_tax_schemas_reconcile_identically(fields):
    values = charge_breakdown(row(**fields))
    assert (values["net"], values["vat"], values["city_tax"], values["other_tax"], values["difference"]) == (100, 10, 2, 0, 0)
    assert not values["issues"]


def test_explicit_zero_never_falls_back_to_another_nonzero_field():
    values = charge_breakdown(row(amount=1, total=0))
    assert values["total"] == 0 and values["difference"] == -1
    assert values["net"] is None and values["tax_unknown"]
    values = charge_breakdown(row(amount=0, total=112, tax_amount=2, vat_amount=10))
    assert values["net"] == 0 and values["difference"] == 100


def test_extra_unit_price_is_not_misread_as_line_net_or_guessed_tax():
    values = charge_breakdown(row(report_source="extra", amount=50, quantity=2, total=100))
    assert values["total"] == 100
    assert values["net"] is values["vat"] is values["city_tax"] is None


def test_pos_aggregate_tax_is_not_called_accommodation_tax_and_refunds_keep_signs():
    values = charge_breakdown(row(report_source="pos", total=-112, report_refund=True, tax_amount=12, vat_amount=10, report_tax_kind="aggregate"))
    assert (values["net"], values["vat"], values["city_tax"], values["other_tax"]) == (-100, -10, None, -2)
    assert sum(values[field] or 0 for field in ("net", "vat", "city_tax", "other_tax")) == values["total"]


def test_unallocated_pos_tax_is_not_fabricated_as_zero_vat_or_city_tax():
    values = charge_breakdown(row(report_source="pos", total=112, tax_amount=12, report_tax_kind="aggregate"))
    assert (values["net"], values["vat"], values["city_tax"], values["other_tax"]) == (100, None, None, 12)


def test_missing_extra_total_uses_unit_quantity_but_explicit_zero_total_wins():
    from modules.pms_core.reporting_ledger import charge_amount

    assert charge_amount(row(report_source="extra", charge_amount=50, quantity=2)) == 100
    assert charge_amount(row(report_source="extra", charge_amount=50, quantity=0)) == 0
    assert charge_amount(row(report_source="extra", charge_amount=50, quantity=2, total=0)) == 0


def test_subtotal_discount_difference_is_not_silently_fixed():
    values = charge_breakdown(row(subtotal=120, discount_amount=5, amount=100, total=112, vat_amount=10, tax_amount=2))
    assert values["subtotal"] == 120 and values["discount"] == 5
    assert "Ara toplam − indirim ile net uyuşmuyor" in values["issues"]
    data = build_revenue_report([row(subtotal=120, discount_amount=5, amount=100, total=112, vat_amount=10, tax_amount=2)], DAY, DAY)
    assert data["totals_by_currency"]["TRY"]["net"] == 100  # original evidence retained
    assert data["totals_by_currency"]["TRY"]["verified_net"] is None


@pytest.mark.parametrize("raw,expected,department", [("mini_bar", "minibar", "minibar"), ("food_and_beverage", "fnb", "fnb"), ("room_charge", "room", "room"), ("upsell", "unclassified", "unclassified"), ("extra", "unclassified", "unclassified"), ("unknown-old-category", "unclassified", "unclassified"), ("alcoholic_beverage", "alcohol", "fnb")])
def test_taxonomy_is_shared_and_does_not_guess_upsell_department(raw, expected, department):
    assert charge_category({"category": raw}) == expected
    assert revenue_department(expected) == department


def test_service_category_can_explicitly_identify_an_upsell():
    assert charge_category({"category": "upsell", "service_category": "spa"}) == "spa"


def test_detail_categories_preserve_custom_keys_without_undoing_known_aliases():
    assert charge_category({"category": "hotel-service-51"}, preserve_unknown=True) == "hotel-service-51"
    assert charge_category({"category": "mini_bar"}, preserve_unknown=True) == "minibar"
    assert charge_category({"category": "food_and_beverage"}, preserve_unknown=True) == "fnb"
    assert charge_category({"category": "upsell"}, preserve_unknown=True) == "unclassified"


def test_report_rounding_does_not_erase_evidence_needed_by_allocation_guards():
    from modules.pms_core.reporting_ledger import charge_amount

    source = row(total="6000.001")
    assert charge_amount(source) == 6000
    assert charge_amount(source, round_to_cents=False) == 6000.001
    assert source["total"] == "6000.001"


def test_one_scope_reconciles_categories_trend_department_and_native_currency_totals():
    data = build_revenue_report([
        row(amount=100, total=112, tax_amount=12, tax_breakdown={"vat": 10, "accommodation_tax": 2}),
        row(id="minibar", charge_category="mini_bar", total=20),
        row(id="fnb", charge_category="food_beverage", total=-5),
        row(id="eur", currency="EUR", total=10),
        row(id="outside", business_date="2026-09-06", total=999999),
    ], DAY, DAY)
    assert data["totals"]["total"] is None
    assert {code: values["total"] for code, values in data["totals_by_currency"].items()} == {"EUR": 10, "TRY": 127}
    assert data["departments_by_currency"]["fnb"] == {"TRY": -5}
    assert data["departments_by_currency"]["minibar"] == {"TRY": 20}
    assert data["revenue_trend"][0]["revenue_by_currency"] == {"EUR": 10, "TRY": 127}
    assert data["totals_by_currency"]["TRY"]["net"] is None
    assert data["reconciliation"]["tax_unknown_count"] == 3


def test_high_volume_cent_rounding_and_complete_date_series():
    data = build_revenue_report([row(total="2.675", amount="2.675", vat_amount=0, tax_amount=0) for _ in range(15001)], DAY, date(2026, 9, 6))
    assert data["totals_by_currency"]["TRY"]["total"] == float(Decimal("2.68") * 15001)
    assert data["totals_by_currency"]["TRY"]["difference"] == 0
    assert data["revenue_trend"][1]["revenue_by_currency"] == {}


def test_catalog_ids_case_variants_and_orphans_have_stable_labels_without_changing_input():
    uuid = "b3c7bb47-1234-1234-1234-123456789012"
    labels = RoomTypeLabels([{"id": uuid, "name": "Standard"}], [{"room_type": "standard"}])
    assert labels(uuid) == labels("standard") == "Standard"
    assert labels("deadbeef-1234-1234-1234-123456789012") == "Envanter dışı oda tipi"
    booking = {"room_id": "suite"}
    assert labels.normalize([booking]) == [booking]  # preserve assigned-room fallback
