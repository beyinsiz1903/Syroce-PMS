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
from datetime import UTC, datetime, timedelta

_BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_demo")

HOTEL_ID = "100001"
DEMO_EMAIL = "demo@syroce.com"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD")
DEMO_HOTEL_NAME = "Syroce Demo Hotel"

# Core PMS E2E intentionally creates bookings 30-365 days in the future to
# avoid stale room-night locks after a failed local run. The production guard
# now treats business_date as authoritative, so the isolated CI fixture must
# establish an explicit operational date that has already reached those stays.
# 400 days keeps the fixture deterministic without weakening the guard itself.
E2E_BUSINESS_DATE_LEAD_DAYS = 400


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def seed() -> None:
    env = os.environ.get("ENV", "development").lower()
    if env == "production":
        raise RuntimeError("Demo user seeding is forbidden in production")
    if not DEMO_PASSWORD:
        raise RuntimeError("DEMO_PASSWORD must be set in environment (e.g. CI secrets)")

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
    else:
        user_id = str(uuid.uuid4())
        await db.users.insert_one({
            "id": user_id,
            "tenant_id": tenant_id,
            "agency_id": None,
            "email": DEMO_EMAIL,
            "username": DEMO_USERNAME,
            "name": "Demo Admin",
            "role": "admin",
            "phone": "+905551234567",
            "is_active": True,
            "email_verified": True,
            "email_verified_at": _now_iso(),
            "hashed_password": _hash(DEMO_PASSWORD),
            "created_at": _now_iso(),
        })
        log.info("created demo user email=%s id=%s tenant_id=%s", DEMO_EMAIL, user_id, tenant_id)

    await _ensure_business_date(db, tenant_id)
    await _ensure_rooms(db, tenant_id)


async def _ensure_business_date(db, tenant_id: str) -> None:
    """Seed the isolated E2E tenant's operational clock explicitly.

    Production check-in/check-out now fail closed when `business_date` is
    missing. CI must therefore model a valid hotel state rather than relying on
    the old wall-clock fallback. This script is forbidden in production above,
    so advancing the demo business date is confined to disposable E2E data.
    """
    now = datetime.now(UTC)
    business_date = (now + timedelta(days=E2E_BUSINESS_DATE_LEAD_DAYS)).date().isoformat()
    await db.tenant_settings.update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                "business_date": business_date,
                "business_date_updated_at": now.isoformat(),
            },
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "previous_business_date": None,
            },
        },
        upsert=True,
    )
    log.info("seeded E2E business_date tenant_id=%s date=%s", tenant_id, business_date)


async def _ensure_rooms(db, tenant_id: str) -> None:
    """Idempotent room seeder for E2E.

    The full bootstrap auto_seed (`auto_seed.py`) skips when users collection
    is non-empty, so once this script creates the demo user the room seed
    never runs in CI. E2E spec #06 (`Core PMS happy-path`) needs at least one
    room or test #1 fails with `Received: 0`. We delegate to the same
    `seed.rooms.seed_rooms` module the bootstrap uses so room shape stays in
    lock-step with production seed (room_number/status/capacity/etc).
    """
    existing_rooms = await db.rooms.count_documents({"tenant_id": tenant_id})
    if existing_rooms > 0:
        log.info("rooms exist tenant_id=%s count=%d — skip", tenant_id, existing_rooms)
        return

    try:
        from seed.rooms import seed_rooms  # noqa: WPS433 — local import keeps script standalone
    except Exception as exc:  # pragma: no cover — import shape mismatch is a CI-fatal bug
        log.error("seed.rooms import failed: %s", exc)
        raise

    ctx: dict = {"tenant_id": tenant_id, "rooms": []}
    await seed_rooms(db, ctx)
    log.info("seeded rooms tenant_id=%s count=%d", tenant_id, len(ctx["rooms"]))


if __name__ == "__main__":
    asyncio.run(seed())
