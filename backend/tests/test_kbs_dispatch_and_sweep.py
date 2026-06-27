"""Task #570 — PMS-içi otomatik KBS gönderimi + gece güvenlik taraması.

Direct-call testleri:
  * ``core.kbs_sender``                      — test-mode / fail-closed kapı.
  * ``core.kbs_dispatch.dispatch_pending_kbs_jobs`` — claim → send → complete/fail.
  * ``celery_tasks._kbs_nightly_sweep_dispatch_async`` — yerel-saat 00:00 eşleşmesi
    + atomik per-local-day claim.

Mongo session loop'una conftest tarafından bağlanır; erişilemezse testler atlanır.
Gönderim ağa ÇIKMAZ: testler KBS_TEST_MODE=1 ile çalışır (gerçek HTTP yok, TEST-
referans). Saat ``_now_utc`` ile sabitlenir.
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.asyncio

PREFIX = "task570_kbs_"
QUEUE_KIND = "queue_job"


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


async def _cleanup(tenant_id: str) -> None:
    from core.database import db
    await db.kbs_reports.delete_many({"tenant_id": tenant_id})
    await db.kbs_alerts.delete_many({"tenant_id": tenant_id})
    await db.kbs_alerts.delete_many({"tenant_id": "_system", "kind": "send_unconfigured"})
    await db.bookings.delete_many({"tenant_id": tenant_id})
    await db.guests.delete_many({"tenant_id": tenant_id})
    await db.users.delete_many({"tenant_id": tenant_id})
    await db.tenant_settings.delete_many({"tenant_id": tenant_id})
    await db.kbs_sweep_state.delete_many({"tenant_id": tenant_id})


@pytest.fixture
async def tenant():
    tid = f"{PREFIX}{_ts()}_{uuid.uuid4().hex[:8]}"
    yield tid
    try:
        await _cleanup(tid)
    except Exception:
        pass


def _valid_payload(**over) -> dict:
    p = {
        "guest_name": "Ada Lovelace",
        "birth_date": "1990-01-01",
        "check_in": datetime.now(UTC).strftime("%Y-%m-%dT12:00:00"),
        "check_out": (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00"),
        "nationality": "TC",
        "id_number": "12345678901",
        "room_number": "101",
    }
    p.update(over)
    return p


async def _seed_job(tenant_id, *, status="pending", payload=None, action="checkin", attempts=0):
    from core.database import db
    job = {
        "_kind": QUEUE_KIND,
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "booking_id": str(uuid.uuid4()),
        "action": action,
        "payload": payload if payload is not None else _valid_payload(),
        "status": status,
        "attempts": attempts,
        "max_attempts": 5,
        "next_retry_at": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.bookings.insert_one({
        "tenant_id": tenant_id, "id": job["booking_id"], "status": "checked_in",
    })
    await db.kbs_reports.insert_one(dict(job))
    return job


# ── sender: fail-closed kapı ───────────────────────────────────────────


async def test_sender_test_mode_returns_test_ref(monkeypatch):
    from core import kbs_sender
    monkeypatch.setenv("KBS_TEST_MODE", "1")
    ref = await kbs_sender.send_kbs_notification(_valid_payload(), "checkin")
    assert ref.startswith("TEST-")


async def test_sender_fail_closed_without_credentials(monkeypatch):
    from core import kbs_sender
    monkeypatch.setenv("KBS_TEST_MODE", "0")
    monkeypatch.delenv("KBS_API_URL", raising=False)
    monkeypatch.delenv("KBS_API_TOKEN", raising=False)
    assert kbs_sender.kbs_dispatch_active() is False
    with pytest.raises(kbs_sender.KBSCredentialsMissing):
        await kbs_sender.send_kbs_notification(_valid_payload(), "checkin")


async def test_dispatch_active_kill_switch(monkeypatch):
    from core import kbs_sender
    monkeypatch.setenv("KBS_TEST_MODE", "1")
    monkeypatch.setenv("KBS_AUTO_DISPATCH", "0")
    assert kbs_sender.kbs_dispatch_active() is False


# ── dispatch: claim → send → complete/fail ─────────────────────────────


async def test_dispatch_inactive_alerts_when_pending(tenant, monkeypatch):
    """Kimlik bilgisi yok + bekleyen iş var → no-op + send_unconfigured alarmı."""
    from core.database import db
    from core.kbs_dispatch import dispatch_pending_kbs_jobs
    monkeypatch.setenv("KBS_TEST_MODE", "0")
    monkeypatch.delenv("KBS_API_URL", raising=False)
    monkeypatch.delenv("KBS_API_TOKEN", raising=False)
    await _seed_job(tenant)

    result = await dispatch_pending_kbs_jobs(db)

    assert result["skipped"] == "inactive"
    assert result["pending"] >= 1
    alert = await db.kbs_alerts.find_one({"kind": "send_unconfigured"})
    assert alert is not None


async def test_dispatch_completes_in_test_mode(tenant, monkeypatch):
    """Test-mode aktif → iş done, TEST- referans, booking bayrağı + legacy report."""
    from core.database import db
    from core.kbs_dispatch import dispatch_pending_kbs_jobs
    monkeypatch.setenv("KBS_TEST_MODE", "1")
    job = await _seed_job(tenant)

    result = await dispatch_pending_kbs_jobs(db)

    assert result["sent"] == 1
    done = await db.kbs_reports.find_one({"_kind": QUEUE_KIND, "id": job["id"]})
    assert done["status"] == "done"
    assert done["kbs_reference"].startswith("TEST-")
    assert done.get("kbs_test") is True
    booking = await db.bookings.find_one({"tenant_id": tenant, "id": job["booking_id"]})
    assert booking["kbs_reported"] is True
    report = await db.kbs_reports.find_one({"_kind": "report", "queue_job_id": job["id"]})
    assert report is not None and report["status"] == "submitted"


async def test_dispatch_missing_data_dead_and_alert(tenant, monkeypatch):
    """Payload eksik → iş dead + missing_data alarmı, gönderim DENENMEZ."""
    from core.database import db
    from core.kbs_dispatch import dispatch_pending_kbs_jobs
    monkeypatch.setenv("KBS_TEST_MODE", "1")
    job = await _seed_job(tenant, payload=_valid_payload(birth_date="", id_number=""))

    result = await dispatch_pending_kbs_jobs(db)

    assert result["missing_data"] == 1
    dead = await db.kbs_reports.find_one({"_kind": QUEUE_KIND, "id": job["id"]})
    assert dead["status"] == "dead"
    alert = await db.kbs_alerts.find_one({"tenant_id": tenant, "kind": "missing_data"})
    assert alert is not None
    assert "birth_date" in alert["missing_fields"]


async def test_dispatch_idempotent_no_double_send(tenant, monkeypatch):
    """Done iş ikinci koşuda yeniden claim edilmez."""
    from core.database import db
    from core.kbs_dispatch import dispatch_pending_kbs_jobs
    monkeypatch.setenv("KBS_TEST_MODE", "1")
    await _seed_job(tenant)

    first = await dispatch_pending_kbs_jobs(db)
    second = await dispatch_pending_kbs_jobs(db)

    assert first["sent"] == 1
    assert second.get("sent", 0) == 0
    assert await db.kbs_reports.count_documents(
        {"_kind": QUEUE_KIND, "tenant_id": tenant, "status": "done"}
    ) == 1


# ── nightly sweep dispatcher: yerel-saat 00:00 ─────────────────────────


async def _seed_active_tenant(tenant_id, *, tz, check_in_day):
    from core.database import db
    await db.users.insert_one({
        "tenant_id": tenant_id, "id": str(uuid.uuid4()),
        "email": f"u_{uuid.uuid4().hex[:6]}@example.com", "is_active": True,
    })
    await db.tenant_settings.update_one(
        {"tenant_id": tenant_id}, {"$set": {"timezone": tz}}, upsert=True
    )
    booking_id = str(uuid.uuid4())
    guest_id = str(uuid.uuid4())
    await db.guests.insert_one({
        "tenant_id": tenant_id, "id": guest_id,
        "nationality": "TC", "id_number": "12345678901",
        "birth_date": "1990-01-01",
    })
    await db.bookings.insert_one({
        "tenant_id": tenant_id, "id": booking_id, "guest_id": guest_id,
        "status": "checked_in", "guest_name": "Grace Hopper", "room_number": "201",
        "check_in": f"{check_in_day}T12:00:00",
        "check_out": f"{check_in_day}T23:00:00",
        "guest_nationality": "TC",
    })
    return booking_id


async def test_nightly_sweep_enqueues_at_local_midnight(tenant, monkeypatch):
    from core.database import db
    from celery_tasks import _kbs_nightly_sweep_dispatch_async
    monkeypatch.setenv("KBS_NIGHTLY_SWEEP", "1")
    monkeypatch.setenv("KBS_AUTO_ENQUEUE", "1")

    tz = "Asia/Tokyo"
    # Pin wall clock so the tenant's LOCAL time is exactly 00:00.
    local_midnight = datetime.now(ZoneInfo(tz)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    pinned = local_midnight.astimezone(UTC)
    yesterday = (local_midnight - timedelta(days=1)).strftime("%Y-%m-%d")
    booking_id = await _seed_active_tenant(tenant, tz=tz, check_in_day=yesterday)

    with patch("celery_tasks._now_utc", return_value=pinned):
        result = await _kbs_nightly_sweep_dispatch_async()

    assert result["success"] is True
    assert tenant in result["swept"]
    job = await db.kbs_reports.find_one({
        "_kind": QUEUE_KIND, "tenant_id": tenant, "booking_id": booking_id,
        "action": "checkin",
    })
    assert job is not None and job["status"] == "pending"


async def test_nightly_sweep_skips_when_not_midnight(tenant, monkeypatch):
    from core.database import db
    from celery_tasks import _kbs_nightly_sweep_dispatch_async
    monkeypatch.setenv("KBS_NIGHTLY_SWEEP", "1")

    tz = "Asia/Tokyo"
    local = datetime.now(ZoneInfo(tz)).replace(
        hour=13, minute=37, second=0, microsecond=0
    )
    pinned = local.astimezone(UTC)
    yesterday = (local - timedelta(days=1)).strftime("%Y-%m-%d")
    await _seed_active_tenant(tenant, tz=tz, check_in_day=yesterday)

    with patch("celery_tasks._now_utc", return_value=pinned):
        result = await _kbs_nightly_sweep_dispatch_async()

    assert tenant not in result.get("swept", [])
    assert await db.kbs_reports.count_documents(
        {"_kind": QUEUE_KIND, "tenant_id": tenant}
    ) == 0


async def test_nightly_sweep_dedups_within_local_day(tenant, monkeypatch):
    from celery_tasks import _kbs_nightly_sweep_dispatch_async
    monkeypatch.setenv("KBS_NIGHTLY_SWEEP", "1")

    tz = "Asia/Tokyo"
    local_midnight = datetime.now(ZoneInfo(tz)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    pinned = local_midnight.astimezone(UTC)
    yesterday = (local_midnight - timedelta(days=1)).strftime("%Y-%m-%d")
    await _seed_active_tenant(tenant, tz=tz, check_in_day=yesterday)

    with patch("celery_tasks._now_utc", return_value=pinned):
        first = await _kbs_nightly_sweep_dispatch_async()
        second = await _kbs_nightly_sweep_dispatch_async()

    assert tenant in first["swept"]
    assert tenant not in second["swept"]


# ── beat schedule kaydı ────────────────────────────────────────────────


async def test_beat_schedule_registered():
    from celery_app import celery_app
    sched = celery_app.conf.beat_schedule
    assert "kbs-dispatch" in sched
    assert sched["kbs-dispatch"]["task"] == "celery_tasks.kbs_dispatch_task"
    assert "kbs-nightly-sweep-dispatch" in sched
    assert (
        sched["kbs-nightly-sweep-dispatch"]["task"]
        == "celery_tasks.kbs_nightly_sweep_dispatch_task"
    )
