"""
HotelRunner Provider — Main Provider Facade
=============================================

THE single public API surface for all HotelRunner operations.
Every system component calls this class. No one touches internals directly.

Public methods:
- test_connection()
- fetch_rooms()
- fetch_channels()
- fetch_connected_channels()
- fetch_reservations()
- push_daily_inventory()
- push_date_range_inventory()
- confirm_delivery()
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from . import endpoints as ep
from .auth import extract_credentials, validate_credentials
from .client import HotelRunnerHttpClient
from .retry import HotelRunnerRetryPolicy
from .paginator import HotelRunnerPaginator
from .parser import (
    parse_rooms_response,
    parse_channels_response,
    parse_connected_channels_response,
    parse_reservations_response,
)
from .mapper import (
    map_reservation_to_canonical,
    map_raw_payload_to_canonical,
    map_ari_delta_to_daily_payload,
    map_ari_delta_to_daterange_payload,
)
from .validators import (
    validate_connection_credentials,
    validate_inventory_payload,
)
from .schemas import ProviderResult
from .errors import (
    HotelRunnerError,
    HotelRunnerAuthError,
    HotelRunnerMappingError,
)
from . import observability as obs

logger = logging.getLogger("hotelrunner.provider")


class HotelRunnerProvider:
    """
    Production-grade HotelRunner adapter.

    Usage:
        provider = HotelRunnerProvider(token="...", hr_id="...")
        result = await provider.test_connection()
        rooms = await provider.fetch_rooms()
        reservations = await provider.fetch_reservations()
    """

    def __init__(
        self,
        token: str = "",
        hr_id: str = "",
        *,
        credentials: Optional[Dict[str, str]] = None,
        connection_id: str = "",
        base_url: str = ep.BASE_URL,
        max_retries: int = 3,
        max_pages: int = 50,
    ):
        """
        Initialize provider with either direct credentials or a credentials dict.

        Args:
            token: HotelRunner API token
            hr_id: HotelRunner Hotel ID
            credentials: Alternative — dict with token/hr_id keys
            connection_id: For logging/tracking
            base_url: Override API base URL (for sandbox/mock)
            max_retries: Retry attempts for transient errors
            max_pages: Max pages for paginated endpoints
        """
        if credentials:
            token, hr_id = extract_credentials(credentials)
        validate_credentials(token, hr_id)

        self._token = token
        self._hr_id = hr_id
        self._connection_id = connection_id
        self._client = HotelRunnerHttpClient(token, hr_id, base_url)
        self._retry = HotelRunnerRetryPolicy(max_retries=max_retries)
        self._paginator = HotelRunnerPaginator(max_pages=max_pages)

    # ── Connection Test ───────────────────────────────────────────────

    async def test_connection(self) -> ProviderResult:
        """
        Smoke test: call GET /infos/channels to verify credentials.
        Returns ProviderResult with connected status.
        """
        start = time.time()
        try:
            async def _call():
                return await self._client.get(ep.CHANNELS)

            result = await self._retry.execute(_call)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                path=ep.CHANNELS, method="GET",
                status_code=result.status_code,
                duration_ms=duration_ms, success=result.success,
                connection_id=self._connection_id,
            )

            if result.success:
                channels = result.data.get("channels", [])
                return ProviderResult(
                    success=True,
                    data={"connected": True, "channels": channels, "channel_count": len(channels)},
                    duration_ms=duration_ms,
                )
            return ProviderResult(
                success=False,
                error=result.error or "Connection test failed",
                duration_ms=duration_ms,
            )
        except HotelRunnerError as e:
            duration_ms = int((time.time() - start) * 1000)
            obs.record_provider_failure(
                error_type=type(e).__name__,
                message=str(e),
                connection_id=self._connection_id,
                path=ep.CHANNELS,
            )
            return ProviderResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=duration_ms,
            )

    # ── Room Discovery ────────────────────────────────────────────────

    async def fetch_rooms(self) -> ProviderResult:
        """Fetch all rooms/rates from HotelRunner."""
        start = time.time()
        try:
            async def _call():
                return await self._client.get(ep.ROOMS)

            result = await self._retry.execute(_call)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                path=ep.ROOMS, method="GET",
                status_code=result.status_code,
                duration_ms=duration_ms, success=result.success,
                connection_id=self._connection_id,
            )

            if result.success:
                rooms = parse_rooms_response(result.data)
                return ProviderResult(
                    success=True,
                    data={"rooms": [r.__dict__ for r in rooms], "room_count": len(rooms)},
                    duration_ms=duration_ms,
                )
            return ProviderResult(success=False, error=result.error, duration_ms=duration_ms)
        except HotelRunnerError as e:
            return self._handle_error(e, start, ep.ROOMS)

    # ── Channel Discovery ─────────────────────────────────────────────

    async def fetch_channels(self) -> ProviderResult:
        """Fetch all available channels."""
        start = time.time()
        try:
            async def _call():
                return await self._client.get(ep.CHANNELS)

            result = await self._retry.execute(_call)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                path=ep.CHANNELS, method="GET",
                status_code=result.status_code,
                duration_ms=duration_ms, success=result.success,
                connection_id=self._connection_id,
            )

            if result.success:
                channels = parse_channels_response(result.data)
                return ProviderResult(
                    success=True,
                    data={"channels": [c.__dict__ for c in channels], "channel_count": len(channels)},
                    duration_ms=duration_ms,
                )
            return ProviderResult(success=False, error=result.error, duration_ms=duration_ms)
        except HotelRunnerError as e:
            return self._handle_error(e, start, ep.CHANNELS)

    async def fetch_connected_channels(self) -> ProviderResult:
        """Fetch connected channels with process stats."""
        start = time.time()
        try:
            async def _call():
                return await self._client.get(ep.CONNECTED_CHANNELS)

            result = await self._retry.execute(_call)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                path=ep.CONNECTED_CHANNELS, method="GET",
                status_code=result.status_code,
                duration_ms=duration_ms, success=result.success,
                connection_id=self._connection_id,
            )

            if result.success:
                channels = parse_connected_channels_response(result.data)
                return ProviderResult(
                    success=True,
                    data={"connected_channels": [c.__dict__ for c in channels]},
                    duration_ms=duration_ms,
                )
            return ProviderResult(success=False, error=result.error, duration_ms=duration_ms)
        except HotelRunnerError as e:
            return self._handle_error(e, start, ep.CONNECTED_CHANNELS)

    # ── Reservation Pull ──────────────────────────────────────────────

    async def fetch_reservations(
        self,
        *,
        undelivered: bool = True,
        from_date: Optional[str] = None,
        from_last_update_date: Optional[str] = None,
        per_page: int = 50,
        page: Optional[int] = None,
        modified: bool = False,
        booked: bool = False,
    ) -> ProviderResult:
        """
        Fetch reservations with optional pagination.

        If page is None and undelivered=False, fetches ALL pages.
        Otherwise fetches the specified single page.
        """
        start = time.time()
        try:
            if page is not None or undelivered:
                # Single page fetch
                return await self._fetch_reservations_page(
                    undelivered=undelivered,
                    from_date=from_date,
                    from_last_update_date=from_last_update_date,
                    per_page=per_page,
                    page=page or 1,
                    modified=modified,
                    booked=booked,
                    start_time=start,
                )
            else:
                # Paginated fetch — all pages
                return await self._fetch_all_reservations(
                    from_date=from_date,
                    from_last_update_date=from_last_update_date,
                    per_page=per_page,
                    modified=modified,
                    booked=booked,
                    start_time=start,
                )
        except HotelRunnerError as e:
            return self._handle_error(e, start, ep.RESERVATIONS)

    async def _fetch_reservations_page(
        self, *, undelivered, from_date, from_last_update_date,
        per_page, page, modified, booked, start_time,
    ) -> ProviderResult:
        params = self._build_reservation_params(
            undelivered=undelivered, from_date=from_date,
            from_last_update_date=from_last_update_date,
            per_page=per_page, page=page,
            modified=modified, booked=booked,
        )

        async def _call():
            return await self._client.get(ep.RESERVATIONS, params=params)

        result = await self._retry.execute(_call)
        duration_ms = int((time.time() - start_time) * 1000)

        obs.record_provider_call(
            path=ep.RESERVATIONS, method="GET",
            status_code=result.status_code,
            duration_ms=duration_ms, success=result.success,
            connection_id=self._connection_id,
        )

        if result.success:
            page_data = parse_reservations_response(result.data)
            return ProviderResult(
                success=True,
                data={
                    "reservations": [r.__dict__ for r in page_data.reservations],
                    "raw_reservations": result.data.get("reservations", []),
                    "current_page": page_data.current_page,
                    "total_pages": page_data.total_pages,
                    "count": len(page_data.reservations),
                },
                duration_ms=duration_ms,
            )
        return ProviderResult(success=False, error=result.error, duration_ms=duration_ms)

    async def _fetch_all_reservations(
        self, *, from_date, from_last_update_date,
        per_page, modified, booked, start_time,
    ) -> ProviderResult:
        async def _fetch_page(page_num: int) -> Dict[str, Any]:
            params = self._build_reservation_params(
                undelivered=False, from_date=from_date,
                from_last_update_date=from_last_update_date,
                per_page=per_page, page=page_num,
                modified=modified, booked=booked,
            )

            async def _call():
                return await self._client.get(ep.RESERVATIONS, params=params)

            result = await self._retry.execute(_call)
            if not result.success:
                raise HotelRunnerError(result.error)
            return result.data

        all_raw = await self._paginator.fetch_all_pages(_fetch_page)
        duration_ms = int((time.time() - start_time) * 1000)

        obs.record_provider_call(
            path=ep.RESERVATIONS, method="GET",
            status_code=200,
            duration_ms=duration_ms, success=True,
            connection_id=self._connection_id,
        )

        return ProviderResult(
            success=True,
            data={
                "reservations": all_raw,
                "count": len(all_raw),
                "paginated": True,
            },
            duration_ms=duration_ms,
        )

    @staticmethod
    def _build_reservation_params(
        *, undelivered, from_date, from_last_update_date,
        per_page, page, modified, booked,
    ) -> Dict[str, str]:
        params: Dict[str, str] = {
            "undelivered": str(undelivered).lower(),
            "per_page": str(per_page),
            "page": str(page),
        }
        if from_date:
            params["from_date"] = from_date
        if from_last_update_date:
            params["from_last_update_date"] = from_last_update_date
        if modified:
            params["modified"] = "true"
        if booked:
            params["booked"] = "true"
        return params

    # ── ARI Push ──────────────────────────────────────────────────────

    async def push_daily_inventory(
        self,
        payload: Dict[str, Any],
        room_mapping: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        """Push daily inventory update via PUT /rooms/daily."""
        start = time.time()
        try:
            if room_mapping:
                form_data = map_ari_delta_to_daily_payload(payload, room_mapping)
            else:
                form_data = payload

            validate_inventory_payload(form_data)

            async def _call():
                return await self._client.put(ep.ROOMS_DAILY, form_data=form_data)

            result = await self._retry.execute(_call)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                path=ep.ROOMS_DAILY, method="PUT",
                status_code=result.status_code,
                duration_ms=duration_ms, success=result.success,
                connection_id=self._connection_id,
            )
            return ProviderResult(
                success=result.success,
                data=result.data,
                error=result.error,
                duration_ms=duration_ms,
            )
        except HotelRunnerError as e:
            return self._handle_error(e, start, ep.ROOMS_DAILY)

    async def push_date_range_inventory(
        self,
        payload: Dict[str, Any],
        room_mapping: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        """Push date range inventory update via PUT /rooms/~."""
        start = time.time()
        try:
            if room_mapping:
                form_data = map_ari_delta_to_daterange_payload(payload, room_mapping)
            else:
                form_data = payload

            validate_inventory_payload(form_data)

            async def _call():
                return await self._client.put(ep.ROOMS_DATERANGE, form_data=form_data)

            result = await self._retry.execute(_call)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                path=ep.ROOMS_DATERANGE, method="PUT",
                status_code=result.status_code,
                duration_ms=duration_ms, success=result.success,
                connection_id=self._connection_id,
            )
            return ProviderResult(
                success=result.success,
                data=result.data,
                error=result.error,
                duration_ms=duration_ms,
            )
        except HotelRunnerError as e:
            return self._handle_error(e, start, ep.ROOMS_DATERANGE)

    # ── Reservation Delivery Confirmation ─────────────────────────────

    async def confirm_delivery(
        self,
        message_uid: str,
        pms_number: Optional[str] = None,
    ) -> ProviderResult:
        """Confirm reservation delivery to HotelRunner."""
        start = time.time()
        try:
            params: Dict[str, str] = {"message_uid": message_uid}
            if pms_number:
                params["pms_number"] = pms_number

            async def _call():
                return await self._client.put(ep.RESERVATIONS_ACK, params=params)

            result = await self._retry.execute(_call)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                path=ep.RESERVATIONS_ACK, method="PUT",
                status_code=result.status_code,
                duration_ms=duration_ms, success=result.success,
                connection_id=self._connection_id,
            )
            return ProviderResult(
                success=result.success,
                data=result.data,
                error=result.error,
                duration_ms=duration_ms,
            )
        except HotelRunnerError as e:
            return self._handle_error(e, start, ep.RESERVATIONS_ACK)

    # ── Canonical helpers (for snapshot collectors & ingest) ───────────

    def map_reservation_to_canonical(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Map a raw HR reservation to canonical format."""
        return map_raw_payload_to_canonical(raw)

    # ── Legacy compatibility methods ──────────────────────────────────
    # These match the old HotelRunnerProvider interface so existing callers
    # can migrate without breaking.

    async def get_rooms(self) -> Dict[str, Any]:
        """Legacy: returns dict like the old provider."""
        result = await self.fetch_rooms()
        if result.success:
            return {"success": True, "data": {"rooms": [r.get("raw", r) for r in result.data.get("rooms", [])]}}
        return {"success": False, "error": result.error}

    async def get_channels(self) -> Dict[str, Any]:
        """Legacy: returns dict like the old provider."""
        result = await self.fetch_channels()
        if result.success:
            return {"success": True, "data": result.data}
        return {"success": False, "error": result.error}

    async def get_connected_channels(self) -> Dict[str, Any]:
        """Legacy: returns dict like the old provider."""
        result = await self.fetch_connected_channels()
        if result.success:
            return {"success": True, "data": result.data}
        return {"success": False, "error": result.error}

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
        """Legacy: returns dict like the old provider."""
        result = await self.fetch_reservations(
            undelivered=undelivered,
            from_date=from_date,
            from_last_update_date=from_last_update_date,
            per_page=per_page,
            page=page,
            modified=modified,
            booked=booked,
        )
        if result.success:
            return {
                "success": True,
                "data": {
                    "reservations": result.data.get("raw_reservations", result.data.get("reservations", [])),
                    "pages": result.data.get("total_pages", 1),
                },
                "duration_ms": result.duration_ms,
            }
        return {"success": False, "error": result.error, "duration_ms": result.duration_ms}

    async def sync_reservations(self) -> Dict[str, Any]:
        """Legacy: Pull all undelivered reservations."""
        all_reservations: list = []
        page = 1
        while True:
            result = await self.get_reservations(undelivered=True, per_page=10, page=page)
            if not result.get("success"):
                return {"success": False, "error": result.get("error"), "reservations": all_reservations}
            data = result.get("data", {})
            reservations = data.get("reservations", [])
            all_reservations.extend(reservations)
            if page >= data.get("pages", 1):
                break
            page += 1
        return {"success": True, "count": len(all_reservations), "reservations": all_reservations}

    async def update_room(self, **kwargs) -> Dict[str, Any]:
        """Legacy: ARI push via PUT /rooms/~."""
        form_data = {}
        for key in ("inv_code", "start_date", "end_date"):
            if key in kwargs:
                form_data[key] = str(kwargs[key])
        for key in ("availability", "price", "stop_sale", "min_stay", "cta", "ctd"):
            if key in kwargs and kwargs[key] is not None:
                form_data[key] = str(kwargs[key])
        if "days" in kwargs and kwargs["days"] is not None:
            form_data["days[]"] = [str(d) for d in kwargs["days"]]
        if "channel_codes" in kwargs and kwargs["channel_codes"] is not None:
            form_data["channel_codes[]"] = kwargs["channel_codes"]

        result = await self._client.put(ep.ROOMS_DATERANGE, form_data=form_data)
        if result.success:
            return {"success": True, "data": result.data, "duration_ms": result.duration_ms}
        return {"success": False, "error": result.error, "duration_ms": result.duration_ms}

    def get_usage_stats(self) -> Dict[str, Any]:
        """Legacy: Get API usage statistics."""
        health = obs.get_provider_health()
        return {
            "requests_this_minute": 0,
            "requests_today": health["call_count"],
            "daily_limit": 250,
            "minute_limit": 5,
            "daily_remaining": 250 - health["call_count"],
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _handle_error(self, error: HotelRunnerError, start_time: float, path: str) -> ProviderResult:
        duration_ms = int((time.time() - start_time) * 1000)
        obs.record_provider_failure(
            error_type=type(error).__name__,
            message=str(error),
            connection_id=self._connection_id,
            path=path,
        )
        return ProviderResult(
            success=False,
            error=str(error),
            error_type=type(error).__name__,
            duration_ms=duration_ms,
        )
