"""Phase B — Auto-seed + Exely webhook connection ensure."""
import logging
import os
from datetime import UTC, datetime

from core.database import _raw_db

logger = logging.getLogger(__name__)


async def phase_b_seed_and_exely_conn(app):
    # Auto-seed demo data
    from infra.production_config import is_production_env
    _seed_override = os.environ.get("ALLOW_AUTO_SEED_IN_PROD", "").lower() in {"1", "true", "yes"}
    if is_production_env() and not _seed_override:
        logger.info("Auto-seed skipped — production mode (set ALLOW_AUTO_SEED_IN_PROD=1 to override)")
    else:
        try:
            from auto_seed import auto_seed_if_empty
            await auto_seed_if_empty(_raw_db)
        except Exception as e:
            logger.warning(f"Auto-seed error: {e}")

    # Ensure Exely webhook test connection exists
    try:
        existing = await _raw_db.exely_connections.find_one({"hotel_code": "501694"}, {"_id": 1})
        if not existing:
            tenant = await _raw_db.tenants.find_one({}, {"_id": 0, "id": 1})
            tid = tenant["id"] if tenant else "demo"
            import uuid
            await _raw_db.exely_connections.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "hotel_code": "501694",
                "credentials_ref": "",
                "endpoint_url": "",
                "property_name": "Exely Webhook Connection",
                "auto_sync_reservations": True,
                "sync_interval_minutes": 15,
                "mode": "sandbox",
                "currency": "TRY",
                "is_active": True,
                "room_types": [],
                "rate_plans": [],
                "connected_at": datetime.now(UTC).isoformat(),
                "last_sync_at": None,
                "created_by": "startup_ensure",
            })
            logger.info("Exely webhook connection (501694) ensured on startup")
    except Exception as e:
        logger.warning(f"Exely connection ensure error: {e}")
