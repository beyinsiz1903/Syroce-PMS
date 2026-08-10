from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
from core.integrations.nilvera.errors import (
    NilveraApiError,
    NilveraBusinessRuleError,
    NilveraMalformedResponseError,
    NilveraTimeoutError,
)
from models.schemas.invoice_lifecycle import (
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)

SOURCE_PROVIDER_UUID = "11112222-3333-4444-5555-666677778888"
GENERATED_PROVIDER_UUID = "99990000-aaaa-bbbb-cccc-ddddeeeeffff"


@pytest.fixture(autouse=True)
def enable_create_return(monkeypatch):
    monkeypatch.setenv("NILVERA_CREATE_RETURN_ENABLED", "true")


def _action(**updates) -> InvoiceLifecycleAction:
    values = {
        "id": "return-action-id",
        "tenant_id": "tenant-id",
        "direction": InvoiceLifecycleDirection.INCOMING,
        "source_invoice_id": "invoice-id",
        "source_provider_uuid": SOURCE_PROVIDER_UUID,
        "action_type": InvoiceLifecycleActionType.CREATE_INCOMING_RETURN,
        "state": InvoiceLifecycleActionState.PROCESSING,
        "request_uuid": "request-id",
        "idempotency_key": "idempotency-key",
        "request_fingerprint": "fingerprint",
        "return_type": "FULL",
        "answer_guard_key": "return:invoice-id",
        "requested_by": "admin-id",
        "requested_at": datetime.now(UTC),
    }
    values.update(updates)
    return InvoiceLifecycleAction(**values)


def _provider_context():
    client = MagicMock()
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    adapter = MagicMock()
    adapter.create_return = AsyncMock(return_value=SimpleNamespace(provider_uuid=GENERATED_PROVIDER_UUID))
    adapter.verify_return_draft = AsyncMock(return_value=None)
    return client_context, adapter


@pytest.mark.asyncio
async def test_create_return_success_posts_once_then_verifies_and_confirms():
    action = _action()
    client_context, adapter = _provider_context()
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
            "core.integrations.invoice_lifecycle_service.NilveraReturnAdapter",
            return_value=adapter,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.prepare_return_action_for_provider",
            new=AsyncMock(return_value=True),
        ) as prepare,
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_return_created",
            new=AsyncMock(return_value=True),
        ) as mark_created,
        patch(
            "core.integrations.invoice_lifecycle_service.handle_return_action_success",
            new=AsyncMock(),
        ) as confirm_allocations,
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

    prepare.assert_awaited_once_with("tenant-id", "return-action-id")
    adapter.create_return.assert_awaited_once_with(
        SOURCE_PROVIDER_UUID,
        correlation_id="return-action-id",
    )
    mark_created.assert_awaited_once()
    adapter.verify_return_draft.assert_awaited_once_with(
        GENERATED_PROVIDER_UUID,
        correlation_id="return-action-id",
    )
    confirm_allocations.assert_awaited_once_with("tenant-id", "return-action-id")
    assert update.await_args.args[3]["state"] == InvoiceLifecycleActionState.SUCCEEDED.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (NilveraTimeoutError("safe timeout"), "NILVERA_TIMEOUT"),
        (
            NilveraApiError(
                "safe provider failure",
                http_status=500,
                safe_code="NILVERA_PROVIDER_SERVER_ERROR",
            ),
            "NILVERA_PROVIDER_SERVER_ERROR",
        ),
    ],
)
async def test_create_return_ambiguous_failure_is_reconciliation_and_never_retried(
    provider_error,
    expected_code,
):
    action = _action()
    client_context, adapter = _provider_context()
    adapter.create_return.side_effect = provider_error
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
            "core.integrations.invoice_lifecycle_service.NilveraReturnAdapter",
            return_value=adapter,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.prepare_return_action_for_provider",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.handle_return_action_unknown_failure",
            new=AsyncMock(),
        ) as mark_allocations,
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

    assert adapter.create_return.await_count == 1
    adapter.verify_return_draft.assert_not_awaited()
    mark_allocations.assert_awaited_once_with("tenant-id", "return-action-id")
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
    assert fields["last_error_code"] == expected_code


@pytest.mark.asyncio
async def test_create_return_attempt_without_result_identifier_never_posts_again():
    action = _action(provider_attempted_at=datetime.now(UTC))
    client_context, adapter = _provider_context()
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
            "core.integrations.invoice_lifecycle_service.NilveraReturnAdapter",
            return_value=adapter,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.handle_return_action_unknown_failure",
            new=AsyncMock(),
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

    adapter.create_return.assert_not_awaited()
    adapter.verify_return_draft.assert_not_awaited()
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
    assert fields["last_error_code"] == "CREATE_RETURN_RESULT_IDENTIFIER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_existing_create_return_result_retries_get_only_verification():
    action = _action(
        provider_attempted_at=datetime.now(UTC),
        generated_invoice_uuid=GENERATED_PROVIDER_UUID,
    )
    client_context, adapter = _provider_context()
    adapter.verify_return_draft.side_effect = NilveraMalformedResponseError("safe malformed response")
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
            "core.integrations.invoice_lifecycle_service.NilveraReturnAdapter",
            return_value=adapter,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    adapter.create_return.assert_not_awaited()
    adapter.verify_return_draft.assert_awaited_once()
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.PROVIDER_PENDING.value
    assert fields["verification_attempt_count"] == 1


@pytest.mark.asyncio
async def test_create_return_validation_rejection_releases_allocations_and_guard():
    action = _action()
    client_context, adapter = _provider_context()
    adapter.create_return.side_effect = NilveraBusinessRuleError(
        "safe rejection",
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
            "core.integrations.invoice_lifecycle_service.NilveraReturnAdapter",
            return_value=adapter,
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.prepare_return_action_for_provider",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.mark_provider_attempt_started",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "core.integrations.invoice_lifecycle_service.handle_return_action_validation_failure",
            new=AsyncMock(),
        ) as release_allocations,
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

    assert adapter.create_return.await_count == 1
    release_allocations.assert_awaited_once_with("tenant-id", "return-action-id")
    assert update.await_args.args[3]["state"] == InvoiceLifecycleActionState.FAILED.value
    assert update.await_args.args[4] == {"answer_guard_key": ""}


@pytest.mark.asyncio
async def test_disabled_create_return_stops_before_credentials_or_provider(monkeypatch):
    monkeypatch.delenv("NILVERA_CREATE_RETURN_ENABLED", raising=False)
    action = _action()
    with (
        patch(
            "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
            new=AsyncMock(),
        ) as get_config,
        patch(
            "core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result",
            new=AsyncMock(return_value=True),
        ) as update,
        patch("core.integrations.invoice_lifecycle_service.NilveraHttpClient") as client_class,
    ):
        await InvoiceLifecycleService._process_claimed_action(action, "worker-id")

    get_config.assert_not_awaited()
    client_class.assert_not_called()
    fields = update.await_args.args[3]
    assert fields["state"] == InvoiceLifecycleActionState.RETRY_SCHEDULED.value
    assert fields["last_error_code"] == "CREATE_RETURN_FEATURE_DISABLED"
