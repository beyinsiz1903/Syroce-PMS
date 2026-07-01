"""Versiyonlu DB migration çerçevesi testleri (Task #398).

Gerçek MongoDB gerektirir (mongomock yüklü değil). Bağlanılamazsa testler
atlanır. Her test atılabilir (throwaway) bir veritabanı kullanır ve sonunda
düşürür; pilot/üretim verisine dokunmaz.

Doğrulananlar:
  - Sıralı uygulama (versiyon sırasına göre).
  - Idempotency: ikinci koşuda applied olanlar atlanır (up tekrar çağrılmaz).
  - up() hatası → aynı migration'ın down() çağrılır, ledger rolled_back/failed,
    runner MigrationError fırlatır (fail-closed), kısmi indeks geri alınır.
  - Per-migration timeout → down() + rolled_back + raise.
  - Advisory lock: iki runner aynı anda koşunca migration tek kez uygulanır.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - motor always present in backend
    AsyncIOMotorClient = None  # type: ignore

from bootstrap.migrations.base import (
    LEDGER_COLLECTION,
    STATUS_APPLIED,
    STATUS_FAILED,
    STATUS_ROLLED_BACK,
    Migration,
)
from bootstrap.migrations.runner import MigrationError, run_migrations

pytestmark = pytest.mark.asyncio

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


async def _mongo_or_skip():
    """Gerçek Mongo'ya bağlan; erişilemezse testi atla."""
    if AsyncIOMotorClient is None:
        pytest.skip("motor yüklü değil")
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=1500)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"MongoDB erişilemez ({MONGO_URL})")
    return client


@pytest.fixture
async def throwaway_db():
    """Atılabilir bir veritabanı sağlar ve sonunda düşürür."""
    client = await _mongo_or_skip()
    db_name = f"test_migrations_{uuid.uuid4().hex[:12]}"
    db = client[db_name]
    try:
        yield db
    finally:
        await client.drop_database(db_name)
        client.close()


# ── Test yardımcı migration'ları ─────────────────────────────────────

class _RecordingMigration(Migration):
    """up/down çağrılarını sayan, indeks ekleyen/düşüren migration."""

    def __init__(self, version: str, coll: str, index_name: str):
        self._version = version
        self.description = f"test migration {version}"
        self._coll = coll
        self._index_name = index_name
        self.up_calls = 0
        self.down_calls = 0

    @property
    def version(self) -> str:  # type: ignore[override]
        return self._version

    @version.setter
    def version(self, v):  # base sınıf class-attr; örnekte property kullanıyoruz
        self._version = v

    async def up(self, db) -> None:
        self.up_calls += 1
        await db[self._coll].create_index(
            [("tenant_id", 1), (f"f_{self._version}", 1)],
            name=self._index_name,
        )

    async def down(self, db) -> None:
        self.down_calls += 1
        try:
            await db[self._coll].drop_index(self._index_name)
        except Exception:
            pass


class _FailingUpMigration(Migration):
    """up() yarıda bir indeks oluşturur sonra patlar; down() temizler."""

    def __init__(self, version: str, coll: str, index_name: str):
        self._version = version
        self.description = f"failing migration {version}"
        self._coll = coll
        self._index_name = index_name
        self.up_calls = 0
        self.down_calls = 0

    @property
    def version(self) -> str:  # type: ignore[override]
        return self._version

    async def up(self, db) -> None:
        self.up_calls += 1
        # Kısmi değişiklik: indeksi oluştur, sonra hata fırlat.
        await db[self._coll].create_index(
            [("tenant_id", 1), (f"f_{self._version}", 1)],
            name=self._index_name,
        )
        raise RuntimeError("kasıtlı up hatası")

    async def down(self, db) -> None:
        self.down_calls += 1
        await db[self._coll].drop_index(self._index_name)


class _SlowUpMigration(Migration):
    """Timeout testi: up() uzun sürer."""

    def __init__(self, version: str):
        self._version = version
        self.description = f"slow migration {version}"
        self.down_calls = 0

    @property
    def version(self) -> str:  # type: ignore[override]
        return self._version

    async def up(self, db) -> None:
        await asyncio.sleep(5)

    async def down(self, db) -> None:
        self.down_calls += 1


async def _index_names(db, coll: str) -> set[str]:
    return set((await db[coll].index_information()).keys())


# ── Testler ──────────────────────────────────────────────────────────

async def test_sequential_apply_in_version_order(throwaway_db):
    db = throwaway_db
    coll = "mig_test_seq"
    m1 = _RecordingMigration("V001", coll, "mig_seq_v001")
    m2 = _RecordingMigration("V002", coll, "mig_seq_v002")
    # Sırasız ver; runner versiyon sırasına göre uygulamalı.
    result = await run_migrations(db, migrations=[m2, m1])

    assert result["status"] == "applied"
    assert result["applied"] == ["V001", "V002"]
    assert m1.up_calls == 1 and m2.up_calls == 1

    names = await _index_names(db, coll)
    assert "mig_seq_v001" in names and "mig_seq_v002" in names

    ledger = [d async for d in db[LEDGER_COLLECTION].find({})]
    statuses = {d["version"]: d["status"] for d in ledger}
    assert statuses == {"V001": STATUS_APPLIED, "V002": STATUS_APPLIED}
    for d in ledger:
        assert d["checksum"]
        assert d["applied_at"]
        assert d["duration_ms"] >= 0


async def test_idempotent_skip_applied(throwaway_db):
    db = throwaway_db
    coll = "mig_test_idem"
    m1 = _RecordingMigration("V001", coll, "mig_idem_v001")

    r1 = await run_migrations(db, migrations=[m1])
    assert r1["applied"] == ["V001"]
    assert m1.up_calls == 1

    # İkinci koşu: applied olduğu için up TEKRAR çağrılmamalı.
    r2 = await run_migrations(db, migrations=[m1])
    assert r2["status"] == "up_to_date"
    assert r2["applied"] == []
    assert m1.up_calls == 1  # değişmedi


async def test_up_failure_triggers_down_and_fail_closed(throwaway_db):
    db = throwaway_db
    coll = "mig_test_fail"
    bad = _FailingUpMigration("V001", coll, "mig_fail_v001")

    with pytest.raises(MigrationError):
        await run_migrations(db, migrations=[bad])

    # down() çağrıldı, kısmi indeks geri alındı.
    assert bad.up_calls == 1
    assert bad.down_calls == 1
    names = await _index_names(db, coll)
    assert "mig_fail_v001" not in names

    # Ledger rolled_back, hata kaydı var, applied DEĞİL.
    doc = await db[LEDGER_COLLECTION].find_one({"version": "V001"})
    assert doc is not None
    assert doc["status"] == STATUS_ROLLED_BACK
    assert doc["error"]
    assert doc["status"] != STATUS_APPLIED


async def test_failure_stops_subsequent_migrations(throwaway_db):
    db = throwaway_db
    coll = "mig_test_stop"
    bad = _FailingUpMigration("V001", coll, "mig_stop_v001")
    after = _RecordingMigration("V002", coll, "mig_stop_v002")

    with pytest.raises(MigrationError):
        await run_migrations(db, migrations=[bad, after])

    # V001 patladı → V002 hiç çalışmamalı (fail-closed, sıralı durur).
    assert after.up_calls == 0
    doc2 = await db[LEDGER_COLLECTION].find_one({"version": "V002"})
    assert doc2 is None


async def test_per_migration_timeout_rolls_back(throwaway_db):
    db = throwaway_db
    slow = _SlowUpMigration("V001")

    with pytest.raises(MigrationError):
        await run_migrations(db, migrations=[slow], per_migration_timeout=0.2)

    assert slow.down_calls == 1
    doc = await db[LEDGER_COLLECTION].find_one({"version": "V001"})
    assert doc is not None
    assert doc["status"] in (STATUS_ROLLED_BACK, STATUS_FAILED)
    assert "timeout" in (doc.get("error") or "").lower()


async def test_advisory_lock_single_run_under_concurrency(throwaway_db):
    db = throwaway_db
    coll = "mig_test_lock"

    # İki ayrı runner aynı anda; her biri kendi migration örneğini alır ama
    # aynı versiyon → ledger'da tek applied olmalı, up bir kez çalışmalı.
    m_a = _RecordingMigration("V001", coll, "mig_lock_v001")
    m_b = _RecordingMigration("V001", coll, "mig_lock_v001")

    results = await asyncio.gather(
        run_migrations(db, migrations=[m_a]),
        run_migrations(db, migrations=[m_b]),
        return_exceptions=True,
    )
    # Hiçbiri exception fırlatmamalı.
    for r in results:
        assert not isinstance(r, Exception), r

    total_up = m_a.up_calls + m_b.up_calls
    assert total_up == 1, f"migration çift koştu: up_calls toplam={total_up}"

    # Ledger'da tek applied kayıt.
    docs = [d async for d in db[LEDGER_COLLECTION].find({"version": "V001"})]
    assert len(docs) == 1
    assert docs[0]["status"] == STATUS_APPLIED

    statuses = {r["status"] for r in results}
    # Biri uyguladı (applied), diğeri ya kilit nedeniyle atladı ya da
    # up_to_date gördü (kilidi alan bitirip bırakınca).
    assert "applied" in statuses
