"""V001 — pms_audit_trail (tenant_id, action, timestamp) bileşik indeksi.

Çerçeveyi kanıtlayan gerçek örnek migration. ``up()`` yeni bir indeks ekler;
``down()`` onu düşürür. İndeks adı (``mig_v001_audit_action_ts``) ve anahtar
kombinasyonu mevcut hiçbir indeksle çakışmaz (pms_audit_trail üzerindeki tek
mevcut indeks ``idx_audit_entity`` = (tenant_id, entity_id, timestamp)).

İkinci açılışta tekrar koşmaz: runner ledger'da ``applied`` olanları atlar.
"""

from __future__ import annotations

from ..base import Migration

INDEX_NAME = "mig_v001_audit_action_ts"
COLLECTION = "pms_audit_trail"


class AddAuditActionIndex(Migration):
    version = "V001__add_audit_action_index"
    description = "pms_audit_trail üzerinde (tenant_id, action, timestamp) bileşik indeksi — action'a göre denetim sorgularını hızlandırır"

    async def up(self, db) -> None:
        await db[COLLECTION].create_index(
            [("tenant_id", 1), ("action", 1), ("timestamp", -1)],
            name=INDEX_NAME,
            background=True,
        )

    async def down(self, db) -> None:
        try:
            await db[COLLECTION].drop_index(INDEX_NAME)
        except Exception as exc:  # noqa: BLE001
            # İndeks zaten yoksa (up() onu hiç oluşturamadan başarısız olduysa)
            # rollback başarılı sayılır — düşürülecek bir şey yok.
            msg = str(exc).lower()
            if "index not found" in msg or "not found" in msg:
                return
            raise


MIGRATION = AddAuditActionIndex()
