"""R5: Eksik index'leri ekle (audit raporundan).

Sadece doc sayısı > 0 veya startup'ta sorgulanan koleksiyonlara ekler.
Boş koleksiyonlar Atlas 500 koleksiyon limit'i nedeniyle atlanır.
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
]


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    print(f"DB: {DB_NAME}\n")

    for col, keys in TO_APPLY:
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

            name = await db[col].create_index(keys, background=True)
            print(f"  {col} ({cnt} doc): index olusturuldu -> {name}")
        except Exception as e:
            print(f"  {col}: HATA -> {str(e)[:80]}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
