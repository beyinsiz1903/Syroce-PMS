"""Custom report money must agree in JSON, Excel and PDF, without live FX."""
import sys
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from routers import eod_report, report_builder as builder


@pytest.fixture
def report_rows(monkeypatch):
    rows = builder.ReportRows([
        {"total_amount": 100.1, "currency": "EUR"},
        {"total_amount": 0.2, "currency": "EUR"},
        {"total_amount": 200, "currency": "USD"},
    ], 8)
    fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(builder, "fetch_report_data", fetch)
    monkeypatch.setattr(builder, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    return rows, fetch


def test_mixed_money_has_only_currency_specific_stats():
    config = builder.ReportConfig(data_source="reservations", columns=["total_amount", "nights"])
    data = [{"total_amount": .1, "currency": "eur", "nights": 2},
            {"total_amount": .2, "currency": "EUR", "nights": 3},
            {"total_amount": 10, "currency": "USD", "nights": 1}]
    summary = builder._report_summary(data, config)
    assert summary["total_amount"]["sum"] is None
    assert summary["total_amount"]["avg"] is None
    assert summary["total_amount"]["by_currency"]["EUR"] == {"sum": .3, "avg": .15, "min": .1, "max": .2, "count": 2}
    assert summary["nights"]["sum"] == 6


def test_builder_treats_numeric_strings_and_decimal128_as_money_and_trusts_current_dates():
    from bson.decimal128 import Decimal128
    source = builder.DATA_SOURCES["reservations"]
    assert builder._report_value("reservations", source, {"total_amount": "100.25"}, "total_amount") == 100.25
    assert builder._report_value("reservations", source, {"total_amount": Decimal128("90.10")}, "total_amount") == 90.1
    assert builder._compute_nights({"check_in": "2026-10-01", "check_out": "2026-10-03", "nights": 99}) == 2


def test_empty_folio_columns_still_fail_validation_and_legacy_total_follows_ledger_aliases():
    config = builder.ReportConfig(data_source="folios", columns=[])
    assert builder._financial_config(config).columns == []
    row = {"charge_amount": 100, "date": "2026-10-01", "charge_date": "2026-10-02"}
    source = builder.DATA_SOURCES["revenue"]
    assert builder._report_value("revenue", source, row, "total") == 100
    assert builder._report_value("revenue", source, row, "date") == "2026-10-01"


@pytest.mark.parametrize("amount", ["not money", "NaN", "Infinity"])
def test_builder_refuses_invalid_money_instead_of_silently_undercounting(amount):
    with pytest.raises(HTTPException) as exc:
        builder._report_value("reservations", builder.DATA_SOURCES["reservations"], {"total_amount": amount}, "total_amount")
    assert exc.value.status_code == 422


async def test_generation_adds_currency_to_old_templates_and_discloses_limit(report_rows):
    _, fetch = report_rows
    config = builder.ReportConfig(data_source="reservations", columns=["total_amount"])
    result = await builder.generate_report(config, SimpleNamespace(tenant_id="A", role="admin"))
    assert config.columns == ["total_amount"]  # no mutation of saved templates
    assert result["columns"] == ["total_amount", "currency"]
    assert result["matched_count"] == 8 and result["total_count"] == 3 and result["truncated"]
    assert result["summary"]["total_amount"]["sum"] is None
    assert fetch.call_args.args[-1] == "TRY"


async def test_excel_preserves_row_currency_and_never_sums_mixed_currency(report_rows):
    config = builder.ReportConfig(data_source="reservations", columns=["total_amount"])
    response = await builder._build_excel_response(config, "A", True)
    content = b"".join([chunk async for chunk in response.body_iterator])
    sheet = load_workbook(BytesIO(content)).active
    assert sheet["A3"].value == "Toplam Tutar" and sheet["B3"].value == "Para Birimi"
    assert sheet["A4"].value == 100.1 and '"EUR"' in sheet["A4"].number_format
    assert sheet["A6"].value == 200 and '"USD"' in sheet["A6"].number_format
    assert sheet["A8"].value is None  # no EUR + USD subtotal
    assert sheet["A9"].value == 100.3 and sheet["B9"].value == "TOPLAM EUR"
    assert sheet["A10"].value == 200 and sheet["B10"].value == "TOPLAM USD"
    assert "SINIRLI RAPOR" in sheet["A2"].value


async def test_pdf_uses_row_currency_and_discloses_partial_report(report_rows, monkeypatch):
    rendered = []

    class HTML:
        def __init__(self, string, **_kwargs):
            rendered.append(string)

        def write_pdf(self):
            return b"%PDF-test-renderer"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=HTML, default_url_fetcher=lambda *_: None))
    config = builder.ReportConfig(data_source="reservations", columns=["total_amount"])
    response = await builder.export_report_pdf(config, SimpleNamespace(tenant_id="A", role="admin"))
    assert response.media_type == "application/pdf"
    html = rendered[0]
    assert "100.10 EUR" in html and "200.00 USD" in html
    assert "TRY" not in html and "SINIRLI RAPOR" in html


@pytest.mark.parametrize("value", ["invalid", "2026-13-01", "2026-10-01junk", "2026-02-30"])
async def test_eod_invalid_dates_return_validation_error(value):
    with pytest.raises(HTTPException) as exc:
        await eod_report._report_business_date("A", value)
    assert exc.value.status_code == 422


def test_eod_renderer_failure_never_downloads_html_as_pdf(monkeypatch):
    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=lambda **_: (_ for _ in ()).throw(RuntimeError("renderer failed"))))
    with pytest.raises(HTTPException) as exc:
        eod_report._html_to_pdf("<h1>report</h1>")
    assert exc.value.status_code == 500


def test_eod_missing_renderer_is_an_explicit_service_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "weasyprint", None)
    with pytest.raises(HTTPException) as exc:
        eod_report._html_to_pdf("<h1>report</h1>")
    assert exc.value.status_code == 503
