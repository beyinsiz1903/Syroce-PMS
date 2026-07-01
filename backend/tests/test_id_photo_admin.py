"""
Tests: Task #86 — Bekleyen Kimlik Fotoğrafları paneli için backend uçları.

Üç uç:
  GET    /api/checkin/online/id-photos              — sayfalı liste, filtreler
  DELETE /api/checkin/online/id-photos/{photo_id}    — manuel tek silme
  POST   /api/checkin/online/id-photos/bulk-delete   — KVKK toplu silme

Tüm uçlar `require_module_v97("frontdesk")` ile korunur. Tenant izolasyonu
kritik: hiçbir sorgu/silme `current_user.tenant_id` dışına çıkmamalı.

Motor cursor'u yerine `MagicMock`/`AsyncMock` kullanılır; gerçek MongoDB
event loop'una dokunulmaz — test_id_photo_view_report.py ile aynı disiplin.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from models.enums import UserRole
from models.schemas import User


def _make_user(tenant: str = "tenant-abc", uid: str = "user-fd-1") -> User:
    return User(
        id=uid,
        tenant_id=tenant,
        email="fd@example.com",
        username="fd1",
        name="Front Desk",
        role=UserRole.FRONT_DESK,
    )


class _AsyncCursor:
    """Motor cursor stand-in: hem `to_list(N)` hem `async for` çalışır.

    Bulk delete uçunda `async for doc in cursor:` kullanıldığı için
    `to_list` mock'u tek başına yetmiyor; `__aiter__/__anext__`
    desteğini de veriyoruz. `sort/skip/limit` self-return — chained
    list endpoint çağrılarında zincir kırılmasın.
    """
    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self._snapshot = list(rows)
        self.sort = MagicMock(return_value=self)
        self.skip = MagicMock(return_value=self)
        self.limit = MagicMock(return_value=self)

    async def to_list(self, _length=None):
        return list(self._snapshot)

    def __aiter__(self):
        self._iter = iter(self._snapshot)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _make_mock_db_find(rows: list[dict], total: int | None = None):
    """`db.online_checkin_id_photos.find(q, p)` → cursor (bkz. _AsyncCursor)."""
    db_mock = MagicMock()
    coll = MagicMock()

    cursor = _AsyncCursor(rows)
    find = MagicMock(return_value=cursor)
    coll.find = find
    coll.count_documents = AsyncMock(
        return_value=total if total is not None else len(rows)
    )
    coll.find_one = AsyncMock(return_value=None)
    coll.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

    db_mock.online_checkin_id_photos = coll

    # Task #124 — list endpoint artık per-tenant retention çözüyor;
    # tenant_settings.find_one async olarak çağrılıyor. Default: None →
    # env varsayılanına düş.
    tenant_settings = MagicMock()
    tenant_settings.find_one = AsyncMock(return_value=None)
    tenant_settings.update_one = AsyncMock()
    db_mock.tenant_settings = tenant_settings

    db_mock.audit_logs = MagicMock()
    db_mock.audit_logs.insert_one = AsyncMock()
    return db_mock, find


# ──────────────────────────────────────────────────────────────────
# GET /api/checkin/online/id-photos — list
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_query_pins_tenant_id():
    """Tenant izolasyonu: find() sorgusunda her zaman current_user.tenant_id."""
    from domains.guest import checkin_router as r

    db_mock, find = _make_mock_db_find([])
    user = _make_user(tenant="tenant-xyz")

    with patch.object(r, "db", db_mock):
        await r.list_online_checkin_id_photos(
            booking_id=None, guest_id=None, claimed=None,
            uploaded_after=None, uploaded_before=None,
            limit=100, offset=0, current_user=user, _perm=None,
        )

    query = find.call_args[0][0]
    assert query["tenant_id"] == "tenant-xyz"


@pytest.mark.asyncio
async def test_list_filters_translate_to_query():
    """booking_id, guest_id, claimed, uploaded_after/before → mongo query."""
    from domains.guest import checkin_router as r

    db_mock, find = _make_mock_db_find([])
    user = _make_user()

    with patch.object(r, "db", db_mock):
        await r.list_online_checkin_id_photos(
            booking_id="bk-1", guest_id="g-9", claimed=False,
            uploaded_after="2026-01-01T00:00:00",
            uploaded_before="2026-05-01T00:00:00",
            limit=10, offset=0, current_user=user, _perm=None,
        )

    query = find.call_args[0][0]
    assert query["booking_id"] == "bk-1"
    assert query["guest_id"] == "g-9"
    assert query["claimed"] is False
    assert query["uploaded_at"]["$gte"] == "2026-01-01T00:00:00"
    assert query["uploaded_at"]["$lte"] == "2026-05-01T00:00:00"


@pytest.mark.asyncio
async def test_list_response_shape_includes_retention_and_expires_at(monkeypatch):
    """expires_at = uploaded_at + retention_days; retention_days yanıtta olmalı."""
    from domains.guest import checkin_router as r

    monkeypatch.setenv("ID_PHOTO_RETENTION_DAYS", "30")
    rows = [
        {
            "photo_id": "p1",
            "tenant_id": "tenant-abc",
            "booking_id": "bk1",
            "guest_id": "g1",
            "checkin_id": "c1",
            "claimed": True,
            "uploaded_at": "2026-04-01T10:00:00+00:00",
            "size_bytes": 12345,
            "sha256": "abc",
            "content_type": "image/jpeg",
            "extension": "jpg",
            "uploaded_by": "guest:bk1",
            "uploaded_by_role": "guest",
            "source": "online_checkin",
        },
    ]
    db_mock, _ = _make_mock_db_find(rows, total=42)
    user = _make_user()

    with patch.object(r, "db", db_mock):
        result = await r.list_online_checkin_id_photos(
            booking_id=None, guest_id=None, claimed=None,
            uploaded_after=None, uploaded_before=None,
            limit=100, offset=0, current_user=user, _perm=None,
        )

    assert result["retention_days"] == 30
    assert result["total"] == 42
    assert len(result["items"]) == 1
    item = result["items"][0]
    # 2026-04-01 + 30 gün = 2026-05-01
    assert item["expires_at"].startswith("2026-05-01")
    assert item["photo_id"] == "p1"
    assert item["claimed"] is True
    # Dahili alanlar yanıtta sızmamalı
    assert "_id" not in item


@pytest.mark.asyncio
async def test_list_pagination_uses_skip_and_limit():
    """offset/limit → cursor.skip/limit."""
    from domains.guest import checkin_router as r

    db_mock, _ = _make_mock_db_find([])
    user = _make_user()

    with patch.object(r, "db", db_mock):
        await r.list_online_checkin_id_photos(
            booking_id=None, guest_id=None, claimed=None,
            uploaded_after=None, uploaded_before=None,
            limit=25, offset=50, current_user=user, _perm=None,
        )

    cursor = db_mock.online_checkin_id_photos.find.return_value
    cursor.skip.assert_called_with(50)
    cursor.limit.assert_called_with(25)


# ──────────────────────────────────────────────────────────────────
# DELETE /api/checkin/online/id-photos/{photo_id} — manual delete
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_delete_requires_reason():
    """Boş veya yalnızca boşluk olan reason → 400."""
    from domains.guest import checkin_router as r

    db_mock, _ = _make_mock_db_find([])
    user = _make_user()

    with patch.object(r, "db", db_mock):
        with pytest.raises(HTTPException) as exc:
            await r.manual_delete_online_checkin_id_photo(
                photo_id="p1", reason="   ", current_user=user, _perm=None,
            )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_manual_delete_404_when_not_found_or_other_tenant():
    """find_one None döndürürse 404 — başka tenant'a sızmaz."""
    from domains.guest import checkin_router as r

    db_mock, _ = _make_mock_db_find([])
    db_mock.online_checkin_id_photos.find_one = AsyncMock(return_value=None)
    user = _make_user()

    with patch.object(r, "db", db_mock):
        with pytest.raises(HTTPException) as exc:
            await r.manual_delete_online_checkin_id_photo(
                photo_id="p1", reason="yanlış yükleme",
                current_user=user, _perm=None,
            )
        assert exc.value.status_code == 404

    # find_one tenant_id ile çağrıldı mı?
    q = db_mock.online_checkin_id_photos.find_one.call_args[0][0]
    assert q["tenant_id"] == user.tenant_id
    assert q["photo_id"] == "p1"


@pytest.mark.asyncio
async def test_manual_delete_calls_delete_one_with_actor_and_reason(monkeypatch):
    """`_delete_one` çağrısı actor_id=current_user.id, reason='manual_delete:...'.
    Bu, audit kaydının action='manual_delete' olarak yazılmasını sağlar
    (cleanup modülünde actor_id != None branch'i)."""
    from domains.guest import checkin_router as r
    from domains.guest import checkin_id_photo_cleanup as cic

    doc = {
        "photo_id": "p1",
        "tenant_id": "tenant-abc",
        "booking_id": "bk1",
        "guest_id": "g1",
        "checkin_id": "c1",
        "claimed": True,
        "uploaded_at": "2026-04-01T10:00:00+00:00",
    }
    db_mock, _ = _make_mock_db_find([])
    db_mock.online_checkin_id_photos.find_one = AsyncMock(return_value=doc)
    user = _make_user(uid="user-fd-7")

    delete_calls = []

    async def fake_delete_one(*, db, doc, reason, actor_id=None):
        delete_calls.append({"reason": reason, "actor_id": actor_id, "photo_id": doc["photo_id"]})
        return True

    monkeypatch.setattr(cic, "_delete_one", fake_delete_one)

    with patch.object(r, "db", db_mock):
        result = await r.manual_delete_online_checkin_id_photo(
            photo_id="p1", reason="KVKK silme talebi #2026-12",
            current_user=user, _perm=None,
        )

    assert result["deleted"] is True
    assert result["photo_id"] == "p1"
    assert len(delete_calls) == 1
    assert delete_calls[0]["actor_id"] == "user-fd-7"
    assert delete_calls[0]["reason"].startswith("manual_delete:")
    assert "KVKK silme talebi #2026-12" in delete_calls[0]["reason"]


@pytest.mark.asyncio
async def test_manual_delete_500_when_delete_one_returns_false(monkeypatch):
    """Hem dosya hem metadata silme başarısız → 500 (sessiz başarısızlık yok)."""
    from domains.guest import checkin_router as r
    from domains.guest import checkin_id_photo_cleanup as cic

    doc = {"photo_id": "p1", "tenant_id": "tenant-abc"}
    db_mock, _ = _make_mock_db_find([])
    db_mock.online_checkin_id_photos.find_one = AsyncMock(return_value=doc)
    user = _make_user()

    async def fake_delete_one(*, db, doc, reason, actor_id=None):
        return False

    monkeypatch.setattr(cic, "_delete_one", fake_delete_one)

    with patch.object(r, "db", db_mock):
        with pytest.raises(HTTPException) as exc:
            await r.manual_delete_online_checkin_id_photo(
                photo_id="p1", reason="test",
                current_user=user, _perm=None,
            )
        assert exc.value.status_code == 500


# ──────────────────────────────────────────────────────────────────
# POST /api/checkin/online/id-photos/bulk-delete — KVKK
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_delete_requires_booking_or_guest_id():
    """Hiçbiri verilmezse 400."""
    from domains.guest import checkin_router as r

    db_mock, _ = _make_mock_db_find([])
    user = _make_user()

    with patch.object(r, "db", db_mock):
        with pytest.raises(HTTPException) as exc:
            await r.bulk_delete_online_checkin_id_photos(
                payload={"reason": "test"}, current_user=user, _perm=None,
            )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_delete_requires_reason():
    """booking_id verilse bile reason yoksa 400."""
    from domains.guest import checkin_router as r

    db_mock, _ = _make_mock_db_find([])
    user = _make_user()

    with patch.object(r, "db", db_mock):
        with pytest.raises(HTTPException) as exc:
            await r.bulk_delete_online_checkin_id_photos(
                payload={"booking_id": "bk1", "reason": "  "},
                current_user=user, _perm=None,
            )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_delete_iterates_matching_docs_with_actor(monkeypatch):
    """Eşleşen her doc için _delete_one çağrılır; actor_id ve reason geçer.
    Sayım yanıtta döner."""
    from domains.guest import checkin_router as r
    from domains.guest import checkin_id_photo_cleanup as cic

    docs = [
        {"photo_id": "p1", "tenant_id": "tenant-abc", "booking_id": "bk1"},
        {"photo_id": "p2", "tenant_id": "tenant-abc", "booking_id": "bk1"},
        {"photo_id": "p3", "tenant_id": "tenant-abc", "booking_id": "bk1"},
    ]
    db_mock, find = _make_mock_db_find(docs)
    user = _make_user(uid="user-fd-9")

    delete_calls = []

    async def fake_delete_one(*, db, doc, reason, actor_id=None):
        delete_calls.append(doc["photo_id"])
        return True

    monkeypatch.setattr(cic, "_delete_one", fake_delete_one)

    with patch.object(r, "db", db_mock):
        result = await r.bulk_delete_online_checkin_id_photos(
            payload={"booking_id": "bk1", "reason": "KVKK #2026-7"},
            current_user=user, _perm=None,
        )

    # Tenant izolasyonu + booking filtresi
    q = find.call_args[0][0]
    assert q == {"tenant_id": "tenant-abc", "booking_id": "bk1"}
    assert delete_calls == ["p1", "p2", "p3"]
    assert result["matched"] == 3
    assert result["deleted"] == 3
    assert result["failed_photo_ids"] == []
    assert result["booking_id"] == "bk1"


@pytest.mark.asyncio
async def test_bulk_delete_partial_failure_reports_failed_ids(monkeypatch):
    """Bir silme False dönerse failed_photo_ids'e eklenir, diğerleri devam eder."""
    from domains.guest import checkin_router as r
    from domains.guest import checkin_id_photo_cleanup as cic

    docs = [
        {"photo_id": "p1", "tenant_id": "tenant-abc", "guest_id": "g9"},
        {"photo_id": "p2", "tenant_id": "tenant-abc", "guest_id": "g9"},
    ]
    db_mock, find = _make_mock_db_find(docs)
    user = _make_user()

    async def fake_delete_one(*, db, doc, reason, actor_id=None):
        return doc["photo_id"] != "p2"  # p2 başarısız

    monkeypatch.setattr(cic, "_delete_one", fake_delete_one)

    with patch.object(r, "db", db_mock):
        result = await r.bulk_delete_online_checkin_id_photos(
            payload={"guest_id": "g9", "reason": "KVKK"},
            current_user=user, _perm=None,
        )

    q = find.call_args[0][0]
    assert q == {"tenant_id": "tenant-abc", "guest_id": "g9"}
    assert result["matched"] == 2
    assert result["deleted"] == 1
    assert result["failed_photo_ids"] == ["p2"]


@pytest.mark.asyncio
async def test_bulk_delete_iterates_all_matches_no_1000_cap(monkeypatch):
    """KVKK gereği eşleşen TÜM kayıtlar silinmeli — eski `to_list(1000)`
    cap'i kaldırıldı; cursor sonuna kadar async iterate edilmeli.

    1500 dokümanlık bir cursor üretip her birinin _delete_one ile
    silindiğini doğrularız. Cap 1000'de kalsaydı bu test 1000'de
    biterdi; >1000 davranışını koruma altına alır."""
    from domains.guest import checkin_router as r
    from domains.guest import checkin_id_photo_cleanup as cic

    big_docs = [
        {"photo_id": f"p{i}", "tenant_id": "tenant-abc", "booking_id": "bk1"}
        for i in range(1500)
    ]
    db_mock, find = _make_mock_db_find(big_docs)
    user = _make_user()

    delete_calls: list[str] = []

    async def fake_delete_one(*, db, doc, reason, actor_id=None):
        delete_calls.append(doc["photo_id"])
        return True

    monkeypatch.setattr(cic, "_delete_one", fake_delete_one)

    with patch.object(r, "db", db_mock):
        result = await r.bulk_delete_online_checkin_id_photos(
            payload={"booking_id": "bk1", "reason": "KVKK toplu"},
            current_user=user, _perm=None,
        )

    assert len(delete_calls) == 1500, "to_list(1000) cap'i geri sızmış olmasın"
    assert result["matched"] == 1500
    assert result["deleted"] == 1500
    assert result["failed_photo_ids"] == []
    assert delete_calls[0] == "p0"
    assert delete_calls[-1] == "p1499"


@pytest.mark.asyncio
async def test_bulk_delete_idempotent_when_no_matches(monkeypatch):
    """Eşleşme yoksa 0/0 döner — 404 değil (idempotent)."""
    from domains.guest import checkin_router as r
    from domains.guest import checkin_id_photo_cleanup as cic

    db_mock, _ = _make_mock_db_find([])
    user = _make_user()

    async def fake_delete_one(*, db, doc, reason, actor_id=None):
        return True

    monkeypatch.setattr(cic, "_delete_one", fake_delete_one)

    with patch.object(r, "db", db_mock):
        result = await r.bulk_delete_online_checkin_id_photos(
            payload={"booking_id": "bk-missing", "reason": "x"},
            current_user=user, _perm=None,
        )

    assert result["matched"] == 0
    assert result["deleted"] == 0
    assert result["failed_photo_ids"] == []


# ──────────────────────────────────────────────────────────────────
# Audit shape via _delete_one — actor_id geçişi cleanup modülünde
# action='manual_delete' branch'ini tetiklemeli.
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_action_is_manual_delete_when_actor_id_provided():
    """`_audit_delete(actor_id='user-1', ...)` audit_logs.insert_one'a
    yazılan kaydın action='manual_delete' olduğunu doğrula."""
    from domains.guest import checkin_id_photo_cleanup as cic

    db_mock = MagicMock()
    db_mock.audit_logs = MagicMock()
    db_mock.audit_logs.insert_one = AsyncMock()

    doc = {
        "tenant_id": "tenant-abc",
        "photo_id": "p1",
        "booking_id": "bk1",
        "guest_id": "g1",
        "checkin_id": "c1",
        "claimed": True,
        "uploaded_at": "2026-04-01T10:00:00+00:00",
    }
    await cic._audit_delete(
        db=db_mock, doc=doc, reason="manual_delete:KVKK",
        file_deleted=True, metadata_deleted=True, actor_id="user-fd-1",
    )

    entry = db_mock.audit_logs.insert_one.call_args[0][0]
    assert entry["action"] == "manual_delete"
    assert entry["actor_id"] == "user-fd-1"
    assert entry["entity_type"] == "online_checkin_id_photo"
    assert entry["entity_id"] == "p1"
    assert entry["metadata"]["reason"] == "manual_delete:KVKK"
    assert entry["metadata"]["guest_id"] == "g1"


@pytest.mark.asyncio
async def test_audit_action_stays_auto_delete_for_worker_calls():
    """actor_id=None (varsayılan, cleanup worker) → action='auto_delete'.
    Bu, Task #72 davranışının regresyon olmadığını doğrular."""
    from domains.guest import checkin_id_photo_cleanup as cic

    db_mock = MagicMock()
    db_mock.audit_logs = MagicMock()
    db_mock.audit_logs.insert_one = AsyncMock()

    doc = {"tenant_id": "tenant-abc", "photo_id": "p1"}
    await cic._audit_delete(
        db=db_mock, doc=doc, reason="retention_expired",
        file_deleted=True, metadata_deleted=True,
    )

    entry = db_mock.audit_logs.insert_one.call_args[0][0]
    assert entry["action"] == "auto_delete"
    assert entry["actor_id"] is None


# ──────────────────────────────────────────────────────────────────
# Task #124 — GET/PUT /api/checkin/online/settings/id-photo-retention
# ──────────────────────────────────────────────────────────────────


def _settings_db_mock(stored_value=None):
    """Tenant settings için izole bir db mock. ``stored_value`` None ise
    tenant ayarı yok (env default geçerli); int verilirse o değer dönülür."""
    db_mock = MagicMock()
    settings_doc = (
        {"id_photo_retention_days": stored_value} if stored_value is not None else None
    )
    ts = MagicMock()
    ts.find_one = AsyncMock(return_value=settings_doc)
    ts.update_one = AsyncMock()
    db_mock.tenant_settings = ts
    db_mock.audit_logs = MagicMock()
    db_mock.audit_logs.insert_one = AsyncMock()
    return db_mock


@pytest.mark.asyncio
async def test_get_retention_setting_returns_env_default_when_unset(monkeypatch):
    """Tenant ayarı yokken efektif değer env varsayılanı + source=env_default."""
    from domains.guest import checkin_router as r

    monkeypatch.setenv("ID_PHOTO_RETENTION_DAYS", "60")
    db_mock = _settings_db_mock(stored_value=None)
    user = _make_user(tenant="tenant-x")

    with patch.object(r, "db", db_mock):
        out = await r.get_id_photo_retention_setting(current_user=user, _perm=None)

    assert out["retention_days"] == 60
    assert out["source"] == "env_default"
    assert out["env_default"] == 60
    assert out["tenant_override"] is None
    assert out["min_days"] == 1
    assert out["max_days"] == 365


@pytest.mark.asyncio
async def test_get_retention_setting_returns_tenant_value(monkeypatch):
    """Tenant özel değeri varsa source=tenant ve tenant_override döner."""
    from domains.guest import checkin_router as r

    monkeypatch.setenv("ID_PHOTO_RETENTION_DAYS", "60")
    db_mock = _settings_db_mock(stored_value=14)
    user = _make_user(tenant="tenant-x")

    with patch.object(r, "db", db_mock):
        out = await r.get_id_photo_retention_setting(current_user=user, _perm=None)

    assert out["retention_days"] == 14
    assert out["source"] == "tenant"
    assert out["env_default"] == 60
    assert out["tenant_override"] == 14


@pytest.mark.asyncio
async def test_get_retention_setting_handles_malformed_legacy_value(monkeypatch):
    """DB'de bozuk değer (string/None tip) → 500 yerine env default'a güvenli düş.

    Code review kontrolü: ham değer int parse edilemiyorsa tenant_override
    None döner ve source=env_default olur. resolve_tenant_retention_days
    zaten env'e düştüğü için efektif değer doğru — UI yine sayısal bir
    rozet gösterir, 500 yemez.
    """
    from domains.guest import checkin_router as r

    monkeypatch.setenv("ID_PHOTO_RETENTION_DAYS", "60")
    db_mock = MagicMock()
    db_mock.tenant_settings = MagicMock()
    db_mock.tenant_settings.find_one = AsyncMock(
        return_value={"id_photo_retention_days": "yedi-gun"},
    )
    db_mock.tenant_settings.update_one = AsyncMock()
    db_mock.audit_logs = MagicMock()
    db_mock.audit_logs.insert_one = AsyncMock()
    user = _make_user(tenant="tenant-x")

    with patch.object(r, "db", db_mock):
        out = await r.get_id_photo_retention_setting(current_user=user, _perm=None)

    assert out["retention_days"] == 60  # env fallback
    assert out["source"] == "env_default"
    assert out["tenant_override"] is None


@pytest.mark.asyncio
async def test_put_retention_setting_writes_clamped_value():
    """Geçerli int → tenant_settings'e yazılır, audit kaydı oluşur."""
    from domains.guest import checkin_router as r

    db_mock = _settings_db_mock(stored_value=None)
    user = _make_user(tenant="tenant-x", uid="user-7")

    # update_one sonrasında okuma için find_one'ı yeni değere döndür.
    db_mock.tenant_settings.find_one = AsyncMock(
        return_value={"id_photo_retention_days": 45},
    )

    with patch.object(r, "db", db_mock):
        out = await r.update_id_photo_retention_setting(
            payload={"retention_days": 45}, current_user=user, _perm=None,
        )

    assert out["retention_days"] == 45
    assert out["source"] == "tenant"
    assert out["tenant_override"] == 45

    # update_one çağrısı: tenant_id filtresi + $set.id_photo_retention_days=45
    update_call = db_mock.tenant_settings.update_one.call_args
    assert update_call.args[0] == {"tenant_id": "tenant-x"}
    set_payload = update_call.args[1]["$set"]
    assert set_payload["id_photo_retention_days"] == 45
    assert "id_photo_retention_updated_at" in set_payload
    assert set_payload["id_photo_retention_updated_by"] == "user-7"
    assert update_call.kwargs.get("upsert") is True

    # KVKK audit izi yazılmalı.
    db_mock.audit_logs.insert_one.assert_awaited()
    audit_entry = db_mock.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["action"] == "update_id_photo_retention"
    assert audit_entry["entity_type"] == "tenant_settings"


@pytest.mark.asyncio
async def test_put_retention_setting_rejects_out_of_range():
    from domains.guest import checkin_router as r

    db_mock = _settings_db_mock(stored_value=None)
    user = _make_user()

    for bad_value in (0, -5, 366, 9999):
        with patch.object(r, "db", db_mock):
            with pytest.raises(HTTPException) as exc:
                await r.update_id_photo_retention_setting(
                    payload={"retention_days": bad_value},
                    current_user=user, _perm=None,
                )
        assert exc.value.status_code == 400
    db_mock.tenant_settings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_put_retention_setting_rejects_non_int_types():
    """bool ve string gibi int olmayan değerler 400 dönmeli."""
    from domains.guest import checkin_router as r

    db_mock = _settings_db_mock(stored_value=None)
    user = _make_user()

    for bad in (True, False, "abc", [30], {"x": 1}):
        with patch.object(r, "db", db_mock):
            with pytest.raises(HTTPException) as exc:
                await r.update_id_photo_retention_setting(
                    payload={"retention_days": bad},
                    current_user=user, _perm=None,
                )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_put_retention_setting_null_unsets_tenant_value(monkeypatch):
    """null payload → $unset; bir sonraki okumada env default'a döner."""
    from domains.guest import checkin_router as r

    monkeypatch.setenv("ID_PHOTO_RETENTION_DAYS", "75")
    db_mock = _settings_db_mock(stored_value=None)
    user = _make_user(tenant="tenant-x")

    # PUT sonrası okuma tenant ayarı yok döner (silindi)
    db_mock.tenant_settings.find_one = AsyncMock(return_value=None)

    with patch.object(r, "db", db_mock):
        out = await r.update_id_photo_retention_setting(
            payload={"retention_days": None}, current_user=user, _perm=None,
        )

    update_call = db_mock.tenant_settings.update_one.call_args
    assert "$unset" in update_call.args[1]
    assert "id_photo_retention_days" in update_call.args[1]["$unset"]
    assert update_call.kwargs.get("upsert") is True

    assert out["retention_days"] == 75
    assert out["source"] == "env_default"
    assert out["tenant_override"] is None


@pytest.mark.asyncio
async def test_put_retention_setting_missing_field_400():
    """Body'de retention_days alanı hiç yoksa 400; sıfırlamak için açıkça null gerekli."""
    from domains.guest import checkin_router as r

    db_mock = _settings_db_mock(stored_value=None)
    user = _make_user()

    with patch.object(r, "db", db_mock):
        with pytest.raises(HTTPException) as exc:
            await r.update_id_photo_retention_setting(
                payload={}, current_user=user, _perm=None,
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_endpoint_uses_tenant_specific_retention():
    """List yanıtı per-tenant retention günü ile expires_at hesaplar."""
    from domains.guest import checkin_router as r

    rows = [
        {
            "photo_id": "p1",
            "tenant_id": "tenant-abc",
            "booking_id": "bk1",
            "guest_id": "g1",
            "checkin_id": "c1",
            "claimed": True,
            "uploaded_at": "2026-04-01T10:00:00+00:00",
            "size_bytes": 100,
            "sha256": "x",
            "content_type": "image/jpeg",
            "extension": "jpg",
            "uploaded_by": "guest:bk1",
            "uploaded_by_role": "guest",
            "source": "online_checkin",
        },
    ]
    db_mock, _ = _make_mock_db_find(rows, total=1)
    # Bu kiracıya 14 gün set edilmiş — list endpoint env'i değil bunu kullanmalı.
    db_mock.tenant_settings.find_one = AsyncMock(
        return_value={"id_photo_retention_days": 14},
    )
    user = _make_user(tenant="tenant-abc")

    with patch.object(r, "db", db_mock):
        result = await r.list_online_checkin_id_photos(
            booking_id=None, guest_id=None, claimed=None,
            uploaded_after=None, uploaded_before=None,
            limit=100, offset=0, current_user=user, _perm=None,
        )

    assert result["retention_days"] == 14
    # 2026-04-01 + 14 gün = 2026-04-15
    assert result["items"][0]["expires_at"].startswith("2026-04-15")
