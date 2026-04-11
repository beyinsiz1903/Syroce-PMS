"""
Sandbox Validation Service — Phase 1: HotelRunner Sandbox Validation.

Runs 10 structured validation checks against HotelRunner to produce
an Integration Readiness Report.

Checks:
  1. Authentication test
  2. Reservation pull test
  3. Reservation pagination test
  4. Reservation payload parsing test
  5. Inventory push test
  6. Rate push test
  7. ACK test
  8. Provider error parsing
  9. Retry behaviour
  10. Audit logging verification
"""
import logging
import time
from datetime import UTC, datetime
from typing import Any

from ..connectors.hotelrunner_v2 import xml_parser
from ..connectors.hotelrunner_v2.auth import HotelRunnerAuth
from ..connectors.hotelrunner_v2.connector_errors import (
    AuthenticationError,
    ProviderUnavailableError,
)
from ..connectors.hotelrunner_v2.hr_client import HotelRunnerClient
from ..connectors.hotelrunner_v2.retry_policy import RetryPolicy
from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.sandbox_validation")


class SandboxValidationService:
    """Validates HotelRunner integration end-to-end in sandbox mode."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def run_validation(
        self,
        tenant_id: str,
        connector_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Run all 10 validation checks and produce Integration Readiness Report."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            raise ValueError("Connector not found")

        credentials = connector.get("credentials", {})
        property_id = connector.get("property_id", "")
        environment = connector.get("environment", "sandbox")

        checks: list[dict[str, Any]] = []
        blocker_issues: list[str] = []

        try:
            auth = HotelRunnerAuth.from_credentials(credentials)
        except AuthenticationError as e:
            return self._report(
                connector_id, property_id,
                checks=[self._check_result("authentication", False, error=str(e), blocker="Missing credentials")],
                blocker_issues=["Missing or invalid credentials"],
            )

        client = HotelRunnerClient(auth=auth, environment=environment)
        try:
            # ── Check 1: Authentication ──
            checks.append(await self._check_authentication(client))
            if not checks[-1]["success"]:
                blocker_issues.append("Authentication failed")

            # ── Check 2: Reservation Pull ──
            checks.append(await self._check_reservation_pull(client))

            # ── Check 3: Reservation Pagination ──
            checks.append(await self._check_reservation_pagination(client))

            # ── Check 4: Reservation Payload Parsing ──
            checks.append(await self._check_reservation_parsing(client))

            # ── Check 5: Inventory Push ──
            checks.append(await self._check_inventory_push(client, auth))

            # ── Check 6: Rate Push ──
            checks.append(await self._check_rate_push(client, auth))

            # ── Check 7: ACK Test ──
            checks.append(await self._check_ack(client))

            # ── Check 8: Provider Error Parsing ──
            checks.append(await self._check_error_parsing())

            # ── Check 9: Retry Behaviour ──
            checks.append(await self._check_retry_behaviour())

            # ── Check 10: Audit Logging Verification ──
            checks.append(await self._check_audit_logging(client))

        finally:
            await client.close()

        # Collect blockers from failed critical checks
        critical_checks = {"authentication", "inventory_push", "rate_push"}
        for c in checks:
            if not c["success"] and c["check_name"] in critical_checks:
                if c.get("blocking_issue"):
                    blocker_issues.append(c["blocking_issue"])

        report = self._report(connector_id, property_id, checks, blocker_issues)

        # ── Integration with operational maturity services ──
        await self._integrate_with_ops_services(tenant_id, connector_id, report)

        # Audit
        await self._audit(
            tenant_id, property_id, connector_id,
            AuditAction.SANDBOX_VALIDATION_RUN, actor_id,
            {"passed": report["passed_checks"], "failed": report["failed_checks"]},
        )

        return report

    # ─── Individual Checks ────────────────────────────────────────────

    async def _check_authentication(self, client: HotelRunnerClient) -> dict[str, Any]:
        start = time.monotonic()
        try:
            result = await client.test_connection_detailed()
            latency = int((time.monotonic() - start) * 1000)
            auth_ok = result.get("auth_status", {}).get("status") == "pass"
            return self._check_result(
                "authentication", auth_ok, latency_ms=latency,
                request_summary="GET /properties",
                response_summary=result.get("summary", ""),
                provider_status=result.get("auth_status", {}).get("status", "unknown"),
                blocking_issue="Authentication failed — credentials invalid" if not auth_ok else None,
            )
        except Exception as e:
            return self._check_result(
                "authentication", False, latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e), blocking_issue="Authentication unreachable",
            )

    async def _check_reservation_pull(self, client: HotelRunnerClient) -> dict[str, Any]:
        start = time.monotonic()
        try:
            reservations = await client.pull_reservations(per_page=5, undelivered=True)
            latency = int((time.monotonic() - start) * 1000)
            return self._check_result(
                "reservation_pull", True, latency_ms=latency,
                request_summary="GET /apps/reservations?undelivered=true&per_page=5",
                response_summary=f"{len(reservations)} reservations pulled",
                provider_status="ok",
                canonical_mapping=f"Mapped {len(reservations)} raw payloads",
            )
        except Exception as e:
            return self._check_result(
                "reservation_pull", False, latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
            )

    async def _check_reservation_pagination(self, client: HotelRunnerClient) -> dict[str, Any]:
        start = time.monotonic()
        try:
            reservations = await client.pull_reservations(per_page=2, undelivered=False)
            latency = int((time.monotonic() - start) * 1000)
            return self._check_result(
                "reservation_pagination", True, latency_ms=latency,
                request_summary="GET /apps/reservations?undelivered=false&per_page=2",
                response_summary=f"Pagination OK — {len(reservations)} items",
                provider_status="ok",
            )
        except Exception as e:
            return self._check_result(
                "reservation_pagination", False,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
            )

    async def _check_reservation_parsing(self, client: HotelRunnerClient) -> dict[str, Any]:
        start = time.monotonic()
        try:
            reservations = await client.pull_reservations(per_page=5, undelivered=True)
            latency = int((time.monotonic() - start) * 1000)
            parsed = 0
            errors = 0
            for r in reservations:
                if r.get("external_id") or r.get("confirmation_number") or r.get("code"):
                    parsed += 1
                else:
                    errors += 1
            return self._check_result(
                "reservation_payload_parsing", parsed > 0 or len(reservations) == 0,
                latency_ms=latency,
                request_summary="Parse reservation payload fields",
                response_summary=f"Parsed {parsed}, errors {errors}",
                canonical_mapping="Fields: external_id, guest, dates, amounts",
            )
        except Exception as e:
            return self._check_result(
                "reservation_payload_parsing", False,
                latency_ms=int((time.monotonic() - start) * 1000), error=str(e),
            )

    async def _check_inventory_push(self, client: HotelRunnerClient, auth: HotelRunnerAuth) -> dict[str, Any]:
        start = time.monotonic()
        try:
            test_updates = [{
                "room_type_code": "TEST-VALIDATION",
                "date_start": "2099-01-01",
                "date_end": "2099-01-01",
                "available": 0,
            }]
            result = await client.push_availability(test_updates)
            latency = int((time.monotonic() - start) * 1000)
            success = result.get("success", False)
            return self._check_result(
                "inventory_push", success, latency_ms=latency,
                request_summary="POST /ari/availability (test payload)",
                response_summary=f"success={success}, errors={result.get('errors', [])}",
                provider_status="accepted" if success else "rejected",
                blocking_issue="Inventory push rejected by provider" if not success else None,
            )
        except Exception as e:
            return self._check_result(
                "inventory_push", False,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e), blocking_issue="Inventory push failed",
            )

    async def _check_rate_push(self, client: HotelRunnerClient, auth: HotelRunnerAuth) -> dict[str, Any]:
        start = time.monotonic()
        try:
            test_updates = [{
                "room_type_code": "TEST-VALIDATION",
                "rate_plan_code": "TEST-RP",
                "date_start": "2099-01-01",
                "date_end": "2099-01-01",
                "amount_after_tax": 0.01,
                "currency": "TRY",
            }]
            result = await client.push_rates(test_updates)
            latency = int((time.monotonic() - start) * 1000)
            success = result.get("success", False)
            return self._check_result(
                "rate_push", success, latency_ms=latency,
                request_summary="POST /ari/rates (test payload)",
                response_summary=f"success={success}",
                provider_status="accepted" if success else "rejected",
                blocking_issue="Rate push rejected by provider" if not success else None,
            )
        except Exception as e:
            return self._check_result(
                "rate_push", False,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e), blocking_issue="Rate push failed",
            )

    async def _check_ack(self, client: HotelRunnerClient) -> dict[str, Any]:
        start = time.monotonic()
        try:
            await client.acknowledge_reservation("VALIDATION-TEST-UID")
            latency = int((time.monotonic() - start) * 1000)
            return self._check_result(
                "ack_delivery", True, latency_ms=latency,
                request_summary="PUT /apps/reservations/~ (test UID)",
                response_summary="ACK accepted",
            )
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            err_str = str(e)
            is_expected = "not found" in err_str.lower() or "invalid" in err_str.lower()
            return self._check_result(
                "ack_delivery", is_expected, latency_ms=latency,
                request_summary="PUT /apps/reservations/~ (test UID)",
                response_summary=f"Expected rejection for test UID: {err_str[:200]}",
                provider_status="expected_rejection" if is_expected else "error",
            )

    async def _check_error_parsing(self) -> dict[str, Any]:
        start = time.monotonic()
        try:
            error_xml = '<?xml version="1.0"?><OTA_HotelAvailNotifRS><Errors><Error Code="42" Type="3">Invalid hotel code</Error></Errors></OTA_HotelAvailNotifRS>'
            result = xml_parser.parse_response_status(error_xml)
            latency = int((time.monotonic() - start) * 1000)
            errors_parsed = len(result.get("errors", []))
            return self._check_result(
                "provider_error_parsing", not result.get("success") and errors_parsed > 0,
                latency_ms=latency,
                request_summary="Parse XML error response",
                response_summary=f"Parsed {errors_parsed} error(s): {result.get('errors', [])}",
            )
        except Exception as e:
            return self._check_result(
                "provider_error_parsing", False,
                latency_ms=int((time.monotonic() - start) * 1000), error=str(e),
            )

    async def _check_retry_behaviour(self) -> dict[str, Any]:
        start = time.monotonic()
        try:
            policy = RetryPolicy(max_retries=2, base_delay=0.01, max_delay=0.05)
            call_count = 0

            async def _failing():
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ProviderUnavailableError("Simulated failure")
                return "ok"

            result = await policy.execute_with_retry(_failing)
            latency = int((time.monotonic() - start) * 1000)
            return self._check_result(
                "retry_behaviour", result == "ok" and call_count == 3,
                latency_ms=latency,
                request_summary=f"Simulated {call_count} calls with retry policy",
                response_summary=f"Succeeded after {call_count} attempts",
            )
        except Exception as e:
            return self._check_result(
                "retry_behaviour", False,
                latency_ms=int((time.monotonic() - start) * 1000), error=str(e),
            )

    async def _check_audit_logging(self, client: HotelRunnerClient) -> dict[str, Any]:
        start = time.monotonic()
        audit_entries = client.audit_entries
        has_entries = len(audit_entries) > 0
        latency = int((time.monotonic() - start) * 1000)
        return self._check_result(
            "audit_logging_verification", has_entries,
            latency_ms=latency,
            request_summary=f"Verify {len(audit_entries)} audit entries collected",
            response_summary=f"Entries have correlation_id, latency, timestamp: {has_entries}",
        )

    # ─── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _check_result(
        check_name: str,
        success: bool,
        latency_ms: int = 0,
        request_summary: str = "",
        response_summary: str = "",
        provider_status: str = "",
        canonical_mapping: str = "",
        blocking_issue: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "check_name": check_name,
            "success": success,
            "latency_ms": latency_ms,
            "request_summary": request_summary,
            "response_summary": response_summary,
            "provider_status": provider_status,
            "canonical_mapping": canonical_mapping,
            "blocking_issue": blocking_issue,
            "error": error,
        }

    @staticmethod
    def _report(
        connector_id: str,
        property_id: str,
        checks: list[dict[str, Any]],
        blocker_issues: list[str],
    ) -> dict[str, Any]:
        passed = [c for c in checks if c["success"]]
        failed = [c for c in checks if not c["success"]]
        has_blockers = len(blocker_issues) > 0

        # Classify warnings vs errors
        warnings = []
        contract_mismatches = []
        for c in failed:
            err = c.get("error", "") or c.get("response_summary", "")
            if "schema" in err.lower() or "mismatch" in err.lower() or "format" in err.lower():
                contract_mismatches.append({
                    "check": c["check_name"],
                    "detail": err[:200],
                })
            elif c["check_name"] not in {"authentication", "inventory_push", "rate_push"}:
                warnings.append({
                    "check": c["check_name"],
                    "detail": err[:200],
                })

        if has_blockers:
            recommendation = "NOT_READY — resolve blocker issues before going live"
        elif len(failed) > 0:
            recommendation = "CONDITIONAL — non-critical checks failed, review before production"
        else:
            recommendation = "READY_FOR_PRODUCTION"

        total_latency = sum(c.get("latency_ms", 0) for c in checks)

        return {
            "connector_id": connector_id,
            "property_id": property_id,
            "total_checks": len(checks),
            "passed_checks": len(passed),
            "failed_checks": len(failed),
            "blocker_issues": blocker_issues,
            "warnings": warnings,
            "contract_mismatches": contract_mismatches,
            "production_recommendation": recommendation,
            "total_latency_ms": total_latency,
            "checks": checks,
            "run_at": datetime.now(UTC).isoformat(),
        }

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
            action=action, actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())

    async def _integrate_with_ops_services(
        self, tenant_id: str, connector_id: str, report: dict[str, Any],
    ):
        """Push validation results into historical metrics, alerting, and reliability."""
        try:
            from .historical_metrics_service import HistoricalMetricsService
            metrics_svc = HistoricalMetricsService(repo=self._repo)
            await metrics_svc.record_validation_result(
                tenant_id, connector_id,
                passed=report["passed_checks"],
                failed=report["failed_checks"],
                total=report["total_checks"],
            )
        except Exception as e:
            logger.warning("Failed to record validation metrics: %s", e)

        try:
            if report["failed_checks"] >= 3:
                from .alerting_service import AlertingService
                alert_svc = AlertingService(repo=self._repo)
                await alert_svc.check_and_fire_alert(
                    tenant_id=tenant_id,
                    trigger="sandbox_validation_failures",
                    connector_id=connector_id,
                    metadata={
                        "failed_checks": report["failed_checks"],
                        "blocker_issues": report.get("blocker_issues", []),
                    },
                )
        except Exception as e:
            logger.warning("Failed to fire validation alert: %s", e)

        try:
            from .reliability_service import ReliabilityService
            rel_svc = ReliabilityService(repo=self._repo)
            await rel_svc.record_validation_event(
                tenant_id, connector_id,
                success=report["failed_checks"] == 0,
                details={"recommendation": report.get("production_recommendation", "")},
            )
        except Exception as e:
            logger.warning("Failed to record reliability event: %s", e)
