"""Task #316 — Coklu-beat yarisinda gunde tek dispatch garantisini dogrula.

Saf birim testi: calisan backend / canli Mongo / Celery worker GEREKMEZ. Sahte yalniz
``_fresh_mongo`` (Motor I/O) ve per-tenant enqueue (``.delay``) noktasidir; dispatch
karar mantigi (``_autonomous_collection_dispatch_async``) gercek kod yolundan gecer.

Dogrulanan invariant'lar:
- Iki es zamanli (gather) dispatch ayni yerel gun icin TEK kez enqueue eder
  (kosullu CAS per-local-day claim ile).
- Ayni gun ikinci dispatch yeniden enqueue ETMEZ (per-day idempotency).
- ``autonomous_collection_runs`` uzerindeki unique index ensure edilemezse dispatch
  FAIL-CLOSED davranir: hicbir tenant kuyruga atilmaz (cift-charge zinciri acilmaz).

Atomik tek-kazanan dogrudan da test edilir: ayni yerel gun icin iki ardisik kosullu
CAS update_one yalnizca BIR kez ``modified_count == 1`` doner.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

import celery_tasks as ct

# Istanbul (UTC+3, DST yok) icin yerel saat 04:00 = UTC 01:00. Default
# AUTOCOLLECT_LOCAL_HOUR=4 / AUTOCOLLECT_LOCAL_MINUTE=0 ile eslesir.
PINNED_UTC = datetime(2026, 6, 27, 1, 0, 0, tzinfo=UTC)
TZ = "Europe/Istanbul"


# ───────────────────────────── in-memory Mongo ─────────────────────────────


class _Res:
    def __init__(self, matched=0, modified=0, upserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id


def _match(doc, flt):
    for k, cond in flt.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        actual = doc.get(k)
        if isinstance(cond, dict):
            for op, val in cond.items():
                if op == "$lt":
                    if not (actual is not None and actual < val):
                        return False
                else:  # pragma: no cover — beklenmeyen operator
                    raise NotImplementedError(op)
        elif actual != cond:
            return False
    return True


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    async def distinct(self, field, flt=None):
        flt = flt or {}
        seen: list = []
        for d in self.docs:
            if _match(d, flt):
                v = d.get(field)
                if v not in seen:
                    seen.append(v)
        return seen

    async def update_one(self, flt, update, upsert=False, session=None):
        # Mongo'nun belge-bazli atomikligini modeller: eslestirme + yazim,
        # diger coroutine'lere yield ETMEDEN tek parcada gerceklesir.
        for d in self.docs:
            if _match(d, flt):
                before = dict(d)
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                return _Res(matched=1, modified=int(d != before))
        if upsert:
            doc: dict = {}
            for k, v in flt.items():
                if k != "$or" and not isinstance(v, dict):
                    doc[k] = v
            for k, v in update.get("$set", {}).items():
                doc[k] = v
            for k, v in update.get("$setOnInsert", {}).items():
                doc[k] = v
            self.docs.append(doc)
            return _Res(matched=0, modified=0, upserted_id=doc.get("tenant_id"))
        return _Res(matched=0, modified=0)


class _RunsColl(_Coll):
    """``autonomous_collection_runs`` — unique index ensure davranisi togglelanir."""

    def __init__(self, *, index_ok=True):
        super().__init__()
        self.index_ok = index_ok
        self.index_calls = 0

    async def create_index(self, *a, **kw):
        self.index_calls += 1
        if not self.index_ok:
            raise RuntimeError("simulated: unique index ensure failed")
        return "autonomous_collection_runs_tenant_uq"


class _DB:
    def __init__(self, *, index_ok=True):
        self._colls: dict[str, _Coll] = {
            "autonomous_collection_runs": _RunsColl(index_ok=index_ok),
        }

    def _get(self, name):
        if name not in self._colls:
            self._colls[name] = _Coll()
        return self._colls[name]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._get(name)

    def __getitem__(self, name):
        return self._get(name)


class _Client:
    def close(self):
        pass


def _make_db(*, index_ok=True, tenants=("tenant-A", "tenant-B")):
    db = _DB(index_ok=index_ok)
    for t in tenants:
        db.users.docs.append({"tenant_id": t, "active": True})
        db.tenant_settings.docs.append({"tenant_id": t, "timezone": TZ})
    return db


@pytest.fixture
def patched(monkeypatch):
    """Pin wall clock + capture enqueue; return a factory that wires a fake DB."""
    monkeypatch.setattr(ct, "_now_utc", lambda: PINNED_UTC)
    calls: list[str] = []
    monkeypatch.setattr(
        ct.autonomous_collection_for_tenant, "delay", lambda tid: calls.append(tid)
    )

    def _wire(db):
        monkeypatch.setattr(ct, "_fresh_mongo", lambda: (_Client(), db))
        return db

    return _wire, calls


# ───────────────────────────────── tests ───────────────────────────────────


async def test_concurrent_dispatch_enqueues_once_per_tenant(patched):
    wire, calls = patched
    db = wire(_make_db(tenants=("tenant-A", "tenant-B")))

    # Iki beat ayni anda dispatch eder (coklu-beat / coklu-worker yarisi).
    res_a, res_b = await asyncio.gather(
        ct._autonomous_collection_dispatch_async(),
        ct._autonomous_collection_dispatch_async(),
    )

    assert res_a["success"] is True
    assert res_b["success"] is True
    # Iki tenant da yerel 04:00'te; her biri TAM bir kez kuyruga atilmali.
    assert sorted(calls) == ["tenant-A", "tenant-B"]
    # Toplam enqueue = iki beat arasinda yalniz biri her tenant'i claim eder.
    assert len(calls) == 2
    # Yalniz tek state dokumani (tenant basina) — claim atomik.
    runs = db.autonomous_collection_runs.docs
    assert sorted(r["tenant_id"] for r in runs) == ["tenant-A", "tenant-B"]
    assert all(r["last_auto_run_status"] == "dispatched" for r in runs)


async def test_second_same_day_dispatch_does_not_reenqueue(patched):
    wire, calls = patched
    db = wire(_make_db(tenants=("tenant-A",)))

    first = await ct._autonomous_collection_dispatch_async()
    assert first["queued"] == ["tenant-A"]

    # Ayni yerel gun ikinci tur: kosullu CAS modified=0 -> yeni enqueue YOK.
    second = await ct._autonomous_collection_dispatch_async()
    assert second["success"] is True
    assert second["queued"] == []
    assert calls == ["tenant-A"]


async def test_missing_unique_index_is_fail_closed(patched):
    wire, calls = patched
    db = wire(_make_db(index_ok=False, tenants=("tenant-A", "tenant-B")))

    res = await ct._autonomous_collection_dispatch_async()

    assert res["success"] is False
    assert res["error"] == "runs_index_unavailable"
    assert res["queued"] == []
    assert res["scanned"] == 0
    # Hicbir tenant kuyruga atilmadi; hatta state dokumani bile olusmadi.
    assert calls == []
    assert db.autonomous_collection_runs.docs == []
    assert db.autonomous_collection_runs.index_calls == 1


async def test_conditional_cas_claim_has_single_winner(patched):
    """Ayni yerel gun icin iki ardisik kosullu CAS yalniz bir kez modify eder."""
    wire, _calls = patched
    db = wire(_make_db(tenants=("tenant-A",)))
    runs = db.autonomous_collection_runs

    now_iso = PINNED_UTC.isoformat()
    # Yerel gun baslangici (Istanbul 00:00) UTC sinirindan once.
    boundary = datetime(2026, 6, 26, 21, 0, 0, tzinfo=UTC).isoformat()

    await runs.update_one(
        {"tenant_id": "tenant-A"},
        {"$setOnInsert": {"tenant_id": "tenant-A", "last_auto_run": None}},
        upsert=True,
    )

    cas_filter = {
        "tenant_id": "tenant-A",
        "$or": [{"last_auto_run": None}, {"last_auto_run": {"$lt": boundary}}],
    }
    first = await runs.update_one(
        cas_filter, {"$set": {"last_auto_run": now_iso, "last_auto_run_status": "dispatched"}}
    )
    second = await runs.update_one(
        cas_filter, {"$set": {"last_auto_run": now_iso, "last_auto_run_status": "dispatched"}}
    )

    assert first.modified_count == 1
    assert second.modified_count == 0
