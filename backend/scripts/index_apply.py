"""R5: Eksik index'leri ekle (audit raporundan).

Sadece doc sayısı > 0 veya startup'ta sorgulanan koleksiyonlara ekler.
Boş koleksiyonlar Atlas 500 koleksiyon limit'i nedeniyle atlanır.

Entry formatı geriye-uyumlu olarak iki biçimi destekler:
  (collection, keys)                         -> isimsiz, opsiyonsuz (varsayılan)
  (collection, keys, name, options)          -> explicit index adı + create
                                                options (ör. {"unique": True})
``name`` verildiğinde index, ``bootstrap/phases/perf_indexes.py`` ile AYNI ada
sahip olmalıdır; aksi halde operatör bu script'i boot öncesi koşunca Mongo iki
ayrı index oluşturur (name drift). Bu yüzden buraya eklenen kalıcı index'ler
perf_indexes.py'deki adlarıyla birebir aynı yazılır.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MONGO_URL = (
    os.environ.get("MONGO_URL")
    or os.environ.get("MONGO_ATLAS_URI")
    or "mongodb://localhost:27017"
)
DB_NAME = os.environ.get("DB_NAME", "syroce-pms")

# Sadece koleksiyonu mevcut + indekslemesi anlamlı olanlar
TO_APPLY = [
    ("audit_logs", [("tenant_id", 1), ("created_at", -1)]),
    ("payments", [("tenant_id", 1), ("payment_date", -1)]),
    ("exely_connections", [("tenant_id", 1), ("is_active", 1)]),
    ("hotelrunner_connections", [("tenant_id", 1), ("is_active", 1)]),
    # Atlas Performance Advisor (2026-06-14): missing (tenant_id, id) companion
    # on folios (~51 q/h) and folio_charges — single-doc lookups by app-level
    # `id` were doing tenant-wide COLLSCANs. Also declared durably in
    # bootstrap/phases/perf_indexes.py; this lets the operator apply them
    # immediately without a full boot.
    ("folios", [("tenant_id", 1), ("id", 1)]),
    ("folio_charges", [("tenant_id", 1), ("id", 1)]),
    # Atlas Query Targeting (2026-06-17): channel_reconciliation_cases global
    # (cross-tenant) ops-health shapes from monitoring/aggregator.py
    # collect_reconciliation_health() — {status:{$in:[open,acknowledged]}} +
    # count_documents({created_at:{$gte:24h}}). No tenant-leading index serves
    # them, so they COLLSCANned ~7.3k docs. Names match perf_indexes.py exactly
    # (idx_recon_cases_status_global / idx_recon_cases_created_global) so an
    # immediate apply here and a later boot never create duplicates.
    ("channel_reconciliation_cases", [("status", 1)],
     "idx_recon_cases_status_global", {}),
    ("channel_reconciliation_cases", [("created_at", 1)],
     "idx_recon_cases_created_global", {}),
    # POS F&B sicak okuma yollari (2026-06-18): pos_orders / pos_transactions
    # read-path tenant compound index'leri. Adlar bootstrap/phases/
    # perf_indexes.py ile BIREBIR ayni -> operator hemen uygularsa ve sonra boot
    # calisirsa duplicate olusmaz. (tenant_id, id) girisleri 2-tuple: default ad
    # "tenant_id_1_id_1" ile uyumlu. Gerekce + cagri yerleri perf_indexes.py'de.
    ("pos_orders", [("tenant_id", 1), ("status", 1), ("created_at", 1)],
     "idx_pos_orders_status_created", {}),
    ("pos_orders", [("tenant_id", 1), ("created_at", 1)],
     "idx_pos_orders_tenant_created", {}),
    ("pos_orders", [("tenant_id", 1), ("id", 1)]),
    ("pos_transactions", [("tenant_id", 1), ("id", 1)]),
    ("pos_transactions", [("tenant_id", 1), ("order_id", 1)],
     "idx_pos_txn_tenant_order", {}),
    ("pos_transactions",
     [("tenant_id", 1), ("outlet_id", 1), ("table_number", 1)],
     "idx_pos_txn_open_tab",
     {"partialFilterExpression": {"status": "open"}}),
    # Task #315 — Otonom tahsilat exactly-once invariant index'leri. Adlar
    # bootstrap/phases/perf_indexes.py ile BIREBIR ayni -> operator hemen
    # uygularsa ve sonra boot calisirsa duplicate olusmaz (name drift yok).
    # autonomous_collection_runs (tenant_id) unique: coklu-beat dispatch tek-
    # kazanan CAS'inin dayanagi. autonomous_collection_jobs (tenant_id,
    # booking_id, charge_kind) unique: kuyruk satir-tekligi. Bos koleksiyonlar
    # estimated_document_count==0 ise Atlas 500 limiti icin atlanir; worker bir
    # kez kostuktan sonra dolar ve apply onlari indeksler.
    ("autonomous_collection_runs", [("tenant_id", 1)],
     "autonomous_collection_runs_tenant_uq", {"unique": True}),
    ("autonomous_collection_jobs",
     [("tenant_id", 1), ("booking_id", 1), ("charge_kind", 1)],
     "autocollect_jobs_uq", {"unique": True}),
]


def _normalize(entry):
    """Accept (col, keys) or (col, keys, name, options) uniformly."""
    if len(entry) == 2:
        col, keys = entry
        return col, keys, None, {}
    col, keys, name, options = entry
    return col, keys, name, options or {}


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    print(f"DB: {DB_NAME}\n")

    for entry in TO_APPLY:
        col, keys, name, options = _normalize(entry)
        try:
            cnt = await db[col].estimated_document_count()
            existing = await db[col].list_indexes().to_list(50)
            existing_keys = [tuple(i["key"].keys()) for i in existing]
            want = tuple(k for k, _ in keys)

            covered = any(
                len(ex) >= len(want) and tuple(ex[: len(want)]) == want
                for ex in existing_keys
            )
            if covered:
                print(f"  {col} ({cnt} doc): zaten kapsanmis, atlandi")
                continue

            kwargs = {"background": True, **options}
            if name:
                kwargs["name"] = name
            created = await db[col].create_index(keys, **kwargs)
            print(f"  {col} ({cnt} doc): index olusturuldu -> {created}")
        except Exception as e:
            print(f"  {col}: HATA -> {str(e)[:80]}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
