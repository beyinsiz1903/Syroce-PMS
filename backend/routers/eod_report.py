"""
Tek-tik Gun Sonu Raporu — PDF + Email gonderimi.
"""

from datetime import UTC, datetime, timedelta
from html import escape
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.business_date_service import accounting_day_match, ensure_business_date_initialized
from core.database import db
from core.email import send_email
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import load_stay_night_metrics

router = APIRouter(prefix="/api/pms/eod-report", tags=["pms"])


async def _report_business_date(tenant_id: str, requested: str | None) -> str:
    if requested:
        return datetime.fromisoformat(requested[:10]).date().isoformat()
    state = await ensure_business_date_initialized(db, tenant_id)
    return str(state["business_date"])[:10]


async def _collect(tenant_id: str, business_date: str) -> dict:
    """Tek bir is gunu icin gun sonu metriklerini topla."""
    # Date araligi
    start = datetime.fromisoformat(business_date + "T00:00:00+00:00")
    end = start + timedelta(days=1)

    business_day = start.date()
    metrics = await load_stay_night_metrics(db, tenant_id, business_day, business_day, actual_only=True)
    metric = metrics[0] if metrics else {"total_rooms": 0, "occupied_rooms": 0, "occupancy_rate": 0}
    rooms_total = metric["total_rooms"]
    occupied = metric["occupied_rooms"]

    arrivals = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "check_in": {"$gte": business_date, "$lt": end.date().isoformat()},
            "status": {"$nin": ["cancelled", "canceled", "no_show", "noshow"]},
        }
    )
    departures = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "check_out": {"$gte": business_date, "$lt": end.date().isoformat()},
            "status": {"$nin": ["cancelled", "canceled", "no_show", "noshow"]},
        }
    )
    no_shows = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "status": "no_show",
            "check_in": {"$gte": business_date, "$lt": end.date().isoformat()},
        }
    )
    cancels = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["cancelled", "canceled"]},
            "check_in": {"$gte": business_date, "$lt": end.date().isoformat()},
        }
    )

    # Gercek check-in / out (timestamp)
    actual_checkins = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "checked_in_at": {"$gte": start.isoformat(), "$lt": end.isoformat()},
        }
    )
    actual_checkouts = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "checked_out_at": {"$gte": start.isoformat(), "$lt": end.isoformat()},
        }
    )

    # Tahsilatlar, front desk tarafinda ``processed_at`` ile; eski kayitlarda
    # ise ``payment_date``/``date`` ile tutulur. Bir gun sonu raporu bu
    # alanlardan yalniz birine bagli olmamali.
    payments = await db.payments.find(
        {
            "tenant_id": tenant_id,
            **accounting_day_match(
                business_date,
                {"payment_date": business_date},
                {"date": business_date},
                {"processed_at": {"$regex": f"^{business_date}"}},
                {"created_at": {"$regex": f"^{business_date}"}},
            ),
        },
        {"_id": 0},
    ).to_list(10000)
    payments_by_method: dict[str, float] = {}
    for payment in payments:
        status = str(payment.get("status") or "paid").lower()
        if payment.get("voided") or status in {"void", "voided", "failed", "cancelled", "rejected"}:
            continue
        method = str(payment.get("payment_method") or payment.get("method") or "other").lower()
        amount = float(payment.get("amount") or 0)
        if str(payment.get("payment_type") or "").lower() == "refund" and amount > 0:
            amount = -amount
        payments_by_method[method] = payments_by_method.get(method, 0.0) + amount
    payments_by_method = {method: round(amount, 2) for method, amount in payments_by_method.items()}
    payments_total = sum(payments_by_method.values())

    extra_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$regex": f"^{business_date}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$charge_amount"}}},
    ]
    ec = await db.extra_charges.aggregate(extra_pipeline).to_list(1)
    extras_total = float(ec[0]["total"]) if ec else 0.0

    posted_charges = await db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": business_date},
                {"business_date": {"$exists": False}, "date": {"$regex": f"^{business_date}"}},
                {"business_date": None, "date": {"$regex": f"^{business_date}"}},
            ],
        },
        {"_id": 0, "total": 1, "amount": 1},
    ).to_list(10000)
    revenue_total = sum(float(charge.get("total") or charge.get("amount") or 0) for charge in posted_charges)

    # Acik folyolar (bakiye > 0)
    open_folios = await db.folios.count_documents(
        {
            "tenant_id": tenant_id,
            "status": {"$ne": "closed"},
        }
    )

    # Vardiya devir notlari (acik)
    open_handovers = await db.shift_handovers.count_documents(
        {
            "tenant_id": tenant_id,
            "business_date": business_date,
            "acknowledged": False,
        }
    )

    # Cap %100: overbooking veya seed verisindeki cakisma durumlarinda
    # raporda imkansiz oran (ornegin %127) gostermemek icin.
    occ_rate = metric["occupancy_rate"]

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
        "payments_by_method": payments_by_method,
        "cash_total": round(payments_by_method.get("cash", 0.0), 2),
        "extras_total": round(extras_total, 2),
        "revenue_total": round(revenue_total, 2),
        "revenue_basis": "posted_folio_charges",
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
<div class="sub">{hotel_name} · İş Günü: <b>{data["business_date"]}</b> · Üretildi: {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}</div>

<div class="grid">
  <div class="card"><div class="label">Doluluk</div><div class="value">{data["occupancy_rate"]}%</div>
    <div style="font-size:12px;color:#6b7280;margin-top:4px;">{data["occupied"]} / {data["rooms_total"]} oda</div></div>
  <div class="card"><div class="label">Toplam Gelir</div><div class="value">{data["revenue_total"]:,.2f} TL</div>
    <div style="font-size:12px;color:#6b7280;margin-top:4px;">Ödeme: {data["payments_total"]:,.2f} · Ekstra: {data["extras_total"]:,.2f}</div></div>
</div>

<div class="section">
  <h3>Kasa Tahsilat Özeti</h3>
  <table>
    <tr><th>Ödeme Yöntemi</th><th>Tutar</th></tr>
    {''.join(f'<tr><td>{escape(str(method))}</td><td>{amount:,.2f} TL</td></tr>' for method, amount in sorted(data["payments_by_method"].items())) or '<tr><td colspan="2">Tahsilat bulunmuyor</td></tr>'}
    <tr><th>Nakit Tahsilat</th><th>{data["cash_total"]:,.2f} TL</th></tr>
    <tr><th>Toplam Tahsilat</th><th>{data["payments_total"]:,.2f} TL</th></tr>
  </table>
</div>

<div class="section">
  <h3>Hareketler</h3>
  <table>
    <tr><th>Beklenen Giris</th><td>{data["arrivals"]}</td><th>Gerceklesen Giris</th><td>{data["actual_checkins"]}</td></tr>
    <tr><th>Beklenen Cikis</th><td>{data["departures"]}</td><th>Gerceklesen Cikis</th><td>{data["actual_checkouts"]}</td></tr>
    <tr><th>No-Show</th><td class="{"warn" if data["no_shows"] else ""}">{data["no_shows"]}</td><th>Iptal</th><td>{data["cancels"]}</td></tr>
  </table>
</div>

<div class="section">
  <h3>Acik Kalan Isler</h3>
  <table>
    <tr><th>Acik Folyo</th><td class="{"warn" if data["open_folios"] else ""}">{data["open_folios"]}</td></tr>
    <tr><th>Onaylanmamis Vardiya Devir Notu</th><td class="{"warn" if data["open_handovers"] else ""}">{data["open_handovers"]}</td></tr>
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
    business_date: str | None = None
    recipients: list[str] = Field(default_factory=list)


@router.get("/preview")
async def preview(
    business_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_reports")),
):
    bd = await _report_business_date(current_user.tenant_id, business_date)
    data = await _collect(current_user.tenant_id, bd)
    return data


@router.get("/pdf")
async def download_pdf(
    business_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_reports")),
):
    bd = await _report_business_date(current_user.tenant_id, business_date)
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
    bd = await _report_business_date(current_user.tenant_id, payload.business_date)
    data = await _collect(current_user.tenant_id, bd)
    html = _build_html(data, hotel_name=getattr(current_user, "tenant_name", None) or "Otel")
    subject = f"Gun Sonu Raporu — {bd}"
    results = []
    for to_addr in payload.recipients:
        r = await send_email(to_addr.strip(), subject, html)
        results.append({"to": to_addr, **r})
    sent = sum(1 for r in results if r.get("sent"))
    # Audit kaydi
    await db.eod_report_log.insert_one(
        {
            "tenant_id": current_user.tenant_id,
            "business_date": bd,
            "recipients": payload.recipients,
            "sent_count": sent,
            "results": results,
            "sent_by_id": current_user.id,
            "sent_by_name": current_user.name or current_user.email,
            "sent_at": datetime.now(UTC).isoformat(),
        }
    )

    # V3 — Syroce mobil: notify GMs / managers on their phones that the
    # gun sonu raporu is available. Tap routes them to the GM dashboard
    # (handled by mobile/src/notifications/push.ts).
    try:
        from services.expo_push import fire_and_forget_expo_push

        fire_and_forget_expo_push(
            current_user.tenant_id,
            title=f"Gun Sonu Raporu hazir — {bd}",
            body=(f"Doluluk %{data.get('occupancy_rate', 0)} · Gelir {data.get('revenue_total', 0):,.0f} TL"),
            data={
                "type": "eod_ready",
                "business_date": bd,
                "occupancy_rate": data.get("occupancy_rate"),
                "revenue_total": data.get("revenue_total"),
            },
            departments=["gm", "general_manager", "admin", "supervisor"],
            priority="default",
        )
    except Exception:
        # Best-effort — email send already succeeded above.
        pass

    return {"sent": sent, "total": len(results), "business_date": bd, "results": results, "summary": data}
