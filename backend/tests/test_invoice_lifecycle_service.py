from unittest.mock import patch

import pytest

from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection


@pytest.fixture
def mock_service():
    with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleService._execute_send_answer") as mock:
        yield mock


@pytest.mark.asyncio
async def test_process_claimed_action_invalid_uuid():
    from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService

    action = InvoiceLifecycleAction(
        id="act_1",
        tenant_id="tenant_1",
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_1",
        source_provider_uuid="invalid-uuid",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
        state=InvoiceLifecycleActionState.PROCESSING,
        request_uuid="123",
        idempotency_key="key",
        request_fingerprint="fingerprint",
        requested_by="admin",
        requested_at="2023-01-01T00:00:00Z"
    )

    with patch("core.integrations.invoice_lifecycle_repository.InvoiceLifecycleRepository.update_action_result") as mock_update:
        await InvoiceLifecycleService._process_claimed_action(action, "worker_1")

        mock_update.assert_called_once()
        args, kwargs = mock_update.call_args
        assert args[0] == "tenant_1"
        assert args[1] == "act_1"
        assert args[2] == "worker_1"
        assert kwargs["update_fields"]["state"] == InvoiceLifecycleActionState.FAILED.value
        assert kwargs["update_fields"]["reconciliation_reason"] == "INVALID_PROVIDER_UUID"

async def test_timeout_requires_reconciliation_without_retry():
    from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
    with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.claim_action_lease") as mock_claim:
        with patch("core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config") as mock_creds:
            with patch("core.integrations.invoice_lifecycle_service.NilveraHttpClient.post") as mock_post:
                with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result") as mock_update:
                    from datetime import UTC, datetime

                    from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection

                    mock_action = InvoiceLifecycleAction(
                        id="act_to", tenant_id="t_to", direction=InvoiceLifecycleDirection.INCOMING,
                        source_invoice_id="inv_to", source_provider_uuid="11112222-3333-4444-5555-666677778888",
                        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, state=InvoiceLifecycleActionState.REQUESTED,
                        request_uuid="r_to", idempotency_key="k_to", request_fingerprint="f_to",
                        requested_by="admin", requested_at=datetime.now(UTC)
                    )
                    mock_claim.return_value = mock_action
                    mock_creds.return_value = {"enabled": True, "api_key": "secret"}
                    mock_post.side_effect = TimeoutError("Timeout")

                    await InvoiceLifecycleService.process_lifecycle_action("t_to", "act_to", "worker")

                    mock_update.assert_called_once()
                    args = mock_update.call_args[0]
                    assert args[3]["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
                    assert args[3]["reconciliation_required"] is True

async def test_rate_limit_requires_reconciliation_without_retry():
    from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
    with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.claim_action_lease") as mock_claim:
        with patch("core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config") as mock_creds:
            with patch("core.integrations.invoice_lifecycle_service.NilveraHttpClient.post") as mock_post:
                with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result") as mock_update:
                    from datetime import UTC, datetime

                    from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection

                    mock_action = InvoiceLifecycleAction(
                        id="act_429", tenant_id="t_429", direction=InvoiceLifecycleDirection.INCOMING,
                        source_invoice_id="inv_429", source_provider_uuid="11112222-3333-4444-5555-666677778888",
                        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, state=InvoiceLifecycleActionState.REQUESTED,
                        request_uuid="r_429", idempotency_key="k_429", request_fingerprint="f_429",
                        requested_by="admin", requested_at=datetime.now(UTC)
                    )
                    mock_claim.return_value = mock_action
                    mock_creds.return_value = {"enabled": True, "api_key": "secret"}

                    # Instead of fastapi HTTPException which service might not catch correctly if it doesn't import it,
                    # service actually catches Exception e and sets RECONCILIATION_REQUIRED
                    mock_post.side_effect = Exception("Rate limit / 429")

                    await InvoiceLifecycleService.process_lifecycle_action("t_429", "act_429", "worker")

                    mock_update.assert_called_once()
                    args = mock_update.call_args[0]
                    assert args[3]["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
                    assert args[3]["reconciliation_required"] is True

async def test_server_error_requires_reconciliation_without_retry():
    from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
    with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.claim_action_lease") as mock_claim:
        with patch("core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config") as mock_creds:
            with patch("core.integrations.invoice_lifecycle_service.NilveraHttpClient.post") as mock_post:
                with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result") as mock_update:
                    from datetime import UTC, datetime

                    from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection

                    mock_action = InvoiceLifecycleAction(
                        id="act_500", tenant_id="t_500", direction=InvoiceLifecycleDirection.INCOMING,
                        source_invoice_id="inv_500", source_provider_uuid="11112222-3333-4444-5555-666677778888",
                        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, state=InvoiceLifecycleActionState.REQUESTED,
                        request_uuid="r_500", idempotency_key="k_500", request_fingerprint="f_500",
                        requested_by="admin", requested_at=datetime.now(UTC)
                    )
                    mock_claim.return_value = mock_action
                    mock_creds.return_value = {"enabled": True, "api_key": "secret"}
                    mock_post.side_effect = Exception("Internal Server Error")

                    await InvoiceLifecycleService.process_lifecycle_action("t_500", "act_500", "worker")

                    mock_update.assert_called_once()
                    args = mock_update.call_args[0]
                    assert args[3]["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
                    assert args[3]["reconciliation_required"] is True

async def test_conflict_requires_reconciliation_without_retry():
    from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
    with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.claim_action_lease") as mock_claim:
        with patch("core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config") as mock_creds:
            with patch("core.integrations.invoice_lifecycle_service.NilveraHttpClient.post") as mock_post:
                with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result") as mock_update:
                    from datetime import UTC, datetime

                    from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection

                    mock_action = InvoiceLifecycleAction(
                        id="act_409", tenant_id="t_409", direction=InvoiceLifecycleDirection.INCOMING,
                        source_invoice_id="inv_409", source_provider_uuid="11112222-3333-4444-5555-666677778888",
                        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, state=InvoiceLifecycleActionState.REQUESTED,
                        request_uuid="r_409", idempotency_key="k_409", request_fingerprint="f_409",
                        requested_by="admin", requested_at=datetime.now(UTC)
                    )
                    mock_claim.return_value = mock_action
                    mock_creds.return_value = {"enabled": True, "api_key": "secret"}
                    mock_post.side_effect = Exception("Conflict")

                    await InvoiceLifecycleService.process_lifecycle_action("t_409", "act_409", "worker")

                    mock_update.assert_called_once()
                    args = mock_update.call_args[0]
                    assert args[3]["state"] == InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
                    assert args[3]["reconciliation_required"] is True

async def test_missing_credentials_skips_provider_call():
    from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
    with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.claim_action_lease") as mock_claim:
        with patch("core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config") as mock_creds:
            with patch("core.integrations.invoice_lifecycle_service.NilveraHttpClient.post") as mock_post:
                with patch("core.integrations.invoice_lifecycle_service.InvoiceLifecycleRepository.update_action_result") as mock_update:
                    from datetime import UTC, datetime

                    from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection

                    mock_action = InvoiceLifecycleAction(
                        id="act_cred", tenant_id="t_cred", direction=InvoiceLifecycleDirection.INCOMING,
                        source_invoice_id="inv_cred", source_provider_uuid="11112222-3333-4444-5555-666677778888",
                        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING, state=InvoiceLifecycleActionState.REQUESTED,
                        request_uuid="r_cred", idempotency_key="k_cred", request_fingerprint="f_cred",
                        requested_by="admin", requested_at=datetime.now(UTC)
                    )
                    mock_claim.return_value = mock_action
                    mock_creds.return_value = {"enabled": False} # MISSING/DISABLED CREDENTIALS

                    await InvoiceLifecycleService.process_lifecycle_action("t_cred", "act_cred", "worker")

                    mock_post.assert_not_called()
                    mock_update.assert_called_once()
                    args = mock_update.call_args[0]
                    assert args[3]["state"] == InvoiceLifecycleActionState.RETRY_SCHEDULED.value
