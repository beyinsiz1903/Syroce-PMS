"""
Exely Provider — Main Provider Facade
=======================================

THE single public API surface for all Exely SOAP operations.
Every system component calls this class. No one touches internals directly.

Public methods:
- test_connection()
- discover_rooms()
- pull_reservations()
- push_ari()
- confirm_delivery()
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from . import observability as obs
from .client import EXELY_DEFAULT_URL, ExelySoapTransport
from .errors import (
    ExelyError,
)
from .normalizer import normalize_reservation
from .response_parser import (
    parse_ari_update_rs,
    parse_hotel_avail_rs,
    parse_notif_report_rs,
    parse_read_rs,
)
from .retry import ExelyRetryPolicy
from .soap_builder import (
    build_ari_update_rq,
    build_hotel_avail_rq,
    build_notif_report_rq,
    build_rate_amount_notif_rq,
    build_read_rq,
    get_soap_action_uri,
)
from .validators import extract_credentials, validate_ari_payload, validate_credentials, validate_date_range

logger = logging.getLogger("exely.provider")

# Reuse the same ProviderResult from hotelrunner for consistency
from domains.channel_manager.provider_failover import provider_failover
from domains.channel_manager.providers.hotelrunner.schemas import ProviderResult


def _exely_circuit_key(connection_id: str) -> str:
    """Per-connection Exely breaker key. One bad tenant must not trip the
    circuit for other tenants."""
    return f"exely:{connection_id or '_default'}"


class ExelyProvider:
    """
    Production-grade Exely SOAP adapter.

    Usage:
        provider = ExelyProvider(username="...", password="...", hotel_code="...")
        result = await provider.test_connection()
        rooms = await provider.discover_rooms()
        reservations = await provider.pull_reservations()
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        hotel_code: str = "",
        *,
        credentials: dict[str, str] | None = None,
        endpoint_url: str = EXELY_DEFAULT_URL,
        connection_id: str = "",
        max_retries: int = 3,
    ):
        if credentials:
            username, password, hotel_code = extract_credentials(credentials)
        validate_credentials(username, password, hotel_code)

        self._username = username
        self._password = password
        self._hotel_code = hotel_code
        self._connection_id = connection_id
        self._transport = ExelySoapTransport(endpoint_url)
        self._retry = ExelyRetryPolicy(max_retries=max_retries)

    # ── Connection Test ───────────────────────────────────────────────

    async def test_connection(self) -> ProviderResult:
        """
        Smoke test: send OTA_HotelAvailRQ to verify credentials.
        Returns ProviderResult with connected status + discovered rooms/rates.
        """
        start = time.time()
        operation = "OTA_HotelAvailRQ"
        soap_action = get_soap_action_uri(operation)
        try:
            checkin = datetime.now().strftime("%Y-%m-%d")
            checkout = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            xml = build_hotel_avail_rq(self._username, self._password, self._hotel_code, checkin, checkout)

            async def _call():
                return await self._transport.send_soap(xml, soap_action)

            raw = await self._retry.execute(_call)
            result = parse_hotel_avail_rs(raw)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            if result["success"]:
                return ProviderResult(
                    success=True,
                    data={
                        "connected": True,
                        "room_types": result["room_types"],
                        "rate_plans": result["rate_plans"],
                    },
                    duration_ms=duration_ms,
                )
            return ProviderResult(
                success=False,
                error=result.get("error", "Connection test failed"),
                duration_ms=duration_ms,
            )
        except ExelyError as e:
            return self._handle_error(e, start, operation)

    # ── Room Discovery ────────────────────────────────────────────────

    async def discover_rooms(
        self, checkin: str | None = None, checkout: str | None = None,
    ) -> ProviderResult:
        """Discover room types and rate plans via OTA_HotelAvailRQ."""
        start = time.time()
        operation = "OTA_HotelAvailRQ"
        soap_action = get_soap_action_uri(operation)
        try:
            ci = checkin or datetime.now().strftime("%Y-%m-%d")
            co = checkout or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            xml = build_hotel_avail_rq(self._username, self._password, self._hotel_code, ci, co)

            async def _call():
                return await self._transport.send_soap(xml, soap_action)

            raw = await self._retry.execute(_call)
            result = parse_hotel_avail_rs(raw)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            if result["success"]:
                return ProviderResult(
                    success=True,
                    data={
                        "room_types": result["room_types"],
                        "rate_plans": result["rate_plans"],
                    },
                    duration_ms=duration_ms,
                )
            return ProviderResult(success=False, error=result.get("error", "Discovery failed"), duration_ms=duration_ms)
        except ExelyError as e:
            return self._handle_error(e, start, operation)

    # ── Reservation Pull ──────────────────────────────────────────────

    async def pull_reservations(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        reservation_id: str | None = None,
    ) -> ProviderResult:
        """Pull reservations via OTA_ReadRQ."""
        start = time.time()
        operation = "OTA_ReadRQ"
        soap_action = get_soap_action_uri(operation)
        try:
            validate_date_range(from_date, to_date)
            xml = build_read_rq(self._username, self._password, self._hotel_code, from_date, to_date, reservation_id)

            async def _call():
                return await self._transport.send_soap(xml, soap_action)

            raw = await self._retry.execute(_call)
            result = parse_read_rs(raw)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            if result["success"]:
                return ProviderResult(
                    success=True,
                    data={
                        "reservations": result.get("reservations", []),
                        "count": result.get("count", 0),
                    },
                    duration_ms=duration_ms,
                )
            return ProviderResult(success=False, error=result.get("error", "Pull failed"), duration_ms=duration_ms)
        except ExelyError as e:
            return self._handle_error(e, start, operation)

    # ── ARI Push ──────────────────────────────────────────────────────

    async def push_ari(
        self,
        room_type_code: str,
        rate_plan_code: str,
        start_date: str,
        end_date: str,
        availability: int | None = None,
        rate_amount: float | None = None,
        currency: str = "TRY",
        stop_sell: bool | None = None,
        min_stay: int | None = None,
    ) -> ProviderResult:
        """Push ARI update. Splits into separate SOAP calls:
        - OTA_HotelRateAmountNotifRQ for rate changes
        - OTA_HotelAvailNotifRQ for availability/restrictions
        Exely requires these as separate operations.

        Wrapped in a per-connection circuit breaker — when OPEN, the SOAP
        calls are short-circuited and a fail-fast ProviderResult is returned
        (metadata.circuit_open=True). Both rate and avail sub-pushes share
        the same breaker; either failing counts as one push attempt.
        """
        start = time.time()
        breaker = provider_failover.get_breaker(_exely_circuit_key(self._connection_id))
        if not await breaker.try_acquire():
            return ProviderResult(
                success=False,
                error=f"circuit_open: Exely breaker is OPEN for connection {self._connection_id or '_default'}",
                error_type="CircuitOpen",
                duration_ms=int((time.time() - start) * 1000),
                metadata={"circuit_open": True, "circuit_state": breaker.get_status()},
            )
        validate_ari_payload(room_type_code, rate_plan_code, start_date, end_date)

        has_rate = rate_amount is not None
        has_avail = availability is not None or stop_sell is not None or min_stay is not None
        errors = []

        # 1) Push rate via OTA_HotelRateAmountNotifRQ
        if has_rate:
            try:
                rate_op = "OTA_HotelRateAmountNotifRQ"
                rate_xml = build_rate_amount_notif_rq(
                    self._username, self._password, self._hotel_code,
                    room_type_code, rate_plan_code, start_date, end_date,
                    rate_amount, currency,
                )
                rate_action = get_soap_action_uri(rate_op)

                async def _rate_call():
                    return await self._transport.send_soap(rate_xml, rate_action)

                raw = await self._retry.execute(_rate_call)
                result = parse_ari_update_rs(raw)
                dur = int((time.time() - start) * 1000)
                obs.record_provider_call(soap_action=rate_op, duration_ms=dur, success=result["success"], connection_id=self._connection_id)
                if not result["success"]:
                    errors.append(f"Rate: {result.get('error', 'failed')}")
                else:
                    logger.info(f"[ARI-PUSH] Rate pushed OK: room={room_type_code} plan={rate_plan_code} rate={rate_amount} currency={currency} {start_date}-{end_date}")
            except ExelyError as e:
                errors.append(f"Rate: {e}")
                logger.error(f"[ARI-PUSH] Rate push error: {e}")

        # 2) Push availability/restrictions via OTA_HotelAvailNotifRQ
        if has_avail:
            try:
                avail_op = "OTA_HotelAvailNotifRQ"
                avail_xml = build_ari_update_rq(
                    self._username, self._password, self._hotel_code,
                    room_type_code, rate_plan_code, start_date, end_date,
                    availability, None, currency, stop_sell, min_stay,
                )
                avail_action = get_soap_action_uri(avail_op)

                async def _avail_call():
                    return await self._transport.send_soap(avail_xml, avail_action)

                raw = await self._retry.execute(_avail_call)
                result = parse_ari_update_rs(raw)
                dur = int((time.time() - start) * 1000)
                obs.record_provider_call(soap_action=avail_op, duration_ms=dur, success=result["success"], connection_id=self._connection_id)
                if not result["success"]:
                    errors.append(f"Avail: {result.get('error', 'failed')}")
                else:
                    logger.info(f"[ARI-PUSH] Avail pushed OK: room={room_type_code} plan={rate_plan_code} avail={availability} stop={stop_sell} min_stay={min_stay} {start_date}-{end_date}")
            except ExelyError as e:
                errors.append(f"Avail: {e}")
                logger.error(f"[ARI-PUSH] Avail push error: {e}")

        duration_ms = int((time.time() - start) * 1000)

        if errors:
            await breaker.record_failure()
            return ProviderResult(success=False, error="; ".join(errors), duration_ms=duration_ms)
        await breaker.record_success()
        return ProviderResult(success=True, data={"message": "ARI update applied"}, duration_ms=duration_ms)

    # ── Reservation Delivery Confirmation ─────────────────────────────

    async def confirm_delivery(
        self,
        reservation_id: str,
        confirmation_number: str,
        create_datetime: str = None,
        last_modify_datetime: str = None,
        res_status: str = "Reserved",
    ) -> ProviderResult:
        """Confirm reservation delivery via OTA_NotifReportRQ.
        Exely accepts ResStatus='Reserved' for delivery confirmation."""
        start = time.time()
        operation = "OTA_NotifReportRQ"
        soap_action = get_soap_action_uri(operation)
        try:
            xml = build_notif_report_rq(
                self._username, self._password, self._hotel_code,
                reservation_id, confirmation_number,
                create_datetime=create_datetime,
                last_modify_datetime=last_modify_datetime,
                res_status=res_status,
            )

            logger.info(f"[EXELY] Confirming delivery for {reservation_id} with ResStatus={res_status}")

            async def _call():
                return await self._transport.send_soap(xml, soap_action)

            raw = await self._retry.execute(_call)
            result = parse_notif_report_rs(raw)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            if result["success"]:
                logger.info(f"[EXELY] Delivery confirmed OK for {reservation_id}")
                return ProviderResult(success=True, data=result, duration_ms=duration_ms)

            logger.warning(f"[EXELY] Delivery confirm failed for {reservation_id}: {result.get('error')}")
            return ProviderResult(success=False, error=result.get("error", "Confirm failed"), duration_ms=duration_ms)
        except ExelyError as e:
            return self._handle_error(e, start, operation)

    # ── Canonical helpers (for snapshot collectors & ingest) ───────────

    def normalize_to_canonical(self, raw: dict[str, Any], source: str = "pull") -> dict[str, Any]:
        """Normalize a raw Exely reservation to canonical format."""
        return normalize_reservation(raw, source)

    # ── Legacy compatibility methods ──────────────────────────────────
    # These match the old ExelyClient interface so existing callers
    # can migrate without breaking.

    async def legacy_test_connection(self) -> dict[str, Any]:
        """Legacy: returns dict like the old ExelyClient."""
        result = await self.test_connection()
        if result.success:
            data = result.data or {}
            return {
                "connected": True,
                "room_types": data.get("room_types", []),
                "rate_plans": data.get("rate_plans", []),
                "duration_ms": result.duration_ms,
            }
        return {"connected": False, "error": result.error, "duration_ms": result.duration_ms}

    async def legacy_pull_reservations(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        reservation_id: str | None = None,
    ) -> dict[str, Any]:
        """Legacy: returns dict like the old ExelyClient."""
        result = await self.pull_reservations(from_date, to_date, reservation_id)
        if result.success:
            data = result.data or {}
            return {
                "success": True,
                "reservations": data.get("reservations", []),
                "count": data.get("count", 0),
                "duration_ms": result.duration_ms,
            }
        return {"success": False, "error": result.error, "reservations": [], "duration_ms": result.duration_ms}

    async def legacy_discover_rooms(self, checkin: str, checkout: str) -> dict[str, Any]:
        """Legacy: returns dict like the old ExelyClient."""
        result = await self.discover_rooms(checkin, checkout)
        if result.success:
            data = result.data or {}
            return {
                "success": True,
                "room_types": data.get("room_types", []),
                "rate_plans": data.get("rate_plans", []),
                "duration_ms": result.duration_ms,
            }
        return {"success": False, "error": result.error, "room_types": [], "rate_plans": [], "duration_ms": result.duration_ms}

    async def legacy_push_ari(self, **kwargs) -> dict[str, Any]:
        """Legacy: returns dict like the old ExelyClient."""
        result = await self.push_ari(**kwargs)
        if result.success:
            return {"success": True, **(result.data or {}), "duration_ms": result.duration_ms}
        return {"success": False, "error": result.error, "duration_ms": result.duration_ms}

    async def legacy_confirm_delivery(self, reservation_id: str, confirmation_number: str, create_datetime: str = None, last_modify_datetime: str = None, res_status: str = "Reserved") -> dict[str, Any]:
        """Legacy: returns dict like the old ExelyClient."""
        result = await self.confirm_delivery(reservation_id, confirmation_number, create_datetime=create_datetime, last_modify_datetime=last_modify_datetime, res_status=res_status)
        if result.success:
            return {"success": True, **(result.data or {}), "duration_ms": result.duration_ms}
        return {"success": False, "error": result.error, "duration_ms": result.duration_ms}

    def get_usage_stats(self) -> dict[str, Any]:
        """Get API usage statistics."""
        health = obs.get_provider_health()
        return {
            "requests_today": health["call_count"],
            "success_rate_pct": health["success_rate_pct"],
            "avg_latency_ms": health["avg_latency_ms"],
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _handle_error(self, error: ExelyError, start_time: float, soap_action: str) -> ProviderResult:
        duration_ms = int((time.time() - start_time) * 1000)
        obs.record_provider_failure(
            error_type=type(error).__name__,
            message=str(error),
            connection_id=self._connection_id,
            soap_action=soap_action,
        )
        return ProviderResult(
            success=False,
            error=str(error),
            error_type=type(error).__name__,
            duration_ms=duration_ms,
        )
