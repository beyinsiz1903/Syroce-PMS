"""
HotelRunner REST API Provider
Implements the Channel Manager provider interface for HotelRunner.

API Docs: https://developers.hotelrunner.com/custom-apps/rest-api
Auth: token + hr_id query parameters on every request
Rate Limits: 250 req/day/property, 5 req/min/property
"""
import asyncio
import logging
import time
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)

HR_BASE_URL = "https://app.hotelrunner.com/api/v2/apps"
HR_V1_BASE_URL = "https://app.hotelrunner.com/api/v1/apps"


class HotelRunnerProvider:
    """Production-grade HotelRunner API client with rate limiting and error handling."""

    def __init__(self, token: str, hr_id: str):
        self.token = token
        self.hr_id = hr_id
        self._request_count = 0
        self._minute_start = time.time()
        self._day_start = time.time()
        self._daily_count = 0

    @property
    def _auth_params(self) -> Dict[str, str]:
        return {"token": self.token, "hr_id": self.hr_id}

    async def _check_rate_limit(self):
        """Enforce HotelRunner rate limits: 5/min, 250/day."""
        now = time.time()
        if now - self._minute_start >= 60:
            self._request_count = 0
            self._minute_start = now
        if now - self._day_start >= 86400:
            self._daily_count = 0
            self._day_start = now

        if self._request_count >= 5:
            wait = 60 - (now - self._minute_start)
            logger.warning(f"HotelRunner rate limit (5/min). Waiting {wait:.1f}s")
            await asyncio.sleep(wait)
            self._request_count = 0
            self._minute_start = time.time()

        if self._daily_count >= 245:
            logger.error("HotelRunner daily limit approaching (245/250). Pausing.")
            raise Exception("HotelRunner daily API limit approaching. Aborting to preserve quota.")

    async def _request(self, method: str, url: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute an HTTP request with rate limiting and error handling."""
        await self._check_rate_limit()

        all_params = {**self._auth_params, **(params or {})}
        start = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if method == "GET":
                    resp = await client.get(url, params=all_params)
                elif method == "PUT":
                    resp = await client.put(url, params=all_params, data=data)
                elif method == "POST":
                    resp = await client.post(url, params=all_params, data=data)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                self._request_count += 1
                self._daily_count += 1
                duration_ms = int((time.time() - start) * 1000)

                result = resp.json()
                if resp.status_code != 200 or result.get("status") == "error":
                    logger.error(f"HotelRunner API error [{resp.status_code}]: {result}")
                    return {
                        "success": False,
                        "error": result.get("error", f"HTTP {resp.status_code}"),
                        "code": result.get("code"),
                        "duration_ms": duration_ms,
                    }

                return {
                    "success": True,
                    "data": result,
                    "duration_ms": duration_ms,
                }

            except httpx.TimeoutException:
                return {"success": False, "error": "Request timed out", "duration_ms": int((time.time() - start) * 1000)}
            except Exception as e:
                return {"success": False, "error": str(e), "duration_ms": int((time.time() - start) * 1000)}

    # ── Connection Test ──────────────────────────────────────────────

    async def test_connection(self) -> Dict[str, Any]:
        """Test API connection by fetching channels list."""
        result = await self._request("GET", f"{HR_BASE_URL}/infos/channels")
        if result["success"]:
            return {
                "connected": True,
                "channels": result["data"].get("channels", []),
                "duration_ms": result["duration_ms"],
            }
        return {
            "connected": False,
            "error": result["error"],
            "duration_ms": result["duration_ms"],
        }

    # ── Channels ─────────────────────────────────────────────────────

    async def get_channels(self) -> Dict[str, Any]:
        """Get all available HotelRunner channels."""
        return await self._request("GET", f"{HR_V1_BASE_URL}/infos/channels")

    async def get_connected_channels(self) -> Dict[str, Any]:
        """Get connected channels with process stats."""
        return await self._request("GET", f"{HR_BASE_URL}/infos/connected_channels")

    # ── Inventory (Rooms) ────────────────────────────────────────────

    async def get_rooms(self) -> Dict[str, Any]:
        """Get all rooms/rates of the property."""
        return await self._request("GET", f"{HR_BASE_URL}/rooms")

    async def update_room(
        self,
        inv_code: str,
        start_date: str,
        end_date: str,
        availability: Optional[int] = None,
        price: Optional[float] = None,
        stop_sale: Optional[int] = None,
        min_stay: Optional[int] = None,
        cta: Optional[int] = None,
        ctd: Optional[int] = None,
        days: Optional[List[int]] = None,
        channel_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update room ARI (Availability, Rates, Inventory).
        Only send parameters you want to update.
        """
        data = {
            "inv_code": inv_code,
            "start_date": start_date,
            "end_date": end_date,
        }
        if availability is not None:
            data["availability"] = str(availability)
        if price is not None:
            data["price"] = str(price)
        if stop_sale is not None:
            data["stop_sale"] = str(stop_sale)
        if min_stay is not None:
            data["min_stay"] = str(min_stay)
        if cta is not None:
            data["cta"] = str(cta)
        if ctd is not None:
            data["ctd"] = str(ctd)
        if days is not None:
            data["days[]"] = [str(d) for d in days]
        if channel_codes is not None:
            data["channel_codes[]"] = channel_codes

        return await self._request("PUT", f"{HR_BASE_URL}/rooms/~", data=data)

    # ── Reservations ─────────────────────────────────────────────────

    async def get_reservations(
        self,
        undelivered: bool = True,
        from_date: Optional[str] = None,
        from_last_update_date: Optional[str] = None,
        per_page: int = 10,
        page: int = 1,
        reservation_number: Optional[str] = None,
        modified: bool = False,
        booked: bool = False,
    ) -> Dict[str, Any]:
        """Retrieve reservations with pagination and filters."""
        params = {
            "undelivered": str(undelivered).lower(),
            "per_page": str(per_page),
            "page": str(page),
        }
        if from_date:
            params["from_date"] = from_date
        if from_last_update_date:
            params["from_last_update_date"] = from_last_update_date
        if reservation_number:
            params["reservation_number"] = reservation_number
        if modified:
            params["modified"] = "true"
        if booked:
            params["booked"] = "true"

        return await self._request("GET", f"{HR_BASE_URL}/reservations", params=params)

    async def confirm_delivery(self, message_uid: str, pms_number: Optional[str] = None) -> Dict[str, Any]:
        """Confirm reservation delivery to HotelRunner."""
        params = {"message_uid": message_uid}
        if pms_number:
            params["pms_number"] = pms_number
        return await self._request("PUT", f"{HR_BASE_URL}/reservations/~", params=params)

    # ── Transaction Details ──────────────────────────────────────────

    async def get_transaction_details(self, transaction_id: str) -> Dict[str, Any]:
        """Get update status logs for a transaction."""
        return await self._request(
            "GET",
            f"{HR_BASE_URL}/infos/transaction_details",
            params={"transaction_id": transaction_id},
        )

    # ── Bulk ARI Push ────────────────────────────────────────────────

    async def push_ari_bulk(self, updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Push multiple ARI updates sequentially (respecting rate limits).
        Each update dict should have: inv_code, start_date, end_date, and optional fields.
        """
        results = []
        for update in updates:
            result = await self.update_room(**update)
            results.append({
                "inv_code": update["inv_code"],
                "start_date": update["start_date"],
                "end_date": update["end_date"],
                **result,
            })
        return results

    # ── Reservation Sync (Pull + Confirm) ────────────────────────────

    async def sync_reservations(self) -> Dict[str, Any]:
        """
        Pull undelivered reservations and return them for PMS processing.
        Does NOT auto-confirm - PMS should confirm after successful import.
        """
        all_reservations = []
        page = 1

        while True:
            result = await self.get_reservations(undelivered=True, per_page=10, page=page)
            if not result["success"]:
                return {"success": False, "error": result["error"], "reservations": all_reservations}

            data = result["data"]
            reservations = data.get("reservations", [])
            all_reservations.extend(reservations)

            if page >= data.get("pages", 1):
                break
            page += 1

        return {
            "success": True,
            "count": len(all_reservations),
            "reservations": all_reservations,
        }

    # ── Stats ────────────────────────────────────────────────────────

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current API usage statistics."""
        return {
            "requests_this_minute": self._request_count,
            "requests_today": self._daily_count,
            "daily_limit": 250,
            "minute_limit": 5,
            "daily_remaining": 250 - self._daily_count,
        }
