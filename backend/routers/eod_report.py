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
from core.tenant_currency import get_tenant_currency
from models.schemas import User
from modules.pms_core.reporting_financials import effective_collection, effective_revenue_adjustment
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import load_stay_night_metrics

router = APIRouter(prefix="/api/pms/eod-report", tags=["pms"])


def _currency_code(value: object, fallback: str = "TRY") -> str:
    code = str(value or fallback or "TRY").strip().upper()
    return "TRY" if code in {"TL", "TRL"} else code


def _add_currency(target: dict[str, float], currency: object, amount: float, fallback: str) -> None:
    code = _currency_code(currency, fallback)
    target[code] = target.get(code, 0.0) + float(amount or 0)


def _rounded_breakdown(values: dict[str, float]) -> dict[str, float]:
    return {code: round(amount, 2) for code, amount in sorted(values.items()) if round(amount, 2) != 0}


def _format_breakdown(values: dict[str, float], *, empty: str = "0") -> str:
    parts = [f"{amount:,.2f} {escape(code)}" for code, amount in sorted(values.items()) if round(amount, 2) != 0]
    return " · ".join(parts) or empty


async def _currency_context(tenant_id: str, documents: list[dict], fallback: str) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve legacy transaction currency without per-row database queries."""
    booking_ids = {str(item.get("booking_id")) for item in documents if item.get("booking_id")}
    folio_ids = {str(item.get("folio_id")) for item in documents if item.get("folio_id") and not item.get("booking_id")}

    folio_booking: dict[str, str] = {}
    if folio_ids:
        folios = await db.folios.find(
            {"tenant_id": tenant_id, "id": {"$in": list(folio_ids)}},
            {"_id": 0, "id": 1, "booking_id": 1, "currency": 1},
        ).to_list(len(folio_ids))
        for folio in folios:
            folio_id = str(folio.get("id") or "")
            booking_id = str(folio.get("booking_id") or "")
            if folio_id and booking_id:
                folio_booking[folio_id] = booking_id
                booking_ids.add(booking_id)

    booking_currency: dict[str, str] = {}
    if booking_ids:
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "id": {"$in": list(booking_ids)}},
            {"_id": 0, "id": 1, "currency": 1},
        ).to_list(len(booking_ids))
        booking_currency = {
            str(booking["id"]): _currency_code(booking.get("currency"), fallback)
            for booking in bookings
            if booking.get("id")
        }
    return booking_currency, folio_booking


def _document_currency(
    item: dict,
    booking_currency: dict[str, str],
    folio_booking: dict[str, str],
    fallback: str,
) -> str:
    if item.get("currency"):
        return _currency_code(item["currency"], fallback)
    booking_id = str(item.get("booking_id") or "")
    if not booking_id and item.get("folio_id"):
        booking_id = folio_booking.get(str(item["folio_id"]), "")
    return booking_currency.get(booking_id, fallback)


async def _report_business_date(tenant_id: str, requested: str | None) -> str:
    if requested:
        return datetime.fromisoformat(requested[:10]).date().isoformat()
    state = await ensure_business_date_initialized(db, tenant_id)
    return str(state["business_date"])[:10]


def _active_extra_charge_query(tenant_id: str, business_date: str) -> dict:
    """Select active extras for one PMS business day, including legacy rows."""
    return {
        "tenant_id": tenant_id,
        "voided": {"$ne": True},
        **accounting_day_match(
            business_date,
            {"created_at": {"$regex": f"^{business_date}"}},
            {"date": {"$regex": f"^{business_date}"}},
        ),
    }


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
    tenant_currency, _ = await get_tenant_currency(tenant_id)
    tenant_currency = _currency_code(tenant_currency)
    payment_booking_currency, payment_folio_booking = await _currency_context(tenant_id, payments, tenant_currency)
    payments_by_method: dict[str, float] = {}
    payments_by_currency: dict[str, float] = {}
    payments_by_method_currency: dict[str, dict[str, float]] = {}
    revenue_adjustments_by_currency: dict[str, float] = {}
    for payment in payments:
        status = str(payment.get("status") or "paid").lower()
        if payment.get("voided") or status in {"void", "voided", "failed", "cancelled", "rejected"}:
            continue
        currency = _document_currency(payment, payment_booking_currency, payment_folio_booking, tenant_currency)
        adjustment = effective_revenue_adjustment(payment)
        if adjustment:
            _add_currency(revenue_adjustments_by_currency, currency, adjustment, tenant_currency)
            continue
        method = str(payment.get("payment_method") or payment.get("method") or "other").lower()
        amount = effective_collection(payment)
        if amount == 0:
            continue
        payments_by_method[method] = payments_by_method.get(method, 0.0) + amount
        _add_currency(payments_by_currency, currency, amount, tenant_currency)
        method_breakdown = payments_by_method_currency.setdefault(method, {})
        _add_currency(method_breakdown, currency, amount, tenant_currency)
    payments_by_method = {method: round(amount, 2) for method, amount in payments_by_method.items()}
    payments_total = sum(payments_by_method.values())

    extra_charges = await db.extra_charges.find(
        _active_extra_charge_query(tenant_id, business_date),
        {"_id": 0, "charge_amount": 1, "amount": 1, "currency": 1, "booking_id": 1, "folio_id": 1},
    ).to_list(10000)
    extra_booking_currency, extra_folio_booking = await _currency_context(tenant_id, extra_charges, tenant_currency)
    extras_by_currency: dict[str, float] = {}
    for charge in extra_charges:
        amount = float(charge.get("charge_amount") or charge.get("amount") or 0)
        currency = _document_currency(charge, extra_booking_currency, extra_folio_booking, tenant_currency)
        _add_currency(extras_by_currency, currency, amount, tenant_currency)
    extras_total = sum(extras_by_currency.values())

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
        {"_id": 0, "total": 1, "amount": 1, "currency": 1, "booking_id": 1, "folio_id": 1},
    ).to_list(10000)
    revenue_booking_currency, revenue_folio_booking = await _currency_context(tenant_id, posted_charges, tenant_currency)
    revenue_by_currency: dict[str, float] = {}
    for charge in posted_charges:
        amount = float(charge.get("total") or charge.get("amount") or 0)
        currency = _document_currency(charge, revenue_booking_currency, revenue_folio_booking, tenant_currency)
        _add_currency(revenue_by_currency, currency, amount, tenant_currency)
    for currency, adjustment in revenue_adjustments_by_currency.items():
        _add_currency(revenue_by_currency, currency, -adjustment, tenant_currency)
    revenue_total = sum(revenue_by_currency.values())

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
        "payments_by_currency": _rounded_breakdown(payments_by_currency),
        "payments_by_method_currency": {
            method: _rounded_breakdown(values) for method, values in sorted(payments_by_method_currency.items())
        },
        "cash_total": round(payments_by_method.get("cash", 0.0), 2),
        "extras_total": round(extras_total, 2),
        "extras_by_currency": _rounded_breakdown(extras_by_currency),
        "revenue_total": round(revenue_total, 2),
        "revenue_by_currency": _rounded_breakdown(revenue_by_currency),
        "revenue_adjustments_by_currency": _rounded_breakdown(revenue_adjustments_by_currency),
        "currency": tenant_currency,
        "revenue_basis": "posted_folio_charges",
        "open_folios": open_folios,
        "open_handovers": open_handovers,
    }


def _build_html(data: dict, hotel_name: str = "Otel") -> str:
    currency = _currency_code(data.get("currency"))
    revenue = _format_breakdown(data.get("revenue_by_currency") or {currency: data.get("revenue_total", 0)})
    payments = _format_breakdown(data.get("payments_by_currency") or {currency: data.get("payments_total", 0)})
    extras = _format_breakdown(data.get("extras_by_currency") or {currency: data.get("extras_total", 0)})
    adjustments = _format_breakdown(data.get("revenue_adjustments_by_currency") or {})
    method_breakdowns = data.get("payments_by_method_currency") or {
        method: {currency: amount} for method, amount in data.get("payments_by_method", {}).items()
    }
    cash = _format_breakdown(method_breakdowns.get("cash", {}))
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
  <div class="card"><div class="label">Toplam Gelir</div><div class="value">{revenue}</div>
    <div style="font-size:12px;color:#6b7280;margin-top:4px;">Tahsilat: {payments} · Ekstra: {extras} · Fiyat düzeltmesi: {adjustments}</div></div>
</div>

<div class="section">
  <h3>Kasa Tahsilat Özeti</h3>
  <table>
    <tr><th>Ödeme Yöntemi</th><th>Tutar</th></tr>
    {''.join(f'<tr><td>{escape(str(method))}</td><td>{_format_breakdown(amounts)}</td></tr>' for method, amounts in sorted(method_breakdowns.items())) or '<tr><td colspan="2">Tahsilat bulunmuyor</td></tr>'}
    <tr><th>Nakit Tahsilat</th><th>{cash}</th></tr>
    <tr><th>Toplam Tahsilat</th><th>{payments}</th></tr>
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
            body=(f"Doluluk %{data.get('occupancy_rate', 0)} · Gelir {_format_breakdown(data.get('revenue_by_currency') or {data.get('currency', 'TRY'): data.get('revenue_total', 0)})}"),
            data={
                "type": "eod_ready",
                "business_date": bd,
                "occupancy_rate": data.get("occupancy_rate"),
                "revenue_total": data.get("revenue_total"),
                "revenue_by_currency": data.get("revenue_by_currency"),
            },
            departments=["gm", "general_manager", "admin", "supervisor"],
            priority="default",
        )
    except Exception:
        # Best-effort — email send already succeeded above.
        pass

    return {"sent": sent, "total": len(results), "business_date": bd, "results": results, "summary": data}
