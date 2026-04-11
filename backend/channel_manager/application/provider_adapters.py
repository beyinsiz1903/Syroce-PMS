"""
Provider Adapters — Phase 2: Inventory & Rate Provider Hardening.

Production-grade adapters that wrap the HotelRunner client with:
  - XML builder / parser integration
  - Request correlation_id
  - Raw payload audit (masked + truncated)
  - Error categorisation
  - SyncJob lifecycle integration
  - Reconciliation issue creation on failure
"""
import logging
import time
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from ..connectors.hotelrunner_v2.auth import HotelRunnerAuth
from ..connectors.hotelrunner_v2.hr_client import HotelRunnerClient
from ..connectors.hotelrunner_v2.connector_errors import (
    AuthenticationError,
    ProviderUnavailableError,
    ProviderValidationError,
    RateLimitError,
    SchemaMismatchError,
    UnknownResponseFormatError,
    XmlParseError,
)
from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.provider_adapters")

MASK_KEYS = {"token", "password", "secret", "api_key"}
TRUNCATE_LEN = 4000

ERROR_TYPE_MAP = {
    AuthenticationError: "auth_error",
    ProviderValidationError: "provider_validation_error",
    RateLimitError: "rate_limit_error",
    ProviderUnavailableError: "provider_unavailable",
    XmlParseError: "invalid_xml",
    SchemaMismatchError: "schema_mismatch",
    UnknownResponseFormatError: "unknown_response_format",
}


def _categorise_error(exc: Exception) -> str:
    for cls, label in ERROR_TYPE_MAP.items():
        if isinstance(exc, cls):
            return label
    return "unknown_error"


def _mask_payload(payload: str) -> str:
    """Mask sensitive tokens in raw payload strings."""
    for key in MASK_KEYS:
        if key in payload.lower():
            import re
            payload = re.sub(
                rf'({key}["\s:=]+)([^"&\s<>]+)',
                r'\1****',
                payload, flags=re.IGNORECASE,
            )
    return payload


def _truncate(text: str, max_len: int = TRUNCATE_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"...[truncated, total {len(text)}]"


class InventoryProviderAdapter:
    """
    Wraps HotelRunnerClient.push_availability with production-grade
    error handling, auditing, and reconciliation integration.
    """

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def push(
        self,
        tenant_id: str,
        connector_id: str,
        property_id: str,
        updates: list[dict[str, Any]],
        credentials: dict[str, str],
        environment: str = "sandbox",
        correlation_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        corr_id = correlation_id or str(_uuid.uuid4())
        start = time.monotonic()

        auth = HotelRunnerAuth.from_credentials(credentials)
        client = HotelRunnerClient(auth=auth, environment=environment)

        audit_entry = {
            "correlation_id": corr_id,
            "operation": "inventory_push",
            "environment": environment,
            "update_count": len(updates),
            "timestamp": datetime.now(UTC).isoformat(),
            "job_id": job_id,
        }

        try:
            result = await client.push_availability(updates, correlation_id=corr_id)
            latency_ms = int((time.monotonic() - start) * 1000)

            audit_entry.update({
                "success": result.get("success", False),
                "latency_ms": latency_ms,
                "raw_request_len": result.get("raw_request_len", 0),
                "raw_response_len": result.get("raw_response_len", 0),
            })

            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.INVENTORY_PUSHED, metadata=audit_entry,
            )

            return {
                "success": result.get("success", False),
                "correlation_id": corr_id,
                "latency_ms": latency_ms,
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
                "raw_request_len": result.get("raw_request_len", 0),
                "raw_response_len": result.get("raw_response_len", 0),
            }

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            error_type = _categorise_error(e)

            audit_entry.update({
                "success": False,
                "latency_ms": latency_ms,
                "error_type": error_type,
                "error_message": _truncate(str(e)),
            })

            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.SYNC_JOB_FAILED, metadata=audit_entry,
            )

            # Create reconciliation issue for push failure
            await self._create_push_failure_issue(
                tenant_id, property_id, connector_id,
                error_type, str(e), corr_id, job_id,
            )

            return {
                "success": False,
                "correlation_id": corr_id,
                "latency_ms": latency_ms,
                "error_type": error_type,
                "error_message": str(e)[:500],
            }
        finally:
            await client.close()

    async def _create_push_failure_issue(
        self, tenant_id, property_id, connector_id,
        error_type, error_message, correlation_id, job_id,
    ):
        from ..application.reconciliation_service import ReconciliationService
        recon = ReconciliationService(self._repo)
        await recon.create_issue(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            issue_type="inventory_mismatch",
            severity="high" if error_type in ("auth_error", "provider_unavailable") else "medium",
            description=f"Inventory push failed: {error_type} — {error_message[:200]}",
            suggested_actions=["retry_sync"],
            evidence_payload={
                "error_type": error_type,
                "correlation_id": correlation_id,
                "job_id": job_id,
            },
            related_sync_job_ids=[job_id] if job_id else [],
        )

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
            action=action, actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())


class RateProviderAdapter:
    """
    Wraps HotelRunnerClient.push_rates with production-grade
    error handling, auditing, and reconciliation integration.
    """

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def push(
        self,
        tenant_id: str,
        connector_id: str,
        property_id: str,
        updates: list[dict[str, Any]],
        credentials: dict[str, str],
        environment: str = "sandbox",
        correlation_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        corr_id = correlation_id or str(_uuid.uuid4())
        start = time.monotonic()

        auth = HotelRunnerAuth.from_credentials(credentials)
        client = HotelRunnerClient(auth=auth, environment=environment)

        audit_entry = {
            "correlation_id": corr_id,
            "operation": "rate_push",
            "environment": environment,
            "update_count": len(updates),
            "timestamp": datetime.now(UTC).isoformat(),
            "job_id": job_id,
        }

        try:
            result = await client.push_rates(updates, correlation_id=corr_id)
            latency_ms = int((time.monotonic() - start) * 1000)

            audit_entry.update({
                "success": result.get("success", False),
                "latency_ms": latency_ms,
                "raw_request_len": result.get("raw_request_len", 0),
                "raw_response_len": result.get("raw_response_len", 0),
            })

            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RATES_PUSHED, metadata=audit_entry,
            )

            return {
                "success": result.get("success", False),
                "correlation_id": corr_id,
                "latency_ms": latency_ms,
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
                "raw_request_len": result.get("raw_request_len", 0),
                "raw_response_len": result.get("raw_response_len", 0),
            }

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            error_type = _categorise_error(e)

            audit_entry.update({
                "success": False,
                "latency_ms": latency_ms,
                "error_type": error_type,
                "error_message": _truncate(str(e)),
            })

            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.SYNC_JOB_FAILED, metadata=audit_entry,
            )

            # Create reconciliation issue for rate push failure
            from ..application.reconciliation_service import ReconciliationService
            recon = ReconciliationService(self._repo)
            await recon.create_issue(
                tenant_id=tenant_id,
                property_id=property_id,
                connector_id=connector_id,
                issue_type="rate_mismatch",
                severity="high" if error_type in ("auth_error", "provider_unavailable") else "medium",
                description=f"Rate push failed: {error_type} — {str(e)[:200]}",
                suggested_actions=["retry_sync"],
                evidence_payload={
                    "error_type": error_type,
                    "correlation_id": corr_id,
                    "job_id": job_id,
                },
                related_sync_job_ids=[job_id] if job_id else [],
            )

            return {
                "success": False,
                "correlation_id": corr_id,
                "latency_ms": latency_ms,
                "error_type": error_type,
                "error_message": str(e)[:500],
            }
        finally:
            await client.close()

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
            action=action, actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
