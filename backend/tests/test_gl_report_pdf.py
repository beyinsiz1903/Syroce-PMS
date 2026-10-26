"""GL PDF layout and Unicode regression; no financial sources are mutated."""
from copy import deepcopy
from io import BytesIO

import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from core.accounting import report_pdf as pdf


@pytest.mark.parametrize("report,columns,money", [("journal", 9, (6, 7)), ("trial_balance", 6, (2, 3, 4, 5)),
    ("income_statement", 4, (3,)), ("balance_sheet", 4, (3,))])
def test_long_unicode_rows_wrap_within_the_page_without_losing_amounts(report, columns, money):
    headers = [f"Başlık {i}" for i in range(columns)]
    row = ["Şevval Işık <&> " + "ab" * 200 for _ in range(columns)]
    for i in money:
        row[i] = -1234567.89
    rows = [row]
    before = deepcopy(rows)
    width = landscape(A4)[0] - 60
    table = pdf.report_table(report, headers, rows, width)
    assert table.repeatRows == 1 and table.splitInRow == 1
    for i in money:
        assert table._cellvalues[1][i].getPlainText() == "-1.234.567,89"
    assert table._cellvalues[1][next(i for i in range(columns) if i not in money)].getPlainText() == row[next(i for i in range(columns) if i not in money)]
    measured, _ = table.wrapOn(Canvas(BytesIO()), width, 480)
    assert measured == pytest.approx(width)
    result = pdf.build_gl_pdf(report, "Yevmiye ŞİĞıöçü", headers, rows, start="2026-10-01", end="2026-10-24")
    assert result.startswith(b"%PDF") and b"/ToUnicode" in result
    assert rows == before


def test_font_contains_all_turkish_glyphs():
    regular, bold = pdf.report_fonts()
    for name in (regular, bold):
        assert all(pdfmetrics.getFont(name).face.charToGlyph.get(ord(letter)) for letter in "ÇĞİÖŞÜçğıöşü")


@pytest.mark.parametrize("value,expected", [(0, "0,00"), (.01, "0,01"), (.005, "0,01"), (1250, "1.250,00"), (-5300, "-5.300,00"), (None, "—")])
def test_money_is_readable_and_does_not_convert_missing_to_zero(value, expected):
    assert pdf.money_text(value) == expected


def test_missing_unicode_font_never_silently_renders_broken_base_font(monkeypatch):
    pdf.report_fonts.cache_clear()
    monkeypatch.setattr(pdf.Path, "is_file", lambda _: False)
    try:
        with pytest.raises(pdf.ReportFontError):
            pdf.report_fonts()
    finally:
        pdf.report_fonts.cache_clear()


def test_mismatched_column_layout_is_not_silently_exported():
    with pytest.raises(ValueError):
        pdf.report_table("journal", ["Only one"], [[1]], 700)


@pytest.mark.parametrize("report", ["trial_balance", "balance_sheet", "journal", "income_statement"])
def test_pdf_scope_uses_only_the_reports_actual_date_filters(report):
    value = pdf.report_scope(report, "2026-10-01", "2026-10-23", "2026-10-24")
    assert value == ("Tarih: 2026-10-24" if report in {"trial_balance", "balance_sheet"} else "Dönem: 2026-10-01 - 2026-10-23")
