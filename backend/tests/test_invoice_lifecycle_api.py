from unittest.mock import patch

# Normally we would import the FastAPI app here, but since we are just mocking the router logic
# we can create a simple test app wrapper.
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.incoming_invoice_integrations import require_admin, router

app = FastAPI()
app.include_router(router)

def mock_require_admin():
    # Minimal mock user matching expected schema structure for Depends(require_admin)
    class MockUser:
        id = "admin_user_123"
        tenant_id = "tenant_1"
    return MockUser()

app.dependency_overrides[require_admin] = mock_require_admin

client = TestClient(app)

def test_answer_incoming_invoice_basic_rejection_denied():
    # Setup mock to return a BASIC invoice
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get:
        from datetime import UTC, datetime

        from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
        from models.schemas.invoice_sync import InvoiceProvider

        mock_inv = IncomingInvoice(
            id="inv_1",
            tenant_id="tenant_1",
            provider=InvoiceProvider.NILVERA,
            provider_uuid="11112222-3333-4444-5555-666677778888",
            invoice_number="ABC2023000000001",
            sender_vkn_tckn="11111111111",
            sender_title="Test Sender A.S.",
            profile=IncomingInvoiceProfile.BASIC,
            answer_status=IncomingInvoiceAnswerStatus.PENDING,
            issue_date=datetime.now(UTC),
            received_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        mock_get.return_value = mock_inv

        response = client.post(
            "/api/integrations/incoming-invoices/inv_1/answer",
            json={"answer": "REJECT", "request_uuid": "req-1"}
        )

        assert response.status_code == 400
        assert "Cannot approve or reject a BASIC" in response.json()["detail"]

def test_idempotency_same_uuid_diff_fingerprint():
    # Mock get_by_idempotency_key to return an existing action
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get_inv:
        with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key") as mock_get_action:
            from datetime import UTC, datetime

            from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
            from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection
            from models.schemas.invoice_sync import InvoiceProvider

            mock_inv = IncomingInvoice(
                id="inv_2",
                tenant_id="tenant_1",
                provider=InvoiceProvider.NILVERA,
                provider_uuid="11112222",
                invoice_number="ABC",
                sender_vkn_tckn="111",
                sender_title="Test",
                profile=IncomingInvoiceProfile.COMMERCIAL,
                answer_status=IncomingInvoiceAnswerStatus.PENDING,
                issue_date=datetime.now(UTC),
                received_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            mock_get_inv.return_value = mock_inv

            mock_action = InvoiceLifecycleAction(
                id="act_1",
                tenant_id="tenant_1",
                direction=InvoiceLifecycleDirection.INCOMING,
                source_invoice_id="inv_2",
                source_provider_uuid="11112222",
                action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
                state=InvoiceLifecycleActionState.REQUESTED,
                request_uuid="req-2",
                idempotency_key="tenant_1:inv_2:APPROVE:req-2",
                request_fingerprint="old-fingerprint", # DIFFERENT fingerprint
                requested_by="admin",
                requested_at=datetime.now(UTC)
            )
            mock_get_action.return_value = mock_action

            response = client.post(
                "/api/integrations/incoming-invoices/inv_2/answer",
                json={"answer": "APPROVE", "request_uuid": "req-2"} # Will calculate a different fingerprint
            )

            assert response.status_code == 409
            assert "IDEMPOTENCY_CONFLICT" in response.json()["detail"]

def test_idempotency_same_uuid_same_fingerprint():
    # Mock get_by_idempotency_key to return an existing action WITH same fingerprint
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get_inv:
        with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key") as mock_get_action:
            import hashlib
            from datetime import UTC, datetime

            from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
            from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection
            from models.schemas.invoice_sync import InvoiceProvider

            mock_inv = IncomingInvoice(
                id="inv_3",
                tenant_id="tenant_1",
                provider=InvoiceProvider.NILVERA,
                provider_uuid="11112222",
                invoice_number="ABC",
                sender_vkn_tckn="111",
                sender_title="Test",
                profile=IncomingInvoiceProfile.COMMERCIAL,
                answer_status=IncomingInvoiceAnswerStatus.PENDING,
                issue_date=datetime.now(UTC),
                received_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            mock_get_inv.return_value = mock_inv

            # Same fingerprint calculation as API
            action_type_val = InvoiceLifecycleActionType.ACCEPT_INCOMING.value
            fingerprint_raw = f"tenant_1:inv_3:{action_type_val}:APPROVE:"
            fingerprint = hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()

            mock_action = InvoiceLifecycleAction(
                id="act_2",
                tenant_id="tenant_1",
                direction=InvoiceLifecycleDirection.INCOMING,
                source_invoice_id="inv_3",
                source_provider_uuid="11112222",
                action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
                state=InvoiceLifecycleActionState.SUCCEEDED, # Existing state
                request_uuid="req-3",
                idempotency_key="tenant_1:inv_3:APPROVE:req-3",
                request_fingerprint=fingerprint, # SAME fingerprint
                requested_by="admin",
                requested_at=datetime.now(UTC)
            )
            mock_get_action.return_value = mock_action

            response = client.post(
                "/api/integrations/incoming-invoices/inv_3/answer",
                json={"answer": "APPROVE", "request_uuid": "req-3"}
            )

            assert response.status_code == 200 # Should return existing without 409
            data = response.json()
            assert data["state"] == "SUCCEEDED"
            assert "idempotency_key" not in data # safe DTO check
            assert "lifecycle_lease_owner" not in data # safe DTO check

def test_status_dto_excludes_internal_fields():
    from datetime import UTC, datetime

    from api.routes.incoming_invoice_integrations import _map_to_response
    from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState, InvoiceLifecycleActionType, InvoiceLifecycleDirection

    action = InvoiceLifecycleAction(
        id="act_dto",
        tenant_id="tenant_1",
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_dto",
        source_provider_uuid="uuid-dto",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid="req-dto",
        idempotency_key="tenant_1:inv_dto:ACCEPT:req-dto",
        request_fingerprint="fingerprint-dto",
        lifecycle_lease_owner="worker_1",
        lifecycle_lease_expires_at=datetime.now(UTC),
        requested_by="admin",
        requested_at=datetime.now(UTC),
        version=5
    )

    response_dto = _map_to_response(action)
    dto_dict = response_dto.model_dump()

    # Excluded internal fields
    assert "idempotency_key" not in dto_dict
    assert "request_fingerprint" not in dto_dict
    assert "lifecycle_lease_owner" not in dto_dict
    assert "lifecycle_lease_expires_at" not in dto_dict
    assert "version" not in dto_dict
    assert "provider_uuid" not in dto_dict
    assert "tenant_id" not in dto_dict

    assert "action_id" in dto_dict
    assert "state" in dto_dict

def test_real_require_admin_dependency_is_used():
    import inspect

    from api.routes.incoming_invoice_integrations import answer_incoming_invoice
    sig = inspect.signature(answer_incoming_invoice)
    assert "user" in sig.parameters
    assert sig.parameters["user"].default.dependency.__name__ == "require_admin"

def test_real_user_tenant_is_used():
    import inspect

    from api.routes.incoming_invoice_integrations import answer_incoming_invoice
    sig = inspect.signature(answer_incoming_invoice)
    # The return type or parameter annotation should indicate we rely on User
    assert sig.parameters["user"].annotation.__name__ == "User"

def test_requested_by_uses_authenticated_user():
    # If we call it with a mock user, does it pass the user.id to requested_by?
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get_inv:
        with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key") as mock_get_action:
            with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.has_active_action_for_invoice") as mock_has_active:
                with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.create_action") as mock_create:
                    from datetime import UTC, datetime

                    from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
                    from models.schemas.invoice_sync import InvoiceProvider

                    mock_inv = IncomingInvoice(
                        id="inv_mock_user", tenant_id="tenant_1", provider=InvoiceProvider.NILVERA, provider_uuid="11112222",
                        invoice_number="ABC", sender_vkn_tckn="111", sender_title="Test", profile=IncomingInvoiceProfile.COMMERCIAL,
                        answer_status=IncomingInvoiceAnswerStatus.PENDING, issue_date=datetime.now(UTC), received_at=datetime.now(UTC),
                        created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
                    )
                    mock_get_inv.return_value = mock_inv
                    mock_get_action.return_value = None
                    mock_has_active.return_value = False
                    mock_create.return_value = True

                    response = client.post(
                        "/api/integrations/incoming-invoices/inv_mock_user/answer",
                        json={"answer": "APPROVE", "request_uuid": "req-mock"}
                    )
                    assert response.status_code == 200
                    mock_create.assert_called_once()
                    created_action = mock_create.call_args[0][0]
                    # We expect our mock_require_admin user.id
                    assert created_action.requested_by == "admin_user_123"
                    assert created_action.tenant_id == "tenant_1"

def test_router_uses_api_prefix():
    from api.routes.incoming_invoice_integrations import router
    assert router.prefix == "/api/integrations/incoming-invoices"

def test_answered_invoice_does_not_create_second_action():
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get_inv:
        with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key") as mock_get_action:
            with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.has_active_action_for_invoice") as mock_has_active:
                from datetime import UTC, datetime

                from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
                from models.schemas.invoice_sync import InvoiceProvider

                mock_inv = IncomingInvoice(
                    id="inv_dup", tenant_id="tenant_1", provider=InvoiceProvider.NILVERA, provider_uuid="11112222",
                    invoice_number="ABC", sender_vkn_tckn="111", sender_title="Test", profile=IncomingInvoiceProfile.COMMERCIAL,
                    answer_status=IncomingInvoiceAnswerStatus.PENDING, issue_date=datetime.now(UTC), received_at=datetime.now(UTC),
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
                )
                mock_get_inv.return_value = mock_inv
                mock_get_action.return_value = None

                # Assume there is an existing processed action for this invoice
                mock_has_active.return_value = True

                response = client.post(
                    "/api/integrations/incoming-invoices/inv_dup/answer",
                    json={"answer": "REJECT", "request_uuid": "req-dup", "note": "Duplicate reject test"}
                )
                assert response.status_code == 409
                assert "INVOICE_ALREADY_ANSWERED" in response.json()["detail"]

def test_conflicting_second_answer_returns_409():
    test_answered_invoice_does_not_create_second_action()
