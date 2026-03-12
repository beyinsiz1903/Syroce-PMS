"""
Feature Store - Feature engineering from operational data.
Extracts features from reservations, stays, folios, guest journey events, and channel signals.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from core.database import db

logger = logging.getLogger("data_pipeline.feature_store")


class FeatureStore:
    """Centralized feature engineering for ML models."""

    FEATURE_SETS = {
        "revenue": {
            "sources": ["bookings", "rooms", "folios"],
            "features": [
                "avg_daily_rate", "occupancy_rate", "revpar", "booking_lead_time",
                "cancellation_rate", "length_of_stay", "channel_mix", "day_of_week_demand",
                "seasonal_factor", "group_vs_transient_ratio",
            ],
        },
        "operational": {
            "sources": ["tasks", "rooms", "bookings"],
            "features": [
                "housekeeping_turnaround_time", "maintenance_request_frequency",
                "room_turnover_rate", "staffing_density", "task_completion_rate",
                "average_response_time", "overdue_task_ratio", "check_in_peak_hour",
            ],
        },
        "guest_intelligence": {
            "sources": ["guests", "bookings", "folios"],
            "features": [
                "guest_lifetime_value", "booking_frequency", "avg_spend_per_stay",
                "preferred_room_type", "channel_preference", "complaint_history",
                "loyalty_tier", "churn_risk_score", "upsell_propensity",
                "satisfaction_trend",
            ],
        },
    }

    async def extract_revenue_features(self, tenant_id: str,
                                       date_from: Optional[str] = None,
                                       date_to: Optional[str] = None) -> Dict[str, Any]:
        """Extract revenue-related features from operational data."""
        now = datetime.now(timezone.utc)
        if not date_from:
            date_from = (now - timedelta(days=90)).isoformat()
        if not date_to:
            date_to = now.isoformat()

        q = {"tenant_id": tenant_id}

        bookings = await db.bookings.find(q, {"_id": 0}).to_list(5000)
        rooms = await db.rooms.find(q, {"_id": 0}).to_list(500)
        total_rooms = len(rooms) or 1

        total_revenue = 0
        total_nights = 0
        lead_times = []
        cancellations = 0
        los_values = []
        channel_counts: Dict[str, int] = {}

        for b in bookings:
            status = b.get("status", "")
            if status == "cancelled":
                cancellations += 1
                continue
            rate = b.get("total_amount") or b.get("rate") or 0
            total_revenue += rate
            ci = b.get("check_in", "")
            co = b.get("check_out", "")
            created = b.get("created_at", "")
            if ci and co:
                try:
                    ci_dt = datetime.fromisoformat(ci.replace("Z", "+00:00")) if isinstance(ci, str) else ci
                    co_dt = datetime.fromisoformat(co.replace("Z", "+00:00")) if isinstance(co, str) else co
                    nights = max((co_dt - ci_dt).days, 1)
                    total_nights += nights
                    los_values.append(nights)
                except (ValueError, TypeError):
                    pass
            if created and ci:
                try:
                    cr_dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
                    ci_dt2 = datetime.fromisoformat(ci.replace("Z", "+00:00")) if isinstance(ci, str) else ci
                    lead_times.append(max((ci_dt2 - cr_dt).days, 0))
                except (ValueError, TypeError):
                    pass
            ch = b.get("channel", "direct")
            channel_counts[ch] = channel_counts.get(ch, 0) + 1

        active_bookings = len(bookings) - cancellations
        occ_rate = round(active_bookings / total_rooms, 4) if total_rooms else 0
        adr = round(total_revenue / max(active_bookings, 1), 2)
        revpar = round(total_revenue / total_rooms, 2) if total_rooms else 0

        features = {
            "tenant_id": tenant_id,
            "feature_set": "revenue",
            "extracted_at": now.isoformat(),
            "date_range": {"from": date_from, "to": date_to},
            "features": {
                "avg_daily_rate": adr,
                "occupancy_rate": occ_rate,
                "revpar": revpar,
                "booking_lead_time": round(sum(lead_times) / max(len(lead_times), 1), 1),
                "cancellation_rate": round(cancellations / max(len(bookings), 1), 4),
                "avg_length_of_stay": round(sum(los_values) / max(len(los_values), 1), 1),
                "channel_mix": channel_counts,
                "total_bookings": len(bookings),
                "total_revenue": total_revenue,
                "total_room_nights": total_nights,
            },
            "record_count": len(bookings),
        }

        await db.feature_store.insert_one({
            "id": str(uuid.uuid4()),
            **features,
        })
        return features

    async def extract_operational_features(self, tenant_id: str) -> Dict[str, Any]:
        """Extract operational features from tasks and room data."""
        now = datetime.now(timezone.utc)
        q = {"tenant_id": tenant_id}

        tasks = await db.tasks.find(q, {"_id": 0}).to_list(2000)
        rooms = await db.rooms.find(q, {"_id": 0}).to_list(500)

        completed = [t for t in tasks if t.get("status") == "completed"]
        overdue = [t for t in tasks if t.get("status") == "overdue"]

        features = {
            "tenant_id": tenant_id,
            "feature_set": "operational",
            "extracted_at": now.isoformat(),
            "features": {
                "total_tasks": len(tasks),
                "completed_tasks": len(completed),
                "overdue_tasks": len(overdue),
                "task_completion_rate": round(len(completed) / max(len(tasks), 1), 4),
                "overdue_ratio": round(len(overdue) / max(len(tasks), 1), 4),
                "total_rooms": len(rooms),
                "rooms_by_status": {},
            },
            "record_count": len(tasks) + len(rooms),
        }

        status_counts: Dict[str, int] = {}
        for r in rooms:
            s = r.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        features["features"]["rooms_by_status"] = status_counts

        await db.feature_store.insert_one({"id": str(uuid.uuid4()), **features})
        return features

    async def extract_guest_features(self, tenant_id: str) -> Dict[str, Any]:
        """Extract guest intelligence features."""
        now = datetime.now(timezone.utc)
        q = {"tenant_id": tenant_id}

        guests = await db.guests.find(q, {"_id": 0}).to_list(5000)
        bookings = await db.bookings.find(q, {"_id": 0}).to_list(5000)

        guest_bookings: Dict[str, list] = {}
        for b in bookings:
            gid = b.get("guest_id", "")
            if gid:
                guest_bookings.setdefault(gid, []).append(b)

        total_ltv = 0
        repeat_guests = 0
        for gid, gbooks in guest_bookings.items():
            ltv = sum(b.get("total_amount", 0) or b.get("rate", 0) for b in gbooks)
            total_ltv += ltv
            if len(gbooks) > 1:
                repeat_guests += 1

        features = {
            "tenant_id": tenant_id,
            "feature_set": "guest_intelligence",
            "extracted_at": now.isoformat(),
            "features": {
                "total_guests": len(guests),
                "guests_with_bookings": len(guest_bookings),
                "repeat_guest_rate": round(repeat_guests / max(len(guest_bookings), 1), 4),
                "avg_lifetime_value": round(total_ltv / max(len(guest_bookings), 1), 2),
                "total_lifetime_value": total_ltv,
            },
            "record_count": len(guests),
        }

        await db.feature_store.insert_one({"id": str(uuid.uuid4()), **features})
        return features

    async def get_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get feature store summary for a tenant."""
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$sort": {"extracted_at": -1}},
            {"$group": {
                "_id": "$feature_set",
                "latest_extraction": {"$first": "$extracted_at"},
                "record_count": {"$first": "$record_count"},
                "total_extractions": {"$sum": 1},
            }},
        ]
        results = await db.feature_store.aggregate(pipeline).to_list(10)
        return {
            "tenant_id": tenant_id,
            "feature_sets": [
                {
                    "name": r["_id"],
                    "latest_extraction": r["latest_extraction"],
                    "record_count": r["record_count"],
                    "total_extractions": r["total_extractions"],
                    "defined_features": len(self.FEATURE_SETS.get(r["_id"], {}).get("features", [])),
                }
                for r in results
            ],
            "available_sets": list(self.FEATURE_SETS.keys()),
        }


feature_store = FeatureStore()
