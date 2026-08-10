import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.incoming_invoice_integrations import require_admin, router
from models.schemas.incoming_invoice import (
    IncomingInvoice,
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceProfile,
    IncomingInvoiceProviderStatus,
)
from models.schemas.invoice_lifecycle import (
    ActionCreationResult,
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)
from models.schemas.invoice_sync import InvoiceProvider

REQUEST_UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"

app = FastAPI()
app.include_router(router)


def mock_require_admin():
    return type("MockUser", (), {"id": "admin-user", "tenant_id": "tenant-1"})()


app.dependency_overrides[require_admin] = mock_require_admin


@pytest.fixture(autouse=True)
def enable_incoming_answer_feature(monkeypatch):
    monkeypatch.setenv("NILVERA_INCOMING_ANSWER_ENABLED", "true")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_disabled_feature_rejects_before_repository_access(client, monkeypatch):
    monkeypatch.delenv("NILVERA_INCOMING_ANSWER_ENABLED", raising=False)
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as get_invoice:
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "NILVERA_INCOMING_ANSWER_DISABLED",
        "detail": "Incoming invoice answers are disabled.",
    }
    get_invoice.assert_not_called()


def _invoice(**updates) -> IncomingInvoice:
    now = datetime.now(UTC)
    values = {
        "id": "invoice-1",
        "tenant_id": "tenant-1",
        "provider": InvoiceProvider.NILVERA,
        "provider_uuid": "11112222-3333-4444-5555-666677778888",
        "invoice_number": "SANDBOX-INVOICE",
        "sender_vkn_tckn": "11111111111",
        "sender_title": "Sandbox Sender",
        "profile": IncomingInvoiceProfile.COMMERCIAL,
        "answer_status": IncomingInvoiceAnswerStatus.PENDING,
        "provider_status": IncomingInvoiceProviderStatus.SUCCEED,
        "issue_date": now,
        "received_at": now,
        "created_at": now,
        "updated_at": now,
    }
    values.update(updates)
    return IncomingInvoice(**values)


def _fingerprint(invoice_id: str, action_type: InvoiceLifecycleActionType, note=None) -> str:
    data = json.dumps(
        {
            "action_type": action_type.value,
            "note": note,
            "source_invoice_id": invoice_id,
            "tenant_id": "tenant-1",
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _action(invoice_id="invoice-1", **updates) -> InvoiceLifecycleAction:
    values = {
        "id": "action-1",
        "tenant_id": "tenant-1",
        "direction": InvoiceLifecycleDirection.INCOMING,
        "source_invoice_id": invoice_id,
        "source_provider_uuid": "11112222-3333-4444-5555-666677778888",
        "action_type": InvoiceLifecycleActionType.ACCEPT_INCOMING,
        "state": InvoiceLifecycleActionState.REQUESTED,
        "request_uuid": REQUEST_UUID,
        "idempotency_key": (f"tenant-1:{invoice_id}:ACCEPT_INCOMING:{REQUEST_UUID}"),
        "request_fingerprint": _fingerprint(
            invoice_id,
            InvoiceLifecycleActionType.ACCEPT_INCOMING,
        ),
        "requested_by": "admin-user",
        "requested_at": datetime.now(UTC),
    }
    values.update(updates)
    return InvoiceLifecycleAction(**values)


def test_basic_invoice_cannot_be_answered(client):
    with patch(
        "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
        return_value=_invoice(profile=IncomingInvoiceProfile.BASIC),
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 400
    assert "Cannot approve or reject a BASIC" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"answer": "INVALID", "request_uuid": REQUEST_UUID},
        {"answer": "REJECT", "request_uuid": REQUEST_UUID},
        {
            "answer": "APPROVE",
            "note": "must not be sent",
            "request_uuid": REQUEST_UUID,
        },
        {"answer": "APPROVE", "request_uuid": "not-a-uuid"},
    ],
)
def test_invalid_answer_requests_return_422_without_repository_access(client, payload):
    with patch("api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id") as get_invoice:
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json=payload,
        )

    assert response.status_code == 422
    get_invoice.assert_not_called()


def test_lowercase_answer_is_normalized(client):
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=_invoice(),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            return_value=None,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.has_active_action_for_invoice",
            return_value=False,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.create_action",
            return_value=ActionCreationResult.SUCCESS,
        ) as create_action,
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "approve", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 200
    assert create_action.call_args.args[0].action_type == InvoiceLifecycleActionType.ACCEPT_INCOMING


@pytest.mark.parametrize(
    "invoice",
    [
        _invoice(answer_status=IncomingInvoiceAnswerStatus.APPROVED),
        _invoice(provider_status=IncomingInvoiceProviderStatus.WAITING),
        _invoice(provider_status=IncomingInvoiceProviderStatus.ERROR),
        _invoice(provider_status=IncomingInvoiceProviderStatus.UNKNOWN),
    ],
)
def test_non_ready_invoice_cannot_create_answer_action(client, invoice):
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=invoice,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            return_value=None,
        ),
        patch("api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.create_action") as create_action,
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 409
    create_action.assert_not_called()


def test_idempotent_replay_returns_existing_action_after_invoice_state_changes(client):
    existing = _action(state=InvoiceLifecycleActionState.SUCCEEDED)
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=_invoice(answer_status=IncomingInvoiceAnswerStatus.APPROVED),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            return_value=existing,
        ),
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 200
    assert response.json()["state"] == InvoiceLifecycleActionState.SUCCEEDED.value


def test_idempotency_fingerprint_conflict_returns_409(client):
    existing = _action(request_fingerprint="different-fingerprint")
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=_invoice(),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            return_value=existing,
        ),
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 409
    assert "IDEMPOTENCY_CONFLICT" in response.json()["detail"]


def test_active_action_returns_409(client):
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=_invoice(),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            return_value=None,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.has_active_action_for_invoice",
            return_value=True,
        ),
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "INVOICE_ALREADY_ANSWERED"


@pytest.mark.parametrize(
    ("creation_result", "expected_detail"),
    [
        (ActionCreationResult.IDEMPOTENCY_CONFLICT, "IDEMPOTENCY_CONFLICT"),
        (ActionCreationResult.GUARD_CONFLICT, "INVOICE_ALREADY_ANSWERED"),
    ],
)
def test_atomic_creation_conflicts_return_409(client, creation_result, expected_detail):
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=_invoice(),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            return_value=None,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.has_active_action_for_invoice",
            return_value=False,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.create_action",
            return_value=creation_result,
        ),
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 409
    assert expected_detail in response.json()["detail"]


def test_concurrent_identical_creation_returns_idempotent_action(client):
    concurrent_action = _action()
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=_invoice(),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            side_effect=[None, concurrent_action],
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.has_active_action_for_invoice",
            return_value=False,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.create_action",
            return_value=ActionCreationResult.IDEMPOTENCY_CONFLICT,
        ),
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={"answer": "APPROVE", "request_uuid": REQUEST_UUID},
        )

    assert response.status_code == 200
    assert response.json()["action_id"] == concurrent_action.id


def test_created_action_uses_authenticated_tenant_and_user(client):
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            return_value=_invoice(),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            return_value=None,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.has_active_action_for_invoice",
            return_value=False,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.create_action",
            return_value=ActionCreationResult.SUCCESS,
        ) as create_action,
    ):
        response = client.post(
            "/api/integrations/incoming-invoices/invoice-1/answer",
            json={
                "answer": "REJECT",
                "note": "Sandbox business rejection",
                "request_uuid": REQUEST_UUID,
            },
        )

    assert response.status_code == 200
    action = create_action.call_args.args[0]
    assert action.tenant_id == "tenant-1"
    assert action.requested_by == "admin-user"
    assert action.action_type == InvoiceLifecycleActionType.REJECT_INCOMING
    assert action.reason == "Sandbox business rejection"


def test_response_dto_excludes_internal_and_provider_fields():
    from api.routes.incoming_invoice_integrations import _map_to_response

    response = _map_to_response(
        _action(
            lifecycle_lease_owner="worker-id",
            lifecycle_lease_expires_at=datetime.now(UTC),
        )
    ).model_dump()

    for field in {
        "idempotency_key",
        "request_fingerprint",
        "lifecycle_lease_owner",
        "lifecycle_lease_expires_at",
        "source_provider_uuid",
        "tenant_id",
    }:
        assert field not in response
