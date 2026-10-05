"""KBS teslimatının yalnızca doğrulanmış kuyruk akışından tamamlanması."""

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

pytestmark = pytest.mark.asyncio

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")


async def test_legacy_single_send_endpoint_is_gone():
    from domains.pms.operations_router import send_kbs_notification

    with pytest.raises(HTTPException) as exc:
        await send_kbs_notification(
            {"booking_id": "booking-1"},
            current_user=SimpleNamespace(tenant_id="tenant-1", email="staff@example.com"),
            _perm=None,
        )

    assert exc.value.status_code == 410


async def test_legacy_batch_send_endpoint_is_gone():
    from domains.pms.operations_router import send_kbs_batch

    with pytest.raises(HTTPException) as exc:
        await send_kbs_batch(
            {"booking_ids": ["booking-1"]},
            current_user=SimpleNamespace(tenant_id="tenant-1", email="staff@example.com"),
            _perm=None,
        )

    assert exc.value.status_code == 410


async def test_production_complete_rejects_test_reference_before_database_write(monkeypatch):
    from routers.kbs import KBSQueueComplete, kbs_queue_complete

    monkeypatch.setenv("KBS_TEST_MODE", "0")
    request = Request({"type": "http", "method": "POST", "path": "/api/kbs/queue/job-1/complete", "headers": []})

    with pytest.raises(HTTPException) as exc:
        await kbs_queue_complete(
            "job-1",
            KBSQueueComplete(worker_id="worker-1", kbs_reference="TEST-FAKE"),
            request,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            _perm=None,
        )

    assert exc.value.status_code == 422
    assert "production" in exc.value.detail
