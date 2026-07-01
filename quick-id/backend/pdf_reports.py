"""
PDF Rapor Oluşturucu
- Form-C (Emniyet Bildirim Formu)
- Misafir Listesi
- KVKK Uyumluluk Raporu
"""
import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import logging

logger = logging.getLogger("quickid.pdf")


def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleTR', fontName='Helvetica-Bold', fontSize=16, alignment=TA_CENTER, spaceAfter=12))
    styles.add(ParagraphStyle(name='SubtitleTR', fontName='Helvetica', fontSize=10, alignment=TA_CENTER, spaceAfter=8, textColor=colors.grey))
    styles.add(ParagraphStyle(name='SectionHeader', fontName='Helvetica-Bold', fontSize=11, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor('#0B5E8A')))
    styles.add(ParagraphStyle(name='FieldLabel', fontName='Helvetica-Bold', fontSize=8, textColor=colors.grey))
    styles.add(ParagraphStyle(name='FieldValue', fontName='Helvetica', fontSize=10, spaceBefore=2))
    styles.add(ParagraphStyle(name='SmallNote', fontName='Helvetica', fontSize=7, textColor=colors.grey, alignment=TA_CENTER))
    return styles


def generate_form_c_pdf(guest_data: dict, hotel_name: str = "Quick ID Hotel") -> bytes:
    """Form-C (Emniyet Genel Mudurlugu Bildirim Formu) PDF olustur"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=2*cm, rightMargin=2*cm)
    styles = get_styles()
    elements = []

    # Header
    elements.append(Paragraph("T.C. EMNIYET GENEL MUDURLUGU", styles['TitleTR']))
    elements.append(Paragraph("KONAKLAMA BILDIRIM FORMU (FORM-C)", styles['SubtitleTR']))
    elements.append(Spacer(1, 6*mm))

    # Hotel info
    elements.append(Paragraph("Tesis Bilgileri", styles['SectionHeader']))
    hotel_data = [
        ['Tesis Adi:', hotel_name, 'Tarih:', datetime.now().strftime('%d.%m.%Y')],
        ['Form No:', guest_data.get('form_number', '-'), 'Saat:', datetime.now().strftime('%H:%M')],
    ]
    t = Table(hotel_data, colWidths=[3*cm, 6*cm, 3*cm, 4*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 4*mm))

    # Guest info
    elements.append(Paragraph("Misafir Bilgileri", styles['SectionHeader']))
    g = guest_data
    guest_table_data = [
        ['Ad:', g.get('first_name', '-'), 'Soyad:', g.get('last_name', '-')],
        ['Uyruk:', g.get('nationality', '-'), 'Cinsiyet:', 'Erkek' if g.get('gender') == 'M' else 'Kadin' if g.get('gender') == 'F' else '-'],
        ['Dogum Tarihi:', g.get('birth_date', '-'), 'Dogum Yeri:', g.get('birth_place', '-')],
        ['Belge Turu:', g.get('document_type', '-'), 'Belge No:', g.get('id_number', g.get('document_number', '-'))],
        ['Giris Tarihi:', g.get('check_in_date', '-'), 'Cikis Tarihi:', g.get('check_out_date', '-')],
        ['Anne Adi:', g.get('mother_name', '-'), 'Baba Adi:', g.get('father_name', '-')],
    ]
    t2 = Table(guest_table_data, colWidths=[3*cm, 5*cm, 3*cm, 5*cm])
    t2.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 8*mm))

    # Signatures
    elements.append(HRFlowable(width='100%', thickness=0.5, color=colors.lightgrey))
    elements.append(Spacer(1, 10*mm))
    sig_data = [['Tesis Yetkilisi', '', 'Misafir Imzasi'],
                ['_________________', '', '_________________']]
    t3 = Table(sig_data, colWidths=[5*cm, 6*cm, 5*cm])
    t3.setStyle(TableStyle([
        ('ALIGNMENT', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, 1), 20),
    ]))
    elements.append(t3)

    # Footer
    elements.append(Spacer(1, 15*mm))
    elements.append(Paragraph("Bu form 1774 sayili Kimlik Bildirme Kanunu geregince duzenlenmistir.", styles['SmallNote']))
    elements.append(Paragraph(f"Olusturulma: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Quick ID Reader", styles['SmallNote']))

    doc.build(elements)
    return buffer.getvalue()


def generate_guest_list_pdf(guests: list, title: str = "Misafir Listesi") -> bytes:
    """Misafir listesi PDF raporu"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = get_styles()
    elements = []

    elements.append(Paragraph(title, styles['TitleTR']))
    elements.append(Paragraph(f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Toplam: {len(guests)} misafir", styles['SubtitleTR']))
    elements.append(Spacer(1, 6*mm))

    # Table header
    header = ['#', 'Ad Soyad', 'Kimlik No', 'Uyruk', 'Belge', 'Durum', 'Giris']
    data = [header]
    for i, g in enumerate(guests, 1):
        name = f"{g.get('first_name', '')} {g.get('last_name', '')}".strip() or '-'
        status_map = {'pending': 'Bekleyen', 'checked_in': 'Giris', 'checked_out': 'Cikis'}
        row = [
            str(i),
            name[:25],
            g.get('id_number', '-')[:15],
            g.get('nationality', '-')[:10],
            g.get('document_type', '-')[:10],
            status_map.get(g.get('status', ''), g.get('status', '-')),
            g.get('check_in_at', g.get('created_at', '-'))[:10] if g.get('check_in_at') or g.get('created_at') else '-',
        ]
        data.append(row)

    t = Table(data, colWidths=[1*cm, 4.5*cm, 3*cm, 2.5*cm, 2.5*cm, 2*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B5E8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)

    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(f"Quick ID Reader | {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['SmallNote']))

    doc.build(elements)
    return buffer.getvalue()
