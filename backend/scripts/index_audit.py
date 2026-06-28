"""R5: Index audit — en sık find edilen koleksiyonların index durumu."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MONGO_URL = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI") or "mongodb://localhost:27017"
DB_NAME = os.environ.get("DB_NAME", "syroce-pms")

TARGETS = [
    ("bookings", [("tenant_id", "check_in"), ("tenant_id", "check_out"), ("tenant_id", "status"), ("tenant_id", "created_at")]),
    ("rooms", [("tenant_id", "status")]),
    ("guests", [("tenant_id", "id")]),
    ("payments", [("tenant_id", "payment_date")]),
    ("folio_charges", [("tenant_id", "date")]),
    ("reviews", [("tenant_id",)]),
    ("feedback", [("tenant_id", "rating", "created_at")]),
    ("incidents", [("tenant_id", "incident_date")]),
    ("housekeeping_tasks", [("tenant_id", "completed_at")]),
    ("audit_logs", [("tenant_id",)]),
    ("survey_responses", [("tenant_id",)]),
    ("external_reviews", [("tenant_id",)]),
    ("department_feedback", [("tenant_id",)]),
    ("expenses", [("tenant_id",)]),
    ("bank_accounts", [("tenant_id",)]),
    ("users", [("tenant_id", "email")]),
    ("complaints", [("tenant_id",)]),
    ("agency_bookings", [("tenant_id",)]),
    ("exely_connections", [("tenant_id", "is_active")]),
    ("hotelrunner_connections", [("tenant_id", "is_active")]),
]


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    print(f"DB: {DB_NAME}\n")
    print(f"{'Koleksiyon':<28} {'Doc#':>10}  Durum")
    print("-" * 95)

    total_missing = 0
    missing_summary = []
    for col, want_keys in TARGETS:
        try:
            cnt = await db[col].estimated_document_count()
            indexes = await db[col].list_indexes().to_list(50)
            existing = [tuple(i["key"].keys()) for i in indexes]

            def covered(want, _existing=existing):
                for ex in _existing:
                    if len(ex) >= len(want) and tuple(ex[: len(want)]) == want:
                        return True
                return False

            missing = [w for w in want_keys if not covered(w)]
            if missing:
                total_missing += len(missing)
                ms = ", ".join("(" + ",".join(m) + ")" for m in missing)
                print(f"{col:<28} {cnt:>10}  EKSIK: {ms}")
                missing_summary.append((col, missing, cnt))
            else:
                print(f"{col:<28} {cnt:>10}  OK ({len(indexes)} idx)")
        except Exception as e:
            print(f"{col:<28} {'-':>10}  ERR: {str(e)[:60]}")

    print(f"\nOZET: {total_missing} eksik oneri, {len(TARGETS)} koleksiyon")
    if missing_summary:
        print("\n— Yuksek doc sayili + eksik (oncelikli) —")
        for col, miss, cnt in sorted(missing_summary, key=lambda x: -x[2])[:10]:
            ms = ", ".join("(" + ",".join(m) + ")" for m in miss)
            print(f"  {col} ({cnt:,} doc): {ms}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
