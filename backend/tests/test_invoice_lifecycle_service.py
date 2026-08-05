from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.integrations.invoice_lifecycle_service import (
    InvoiceLifecycleService,
    _get_next_poll_delay,
)
from core.integrations.nilvera.errors import (
    NilveraBusinessRuleError,
    NilveraTimeoutError,
)
from core.integrations.nilvera.incoming_answer import NilveraIncomingAnswerState
from models.schemas.invoice_lifecycle import (
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)

PROVIDER_UUID = "11112222-3333-4444-5555-666677778888"


def _action(**updates) -> InvoiceLifecycleAction:
    values = {
        "id": "action-id",
        "tenant_id": "tenant-id",
        "direction": InvoiceLifecycleDirection.INCOMING,
        "source_invoice_id": "invoice-id",
        "source_provider_uuid": PROVIDER_UUID,
        "action_type": InvoiceLifecycleActionType.ACCEPT_INCOMING,
        "state": InvoiceLifecycleActionState.PROCESSING,
        "request_uuid": "request-id",
        "idempotency_key": "idempotency-key",
        "request_fingerprint": "fingerprint",
        "requested_by": "admin-id",
        "requested_at": datetime.now(UTC),
    }
    values.update(updates)
    return InvoiceLifecycleAction(**values)


def _provider_context(answer_state=NilveraIncomingAnswerState.APPROVED):
    client = MagicMock()
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    answer_service = MagicMock()
    answer_service.send_answer = AsyncMock(return_value=None)
    answer_service.fetch_answer_state = AsyncMock(return_value=answer_state)
    return client_context, answer_service


@pytest.mark.asyncio
async def test_invalid_provider_uuid_fails_without_provider_call():
    action = _action(source_provider_uuid="sensitive-invalid-provider-identity")
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
        patch(
            "core.integrations.invoice_lifecycle_service.event_bus.publish",
            new=AsyncMock(),
        ),
        patch("core.integrations.invoice_lifecycle_service.NilveraHttpClient") as client_class,
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    client_class.assert_not_called()
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.FAILED.value
    assert fields["last_error_code"] == "INVALID_PROVIDER_UUID"
    assert update.await_args.args[4] == {"answer_guard_key": ""}


@pytest.mark.asyncio
async def test_missing_credentials_schedules_retry_without_provider_attempt():
    action = _action()
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": False}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(),
        ) as mark_attempt,
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    mark_attempt.assert_not_awaited()
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.RETRY_SCHEDULED.value
    assert fields["last_error_code"] == "TENANT_CREDENTIAL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_invalid_tenant_configuration_schedules_retry_without_provider_attempt():
    action = _action()
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(),
        ) as mark_attempt,
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    mark_attempt.assert_not_awaited()
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.RETRY_SCHEDULED.value
    assert fields["last_error_code"] == "TENANT_CONFIGURATION_UNAVAILABLE"


@pytest.mark.asyncio
async def test_success_requires_provider_status_and_local_update():
    action = _action()
    client_context, answer_service = _provider_context()
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_request_accepted",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.IncomingInvoiceRepository.update_answer_status",
            new=AsyncMock(return_value=True),
        ) as update_invoice,
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update_action,
        patch(
            "core.integrations.invoice_lifecycle_service.event_bus.publish",
            new=AsyncMock(),
        ) as publish,
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    answer_service.send_answer.assert_awaited_once()
    answer_service.fetch_answer_state.assert_awaited_once_with(PROVIDER_UUID)
    update_invoice.assert_awaited_once()
    assert update_action.await_args.args[3]["state"] == InvoiceLifecycleActionState.SUCCEEDED.value
    publish.assert_awaited_once_with(
        "tenant-id",
        "invoice.lifecycle.accept_incoming.completed",
        {
            "action_id": "action-id",
            "source_invoice_id": "invoice-id",
        },
    )


@pytest.mark.asyncio
async def test_completion_event_failure_does_not_change_provider_success(caplog):
    action = _action(provider_attempted_at=datetime.now(UTC))
    client_context, answer_service = _provider_context()
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.IncomingInvoiceRepository.update_answer_status",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update_action,
        patch(
            "core.integrations.invoice_lifecycle_service.event_bus.publish",
            new=AsyncMock(side_effect=RuntimeError("sensitive event detail")),
        ),
        caplog.at_level(
            "WARNING",
            logger="core.integrations.invoice_lifecycle_service",
        ),
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    assert update_action.await_args.args[3]["state"] == InvoiceLifecycleActionState.SUCCEEDED.value
    assert "error_type=RuntimeError" in caplog.text
    assert "sensitive event detail" not in caplog.text


@pytest.mark.asyncio
async def test_existing_provider_attempt_verifies_without_repeating_write():
    action = _action(provider_attempted_at=datetime.now(UTC))
    client_context, answer_service = _provider_context()
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(),
        ) as mark_attempt,
        patch(
            "core.integrations.invoice_lifecycle_service.IncomingInvoiceRepository.update_answer_status",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.event_bus.publish",
            new=AsyncMock(),
        ),
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    mark_attempt.assert_not_awaited()
    answer_service.send_answer.assert_not_awaited()
    answer_service.fetch_answer_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_timeout_moves_to_verification_without_retrying_write():
    action = _action()
    client_context, answer_service = _provider_context()
    answer_service.send_answer.side_effect = NilveraTimeoutError("safe timeout")
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    answer_service.send_answer.assert_awaited_once()
    answer_service.fetch_answer_state.assert_not_awaited()
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.PROVIDER_PENDING.value
    assert fields["last_error_code"] == "NILVERA_TIMEOUT"


@pytest.mark.asyncio
async def test_business_rule_failure_releases_answer_guard():
    action = _action()
    client_context, answer_service = _provider_context()
    answer_service.send_answer.side_effect = NilveraBusinessRuleError(
        "safe business rule",
        http_status=422,
    )
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
        patch(
            "core.integrations.invoice_lifecycle_service.event_bus.publish",
            new=AsyncMock(),
        ),
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    assert update.await_args.args[3]["state"] == InvoiceLifecycleActionState.FAILED.value
    assert update.await_args.args[4] == {"answer_guard_key": ""}


@pytest.mark.asyncio
async def test_pending_status_exhaustion_requires_reconciliation():
    action = _action(
        provider_attempted_at=datetime.now(UTC),
        verification_attempt_count=5,
    )
    client_context, answer_service = _provider_context(NilveraIncomingAnswerState.WAITING)
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
        patch(
            "core.integrations.invoice_lifecycle_service.event_bus.publish",
            new=AsyncMock(),
        ),
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
    assert fields["last_error_code"] == "ANSWER_VERIFICATION_EXHAUSTED"


@pytest.mark.asyncio
async def test_opposite_terminal_status_requires_reconciliation():
    action = _action(provider_attempted_at=datetime.now(UTC))
    client_context, answer_service = _provider_context(NilveraIncomingAnswerState.REJECTED)
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
        patch(
            "core.integrations.invoice_lifecycle_service.event_bus.publish",
            new=AsyncMock(),
        ),
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
    assert fields["last_error_code"] == "ANSWER_STATUS_MISMATCH"


@pytest.mark.asyncio
async def test_lost_lease_before_write_prevents_provider_call():
    action = _action()
    client_context, answer_service = _provider_context()
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(return_value={"enabled": True, "api_key": "test-key"}),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
            return_value=client_context,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.NilveraIncomingAnswerService",
            return_value=answer_service,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(return_value=False),
        ),
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    answer_service.send_answer.assert_not_awaited()


def test_poll_delay_is_bounded():
    assert _get_next_poll_delay(-1) == 30
    assert _get_next_poll_delay(0) == 30
    assert _get_next_poll_delay(4) == 900
    assert _get_next_poll_delay(99) == 900
