"""Versiyonlu DB migration çerçevesi — birim sözleşmesi + ledger sabitleri.

Bu modül, sıralı/versiyonlu bir migration biriminin (``Migration``) sözleşmesini
ve ``schema_migrations`` defterinin (ledger) alan adlarını tanımlar.

Önemli teknik gerçek: MongoDB'de indeks/DDL işlemleri çok-belgeli bir ACID
transaction'a sarılamaz; bu yüzden "atomik rollback" şu anlama gelir — her
migration kendi ileri (``up``) ve geri (``down``) adımını tanımlar; runner bir
migration'ı yalnızca ``up()`` tamamen başarılıysa ledger'da ``applied`` olarak
işaretler, ``up()`` hata/timeout verirse aynı migration'ın ``down()`` adımını
çağırıp kısmi değişikliği geri alır ve fail-closed sinyali üretir.
"""

from __future__ import annotations

import hashlib
import inspect
from abc import ABC, abstractmethod

# ── Koleksiyon adları ────────────────────────────────────────────────
LEDGER_COLLECTION = "schema_migrations"
LOCK_COLLECTION = "schema_migration_locks"

# ── Ledger durumları ─────────────────────────────────────────────────
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"
STATUS_ROLLED_BACK = "rolled_back"


class Migration(ABC):
    """Tek bir versiyonlu migration biriminin sözleşmesi.

    Alt sınıflar şunları sağlamalı:
      - ``version``: sıralanabilir benzersiz kimlik, örn. ``"V001__add_x_index"``.
        Runner migration'ları bu alanın leksikografik sırasına göre uygular,
        bu yüzden sayısal kısım sıfır dolgulu olmalı (V001, V002, ...).
      - ``description``: insan-okur kısa açıklama.
      - ``up(db)``: ileri adım (indeks ekleme, veri dönüşümü, ...).
      - ``down(db)``: ``up()`` adımını geri alan adım (rollback).

    ``checksum()`` versiyon + açıklama + ``up``/``down`` kaynak kodundan türetilir;
    ledger'a yazılır ve uygulanmış bir migration'ın kodu sonradan değişirse bunu
    görünür kılar (drift tespiti).
    """

    #: Sıralanabilir benzersiz versiyon kimliği (örn. "V001__add_x_index").
    version: str = ""
    #: İnsan-okur kısa açıklama.
    description: str = ""

    @abstractmethod
    async def up(self, db) -> None:
        """İleri adım. Hata/timeout fırlatırsa runner ``down()`` çağırır."""
        raise NotImplementedError

    @abstractmethod
    async def down(self, db) -> None:
        """Geri adım (rollback). ``up()`` ile yapılan değişikliği geri alır."""
        raise NotImplementedError

    def checksum(self) -> str:
        """Versiyon + açıklama + up/down kaynak kodundan SHA-256 türetir."""
        try:
            up_src = inspect.getsource(self.up.__func__)  # type: ignore[attr-defined]
            down_src = inspect.getsource(self.down.__func__)  # type: ignore[attr-defined]
        except (OSError, TypeError, AttributeError):
            up_src = down_src = ""
        payload = "\n".join([self.version, self.description, up_src, down_src])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Migration {self.version}: {self.description!r}>"
