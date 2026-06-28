"""Mukerrer kullanici e-postasi (duplicate `_hash_email`) temizligi.

Background
----------
E-posta sifreli saklanir; tekillik DETERMINISTIK blind-index ``_hash_email``
(HMAC-SHA256, normalize edilmis e-posta) uzerinden saglanir. Uretim zirhi
olarak ``users`` koleksiyonuna ``uniq_users_hash_email`` (partial-unique)
indeksi eklendi. Ancak bu indeks, koleksiyonda ZATEN mukerrer ``_hash_email``
varsa kurulamaz (E11000) — gecmiste yasanmis yaris/cift-insert kaynakli
"enkaz" hesaplar indeksi bloke eder.

Bu script o engeli kaldirir: ayni ``_hash_email`` degerine sahip kullanici
gruplarini bulur, her grupta EN ESKI (OLDEST) hesabi otorite kabul eder ve
geri kalan mukerrer fazlalıkları siler. Boylece indeks bir sonraki backend
restart'inda (bootstrap d_perf -> DatabaseOptimizer) temiz kurulur.

Safety contract (fail-closed, cift opt-in)
------------------------------------------
* Mongo baglantisi yoksa (MONGO_URL / MONGO_ATLAS_URI) script reddeder.
* Varsayilan ``--apply``: KAPALI (dry-run). Silme yapmak icin HEM ``--apply``
  HEM de ``ALLOW_USER_DEDUPE=true`` env gerekir (cift opt-in).
* Yalniz ``_hash_email`` (string) tasiyan dokumanlar dikkate alinir.
* Her grupta otorite olarak (created_at, _id) en kucugu (en eski) secilir;
  ``_id`` tie-break sayesinde ayni saniyede olusan kayitlar bile deterministik
  cozulur. Otorite ASLA silinmez; her gruptan tam olarak 1 hesap korunur.
* Blast-radius kapani: toplam silinecek kayit ``--max-deletes`` (vars. 100)
  esigini asarsa script durur (beklenmedik kitlesel silme korumasi).
* Silinen her ``users`` kaydinin ``id``'sine bagli ``staff_members`` ozluk
  kaydi da (tenant-scoped) silinir; orphan ozluk birakilmaz.
* PII yazilmaz: log'da yalniz hash son-eki, tenant/id on-eki, role, created_at.
* Her calisma ``user_dedupe_scans`` koleksiyonuna ozet metrik dokumani yazar.

Usage
-----
    # Varsayilan: dry-run, listele, hicbir yazma yok
    python -m scripts.cleanup_duplicate_user_emails

    # Uygula (ALLOW_USER_DEDUPE=true env zorunlu)
    ALLOW_USER_DEDUPE=true python -m scripts.cleanup_duplicate_user_emails --apply
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Mongo: script start.sh disinda kosabilir; MONGO_URL yoksa MONGO_ATLAS_URI'ye
# dus (conftest ile ayni kaynak). Secret CLI'a YAZILMAZ; yalniz env'de kalir.
if not os.environ.get("MONGO_URL"):
    _atlas = os.environ.get("MONGO_ATLAS_URI")
    if _atlas:
        os.environ["MONGO_URL"] = _atlas
        os.environ.setdefault("DB_NAME", "syroce-pms")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.database import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cleanup_duplicate_user_emails")


def _sort_key(doc: dict) -> tuple:
    """Deterministik 'en eski' anahtari: (created_at, _id).

    created_at ISO string ya da BSON datetime olabilir; eksikse asla en eski
    secilmesin diye buyuk bir sentinel verilir. _id (ObjectId) tie-break:
    ayni created_at'te ilk insert edilen kazanir.
    """
    ca = doc.get("created_at")
    if isinstance(ca, str):
        ca_key = ca
    elif hasattr(ca, "isoformat"):
        ca_key = ca.isoformat()
    else:
        ca_key = "9999-12-31T23:59:59"
    return (ca_key, str(doc.get("_id", "")))


async def scan() -> list[dict]:
    """Ayni `_hash_email` degerine sahip (count>1) kullanici gruplarini dondur."""
    pipeline = [
        {"$match": {"_hash_email": {"$type": "string"}}},
        {"$group": {"_id": "$_hash_email", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    groups: list[dict] = []
    async for g in db.users.aggregate(pipeline):
        h = g["_id"]
        docs = await db.users.find(
            {"_hash_email": h},
            {"_id": 1, "id": 1, "tenant_id": 1, "role": 1, "active": 1, "created_at": 1},
        ).to_list(length=1000)
        docs.sort(key=_sort_key)
        authority = docs[0]
        victims = docs[1:]
        groups.append({"hash": h, "authority": authority, "victims": victims})
    return groups


def _report(groups: list[dict]) -> int:
    total_victims = 0
    for g in groups:
        a = g["authority"]
        logger.info(
            "GRUP hash=...%s | toplam=%d | KORUNAN id=%s tenant=%s role=%s created=%s",
            g["hash"][-8:],
            len(g["victims"]) + 1,
            str(a.get("id"))[:12],
            str(a.get("tenant_id"))[:12],
            a.get("role"),
            str(a.get("created_at"))[:19],
        )
        for v in g["victims"]:
            total_victims += 1
            logger.info(
                "    SILINECEK id=%s tenant=%s role=%s created=%s",
                str(v.get("id"))[:12],
                str(v.get("tenant_id"))[:12],
                v.get("role"),
                str(v.get("created_at"))[:19],
            )
    return total_victims


async def apply(groups: list[dict]) -> dict:
    deleted_users = 0
    deleted_staff = 0
    for g in groups:
        authority_id = g["authority"].get("id")
        for v in g["victims"]:
            vid = v.get("id")
            tid = v.get("tenant_id")
            if not vid or vid == authority_id:
                # Guard: otorite asla silinmez.
                continue
            res_u = await db.users.delete_one({"id": vid, "_hash_email": g["hash"]})
            deleted_users += res_u.deleted_count
            res_s = await db.staff_members.delete_many({"user_id": vid, "tenant_id": tid})
            deleted_staff += res_s.deleted_count
    return {"deleted_users": deleted_users, "deleted_staff": deleted_staff}


async def main() -> int:
    parser = argparse.ArgumentParser(description="Mukerrer kullanici e-postasi temizligi")
    parser.add_argument("--apply", action="store_true", help="Silmeyi uygula (ALLOW_USER_DEDUPE=true gerekir)")
    parser.add_argument("--max-deletes", type=int, default=100, help="Blast-radius kapani (vars. 100)")
    args = parser.parse_args()

    if not os.environ.get("MONGO_URL"):
        logger.error("MONGO_URL/MONGO_ATLAS_URI yok — baglanti reddedildi (fail-closed).")
        return 2

    groups = await scan()
    if not groups:
        logger.info("Mukerrer `_hash_email` grubu YOK — temiz. Unique index kurulmaya hazir.")
        return 0

    total_victims = _report(groups)
    logger.info("OZET: %d grup, %d silinecek mukerrer hesap.", len(groups), total_victims)

    if total_victims > args.max_deletes:
        logger.error(
            "BLAST-RADIUS: silinecek (%d) > --max-deletes (%d). Durduruldu (fail-closed).",
            total_victims,
            args.max_deletes,
        )
        return 3

    mode = "dry-run"
    applied = {"deleted_users": 0, "deleted_staff": 0}
    if args.apply:
        if os.environ.get("ALLOW_USER_DEDUPE") != "true":
            logger.error("--apply icin ALLOW_USER_DEDUPE=true env zorunlu (cift opt-in). Durduruldu.")
            return 4
        applied = await apply(groups)
        mode = "apply"
        logger.info(
            "UYGULANDI: %d kullanici, %d ozluk kaydi silindi.",
            applied["deleted_users"],
            applied["deleted_staff"],
        )
        # Dogrulama: kalan mukerrer grup olmamali.
        remaining = await scan()
        if remaining:
            logger.error("UYARI: %d mukerrer grup HALA var — manuel inceleme gerek.", len(remaining))
        else:
            logger.info("Dogrulandi: kalan mukerrer grup YOK. Index kurulmaya hazir.")
    else:
        logger.info("DRY-RUN: hicbir yazma yapilmadi. Uygulamak icin: ALLOW_USER_DEDUPE=true ... --apply")

    try:
        await db.user_dedupe_scans.insert_one(
            {
                "ts": datetime.now(UTC).isoformat(),
                "mode": mode,
                "groups": len(groups),
                "victims_found": total_victims,
                "deleted_users": applied["deleted_users"],
                "deleted_staff": applied["deleted_staff"],
            }
        )
    except Exception as e:
        logger.warning("Metrik kaydi yazilamadi (kritik degil): %s", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
