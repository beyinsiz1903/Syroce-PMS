"""
Report Builder Router - Özel Rapor Oluşturucu
Kullanıcıların dinamik rapor oluşturmasını, filtrelemesini ve dışa aktarmasını sağlar.
"""
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel

router = APIRouter(prefix="/api/reports/builder", tags=["report-builder"])


# ─── Models ───────────────────────────────────────────────────────────────

class ReportFilter(BaseModel):
    field: str
    operator: str  # eq, ne, gt, gte, lt, lte, in, contains
    value: object


class ReportConfig(BaseModel):
    data_source: str  # reservations, revenue, guests, rooms, housekeeping, folios
    columns: List[str]
    filters: Optional[List[ReportFilter]] = []
    sort_by: Optional[str] = None
    sort_order: Optional[str] = "desc"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    group_by: Optional[str] = None
    limit: Optional[int] = 500


class SavedTemplate(BaseModel):
    name: str
    description: Optional[str] = ""
    config: ReportConfig


# ─── Dependencies (will be injected from server.py) ──────────────────────

_db = None
_get_current_user = None


def init_report_builder(db, get_current_user_dep):
    global _db, _get_current_user
    _db = db
    _get_current_user = get_current_user_dep


def get_db():
    return _db


def get_user():
    return Depends(_get_current_user)


# ─── Data Source Definitions ──────────────────────────────────────────────

DATA_SOURCES = {
    "reservations": {
        "label": "Rezervasyonlar",
        "collection": "bookings",
        "columns": {
            "guest_name": {"label": "Misafir Adı", "type": "text"},
            "room_number": {"label": "Oda No", "type": "text"},
            "room_type": {"label": "Oda Tipi", "type": "text"},
            "check_in": {"label": "Giriş Tarihi", "type": "date"},
            "check_out": {"label": "Çıkış Tarihi", "type": "date"},
            "status": {"label": "Durum", "type": "select", "options": ["confirmed", "checked_in", "checked_out", "cancelled", "no_show"]},
            "total_amount": {"label": "Toplam Tutar", "type": "currency"},
            "source": {"label": "Kaynak", "type": "select", "options": ["direct", "ota", "corporate", "walk_in", "booking_com"]},
            "nights": {"label": "Gece Sayısı", "type": "number"},
            "adults": {"label": "Yetişkin", "type": "number"},
            "children": {"label": "Çocuk", "type": "number"},
            "rate_code": {"label": "Ücret Kodu", "type": "text"},
            "market_segment": {"label": "Pazar Segmenti", "type": "text"},
            "created_at": {"label": "Oluşturma Tarihi", "type": "date"},
            "notes": {"label": "Notlar", "type": "text"},
        },
        "date_field": "check_in",
    },
    "revenue": {
        "label": "Gelir",
        "collection": "folio_charges",
        "columns": {
            "description": {"label": "Açıklama", "type": "text"},
            "amount": {"label": "Tutar", "type": "currency"},
            "total": {"label": "Toplam", "type": "currency"},
            "charge_type": {"label": "Masraf Tipi", "type": "select", "options": ["room", "fnb", "minibar", "laundry", "spa", "parking", "phone", "other"]},
            "date": {"label": "Tarih", "type": "date"},
            "room_number": {"label": "Oda No", "type": "text"},
            "folio_id": {"label": "Folio ID", "type": "text"},
            "quantity": {"label": "Adet", "type": "number"},
            "unit_price": {"label": "Birim Fiyat", "type": "currency"},
            "voided": {"label": "İptal Edildi", "type": "boolean"},
            "posted_by": {"label": "İşlemi Yapan", "type": "text"},
        },
        "date_field": "date",
    },
    "guests": {
        "label": "Misafirler",
        "collection": "guests",
        "columns": {
            "name": {"label": "Ad Soyad", "type": "text"},
            "email": {"label": "E-posta", "type": "text"},
            "phone": {"label": "Telefon", "type": "text"},
            "nationality": {"label": "Uyruk", "type": "text"},
            "id_number": {"label": "TC/Pasaport No", "type": "text"},
            "vip": {"label": "VIP", "type": "boolean"},
            "gender": {"label": "Cinsiyet", "type": "text"},
            "total_stays": {"label": "Toplam Konaklama", "type": "number"},
            "total_revenue": {"label": "Toplam Harcama", "type": "currency"},
            "created_at": {"label": "Kayıt Tarihi", "type": "date"},
            "notes": {"label": "Notlar", "type": "text"},
        },
        "date_field": "created_at",
    },
    "rooms": {
        "label": "Odalar",
        "collection": "rooms",
        "columns": {
            "number": {"label": "Oda No", "type": "text"},
            "type": {"label": "Oda Tipi", "type": "text"},
            "floor": {"label": "Kat", "type": "number"},
            "status": {"label": "Durum", "type": "select", "options": ["available", "occupied", "dirty", "maintenance", "out_of_order"]},
            "housekeeping_status": {"label": "HK Durumu", "type": "text"},
            "base_rate": {"label": "Taban Fiyat", "type": "currency"},
            "max_occupancy": {"label": "Max Kapasite", "type": "number"},
            "amenities": {"label": "Olanaklar", "type": "text"},
            "is_active": {"label": "Aktif", "type": "boolean"},
        },
        "date_field": None,
    },
    "housekeeping": {
        "label": "Kat Hizmetleri",
        "collection": "housekeeping_tasks",
        "columns": {
            "room_number": {"label": "Oda No", "type": "text"},
            "task_type": {"label": "Görev Tipi", "type": "select", "options": ["checkout_clean", "stayover_clean", "deep_clean", "turndown", "inspection"]},
            "status": {"label": "Durum", "type": "select", "options": ["pending", "in_progress", "completed", "inspected"]},
            "assigned_to": {"label": "Atanan Kişi", "type": "text"},
            "priority": {"label": "Öncelik", "type": "select", "options": ["low", "medium", "high", "urgent"]},
            "started_at": {"label": "Başlangıç", "type": "date"},
            "completed_at": {"label": "Tamamlanma", "type": "date"},
            "duration_minutes": {"label": "Süre (dk)", "type": "number"},
            "notes": {"label": "Notlar", "type": "text"},
        },
        "date_field": "created_at",
    },
    "folios": {
        "label": "Foliolar",
        "collection": "folios",
        "columns": {
            "folio_number": {"label": "Folio No", "type": "text"},
            "guest_name": {"label": "Misafir Adı", "type": "text"},
            "room_number": {"label": "Oda No", "type": "text"},
            "status": {"label": "Durum", "type": "select", "options": ["open", "closed", "settled"]},
            "total_charges": {"label": "Toplam Masraf", "type": "currency"},
            "total_payments": {"label": "Toplam Ödeme", "type": "currency"},
            "balance": {"label": "Bakiye", "type": "currency"},
            "check_in": {"label": "Giriş", "type": "date"},
            "check_out": {"label": "Çıkış", "type": "date"},
            "created_at": {"label": "Oluşturma", "type": "date"},
            "payment_method": {"label": "Ödeme Yöntemi", "type": "text"},
        },
        "date_field": "created_at",
    },
}


# ─── Helpers ──────────────────────────────────────────────────────────────

def build_mongo_filter(config: ReportConfig, tenant_id: str) -> dict:
    """Build MongoDB query filter from ReportConfig."""
    query = {"tenant_id": tenant_id}

    # Date range filter
    date_field = DATA_SOURCES.get(config.data_source, {}).get("date_field")
    if date_field and (config.date_from or config.date_to):
        date_q = {}
        if config.date_from:
            date_q["$gte"] = config.date_from
        if config.date_to:
            date_q["$lte"] = config.date_to
        query[date_field] = date_q

    # Custom filters
    for f in (config.filters or []):
        field = f.field
        op = f.operator
        val = f.value

        if op == "eq":
            query[field] = val
        elif op == "ne":
            query[field] = {"$ne": val}
        elif op == "gt":
            query[field] = {"$gt": val}
        elif op == "gte":
            query[field] = {"$gte": val}
        elif op == "lt":
            query[field] = {"$lt": val}
        elif op == "lte":
            query[field] = {"$lte": val}
        elif op == "in":
            query[field] = {"$in": val if isinstance(val, list) else [val]}
        elif op == "contains":
            query[field] = {"$regex": str(val), "$options": "i"}

    return query


def build_projection(columns: List[str]) -> dict:
    """Build MongoDB projection from column list."""
    proj = {"_id": 0}
    for col in columns:
        proj[col] = 1
    return proj


async def fetch_report_data(config: ReportConfig, tenant_id: str) -> list:
    """Fetch data from MongoDB based on report config."""
    db = get_db()
    source_def = DATA_SOURCES.get(config.data_source)
    if not source_def:
        raise HTTPException(status_code=400, detail=f"Geçersiz veri kaynağı: {config.data_source}")

    collection = db[source_def["collection"]]
    query = build_mongo_filter(config, tenant_id)
    projection = build_projection(config.columns)

    sort_field = config.sort_by or source_def.get("date_field") or "_id"
    sort_dir = -1 if config.sort_order == "desc" else 1

    cursor = collection.find(query, projection).sort(sort_field, sort_dir).limit(config.limit or 500)
    results = await cursor.to_list(length=config.limit or 500)

    # Clean data: convert any remaining ObjectIds
    cleaned = []
    for doc in results:
        row = {}
        for col in config.columns:
            val = doc.get(col, "")
            if hasattr(val, '__str__') and type(val).__name__ == 'ObjectId':
                val = str(val)
            row[col] = val
        cleaned.append(row)

    return cleaned


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.get("/config")
async def get_builder_config(credentials=Depends(HTTPBearer())):
    """Rapor oluşturucu için mevcut veri kaynaklarını ve sütun tanımlarını döndürür."""
    await _get_current_user(credentials)

    sources = {}
    for key, src in DATA_SOURCES.items():
        sources[key] = {
            "label": src["label"],
            "columns": src["columns"],
            "date_field": src.get("date_field"),
        }
    return {"data_sources": sources}


@router.post("/generate")
async def generate_report(config: ReportConfig, credentials=Depends(HTTPBearer())):
    """Özel rapor verisini üretir."""
    current_user = await _get_current_user(credentials)

    tenant_id = getattr(current_user, 'tenant_id', None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant bilgisi bulunamadı")

    data = await fetch_report_data(config, tenant_id)

    # Build column labels
    source_def = DATA_SOURCES.get(config.data_source, {})
    column_labels = {}
    for col in config.columns:
        col_def = source_def.get("columns", {}).get(col, {})
        column_labels[col] = col_def.get("label", col)

    # Calculate summary stats for numeric/currency columns
    summary = {}
    for col in config.columns:
        col_type = source_def.get("columns", {}).get(col, {}).get("type")
        if col_type in ("number", "currency"):
            values = [row.get(col, 0) for row in data if isinstance(row.get(col), (int, float))]
            if values:
                summary[col] = {
                    "sum": round(sum(values), 2),
                    "avg": round(sum(values) / len(values), 2),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "count": len(values),
                }

    return {
        "data": data,
        "total_count": len(data),
        "column_labels": column_labels,
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/export/excel")
async def export_report_excel(config: ReportConfig, credentials=Depends(HTTPBearer())):
    """Özel raporu Excel formatında dışa aktarır."""
    current_user = await _get_current_user(credentials)

    tenant_id = getattr(current_user, 'tenant_id', None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant bilgisi bulunamadı")

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    data = await fetch_report_data(config, tenant_id)
    source_def = DATA_SOURCES.get(config.data_source, {})

    wb = Workbook()
    ws = wb.active
    ws.title = source_def.get("label", "Rapor")

    # Title row
    headers = []
    for col in config.columns:
        col_def = source_def.get("columns", {}).get(col, {})
        headers.append(col_def.get("label", col))

    ws.merge_cells('A1:' + get_column_letter(max(len(headers), 1)) + '1')
    title_cell = ws['A1']
    title_cell.value = f"{source_def.get('label', 'Rapor')} - Özel Rapor"
    title_cell.font = Font(size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    # Date info row
    ws.merge_cells('A2:' + get_column_letter(max(len(headers), 1)) + '2')
    date_cell = ws['A2']
    date_parts = []
    if config.date_from:
        date_parts.append(f"Başlangıç: {config.date_from}")
    if config.date_to:
        date_parts.append(f"Bitiş: {config.date_to}")
    date_cell.value = " | ".join(date_parts) if date_parts else f"Oluşturma: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
    date_cell.font = Font(size=10, italic=True, color="666666")
    date_cell.alignment = Alignment(horizontal="center")

    # Headers
    header_fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_num)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
        ws.column_dimensions[get_column_letter(col_num)].width = max(len(header) + 4, 14)

    # Data rows
    light_fill = PatternFill(start_color="F2F7FB", end_color="F2F7FB", fill_type="solid")
    for row_num, row_data in enumerate(data, 4):
        for col_num, col_key in enumerate(config.columns, 1):
            cell = ws.cell(row=row_num, column=col_num)
            val = row_data.get(col_key, "")
            col_type = source_def.get("columns", {}).get(col_key, {}).get("type")

            if col_type == "currency" and isinstance(val, (int, float)):
                cell.value = val
                cell.number_format = '#,##0.00 ₺'
            elif col_type == "number" and isinstance(val, (int, float)):
                cell.value = val
                cell.number_format = '#,##0'
            elif isinstance(val, list):
                cell.value = ", ".join(str(v) for v in val)
            else:
                cell.value = str(val) if val is not None else ""

            cell.border = border
            cell.alignment = Alignment(vertical="center")
            if (row_num - 4) % 2 == 1:
                cell.fill = light_fill

    # Summary row
    summary_row = len(data) + 5
    ws.cell(row=summary_row, column=1, value="TOPLAM").font = Font(bold=True, size=11)
    for col_num, col_key in enumerate(config.columns, 1):
        col_type = source_def.get("columns", {}).get(col_key, {}).get("type")
        if col_type in ("number", "currency"):
            values = [r.get(col_key, 0) for r in data if isinstance(r.get(col_key), (int, float))]
            if values:
                cell = ws.cell(row=summary_row, column=col_num)
                cell.value = sum(values)
                cell.font = Font(bold=True, size=11)
                cell.border = Border(top=Side(style='double'))
                if col_type == "currency":
                    cell.number_format = '#,##0.00 ₺'

    # Auto-width
    for col in ws.columns:
        max_length = 0
        try:
            column_letter = col[0].column_letter
        except AttributeError:
            continue
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 3, 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"ozel_rapor_{config.data_source}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/export/pdf")
async def export_report_pdf(config: ReportConfig, credentials=Depends(HTTPBearer())):
    """Özel raporu PDF formatında dışa aktarır."""
    current_user = await _get_current_user(credentials)

    tenant_id = getattr(current_user, 'tenant_id', None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant bilgisi bulunamadı")

    data = await fetch_report_data(config, tenant_id)
    source_def = DATA_SOURCES.get(config.data_source, {})

    headers = []
    for col in config.columns:
        col_def = source_def.get("columns", {}).get(col, {})
        headers.append(col_def.get("label", col))

    # Build HTML table for PDF
    col_count = len(headers)
    max(100 // col_count, 8)

    rows_html = ""
    for i, row in enumerate(data):
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        cells = ""
        for col_key in config.columns:
            val = row.get(col_key, "")
            col_type = source_def.get("columns", {}).get(col_key, {}).get("type")
            if col_type == "currency" and isinstance(val, (int, float)):
                display = f"₺{val:,.2f}"
            elif isinstance(val, list):
                display = ", ".join(str(v) for v in val)
            else:
                display = str(val) if val is not None else ""
            cells += f'<td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:10px;">{display}</td>'
        rows_html += f'<tr style="background:{bg}">{cells}</tr>'

    header_cells = "".join(
        f'<th style="padding:8px;background:#1e3a5f;color:white;font-size:10px;text-align:left;border-bottom:2px solid #0d2137;">{h}</th>'
        for h in headers
    )

    date_info = ""
    if config.date_from or config.date_to:
        parts = []
        if config.date_from:
            parts.append(f"Başlangıç: {config.date_from}")
        if config.date_to:
            parts.append(f"Bitiş: {config.date_to}")
        date_info = f'<p style="color:#64748b;font-size:11px;margin:4px 0 12px;">{" | ".join(parts)}</p>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  @page {{ size: A4 landscape; margin: 1.5cm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1e293b; margin:0; padding:0; }}
  .header {{ background: linear-gradient(135deg, #1e3a5f, #2563eb); color: white; padding: 20px 24px; margin-bottom: 16px; }}
  .header h1 {{ margin: 0; font-size: 18px; }}
  .header p {{ margin: 4px 0 0; font-size: 11px; opacity: 0.8; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
  .footer {{ text-align: center; font-size: 9px; color: #94a3b8; margin-top: 16px; padding-top: 8px; border-top: 1px solid #e2e8f0; }}
</style></head><body>
<div class="header">
  <h1>{source_def.get('label', 'Rapor')} - Özel Rapor</h1>
  <p>Toplam {len(data)} kayıt | Oluşturma: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')}</p>
</div>
{date_info}
<table><thead><tr>{header_cells}</tr></thead><tbody>{rows_html}</tbody></table>
<div class="footer">Syroce PMS - Otomatik Oluşturulmuş Rapor</div>
</body></html>"""

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        output = io.BytesIO(pdf_bytes)
    except Exception:
        # Fallback: return HTML as PDF-like content
        output = io.BytesIO(html.encode('utf-8'))

    output.seek(0)
    filename = f"ozel_rapor_{config.data_source}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── Template CRUD ────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(credentials=Depends(HTTPBearer())):
    """Kayıtlı rapor şablonlarını listeler."""
    current_user = await _get_current_user(credentials)

    db = get_db()
    tenant_id = getattr(current_user, 'tenant_id', None)
    templates = await db.report_templates.find(
        {"tenant_id": tenant_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"templates": templates}


@router.post("/templates")
async def save_template(template: SavedTemplate, credentials=Depends(HTTPBearer())):
    """Rapor şablonunu kaydeder."""
    current_user = await _get_current_user(credentials)

    db = get_db()
    tenant_id = getattr(current_user, 'tenant_id', None)
    user_id = getattr(current_user, 'id', None)

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "created_by": user_id,
        "name": template.name,
        "description": template.description,
        "config": template.config.dict(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.report_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, credentials=Depends(HTTPBearer())):
    """Rapor şablonunu siler."""
    current_user = await _get_current_user(credentials)

    db = get_db()
    tenant_id = getattr(current_user, 'tenant_id', None)
    result = await db.report_templates.delete_one({"id": template_id, "tenant_id": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    return {"message": "Şablon silindi"}
