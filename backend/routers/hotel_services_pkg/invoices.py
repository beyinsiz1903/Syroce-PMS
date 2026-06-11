"""Auto-split from hotel_services.py — backward-compatible sub-router."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import require_op
from security.encrypted_lookup import decrypt_guest_doc

from ._common import (
    InvoiceItemSelection,
    _e,
    _safe_logo_src,
)

logger = logging.getLogger(__name__)
sub_router = APIRouter()


@sub_router.get("/reservations/{booking_id}/invoice-pdf")
async def generate_invoice_pdf(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Generate a PDF invoice from reservation folio."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Get booking
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    # Get folio entries
    folios = []
    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        folios.append(f)

    # Get payments
    payments = []
    async for p in db.payments.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        payments.append(p)

    # Get hotel settings
    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    if not settings:
        tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "hotel_name": tenant.get("property_name", "Hotel") if tenant else "Hotel",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", "") if tenant else "",
            "hotel_email": tenant.get("email", "") if tenant else "",
            "tax_id": "",
            "tax_office": "",
            "logo_data": None,
            "invoice_footer": "",
            "currency_symbol": "₺",
        }

    # Get guest info
    guest = None
    if booking.get("guest_id"):
        guest = decrypt_guest_doc(await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0}))

    # Build invoice data
    invoice_number = f"INV-{datetime.now(UTC).strftime('%Y%m%d')}-{booking_id[:8].upper()}"

    # Calculate totals
    total_payments = sum(p.get("amount", 0) for p in payments)

    # Also include accommodation total
    accommodation_total = booking.get("total_amount", 0)

    # Generate HTML for PDF
    currency = settings.get("currency_symbol", "₺")

    logo_html = ""
    safe_logo = _safe_logo_src(settings.get("logo_data"))
    if safe_logo:
        logo_html = f'<img src="{_e(safe_logo)}" style="max-height:80px;max-width:200px;" />'

    folio_rows = ""
    if accommodation_total > 0:
        folio_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">Konaklama</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{_e(booking.get("check_in",""))[:10]} - {_e(booking.get("check_out",""))[:10]}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{_e(currency)}{accommodation_total:,.2f}</td>
        </tr>"""

    for f in folios:
        if f.get("type") == "payment":
            continue
        folio_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{_e(f.get("description", f.get("category", "Masraf")))}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{_e((f.get("created_at",""))[:10])}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{_e(currency)}{f.get("amount",0):,.2f}</td>
        </tr>"""

    payment_rows = ""
    for p in payments:
        method_label = {"cash": "Nakit", "card": "Kredi Karti", "bank_transfer": "Havale/EFT", "online": "Online"}.get(p.get("method", ""), p.get("method", ""))
        payment_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{_e(method_label)}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{_e((p.get("created_at",""))[:10])}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{_e(currency)}{p.get("amount",0):,.2f}</td>
        </tr>"""

    grand_total = accommodation_total + sum(f.get("amount", 0) for f in folios if f.get("type") != "payment")
    balance = grand_total - total_payments

    guest_name = guest.get("name", booking.get("guest_name", "-")) if guest else booking.get("guest_name", "-")
    guest_email = guest.get("email", "") if guest else ""
    guest_phone = guest.get("phone", "") if guest else ""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:40px; color:#333; font-size:13px; }}
.header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:30px; border-bottom:3px solid #1a56db; padding-bottom:20px; }}
.hotel-info {{ text-align:right; }}
.hotel-name {{ font-size:22px; font-weight:700; color:#1a56db; }}
.invoice-title {{ font-size:28px; font-weight:700; color:#1a56db; margin:20px 0 10px; }}
.info-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:25px; }}
.info-box {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; }}
.info-box h3 {{ margin:0 0 8px; font-size:13px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:20px; }}
th {{ background:#f1f5f9; padding:10px 8px; text-align:left; font-weight:600; font-size:12px; color:#475569; text-transform:uppercase; }}
.total-row {{ font-weight:700; background:#f0f9ff; }}
.balance-row {{ font-weight:700; font-size:16px; background:#eff6ff; color:#1a56db; }}
.footer {{ margin-top:40px; padding-top:20px; border-top:2px solid #e2e8f0; text-align:center; color:#94a3b8; font-size:11px; }}
</style></head><body>

<div class="header">
    <div>{logo_html}</div>
    <div class="hotel-info">
        <div class="hotel-name">{_e(settings.get("hotel_name",""))}</div>
        <div>{_e(settings.get("hotel_address",""))}</div>
        <div>{_e(settings.get("hotel_phone",""))}</div>
        <div>{_e(settings.get("hotel_email",""))}</div>
        {f'<div>Vergi No: {_e(settings.get("tax_id",""))}</div>' if settings.get("tax_id") else ''}
        {f'<div>Vergi Dairesi: {_e(settings.get("tax_office",""))}</div>' if settings.get("tax_office") else ''}
    </div>
</div>

<div class="invoice-title">FATURA</div>
<div style="margin-bottom:20px;color:#64748b;">
    Fatura No: <strong>{_e(invoice_number)}</strong><br>
    Tarih: <strong>{datetime.now(UTC).strftime("%d.%m.%Y")}</strong>
</div>

<div class="info-grid">
    <div class="info-box">
        <h3>Misafir Bilgileri</h3>
        <div><strong>{_e(guest_name)}</strong></div>
        {f'<div>{_e(guest_email)}</div>' if guest_email else ''}
        {f'<div>{_e(guest_phone)}</div>' if guest_phone else ''}
    </div>
    <div class="info-box">
        <h3>Rezervasyon Bilgileri</h3>
        <div>Oda: <strong>{_e(booking.get("room_number","-"))}</strong></div>
        <div>Giris: <strong>{_e((booking.get("check_in",""))[:10])}</strong></div>
        <div>Cikis: <strong>{_e((booking.get("check_out",""))[:10])}</strong></div>
    </div>
</div>

<h3 style="color:#1a56db;margin-bottom:8px;">Masraflar</h3>
<table>
    <thead><tr>
        <th>Aciklama</th>
        <th>Tarih</th>
        <th style="text-align:right;">Tutar</th>
    </tr></thead>
    <tbody>
        {folio_rows}
        <tr class="total-row">
            <td colspan="2" style="padding:10px 8px;">TOPLAM MASRAF</td>
            <td style="padding:10px 8px;text-align:right;">{_e(currency)}{grand_total:,.2f}</td>
        </tr>
    </tbody>
</table>

<h3 style="color:#1a56db;margin-bottom:8px;">Odemeler</h3>
<table>
    <thead><tr>
        <th>Odeme Yontemi</th>
        <th>Tarih</th>
        <th style="text-align:right;">Tutar</th>
    </tr></thead>
    <tbody>
        {payment_rows if payment_rows else '<tr><td colspan="3" style="padding:8px;text-align:center;color:#94a3b8;">Henuz odeme yok</td></tr>'}
        <tr class="total-row">
            <td colspan="2" style="padding:10px 8px;">TOPLAM ODEME</td>
            <td style="padding:10px 8px;text-align:right;">{_e(currency)}{total_payments:,.2f}</td>
        </tr>
    </tbody>
</table>

<table>
    <tr class="balance-row">
        <td colspan="2" style="padding:12px 8px;font-size:16px;">KALAN BAKIYE</td>
        <td style="padding:12px 8px;text-align:right;font-size:16px;">{_e(currency)}{balance:,.2f}</td>
    </tr>
</table>

<div class="footer">
    {_e(settings.get("invoice_footer", "") or "Bizi tercih ettiginiz icin tesekkur ederiz.")}
    <br><br>
    {_e(settings.get("hotel_name",""))} | {_e(settings.get("hotel_address",""))} | {_e(settings.get("hotel_phone",""))}
</div>

</body></html>"""

    return {
        "success": True,
        "invoice_html": html,
        "invoice_number": invoice_number,
        "booking_id": booking_id,
        "guest_name": guest_name,
        "total_charges": grand_total,
        "total_payments": total_payments,
        "balance": balance,
    }


# ═══════════════════════════════════════════════════
# 6. GROUP FOLIO MERGING
# ═══════════════════════════════════════════════════



@sub_router.get("/reservations/{booking_id}/voucher")
async def generate_voucher(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    guest = None
    if booking.get("guest_id"):
        guest = decrypt_guest_doc(await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0}))

    room = None
    if booking.get("room_id"):
        room = await db.rooms.find_one({"id": booking["room_id"], "tenant_id": tid}, {"_id": 0})

    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    if not settings:
        tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "hotel_name": tenant.get("property_name", "Hotel") if tenant else "Hotel",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", "") if tenant else "",
            "hotel_email": tenant.get("email", "") if tenant else "",
        }

    guest_name = guest.get("name", booking.get("guest_name", "-")) if guest else booking.get("guest_name", "-")
    nights = max(1, (datetime.fromisoformat(str(booking.get("check_out", ""))[:10]) - datetime.fromisoformat(str(booking.get("check_in", ""))[:10])).days)

    voucher_no = f"V-{datetime.now(UTC).strftime('%Y%m%d')}-{booking_id[:8].upper()}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:40px; color:#333; font-size:13px; }}
.voucher {{ border: 2px solid #1a56db; border-radius: 12px; padding: 32px; max-width: 700px; margin: 0 auto; }}
.header {{ text-align: center; border-bottom: 2px solid #1a56db; padding-bottom: 16px; margin-bottom: 24px; }}
.hotel-name {{ font-size: 24px; font-weight: 700; color: #1a56db; }}
.voucher-title {{ font-size: 20px; font-weight: 600; color: #1e293b; margin-top: 8px; }}
.voucher-no {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
.info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
.info-item {{ padding: 12px; background: #f8fafc; border-radius: 8px; }}
.info-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; }}
.info-value {{ font-size: 14px; font-weight: 600; color: #1e293b; margin-top: 4px; }}
.footer {{ text-align: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 11px; }}
</style></head><body>
<div class="voucher">
    <div class="header">
        <div class="hotel-name">{_e(settings.get("hotel_name", ""))}</div>
        <div style="font-size:12px;color:#64748b;">{_e(settings.get("hotel_address", ""))}</div>
        <div class="voucher-title">KONAKLAMA VOUCHER</div>
        <div class="voucher-no">Voucher No: {_e(voucher_no)}</div>
    </div>
    <div class="info-grid">
        <div class="info-item"><div class="info-label">Misafir</div><div class="info-value">{_e(guest_name)}</div></div>
        <div class="info-item"><div class="info-label">Rezervasyon No</div><div class="info-value">{_e(booking.get("ota_confirmation", booking_id[:12]))}</div></div>
        <div class="info-item"><div class="info-label">Giris Tarihi</div><div class="info-value">{_e(str(booking.get("check_in",""))[:10])}</div></div>
        <div class="info-item"><div class="info-label">Cikis Tarihi</div><div class="info-value">{_e(str(booking.get("check_out",""))[:10])}</div></div>
        <div class="info-item"><div class="info-label">Oda / Tip</div><div class="info-value">{_e(booking.get("room_number", room.get("room_number","-") if room else "-"))} / {_e(room.get("room_type","") if room else booking.get("room_type",""))}</div></div>
        <div class="info-item"><div class="info-label">Gece Sayisi</div><div class="info-value">{nights}</div></div>
        <div class="info-item"><div class="info-label">Yetiskin / Cocuk</div><div class="info-value">{int(booking.get("adults",1) or 0)} / {int(booking.get("children",0) or 0)}</div></div>
        <div class="info-item"><div class="info-label">Pansiyon</div><div class="info-value">{_e(booking.get("rate_plan","Standart"))}</div></div>
    </div>
    {f'<div style="padding:12px;background:#fffbeb;border-radius:8px;margin-bottom:16px;"><strong>Ozel Istekler:</strong> {_e(booking.get("special_requests",""))}</div>' if booking.get("special_requests") else ''}
    <div class="footer">
        <div>Bu voucher {_e(settings.get("hotel_name",""))} tarafindan duzenlenmistir.</div>
        <div>{_e(settings.get("hotel_phone",""))} | {_e(settings.get("hotel_email",""))}</div>
        <div style="margin-top:8px;">Tarih: {datetime.now(UTC).strftime("%d.%m.%Y %H:%M")}</div>
    </div>
</div>
</body></html>"""

    return {"success": True, "voucher_html": html, "voucher_no": voucher_no}


# ═══════════════════════════════════════════════════
# 12. ADVANCED INVOICE WITH ITEM SELECTION
# ═══════════════════════════════════════════════════


@sub_router.post("/reservations/{booking_id}/generate-invoice")
async def generate_custom_invoice(
    booking_id: str,
    body: InvoiceItemSelection,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v97 DW
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    guest = None
    if booking.get("guest_id"):
        guest = decrypt_guest_doc(await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0}))

    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    if not settings:
        tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "hotel_name": tenant.get("property_name", "Hotel") if tenant else "Hotel",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", "") if tenant else "",
            "hotel_email": tenant.get("email", "") if tenant else "",
            "tax_id": "", "tax_office": "", "currency_symbol": "₺", "invoice_footer": "",
        }

    all_charges = []
    if booking.get("total_amount", 0) > 0:
        all_charges.append({
            "id": "accommodation",
            "description": "Konaklama",
            "date": str(booking.get("check_in", ""))[:10],
            "amount": booking["total_amount"],
            "category": "room",
        })

    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid, "type": {"$ne": "payment"}}, {"_id": 0}).sort("created_at", 1):
        all_charges.append({
            "id": f.get("id", ""),
            "description": f.get("description", f.get("category", "Masraf")),
            "date": str(f.get("created_at", ""))[:10],
            "amount": f.get("amount", 0),
            "category": f.get("category", "other"),
        })

    async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        all_charges.append({
            "id": ec.get("id", ""),
            "description": ec.get("description", "Ekstra"),
            "date": str(ec.get("created_at", ""))[:10],
            "amount": ec.get("total", ec.get("amount", 0)),
            "category": ec.get("category", "other"),
        })

    if body.selected_charge_ids:
        selected = [c for c in all_charges if c["id"] in body.selected_charge_ids]
    else:
        selected = all_charges

    currency = settings.get("currency_symbol", "₺")
    grand_total = sum(c["amount"] for c in selected)
    invoice_number = f"INV-{datetime.now(UTC).strftime('%Y%m%d%H%M')}-{booking_id[:6].upper()}"

    guest_name = body.billing_name or (guest.get("name", booking.get("guest_name", "-")) if guest else booking.get("guest_name", "-"))

    charge_rows = ""
    for c in selected:
        charge_rows += f"""<tr>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;">{_e(c["description"])}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;text-align:center;">{_e(c["date"])}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:600;">{_e(currency)}{c["amount"]:,.2f}</td>
        </tr>"""

    logo_html = ""
    safe_logo = _safe_logo_src(settings.get("logo_data"))
    if safe_logo:
        logo_html = f'<img src="{_e(safe_logo)}" style="max-height:70px;max-width:180px;" />'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:0; color:#1e293b; font-size:13px; background:#fff; }}
.page {{ max-width:800px; margin:0 auto; padding:40px; }}
.header {{ display:flex; justify-content:space-between; align-items:flex-start; padding-bottom:24px; border-bottom:3px solid #1a56db; margin-bottom:28px; }}
.hotel-info {{ text-align:right; }}
.hotel-name {{ font-size:20px; font-weight:700; color:#1a56db; margin-bottom:4px; }}
.hotel-detail {{ font-size:11px; color:#64748b; line-height:1.6; }}
.invoice-badge {{ display:inline-block; background:linear-gradient(135deg,#1a56db,#3b82f6); color:#fff; padding:6px 16px; border-radius:6px; font-size:18px; font-weight:700; letter-spacing:1px; margin-bottom:12px; }}
.invoice-meta {{ color:#64748b; font-size:12px; line-height:1.8; }}
.invoice-meta strong {{ color:#1e293b; }}
.bill-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:28px; }}
.bill-box {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; }}
.bill-box h4 {{ margin:0 0 8px; font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; font-weight:600; }}
.bill-box p {{ margin:2px 0; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:24px; }}
thead th {{ background:#f1f5f9; padding:10px 12px; text-align:left; font-weight:600; font-size:11px; color:#475569; text-transform:uppercase; letter-spacing:0.5px; }}
.total-section {{ background:#f0f9ff; border:2px solid #bfdbfe; border-radius:8px; padding:16px; text-align:right; }}
.total-section .grand {{ font-size:20px; font-weight:700; color:#1a56db; }}
.footer {{ margin-top:40px; padding-top:20px; border-top:2px solid #e2e8f0; text-align:center; color:#94a3b8; font-size:10px; line-height:1.8; }}
</style></head><body>
<div class="page">
    <div class="header">
        <div>{logo_html}<div class="invoice-badge">FATURA</div>
            <div class="invoice-meta">Fatura No: <strong>{_e(invoice_number)}</strong><br>Tarih: <strong>{datetime.now(UTC).strftime("%d.%m.%Y")}</strong></div>
        </div>
        <div class="hotel-info">
            <div class="hotel-name">{_e(settings.get("hotel_name",""))}</div>
            <div class="hotel-detail">
                {_e(settings.get("hotel_address",""))}<br>
                Tel: {_e(settings.get("hotel_phone",""))}<br>
                {_e(settings.get("hotel_email",""))}
                {f"<br>Vergi No: {_e(settings.get('tax_id',''))}" if settings.get("tax_id") else ""}
                {f"<br>V.D.: {_e(settings.get('tax_office',''))}" if settings.get("tax_office") else ""}
            </div>
        </div>
    </div>

    <div class="bill-grid">
        <div class="bill-box">
            <h4>Fatura Edilen</h4>
            <p><strong>{_e(guest_name)}</strong></p>
            {f"<p>Vergi No: {_e(body.billing_tax_id)}</p>" if body.billing_tax_id else ""}
            {f"<p>V.D.: {_e(body.billing_tax_office)}</p>" if body.billing_tax_office else ""}
            {f"<p>{_e(body.billing_address)}</p>" if body.billing_address else ""}
            {f"<p>{_e(body.billing_email)}</p>" if body.billing_email else ""}
        </div>
        <div class="bill-box">
            <h4>Konaklama Bilgileri</h4>
            <p>Oda: <strong>{_e(booking.get("room_number","-"))}</strong></p>
            <p>Giris: <strong>{_e(str(booking.get("check_in",""))[:10])}</strong></p>
            <p>Cikis: <strong>{_e(str(booking.get("check_out",""))[:10])}</strong></p>
            <p>Rez. No: <strong>{_e(booking.get("ota_confirmation", booking_id[:12]))}</strong></p>
        </div>
    </div>

    <table>
        <thead><tr><th>Aciklama</th><th style="text-align:center;">Tarih</th><th style="text-align:right;">Tutar</th></tr></thead>
        <tbody>{charge_rows}</tbody>
    </table>

    <div class="total-section">
        <div class="grand">TOPLAM: {_e(currency)}{grand_total:,.2f}</div>
    </div>

    {f'<div style="margin-top:16px;padding:12px;background:#fffbeb;border-radius:8px;font-size:12px;">{_e(body.invoice_note)}</div>' if body.invoice_note else ''}

    <div class="footer">
        {_e(settings.get("invoice_footer", "") or "Bizi tercih ettiginiz icin tesekkur ederiz.")}<br>
        {_e(settings.get("hotel_name",""))} | {_e(settings.get("hotel_address",""))} | {_e(settings.get("hotel_phone",""))}
    </div>
</div>
</body></html>"""

    await db.invoices.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "invoice_number": invoice_number,
        "billing_name": guest_name,
        "billing_tax_id": body.billing_tax_id,
        "total": grand_total,
        "item_count": len(selected),
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    })

    return {
        "success": True,
        "invoice_html": html,
        "invoice_number": invoice_number,
        "total": grand_total,
        "all_charges": all_charges,
    }


# ═══════════════════════════════════════════════════
# 13. GET INVOICE CHARGES (for frontend item selection)
# ═══════════════════════════════════════════════════

@sub_router.get("/reservations/{booking_id}/invoice-charges")
async def get_invoice_charges(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    charges = []
    if booking.get("total_amount", 0) > 0:
        charges.append({
            "id": "accommodation",
            "description": "Konaklama",
            "category": "room",
            "amount": booking["total_amount"],
            "date": str(booking.get("check_in", ""))[:10],
        })

    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid, "type": {"$ne": "payment"}}, {"_id": 0}).sort("created_at", 1):
        charges.append({
            "id": f.get("id", ""),
            "description": f.get("description", f.get("category", "Masraf")),
            "category": f.get("category", "other"),
            "amount": f.get("amount", 0),
            "date": str(f.get("created_at", ""))[:10],
        })

    async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        charges.append({
            "id": ec.get("id", ""),
            "description": ec.get("description", "Ekstra"),
            "category": ec.get("category", "other"),
            "amount": ec.get("total", ec.get("amount", 0)),
            "date": str(ec.get("created_at", ""))[:10],
        })

    return {"charges": charges}


# ═══════════════════════════════════════════════════
# 14. ROOM CHANGE WITH ROOM TYPE FILTER AND PRICING
# ═══════════════════════════════════════════════════


