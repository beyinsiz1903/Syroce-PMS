"""Unicode, page-bounded GL reports. Reads prepared report rows unchanged."""
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class ReportFontError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def report_fonts():
    # The production Dockerfile installs fonts-dejavu-core. Arial is the
    # equivalent local macOS font; never fall back to lossy PDF base fonts.
    candidates = [
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont("SyroceGL", str(regular)))
            pdfmetrics.registerFont(TTFont("SyroceGLBold", str(bold)))
            return "SyroceGL", "SyroceGLBold"
    raise ReportFontError("Türkçe PDF yazı tipi kurulu değil; fonts-dejavu-core yüklenmelidir")


def money_text(value):
    if value is None:
        return "—"
    # GL rows are already rounded to their canonical two-decimal TRY amount.
    amount = Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def report_scope(report, start=None, end=None, as_of=None):
    # Match the owning report's filters, including ignored generic UI params.
    if report in {"trial_balance", "balance_sheet"}:
        return f"Tarih: {as_of or 'Tüm tarihler'}"
    return f"Dönem: {start or 'Başlangıçtan'} - {end or 'Tüm tarihler'}"


def report_table(report, headers, rows, width):
    regular, bold = report_fonts()
    journal = report == "journal"
    weights = [85, 65, 220, 28, 48, 130, 70, 70, 78] if journal else (
        [60, 245, 120, 120, 115, 115] if report == "trial_balance" else [100, 70, 430, 130])
    if len(headers) != len(weights) or any(len(row) != len(headers) for row in rows):
        raise ValueError("GL PDF satır/sütun yapısı raporla eşleşmiyor")
    widths = [width * weight / sum(weights) for weight in weights]
    style = ParagraphStyle("cell", fontName=regular, fontSize=7 if journal else 8,
        leading=9 if journal else 11, splitLongWords=True)
    header_style = ParagraphStyle("header", parent=style, fontName=bold, textColor=colors.white)
    amount_style = ParagraphStyle("amount", parent=style, alignment=TA_RIGHT)
    money_columns = {6, 7} if journal else set(range(2, 6)) if report == "trial_balance" else {3}

    def paragraph(value, text_style):
        return Paragraph(escape(str(value) if value is not None else "—").replace("\n", "<br/>"), text_style)

    data = [[paragraph(value, header_style) for value in headers]]
    data.extend([paragraph(money_text(value) if i in money_columns else value,
        amount_style if i in money_columns else style) for i, value in enumerate(row)] for row in rows)
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1, splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def build_gl_pdf(report, title, headers, rows, *, start=None, end=None, as_of=None):
    regular, bold = report_fonts()
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=32)
    # Platypus's default frame adds six points of internal padding per edge.
    table = report_table(report, headers, rows, document.width - 12)
    title_style = ParagraphStyle("title", fontName=bold, fontSize=14, leading=18)
    scope_style = ParagraphStyle("scope", fontName=regular, fontSize=8, leading=12, textColor=colors.HexColor("#475569"))
    scope = report_scope(report, start, end, as_of)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.drawRightString(document.pagesize[0] - 24, 16, f"Sayfa {doc.page}")
        canvas.restoreState()

    document.build([Paragraph(escape(title), title_style), Spacer(1, 6),
        Paragraph(escape(scope + " · Para birimi: TRY"), scope_style), Spacer(1, 10), table],
        onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
