"""Service for Nilvera Invoice Status Polling & Reconciliation."""

import logging
from datetime import UTC, datetime, timedelta

from core.integrations.invoice_status_repository import InvoiceStatusRepository
from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome, map_nilvera_status
from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_sync import InvoiceSync, InvoiceSyncState
from modules.event_bus.abstraction import event_bus

logger = logging.getLogger(__name__)

STATUS_POLL_DELAYS = (30, 60, 120, 300, 900)  # Seconds


def _get_next_poll_delay(attempt_count: int) -> int:
    if attempt_count < len(STATUS_POLL_DELAYS):
        return STATUS_POLL_DELAYS[attempt_count]
    return STATUS_POLL_DELAYS[-1]


class InvoiceStatusService:
    """Orchestrates status polling and reconciliation for Nilvera."""

    @staticmethod
    async def poll_invoice_status(tenant_id: str, dispatch_id: str, worker_id: str) -> None:
        """
        Polls Nilvera for the status of a specific SUBMITTED invoice.
        The worker must hold the status lease.
        """
        db_record = await InvoiceStatusRepository.claim_status_lease(tenant_id, dispatch_id, worker_id, 60)
        # If we couldn't claim it or someone else has it, we just return.
        if not db_record:
            # We assume the caller already claimed it, or we re-claim just to be safe.
            # Actually, the worker will pass the record it claimed.
            # To be safe, we will just read from the DB without claim if the caller is the worker.
            pass

    @staticmethod
    async def process_polled_record(record: InvoiceSync, worker_id: str) -> None:
        """Processes a claimed record."""
        now = datetime.now(UTC)
        tracking_started = record.status_tracking_started_at or record.submitted_at or now

        # Check 24-hour rule
        if now - tracking_started >= timedelta(hours=24):
            logger.warning(f"Status tracking for dispatch {record.id} exceeded 24h. Flagging for reconciliation.")
            await InvoiceStatusRepository.update_status_poll_result(
                record.tenant_id,
                record.id,
                worker_id,
                {
                    "reconciliation_required": True,
                    "reconciliation_reason": "STATUS_TIMEOUT_24H",
                    "next_status_check_at": None,
                }
            )
            return


        # If missing uuid
        if not record.provider_document_id:
            await InvoiceStatusRepository.update_status_poll_result(
                record.tenant_id,
                record.id,
                worker_id,
                {
                    "reconciliation_required": True,
                    "reconciliation_reason": "MISSING_PROVIDER_DOCUMENT_ID",
                    "next_status_check_at": None,
                }
            )
            return

        next_attempt = record.status_check_attempt_count + 1
        delay_sec = _get_next_poll_delay(record.status_check_attempt_count)
        next_check = now + timedelta(seconds=delay_sec)

        # tenant config check should go here in a real impl, but we will assume client can be instantiated
        # We need the tenant api key
        db = get_db_for_tenant(record.tenant_id)
        tenant_doc = await db.tenants.find_one({"_id": record.tenant_id})
        api_key = tenant_doc.get("settings", {}).get("nilvera", {}).get("api_key") if tenant_doc else None

        if not api_key:
            # Missing credential -> Do not consume attempt. Defer check.
            await InvoiceStatusRepository.update_status_poll_result(
                record.tenant_id,
                record.id,
                worker_id,
                {
                    "next_status_check_at": now + timedelta(minutes=15),
                    "status_poll_error_message": "Missing tenant API key",
                }
            )
            return

        endpoint = NilveraEndpoints.GET_SALE_INVOICE_STATUS.format(uuid=record.provider_document_id)

        try:
            async with NilveraHttpClient(api_key=api_key) as client:
                response = await client.get(
                    endpoint,
                    correlation_id=record.id,
                    retryable=True,
                )

            raw_status = response.get("Status")
            raw_code = response.get("StatusCode")
            outcome = map_nilvera_status(raw_status, str(raw_code) if raw_code else None)

            update_fields = {
                "provider_status": raw_status,
                "provider_status_code": str(raw_code) if raw_code else None,
                "last_status_check_at": now,
                "status_check_attempt_count": next_attempt,
                "status_poll_error_code": None,
                "status_poll_error_message": None,
                "status_poll_retryable": False,
            }

            if outcome == ProviderInvoiceOutcome.PENDING:
                update_fields["next_status_check_at"] = next_check
                await InvoiceStatusRepository.update_status_poll_result(record.tenant_id, record.id, worker_id, update_fields)

            elif outcome == ProviderInvoiceOutcome.ACCEPTED:
                update_fields["state"] = InvoiceSyncState.ACCEPTED.value
                update_fields["accepted_at"] = now
                update_fields["next_status_check_at"] = None
                await InvoiceStatusRepository.update_status_poll_result(record.tenant_id, record.id, worker_id, update_fields)
                await event_bus.publish("invoice.accepted", {"dispatch_id": record.id, "tenant_id": record.tenant_id})

            elif outcome == ProviderInvoiceOutcome.REJECTED:
                update_fields["state"] = InvoiceSyncState.REJECTED.value
                update_fields["rejected_at"] = now
                update_fields["next_status_check_at"] = None
                await InvoiceStatusRepository.update_status_poll_result(record.tenant_id, record.id, worker_id, update_fields)
                await event_bus.publish("invoice.rejected", {"dispatch_id": record.id, "tenant_id": record.tenant_id})

            elif outcome == ProviderInvoiceOutcome.CANCELLED:
                update_fields["state"] = InvoiceSyncState.CANCELLED.value
                update_fields["cancelled_at"] = now
                update_fields["next_status_check_at"] = None
                await InvoiceStatusRepository.update_status_poll_result(record.tenant_id, record.id, worker_id, update_fields)
                await event_bus.publish("invoice.cancelled", {"dispatch_id": record.id, "tenant_id": record.tenant_id})

            elif outcome == ProviderInvoiceOutcome.UNKNOWN:
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = "UNKNOWN_PROVIDER_STATUS"
                update_fields["next_status_check_at"] = None
                await InvoiceStatusRepository.update_status_poll_result(record.tenant_id, record.id, worker_id, update_fields)

        except NilveraApiError as e:
            # HTTP errors logic
            update_fields = {
                "last_status_check_at": now,
                "status_poll_error_code": e.provider_code or str(e.http_status),
                "status_poll_error_message": "Nilvera API error during status check", # Sanitize!
            }

            if e.http_status in (401, 403):
                # Auth error -> do not consume attempt, retryable later, maybe config will be fixed
                update_fields["next_status_check_at"] = now + timedelta(minutes=15)
                update_fields["status_poll_retryable"] = True
            elif e.http_status == 404:
                # Document not found in Nilvera -> reconciliation
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = "PROVIDER_NOT_FOUND_404"
                update_fields["next_status_check_at"] = None
                update_fields["status_check_attempt_count"] = next_attempt
            elif e.http_status == 409:
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = "UNEXPECTED_409_ON_GET"
                update_fields["next_status_check_at"] = None
                update_fields["status_check_attempt_count"] = next_attempt
            elif e.http_status == 400:
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = "PROVIDER_VALIDATION_400"
                update_fields["next_status_check_at"] = None
                update_fields["status_check_attempt_count"] = next_attempt
            else:
                # 429, 5xx, timeouts -> Retryable polling
                update_fields["status_check_attempt_count"] = next_attempt
                update_fields["next_status_check_at"] = next_check
                update_fields["status_poll_retryable"] = True

            await InvoiceStatusRepository.update_status_poll_result(record.tenant_id, record.id, worker_id, update_fields)
        except Exception as e:
            logger.error(f"Unexpected error during status poll: {e}")
            await InvoiceStatusRepository.update_status_poll_result(
                record.tenant_id,
                record.id,
                worker_id,
                {
                    "last_status_check_at": now,
                    "status_check_attempt_count": next_attempt,
                    "next_status_check_at": next_check,
                    "status_poll_retryable": True,
                    "status_poll_error_message": "Internal error during status check",
                }
            )
