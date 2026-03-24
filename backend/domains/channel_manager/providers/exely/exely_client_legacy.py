"""
Exely SOAP API Client
Handles HTTP transport for SOAP messages with retry and logging.
"""
import logging
import time
from typing import Any, Dict, Optional

import httpx

from .response_parser import (
    parse_ari_update_rs,
    parse_hotel_avail_rs,
    parse_notif_report_rs,
    parse_read_rs,
)
from .soap_builder import (
    build_ari_update_rq,
    build_hotel_avail_rq,
    build_notif_report_rq,
    build_read_rq,
)

logger = logging.getLogger(__name__)

EXELY_DEFAULT_URL = "https://www.exely.com/ota/OTA"
SOAP_CONTENT_TYPE = "text/xml; charset=utf-8"


class ExelyClient:
    """SOAP-based client for Exely channel manager API."""

    def __init__(self, username: str, password: str, hotel_code: str, endpoint_url: str = EXELY_DEFAULT_URL):
        self.username = username
        self.password = password
        self.hotel_code = hotel_code
        self.endpoint_url = endpoint_url

    async def _send_soap(self, xml_body: str, soap_action: str = "") -> bytes:
        """Send SOAP request and return raw response bytes."""
        headers = {
            "Content-Type": SOAP_CONTENT_TYPE,
            "SOAPAction": soap_action,
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.endpoint_url, content=xml_body.encode("utf-8"), headers=headers)
            duration = int((time.time() - start) * 1000)
            logger.info(f"[EXELY] SOAP {soap_action or 'POST'} -> {resp.status_code} ({duration}ms)")
            resp.raise_for_status()
            return resp.content

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection by attempting a room availability request."""
        start = time.time()
        try:
            from datetime import datetime, timedelta
            checkin = datetime.now().strftime("%Y-%m-%d")
            checkout = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            xml = build_hotel_avail_rq(self.username, self.password, self.hotel_code, checkin, checkout)
            raw = await self._send_soap(xml, "OTA_HotelAvailRQ")
            result = parse_hotel_avail_rs(raw)
            duration_ms = int((time.time() - start) * 1000)
            if result["success"]:
                return {
                    "connected": True,
                    "room_types": result["room_types"],
                    "rate_plans": result["rate_plans"],
                    "duration_ms": duration_ms,
                }
            return {"connected": False, "error": result.get("error", "Unknown"), "duration_ms": duration_ms}
        except Exception as e:
            return {"connected": False, "error": str(e), "duration_ms": int((time.time() - start) * 1000)}

    async def pull_reservations(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        reservation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Pull reservations via OTA_ReadRQ."""
        start = time.time()
        try:
            xml = build_read_rq(self.username, self.password, self.hotel_code, from_date, to_date, reservation_id)
            raw = await self._send_soap(xml, "OTA_ReadRQ")
            result = parse_read_rs(raw)
            result["duration_ms"] = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "reservations": [], "duration_ms": int((time.time() - start) * 1000)}

    async def discover_rooms(self, checkin: str, checkout: str) -> Dict[str, Any]:
        """Discover available room types and rate plans via OTA_HotelAvailRQ."""
        start = time.time()
        try:
            xml = build_hotel_avail_rq(self.username, self.password, self.hotel_code, checkin, checkout)
            raw = await self._send_soap(xml, "OTA_HotelAvailRQ")
            result = parse_hotel_avail_rs(raw)
            result["duration_ms"] = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "room_types": [], "rate_plans": [], "duration_ms": int((time.time() - start) * 1000)}

    async def confirm_delivery(self, reservation_id: str, confirmation_number: str) -> Dict[str, Any]:
        """Confirm reservation delivery via OTA_NotifReportRQ."""
        start = time.time()
        try:
            xml = build_notif_report_rq(self.username, self.password, self.hotel_code, reservation_id, confirmation_number)
            raw = await self._send_soap(xml, "OTA_NotifReportRQ")
            result = parse_notif_report_rs(raw)
            result["duration_ms"] = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "duration_ms": int((time.time() - start) * 1000)}

    async def push_ari(
        self,
        room_type_code: str, rate_plan_code: str,
        start_date: str, end_date: str,
        availability: Optional[int] = None,
        rate_amount: Optional[float] = None,
        currency: str = "TRY",
        stop_sell: Optional[bool] = None,
        min_stay: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Push ARI update via OTA_HotelAvailNotifRQ."""
        start = time.time()
        try:
            xml = build_ari_update_rq(
                self.username, self.password, self.hotel_code,
                room_type_code, rate_plan_code, start_date, end_date,
                availability, rate_amount, currency, stop_sell, min_stay,
            )
            raw = await self._send_soap(xml, "OTA_HotelAvailNotifRQ")
            result = parse_ari_update_rs(raw)
            result["duration_ms"] = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "duration_ms": int((time.time() - start) * 1000)}
