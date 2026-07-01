"""
WhatsApp Business Integration
Simplified version - requires WhatsApp Business API credentials
"""

import logging

logger = logging.getLogger(__name__)


class WhatsAppService:
    """WhatsApp Business service"""

    def __init__(self):
        # A real WhatsApp Business API transport is not implemented yet.
        # Until it is, sends are reported honestly as "not delivered" so
        # callers fail closed instead of claiming a fake success
        # (doctrine: no fake-green / fail-closed).
        self.configured = False

    def _deliver(self, phone: str, message: str, label: str) -> bool:
        # No real WhatsApp Business API transport is configured. Report
        # honestly that the message was not delivered (fail-closed). Do NOT
        # log the phone number or message body: they contain guest PII
        # (name, stay dates, amount, booking id) — doctrine: no PII in logs.
        logger.info("[whatsapp:%s] not delivered (integration not configured)", label)
        return False

    async def send_booking_confirmation(self, phone: str, booking_details: dict) -> bool:
        """Send booking confirmation message"""
        message = f"""
🏨 *Syroce - Booking Confirmation*

Dear {booking_details["guest_name"]},

Your reservation number: *{booking_details["booking_id"][:8].upper()}*

📅 Check-in: {booking_details["check_in"]}
📅 Check-out: {booking_details["check_out"]}
🛏️ Room: {booking_details["room_type"]}
💰 Total: €{booking_details["total_amount"]}

✅ Online check-in available at: https://syroce.com/checkin/{booking_details["booking_id"]}

See you soon!
"""

        return self._deliver(phone, message, "booking_confirmation")

    async def send_pre_arrival_message(self, phone: str, guest_name: str, checkin_date: str) -> bool:
        """Send pre-arrival message"""
        message = f"""
✨ Hello {guest_name}!

We look forward to welcoming you to our hotel tomorrow.

🎁 *Special Offers:*
- 🛏️ Deluxe Upgrade - Only €75
- ⏰ Early Check-in - Only €35
- 💆 Spa Package - 20% Discount

Reply to claim an offer!

Syroce Team 🌟
"""

        return self._deliver(phone, message, "pre_arrival")

    async def send_upsell_offer(self, phone: str, offer_details: dict) -> bool:
        """Send upsell offer"""
        message = f"""
💎 *Special Offer - Just for You!*

{offer_details["title"]}

{offer_details["description"]}

~~€{offer_details["original_price"]}~~ ➡️ *€{offer_details["discounted_price"]}*

💚 Save €{offer_details["savings"]}!

Reply 'YES' to accept.
"""

        return self._deliver(phone, message, "upsell")


whatsapp_service = WhatsAppService()
