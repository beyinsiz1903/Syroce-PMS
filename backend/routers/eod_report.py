"""
Tek-tik Gun Sonu Raporu — PDF + Email gonderimi.
"""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.database import db
from core.email import send_email
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/pms/eod-report", tags=["pms"])


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _collect(tenant_id: str, business_date: str) -> dict:
    """Tek bir is gunu icin gun sonu metriklerini topla."""
    # Date araligi
    start = datetime.fromisoformat(business_date + "T00:00:00+00:00")
    end = start + timedelta(days=1)

    rooms_total = await db.rooms.count_documents({"tenant_id": tenant_id})

    # Bugun aktif konaklamalar (occupancy)
    occupied = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["checked_in", "in_house"]},
        "check_in": {"$lte": business_date},
        "check_out": {"$gt": business_date},
    })

    arrivals = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "check_in": business_date,
    })
    departures = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "check_out": business_date,
    })
    no_shows = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "status": "no_show",
        "check_in": business_date,
    })
    cancels = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "status": "cancelled",
        "check_in": business_date,
    })

    # Gercek check-in / out (timestamp)
    actual_checkins = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "checked_in_at": {"$gte": start.isoformat(), "$lt": end.isoformat()},
    })
    actual_checkouts = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "checked_out_at": {"$gte": start.isoformat(), "$lt": end.isoformat()},
    })

    # Gelir — odeme + extra_charges toplamlari
    pay_pipeline = [
        {"$match": {"tenant_id": tenant_id, "payment_date": business_date}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    pay = await db.folio_payments.aggregate(pay_pipeline).to_list(1)
    payments_total = float(pay[0]["total"]) if pay else 0.0

    extra_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$regex": f"^{business_date}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$charge_amount"}}},
    ]
    ec = await db.extra_charges.aggregate(extra_pipeline).to_list(1)
    extras_total = float(ec[0]["total"]) if ec else 0.0

    # Acik folyolar (bakiye > 0)
    open_folios = await db.folios.count_documents({
        "tenant_id": tenant_id,
        "status": {"$ne": "closed"},
    })

    # Vardiya devir notlari (acik)
    open_handovers = await db.shift_handovers.count_documents({
        "tenant_id": tenant_id,
        "business_date": business_date,
        "acknowledged": False,
    })

    occ_rate = (occupied / rooms_total * 100.0) if rooms_total else 0.0

    return {
        "business_date": business_date,
        "rooms_total": rooms_total,
        "occupied": occupied,
        "occupancy_rate": round(occ_rate, 1),
        "arrivals": arrivals,
        "departures": departures,
        "actual_checkins": actual_checkins,
        "actual_checkouts": actual_checkouts,
        "no_shows": no_shows,
        "cancels": cancels,
        "payments_total": round(payments_total, 2),
        "extras_total": round(extras_total, 2),
        "revenue_total": round(payments_total + extras_total, 2),
        "open_folios": open_folios,
        "open_handovers": open_handovers,
    }


def _build_html(data: dict, hotel_name: str = "Otel") -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; color:#1f2937; }}
h1 {{ color: #c2410c; margin: 0 0 4px; }}
.sub {{ color:#6b7280; font-size: 13px; margin-bottom:18px; }}
.grid {{ display: grid; grid-template-columns: repeat(2,1fr); gap: 12px; margin: 12px 0; }}
.card {{ border:1px solid #e5e7eb; border-radius:8px; padding:12px; background:#fafafa; }}
.label {{ font-size:11px; color:#6b7280; text-transform:uppercase; letter-spacing:0.05em; }}
.value {{ font-size:22px; font-weight:700; color:#111827; margin-top:4px; }}
.section {{ margin-top:18px; }}
table {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }}
th,td {{ border:1px solid #e5e7eb; padding:8px 10px; text-align:left; }}
th {{ background:#f3f4f6; font-weight:600; }}
.warn {{ color:#b91c1c; font-weight:600; }}
.foot {{ margin-top:24px; font-size:11px; color:#9ca3af; text-align:center; }}
</style></head><body>
<h1>Gun Sonu Raporu</h1>
<div class="sub">{hotel_name} · İş Günü: <b>{data['business_date']}</b> · Üretildi: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>

<div class="grid">
  <div class="card"><div class="label">Doluluk</div><div class="value">{data['occupancy_rate']}%</div>
    <div style="font-size:12px;color:#6b7280;margin-top:4px;">{data['occupied']} / {data['rooms_total']} oda</div></div>
  <div class="card"><div class="label">Toplam Gelir</div><div class="value">{data['revenue_total']:,.2f} TL</div>
    <div style="font-size:12px;color:#6b7280;margin-top:4px;">Ödeme: {data['payments_total']:,.2f} · Ekstra: {data['extras_total']:,.2f}</div></div>
</div>

<div class="section">
  <h3>Hareketler</h3>
  <table>
    <tr><th>Beklenen Giris</th><td>{data['arrivals']}</td><th>Gerceklesen Giris</th><td>{data['actual_checkins']}</td></tr>
    <tr><th>Beklenen Cikis</th><td>{data['departures']}</td><th>Gerceklesen Cikis</th><td>{data['actual_checkouts']}</td></tr>
    <tr><th>No-Show</th><td class="{'warn' if data['no_shows'] else ''}">{data['no_shows']}</td><th>Iptal</th><td>{data['cancels']}</td></tr>
  </table>
</div>

<div class="section">
  <h3>Acik Kalan Isler</h3>
  <table>
    <tr><th>Acik Folyo</th><td class="{'warn' if data['open_folios'] else ''}">{data['open_folios']}</td></tr>
    <tr><th>Onaylanmamis Vardiya Devir Notu</th><td class="{'warn' if data['open_handovers'] else ''}">{data['open_handovers']}</td></tr>
  </table>
</div>

<div class="foot">Syroce PMS · Gün Sonu Raporu</div>
</body></html>"""


def _html_to_pdf(html: str) -> bytes:
    """weasyprint ile PDF; kurulu degilse HTML bytes dondur."""
    try:
        from weasyprint import HTML  # type: ignore
        return HTML(string=html).write_pdf()
    except Exception:
        return html.encode("utf-8")


class SendRequest(BaseModel):
    business_date: Optional[str] = None
    recipients: list[str] = Field(default_factory=list)


@router.get("/preview")
async def preview(
    business_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_reports")),
):
    bd = business_date or _today_str()
    data = await _collect(current_user.tenant_id, bd)
    return data


@router.get("/pdf")
async def download_pdf(
    business_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_reports")),
):
    bd = business_date or _today_str()
    data = await _collect(current_user.tenant_id, bd)
    html = _build_html(data, hotel_name=getattr(current_user, "tenant_name", None) or "Otel")
    pdf_bytes = _html_to_pdf(html)
    is_pdf = pdf_bytes[:4] == b"%PDF"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf" if is_pdf else "text/html",
        headers={"Content-Disposition": f"attachment; filename=eod-{bd}.{'pdf' if is_pdf else 'html'}"},
    )


@router.post("/send")
async def send_eod(
    payload: SendRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_reports")),
):
    if not payload.recipients:
        raise HTTPException(400, "En az bir alici e-postasi gerekli")
    bd = payload.business_date or _today_str()
    data = await _collect(current_user.tenant_id, bd)
    html = _build_html(data, hotel_name=getattr(current_user, "tenant_name", None) or "Otel")
    subject = f"Gun Sonu Raporu — {bd}"
    results = []
    for to_addr in payload.recipients:
        r = await send_email(to_addr.strip(), subject, html)
        results.append({"to": to_addr, **r})
    sent = sum(1 for r in results if r.get("sent"))
    # Audit kaydi
    await db.eod_report_log.insert_one({
        "tenant_id": current_user.tenant_id,
        "business_date": bd,
        "recipients": payload.recipients,
        "sent_count": sent,
        "results": results,
        "sent_by_id": current_user.id,
        "sent_by_name": current_user.name or current_user.email,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"sent": sent, "total": len(results), "business_date": bd, "results": results, "summary": data}
