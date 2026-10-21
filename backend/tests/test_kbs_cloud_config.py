"""Real local Mongo configuration/queue semantics; authority calls are mocked."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import kbs_cloud as cloud
from core.crypto.service import CredentialEncryptionService
from core.kbs_jandarma import JandarmaError

pytestmark = pytest.mark.asyncio
CREDS = {"user_tc": "12345678901", "facility_code": "123", "password": "synthetic-not-a-real-service-password"}


@pytest.fixture
async def config_db(monkeypatch):
    from core.tenant_db import get_system_db

    monkeypatch.setenv("CM_CREDENTIAL_KEY", "synthetic-cloud-test-credential-key-32-chars")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "synthetic-cloud-test-master-key-32-chars")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "cloudtest")
    monkeypatch.delenv("CM_KEY_VERSION", raising=False)
    monkeypatch.delenv("CM_KEY_VERSION_PREVIOUS", raising=False)
    monkeypatch.delenv("CM_MASTER_KEY_PREVIOUS", raising=False)
    monkeypatch.setenv("CRYPTO_BYPASS_ALLOWED", "false")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("KBS_PUBLIC_EGRESS_IP", "8.8.8.8")
    monkeypatch.setenv("KBS_TEST_MODE", "0")
    monkeypatch.setenv("KBS_AUTO_DISPATCH", "1")
    svc = CredentialEncryptionService()
    monkeypatch.setattr(cloud, "get_crypto_service", lambda: svc)
    db = get_system_db()
    tenant = "test_cloud_kbs_" + uuid.uuid4().hex
    yield db, tenant
    for collection in (db.kbs_cloud_configs, db.kbs_reports, db.kbs_alerts, db.tenant_settings):
        await collection.delete_many({"tenant_id": tenant})


async def test_save_verify_activate_rotate_lifecycle(config_db, monkeypatch):
    db, tenant = config_db
    status = await cloud.save_config(db, tenant, CREDS, "admin")
    assert status["configured"] and not status["enabled"] and not status["verified"]
    record = await db.kbs_cloud_configs.find_one(cloud.config_query(tenant))
    assert CREDS["password"] not in str(record)
    assert cloud.reveal(tenant, record) == CREDS
    call = AsyncMock(return_value={"code": "Basarili"})
    monkeypatch.setattr(cloud, "call_jandarma", call)
    verified = await cloud.verify_config(db, tenant)
    assert verified["verified"] and not verified["enabled"]
    enabled = await cloud.save_config(db, tenant, {"enabled": True, "live_confirmed": True}, "admin")
    assert enabled["enabled"]
    rotated = await cloud.save_config(db, tenant, {"password": "synthetic-rotated-test-password"}, "admin")
    assert not rotated["verified"] and not rotated["enabled"]
    call.assert_awaited_once_with(CREDS)


async def test_kbs_config_does_not_replace_existing_tenant_settings(config_db):
    db, tenant = config_db
    await db.tenant_settings.insert_one({"tenant_id": tenant, "timezone": "Europe/Istanbul", "business_date": "2026-10-21"})
    await cloud.save_config(db, tenant, CREDS, "admin")
    settings = await db.tenant_settings.find_one({"tenant_id": tenant})
    assert settings["timezone"] == "Europe/Istanbul" and settings["business_date"] == "2026-10-21"
    assert "credentials_enc" not in settings
    assert await db.tenant_settings.count_documents({"tenant_id": tenant}) == 1


async def test_changed_revision_cannot_be_verified_by_old_request(config_db, monkeypatch):
    db, tenant = config_db
    await cloud.save_config(db, tenant, CREDS, "admin")

    async def race(_credentials):
        await db.kbs_cloud_configs.update_one(cloud.config_query(tenant), {"$set": {"revision": "new-revision"}})
        return {"code": "Basarili"}

    monkeypatch.setattr(cloud, "call_jandarma", race)
    with pytest.raises(JandarmaError, match="configuration_changed"):
        await cloud.verify_config(db, tenant)
    assert not cloud.public_status(await db.kbs_cloud_configs.find_one(cloud.config_query(tenant)))["verified"]


async def test_tenant_cannot_read_another_hotels_credentials(config_db):
    db, tenant = config_db
    await cloud.save_config(db, tenant, CREDS, "admin")
    assert await db.kbs_cloud_configs.find_one(cloud.config_query(tenant + "other")) is None
    record = await db.kbs_cloud_configs.find_one(cloud.config_query(tenant))
    with pytest.raises(JandarmaError):
        cloud.reveal(tenant + "other", record)


async def test_expired_send_is_held_not_resent_or_cleared(config_db, monkeypatch):
    from routers import kbs

    db, tenant = config_db
    await cloud.save_config(db, tenant, CREDS, "admin")
    monkeypatch.setattr(cloud, "call_jandarma", AsyncMock(return_value={"code": "Basarili"}))
    await cloud.verify_config(db, tenant)
    await cloud.save_config(db, tenant, {"enabled": True, "live_confirmed": True}, "admin")
    job = {
        "id": "job",
        "tenant_id": tenant,
        "_kind": "queue_job",
        "booking_id": "b1",
        "action": "checkin",
        "status": "in_progress",
        "worker_id": "system:kbs_dispatch",
        "_open_lock": "keep-this",
        "leased_until": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    await db.kbs_reports.insert_one(job)
    send = AsyncMock()
    monkeypatch.setattr(cloud, "call_jandarma", send)
    await cloud.dispatch_cloud_jobs(db)
    send.assert_awaited_once_with(CREDS)  # Read-only worker connection check, no guest payload.
    held = await db.kbs_reports.find_one({"tenant_id": tenant, "id": "job"})
    assert held["delivery_uncertain"] is True and held["status"] == "dead"
    assert held["_open_lock"] == "keep-this"
    monkeypatch.setattr(kbs, "db", db)
    with pytest.raises(HTTPException) as exc:
        await kbs.kbs_queue_requeue("job", current_user=SimpleNamespace(tenant_id=tenant), _perm=None)
    assert exc.value.status_code == 409


async def test_cloud_ownership_blocks_browser_even_while_paused(config_db, monkeypatch):
    from routers import kbs

    db, tenant = config_db
    await cloud.save_config(db, tenant, CREDS, "admin")
    monkeypatch.setattr(kbs, "db", db)
    with pytest.raises(HTTPException) as exc:
        await kbs.kbs_queue_claim("job", kbs.KBSQueueClaim(worker_id="browser"), current_user=SimpleNamespace(tenant_id=tenant), _perm=None)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("operation", ["complete", "fail"])
async def test_browser_cannot_forge_cloud_delivery_outcome(config_db, monkeypatch, operation):
    from starlette.requests import Request

    from routers import kbs

    db, tenant = config_db
    await cloud.save_config(db, tenant, CREDS, "admin")
    monkeypatch.setattr(kbs, "db", db)
    request = Request({"type": "http", "method": "POST", "path": f"/api/kbs/queue/job/{operation}", "headers": []})
    data = kbs.KBSQueueComplete(worker_id="system:kbs_dispatch", kbs_reference="FAKE") if operation == "complete" else kbs.KBSQueueFail(worker_id="system:kbs_dispatch", error="FAKE")
    with pytest.raises(HTTPException) as exc:
        await getattr(kbs, f"kbs_queue_{operation}")("job", data, request, current_user=SimpleNamespace(tenant_id=tenant), _perm=None)
    assert exc.value.status_code == 409
