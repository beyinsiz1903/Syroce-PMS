from unittest.mock import patch
from fastapi.testclient import TestClient

# Normally we would import the FastAPI app here, but since we are just mocking the router logic 
# we can create a simple test app wrapper.
from fastapi import FastAPI
from api.routes.incoming_invoice_integrations import router

app = FastAPI()
app.include_router(router)

client = TestClient(app)

def test_answer_incoming_invoice_basic_rejection_denied():
    # Setup mock to return a BASIC invoice
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get:
        from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceProfile, IncomingInvoiceAnswerStatus
        from models.schemas.invoice_sync import InvoiceProvider
        from datetime import datetime, UTC
        
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
            "/integrations/incoming-invoices/inv_1/answer",
            json={"answer": "REJECT", "request_uuid": "req-1"}
        )
        
        assert response.status_code == 400
        assert "Cannot approve or reject a BASIC" in response.json()["detail"]

def test_idempotency_same_uuid_diff_fingerprint():
    # Mock get_by_idempotency_key to return an existing action
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get_inv:
        with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key") as mock_get_action:
            from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceProfile, IncomingInvoiceAnswerStatus
            from models.schemas.invoice_sync import InvoiceProvider
            from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleDirection, InvoiceLifecycleActionType, InvoiceLifecycleActionState
            from datetime import datetime, UTC
            
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
                "/integrations/incoming-invoices/inv_2/answer",
                json={"answer": "APPROVE", "request_uuid": "req-2"} # Will calculate a different fingerprint
            )
            
            assert response.status_code == 409
            assert "IDEMPOTENCY_CONFLICT" in response.json()["detail"]

def test_idempotency_same_uuid_same_fingerprint():
    # Mock get_by_idempotency_key to return an existing action WITH same fingerprint
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as mock_get_inv:
        with patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key") as mock_get_action:
            from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceProfile, IncomingInvoiceAnswerStatus
            from models.schemas.invoice_sync import InvoiceProvider
            from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleDirection, InvoiceLifecycleActionType, InvoiceLifecycleActionState
            from datetime import datetime, UTC
            import hashlib
            import json
            
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
                "/integrations/incoming-invoices/inv_3/answer",
                json={"answer": "APPROVE", "request_uuid": "req-3"} 
            )
            
            assert response.status_code == 200 # Should return existing without 409
            data = response.json()
            assert data["state"] == "SUCCEEDED"
            assert "idempotency_key" not in data # safe DTO check
            assert "lifecycle_lease_owner" not in data # safe DTO check

def test_status_dto_excludes_internal_fields():
    from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleDirection, InvoiceLifecycleActionType, InvoiceLifecycleActionState
    from api.routes.incoming_invoice_integrations import _map_to_response
    from datetime import datetime, UTC
    
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
    
    # Included fields
    assert "action_id" in dto_dict
    assert "state" in dto_dict
