"""Seed one approved demo vendor + a starter catalogue.

Idempotent: re-running updates the demo vendor & products instead of duplicating.

Usage:
    python -m scripts.seed_supplies_market

Demo credentials:
    email:    demo-vendor@syroce.com
    password: vendor1234
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.supplies_market.repository import (  # noqa: E402
    ensure_indexes,
    products_col,
    vendors_col,
)
from modules.supplies_market.vendor_auth import hash_password  # noqa: E402


def _now() -> str:
    return datetime.now(UTC).isoformat()


DEMO_EMAIL = "demo-vendor@syroce.com"
DEMO_PASSWORD = "vendor1234"
DEMO_COMPANY = "Demo Otelcilik Tedarik A.Ş."

CATALOGUE = [
    # banyo
    {"name": "Pamuk Yüz Havlusu 50x90 (12'li paket)", "category": "banyo",
     "description": "300 g/m² %100 pamuk, otel kalitesi", "price_try": 480.0,
     "unit": "paket", "pack_size": 12, "moq": 5, "stock": 200},
    {"name": "Otel Tipi Tek Kullanımlık Terlik (200 çift)", "category": "banyo",
     "description": "Beyaz EVA taban, kapalı burun", "price_try": 1750.0,
     "unit": "koli", "pack_size": 200, "moq": 1, "stock": 60},
    {"name": "Şampuan & Duş Jeli 30 ml (288 adet)", "category": "banyo",
     "description": "Hipoalerjenik formül, parfümlü", "price_try": 1320.0,
     "unit": "koli", "pack_size": 288, "moq": 1, "stock": 80},
    {"name": "Banyo Sabunu 20 g (500 adet)", "category": "banyo",
     "description": "Tek kullanımlık, kâğıt sargı", "price_try": 950.0,
     "unit": "koli", "pack_size": 500, "moq": 1, "stock": 120},
    {"name": "Diş Bakım Kiti (150 adet)", "category": "banyo",
     "description": "Diş fırçası + 5 g macun, kapalı paket", "price_try": 870.0,
     "unit": "koli", "pack_size": 150, "moq": 1, "stock": 90},
    # yatak_tekstil
    {"name": "Saten Nevresim Takımı Çift Kişilik (10'lu)", "category": "yatak_tekstil",
     "description": "%100 pamuk, 200 iplik, beyaz", "price_try": 5400.0,
     "unit": "paket", "pack_size": 10, "moq": 1, "stock": 25},
    # temizlik
    {"name": "Çamaşır Deterjanı Profesyonel 20 L", "category": "temizlik",
     "description": "Yüksek konsantrasyon, makine için uygun", "price_try": 880.0,
     "unit": "bidon", "pack_size": 1, "moq": 2, "stock": 40},
    {"name": "Yüzey Dezenfektanı 5 L (4'lü koli)", "category": "temizlik",
     "description": "Geniş spektrum, gıda alanı uyumlu", "price_try": 720.0,
     "unit": "koli", "pack_size": 4, "moq": 1, "stock": 50},
]


async def main():
    await ensure_indexes()

    existing = await vendors_col.find_one({"email": DEMO_EMAIL})
    if existing:
        vendor_id = existing["id"]
        await vendors_col.update_one(
            {"id": vendor_id},
            {"$set": {
                "status": "approved",
                "company_name": DEMO_COMPANY,
                "commission_pct": 8.0,
                "updated_at": _now(),
            }},
        )
        print(f"↻ Updated demo vendor {vendor_id}")
    else:
        vendor_id = str(uuid.uuid4())
        await vendors_col.insert_one({
            "id": vendor_id,
            "email": DEMO_EMAIL,
            "password_hash": hash_password(DEMO_PASSWORD),
            "company_name": DEMO_COMPANY,
            "contact_name": "Demo İletişim",
            "phone": "+90 555 555 55 55",
            "tax_no": "1234567890",
            "tax_office": "Beyoğlu",
            "iban": "TR00 0000 0000 0000 0000 0000 00",
            "address": "Demo Mahallesi No:1 Beyoğlu/İstanbul",
            "city": "İstanbul",
            "status": "approved",
            "commission_pct": 8.0,
            "created_at": _now(),
            "updated_at": _now(),
        })
        print(f"+ Created demo vendor {vendor_id}")

    inserted = updated = 0
    for item in CATALOGUE:
        existing_p = await products_col.find_one({"vendor_id": vendor_id, "name": item["name"]})
        doc = {
            "vendor_id": vendor_id,
            "vendor_name": DEMO_COMPANY,
            "is_active": True,
            "images": [],
            "updated_at": _now(),
            **item,
        }
        if existing_p:
            await products_col.update_one({"id": existing_p["id"]}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = _now()
            await products_col.insert_one(doc)
            inserted += 1

    print(f"📦 Catalogue: {inserted} inserted, {updated} updated")
    print("\nDemo vendor login:")
    print(f"  email:    {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
