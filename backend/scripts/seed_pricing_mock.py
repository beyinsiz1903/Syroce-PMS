"""Gölge (shadow) koşusu için competitor_rates tohumlama — yalnız pilot tenant.

Amac
----
RevenueAutopilot ilk tam-kapsamli gölge döngüsünde rakip-analiz (competitor
matching) blogunu da calistirabilsin diye ``competitor_rates`` koleksiyonuna
GERCEKCI ama SAHTE (mock) rakip fiyatlari yazar. Taban fiyatlar pilot otelin
ZATEN gercek olan ``rooms.base_price`` degerlerinden turetilir; bu betik
``rooms``'a / ``base_price``'a ASLA dokunmaz (salt-okunur referans).

Doktrin / guvenlik sozlesmesi
-----------------------------
* YALNIZ pilot tenant (PILOT_DEFAULT). Varsayilan budur; ``--tenant`` /
  ``SHADOW_SEED_TENANT_ID`` ile baska bir tenant verilirse betik fail-closed
  REDDEDER. Pilot-disi bir tenant'a bilincli yazim YALNIZCA acik
  ``ALLOW_NON_PILOT_SHADOW_SEED=true`` opt-in'i ile mumkundur (cift-onay).
  Tenant_id bos ise fail-closed (cikar).
* Tum yazilan dokumanlar ``source='shadow_seed'`` etiketlidir → tek sorguyla
  geri alinabilir (``--purge``). Uretim verisi (gercek competitor_rates,
  source alani olmayan) ASLA silinmez/degistirilmez.
* Idempotent: ``seed`` once bu tenant'in tum ``shadow_seed`` kayitlarini siler,
  sonra BUGUNun tarihiyle yeniden yazar (tekrar calistir → cift kayit yok).
* PII yazilmaz/loglanmaz.

Uretilen veri (her iki kod yolunu test eder)
-------------------------------------------
* room_type'a ESLENMIS rakip fiyatlari (tipe-ozel branch) — son 2 oda tipi
  HARIC tum tipler icin, o tipin gercek ort. base_price'ina gore 2 rakip.
* GENEL (room_type'siz) rakip fiyatlari — genel-ortalama fallback branch'i
  test etsin diye (tipe-ozel rakibi olmayan o 2 tip buraya duser).

Kullanim
--------
    # On-izleme (dry-run, yazma yok)
    DB_NAME=syroce-pms python -m scripts.seed_pricing_mock

    # Uygula (pilot tenant)
    DB_NAME=syroce-pms python -m scripts.seed_pricing_mock --apply

    # Geri al (bu tenant'in TUM shadow_seed kayitlarini sil)
    DB_NAME=syroce-pms python -m scripts.seed_pricing_mock --purge --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient

PILOT_DEFAULT = "23377306-a501-4232-adc8-8aea50e243c0"
SEED_SOURCE = "shadow_seed"

# Tipe-ozel rakip fiyat carpanlari (o tipin gercek ort. base_price'ina gore)
TYPE_MULTIPLIERS = (0.96, 1.07)
# Genel (room_type'siz) rakip fiyat carpanlari (tum tiplerin genel ort.'sina gore)
GLOBAL_MULTIPLIERS = (0.98, 1.06)
# Genel-fallback branch'ini test etmek icin tipe-ozel rakipsiz birakilacak tip sayisi
LEAVE_FOR_GLOBAL = 2


def _enforce_pilot(tenant_id: str | None) -> str:
    """Fail-closed pilot guard: yalniz PILOT_DEFAULT'a yazima izin ver.

    Pilot-disi tenant YALNIZCA acik ``ALLOW_NON_PILOT_SHADOW_SEED=true`` ile
    gecer (cift-onay). Bos tenant veya guard ihlali -> ``SystemExit`` (fail-closed),
    boylece uretim Atlas uzerinde yanlis-tenant kirletme blast-radius'u 0 kalir.
    """
    tid = (tenant_id or "").strip()
    if not tid:
        raise SystemExit("FAIL-CLOSED: tenant_id bos. --tenant veya SHADOW_SEED_TENANT_ID gerekli.")
    allow_non_pilot = os.environ.get("ALLOW_NON_PILOT_SHADOW_SEED", "false").lower() == "true"
    if tid != PILOT_DEFAULT and not allow_non_pilot:
        raise SystemExit(
            f"FAIL-CLOSED: yalniz pilot tenant ({PILOT_DEFAULT}) tohumlanabilir. "
            f"Verilen tenant ({tid}) pilot degil. Bilincli istisna icin "
            "ALLOW_NON_PILOT_SHADOW_SEED=true gerekli."
        )
    return tid


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _mongo():
    url = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")
    if not url:
        print("FAIL-CLOSED: MONGO_URL/MONGO_ATLAS_URI tanimli degil.", file=sys.stderr)
        sys.exit(2)
    db_name = os.environ.get("DB_NAME", "syroce-pms")
    return AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000), db_name


async def _per_type_avg_base(db, tenant_id: str) -> list[tuple[str, float]]:
    """Pilotun GERCEK base_price'larindan oda-tipi -> ort. taban fiyat (salt-okunur)."""
    rows = await db.rooms.aggregate([
        {"$match": {"tenant_id": tenant_id, "base_price": {"$gt": 0}}},
        {"$group": {"_id": "$room_type", "avg": {"$avg": "$base_price"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(10000)
    out = []
    for r in rows:
        rt = r.get("_id")
        avg = r.get("avg")
        if rt and avg and avg > 0:
            out.append((str(rt), round(float(avg), 2)))
    return out


def _build_docs(tenant_id: str, per_type: list[tuple[str, float]]) -> list[dict]:
    today = _today()
    now_iso = datetime.now(UTC).isoformat()
    docs: list[dict] = []

    def _doc(name, rate, room_type=None):
        d = {
            "tenant_id": tenant_id,
            "date": today,
            "competitor_name": name,
            "rate": round(float(rate), 2),
            "source": SEED_SOURCE,
            "created_at": now_iso,
            "note": "GOLGE KOSUSU mock rakip verisi (gercek degildir) — geri alinabilir",
        }
        if room_type is not None:
            d["room_type"] = room_type
        return d

    # Tipe-ozel rakipler (genel-fallback testi icin son LEAVE_FOR_GLOBAL tip haric)
    type_specific = per_type[:-LEAVE_FOR_GLOBAL] if len(per_type) > LEAVE_FOR_GLOBAL else per_type
    for room_type, base_avg in type_specific:
        for i, m in enumerate(TYPE_MULTIPLIERS, start=1):
            docs.append(_doc(f"SHADOW-MOCK Rakip {i}", base_avg * m, room_type=room_type))

    # Genel (room_type'siz) rakipler — tipe-ozel rakibi olmayan tipler buraya duser
    overall_avg = round(sum(b for _, b in per_type) / len(per_type), 2) if per_type else 0.0
    if overall_avg > 0:
        for i, m in enumerate(GLOBAL_MULTIPLIERS, start=1):
            docs.append(_doc(f"SHADOW-MOCK Pazar {i}", overall_avg * m))
    return docs


async def main():
    ap = argparse.ArgumentParser(description="Golge kosusu icin competitor_rates tohumlama (yalniz pilot).")
    ap.add_argument("--tenant", default=os.environ.get("SHADOW_SEED_TENANT_ID") or PILOT_DEFAULT)
    ap.add_argument("--apply", action="store_true", help="Gercekten yaz/sil (varsayilan: dry-run).")
    ap.add_argument("--purge", action="store_true", help="Bu tenant'in TUM shadow_seed kayitlarini sil ve cik.")
    args = ap.parse_args()

    tenant_id = _enforce_pilot(args.tenant)

    client, db_name = _mongo()
    db = client[db_name]
    try:
        existing = await db.competitor_rates.count_documents(
            {"tenant_id": tenant_id, "source": SEED_SOURCE}
        )
        print(f"DB={db_name} tenant={tenant_id}")
        print(f"mevcut shadow_seed kayit: {existing}")

        if args.purge:
            if not args.apply:
                print(f"[DRY-RUN] {existing} shadow_seed kaydi SILINECEK (--apply ile uygula).")
                return
            res = await db.competitor_rates.delete_many(
                {"tenant_id": tenant_id, "source": SEED_SOURCE}
            )
            print(f"PURGE: {res.deleted_count} shadow_seed kaydi silindi.")
            return

        per_type = await _per_type_avg_base(db, tenant_id)
        if not per_type:
            print("FAIL-CLOSED: gercek base_price (oda) bulunamadi; tohumlama yapilmaz.", file=sys.stderr)
            sys.exit(3)
        docs = _build_docs(tenant_id, per_type)
        n_type = sum(1 for d in docs if "room_type" in d)
        n_global = sum(1 for d in docs if "room_type" not in d)
        rtypes = sorted({d["room_type"] for d in docs if "room_type" in d})
        print(f"oda tipi (base_price>0): {len(per_type)} | tipe-ozel rakip dok: {n_type} ({len(rtypes)} tip) | genel rakip dok: {n_global}")
        sample = docs[0] if docs else None
        print(f"ornek dok: {sample}")

        if not args.apply:
            print(f"[DRY-RUN] {len(docs)} dokuman YAZILACAK (once {existing} eski shadow_seed silinir). --apply ile uygula.")
            return

        deleted = await db.competitor_rates.delete_many(
            {"tenant_id": tenant_id, "source": SEED_SOURCE}
        )
        ins = await db.competitor_rates.insert_many(docs)
        print(f"APPLY: {deleted.deleted_count} eski shadow_seed silindi, {len(ins.inserted_ids)} yeni kayit yazildi (date={_today()}).")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
