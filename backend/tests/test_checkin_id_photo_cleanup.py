"""
Tests: Task #72 — Süresi dolan kimlik fotoğraflarının periyodik temizliği.

`prune_expired_id_photos` saf bir fonksiyon olduğu için motor/Mongo
event-loop sorunu yaşamaz; CI'da da çalışır. Worker scheduler kısmı
testin dışında — bootstrap wiring'i manuel doğrulanır.
"""
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domains.guest import checkin_id_photo_cleanup as cic
from domains.guest.checkin_id_photo_cleanup import (
    _is_enabled,
    _worker_loop,
    prune_expired_id_photos,
    start_checkin_id_photo_cleanup_worker,
    stop_checkin_id_photo_cleanup_worker,
)


class _AsyncCursor:
    """Minimal motor cursor stand-in — supports only ``async for``."""

    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


def _mock_db(*, find_results=None, deleted_count: int = 1):
    """Build a mock db with online_checkin_id_photos + audit_logs.

    ``find_results`` is a list of lists: one list per find() invocation. The
    first call (retention sweep) consumes index 0, the second (orphan sweep)
    index 1.
    """
    db = MagicMock()
    db.online_checkin_id_photos = MagicMock()
    db.audit_logs = MagicMock()
    db.audit_logs.insert_one = AsyncMock()

    calls = list(find_results or [[], []])

    def _find(query, projection=None):
        docs = calls.pop(0) if calls else []
        return _AsyncCursor(docs)

    db.online_checkin_id_photos.find = MagicMock(side_effect=_find)
    db.online_checkin_id_photos.delete_one = AsyncMock(
        return_value=MagicMock(deleted_count=deleted_count),
    )
    return db


@pytest.fixture(autouse=True)
def _stub_file_delete(monkeypatch):
    """delete_id_photo gerçek dosya sistemine dokunmasın."""
    import domains.guest.checkin_id_photo_storage as storage
    monkeypatch.setattr(storage, "delete_id_photo", lambda *, tenant_id, photo_id: True)


# ────────────────────────────────────────────────────────────────────
# prune_expired_id_photos — saklama süresi taraması
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retention_uses_correct_cutoff_iso():
    """retention_days kullanıldığında uploaded_at < (now - N gün) sorgusu kurulur."""
    now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    expired_doc = {
        "photo_id": "abc123",
        "tenant_id": "tenant-1",
        "booking_id": "bk1",
        "uploaded_at": (now - timedelta(days=120)).isoformat(),
        "claimed": True,
    }
    db = _mock_db(find_results=[[expired_doc], []])

    counts = await prune_expired_id_photos(
        db=db, retention_days=90, orphan_ttl_hours=24, now=now,
    )
    assert counts == {"expired": 1, "orphans": 0}

    # İlk find çağrısı retention taraması — uploaded_at < cutoff_iso içermeli.
    first_call_query = db.online_checkin_id_photos.find.call_args_list[0][0][0]
    expected_iso = (now - timedelta(days=90)).isoformat()
    assert any(
        c.get("uploaded_at") == {"$lt": expected_iso}
        for c in first_call_query["$or"]
    ), first_call_query

    # Metadata silindi ve audit kaydedildi.
    db.online_checkin_id_photos.delete_one.assert_awaited_once_with(
        {"photo_id": "abc123", "tenant_id": "tenant-1"},
    )
    db.audit_logs.insert_one.assert_awaited_once()
    audit_entry = db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["entity_type"] == "online_checkin_id_photo"
    assert audit_entry["entity_id"] == "abc123"
    assert audit_entry["action"] == "auto_delete"
    assert audit_entry["actor_id"] is None
    assert audit_entry["metadata"]["reason"] == "retention_expired"
    assert audit_entry["metadata"]["file_deleted"] is True
    assert audit_entry["metadata"]["metadata_deleted"] is True


# ────────────────────────────────────────────────────────────────────
# Yetim (orphan) taraması
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orphan_query_filters_unclaimed_and_uses_hours_cutoff():
    now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    orphan_doc = {
        "photo_id": "orphan1",
        "tenant_id": "tenant-2",
        "booking_id": "bk2",
        "uploaded_at": (now - timedelta(hours=48)).isoformat(),
        "claimed": False,
    }
    db = _mock_db(find_results=[[], [orphan_doc]])

    counts = await prune_expired_id_photos(
        db=db, retention_days=90, orphan_ttl_hours=24, now=now,
    )
    assert counts == {"expired": 0, "orphans": 1}

    orphan_query = db.online_checkin_id_photos.find.call_args_list[1][0][0]
    assert orphan_query["claimed"] is False
    expected_iso = (now - timedelta(hours=24)).isoformat()
    assert any(
        c.get("uploaded_at") == {"$lt": expected_iso}
        for c in orphan_query["$or"]
    ), orphan_query

    audit_entry = db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["metadata"]["reason"] == "orphan_unclaimed"
    assert audit_entry["metadata"]["claimed"] is False


@pytest.mark.asyncio
async def test_recent_orphan_is_not_deleted():
    """24 saatten yeni yetim yükleme query filtresine takılmayacağı için
    cursor onu döndürmez — sayaç sıfır kalmalı."""
    now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    db = _mock_db(find_results=[[], []])  # iki tarama da boş

    counts = await prune_expired_id_photos(
        db=db, retention_days=90, orphan_ttl_hours=24, now=now,
    )
    assert counts == {"expired": 0, "orphans": 0}
    db.online_checkin_id_photos.delete_one.assert_not_awaited()
    db.audit_logs.insert_one.assert_not_awaited()


# ────────────────────────────────────────────────────────────────────
# Env defaults & emniyet supabı
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_env_defaults_used_when_args_omitted(monkeypatch):
    monkeypatch.delenv("ID_PHOTO_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("ID_PHOTO_ORPHAN_TTL_HOURS", raising=False)
    now = datetime(2026, 5, 1, tzinfo=UTC)
    db = _mock_db(find_results=[[], []])

    await prune_expired_id_photos(db=db, now=now)

    retention_query = db.online_checkin_id_photos.find.call_args_list[0][0][0]
    expected_iso = (now - timedelta(days=90)).isoformat()
    assert any(
        c.get("uploaded_at") == {"$lt": expected_iso}
        for c in retention_query["$or"]
    )

    orphan_query = db.online_checkin_id_photos.find.call_args_list[1][0][0]
    expected_orphan_iso = (now - timedelta(hours=24)).isoformat()
    assert any(
        c.get("uploaded_at") == {"$lt": expected_orphan_iso}
        for c in orphan_query["$or"]
    )


@pytest.mark.asyncio
async def test_env_overrides_apply(monkeypatch):
    monkeypatch.setenv("ID_PHOTO_RETENTION_DAYS", "30")
    monkeypatch.setenv("ID_PHOTO_ORPHAN_TTL_HOURS", "6")
    now = datetime(2026, 5, 1, tzinfo=UTC)
    db = _mock_db(find_results=[[], []])

    await prune_expired_id_photos(db=db, now=now)

    retention_query = db.online_checkin_id_photos.find.call_args_list[0][0][0]
    expected_iso = (now - timedelta(days=30)).isoformat()
    assert any(
        c.get("uploaded_at") == {"$lt": expected_iso}
        for c in retention_query["$or"]
    )
    orphan_query = db.online_checkin_id_photos.find.call_args_list[1][0][0]
    expected_orphan_iso = (now - timedelta(hours=6)).isoformat()
    assert any(
        c.get("uploaded_at") == {"$lt": expected_orphan_iso}
        for c in orphan_query["$or"]
    )


@pytest.mark.asyncio
async def test_invalid_env_int_falls_back_to_default(monkeypatch, caplog):
    monkeypatch.setenv("ID_PHOTO_RETENTION_DAYS", "not-a-number")
    db = _mock_db(find_results=[[], []])
    now = datetime(2026, 5, 1, tzinfo=UTC)
    with caplog.at_level("WARNING", logger="domains.guest.checkin_id_photo_cleanup"):
        await prune_expired_id_photos(db=db, orphan_ttl_hours=24, now=now)
    retention_query = db.online_checkin_id_photos.find.call_args_list[0][0][0]
    expected_iso = (now - timedelta(days=90)).isoformat()
    assert any(
        c.get("uploaded_at") == {"$lt": expected_iso}
        for c in retention_query["$or"]
    )
    assert any("invalid" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_retention_days_zero_skips_retention_sweep(caplog):
    db = _mock_db(find_results=[[]])  # sadece orphan find çağrılmalı
    now = datetime(2026, 5, 1, tzinfo=UTC)
    with caplog.at_level("WARNING", logger="domains.guest.checkin_id_photo_cleanup"):
        counts = await prune_expired_id_photos(
            db=db, retention_days=0, orphan_ttl_hours=24, now=now,
        )
    assert counts == {"expired": 0, "orphans": 0}
    assert db.online_checkin_id_photos.find.call_count == 1
    assert any("retention_days=0" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_orphan_ttl_zero_skips_orphan_sweep(caplog):
    db = _mock_db(find_results=[[]])  # sadece retention find çağrılmalı
    now = datetime(2026, 5, 1, tzinfo=UTC)
    with caplog.at_level("WARNING", logger="domains.guest.checkin_id_photo_cleanup"):
        counts = await prune_expired_id_photos(
            db=db, retention_days=90, orphan_ttl_hours=0, now=now,
        )
    assert counts == {"expired": 0, "orphans": 0}
    assert db.online_checkin_id_photos.find.call_count == 1
    assert any("orphan_ttl_hours=0" in r.getMessage() for r in caplog.records)


# ────────────────────────────────────────────────────────────────────
# Hata dayanıklılığı
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_metadata_deleted_even_when_file_delete_fails(monkeypatch):
    """delete_id_photo False/exception dönerse metadata yine de silinmeli."""
    import domains.guest.checkin_id_photo_storage as storage

    def _fail(*, tenant_id, photo_id):
        raise OSError("disk gone")

    monkeypatch.setattr(storage, "delete_id_photo", _fail)
    now = datetime(2026, 5, 1, tzinfo=UTC)
    doc = {
        "photo_id": "p1", "tenant_id": "t1", "booking_id": "b1",
        "uploaded_at": (now - timedelta(days=120)).isoformat(),
        "claimed": True,
    }
    db = _mock_db(find_results=[[doc], []])

    counts = await prune_expired_id_photos(
        db=db, retention_days=90, orphan_ttl_hours=24, now=now,
    )
    # delete_one başarılı → kayıt silindi sayılır.
    assert counts == {"expired": 1, "orphans": 0}
    db.online_checkin_id_photos.delete_one.assert_awaited_once()
    audit_entry = db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["metadata"]["file_deleted"] is False
    assert audit_entry["metadata"]["metadata_deleted"] is True


@pytest.mark.asyncio
async def test_skips_doc_missing_photo_id_or_tenant():
    """Bozuk metadata kaydı (photo_id veya tenant_id eksik) atlanmalı —
    silme/audit denenmemeli."""
    now = datetime(2026, 5, 1, tzinfo=UTC)
    bad_doc = {"uploaded_at": (now - timedelta(days=120)).isoformat()}
    db = _mock_db(find_results=[[bad_doc], []])

    counts = await prune_expired_id_photos(
        db=db, retention_days=90, orphan_ttl_hours=24, now=now,
    )
    assert counts == {"expired": 0, "orphans": 0}
    db.online_checkin_id_photos.delete_one.assert_not_awaited()
    db.audit_logs.insert_one.assert_not_awaited()


# ────────────────────────────────────────────────────────────────────
# Worker lifecycle / env gate / interval clamp
# ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _ensure_worker_stopped():
    await stop_checkin_id_photo_cleanup_worker()
    yield
    await stop_checkin_id_photo_cleanup_worker()


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        ("no", False),
        ("off", False),
    ],
)
def test_is_enabled_env_gate(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("ID_PHOTO_CLEANUP_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ID_PHOTO_CLEANUP_ENABLED", value)
    assert _is_enabled() is expected


@pytest.mark.asyncio
async def test_start_worker_disabled_via_env(monkeypatch):
    monkeypatch.setenv("ID_PHOTO_CLEANUP_ENABLED", "0")
    start_checkin_id_photo_cleanup_worker()
    assert cic._worker_task is None


@pytest.mark.asyncio
async def test_start_worker_idempotent(monkeypatch):
    monkeypatch.setenv("ID_PHOTO_CLEANUP_ENABLED", "1")
    monkeypatch.setenv("ID_PHOTO_CLEANUP_INTERVAL_SECONDS", "60")
    start_checkin_id_photo_cleanup_worker()
    first = cic._worker_task
    assert first is not None
    start_checkin_id_photo_cleanup_worker()
    assert cic._worker_task is first


@pytest.mark.asyncio
async def test_stop_worker_cancels_cleanly(monkeypatch):
    monkeypatch.setenv("ID_PHOTO_CLEANUP_ENABLED", "1")
    monkeypatch.setenv("ID_PHOTO_CLEANUP_INTERVAL_SECONDS", "60")
    start_checkin_id_photo_cleanup_worker()
    task = cic._worker_task
    assert task is not None and not task.done()
    await stop_checkin_id_photo_cleanup_worker()
    assert cic._worker_task is None
    assert task.done()


@pytest.mark.asyncio
async def test_stop_worker_when_not_started():
    await stop_checkin_id_photo_cleanup_worker()  # raise etmemeli


@pytest.mark.asyncio
async def test_interval_clamped_to_minimum(monkeypatch, caplog):
    monkeypatch.setenv("ID_PHOTO_CLEANUP_ENABLED", "1")
    monkeypatch.setenv("ID_PHOTO_CLEANUP_INTERVAL_SECONDS", "5")
    with caplog.at_level("WARNING", logger="domains.guest.checkin_id_photo_cleanup"):
        start_checkin_id_photo_cleanup_worker()
    assert any("clamping" in r.getMessage().lower() for r in caplog.records)
    assert cic._worker_task is not None


@pytest.mark.asyncio
async def test_worker_loop_cancels_during_initial_sleep():
    task = asyncio.create_task(_worker_loop(interval_seconds=3600))
    await asyncio.sleep(0)
    task.cancel()
    await task
    assert task.done()
