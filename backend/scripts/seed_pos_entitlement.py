import asyncio
import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient

from core.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

POS_PRODUCTS = [
    {
        "key": "pos_fnb_basic",
        "title": "Restoran POS (Basic)",
        "description": "Temel Restoran POS sistemi. Tek outlet, masa, adisyon ve ödeme işlemleri için.",
        "icon": "PointOfSale",
        "category": "operations",
        "price": 0,
        "currency": "TRY",
        "billing_cycle": "monthly",
        "is_active": True,
        "is_featured": True,
        "trial_days": 14,
        "features": [
            "1 Adet Outlet/Kasa",
            "Masa ve Adisyon Yönetimi",
            "Nakit ve Kredi Kartı Tahsilatı",
            "Oda Hesabına Aktarım",
            "Temel Satış Raporları"
        ]
    },
    {
        "key": "pos_fnb_pro",
        "title": "Restoran POS (Pro)",
        "description": "Çoklu outlet ve gelişmiş restoran yönetimi (KDS, Stok, Mobil Garson).",
        "icon": "PointOfSale",
        "category": "operations",
        "price": 999,
        "currency": "TRY",
        "billing_cycle": "monthly",
        "is_active": True,
        "is_featured": True,
        "trial_days": 14,
        "features": [
            "Çoklu Outlet (5 Kasaya Kadar)",
            "Mobil Garson Terminali",
            "Mutfak Ekranı (KDS)",
            "Stok ve Reçete Yönetimi",
            "Gelişmiş Analitik ve Raporlar"
        ]
    }
]

async def seed_pos_entitlements() -> None:
    logger.info("Starting POS Entitlement Seeding...")
    inserted = 0
    updated = 0
    
    for prod in POS_PRODUCTS:
        try:
            # Fields that we ALWAYS want to update (schema / core attributes)
            set_fields = {
                "title": prod["title"],
                "icon": prod["icon"],
                "category": prod["category"],
                "features": prod["features"],
                "updated_at": _now_iso()
            }
            # Fields that we ONLY set on insert (user can edit these later)
            set_on_insert_fields = {
                "description": prod["description"],
                "price": prod["price"],
                "currency": prod["currency"],
                "billing_cycle": prod["billing_cycle"],
                "is_active": prod["is_active"],
                "is_featured": prod["is_featured"],
                "trial_days": prod["trial_days"],
                "created_at": _now_iso()
            }
            
            res = await db.marketplace_products.update_one(
                {"key": prod["key"]},
                {
                    "$set": set_fields,
                    "$setOnInsert": set_on_insert_fields
                },
                upsert=True
            )
            if res.upserted_id:
                inserted += 1
            elif res.modified_count:
                updated += 1
        except Exception as e:
            logger.error(f"Failed to seed {prod['key']}: {e}")
            
    logger.info(f"Seeding completed: {inserted} inserted, {updated} updated.")

if __name__ == "__main__":
    asyncio.run(seed_pos_entitlements())
