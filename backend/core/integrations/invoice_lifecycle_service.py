"""Safe orchestration for Nilvera incoming invoice answers."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.incoming_answer import (
    NilveraIncomingAnswerDecision,
    NilveraIncomingAnswerService,
    NilveraIncomingAnswerState,
)
from core.integrations.nilvera.provisioner import get_nilvera_tenant_config
from models.schemas.incoming_invoice import IncomingInvoiceAnswerStatus
from models.schemas.invoice_lifecycle import (
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
)
from modules.event_bus.abstraction import event_bus

logger = logging.getLogger(__name__)

STATUS_POLL_DELAYS = (30, 60, 120, 300, 900)


def _get_next_poll_delay(attempt_count: int) -> int:
    index = min(max(attempt_count, 0), len(STATUS_POLL_DELAYS) - 1)
    return STATUS_POLL_DELAYS[index]


class InvoiceLifecycleService:
    """Executes one leased lifecycle action without retrying provider writes."""

    @classmethod
    async def process_lifecycle_action(cls, tenant_id: str, action_id: str, worker_id: str) -> bool:
        action = await InvoiceLifecycleRepository.claim_action_lease(
            tenant_id,
            action_id,
            worker_id,
            60,
        )
        if action is None:
            return False

        await cls._process_claimed_action(action, worker_id)
        return True

    @classmethod
    async def _process_claimed_action(cls, action: InvoiceLifecycleAction, worker_id: str) -> None:
        try:
            provider_uuid = str(uuid.UUID(action.source_provider_uuid))
        except (TypeError, ValueError):
            await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.FAILED,
                error_code="INVALID_PROVIDER_UUID",
                release_answer_guard=True,
            )
            return

        try:
            decision = cls._decision_for(action)
        except ValueError:
            await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.FAILED,
                error_code="UNSUPPORTED_ACTION_TYPE",
                release_answer_guard=True,
            )
            return

        try:
            tenant_config = await get_nilvera_tenant_config(action.tenant_id, decrypt_api_key=True)
        except Exception:
            await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.RETRY_SCHEDULED,
                error_code="TENANT_CONFIGURATION_UNAVAILABLE",
                next_attempt_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            return
        if not isinstance(tenant_config, dict):
            await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.RETRY_SCHEDULED,
                error_code="TENANT_CONFIGURATION_UNAVAILABLE",
                next_attempt_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            return
        api_key = tenant_config.get("api_key")
        if not tenant_config.get("enabled") or not isinstance(api_key, str) or not api_key:
            await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.RETRY_SCHEDULED,
                error_code="TENANT_CREDENTIAL_UNAVAILABLE",
                next_attempt_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            return

        async with NilveraHttpClient(api_key=api_key) as client:
            answer_service = NilveraIncomingAnswerService(client)
            if action.provider_attempted_at is None:
                attempt_started = await InvoiceLifecycleRepository.mark_provider_attempt_started(
                    action.tenant_id,
                    action.id,
                    worker_id,
                    datetime.now(UTC),
                )
                if not attempt_started:
                    cls._log_lease_lost("mark_provider_attempt")
                    return

                try:
                    await answer_service.send_answer(
                        provider_uuid,
                        decision,
                        reject_note=action.reason,
                        correlation_id=action.id,
                    )
                except NilveraApiError as exc:
                    await cls._handle_send_error(action, worker_id, exc)
                    return
                except Exception:
                    await cls._schedule_verification(
                        action,
                        worker_id,
                        error_code="PROVIDER_WRITE_OUTCOME_UNKNOWN",
                    )
                    return

                accepted = await InvoiceLifecycleRepository.mark_provider_request_accepted(
                    action.tenant_id,
                    action.id,
                    worker_id,
                    datetime.now(UTC),
                )
                if not accepted:
                    cls._log_lease_lost("mark_provider_accepted")
                    return

            await cls._verify_provider_answer(
                action,
                worker_id,
                provider_uuid,
                decision,
                answer_service,
            )

    @staticmethod
    def _decision_for(action: InvoiceLifecycleAction) -> NilveraIncomingAnswerDecision:
        if action.action_type == InvoiceLifecycleActionType.ACCEPT_INCOMING:
            return NilveraIncomingAnswerDecision.APPROVED
        if action.action_type == InvoiceLifecycleActionType.REJECT_INCOMING:
            return NilveraIncomingAnswerDecision.REJECTED
        raise ValueError("Unsupported incoming invoice lifecycle action")

    @classmethod
    async def _verify_provider_answer(
        cls,
        action: InvoiceLifecycleAction,
        worker_id: str,
        provider_uuid: str,
        decision: NilveraIncomingAnswerDecision,
        answer_service: NilveraIncomingAnswerService,
    ) -> None:
        try:
            observed = await answer_service.fetch_answer_state(provider_uuid)
        except NilveraApiError as exc:
            if exc.http_status in {401, 403, 404}:
                await cls._finish(
                    action,
                    worker_id,
                    state=InvoiceLifecycleActionState.RECONCILIATION_REQUIRED,
                    error_code=exc.safe_code,
                    reconciliation_required=True,
                )
                return
            await cls._schedule_verification(
                action,
                worker_id,
                error_code=exc.safe_code,
            )
            return
        except Exception:
            await cls._schedule_verification(
                action,
                worker_id,
                error_code="ANSWER_STATUS_UNAVAILABLE",
            )
            return

        expected = {
            NilveraIncomingAnswerDecision.APPROVED: NilveraIncomingAnswerState.APPROVED,
            NilveraIncomingAnswerDecision.REJECTED: NilveraIncomingAnswerState.REJECTED,
        }[decision]
        if observed == expected:
            local_status = {
                NilveraIncomingAnswerDecision.APPROVED: IncomingInvoiceAnswerStatus.APPROVED,
                NilveraIncomingAnswerDecision.REJECTED: IncomingInvoiceAnswerStatus.REJECTED,
            }[decision]
            updated = await IncomingInvoiceRepository.update_answer_status(
                action.tenant_id,
                action.source_invoice_id,
                local_status,
            )
            if not updated:
                await cls._finish(
                    action,
                    worker_id,
                    state=InvoiceLifecycleActionState.RECONCILIATION_REQUIRED,
                    error_code="LOCAL_INVOICE_UPDATE_FAILED",
                    reconciliation_required=True,
                )
                return

            completed_at = datetime.now(UTC)
            persisted = await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.SUCCEEDED,
                error_code=None,
                completed_at=completed_at,
            )
            if persisted:
                try:
                    await event_bus.publish(
                        action.tenant_id,
                        f"invoice.lifecycle.{action.action_type.value.lower()}.completed",
                        {
                            "action_id": action.id,
                            "source_invoice_id": action.source_invoice_id,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Incoming invoice lifecycle completion event unavailable error_type=%s",
                        type(exc).__name__,
                    )
            return

        if observed in {NilveraIncomingAnswerState.UNKNOWN, NilveraIncomingAnswerState.WAITING}:
            await cls._schedule_verification(
                action,
                worker_id,
                error_code="ANSWER_STATUS_PENDING",
            )
            return

        await cls._finish(
            action,
            worker_id,
            state=InvoiceLifecycleActionState.RECONCILIATION_REQUIRED,
            error_code="ANSWER_STATUS_MISMATCH",
            reconciliation_required=True,
        )

    @classmethod
    async def _handle_send_error(
        cls,
        action: InvoiceLifecycleAction,
        worker_id: str,
        exc: NilveraApiError,
    ) -> None:
        if exc.http_status in {400, 401, 403, 404, 422}:
            await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.FAILED,
                error_code=exc.safe_code,
                release_answer_guard=True,
            )
            return

        await cls._schedule_verification(
            action,
            worker_id,
            error_code=exc.safe_code,
        )

    @classmethod
    async def _schedule_verification(
        cls,
        action: InvoiceLifecycleAction,
        worker_id: str,
        *,
        error_code: str,
    ) -> None:
        next_count = action.verification_attempt_count + 1
        if next_count > len(STATUS_POLL_DELAYS):
            await cls._finish(
                action,
                worker_id,
                state=InvoiceLifecycleActionState.RECONCILIATION_REQUIRED,
                error_code="ANSWER_VERIFICATION_EXHAUSTED",
                reconciliation_required=True,
                verification_attempt_count=next_count,
            )
            return

        await cls._finish(
            action,
            worker_id,
            state=InvoiceLifecycleActionState.PROVIDER_PENDING,
            error_code=error_code,
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=_get_next_poll_delay(action.verification_attempt_count)),
            verification_attempt_count=next_count,
        )

    @staticmethod
    async def _finish(
        action: InvoiceLifecycleAction,
        worker_id: str,
        *,
        state: InvoiceLifecycleActionState,
        error_code: str | None,
        next_attempt_at: datetime | None = None,
        completed_at: datetime | None = None,
        reconciliation_required: bool = False,
        verification_attempt_count: int | None = None,
        release_answer_guard: bool = False,
    ) -> bool:
        update_fields = {
            "state": state.value,
            "attempt_count": action.attempt_count + 1,
            "next_attempt_at": next_attempt_at,
            "completed_at": completed_at,
            "last_error_code": error_code,
            "reconciliation_required": reconciliation_required,
            "reconciliation_reason": error_code if reconciliation_required else None,
        }
        if verification_attempt_count is not None:
            update_fields["verification_attempt_count"] = verification_attempt_count
        unset_fields = {"answer_guard_key": ""} if release_answer_guard else None
        persisted = await InvoiceLifecycleRepository.update_action_result(
            action.tenant_id,
            action.id,
            worker_id,
            update_fields,
            unset_fields,
        )
        if not persisted:
            InvoiceLifecycleService._log_lease_lost("finish_action")
        elif state in {
            InvoiceLifecycleActionState.FAILED,
            InvoiceLifecycleActionState.RECONCILIATION_REQUIRED,
        }:
            try:
                await event_bus.publish(
                    action.tenant_id,
                    f"invoice.lifecycle.{action.action_type.value.lower()}.failed",
                    {
                        "action_id": action.id,
                        "error_code": error_code,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Incoming invoice lifecycle failure event unavailable error_type=%s",
                    type(exc).__name__,
                )
        return persisted

    @staticmethod
    def _log_lease_lost(operation: str) -> None:
        logger.warning(
            "Incoming invoice lifecycle lease lost operation=%s",
            operation,
        )
