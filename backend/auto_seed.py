"""
Auto Seed Data — Creates demo data on startup if database is empty.

The original 1475-line implementation has been split into per-area modules
under `seed/`. This file is now a thin orchestrator preserving the exact
public entry point (`auto_seed_if_empty`) used by `bootstrap.startup_phases`.

Order matches the original layout:
  1) tenant + admin/legacy/staff users
  2) rooms (30)
  3) guests (50, encrypted PII)
  4) bookings (45 = 15 past + 10 current + 20 future) + complaints + folios
     — also mutates room status for occupied/dirty/cleaning
  5) housekeeping tasks (active for dirty/cleaning + 15 historical)
  6) channel manager (Exely + HR + 9-collection + v2 + flags)
  7) RMS (room_types + 6-month extended bookings + yield rules + seasons)

If the users collection is non-empty, only idempotent ensure-helpers run
(`ensure_hr_legacy_connection`, `ensure_tenant_admin_seeded`,
`ensure_complaints_seeded`, `ensure_agencies_seeded`).
"""
import logging

from seed._helpers import DEMO_EMAIL, DEMO_HOTEL_NAME
from seed.bookings import seed_bookings_and_folios
from seed.channels import seed_channels
from seed.guests import seed_guests
from seed.housekeeping import seed_housekeeping
from seed.legacy_ensure import (
    ensure_agencies_seeded,
    ensure_complaints_seeded,
    ensure_hr_legacy_connection,
    ensure_tenant_admin_seeded,
)
from seed.rms import seed_rms
from seed.rooms import seed_rooms
from seed.tenant_users import seed_tenant_and_users

logger = logging.getLogger(__name__)


async def auto_seed_if_empty(db):
    """Main entry point: seeds demo data only when users collection is empty."""
    user_count = await db.users.count_documents({})
    if user_count > 0:
        logger.info("ℹ️  Database already has users — skipping auto-seed.")
        await ensure_hr_legacy_connection(db)
        await ensure_tenant_admin_seeded(db)
        await ensure_complaints_seeded(db)
        await ensure_agencies_seeded(db)
        return False

    logger.info("🌱 Empty database detected — seeding demo data...")

    ctx: dict = {}
    await seed_tenant_and_users(db, ctx)
    await seed_rooms(db, ctx)
    await seed_guests(db, ctx)
    await seed_bookings_and_folios(db, ctx)
    await seed_housekeeping(db, ctx)
    await seed_channels(db, ctx)
    await seed_rms(db, ctx)

    # ── Summary ─────────────────────────────────────────
    total_bookings = len(ctx["bookings"]) + len(ctx["extended_bookings"])
    logger.info("Demo data seeded successfully!")
    # v109 round-8: do not log the seed password — even at info level, log
    # aggregators/log-mirrors would capture it (hounddog CRITICAL). The
    # admin email + password env var name is enough for operators to debug.
    logger.info(
        "   Users: %s (admin: %s / password from $DEMO_PASSWORD)",
        1 + ctx["staff_users_count"], DEMO_EMAIL,
    )
    logger.info(f"   Tenant: {DEMO_HOTEL_NAME} (tier: enterprise)")
    logger.info(f"   Rooms: {len(ctx['rooms'])}")
    logger.info(f"   Room Types: {len(ctx['room_types_docs'])}")
    logger.info(f"   Guests: {len(ctx['guests'])}")
    logger.info(f"   Bookings: {total_bookings} (incl. 6-month history)")
    logger.info(f"   Yield Rules: {len(ctx['yield_rules'])}")
    logger.info(f"   Seasonal Calendar: {len(ctx['seasonal_entries'])}")
    logger.info(f"   Folios: {len(ctx['folios'])}")
    logger.info(f"   HK Tasks: {len(ctx['tasks'])}")
    return True
