"""
Migration Verification — Schema Drift Detection & Index Validation
===================================================================
Checks that MongoDB collections have the expected indexes and structure.
Used as a hard gate in the deploy pipeline.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from common.result import ServiceResult

logger = logging.getLogger("ops.migration_verification")

# Expected indexes by collection — defines what MUST exist
REQUIRED_INDEXES = {
    "bookings": [
        {"name": "idx_booking_status_checkin", "keys": [("tenant_id", 1), ("status", 1), ("check_in", 1)]},
        {"name": "idx_booking_room_dates", "keys": [("tenant_id", 1), ("room_id", 1), ("check_in", 1), ("check_out", 1)]},
    ],
    "rooms": [
        {"name": "idx_rooms_tenant_number", "keys": [("tenant_id", 1), ("room_number", 1)]},
    ],
    "guests": [
        {"name": "idx_guests_tenant_email", "keys": [("tenant_id", 1), ("email", 1)]},
    ],
    "outbox_events": [
        {"name": "idx_outbox_queue", "keys": [("status", 1), ("event_type", 1), ("created_at", 1)]},
    ],
    "event_timeline": [
        {"name": "idx_timeline_correlation", "keys": [("correlation_id", 1)]},
    ],
    "feature_flags": [
        {"name": "idx_ff_key", "keys": [("flag_key", 1)]},
    ],
}

# Expected collections that must exist
REQUIRED_COLLECTIONS = [
    "users",
    "bookings",
    "rooms",
    "guests",
    "tenants",
    "organizations",
    "folios",
    "folio_charges",
    "payments",
    "outbox_events",
    "event_timeline",
    "feature_flags",
    "usage_daily",
]


class MigrationVerifier:
    """Verifies database schema integrity before deployment."""

    def __init__(self):
        from core.database import db

        self._db = db

    async def verify_all(self) -> ServiceResult:
        """Run full migration verification suite."""
        now = datetime.now(UTC).isoformat()
        drift_issues: list[dict[str, Any]] = []
        missing_indexes: list[dict[str, Any]] = []
        collections_checked = 0

        try:
            # Get existing collections
            existing_collections = await self._db.list_collection_names()

            # Check required collections
            for coll_name in REQUIRED_COLLECTIONS:
                collections_checked += 1
                if coll_name not in existing_collections:
                    drift_issues.append(
                        {
                            "collection": coll_name,
                            "issue": "Collection does not exist",
                            "severity": "warning",
                        }
                    )

            # Check required indexes
            for coll_name, indexes in REQUIRED_INDEXES.items():
                if coll_name not in existing_collections:
                    for idx in indexes:
                        missing_indexes.append(
                            {
                                "collection": coll_name,
                                "index_name": idx["name"],
                                "reason": "Collection missing",
                            }
                        )
                    continue

                try:
                    existing_idx_info = await self._db[coll_name].index_information()
                    existing_idx_names = set(existing_idx_info.keys())

                    for idx in indexes:
                        if idx["name"] not in existing_idx_names:
                            # Check if an equivalent index exists with different name
                            idx_key_set = {tuple(k) for k in idx["keys"]}
                            found = False
                            for eidx_name, eidx_info in existing_idx_info.items():
                                existing_key_set = {tuple(k) for k in eidx_info.get("key", [])}
                                if idx_key_set == existing_key_set:
                                    found = True
                                    break
                            if not found:
                                missing_indexes.append(
                                    {
                                        "collection": coll_name,
                                        "index_name": idx["name"],
                                        "reason": "Index not found",
                                    }
                                )
                except Exception as e:
                    drift_issues.append(
                        {
                            "collection": coll_name,
                            "issue": f"Cannot read indexes: {str(e)[:100]}",
                            "severity": "warning",
                        }
                    )

            # Check for oversized collections (potential data issues)
            for coll_name in ["outbox_events", "event_timeline"]:
                if coll_name in existing_collections:
                    try:
                        count = await self._db[coll_name].estimated_document_count()
                        if count > 10_000_000:
                            drift_issues.append(
                                {
                                    "collection": coll_name,
                                    "issue": f"Very large collection ({count:,} docs) — consider archival",
                                    "severity": "info",
                                }
                            )
                    except Exception:
                        pass

            # Critical drift = any missing required index
            critical_count = len(missing_indexes)
            warning_count = len([d for d in drift_issues if d["severity"] == "warning"])

            return ServiceResult.success(
                {
                    "verified_at": now,
                    "collections_checked": collections_checked,
                    "drift_issues": drift_issues,
                    "missing_indexes": missing_indexes,
                    "critical_count": critical_count,
                    "warning_count": warning_count,
                    "verdict": "FAIL" if critical_count > 0 else ("WARN" if warning_count > 0 else "PASS"),
                }
            )

        except Exception as e:
            return ServiceResult.fail(f"Migration verification error: {str(e)}", "VERIFY_ERROR")

    async def get_collection_stats(self) -> ServiceResult:
        """Get document counts and index counts for all collections."""
        try:
            collections = await self._db.list_collection_names()
            stats = []
            for coll_name in sorted(collections):
                try:
                    count = await self._db[coll_name].estimated_document_count()
                    idx_info = await self._db[coll_name].index_information()
                    stats.append(
                        {
                            "collection": coll_name,
                            "document_count": count,
                            "index_count": len(idx_info),
                        }
                    )
                except Exception:
                    stats.append({"collection": coll_name, "document_count": -1, "index_count": -1})

            return ServiceResult.success({"collections": stats, "total": len(stats)})
        except Exception as e:
            return ServiceResult.fail(str(e), "STATS_ERROR")


migration_verifier = MigrationVerifier()
