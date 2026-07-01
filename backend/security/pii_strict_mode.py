"""
PII Strict Mode — Global enforcement of PII masking across all API responses.

When enabled, ALL JSON responses from /api/* endpoints are automatically
scanned and PII fields are masked based on the caller's role.

Configuration is DB-backed (collection: pii_strict_mode_config).
Violations (unmasked PII access attempts) are logged to pii_strict_violations.
"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger("security.pii_strict_mode")

COLL_CONFIG = "pii_strict_mode_config"
COLL_VIOLATIONS = "pii_strict_violations"
CONFIG_DOC_ID = "global_strict_mode"


class PIIStrictModeService:
    """Manages PII Strict Mode configuration and violation tracking."""

    def __init__(self):
        self._db = None
        self._cache = None
        self._cache_ts = None

    def _get_db(self):
        if self._db is None:
            from core.database import db

            self._db = db
        return self._db

    async def get_config(self) -> dict:
        """Return current strict mode configuration."""
        db = self._get_db()
        doc = await db[COLL_CONFIG].find_one({"_id": CONFIG_DOC_ID}, {"_id": 0})
        if not doc:
            return {
                "enabled": False,
                "whitelisted_paths": [
                    "/api/auth/login",
                    "/api/auth/register",
                    "/api/auth/forgot-password",
                    "/api/health",
                    "/api/docs",
                    "/api/redoc",
                    "/api/openapi.json",
                ],
                "enforcement_level": "mask",
                "log_violations": True,
                "updated_at": None,
                "updated_by": None,
            }
        return doc

    async def is_enabled(self) -> bool:
        """Check if strict mode is currently enabled (with simple cache)."""
        import time

        now = time.time()
        if self._cache is not None and self._cache_ts and (now - self._cache_ts) < 30:
            return self._cache
        config = await self.get_config()
        self._cache = config.get("enabled", False)
        self._cache_ts = now
        return self._cache

    async def toggle(self, *, enabled: bool, actor: str, actor_role: str) -> dict:
        """Enable or disable strict mode."""
        db = self._get_db()
        now = datetime.now(UTC).isoformat()
        config = await self.get_config()
        config["enabled"] = enabled
        config["updated_at"] = now
        config["updated_by"] = actor

        await db[COLL_CONFIG].update_one(
            {"_id": CONFIG_DOC_ID},
            {"$set": {**config, "_id": CONFIG_DOC_ID}},
            upsert=True,
        )

        # Log the toggle event
        await db[COLL_VIOLATIONS].insert_one(
            {
                "event_type": "strict_mode_toggled",
                "enabled": enabled,
                "actor": actor,
                "actor_role": actor_role,
                "timestamp": now,
            }
        )

        # Invalidate cache
        self._cache = enabled
        import time

        self._cache_ts = time.time()

        logger.info("PII Strict Mode %s by %s", "ENABLED" if enabled else "DISABLED", actor)
        return config

    async def update_whitelist(self, *, paths: list[str], actor: str) -> dict:
        """Update whitelisted paths that bypass strict mode."""
        db = self._get_db()
        now = datetime.now(UTC).isoformat()
        await db[COLL_CONFIG].update_one(
            {"_id": CONFIG_DOC_ID},
            {"$set": {"whitelisted_paths": paths, "updated_at": now, "updated_by": actor}},
            upsert=True,
        )
        config = await self.get_config()
        return config

    async def log_violation(
        self,
        *,
        path: str,
        method: str,
        user_id: str = "",
        user_role: str = "",
        pii_fields_found: list[str],
        action_taken: str = "masked",
    ) -> None:
        """Record a PII violation event."""
        db = self._get_db()
        await db[COLL_VIOLATIONS].insert_one(
            {
                "event_type": "pii_violation",
                "path": path,
                "method": method,
                "user_id": user_id,
                "user_role": user_role,
                "pii_fields_found": pii_fields_found,
                "action_taken": action_taken,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def get_violations(self, *, limit: int = 50, skip: int = 0, event_type: str | None = None) -> dict:
        """Query violation/event log."""
        db = self._get_db()
        query = {}
        if event_type:
            query["event_type"] = event_type
        total = await db[COLL_VIOLATIONS].count_documents(query)
        items = await db[COLL_VIOLATIONS].find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
        return {"items": items, "total": total, "limit": limit, "skip": skip}

    async def get_summary(self, *, hours: int = 24) -> dict:
        """Aggregate violation stats for the dashboard."""
        from datetime import timedelta

        db = self._get_db()
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        config = await self.get_config()

        pipeline = [
            {"$match": {"event_type": "pii_violation", "timestamp": {"$gte": cutoff}}},
            {
                "$group": {
                    "_id": None,
                    "total_violations": {"$sum": 1},
                    "unique_paths": {"$addToSet": "$path"},
                    "unique_users": {"$addToSet": "$user_id"},
                    "fields_seen": {"$push": "$pii_fields_found"},
                }
            },
        ]
        result = await db[COLL_VIOLATIONS].aggregate(pipeline).to_list(1)

        if result:
            r = result[0]
            all_fields = []
            for fl in r.get("fields_seen", []):
                if isinstance(fl, list):
                    all_fields.extend(fl)
            field_counts = {}
            for f in all_fields:
                field_counts[f] = field_counts.get(f, 0) + 1
            return {
                "strict_mode_enabled": config.get("enabled", False),
                "period_hours": hours,
                "total_violations": r["total_violations"],
                "unique_paths": len(r["unique_paths"]),
                "unique_users": len(r["unique_users"]),
                "top_fields": sorted(field_counts.items(), key=lambda x: -x[1])[:10],
                "whitelisted_paths": len(config.get("whitelisted_paths", [])),
            }

        return {
            "strict_mode_enabled": config.get("enabled", False),
            "period_hours": hours,
            "total_violations": 0,
            "unique_paths": 0,
            "unique_users": 0,
            "top_fields": [],
            "whitelisted_paths": len(config.get("whitelisted_paths", [])),
        }

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient violation queries."""
        db = self._get_db()
        coll = db[COLL_VIOLATIONS]
        await coll.create_index([("event_type", 1), ("timestamp", -1)])
        await coll.create_index("timestamp", expireAfterSeconds=90 * 86400)


# Singleton
_instance: PIIStrictModeService | None = None


def get_pii_strict_mode_service() -> PIIStrictModeService:
    global _instance
    if _instance is None:
        _instance = PIIStrictModeService()
    return _instance
