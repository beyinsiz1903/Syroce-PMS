"""
HotelRunner v2 — Service (Business Logic Orchestration)
========================================================

The ONLY public entry point for all HotelRunner v2 operations.
Orchestrates: client → mapper → pipeline → outbox → metrics.

Endpoint paths from endpoint_map.py (v1/v2 mixed, per HR docs).
"""
import logging
import time
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from .client import HRv2Client
from .endpoint_map import get_path
from .errors import HRv2AuthError, HRv2Error
from .feature_flags import is_shadow_mode, is_write_enabled
from .mapper import (
    ari_to_update_payload,
    compute_idempotency_key,
    compute_payload_hash,
    detect_event_type,
    extract_identity,
    reservation_to_canonical,
)
from .metrics import record_metric
from .retry import HRv2RetryPolicy, send_to_dlq

logger = logging.getLogger("hrv2.service")

# Environment URL map
ENV_URLS = {
    "mock": "http://localhost:9999",
    "sandbox": "https://sandbox.hotelrunner.com",
    "production": "https://app.hotelrunner.com",
}


class HotelRunnerV2Service:
    """
    Production-grade HotelRunner v2 connector service.

    Usage:
        svc = await HotelRunnerV2Service.create(tenant_id, property_id)
        result = await svc.test_connection()
        reservations = await svc.pull_reservations()
        await svc.push_ari("HR:1", "2026-05-01", "2026-05-05", availability=5)
    """

    def __init__(
        self,
        tenant_id: str,
        property_id: str,
        client: HRv2Client,
        *,
        environment: str = "production",
    ):
        self._tenant_id = tenant_id
        self._property_id = property_id
        self._client = client
        self._environment = environment
        self._retry = HRv2RetryPolicy(max_retries=5)

    @classmethod
    async def create(
        cls,
        tenant_id: str,
        property_id: str,
        *,
        environment: str = "",
    ) -> "HotelRunnerV2Service":
        """
        Factory: resolve credentials from SecretManager and build service.
        Never uses plaintext credentials.
        """
        from domains.channel_manager.credential_vault import get_decrypted_credentials

        creds = await get_decrypted_credentials(tenant_id, "hotelrunner", property_id)
        if not creds:
            raise HRv2AuthError(f"No credentials found for tenant={tenant_id} property={property_id}")

        token = creds.get("token", "")
        hr_id = creds.get("hr_id", "")
        if not token or not hr_id:
            raise HRv2AuthError("Incomplete credentials (token or hr_id missing)")

        env = environment or creds.get("environment", "production")
        base_url = ENV_URLS.get(env, ENV_URLS["production"])

        client = HRv2Client(token=token, hr_id=hr_id, base_url=base_url)
        return cls(tenant_id, property_id, client, environment=env)

    @classmethod
    def create_direct(
        cls,
        tenant_id: str,
        property_id: str,
        token: str,
        hr_id: str,
        *,
        environment: str = "mock",
    ) -> "HotelRunnerV2Service":
        """Direct construction for testing (bypasses SecretManager)."""
        base_url = ENV_URLS.get(environment, ENV_URLS["production"])
        client = HRv2Client(token=token, hr_id=hr_id, base_url=base_url)
        return cls(tenant_id, property_id, client, environment=environment)

    # ── Connection Test ───────────────────────────────────────────────

    async def test_connection(self) -> dict[str, Any]:
        """Smoke test: auth → channels → rooms → reservations."""
        start = time.time()
        corr_id = str(_uuid.uuid4())[:12]
        steps: list[dict] = []

        test_endpoints = [
            ("auth", get_path("channels_list")),
            ("rooms", get_path("rooms_list")),
            ("reservations", get_path("reservations_list")),
        ]

        for name, path in test_endpoints:
            step_start = time.time()
            try:
                resp = await self._client.get(path, params={"per_page": "1"}, correlation_id=corr_id)
                steps.append({
                    "step": name,
                    "status": "pass" if resp.success else "fail",
                    "latency_ms": int((time.time() - step_start) * 1000),
                    "error": resp.error if not resp.success else None,
                })
            except HRv2Error as e:
                steps.append({
                    "step": name,
                    "status": "fail",
                    "latency_ms": int((time.time() - step_start) * 1000),
                    "error": str(e),
                    "category": e.category,
                })

        total_ms = int((time.time() - start) * 1000)
        all_pass = all(s["status"] == "pass" for s in steps)

        await record_metric(
            self._tenant_id, "test_connection",
            success=all_pass, duration_ms=total_ms, correlation_id=corr_id,
        )

        return {
            "success": all_pass,
            "steps": steps,
            "total_latency_ms": total_ms,
            "environment": self._environment,
            "correlation_id": corr_id,
        }

    # ── Reservation Pull ──────────────────────────────────────────────

    async def pull_reservations(
        self,
        *,
        undelivered: bool = True,
        from_date: str | None = None,
        from_last_update_date: str | None = None,
        modified: bool | None = None,
        booked: bool | None = None,
        reservation_number: str | None = None,
        per_page: int = 50,
        max_pages: int = 20,
    ) -> dict[str, Any]:
        """
        Pull reservations from HotelRunner.
        GET /api/v2/apps/reservations

        Params from HR docs:
        - undelivered: true (default) returns only new/undelivered
        - from_date: YYYY-MM-DD (max 30 days before)
        - from_last_update_date: YYYY-MM-DD
        - modified: true for modified-only
        - booked: true for new-only
        - reservation_number: specific reservation
        """
        start = time.time()
        corr_id = str(_uuid.uuid4())[:12]
        all_raw: list[dict] = []
        page = 1
        ep = get_path("reservations_list")

        while page <= max_pages:
            params: dict[str, str] = {
                "undelivered": str(undelivered).lower(),
                "per_page": str(per_page),
                "page": str(page),
            }
            if from_date:
                params["from_date"] = from_date
            if from_last_update_date:
                params["from_last_update_date"] = from_last_update_date
            if modified is not None:
                params["modified"] = str(modified).lower()
            if booked is not None:
                params["booked"] = str(booked).lower()
            if reservation_number:
                params["reservation_number"] = reservation_number

            try:
                async def _call(p=params):
                    return await self._client.get(ep, params=p, correlation_id=corr_id)

                resp = await self._retry.execute(_call, context=f"pull page={page}")
            except HRv2Error as e:
                logger.error("[HRv2] pull failed page=%d: %s", page, e)
                await record_metric(
                    self._tenant_id, "pull_reservations",
                    success=False, duration_ms=int((time.time() - start) * 1000),
                    error_category=e.category, correlation_id=corr_id,
                )
                return {"success": False, "error": str(e), "correlation_id": corr_id}

            if not resp.success:
                logger.error("[HRv2] pull error page=%d: %s", page, resp.error)
                break

            reservations = resp.data.get("reservations", [])
            all_raw.extend(reservations)

            total_pages = resp.data.get("pages", 1)
            if page >= total_pages:
                break
            page += 1

        # Map to canonical
        canonical_list = []
        for raw in all_raw:
            try:
                canonical_list.append(reservation_to_canonical(raw))
            except Exception as e:
                logger.warning("[HRv2] normalize error: %s (hr_number=%s)", e, raw.get("hr_number"))

        duration_ms = int((time.time() - start) * 1000)
        await record_metric(
            self._tenant_id, "pull_reservations",
            success=True, duration_ms=duration_ms, correlation_id=corr_id,
            metadata={"count": len(all_raw), "pages": page},
        )

        return {
            "success": True,
            "raw_reservations": all_raw,
            "canonical_reservations": canonical_list,
            "count": len(all_raw),
            "duration_ms": duration_ms,
            "correlation_id": corr_id,
        }

    # ── Reservation Ingest (single event) ─────────────────────────────

    async def ingest_reservation(
        self,
        raw_payload: dict[str, Any],
        *,
        received_via: str = "webhook",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """
        Ingest a single reservation through the full pipeline.

        Flow: raw → canonical → dedup → validate → persist → trace
        """
        start = time.time()
        corr_id = correlation_id or str(_uuid.uuid4())[:12]

        try:
            # 1. Map to canonical
            canonical = reservation_to_canonical(raw_payload)
            identity = extract_identity(raw_payload)
            payload_hash = compute_payload_hash(canonical)
            event_type = detect_event_type(canonical)
            idem_key = compute_idempotency_key(
                identity["external_reservation_id"],
                identity.get("provider_version", ""),
            )

            # 2. Store raw event
            from core.database import db as _db
            raw_event_id = str(_uuid.uuid4())
            raw_event = {
                "id": raw_event_id,
                "tenant_id": self._tenant_id,
                "property_id": self._property_id,
                "provider": "hotelrunner",
                "event_type": event_type,
                "received_via": received_via,
                "external_reservation_id": identity["external_reservation_id"],
                "provider_event_id": identity["provider_event_id"],
                "provider_version": identity.get("provider_version", ""),
                "payload_hash": payload_hash,
                "idempotency_key": idem_key,
                "raw_payload": raw_payload,
                "correlation_id": corr_id,
                "trace_id": corr_id,
                "processing_status": "pending",
                "received_at": datetime.now(UTC).isoformat(),
            }
            await _db["raw_channel_events"].insert_one(raw_event)

            # 3. Process through existing pipeline
            from domains.channel_manager.ingest.pipeline import process_event
            pipeline_result = await process_event(raw_event)

            duration_ms = int((time.time() - start) * 1000)
            await record_metric(
                self._tenant_id, "ingest_reservation",
                success=pipeline_result.status == "processed",
                duration_ms=duration_ms, correlation_id=corr_id,
                metadata={
                    "event_type": event_type,
                    "decision": pipeline_result.decision,
                    "external_id": identity["external_reservation_id"],
                },
            )

            return {
                "success": pipeline_result.status == "processed",
                "event_id": raw_event_id,
                "decision": pipeline_result.decision,
                "reason": pipeline_result.reason,
                "status": pipeline_result.status,
                "lineage_id": pipeline_result.lineage_id,
                "correlation_id": corr_id,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            await record_metric(
                self._tenant_id, "ingest_reservation",
                success=False, duration_ms=duration_ms,
                error_category="unknown", correlation_id=corr_id,
            )
            logger.error("[HRv2] ingest error: %s", e)
            return {
                "success": False,
                "error": str(e),
                "correlation_id": corr_id,
                "duration_ms": duration_ms,
            }

    # ── ARI Push ──────────────────────────────────────────────────────

    async def push_ari(
        self,
        inv_code: str,
        start_date: str,
        end_date: str,
        *,
        availability: int | None = None,
        price: float | None = None,
        stop_sale: bool | None = None,
        min_stay: int | None = None,
        cta: bool | None = None,
        ctd: bool | None = None,
        days: list[int] | None = None,
        channel_codes: list[str] | None = None,
        verify: bool = True,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """
        Push ARI update to HotelRunner.
        PUT /api/v2/apps/rooms/~

        Respects shadow mode and write flags.
        Optional verify step via transaction_details.
        """
        corr_id = correlation_id or str(_uuid.uuid4())[:12]
        start = time.time()

        # Shadow mode check
        shadow = await is_shadow_mode(self._tenant_id)
        write_ok = await is_write_enabled(self._tenant_id)

        if shadow or not write_ok:
            duration_ms = int((time.time() - start) * 1000)
            logger.info("[HRv2 SHADOW] ARI push skipped: inv=%s %s→%s (shadow=%s, write=%s)",
                        inv_code, start_date, end_date, shadow, write_ok)
            await record_metric(
                self._tenant_id, "ari_push_shadow",
                success=True, duration_ms=duration_ms, correlation_id=corr_id,
                metadata={"inv_code": inv_code, "shadow": True},
            )
            return {
                "success": True,
                "shadow_mode": True,
                "message": "ARI push skipped (shadow mode)",
                "correlation_id": corr_id,
            }

        form_data = ari_to_update_payload(
            inv_code, start_date, end_date,
            availability=availability, price=price, stop_sale=stop_sale,
            min_stay=min_stay, cta=cta, ctd=ctd,
            days=days, channel_codes=channel_codes,
        )

        ep = get_path("rooms_update")

        try:
            async def _call():
                return await self._client.put(ep, form_data=form_data, correlation_id=corr_id)

            resp = await self._retry.execute(_call, context=f"ARI {inv_code}")
            duration_ms = int((time.time() - start) * 1000)

            await record_metric(
                self._tenant_id, "ari_push",
                success=resp.success, duration_ms=duration_ms, correlation_id=corr_id,
                metadata={"inv_code": inv_code},
            )

            if resp.success:
                # Store in outbox for audit
                await self._store_outbox(corr_id, "ari_push", form_data, resp.data)

                # Verify step (check transaction status)
                transaction_id = resp.data.get("transaction_id")
                verification = None
                if verify and transaction_id:
                    verification = await self.verify_transaction(transaction_id, correlation_id=corr_id)

            return {
                "success": resp.success,
                "data": resp.data,
                "verification": verification if resp.success and verify else None,
                "error": resp.error if not resp.success else None,
                "duration_ms": duration_ms,
                "correlation_id": corr_id,
            }

        except HRv2Error as e:
            duration_ms = int((time.time() - start) * 1000)
            await record_metric(
                self._tenant_id, "ari_push",
                success=False, duration_ms=duration_ms,
                error_category=e.category, correlation_id=corr_id,
            )
            # Send to DLQ on final failure
            await send_to_dlq(
                self._tenant_id, "ari_push", form_data,
                str(e), self._retry.max_retries, corr_id,
            )
            return {
                "success": False,
                "error": str(e),
                "error_category": e.category,
                "dlq": True,
                "correlation_id": corr_id,
                "duration_ms": duration_ms,
            }

    # ── Transaction Verification ──────────────────────────────────────

    async def verify_transaction(self, transaction_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        """
        Verify ARI push result via GET /api/v1/apps/infos/transaction_details

        Returns transaction status with per-channel breakdown.
        """
        corr_id = correlation_id or str(_uuid.uuid4())[:12]
        ep = get_path("transaction_details")

        try:
            resp = await self._client.get(
                ep,
                params={"transaction_id": transaction_id},
                correlation_id=corr_id,
            )
            if resp.success and "transaction" in resp.data:
                txn = resp.data["transaction"]
                counts = txn.get("counts", {})
                return {
                    "transaction_id": txn.get("id", transaction_id),
                    "succeeded": counts.get("succeeded", 0),
                    "failed": counts.get("failed", 0),
                    "in_progress": counts.get("in_progress", 0),
                    "details": txn.get("details", []),
                    "verified": True,
                }
            return {"transaction_id": transaction_id, "verified": False, "error": resp.error}
        except HRv2Error as e:
            logger.warning("[HRv2] verify transaction %s failed: %s", transaction_id, e)
            return {"transaction_id": transaction_id, "verified": False, "error": str(e)}

    # ── Confirm Delivery ──────────────────────────────────────────────

    async def confirm_delivery(self, message_uid: str, pms_number: str | None = None) -> dict[str, Any]:
        """
        Acknowledge reservation delivery to HotelRunner.
        PUT /api/v2/apps/reservations/~
        """
        ep = get_path("reservations_confirm")
        params: dict[str, str] = {"message_uid": message_uid}
        if pms_number:
            params["pms_number"] = pms_number

        try:
            async def _call():
                return await self._client.put(ep, params=params)

            resp = await self._retry.execute(_call, context=f"ack {message_uid}")
            return {"success": resp.success, "data": resp.data, "error": resp.error}
        except HRv2Error as e:
            return {"success": False, "error": str(e), "category": e.category}

    # ── Fetch Channels / Rooms ────────────────────────────────────────

    async def fetch_channels(self) -> dict[str, Any]:
        resp = await self._client.get(get_path("channels_list"))
        return {"success": resp.success, "data": resp.data, "error": resp.error}

    async def fetch_rooms(self) -> dict[str, Any]:
        """
        Fetch room list. Returns rooms with update permissions:
        availability_update, restrictions_update, price_update flags.
        """
        resp = await self._client.get(get_path("rooms_list"))
        return {"success": resp.success, "data": resp.data, "error": resp.error}

    # ── Outbox (audit trail) ──────────────────────────────────────────

    async def _store_outbox(self, corr_id: str, operation: str, request: dict, response: dict) -> None:
        """Store outbound operation in outbox collection for audit."""
        from core.database import db as _db
        await _db["connector_outbox"].insert_one({
            "id": str(_uuid.uuid4()),
            "tenant_id": self._tenant_id,
            "property_id": self._property_id,
            "provider": "hotelrunner_v2",
            "operation": operation,
            "request_payload": request,
            "response_payload": response,
            "correlation_id": corr_id,
            "status": "completed",
            "created_at": datetime.now(UTC).isoformat(),
        })

    # ── Health / Status ───────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Get connector health status."""
        from .metrics import get_last_sync, get_summary

        flags_data = None
        try:
            from .feature_flags import get_flags
            flags_data = await get_flags(self._tenant_id)
        except Exception:
            pass

        summary = await get_summary(self._tenant_id, hours=24)
        last_sync = await get_last_sync(self._tenant_id)

        return {
            "tenant_id": self._tenant_id,
            "property_id": self._property_id,
            "provider": "hotelrunner_v2",
            "environment": self._environment,
            "feature_flags": flags_data,
            "metrics_24h": summary,
            "last_sync": {
                "operation": last_sync.get("operation") if last_sync else None,
                "timestamp": last_sync.get("recorded_at") if last_sync else None,
                "success": last_sync.get("success") if last_sync else None,
            },
        }
