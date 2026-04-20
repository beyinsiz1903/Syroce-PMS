"""Idempotent demo user seeder.

Ensures the credentials shown on the login screen
(hotel_id=100001, username=demo, password=demo123) always work,
even if the database is recreated or the user is accidentally removed.

Safe to run multiple times — only inserts when missing, never overwrites
an existing user's password.
"""
import logging
import uuid
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

DEMO_HOTEL_ID = "100001"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"


async def ensure_demo_user(db: AsyncIOMotorDatabase) -> None:
    try:
        tenant = await db.tenants.find_one({"hotel_id": DEMO_HOTEL_ID})
        if not tenant:
            logger.info("ensure_demo_user: no tenant with hotel_id=%s, skipping", DEMO_HOTEL_ID)
            return

        tenant_id = tenant.get("id") or tenant.get("tenant_id") or str(tenant.get("_id"))
        existing = await db.users.find_one({"tenant_id": tenant_id, "username": DEMO_USERNAME})
        if existing:
            return

        from core.security import hash_password

        now = datetime.now(UTC).isoformat()
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "agency_id": None,
            "email": "demo@syroce.com",
            "name": "Demo Kullanıcı",
            "role": "super_admin",
            "phone": "+905555555555",
            "is_active": True,
            "email_verified": True,
            "email_verified_at": now,
            "hashed_password": hash_password(DEMO_PASSWORD),
            "created_at": now,
            "username": DEMO_USERNAME,
        })
        logger.info("ensure_demo_user: created demo user (tenant=%s, hotel_id=%s)", tenant_id, DEMO_HOTEL_ID)
    except Exception as exc:
        logger.warning("ensure_demo_user skipped: %s", exc)
