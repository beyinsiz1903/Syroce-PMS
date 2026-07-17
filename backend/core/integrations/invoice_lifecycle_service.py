"""Service for Nilvera Incoming Invoice Lifecycle Operations (Reject, Return)."""

import logging
from datetime import UTC, datetime, timedelta

from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.provisioner import get_nilvera_tenant_config
from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType
from modules.event_bus.abstraction import event_bus

logger = logging.getLogger(__name__)

STATUS_POLL_DELAYS = (30, 60, 120, 300, 900)  # Seconds


def _get_next_poll_delay(attempt_count: int) -> int:
    if attempt_count < len(STATUS_POLL_DELAYS):
        return STATUS_POLL_DELAYS[attempt_count]
    return STATUS_POLL_DELAYS[-1]


class InvoiceLifecycleService:
    """Orchestrates lifecycle actions for incoming invoices."""

    @staticmethod
    async def process_lifecycle_action(tenant_id: str, action_id: str, worker_id: str) -> bool:
        """
        Executes a claimed lifecycle action.
        The worker must hold the action lease.
        """
        action = await InvoiceLifecycleRepository.claim_action_lease(tenant_id, action_id, worker_id, 60)
        if not action:
            return False

        await InvoiceLifecycleService._process_claimed_action(action, worker_id)
        return True

    @staticmethod
    async def _process_claimed_action(action: InvoiceLifecycleAction, worker_id: str) -> None:
        """Processes a claimed action."""
        now = datetime.now(UTC)

        import uuid

        try:
            normalized_uuid = str(uuid.UUID(action.source_provider_uuid))
        except (ValueError, TypeError):
            await InvoiceLifecycleRepository.update_action_result(
                action.tenant_id,
                action.id,
                worker_id,
                update_fields={
                    "state": InvoiceLifecycleActionState.FAILED.value,
                    "reconciliation_required": True,
                    "reconciliation_reason": "INVALID_PROVIDER_UUID",
                    "next_attempt_at": None,
                },
                unset_fields={"answer_guard_key": ""}
            )
            return

        next_attempt = action.attempt_count + 1

        nilvera_cfg = await get_nilvera_tenant_config(action.tenant_id, decrypt_api_key=True)
        if not nilvera_cfg.get("enabled") or not nilvera_cfg.get("api_key"):
            await InvoiceLifecycleRepository.update_action_result(
                action.tenant_id,
                action.id,
                worker_id,
                {
                    "state": InvoiceLifecycleActionState.RETRY_SCHEDULED.value,
                    "next_attempt_at": now + timedelta(minutes=15),
                    "reason": "Missing tenant API key",
                },
            )
            return

        api_key = nilvera_cfg["api_key"]

        try:
            if action.action_type in (InvoiceLifecycleActionType.ACCEPT_INCOMING, InvoiceLifecycleActionType.REJECT_INCOMING):
                await InvoiceLifecycleService._execute_send_answer(action, normalized_uuid, api_key)
            else:
                raise ValueError(f"Unknown action type: {action.action_type}")

            # If successful, mark as SUCCEEDED
            await InvoiceLifecycleRepository.update_action_result(
                action.tenant_id,
                action.id,
                worker_id,
                {
                    "state": InvoiceLifecycleActionState.SUCCEEDED.value,
                    "attempt_count": next_attempt,
                    "next_attempt_at": None,
                    "completed_at": datetime.now(UTC),
                },
            )

            await event_bus.publish(
                f"invoice.lifecycle.{action.action_type.value.lower()}.completed", {"action_id": action.id, "tenant_id": action.tenant_id, "source_invoice_id": action.source_invoice_id}
            )

        except NilveraApiError as e:
            update_fields = {
                "attempt_count": next_attempt,
            }
            unset_fields = None

            if e.http_status in (401, 403):
                update_fields["state"] = InvoiceLifecycleActionState.FAILED.value
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = "CREDENTIAL_ERROR"
                update_fields["next_attempt_at"] = None
                unset_fields = {"answer_guard_key": ""}
            elif e.http_status == 400:
                update_fields["state"] = InvoiceLifecycleActionState.FAILED.value
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = "BAD_REQUEST"
                update_fields["next_attempt_at"] = None
                unset_fields = {"answer_guard_key": ""}
            elif e.http_status in (404, 409, 429) or e.http_status >= 500:
                update_fields["state"] = InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = f"PROVIDER_ERROR_{e.http_status}"
                update_fields["next_attempt_at"] = None
            else:
                # Connection error without request going through or other unknown errors
                update_fields["state"] = InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = "UNKNOWN_ERROR"
                update_fields["next_attempt_at"] = None

            await InvoiceLifecycleRepository.update_action_result(action.tenant_id, action.id, worker_id, update_fields, unset_fields)
            await event_bus.publish(f"invoice.lifecycle.{action.action_type.value.lower()}.failed", {"action_id": action.id, "tenant_id": action.tenant_id, "reason": str(e)})

        except Exception as e:
            logger.error(f"Unexpected error during lifecycle action {action.id}: {e}")
            await InvoiceLifecycleRepository.update_action_result(
                action.tenant_id,
                action.id,
                worker_id,
                {
                    "state": InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value,
                    "reconciliation_required": True,
                    "reconciliation_reason": "INTERNAL_ERROR",
                    "attempt_count": next_attempt,
                    "next_attempt_at": None,
                },
            )

    @staticmethod
    async def _execute_send_answer(action: InvoiceLifecycleAction, provider_uuid: str, api_key: str) -> None:
        answer_code = "approved" if action.action_type == InvoiceLifecycleActionType.ACCEPT_INCOMING else "rejected"
        payload = {"UUID": provider_uuid, "AnswerCode": answer_code}
        if action.reason:
            payload["RejectNote"] = action.reason

        async with NilveraHttpClient(api_key=api_key) as client:
            await client.post(
                NilveraEndpoints.SEND_ANSWER,
                payload=payload,
                correlation_id=action.id,
                retryable=False,
            )
