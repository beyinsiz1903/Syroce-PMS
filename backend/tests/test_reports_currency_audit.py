"""Read-only reporting acceptance: currencies, dates, partial debt and exports."""
import sys
from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from modules.pms_core.report_money import add_amount, rounded_totals, single_amount
from modules.pms_core.reporting_financials import effective_collection, effective_revenue_adjustment, reporting_collection_summary
from modules.pms_core.stay_night_metrics import calculate_stay_night_metrics, load_stay_night_metrics
from routers import report_scheduler
from routers.departments import reports
from routers.reports_pkg import flash_email, standard_reports


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.queries = []
        self.projections = []
        self.limits = []

    def find(self, query, projection=None):
        self.queries.append(query)
        self.projections.append(projection)
        return self

    async def to_list(self, limit):
        self.limits.append(limit)
        return self.rows[:limit] if limit is not None else self.rows

    async def find_one(self, query, _projection=None):
        self.queries.append(query)
        return next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)


USER = SimpleNamespace(tenant_id="tenant-A", role="admin")


@pytest.fixture
def report_db(monkeypatch):
    db = SimpleNamespace(**{key: Collection() for key in ("bookings", "folios", "companies", "payments", "folio_charges", "accounting_invoices", "purchase_orders", "extra_charges", "pos_orders", "pos_transactions", "pos_menu_transactions", "transactions", "cari_accounts", "cari_transactions", "city_ledger_accounts", "city_ledger_transactions")})
    monkeypatch.setattr(reports, "db", db)
    monkeypatch.setattr(reports, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-15"}))
    monkeypatch.setattr(reports, "_enforce", lambda *_: None)
    return db


async def workbook(response):
    content = b"".join([chunk if isinstance(chunk, bytes) else chunk.encode() async for chunk in response.body_iterator])
    assert content.startswith(b"PK")
    return load_workbook(BytesIO(content), data_only=False)


def booking(amount, currency, **fields):
    return {"check_in": "2026-10-01", "check_out": "2026-10-03", "status": "checked_in", "room_id": currency,
            "total_amount": amount, "currency": currency, "market_segment": "direct", **fields}


def test_currency_arithmetic_normalizes_tl_and_never_creates_mixed_scalar():
    totals = {}
    for code, amount in (("TL", "0.10"), ("try", "0.20"), ("EUR", "40.01")):
        add_amount(totals, code, amount)
    assert rounded_totals(totals) == {"EUR": 40.01, "TRY": .30}
    assert single_amount(totals) is None


def test_cash_report_deduplicates_retries_and_preserves_negative_collection_sign():
    payment = {"id": "a", "amount": -20, "reporting_amount": -20, "currency": "TRY", "method": "cash"}
    result = reporting_collection_summary([payment, {**payment, "id": "a"}])
    assert result["amount"] == -20 and result["payment_count"] == 1


def test_room_night_metrics_separate_currencies_without_changing_occupancy():
    rows = calculate_stay_night_metrics([booking(200, "TRY"), booking(40, "EUR")], [{"id": "TRY"}, {"id": "EUR"}], date(2026, 10, 1), date(2026, 10, 3))
    assert rows[0]["occupied_rooms"] == 2 and rows[0]["occupancy_rate"] == 100
    assert rows[0]["revenue_by_currency"] == {"EUR": 20, "TRY": 100}
    assert rows[0]["revenue"] is None and rows[0]["adr"] is None
    assert rows[0]["mixed_currency"] is True
    assert rows[2]["revenue"] == 0 and rows[2]["occupied_rooms"] == 0


def test_lagging_business_date_does_not_hide_actually_checked_in_room():
    rows = calculate_stay_night_metrics([booking(100, "TRY", checked_in_at="2026-10-15T10:00:00Z")],
        [{"id": "TRY"}], date(2026, 10, 1), date(2026, 10, 1), actual_only=True)
    assert rows[0]["occupied_rooms"] == 1 and rows[0]["revenue"] == 50


async def test_stay_night_loader_keeps_currency_and_does_not_truncate(monkeypatch):
    db = SimpleNamespace(rooms=Collection([{"id": "EUR"}]), bookings=Collection([booking(40, "EUR")]), room_blocks=Collection())
    rows = await load_stay_night_metrics(db, "tenant-A", date(2026, 10, 1), date(2026, 10, 1))
    assert rows[0]["revenue_by_currency"] == {"EUR": 20}
    assert db.bookings.projections[0]["currency"] == 1
    assert all(collection.limits == [None] for collection in vars(db).values())


async def test_market_api_and_excel_keep_currency_specific_revenue_and_adr(report_db):
    report_db.bookings.rows = [booking(200, "TRY"), booking(40, "EUR")]
    result = await reports.get_market_segment_report.__wrapped__("2026-10-01", "2026-10-15", USER)
    row = result["market_segments"]["direct"]
    assert row["revenue"] is None
    assert row["revenue_by_currency"] == {"EUR": 40, "TRY": 200}
    assert row["adr_by_currency"] == {"EUR": 20, "TRY": 100}
    for _ in range(2):
        wb = await workbook(await reports.export_market_segment_excel("2026-10-01", "2026-10-15", USER))
        assert list(wb.active.values)[1] == ("Segment", "Currency", "Bookings", "Nights", "Booked value", "Paid-night average", "Paid nights", "Invalid amounts")
        assert {row[6] for row in list(wb.active.values)[2:]} == {2}
        assert {row[1] for row in list(wb.active.values)[2:]} == {"TRY", "EUR"}


async def test_market_excel_treats_guest_controlled_labels_as_text(report_db):
    report_db.bookings.rows = [booking(100, "TRY", market_segment="=1+1", rate_type="=2+2")]
    wb = await workbook(await reports.export_market_segment_excel("2026-10-01", "2026-10-15", USER))
    assert wb.worksheets[0]["A3"].data_type == "s"
    assert wb.worksheets[1]["A3"].data_type == "s"


async def test_revenue_detail_excel_does_not_combine_same_product_in_different_currencies(report_db):
    report_db.bookings.rows = [booking(200, "TRY"), booking(40, "EUR")]
    wb = await workbook(await reports.export_revenue_detail_excel("2026-10-01", "2026-10-01", USER))
    rows = list(wb.active.values)
    assert rows[1] == ("Date", "Room Type", "Rate Code", "Currency", "Room Nights", "Booked Revenue", "ADR", "Sold Room Nights")
    assert {(row[3], row[5]) for row in rows[2:]} == {("TRY", 100), ("EUR", 20)}
    assert report_db.bookings.projections[0]["currency"] == 1


async def test_channel_export_groups_shares_within_each_currency_and_uses_business_day(report_db):
    report_db.bookings.rows = [booking(200, "TRY", channel="Direct"), booking(40, "EUR", channel="OTA"), booking(40, "EUR", channel="Direct")]
    wb = await workbook(await reports.export_channel_distribution_excel(current_user=USER))
    rows = list(wb.active.values)[2:]
    assert {(row[0], row[1], row[4]) for row in rows} == {("Direct", "TRY", 100), ("Direct", "EUR", 50), ("OTA", "EUR", 50)}
    assert report_db.bookings.queries[0]["$or"] == [
        {"check_in": {"$gte": "2026-09-16", "$lt": "2026-10-16"}},
        {"check_in": {"$gte": datetime(2026, 9, 16, tzinfo=UTC), "$lt": datetime(2026, 10, 16, tzinfo=UTC)}},
    ]


@pytest.mark.parametrize("handler", [reports.get_market_segment_report.__wrapped__, reports.export_revenue_detail_excel, reports.export_forecast_detail_excel, reports.export_channel_distribution_excel])
@pytest.mark.parametrize("start,end", [("2026-10-20", "2026-10-01"), ("invalid", "2026-10-01")])
async def test_report_ranges_are_rejected_as_validation_errors(report_db, handler, start, end):
    with pytest.raises(HTTPException) as exc:
        await handler(start, end, current_user=USER)
    assert exc.value.status_code == 422


async def test_company_aging_separates_two_currencies_for_one_company(report_db, monkeypatch):
    report_db.folios.rows = [{"id": "f1", "company_id": "c1", "currency": "TRY"}, {"id": "f2", "company_id": "c1", "currency": "EUR"}]
    report_db.companies.rows = [{"id": "c1", "tenant_id": "tenant-A", "name": "Company"}]
    monkeypatch.setattr(reports, "folio_snapshots", AsyncMock(return_value={"f1": {"currency": "TRY", "balance_by_currency": {"TRY": 100}}, "f2": {"currency": "EUR", "balance_by_currency": {"EUR": 20}}}))
    result = await reports._compute_company_aging("tenant-A")
    assert result["total_ar"] is None
    assert result["total_ar_by_currency"] == {"TRY": 100, "EUR": 20}
    assert result["company_count"] == 1 and len(result["companies"]) == 2
    wb = await workbook(await reports.export_company_aging_excel(USER))
    assert {row[2] for row in list(wb.active.values)[2:]} == {"TRY", "EUR"}


async def test_company_aging_cannot_export_an_incomplete_balance_as_success(report_db, monkeypatch):
    report_db.folios.rows = [{"id": "failed", "company_id": "c1"}]
    monkeypatch.setattr(reports, "folio_snapshots", AsyncMock(side_effect=RuntimeError("unavailable")))
    result = await reports._compute_company_aging("tenant-A")
    assert not result["complete"] and result["total_ar"] is None
    with pytest.raises(HTTPException) as exc:
        await reports.export_company_aging_excel(USER)
    assert exc.value.status_code == 503


async def test_company_aging_keeps_debt_even_when_company_metadata_is_missing(report_db, monkeypatch):
    report_db.folios.rows = [{"id": "f1", "company_id": "deleted-company", "currency": "EUR"}]
    monkeypatch.setattr(reports, "folio_snapshots", AsyncMock(return_value={"f1": {"currency": "EUR", "balance_by_currency": {"EUR": 42.5}}}))
    result = await reports._compute_company_aging("tenant-A")
    assert result["total_ar_by_currency"] == {"EUR": 42.5}
    assert result["companies"][0]["company_name"] == "Şirket kaydı bulunamadı"


async def test_finance_snapshot_never_mixes_debt_or_substitutes_partial_invoice_face_value(report_db, monkeypatch):
    report_db.folios.rows = [{"id": "f1", "currency": "TRY"}, {"id": "f2", "currency": "EUR"}]
    report_db.accounting_invoices.rows = [{"currency": "TRY", "total": 100, "amount_paid": 40}, {"currency": "EUR", "total": 20, "amount_paid": 5}]
    report_db.folio_charges.rows = [{"currency": "TRY", "total": 500}, {"currency": "EUR", "total": 20}]
    monkeypatch.setattr(reports, "folio_snapshots", AsyncMock(return_value={"f1": {"currency": "TRY", "balance_by_currency": {"TRY": 100}}, "f2": {"currency": "EUR", "balance_by_currency": {"EUR": 20}}}))
    result = await reports.get_finance_snapshot.__wrapped__(USER)
    assert result["pending_ar"]["total"] is None
    assert result["pending_ar"]["by_currency"]["EUR"]["total"] == 20
    assert result["accounting_invoices"]["pending_total"] is None
    assert result["accounting_invoices"]["by_currency"] == {"TRY": 60, "EUR": 15}
    assert result["mtd_collections"]["collection_rate_percentage"] is None
    assert not result["mtd_collections"]["collection_rate_complete"]


async def test_mtd_profit_and_cost_rankings_are_separate_by_currency(report_db, monkeypatch):
    report_db.purchase_orders.rows = [{"currency": "TRY", "total_amount": 100, "category": "food"}, {"currency": "EUR", "total_amount": 10, "category": "food"}]
    report_db.folio_charges.rows = [{"currency": "TRY", "total": 200}, {"currency": "EUR", "total": 30}]
    monkeypatch.setattr(reports, "load_stay_night_metrics", AsyncMock(return_value=[{"occupied_rooms": 2, "total_rooms": 10}]))
    result = await reports._compute_mtd_cost_summary("tenant-A")
    assert result["total_mtd_costs"] is None and result["top_3_categories"] == []
    assert result["financial_metrics"]["gross_profit"] is None
    assert result["financial_metrics"]["by_currency"]["TRY"]["gross_profit"] == 100
    assert result["financial_metrics"]["by_currency"]["EUR"]["gross_profit"] == 20


def test_flash_document_money_uses_original_currencies_not_tenant_symbol():
    value = flash_email._flash_money({"total_revenue": 0, "total_revenue_by_currency": {"EUR": 20, "TRY": 100}}, "total_revenue", "TRY")
    assert "EUR 20.00" in value and "TRY 100.00" in value


async def test_forecast_api_exposes_the_same_currency_breakdown_as_room_night_metrics(monkeypatch):
    monkeypatch.setattr(standard_reports, "_default_business_date", AsyncMock(return_value=date(2026, 10, 1)))
    monkeypatch.setattr(standard_reports, "load_stay_night_metrics", AsyncMock(return_value=[{"date": "2026-10-01", "occupied_rooms": 2,
        "total_rooms": 2, "occupancy_rate": 100, "revenue": None, "revenue_by_currency": {"TRY": 100, "EUR": 20}, "mixed_currency": True}]))
    result = await standard_reports.get_forecast.__wrapped__(days=1, current_user=USER)
    assert result[0]["expected_revenue"] is None
    assert result[0]["expected_revenue_by_currency"] == {"TRY": 100, "EUR": 20}


@pytest.mark.parametrize("method", ["city_ledger", "complimentary", "correction", "ar", "discount"])
def test_non_cash_offsets_never_become_collections(method):
    payment = {"amount": 100, "currency": "TRY", "payment_method": method, "method": "cash"}
    assert effective_collection(payment) == 0
    assert reporting_collection_summary([payment])["amount"] == 0
    assert effective_revenue_adjustment(payment) == (100 if method == "discount" else 0)


async def test_daily_room_allocation_and_excel_preserve_cents_over_entire_stay(report_db):
    report_db.bookings.rows = [booking(100, "EUR", check_out="2026-10-04")]
    metrics = calculate_stay_night_metrics(report_db.bookings.rows, [{"id": "EUR"}], date(2026, 10, 1), date(2026, 10, 3))
    assert sum(day["revenue"] for day in metrics) == 100
    wb = await workbook(await reports.export_revenue_detail_excel("2026-10-01", "2026-10-03", USER))
    assert sum(row[5] for row in list(wb.active.values)[2:]) == 100


async def test_mtd_profit_respects_explicit_zero_total(report_db, monkeypatch):
    report_db.folio_charges.rows = [{"currency": "TRY", "total": 0, "amount": 100}]
    monkeypatch.setattr(reports, "load_stay_night_metrics", AsyncMock(return_value=[]))
    result = await reports._compute_mtd_cost_summary("tenant-A")
    assert result["financial_metrics"]["mtd_revenue"] == 0
    assert result["financial_metrics"]["gross_profit"] == 0


async def test_flash_and_standard_revenue_share_posted_ledger_and_export_numeric_currencies(monkeypatch):
    from core import tenant_currency
    db = SimpleNamespace(bookings=Collection(),
        folio_charges=Collection([{"charge_category": "room", "total": 200, "currency": "TRY", "source_pos_order_id": "transferred"}]),
        extra_charges=Collection([{"category": "spa", "total": -5, "currency": "EUR"}]),
        pos_orders=Collection([{"id": "direct", "grand_total": 24, "total_amount": 20, "currency": "TRY"},
            {"id": "free", "grand_total": 0, "total_amount": 10, "currency": "TRY"},
            {"id": "transferred", "grand_total": 200, "currency": "TRY"}]))
    db.pos_transactions, db.pos_menu_transactions, db.transactions = Collection(), Collection(), Collection()
    monkeypatch.setattr(flash_email, "db", db)
    monkeypatch.setattr(flash_email, "load_stay_night_metrics", AsyncMock(return_value=[{"occupied_rooms": 1, "sold_rooms": 1, "total_rooms": 2, "occupancy_rate": 50}]))
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    report = await flash_email.get_daily_flash_report.__wrapped__("2026-10-01", USER)
    assert report["revenue"]["total_revenue_by_currency"] == {"TRY": 224, "EUR": -5}
    assert report["revenue"]["fb_revenue_by_currency"] == {"TRY": 24}
    assert report["revenue"]["other_revenue_by_currency"]["EUR"] == -5
    assert db.pos_orders.queries[0]["status"] == {"$in": ["closed", "completed", "paid"]}
    assert db.pos_orders.limits == [None]
    monkeypatch.setattr(flash_email, "get_daily_flash_report", SimpleNamespace(__wrapped__=AsyncMock(return_value=report)))
    for _ in range(2):
        wb = await workbook(await flash_email.export_daily_flash_excel("2026-10-01", USER))
        values = list(wb.active.values)
        assert values[1] == ("Metric", "Currency", "Value")
        assert ("Total Revenue", "EUR", -5) in values
        assert ("Total Revenue", "TRY", 224) in values


async def test_legacy_date_fallbacks_are_exclusive_and_empty_business_dates_supported(monkeypatch):
    db = SimpleNamespace(**{key: Collection() for key in ("folio_charges", "extra_charges", "pos_orders", "pos_transactions", "pos_menu_transactions", "transactions")})
    await standard_reports._posted_revenue_rows("t", date(2026, 10, 1), date(2026, 10, 1), database=db)
    charge_query = db.folio_charges.queries[0]
    missing, alternatives = charge_query["$or"][1]["$and"]
    assert {"business_date": ""} in missing["$or"]
    assert alternatives["$or"][1]["date"] == {"$in": [None, ""]}
    assert alternatives["$or"][2]["charge_date"] == {"$in": [None, ""]}
    pos_alternatives = db.pos_orders.queries[0]["$or"][1]["$and"][1]["$or"]
    assert pos_alternatives[1]["closed_at"] == {"$in": [None, ""]}


async def test_scheduled_finance_payload_keeps_currency_and_comp_exclusion(monkeypatch):
    from core import business_date_service, database, tenant_currency
    from modules.pms_core import stay_night_metrics
    raw_db = SimpleNamespace(folio_charges=Collection([
        {"total": 200, "currency": "TRY", "charge_category": "room"},
        {"total": 40, "currency": "EUR", "charge_category": "room"}]))
    for key in ("extra_charges", "pos_orders", "pos_transactions", "pos_menu_transactions", "transactions"):
        setattr(raw_db, key, Collection())
    monkeypatch.setattr(database, "_raw_db", raw_db)
    monkeypatch.setattr(business_date_service, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-01"}))
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(stay_night_metrics, "load_stay_night_metrics", AsyncMock(return_value=[{"occupied_rooms": 5, "sold_rooms": 2, "total_rooms": 10}]))
    result = await report_scheduler._build_report_payload({"tenant_id": "t", "report_type": "financial"}, datetime(2026, 10, 15, tzinfo=UTC))
    rows = {row["label"]: row["value"] for row in result["rows"]}
    assert result["range"] == "2026-10-01"
    assert rows["Toplam gelir (para birimine göre)"] == "EUR 40.00 · TRY 200.00"
    assert rows["ADR (Ortalama Günlük Fiyat)"] == "EUR 20.00 · TRY 100.00"
    assert raw_db.folio_charges.limits == [None]


async def test_forecast_excel_keeps_mixed_currency_rows(report_db, monkeypatch):
    monkeypatch.setattr(reports, "load_stay_night_metrics", AsyncMock(return_value=[{"date": "2026-10-01", "occupancy_rate": 50, "revenue": None, "revenue_by_currency": {"TRY": 100, "EUR": 20}}]))
    wb = await workbook(await reports.export_forecast_detail_excel("2026-10-01", "2026-10-01", USER))
    assert {row[2] for row in list(wb.active.values)[2:]} == {"TRY", "EUR"}


async def test_revenue_trend_uses_postings_not_folio_creation_day_and_exact_business_day_range(monkeypatch):
    from domains.pms.misc import analytics_network
    monkeypatch.setattr(analytics_network, "db", SimpleNamespace())
    monkeypatch.setattr(analytics_network, "get_current_user", AsyncMock(return_value=USER))
    monkeypatch.setattr(analytics_network, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-02"}))
    loader = AsyncMock(return_value=[{"business_date": "2026-10-01", "date": "2026-10-02T02:00:00Z", "total": 100, "currency": "TRY"},
        {"business_date": "2026-10-02", "total": 20, "currency": "EUR"}])
    monkeypatch.setattr(standard_reports, "_posted_revenue_rows", loader)
    result = await analytics_network.get_revenue_trend(days=2, credentials=None)
    assert len(result["trend"]) == 2
    assert result["business_date"] == "2026-10-02"
    assert result["trend"][0]["revenue_by_currency"] == {"TRY": 100}
    assert result["trend"][1]["revenue_by_currency"] == {"EUR": 20}
    assert result["total_revenue"] is None and result["average_daily_revenue"] is None
    assert result["average_daily_revenue_by_currency"] == {"TRY": 50, "EUR": 10}
    assert loader.call_args.args[1:] == (date(2026, 10, 1), date(2026, 10, 2))


@pytest.mark.parametrize("days", [0, -1, 367])
async def test_analytics_ranges_reject_invalid_days(monkeypatch, days):
    from domains.pms.misc import analytics_network
    with pytest.raises(HTTPException) as exc:
        await analytics_network._trend_range("t", days)
    assert exc.value.status_code == 422


async def test_pos_refund_ledger_is_signed_and_mirrors_and_tips_do_not_inflate_revenue():
    db = SimpleNamespace(**{key: Collection() for key in ("folio_charges", "extra_charges", "pos_orders", "pos_transactions", "pos_menu_transactions", "transactions")})
    sale = {"id": "sale", "order_id": "o1", "transaction_date": "2026-10-01", "total_amount": 110, "tip_amount": 10, "currency": "EUR", "status": "completed"}
    refund = {"id": "refund", "order_id": "o1", "transaction_date": "2026-10-02", "total_amount": -55, "tip_amount": -5, "currency": "EUR", "status": "refunded", "payment_type": "refund"}
    db.pos_transactions.rows = [sale, refund]
    db.pos_menu_transactions.rows = [{**sale, "id": "mirror"}]
    db.pos_orders.rows = [{"id": "o1", "grand_total": 100, "currency": "EUR"}]
    rows = await standard_reports._posted_revenue_rows("t", date(2026, 10, 1), date(2026, 10, 2), database=db)
    assert [(row["business_date"], row["total"]) for row in rows] == [("2026-10-01", 100), ("2026-10-02", -50)]
    assert all(row["currency"] == "EUR" for row in rows)


async def test_legacy_flash_uses_same_posted_revenue_without_estimates_or_mixed_totals(monkeypatch):
    monkeypatch.setattr(flash_email, "get_daily_flash_report", SimpleNamespace(__wrapped__=AsyncMock(return_value={
        "occupancy": {"occupied_rooms": 2, "total_rooms": 10, "occupancy_rate": 20}, "movements": {"arrivals": 0, "departures": 0},
        "revenue": {"total_revenue_by_currency": {"TRY": 1000.49, "EUR": 20.25}, "room_revenue_by_currency": {"TRY": 1000.49, "EUR": 20.25},
            "fb_revenue_by_currency": {}, "category_revenue_by_currency": {}, "adr": None, "adr_by_currency": {"TRY": 500.245, "EUR": 10.125},
            "rev_par": None, "rev_par_by_currency": {"TRY": 100.049, "EUR": 2.025}, "basis": "posted_ledger"}})))
    payment = {"id": "p", "amount": 5, "currency": "EUR", "method": "cash"}
    monkeypatch.setattr(flash_email, "db", SimpleNamespace(bookings=Collection(), payments=Collection([payment, payment])))
    result = await flash_email.get_flash_report.__wrapped__("2026-10-01", USER)
    assert result["revenue"]["total"] is None
    assert result["revenue"]["total_by_currency"] == {"TRY": 1000.49, "EUR": 20.25}
    assert result["revenue"]["collected_by_currency"] == {"EUR": 5}
    assert result["departments"][0]["amount_by_currency"] == {"TRY": 1000.49, "EUR": 20.25}


async def test_pdf_response_is_not_json_cached_and_html_contains_correct_currencies(monkeypatch):
    from core import tenant_currency
    report = {"date": "2026-10-01", "occupancy": {"occupied_rooms": 1, "total_rooms": 2, "occupancy_rate": 50},
        "movements": {"arrivals": 1, "departures": 0, "stayovers": 0},
        "revenue": {"total_revenue_by_currency": {"EUR": 1000.49, "TRY": 500}, "room_revenue_by_currency": {"EUR": 1000.49}, "adr_by_currency": {"EUR": 1000.49}, "rev_par_by_currency": {"EUR": 500.245}}}
    monkeypatch.setattr(flash_email, "get_daily_flash_report", SimpleNamespace(__wrapped__=AsyncMock(return_value=report)))
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    html = []
    class Renderer:
        def __init__(self, string):
            html.append(string)
        def write_pdf(self):
            return b"%PDF-test"
    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=Renderer))
    for _ in range(2):
        response = await flash_email.get_daily_flash_pdf(USER)
        assert response.body.startswith(b"%PDF")
    assert len(html) == 2
    assert "EUR 1,000.49" in html[0] and "TRY 500.00" in html[0]


async def test_finance_refresh_bypasses_stale_json_cache(report_db, monkeypatch):
    import cache_manager
    fake_cache = SimpleNamespace(enabled=True, get=MagicMock(return_value={"stale": True}), set=MagicMock())
    monkeypatch.setattr(cache_manager, "cache", fake_cache)
    result = await reports.get_finance_snapshot(current_user=USER, _nocache=True)
    assert result["report_date"] == "2026-10-15"
    fake_cache.get.assert_not_called()
    assert ":report_finance_snapshot_v4:" in fake_cache.set.call_args.args[0]


@pytest.mark.parametrize("handler,kwargs,prefix", [
    ("get_market_segment_report", {"start_date": "2026-10-01", "end_date": "2026-10-15"}, "report_market_segment_v4"),
    ("get_company_aging_report", {}, "report_company_aging_v4"),
    ("get_finance_snapshot", {}, "report_finance_snapshot_v4"),
    ("get_cost_summary", {}, "report_cost_summary_v3"),
    ("get_mtd_cost_summary", {}, "finance_mtd_cost_summary_v3"),
])
async def test_changed_financial_reports_cannot_reuse_pre_deploy_cached_totals(report_db, monkeypatch, handler, kwargs, prefix):
    import cache_manager

    fake_cache = SimpleNamespace(enabled=True, get=MagicMock(side_effect=lambda key: {"stale": True} if "_v2:" in key else None), set=MagicMock())
    monkeypatch.setattr(cache_manager, "cache", fake_cache)
    monkeypatch.setattr(reports, "_compute_company_aging", AsyncMock(return_value={"report_date": "2026-10-15"}))
    monkeypatch.setattr(reports, "_compute_mtd_cost_summary", AsyncMock(return_value={"report_date": "2026-10-15"}))
    result = await getattr(reports, handler)(current_user=USER, **kwargs)
    assert result != {"stale": True}
    assert f":{prefix}:" in fake_cache.get.call_args.args[0]
    fake_cache.set.assert_called_once()


@pytest.mark.parametrize("category", ["ROOM", "room_charge", "accommodation", "lodging", " Konaklama "])
def test_room_category_aliases_share_one_report_classification(category):
    assert standard_reports._charge_category({"category": category}) == "room"


@pytest.mark.parametrize("status", ["refund", "refunded"])
async def test_legacy_positive_refund_rows_are_negative_revenue(status):
    db = SimpleNamespace(**{key: Collection() for key in ("folio_charges", "extra_charges", "pos_orders", "pos_transactions", "pos_menu_transactions", "transactions")})
    db.pos_transactions.rows = [{"id": "r", "status": status, "total_amount": 60, "tip_amount": 10, "currency": "EUR"}]
    rows = await standard_reports._posted_revenue_rows("t", date(2026, 10, 1), date(2026, 10, 1), database=db)
    assert rows[0]["total"] == -50
    assert status in db.pos_transactions.queries[0]["status"]["$in"]
