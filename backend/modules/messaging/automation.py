"""
Messaging Automation Engine.
Processes booking events and triggers automated messages based on configured rules.

Trigger Events:
- booking_confirmed: Rezervasyon onaylandi
- pre_arrival: Check-in oncesi (1 gun once, scheduler ile)
- checked_in: Misafir check-in yapti
- checked_out: Misafir check-out yapti
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

TRIGGER_EVENTS = {
    "booking_confirmed": {
        "label": "Rezervasyon Onaylandi",
        "description": "Rezervasyon durumu confirmed olunca",
        "default_channel": "email",
        "default_category": "rezervasyon_onay",
    },
    "pre_arrival": {
        "label": "Check-in Oncesi",
        "description": "Giris tarihinden 1 gun once (otomatik kontrol)",
        "default_channel": "whatsapp",
        "default_category": "yol_tarifi",
    },
    "checked_in": {
        "label": "Check-in Yapildi",
        "description": "Misafir check-in yapinca",
        "default_channel": "whatsapp",
        "default_category": "hosgeldiniz",
    },
    "checked_out": {
        "label": "Check-out Yapildi",
        "description": "Misafir check-out yapinca",
        "default_channel": "email",
        "default_category": "checkout",
    },
}


def new_automation_rule(
    tenant_id: str,
    trigger_event: str,
    template_id: str,
    channel: str,
    name: str,
    enabled: bool = True,
    delay_minutes: int = 0,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "trigger_event": trigger_event,
        "template_id": template_id,
        "channel": channel,
        "name": name,
        "enabled": enabled,
        "delay_minutes": delay_minutes,
        "total_sent": 0,
        "total_failed": 0,
        "last_triggered_at": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


async def _get_db():
    from server import db
    return db


async def process_booking_event(tenant_id: str, event_type: str, booking: dict):
    """
    Called when a booking status changes.
    Finds matching automation rules and sends messages.
    """
    if event_type not in TRIGGER_EVENTS:
        return

    try:
        db = await _get_db()

        rules = await db.messaging_automation_rules.find(
            {"tenant_id": tenant_id, "trigger_event": event_type, "enabled": True},
            {"_id": 0},
        ).to_list(20)

        if not rules:
            return

        guest = None
        guest_id = booking.get("guest_id")
        if guest_id:
            guest = await db.guests.find_one(
                {"id": guest_id, "tenant_id": tenant_id}, {"_id": 0}
            )

        room = None
        room_id = booking.get("room_id")
        if room_id:
            room = await db.rooms.find_one(
                {"id": room_id, "tenant_id": tenant_id}, {"_id": 0}
            )

        tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})

        variables = _build_template_variables(booking, guest, room, tenant)

        recipient_email = guest.get("email", "") if guest else ""
        recipient_phone = guest.get("phone", "") if guest else ""

        for rule in rules:
            try:
                recipient = recipient_email if rule["channel"] == "email" else recipient_phone
                if not recipient:
                    logger.warning(
                        f"Automation {rule['id']}: {rule['channel']} alici bilgisi yok (booking={booking.get('id')})"
                    )
                    await db.messaging_automation_rules.update_one(
                        {"id": rule["id"]},
                        {"$inc": {"total_failed": 1}, "$set": {"last_triggered_at": datetime.now(UTC).isoformat()}},
                    )
                    continue

                template = None
                if rule.get("template_id"):
                    template = await db.messaging_templates.find_one(
                        {"id": rule["template_id"], "tenant_id": tenant_id}, {"_id": 0}
                    )

                # v41 Bug BG: HTML-escape variables when channel renders HTML.
                _esc_html = rule["channel"] in ("email",)
                body = _render_template(template, variables, escape_html=_esc_html) if template else f"Otomatik bildirim: {event_type}"
                subject = _render_subject(template, variables) if template else None

                from modules.messaging.service import MessagingService
                svc = MessagingService(db)
                result = await svc.send_message(
                    tenant_id=tenant_id,
                    channel=rule["channel"],
                    recipient=recipient,
                    body=body,
                    subject=subject,
                    template_id=rule.get("template_id"),
                    variables=variables,
                    booking_id=booking.get("id"),
                    guest_id=guest_id,
                    use_case=event_type,
                )

                if result.get("success"):
                    await db.messaging_automation_rules.update_one(
                        {"id": rule["id"]},
                        {"$inc": {"total_sent": 1}, "$set": {"last_triggered_at": datetime.now(UTC).isoformat()}},
                    )
                    logger.info(f"Automation sent: {rule['name']} -> {recipient} ({rule['channel']})")
                    # Create in-app notification for success
                    await _create_automation_notification(
                        db, tenant_id, success=True,
                        rule_name=rule["name"],
                        guest_name=variables.get("misafir_adi", "Misafir"),
                        channel=rule["channel"],
                        event_type=event_type,
                    )
                else:
                    await db.messaging_automation_rules.update_one(
                        {"id": rule["id"]},
                        {"$inc": {"total_failed": 1}, "$set": {"last_triggered_at": datetime.now(UTC).isoformat()}},
                    )
                    logger.warning(f"Automation failed: {rule['name']} -> {result.get('error')}")
                    # Create in-app notification for failure
                    await _create_automation_notification(
                        db, tenant_id, success=False,
                        rule_name=rule["name"],
                        guest_name=variables.get("misafir_adi", "Misafir"),
                        channel=rule["channel"],
                        event_type=event_type,
                        error=result.get("error", ""),
                    )

            except Exception as e:
                logger.exception(f"Automation rule {rule.get('id')} failed: {e}")

    except Exception as e:
        logger.exception(f"process_booking_event error: {e}")


def _build_template_variables(booking: dict, guest: dict | None, room: dict | None, tenant: dict | None) -> dict:
    """Build a dict of template variables from booking context."""
    v = {
        "misafir_adi": guest.get("name", "") if guest else booking.get("guest_name", "Misafir"),
        "otel_adi": tenant.get("name", "Otel") if tenant else "Otel",
        "oda_no": room.get("room_number", "") if room else booking.get("room_number", ""),
        "oda_tipi": room.get("type", "") if room else "",
        "giris_tarihi": _format_date(booking.get("check_in", "")),
        "cikis_tarihi": _format_date(booking.get("check_out", "")),
        "konfirmasyon_no": booking.get("id", "")[:8].upper(),
        "toplam_tutar": str(booking.get("total_amount", "")),
        "wifi_sifre": "Hotel2026",
        "restoran_saatleri": "07:00-10:00 / 12:00-14:00 / 19:00-22:00",
        "havuz_saatleri": "08:00-20:00",
        "spa_saatleri": "10:00-21:00",
        "telefon": tenant.get("phone", "") if tenant else "",
        "email": tenant.get("email", "") if tenant else "",
        "adres": tenant.get("address", "") if tenant else "",
        "harita_link": "https://maps.google.com",
        "transfer_bilgi": "Detaylar icin resepsiyonu arayiniz",
        "degerlendirme_link": "https://g.page/review",
        "fatura_no": booking.get("id", "")[:8].upper(),
    }
    return v


def _format_date(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def _render_template(template: dict, variables: dict, escape_html: bool = False) -> str:
    # v41 Bug BG: HTML-escape variables for email/HTML channels — guest-controlled
    # fields must not inject markup into rendered email bodies.
    import html as _html_mod
    body = template.get("body_template", "")
    for key, val in variables.items():
        sv = str(val) if val is not None else ""
        if escape_html:
            sv = _html_mod.escape(sv, quote=True)
        body = body.replace(f"{{{{{key}}}}}", sv)
    return body


def _render_subject(template: dict, variables: dict) -> str | None:
    subject = template.get("subject")
    if not subject:
        return None
    for key, val in variables.items():
        subject = subject.replace(f"{{{{{key}}}}}", str(val))
    return subject


async def _create_automation_notification(
    db, tenant_id: str, success: bool,
    rule_name: str, guest_name: str, channel: str, event_type: str,
    error: str = "",
):
    """Create in-app notification for automation event results."""
    try:
        channel_label = "WhatsApp" if channel == "whatsapp" else "Email"
        event_labels = {
            "booking_confirmed": "Rez. Onay",
            "pre_arrival": "Check-in Oncesi",
            "checked_in": "Check-in",
            "checked_out": "Check-out",
        }
        event_label = event_labels.get(event_type, event_type)

        if success:
            title = f"Otomasyon: {rule_name}"
            message = f"{guest_name} icin {channel_label} mesaji gonderildi ({event_label})"
            priority = "normal"
        else:
            title = f"Otomasyon Hatasi: {rule_name}"
            message = f"{guest_name} icin {channel_label} gonderilemedi ({event_label}): {error[:100]}"
            priority = "high"

        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": None,
            "type": "messaging_automation",
            "title": title,
            "message": message,
            "priority": priority,
            "read": False,
            "action_url": "/messaging-dashboard",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.notifications.insert_one(doc)
    except Exception as e:
        logger.warning(f"Failed to create automation notification: {e}")


async def fire_booking_event(tenant_id: str, event_type: str, booking: dict):
    """
    Non-blocking fire-and-forget. Called from UpdateReservationService.
    """
    asyncio.create_task(process_booking_event(tenant_id, event_type, booking))
