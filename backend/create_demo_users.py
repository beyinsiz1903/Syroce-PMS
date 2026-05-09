"""CI/E2E seeder: tenant hotel_id=100001 + demo@syroce.com / demo123 user.

Idempotent. Mirrors the relevant pieces of `seed/tenant_users.py` but does
not depend on the full bootstrap pipeline so it can be invoked directly
from a fresh CI database. Used by `.github/workflows/frontend-quality.yml`
before the e2e smoke run.
"""

import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime

_BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from motor.motor_asyncio import AsyncIOMotorClient

from core._pwd import BcryptContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_demo")

HOTEL_ID = "100001"
DEMO_EMAIL = "demo@syroce.com"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"
DEMO_HOTEL_NAME = "Syroce Demo Hotel"

pwd_context = BcryptContext()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def seed() -> None:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "hotel_pms_test")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    tenant = await db.tenants.find_one({"hotel_id": HOTEL_ID})
    if tenant:
        tenant_id = tenant.get("id") or tenant.get("tenant_id") or str(tenant.get("_id"))
        log.info("tenant exists hotel_id=%s id=%s", HOTEL_ID, tenant_id)
    else:
        tenant_id = str(uuid.uuid4())
        await db.tenants.insert_one({
            "id": tenant_id,
            "hotel_id": HOTEL_ID,
            "name": DEMO_HOTEL_NAME,
            "property_name": DEMO_HOTEL_NAME,
            "property_type": "hotel",
            "contact_email": DEMO_EMAIL,
            "contact_phone": "+905551234567",
            "address": "Antalya, Türkiye",
            "total_rooms": 30,
            "subscription_status": "active",
            "subscription_tier": "enterprise",
            "plan": "enterprise",
            "location": "Antalya",
            "created_at": _now_iso(),
            "modules": {
                "pms": True, "reports": True, "invoices": True, "ai": True,
                "channel_manager": True, "rms": True, "housekeeping": True,
                "reservation_calendar": True, "loyalty": True, "marketplace": True,
                "maintenance": True, "night_audit": True, "folio_management": True,
                "cost_management": True, "sales_crm": True, "group_sales": True,
                "gm_dashboards": True, "mobile_housekeeping": True,
                "rate_management": True, "basic_reporting": True,
                "revenue_management": True, "advanced_analytics": True,
            },
        })
        log.info("created tenant hotel_id=%s id=%s", HOTEL_ID, tenant_id)

    existing = await db.users.find_one({
        "tenant_id": tenant_id,
        "$or": [{"email": DEMO_EMAIL}, {"username": DEMO_USERNAME}],
    })
    if existing:
        log.info("demo user exists email=%s id=%s", DEMO_EMAIL, existing.get("id"))
        return

    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": user_id,
        "tenant_id": tenant_id,
        "agency_id": None,
        "email": DEMO_EMAIL,
        "username": DEMO_USERNAME,
        "name": "Demo Admin",
        "role": "super_admin",
        "phone": "+905551234567",
        "is_active": True,
        "email_verified": True,
        "email_verified_at": _now_iso(),
        "hashed_password": pwd_context.hash(DEMO_PASSWORD),
        "created_at": _now_iso(),
    })
    log.info("created demo user email=%s id=%s tenant_id=%s", DEMO_EMAIL, user_id, tenant_id)


if __name__ == "__main__":
    asyncio.run(seed())
