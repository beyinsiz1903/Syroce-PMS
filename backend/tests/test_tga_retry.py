"""TGA gönderim hatalarında otomatik tekrar deneme — Task #151.

Bu testler ``core.tga_outbound.retry_failed_outbox`` ve yardımcı
``_next_backoff_seconds`` fonksiyonlarını izole bir in-memory outbox
üzerinde doğrular. Gerçek HTTP / Mongo bağımlılıkları monkeypatch
ile kesilir.

Kapsanan davranışlar:
  * Backoff adımları (5dk, 15dk, 1sa, 4sa, sonrası 4sa cap).
  * `send_batch` failed kayıt için ``retry_count=0`` ve ``next_retry_at``
    yazar; başarılı kayıt için yazmaz.
  * `retry_failed_outbox` başarılı retry'da kaydı ``status=sent``,
    ``next_retry_at=None`` yapar.
  * Başarısız retry'da ``retry_count`` artar, ``next_retry_at`` exponential
    backoff ile güncellenir.
  * 24 saatten eski hâlâ başarısız kayıt ``failed_permanent``'e geçer ve
    ``audit_logs`` içine ``TGA_DELIVERY_FAILED`` yazılır (yönetici uyarısı).
  * `next_retry_at` gelecekteki kayıtlar bu tickte işlenmez.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core import tga_outbound


# ──────────────────────────────────────────────────────────────────────
# In-memory db stub
# ──────────────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs: list[dict]):
        self._docs = list(docs)

    def sort(self, *_a, **_kw):
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length: int):
        return list(self._docs[:length])


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []
        self._next_id = 1

    async def insert_one(self, doc: dict) -> Any:
        d = dict(doc)
        d["_id"] = self._next_id
        self._next_id += 1
        self.docs.append(d)
        return type("R", (), {"inserted_id": d["_id"]})()

    def find(self, q: dict | None = None, projection: dict | None = None):
        q = q or {}
        out: list[dict] = []
        for d in self.docs:
            if not _matches(d, q):
                continue
            out.append(dict(d))
        return _Cursor(out)

    async def update_one(self, q: dict, upd: dict) -> Any:
        for d in self.docs:
            if _matches(d, q):
                if "$set" in upd:
                    d.update(upd["$set"])
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    async def create_index(self, *_a, **_kw):
        return None


def _matches(d: dict, q: dict) -> bool:
    for k, v in q.items():
        if isinstance(v, dict):
            for op, val in v.items():
                got = d.get(k)
                if op == "$lte":
                    if got is None or not (got <= val):
                        return False
                elif op == "$ne":
                    if got == val:
                        return False
                elif op == "$exists":
                    if (k in d) != bool(val):
                        return False
                elif op == "$in":
                    if got not in val:
                        return False
                else:
                    return False
        else:
            if d.get(k) != v:
                return False
    return True


class _DB:
    def __init__(self):
        self._colls: dict[str, _Coll] = {}

    def __getitem__(self, name: str) -> _Coll:
        return self._colls.setdefault(name, _Coll())

    def __getattr__(self, name: str) -> _Coll:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._colls.setdefault(name, _Coll())


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_db(monkeypatch):
    fdb = _DB()
    monkeypatch.setattr(tga_outbound, "db", fdb)
    return fdb


@pytest.fixture
def cfg_ok(monkeypatch):
    async def _get_cfg(tenant_id: str, *, decrypt_api_key: bool = False):
        return {
            "belge_no": "BLG-1",
            "vergi_no": "VRG-1",
            "environment": "test",
            "enabled": True,
            "api_key_set": True,
            "api_key": "k-secret",
        }
    monkeypatch.setattr(tga_outbound, "get_tga_config", _get_cfg)


@pytest.fixture
def empty_envelope(monkeypatch):
    async def _build(tenant_id, end_date, *, days=7):
        return {
            "tesis_belge_no": "BLG-1",
            "vergi_no": "VRG-1",
            "data": [
                {"rapor_tarihi": (end_date - timedelta(days=i)).isoformat(),
                 "toplam_oda": 0, "net_oda_geliri": 0.0}
                for i in range(days - 1, -1, -1)
            ],
        }
    monkeypatch.setattr(tga_outbound, "build_batch_envelope", _build)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────
# Pure-function tests
# ──────────────────────────────────────────────────────────────────────

def test_backoff_steps_are_5m_15m_1h_4h_then_capped():
    assert tga_outbound._next_backoff_seconds(0) == 300
    assert tga_outbound._next_backoff_seconds(1) == 900
    assert tga_outbound._next_backoff_seconds(2) == 3600
    assert tga_outbound._next_backoff_seconds(3) == 14400
    # Cap: 4. denemeden sonra 4sa kalır.
    assert tga_outbound._next_backoff_seconds(4) == 14400
    assert tga_outbound._next_backoff_seconds(99) == 14400
    assert tga_outbound._next_backoff_seconds(-1) == 300


def test_alert_threshold_is_24h():
    assert tga_outbound.ALERT_THRESHOLD_SECONDS == 24 * 3600


# ──────────────────────────────────────────────────────────────────────
# send_batch: failed kayıt retry alanlarıyla yazılır
# ──────────────────────────────────────────────────────────────────────

def test_send_batch_failed_writes_retry_fields(fake_db, cfg_ok, empty_envelope, monkeypatch):
    async def _post_fail(cfg, env):
        return {"status": "failed", "error": "boom"}
    monkeypatch.setattr(tga_outbound, "_post_envelope", _post_fail)

    end = datetime.now(UTC).date() - timedelta(days=1)
    res = _run(tga_outbound.send_batch("t1", end, days=7, triggered_by="scheduler"))

    assert res["status"] == "failed"
    assert res["retry_count"] == 0
    assert res["first_failed_at"] == res["started_at"]
    assert res["next_retry_at"] is not None
    # next_retry_at ~ finished_at + 5dk
    nra = datetime.fromisoformat(res["next_retry_at"])
    fin = datetime.fromisoformat(res["finished_at"])
    delta = (nra - fin).total_seconds()
    assert 290 <= delta <= 310

    # Outbox'a yazıldı mı?
    outbox = fake_db[tga_outbound.OUTBOX_COLL].docs
    assert len(outbox) == 1
    assert outbox[0]["status"] == "failed"
    assert outbox[0]["next_retry_at"] is not None


def test_send_batch_success_does_not_set_retry(fake_db, cfg_ok, empty_envelope, monkeypatch):
    async def _post_ok(cfg, env):
        return {"status": "sent", "http_status": 200, "response_text": "OK"}
    monkeypatch.setattr(tga_outbound, "_post_envelope", _post_ok)

    end = datetime.now(UTC).date() - timedelta(days=1)
    res = _run(tga_outbound.send_batch("t1", end, days=7))

    assert res["status"] == "sent"
    assert res["retry_count"] == 0
    assert res["next_retry_at"] is None
    assert "first_failed_at" not in res


# ──────────────────────────────────────────────────────────────────────
# retry_failed_outbox
# ──────────────────────────────────────────────────────────────────────

def _seed_failed(fdb, *, tenant="t1", retry_count=0,
                 first_failed_minutes_ago=10,
                 next_retry_minutes_ago=1,
                 end_date=None):
    now = datetime.now(UTC)
    end_date = end_date or (now.date() - timedelta(days=1))
    doc = {
        "tenant_id": tenant,
        "end_date": end_date.isoformat(),
        "days": 7,
        "environment": "test",
        "triggered_by": "scheduler",
        "started_at": (now - timedelta(minutes=first_failed_minutes_ago)).isoformat(),
        "first_failed_at": (now - timedelta(minutes=first_failed_minutes_ago)).isoformat(),
        "finished_at": (now - timedelta(minutes=first_failed_minutes_ago)).isoformat(),
        "request_summary": {"tesis_belge_no": "BLG-1", "rapor_tarihleri": [],
                            "toplam_oda_sum": 0, "net_oda_geliri_sum": 0.0},
        "status": "failed",
        "retry_count": retry_count,
        "next_retry_at": (now - timedelta(minutes=next_retry_minutes_ago)).isoformat(),
        "error": "previous failure",
    }
    return _run(fdb[tga_outbound.OUTBOX_COLL].insert_one(doc))


def test_retry_success_marks_sent_and_clears_next_retry(
    fake_db, cfg_ok, empty_envelope, monkeypatch,
):
    _seed_failed(fake_db, retry_count=1)

    async def _post_ok(cfg, env):
        return {"status": "sent", "http_status": 200, "response_text": "OK"}
    monkeypatch.setattr(tga_outbound, "_post_envelope", _post_ok)

    stats = _run(tga_outbound.retry_failed_outbox())
    assert stats["attempted"] == 1
    assert stats["succeeded"] == 1
    assert stats["failed"] == 0
    assert stats["alerted"] == 0

    doc = fake_db[tga_outbound.OUTBOX_COLL].docs[0]
    assert doc["status"] == "sent"
    assert doc["next_retry_at"] is None
    assert doc["retry_count"] == 2  # was 1, incremented
    assert doc["error"] is None


def test_retry_failure_increments_count_and_extends_backoff(
    fake_db, cfg_ok, empty_envelope, monkeypatch,
):
    # retry_count başlangıç=0. Bu retry'dan sonra count=1 olur, dolayısıyla
    # bir sonraki backoff 15dk (steps[1]) olmalı.
    _seed_failed(fake_db, retry_count=0)

    async def _post_fail(cfg, env):
        return {"status": "failed", "http_status": 503, "response_text": "down"}
    monkeypatch.setattr(tga_outbound, "_post_envelope", _post_fail)

    before = datetime.now(UTC)
    stats = _run(tga_outbound.retry_failed_outbox())
    after = datetime.now(UTC)

    assert stats == {"attempted": 1, "succeeded": 0, "failed": 1,
                     "alerted": 0, "skipped": 0}

    doc = fake_db[tga_outbound.OUTBOX_COLL].docs[0]
    assert doc["status"] == "failed"
    assert doc["retry_count"] == 1
    assert doc["http_status"] == 503
    nra = datetime.fromisoformat(doc["next_retry_at"])
    expected_min = before + timedelta(seconds=900)
    expected_max = after + timedelta(seconds=900)
    assert expected_min <= nra <= expected_max


def test_retry_skips_records_not_yet_due(fake_db, cfg_ok, empty_envelope, monkeypatch):
    # next_retry_at gelecekte → bu tickte alınmaz.
    now = datetime.now(UTC)
    doc = {
        "tenant_id": "t1",
        "end_date": (now.date() - timedelta(days=1)).isoformat(),
        "days": 7,
        "status": "failed",
        "retry_count": 0,
        "next_retry_at": (now + timedelta(minutes=10)).isoformat(),
        "first_failed_at": now.isoformat(),
        "started_at": now.isoformat(),
    }
    _run(fake_db[tga_outbound.OUTBOX_COLL].insert_one(doc))

    called = {"n": 0}
    async def _post(cfg, env):
        called["n"] += 1
        return {"status": "sent", "http_status": 200}
    monkeypatch.setattr(tga_outbound, "_post_envelope", _post)

    stats = _run(tga_outbound.retry_failed_outbox())
    assert stats["attempted"] == 0
    assert called["n"] == 0


def test_retry_after_24h_marks_permanent_and_writes_audit(
    fake_db, cfg_ok, empty_envelope, monkeypatch,
):
    # first_failed_at 25 saat önce → bu retry de başarısızsa alert.
    _seed_failed(
        fake_db, retry_count=5,
        first_failed_minutes_ago=25 * 60,
        next_retry_minutes_ago=1,
    )

    async def _post_fail(cfg, env):
        return {"status": "failed", "http_status": 502, "response_text": "bad gw"}
    monkeypatch.setattr(tga_outbound, "_post_envelope", _post_fail)

    stats = _run(tga_outbound.retry_failed_outbox())
    assert stats["alerted"] == 1
    assert stats["failed"] == 0

    doc = fake_db[tga_outbound.OUTBOX_COLL].docs[0]
    assert doc["status"] == "failed_permanent"
    assert doc["next_retry_at"] is None
    assert doc.get("alerted_at")

    # Audit log yazıldı mı?
    audit = fake_db.audit_logs.docs
    assert len(audit) == 1
    a = audit[0]
    assert a["action"] == "TGA_DELIVERY_FAILED"
    assert a["entity_type"] == "integration_tga"
    assert a["tenant_id"] == "t1"
    assert a["changes"]["retry_count"] == 6  # 5 + this attempt
    assert a["changes"]["age_hours"] >= 24.0
    assert a["changes"]["http_status"] == 502


def test_retry_skips_when_tenant_disabled(fake_db, empty_envelope, monkeypatch):
    _seed_failed(fake_db, retry_count=0)

    async def _get_cfg(tenant_id, *, decrypt_api_key=False):
        return {"enabled": False, "api_key_set": False}
    monkeypatch.setattr(tga_outbound, "get_tga_config", _get_cfg)

    stats = _run(tga_outbound.retry_failed_outbox())
    assert stats["skipped"] == 1
    assert stats["attempted"] == 1
    doc = fake_db[tga_outbound.OUTBOX_COLL].docs[0]
    assert doc["status"] == "failed_skipped"
    assert doc["next_retry_at"] is None
    # Observability — skipped audit yazılmalı.
    audit = fake_db.audit_logs.docs
    assert len(audit) == 1
    assert audit[0]["action"] == "TGA_DELIVERY_SKIPPED"


def test_retry_reschedules_on_transient_config_read_error(
    fake_db, empty_envelope, monkeypatch,
):
    """Config okuma istisna atarsa retry kalıcı olarak düşmemeli; backoff ile
    ertelenmeli ki vault/Mongo geri gelince devam edebilsin."""
    _seed_failed(fake_db, retry_count=0)

    async def _boom_cfg(tenant_id, *, decrypt_api_key=False):
        raise RuntimeError("vault unreachable")
    monkeypatch.setattr(tga_outbound, "get_tga_config", _boom_cfg)

    called = {"n": 0}
    async def _post(cfg, env):
        called["n"] += 1
        return {"status": "sent", "http_status": 200}
    monkeypatch.setattr(tga_outbound, "_post_envelope", _post)

    stats = _run(tga_outbound.retry_failed_outbox())
    assert stats["failed"] == 1
    assert stats["skipped"] == 0
    assert called["n"] == 0  # POST atılmadı
    doc = fake_db[tga_outbound.OUTBOX_COLL].docs[0]
    assert doc["status"] == "failed"
    assert doc["retry_count"] == 1
    assert doc["next_retry_at"] is not None
    assert doc["error"] == "config_unavailable"


def test_retry_reschedules_on_transient_missing_api_key(
    fake_db, empty_envelope, monkeypatch,
):
    """belge_no/vergi_no var ama api_key decrypt başarısız olmuş (None) ise
    intentionally_disabled değil — backoff ile yeniden denenmeli."""
    _seed_failed(fake_db, retry_count=2)

    async def _get_cfg(tenant_id, *, decrypt_api_key=False):
        return {
            "belge_no": "BLG-1", "vergi_no": "VRG-1",
            "environment": "test", "enabled": True,
            "api_key_set": True, "api_key": None,  # decrypt failed
        }
    monkeypatch.setattr(tga_outbound, "get_tga_config", _get_cfg)

    stats = _run(tga_outbound.retry_failed_outbox())
    assert stats["failed"] == 1
    assert stats["skipped"] == 0
    doc = fake_db[tga_outbound.OUTBOX_COLL].docs[0]
    assert doc["status"] == "failed"
    assert doc["retry_count"] == 3
    assert doc["error"] == "api_key_unavailable"
    assert doc["next_retry_at"] is not None
