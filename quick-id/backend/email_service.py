"""
E-posta Bildirim Servisi (MOCK)
- Check-in/Check-out bildirimleri
- KVKK hak talep bildirimleri
- Sistem uyarilari

NOT: Bu servis MOCK modunda calisir. Gercek e-posta gondermek icin
SMTP ayarlarini yapilandirin veya SendGrid/SES entegrasyonu ekleyin.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("quickid.email")

# SMTP Configuration (not connected - MOCK mode)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@quickid.hotel")
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER)

# In-memory log of sent emails (for mock mode)
email_log = []


def is_email_configured() -> bool:
    return EMAIL_ENABLED


async def send_email(to: str, subject: str, body_html: str, body_text: str = "", 
                     template_name: str = "", metadata: dict = None) -> dict:
    """E-posta gonder (MOCK modunda sadece loglar)"""
    email_record = {
        "to": to,
        "subject": subject,
        "template": template_name,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "mock": not EMAIL_ENABLED,
    }

    if EMAIL_ENABLED:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = SMTP_FROM
            msg['To'] = to

            if body_text:
                msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)

            email_record["status"] = "sent"
            logger.info(f"Email sent: {subject} -> {to}")
        except Exception as e:
            email_record["status"] = "failed"
            email_record["error"] = str(e)
            logger.error(f"Email failed: {subject} -> {to}: {e}")
    else:
        email_record["status"] = "mocked"
        logger.info(f"[MOCK] Email: {subject} -> {to}")

    email_log.append(email_record)
    # Keep only last 100 entries
    if len(email_log) > 100:
        email_log.pop(0)

    return email_record


# ===== Notification Templates =====

async def notify_checkin(guest_name: str, room_number: str = "", admin_email: str = ""):
    """Check-in bildirimi"""
    subject = f"Check-in: {guest_name}"
    body = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;">
        <h2 style="color:#0B5E8A;">Yeni Check-in</h2>
        <p><strong>Misafir:</strong> {guest_name}</p>
        {f'<p><strong>Oda:</strong> {room_number}</p>' if room_number else ''}
        <p><strong>Tarih:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        <hr style="border:none;border-top:1px solid #eee;">
        <p style="color:#888;font-size:12px;">Quick ID Reader - Otel Kimlik Okuyucu</p>
    </div>
    """
    return await send_email(admin_email or SMTP_FROM, subject, body, template_name="checkin", metadata={"guest": guest_name})


async def notify_checkout(guest_name: str, room_number: str = "", admin_email: str = ""):
    """Check-out bildirimi"""
    subject = f"Check-out: {guest_name}"
    body = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;">
        <h2 style="color:#0B5E8A;">Check-out</h2>
        <p><strong>Misafir:</strong> {guest_name}</p>
        {f'<p><strong>Oda:</strong> {room_number}</p>' if room_number else ''}
        <p><strong>Tarih:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        <hr style="border:none;border-top:1px solid #eee;">
        <p style="color:#888;font-size:12px;">Quick ID Reader - Otel Kimlik Okuyucu</p>
    </div>
    """
    return await send_email(admin_email or SMTP_FROM, subject, body, template_name="checkout", metadata={"guest": guest_name})


async def notify_kvkk_request(request_type: str, requester_name: str, admin_email: str = ""):
    """KVKK hak talep bildirimi"""
    type_labels = {"access": "Erisim", "rectification": "Duzeltme", "erasure": "Silme", "portability": "Tasinabilirlik", "objection": "Itiraz"}
    subject = f"KVKK Hak Talebi: {type_labels.get(request_type, request_type)} - {requester_name}"
    body = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;">
        <h2 style="color:#D97706;">Yeni KVKK Hak Talebi</h2>
        <p><strong>Talep Eden:</strong> {requester_name}</p>
        <p><strong>Talep Turu:</strong> {type_labels.get(request_type, request_type)}</p>
        <p><strong>Tarih:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        <p style="color:#D97706;">30 gun icinde yanitlanmasi gerekmektedir.</p>
        <hr style="border:none;border-top:1px solid #eee;">
        <p style="color:#888;font-size:12px;">Quick ID Reader - KVKK Uyumluluk</p>
    </div>
    """
    return await send_email(admin_email or SMTP_FROM, subject, body, template_name="kvkk_request", metadata={"type": request_type})


async def notify_system_alert(title: str, message: str, admin_email: str = ""):
    """Sistem uyari bildirimi"""
    subject = f"Sistem Uyarisi: {title}"
    body = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;">
        <h2 style="color:#DC2626;">Sistem Uyarisi</h2>
        <p><strong>{title}</strong></p>
        <p>{message}</p>
        <p><strong>Tarih:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        <hr style="border:none;border-top:1px solid #eee;">
        <p style="color:#888;font-size:12px;">Quick ID Reader</p>
    </div>
    """
    return await send_email(admin_email or SMTP_FROM, subject, body, template_name="system_alert")


def get_email_log(limit: int = 50) -> list:
    """Son e-posta loglarini getir"""
    return list(reversed(email_log[-limit:]))


def get_email_status() -> dict:
    """E-posta servis durumu"""
    return {
        "configured": EMAIL_ENABLED,
        "mode": "live" if EMAIL_ENABLED else "mock",
        "smtp_host": SMTP_HOST or "(yapilandirilmamis)",
        "from_address": SMTP_FROM,
        "total_sent": len(email_log),
        "last_sent": email_log[-1] if email_log else None,
    }
