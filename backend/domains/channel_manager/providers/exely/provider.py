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
    ExelyAuthError,
    ExelyError,
    ExelyParseError,
    ExelyPayloadError,
    ExelyRateLimitError,
    ExelyTemporaryError,
    ExelyValidationError,
)
from .normalizer import normalize_reservation
from .provider_quota import ExelyProviderQuota
from .response_parser import (
    AMBIGUOUS,
    AUTH_FAILED,
    MALFORMED,
    PROVIDER_ERROR,
    RATE_LIMITED,
    REJECTED,
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
        tenant_id: str = "",
        property_id: str = "",
        quota_guard: ExelyProviderQuota | None = None,
        max_retries: int = 3,
    ):
        if credentials:
            username, password, hotel_code = extract_credentials(credentials)
        validate_credentials(username, password, hotel_code)

        self._username = username
        self._password = password
        self._hotel_code = hotel_code
        self._connection_id = connection_id
        self._tenant_id = tenant_id
        self._property_id = property_id or hotel_code
        self._transport = ExelySoapTransport(endpoint_url)
        self._retry = ExelyRetryPolicy(max_retries=max_retries)
        self._quota = quota_guard
        if self._quota is None and tenant_id and self._property_id:
            self._quota = ExelyProviderQuota(tenant_id, self._property_id)

    async def _reserve_quota(self, operation: str, *, change_count: int = 0) -> None:
        if self._quota is None:
            return
        decision = await self._quota.reserve(operation=operation, change_count=change_count)
        if not decision.allowed:
            raise ExelyRateLimitError(
                retry_after_seconds=decision.retry_after_seconds or 60,
                message=decision.reason,
                source="local_quota",
            )

    async def _send_read(self, xml: str, soap_action: str, *, operation: str) -> bytes:
        async def _call():
            await self._reserve_quota(operation)
            try:
                return await self._transport.send_soap(xml, soap_action)
            except ExelyRateLimitError as exc:
                if self._quota is not None and exc.source == "provider":
                    await self._quota.record_cooldown(exc.retry_after_seconds)
                raise

        return await self._retry.execute_read(_call)

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

            raw = await self._send_read(xml, soap_action, operation="discovery")
            result = parse_hotel_avail_rs(raw)
            await self._record_provider_limit(result)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            metadata = _parser_metadata(result)
            if result["success"]:
                return ProviderResult(
                    success=True,
                    data={
                        "connected": True,
                        "room_types": result["room_types"],
                        "rate_plans": result["rate_plans"],
                    },
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
            return ProviderResult(
                success=False,
                error=result.get("error", "Connection test failed"),
                error_type=result.get("result_class", MALFORMED),
                duration_ms=duration_ms,
                metadata=metadata,
            )
        except ExelyError as e:
            return self._handle_error(e, start, operation)

    # ── Room Discovery ────────────────────────────────────────────────

    async def discover_rooms(
        self,
        checkin: str | None = None,
        checkout: str | None = None,
    ) -> ProviderResult:
        """Discover room types and rate plans via OTA_HotelAvailRQ."""
        start = time.time()
        operation = "OTA_HotelAvailRQ"
        soap_action = get_soap_action_uri(operation)
        try:
            ci = checkin or datetime.now().strftime("%Y-%m-%d")
            co = checkout or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            xml = build_hotel_avail_rq(self._username, self._password, self._hotel_code, ci, co)

            raw = await self._send_read(xml, soap_action, operation="discovery")
            result = parse_hotel_avail_rs(raw)
            await self._record_provider_limit(result)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            metadata = _parser_metadata(result)
            if result["success"]:
                return ProviderResult(
                    success=True,
                    data={
                        "room_types": result["room_types"],
                        "rate_plans": result["rate_plans"],
                    },
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
            return ProviderResult(
                success=False,
                error=result.get("error", "Discovery failed"),
                error_type=result.get("result_class", MALFORMED),
                duration_ms=duration_ms,
                metadata=metadata,
            )
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

            raw = await self._send_read(xml, soap_action, operation="reservation_read")
            result = parse_read_rs(raw)
            await self._record_provider_limit(result)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            metadata = _parser_metadata(result)
            if result["success"]:
                return ProviderResult(
                    success=True,
                    data={
                        "reservations": result.get("reservations", []),
                        "count": result.get("count", 0),
                    },
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
            return ProviderResult(
                success=False,
                error=result.get("error", "Pull failed"),
                error_type=result.get("result_class", MALFORMED),
                duration_ms=duration_ms,
                metadata=metadata,
            )
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
        min_los_arrival: int | None = None,
        max_stay: int | None = None,
        cta: bool | None = None,
        ctd: bool | None = None,
    ) -> ProviderResult:
        """Compatibility facade that permits exactly one ARI mutation.

        Durable callers must use the canonical delivery service. Keeping this
        low-level facade single-operation prevents partial multi-write results
        and blind retries in older call sites while they are retired.
        """
        operations = [
            ("availability", availability),
            ("rate", rate_amount),
            ("stop_sell", stop_sell),
            ("min_los", min_stay),
            ("min_los_arrival", min_los_arrival),
            ("max_los", max_stay),
            ("cta", cta),
            ("ctd", ctd),
        ]
        selected = [(name, value) for name, value in operations if value is not None]
        validate_ari_payload(room_type_code, rate_plan_code, start_date, end_date)
        if len(selected) != 1:
            raise ExelyValidationError("Exactly one Exely ARI mutation is required", field="operation")
        operation, value = selected[0]
        return await self.push_ari_operation(
            operation=operation,
            room_type_code=room_type_code,
            rate_plan_code=rate_plan_code,
            start_date=start_date,
            end_date=end_date,
            value=value,
            currency=currency,
        )

    async def push_ari_operation(
        self,
        *,
        operation: str,
        room_type_code: str,
        rate_plan_code: str,
        start_date: str,
        end_date: str,
        value: Any,
        currency: str = "TRY",
    ) -> ProviderResult:
        """Send one SOAP mutation once and require explicit provider success."""
        start = time.time()
        provider_write_count = 0
        breaker = provider_failover.get_breaker(_exely_circuit_key(self._connection_id))
        if not await breaker.try_acquire():
            return ProviderResult(
                success=False,
                error=f"circuit_open: Exely breaker is OPEN for connection {self._connection_id or '_default'}",
                error_type="CircuitOpen",
                duration_ms=int((time.time() - start) * 1000),
                metadata={
                    "circuit_open": True,
                    "circuit_state": breaker.get_status(),
                    "provider_write_count": 0,
                    "provider_status_class": "NOT_SENT",
                },
            )
        validate_ari_payload(room_type_code, rate_plan_code, start_date, end_date)
        supported = {
            "availability",
            "rate",
            "stop_sell",
            "min_los",
            "min_los_arrival",
            "max_los",
            "cta",
            "ctd",
        }
        if operation not in supported:
            raise ExelyValidationError("Unsupported Exely ARI operation", field="operation")

        soap_operation = "OTA_HotelRateAmountNotifRQ" if operation == "rate" else "OTA_HotelAvailNotifRQ"
        if operation == "rate":
            xml = build_rate_amount_notif_rq(
                self._username,
                self._password,
                self._hotel_code,
                room_type_code,
                rate_plan_code,
                start_date,
                end_date,
                float(value),
                currency,
            )
        else:
            kwargs = {
                "availability": value if operation == "availability" else None,
                "stop_sell": value if operation == "stop_sell" else None,
                "min_stay": value if operation == "min_los" else None,
                "min_los_arrival": value if operation == "min_los_arrival" else None,
                "max_stay": value if operation == "max_los" else None,
                "cta": value if operation == "cta" else None,
                "ctd": value if operation == "ctd" else None,
            }
            xml = build_ari_update_rq(
                self._username,
                self._password,
                self._hotel_code,
                room_type_code,
                rate_plan_code,
                start_date,
                end_date,
                currency=currency,
                **kwargs,
            )

        try:
            await self._reserve_quota(
                "ari_mutation",
                change_count=_ari_change_count(start_date, end_date),
            )
            provider_write_count = 1
            raw = await self._transport.send_soap(xml, get_soap_action_uri(soap_operation))
            parsed = parse_ari_update_rs(raw)
            await self._record_provider_limit(parsed)
            duration_ms = int((time.time() - start) * 1000)
            obs.record_provider_call(
                soap_action=soap_operation,
                duration_ms=duration_ms,
                success=parsed["success"],
                connection_id=self._connection_id,
            )
            metadata = {
                "provider_write_count": provider_write_count,
                "provider_status_class": parsed.get("result_class", "MALFORMED"),
                "provider_codes": parsed.get("provider_codes", []),
                "warning_codes": parsed.get("warning_codes", []),
            }
            if parsed.get("retry_after_seconds"):
                metadata["retry_after_seconds"] = int(parsed["retry_after_seconds"])
            if not parsed["success"]:
                await breaker.record_failure()
                return ProviderResult(
                    success=False,
                    error=parsed.get("error", "Provider rejected ARI update"),
                    error_type=parsed.get("result_class", "MALFORMED"),
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
            await breaker.record_success()
            logger.info(
                "[EXELY-ARI] operation=%s delivery_state=%s",
                operation,
                parsed.get("result_class", "SUCCESS").lower(),
            )
            return ProviderResult(
                success=True,
                data={"result_class": parsed.get("result_class", "SUCCESS")},
                duration_ms=duration_ms,
                metadata=metadata,
            )
        except ExelyError as error:
            await breaker.record_failure()
            result = self._handle_error(
                error,
                start,
                soap_operation,
                mutation=True,
                provider_write_count=provider_write_count,
            )
            return result

    # ── Reservation Delivery Confirmation ─────────────────────────────

    async def confirm_delivery(
        self,
        reservation_id: str,
        confirmation_number: str,
        create_datetime: str = None,
        last_modify_datetime: str = None,
        res_status: str = "Reserved",
        *,
        provider_id_context: str = "",
        confirmations: list[dict[str, Any]] | None = None,
    ) -> ProviderResult:
        """Confirm reservation delivery via OTA_NotifReportRQ.
        Exely accepts ResStatus='Reserved' for delivery confirmation."""
        start = time.time()
        provider_write_count = 0
        operation = "OTA_NotifReportRQ"
        soap_action = get_soap_action_uri(operation)
        try:
            if not create_datetime or not last_modify_datetime:
                raise ExelyValidationError("Exact provider acknowledgement timestamps are required")
            acknowledgement_rows = confirmations or [{"pms_booking_id": confirmation_number, "room_stay_indexes": []}]
            if not reservation_id or not acknowledgement_rows or any(not str(row.get("pms_booking_id") or "") for row in acknowledgement_rows):
                raise ExelyValidationError("A provider reservation and PMS confirmation are required")
            xml = build_notif_report_rq(
                self._username,
                self._password,
                self._hotel_code,
                reservation_id,
                confirmation_number,
                create_datetime=create_datetime,
                last_modify_datetime=last_modify_datetime,
                res_status=res_status,
                provider_id_context=provider_id_context,
                confirmations=acknowledgement_rows,
            )

            logger.info("[EXELY] operation=reservation_ack delivery_state=sending")

            # Delivery ACKs are provider mutations. Without a provider idempotency
            # key, an ambiguous timeout must never trigger a blind retry.
            await self._reserve_quota("reservation_ack")
            provider_write_count = 1
            raw = await self._transport.send_soap(xml, soap_action)
            result = parse_notif_report_rs(raw)
            await self._record_provider_limit(result)
            duration_ms = int((time.time() - start) * 1000)

            obs.record_provider_call(
                soap_action=operation,
                duration_ms=duration_ms,
                success=result["success"],
                connection_id=self._connection_id,
            )

            if result["success"]:
                logger.info("[EXELY] operation=reservation_ack delivery_state=accepted")
                return ProviderResult(
                    success=True,
                    data=result,
                    duration_ms=duration_ms,
                    metadata={**_parser_metadata(result), "provider_write_count": 1},
                )

            logger.warning("[EXELY] operation=reservation_ack delivery_state=rejected")
            return ProviderResult(
                success=False,
                error="Provider rejected reservation acknowledgement",
                error_type=result.get("error_type") or result.get("result_class", REJECTED),
                duration_ms=duration_ms,
                metadata={**_parser_metadata(result), "provider_write_count": 1},
            )
        except ExelyError as e:
            return self._handle_error(
                e,
                start,
                operation,
                mutation=True,
                provider_write_count=provider_write_count,
            )

    # ── Canonical helpers (for snapshot collectors & ingest) ───────────

    def normalize_to_canonical(self, raw: dict[str, Any], source: str = "pull") -> dict[str, Any]:
        """Normalize a raw Exely reservation to canonical format."""
        return normalize_reservation(raw, source)

    async def _record_provider_limit(self, result: dict[str, Any]) -> None:
        if result.get("result_class") != RATE_LIMITED or self._quota is None:
            return
        await self._quota.record_cooldown(int(result.get("retry_after_seconds") or 60))

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

    async def legacy_confirm_delivery(
        self,
        reservation_id: str,
        confirmation_number: str,
        create_datetime: str = None,
        last_modify_datetime: str = None,
        res_status: str = "Reserved",
        *,
        provider_id_context: str = "",
        confirmations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Legacy: returns dict like the old ExelyClient."""
        result = await self.confirm_delivery(
            reservation_id,
            confirmation_number,
            create_datetime=create_datetime,
            last_modify_datetime=last_modify_datetime,
            res_status=res_status,
            provider_id_context=provider_id_context,
            confirmations=confirmations,
        )
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

    def _handle_error(
        self,
        error: ExelyError,
        start_time: float,
        soap_action: str,
        *,
        mutation: bool = False,
        provider_write_count: int = 0,
    ) -> ProviderResult:
        duration_ms = int((time.time() - start_time) * 1000)
        obs.record_provider_failure(
            error_type=type(error).__name__,
            message=str(error),
            connection_id=self._connection_id,
            soap_action=soap_action,
        )
        classification = _classify_exception(error, mutation=mutation, provider_write_count=provider_write_count)
        provider_status_class = "WRITE_OUTCOME_UNKNOWN" if classification == AMBIGUOUS else classification
        error_type = type(error).__name__ if isinstance(error, ExelyTemporaryError) else classification
        metadata = {
            "classification": classification,
            "provider_status_class": provider_status_class,
            "provider_codes": [error.provider_code] if isinstance(error, ExelyRateLimitError) and error.provider_code else [],
            "provider_write_count": provider_write_count,
        }
        if isinstance(error, ExelyRateLimitError):
            metadata["retry_after_seconds"] = error.retry_after_seconds
        return ProviderResult(
            success=False,
            error=str(error),
            error_type=error_type,
            duration_ms=duration_ms,
            metadata=metadata,
        )


def _parser_metadata(result: dict[str, Any]) -> dict[str, Any]:
    classification = result.get("result_class", MALFORMED)
    metadata = {
        "classification": classification,
        "provider_status_class": classification,
        "provider_codes": result.get("provider_codes", []),
        "warning_codes": result.get("warning_codes", []),
        "provider_write_count": 0,
    }
    if result.get("retry_after_seconds"):
        metadata["retry_after_seconds"] = int(result["retry_after_seconds"])
    return metadata


def _classify_exception(error: ExelyError, *, mutation: bool, provider_write_count: int) -> str:
    if isinstance(error, ExelyRateLimitError):
        return RATE_LIMITED
    if isinstance(error, ExelyAuthError):
        return AUTH_FAILED
    if isinstance(error, ExelyParseError):
        return MALFORMED
    if isinstance(error, ExelyPayloadError | ExelyValidationError):
        return REJECTED
    if isinstance(error, ExelyTemporaryError) and mutation and provider_write_count:
        return AMBIGUOUS
    return PROVIDER_ERROR


def _ari_change_count(start_date: str, end_date: str) -> int:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    return max(1, (end - start).days + 1)
