"""
Cross-Module Deep Integration Bus - Operational intelligence flows
connecting different hotel system modules.
10 defined integration pathways for enterprise operational intelligence.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)


class CrossModuleIntegrationBus:
    """
    Orchestrates cross-module data flows:
    1. cancellation_prediction → overbooking_strategy
    2. booking_probability → revenue_recommendation_confidence
    3. comp_set_price_gap → ADR_recommendation
    4. guest_request_volume → housekeeping_priority
    5. vip_arrival → room_readiness_priority
    6. night_audit_exception → escalation_queue
    7. failed_messaging → guest_journey_fallback
    8. sync_failure → operations_alert
    9. revenue_auto_apply_result → dashboard_metrics
    10. reservation_risk_signals → front_desk_warning_badges
    """

    async def run_all_integrations(self, tenant_id: str) -> dict[str, Any]:
        """Execute all cross-module integrations and return results."""
        results = {}
        integrations = [
            ("cancellation_to_overbooking", self.cancellation_to_overbooking),
            ("booking_prob_to_revenue", self.booking_prob_to_revenue_confidence),
            ("compset_to_adr", self.compset_gap_to_adr),
            ("guest_requests_to_hk", self.guest_requests_to_hk_priority),
            ("vip_to_room_readiness", self.vip_to_room_readiness),
            ("audit_to_escalation", self.audit_exception_to_escalation),
            ("messaging_to_fallback", self.failed_messaging_to_fallback),
            ("sync_to_ops_alert", self.sync_failure_to_ops_alert),
            ("autopricing_to_metrics", self.autopricing_to_dashboard_metrics),
            ("risk_to_frontdesk", self.reservation_risk_to_frontdesk_badges),
        ]
        for name, func in integrations:
            try:
                results[name] = await func(tenant_id)
            except Exception as e:
                logger.error(f"Integration {name} failed: {e}")
                results[name] = {"status": "error", "error": str(e)}

        await db.cross_module_runs.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "results": {k: v.get("status", "unknown") for k, v in results.items()},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        return {
            "tenant_id": tenant_id,
            "integrations_run": len(results),
            "results": results,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # ── 1. Cancellation Prediction → Overbooking Strategy ──

    async def cancellation_to_overbooking(self, tenant_id: str) -> dict[str, Any]:
        """Use cancellation risk predictions to adjust overbooking strategy."""
        today = date.today().isoformat()
        at_risk = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": {"$gte": today}, "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "id": 1, "check_in": 1, "room_type": 1, "source": 1, "total_amount": 1, "payment_received": 1},
        ).to_list(200)

        # Simple risk scoring
        risk_bookings = []
        expected_cancellations = 0
        for b in at_risk:
            risk = 0.0
            if b.get("source") in ("ota", "booking.com", "expedia"):
                risk += 0.15
            if not b.get("payment_received"):
                risk += 0.20
            if risk > 0.2:
                risk_bookings.append({"booking_id": b["id"], "risk": round(risk, 2), "check_in": b["check_in"], "room_type": b.get("room_type")})
                expected_cancellations += risk

        total_rooms = await db.rooms.count_documents(
            {
                "tenant_id": tenant_id,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            }
        )
        safe_overbook = min(int(expected_cancellations), max(int(total_rooms * 0.05), 1))

        signal = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "signal_type": "overbooking_allowance",
            "expected_cancellations": round(expected_cancellations, 1),
            "safe_overbook_rooms": safe_overbook,
            "at_risk_count": len(risk_bookings),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await db.cross_module_signals.insert_one(signal)

        return {"status": "ok", "safe_overbook_rooms": safe_overbook, "at_risk_bookings": len(risk_bookings), "expected_cancellations": round(expected_cancellations, 1)}

    # ── 2. Booking Probability → Revenue Recommendation Confidence ──

    async def booking_prob_to_revenue_confidence(self, tenant_id: str) -> dict[str, Any]:
        """Adjust revenue recommendation confidence based on booking conversion rates."""
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "status": 1, "source": 1},
        ).to_list(5000)

        total = len(bookings)
        cancelled = sum(1 for b in bookings if b.get("status") == "cancelled")
        conversion_rate = 1.0 - (cancelled / max(total, 1))

        # Confidence multiplier for revenue recommendations
        if conversion_rate > 0.85:
            confidence_boost = 1.1
            note = "Yuksek donusum orani - ML onerileri guvenilir"
        elif conversion_rate > 0.7:
            confidence_boost = 1.0
            note = "Normal donusum orani"
        else:
            confidence_boost = 0.8
            note = "Dusuk donusum - Fiyat onerilerinde ihtiyatli olun"

        signal = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "signal_type": "revenue_confidence_adjustment",
            "conversion_rate": round(conversion_rate, 3),
            "confidence_boost": confidence_boost,
            "note": note,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await db.cross_module_signals.insert_one(signal)

        return {"status": "ok", "conversion_rate": round(conversion_rate, 3), "confidence_boost": confidence_boost, "note": note}

    # ── 3. Comp Set Price Gap → ADR Recommendation ──

    async def compset_gap_to_adr(self, tenant_id: str) -> dict[str, Any]:
        """Generate ADR adjustment signals from competitive price gaps."""
        room_types = await db.rooms.distinct("room_type", {"tenant_id": tenant_id})
        if not room_types:
            return {"status": "ok", "adjustments": [], "note": "No room types found"}

        adjustments = []
        for rt in room_types:
            our_rooms = await db.rooms.find(
                {"tenant_id": tenant_id, "room_type": rt},
                {"_id": 0, "base_price": 1},
            ).to_list(100)
            our_avg = sum(r.get("base_price", 0) for r in our_rooms) / max(len(our_rooms), 1)

            # Get competitor rates
            competitors = await db.competitors.find({"tenant_id": tenant_id, "active": True}, {"_id": 0, "id": 1}).to_list(50)
            comp_rates = []
            for c in competitors:
                rate = await db.competitor_rates.find_one(
                    {"tenant_id": tenant_id, "competitor_id": c["id"], "room_type": rt},
                    {"_id": 0, "rate": 1},
                    sort=[("recorded_at", -1)],
                )
                if rate:
                    comp_rates.append(rate["rate"])

            if not comp_rates:
                continue

            market_avg = sum(comp_rates) / len(comp_rates)
            gap_pct = round((our_avg - market_avg) / max(market_avg, 1) * 100, 1)

            if abs(gap_pct) > 5:
                adjustments.append(
                    {
                        "room_type": rt,
                        "our_rate": round(our_avg, 2),
                        "market_avg": round(market_avg, 2),
                        "gap_pct": gap_pct,
                        "suggested_action": "decrease" if gap_pct > 10 else ("increase" if gap_pct < -10 else "monitor"),
                    }
                )

        if adjustments:
            await db.cross_module_signals.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "signal_type": "compset_adr_adjustment",
                    "adjustments": adjustments,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        return {"status": "ok", "adjustments": adjustments}

    # ── 4. Guest Request Volume → Housekeeping Priority ──

    async def guest_requests_to_hk_priority(self, tenant_id: str) -> dict[str, Any]:
        """Boost housekeeping priority for rooms with high guest request volume."""
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        requests = await db.guest_requests.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}, "status": {"$in": ["open", "assigned"]}},
            {"_id": 0, "room_id": 1, "request_type": 1},
        ).to_list(500)

        # Count requests per room
        room_counts: dict[str, int] = {}
        for r in requests:
            rid = r.get("room_id", "")
            if rid:
                room_counts[rid] = room_counts.get(rid, 0) + 1

        # Rooms with 2+ requests get priority boost
        priority_rooms = [{"room_id": rid, "request_count": cnt} for rid, cnt in room_counts.items() if cnt >= 2]
        priority_rooms.sort(key=lambda x: x["request_count"], reverse=True)

        # Update HK task priorities
        boosted = 0
        for pr in priority_rooms:
            result = await db.housekeeping_tasks.update_many(
                {"tenant_id": tenant_id, "room_id": pr["room_id"], "status": {"$in": ["pending", "assigned"]}},
                {"$set": {"priority": "high", "priority_reason": "guest_request_volume"}},
            )
            boosted += result.modified_count

        return {"status": "ok", "priority_rooms": len(priority_rooms), "tasks_boosted": boosted}

    # ── 5. VIP Arrival → Room Readiness Priority ──

    async def vip_to_room_readiness(self, tenant_id: str) -> dict[str, Any]:
        """Prioritize room readiness for VIP arrivals."""
        today = date.today().isoformat()
        vip_bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": today, "status": {"$in": ["confirmed", "guaranteed"]}, "$or": [{"vip_status": True}, {"tags": "vip"}]},
            {"_id": 0, "id": 1, "room_id": 1, "guest_name": 1},
        ).to_list(50)

        prioritized = 0
        for vb in vip_bookings:
            rid = vb.get("room_id")
            if not rid:
                continue
            result = await db.housekeeping_tasks.update_many(
                {"tenant_id": tenant_id, "room_id": rid, "status": {"$in": ["pending", "assigned"]}},
                {"$set": {"priority": "urgent", "priority_reason": "vip_arrival", "vip_guest": vb.get("guest_name", "")}},
            )
            prioritized += result.modified_count

        return {"status": "ok", "vip_arrivals": len(vip_bookings), "tasks_prioritized": prioritized}

    # ── 6. Night Audit Exception → Escalation Queue ──

    async def audit_exception_to_escalation(self, tenant_id: str) -> dict[str, Any]:
        """Route unresolved night audit exceptions to escalation queue."""
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        exceptions = await db.platform_events.find(
            {"tenant_id": tenant_id, "event_type": "audit_exception", "acknowledged": False, "created_at": {"$gte": cutoff}},
            {"_id": 0, "id": 1, "payload": 1, "created_at": 1},
        ).to_list(100)

        escalated = 0
        for exc in exceptions:
            await db.escalation_queue.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "source": "night_audit",
                    "event_id": exc["id"],
                    "description": exc.get("payload", {}).get("description", "Audit exception"),
                    "priority": "high",
                    "status": "open",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            escalated += 1

        return {"status": "ok", "exceptions_found": len(exceptions), "escalated": escalated}

    # ── 7. Failed Messaging → Guest Journey Fallback ──

    async def failed_messaging_to_fallback(self, tenant_id: str) -> dict[str, Any]:
        """Create fallback tasks for failed guest messages."""
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        failed = await db.message_deliveries.find(
            {"tenant_id": tenant_id, "status": "failed", "created_at": {"$gte": cutoff}},
            {"_id": 0, "id": 1, "channel": 1, "to": 1, "guest_id": 1, "booking_id": 1},
        ).to_list(200)

        fallbacks_created = 0
        for msg in failed:
            # Create a manual follow-up task
            existing = await db.guest_journey_fallbacks.find_one({"delivery_id": msg["id"], "tenant_id": tenant_id})
            if existing:
                continue
            await db.guest_journey_fallbacks.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "delivery_id": msg["id"],
                    "guest_id": msg.get("guest_id"),
                    "booking_id": msg.get("booking_id"),
                    "original_channel": msg.get("channel"),
                    "fallback_action": "manual_contact",
                    "status": "pending",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            fallbacks_created += 1

        return {"status": "ok", "failed_messages": len(failed), "fallbacks_created": fallbacks_created}

    # ── 8. Sync Failure → Operations Alert ──

    async def sync_failure_to_ops_alert(self, tenant_id: str) -> dict[str, Any]:
        """Generate operations alerts from channel sync failures."""
        cutoff = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
        sync_errors = await db.sync_errors.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "id": 1, "channel": 1, "error": 1, "created_at": 1},
        ).to_list(100)

        alerts_created = 0
        if len(sync_errors) >= 3:
            await db.platform_events.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "event_type": "system_health_alert",
                    "payload": {
                        "source": "channel_sync",
                        "error_count": len(sync_errors),
                        "description": f"Son 6 saatte {len(sync_errors)} senkronizasyon hatasi",
                    },
                    "priority": "high" if len(sync_errors) >= 5 else "medium",
                    "created_at": datetime.now(UTC).isoformat(),
                    "acknowledged": False,
                }
            )
            alerts_created = 1

        return {"status": "ok", "sync_errors": len(sync_errors), "alerts_created": alerts_created}

    # ── 9. Revenue Auto-Apply Result → Dashboard Metrics ──

    async def autopricing_to_dashboard_metrics(self, tenant_id: str) -> dict[str, Any]:
        """Aggregate auto-pricing results into dashboard metrics."""
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        recs = await db.pricing_recommendations.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "status": 1, "current_rate": 1, "suggested_rate": 1, "rooms_affected": 1, "auto_applied": 1},
        ).to_list(500)

        metrics = {
            "total_recommendations": len(recs),
            "applied": sum(1 for r in recs if r.get("status") == "applied"),
            "auto_applied": sum(1 for r in recs if r.get("auto_applied")),
            "pending": sum(1 for r in recs if r.get("status") == "pending"),
            "rejected": sum(1 for r in recs if r.get("status") == "rejected"),
            "rolled_back": sum(1 for r in recs if r.get("status") == "rolled_back"),
            "avg_change_pct": 0,
        }

        applied = [r for r in recs if r.get("status") == "applied"]
        if applied:
            changes = []
            for r in applied:
                old = r.get("current_rate", 0)
                new = r.get("suggested_rate", 0)
                if old > 0:
                    changes.append(abs(new - old) / old * 100)
            metrics["avg_change_pct"] = round(sum(changes) / max(len(changes), 1), 1)

        await db.cross_module_signals.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "signal_type": "autopricing_metrics",
                "metrics": metrics,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        return {"status": "ok", "metrics": metrics}

    # ── 10. Reservation Risk Signals → Front Desk Warning Badges ──

    async def reservation_risk_to_frontdesk_badges(self, tenant_id: str) -> dict[str, Any]:
        """Generate front desk warning badges for risky reservations."""
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        arrivals = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": {"$gte": today, "$lte": tomorrow}, "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "room_id": 1, "source": 1, "total_amount": 1, "payment_received": 1, "check_in": 1},
        ).to_list(200)

        badges = []
        for arr in arrivals:
            warnings = []
            if not arr.get("payment_received"):
                warnings.append("no_payment")
            if arr.get("source") in ("ota", "booking.com", "expedia"):
                warnings.append("ota_no_guarantee")
            if not arr.get("room_id"):
                warnings.append("no_room_assigned")

            if warnings:
                badge = {
                    "booking_id": arr["id"],
                    "guest_name": arr.get("guest_name", ""),
                    "check_in": arr.get("check_in"),
                    "warnings": warnings,
                    "badge_level": "high" if len(warnings) >= 2 else "medium",
                }
                badges.append(badge)

        # Store for front desk consumption
        if badges:
            await db.frontdesk_warning_badges.delete_many({"tenant_id": tenant_id})
            for badge in badges:
                await db.frontdesk_warning_badges.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        **badge,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )

        return {"status": "ok", "arrivals_checked": len(arrivals), "warnings_generated": len(badges), "badges": badges[:20]}


# Singleton
cross_module_bus = CrossModuleIntegrationBus()
