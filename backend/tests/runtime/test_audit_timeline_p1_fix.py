"""
Regression — Audit Timeline P1 Fix (2026-05-13)

Pilot DB'de `audit_logs.timestamp` alanı bazı kayıtlarda `datetime`
objesi (BSON Date), bazılarında ISO string olarak yazılmış. Eski
`_group_by_time` `len(ts)` çağırıp `TypeError` fırlatıyor, route 500
dönüyordu. Fix: `_ts_to_iso` normalize + outer try/except → degraded
fallback.

Bu suite üç şeyi garanti eder:
  1. `_group_by_time` mixed/datetime/None timestamp'lerle crash etmez.
  2. `/api/audit/timeline` route TypeError yerine 200 + boş + degraded
     döner (helper'ı zorla bozarak simüle).
  3. limit/cursor parse + tenant scope korunur.
"""
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# NOT: Bu suite kasıtlı olarak motor/Mongo'ya dokunmuyor — tüm route
# testleri `monkeypatch` + `_FakeAuditCollection` ile in-process çalışır.
# Bu yüzden komşu `test_audit_timeline_stress.py`'deki "CI skip"
# uygulanmaz; P1 koruması her CI run'unda enforce edilmeli.

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ── Pure-helper tests (no DB) ────────────────────────────────────────


def test_ts_to_iso_handles_str():
    from routers.audit_timeline import _ts_to_iso
    assert _ts_to_iso("2026-05-13T10:00:00") == "2026-05-13T10:00:00"


def test_ts_to_iso_handles_datetime():
    from routers.audit_timeline import _ts_to_iso
    out = _ts_to_iso(datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC))
    assert out.startswith("2026-05-13T10:00:00")


def test_ts_to_iso_handles_none():
    from routers.audit_timeline import _ts_to_iso
    assert _ts_to_iso(None) == ""


def test_group_by_time_mixed_types_no_crash():
    """Pilot DB'nin gerçek hali: aynı listede str + datetime + None."""
    from routers.audit_timeline import _group_by_time
    logs = [
        {"id": "a", "timestamp": "2026-05-13T10:00:00"},
        {"id": "b", "timestamp": datetime(2026, 5, 13, 11, 0, 0, tzinfo=UTC)},
        {"id": "c", "timestamp": None},
        {"id": "d"},  # timestamp anahtarı yok
    ]
    grouped = _group_by_time(logs)
    assert isinstance(grouped, list)
    total = sum(g["count"] for g in grouped)
    assert total == len(logs)


# ── Route-level tests (mock DB) ──────────────────────────────────────


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, _n):
        return self._docs


class _FakeAuditCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, projection=None):
        # Tenant scope guard — sadece doğru tenant_id'li kayıtları ver.
        tenant = query.get("tenant_id")
        out = [d for d in self._docs if d.get("tenant_id") == tenant]
        return _FakeCursor(out)


class _FakeUser:
    """Minimal `User` stand-in — `OperationContext.from_user` ihtiyacı."""
    id = "u1"
    tenant_id = "tenant-A"
    role = "admin"
    email = "u1@example.com"
    full_name = "User One"


@pytest.mark.asyncio
async def test_route_empty_dataset_returns_200_empty_list(monkeypatch):
    """Boş tenant → 500 değil, 200 + events=[]."""
    from routers import audit_timeline as mod

    monkeypatch.setattr(
        mod, "db",
        type("X", (), {"audit_logs": _FakeAuditCollection([])})()
    )
    out = await mod.get_audit_timeline(limit=50, current_user=_FakeUser())
    assert out["events"] == []
    assert out["count"] == 0
    assert out["has_more"] is False
    assert out.get("degraded") in (None, False)


@pytest.mark.asyncio
async def test_route_mixed_timestamps_returns_200(monkeypatch):
    """Pilot bug repro: datetime + str karışımı → eskiden 500, artık 200."""
    from routers import audit_timeline as mod

    docs = [
        {"tenant_id": "tenant-A", "id": "1",
         "timestamp": datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)},
        {"tenant_id": "tenant-A", "id": "2", "timestamp": "2026-05-13T11:00:00"},
        # cross-tenant — gelmemeli
        {"tenant_id": "tenant-B", "id": "leak", "timestamp": "2026-05-13T12:00:00"},
    ]
    monkeypatch.setattr(
        mod, "db",
        type("X", (), {"audit_logs": _FakeAuditCollection(docs)})()
    )
    out = await mod.get_audit_timeline(limit=50, current_user=_FakeUser())
    assert out["count"] == 2  # cross-tenant filtered out
    ids = [e["id"] for e in out["events"]]
    assert "leak" not in ids
    # Tüm timestamp'ler artık string (JSON-serializable)
    for e in out["events"]:
        assert isinstance(e["timestamp"], str)


@pytest.mark.asyncio
async def test_route_unexpected_error_returns_degraded(monkeypatch):
    """Aggregation çökerse 500 değil, degraded=true 200 dön."""
    from routers import audit_timeline as mod

    class Boom:
        def find(self, *_a, **_kw):
            raise RuntimeError("simulated mongo failure")

    monkeypatch.setattr(
        mod, "db",
        type("X", (), {"audit_logs": Boom()})()
    )
    out = await mod.get_audit_timeline(limit=50, current_user=_FakeUser())
    assert out["events"] == []
    assert out["degraded"] is True


@pytest.mark.asyncio
async def test_route_limit_param_clamped_by_fastapi():
    """`limit` Query(ge=1, le=200) — FastAPI seviyesinde validate edilir.

    Burada doğrudan signature'ı çağırdığımız için Pydantic devreye
    girmez; ama testin amacı parametre tipinin int olduğunu garanti
    etmek. Daha geniş validation `test_phase6_api`'de kapsanır.
    """
    from inspect import signature
    from routers.audit_timeline import get_audit_timeline
    sig = signature(get_audit_timeline)
    limit_param = sig.parameters["limit"]
    # default 50, annotation int — FastAPI Query(ge=1, le=200) wrap eder
    assert limit_param.annotation is int


@pytest.mark.asyncio
async def test_route_cursor_and_date_filter_coexist(monkeypatch):
    """Eski kod `cursor` geldiğinde `start_date`/`end_date` üzerine yazıyordu.

    Bu regression: üç filtre birden geldiğinde fonksiyon hata vermez ve
    tenant-A kayıtları döner. (Type-aware Mongo karşılaştırması ayrı bir
    iyileştirme — bkz. raporun §3 notu; bu test sadece route içindeki
    sözlük inşaasının bozulmadığını garanti eder.)
    """
    from routers import audit_timeline as mod

    docs = [
        {"tenant_id": "tenant-A", "id": "old", "timestamp": "2026-01-01T00:00:00"},
        {"tenant_id": "tenant-A", "id": "mid", "timestamp": "2026-05-10T00:00:00"},
        {"tenant_id": "tenant-A", "id": "new", "timestamp": "2026-06-01T00:00:00"},
    ]
    monkeypatch.setattr(
        mod, "db",
        type("X", (), {"audit_logs": _FakeAuditCollection(docs)})()
    )
    out = await mod.get_audit_timeline(
        start_date="2026-04-01",
        end_date="2026-12-31",
        cursor="2026-07-01",
        limit=50,
        current_user=_FakeUser(),
    )
    # _FakeAuditCollection sadece tenant filtresi uygular (basit mock).
    # Burada amaç: 3 filtre birden geldiğinde route TypeError/KeyError
    # atmadan 200 dönsün ve tenant scope kaybolmasın.
    assert out.get("degraded") in (None, False)
    assert all(e["tenant_id"] == "tenant-A" for e in out["events"])


@pytest.mark.asyncio
async def test_route_tenant_scope_isolation(monkeypatch):
    """Aynı koleksiyonda iki tenant — yalnız çağıranın tenant'ı dönmeli."""
    from routers import audit_timeline as mod

    docs = [
        {"tenant_id": "tenant-A", "id": "ok-1", "timestamp": "2026-05-13T10:00:00"},
        {"tenant_id": "tenant-B", "id": "leak-1", "timestamp": "2026-05-13T10:00:00"},
        {"tenant_id": "tenant-A", "id": "ok-2", "timestamp": "2026-05-13T11:00:00"},
    ]
    monkeypatch.setattr(
        mod, "db",
        type("X", (), {"audit_logs": _FakeAuditCollection(docs)})()
    )
    out = await mod.get_audit_timeline(limit=50, current_user=_FakeUser())
    ids = sorted(e["id"] for e in out["events"])
    assert ids == ["ok-1", "ok-2"]
