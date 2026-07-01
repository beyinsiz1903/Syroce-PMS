"""
Guest Intelligence - Guest analytics, segmentation, churn prediction, and upsell recommendations.
Uses existing guest journey, reservations, messaging, and review data.
"""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)


class GuestLifetimeValueModel:
    """Calculate guest lifetime value based on stay history and spending."""

    async def calculate(self, tenant_id: str, guest_id: str) -> dict[str, Any]:
        # Get all bookings for guest
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "guest_id": guest_id},
            {"_id": 0, "total_amount": 1, "status": 1, "check_in": 1, "check_out": 1, "room_type": 1, "source": 1},
        ).to_list(500)

        completed = [b for b in bookings if b.get("status") in ("checked_out", "checked_in")]
        cancelled = [b for b in bookings if b.get("status") == "cancelled"]

        total_revenue = sum(b.get("total_amount", 0) for b in completed)
        stay_count = len(completed)
        avg_spend = round(total_revenue / max(stay_count, 1), 2)

        # Folio charges
        folio_charges = await db.folio_charges.find(
            {"tenant_id": tenant_id, "guest_id": guest_id, "voided": False},
            {"_id": 0, "amount": 1},
        ).to_list(500)
        ancillary_revenue = sum(c.get("amount", 0) for c in folio_charges)

        # Stay frequency
        if stay_count >= 2:
            dates = sorted([b.get("check_in", "") for b in completed if b.get("check_in")])
            if len(dates) >= 2:
                try:
                    first = date.fromisoformat(dates[0][:10])
                    last = date.fromisoformat(dates[-1][:10])
                    span_months = max((last - first).days / 30, 1)
                    frequency = round(stay_count / span_months, 2)
                except (ValueError, TypeError):
                    frequency = 0
            else:
                frequency = 0
        else:
            frequency = 0

        # Projected LTV (next 12 months)
        projected_annual = round(avg_spend * frequency * 12, 2) if frequency > 0 else avg_spend

        # Value score (0-100)
        value_score = min(100, round((min(total_revenue / 5000, 1) * 30) + (min(stay_count / 10, 1) * 25) + (min(ancillary_revenue / 1000, 1) * 20) + (min(frequency, 1) * 25)))

        return {
            "guest_id": guest_id,
            "total_revenue": round(total_revenue, 2),
            "ancillary_revenue": round(ancillary_revenue, 2),
            "stay_count": stay_count,
            "cancellation_count": len(cancelled),
            "avg_spend_per_stay": avg_spend,
            "stay_frequency_per_month": frequency,
            "projected_annual_value": projected_annual,
            "value_score": value_score,
            "value_tier": "platinum" if value_score > 75 else ("gold" if value_score > 50 else ("silver" if value_score > 25 else "bronze")),
        }


class GuestSegmentationModel:
    """Segment guests based on behavior patterns."""

    async def segment_guest(self, tenant_id: str, guest_id: str) -> dict[str, Any]:
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "guest_id": guest_id},
            {"_id": 0, "total_amount": 1, "status": 1, "source": 1, "check_in": 1, "check_out": 1, "room_type": 1, "purpose": 1},
        ).to_list(500)

        completed = [b for b in bookings if b.get("status") in ("checked_out", "checked_in")]
        stay_count = len(completed)
        total_spend = sum(b.get("total_amount", 0) for b in completed)

        # Determine purpose
        business_count = sum(1 for b in completed if b.get("purpose") in ("business", "corporate"))
        leisure_count = stay_count - business_count

        # Room type preference
        room_types = [b.get("room_type", "Standard") for b in completed]
        preferred_room = max(set(room_types), key=room_types.count) if room_types else "Standard"

        # Source preference
        sources = [b.get("source", "direct") for b in completed]
        preferred_source = max(set(sources), key=sources.count) if sources else "direct"

        # Lead time analysis
        avg_lead_time = 0
        if completed:
            lead_times = []
            for b in completed:
                try:
                    ci = date.fromisoformat(b.get("check_in", "")[:10])
                    lead_times.append((ci - date.today()).days)
                except (ValueError, TypeError):
                    pass
            if lead_times:
                avg_lead_time = round(sum(lead_times) / len(lead_times))

        # Segment assignment
        segment = self._assign_segment(stay_count, total_spend, business_count, leisure_count, preferred_room)

        return {
            "guest_id": guest_id,
            "segment": segment["name"],
            "segment_description": segment["description"],
            "stay_count": stay_count,
            "total_spend": round(total_spend, 2),
            "primary_purpose": "business" if business_count > leisure_count else "leisure",
            "preferred_room_type": preferred_room,
            "preferred_booking_source": preferred_source,
            "avg_lead_time_days": avg_lead_time,
            "behavioral_tags": segment["tags"],
        }

    def _assign_segment(self, stays: int, spend: float, biz: int, leisure: int, room_type: str) -> dict[str, Any]:
        if stays >= 5 and spend > 10000:
            return {"name": "loyal_high_value", "description": "Sadik yuksek degerli misafir", "tags": ["loyal", "high_spender", "priority"]}
        if stays >= 3 and biz > leisure:
            return {"name": "business_regular", "description": "Duzeni is seyahati misafiri", "tags": ["business", "regular", "corporate"]}
        if stays >= 3 and leisure > biz:
            return {"name": "leisure_regular", "description": "Duzenli tatil misafiri", "tags": ["leisure", "regular", "vacation"]}
        if spend > 5000:
            return {"name": "high_spender", "description": "Yuksek harcama yapan misafir", "tags": ["high_spender", "premium"]}
        if stays == 1:
            return {"name": "first_timer", "description": "Ilk kez konaklayan misafir", "tags": ["new", "acquisition"]}
        return {"name": "occasional", "description": "Ara sira gelen misafir", "tags": ["occasional", "retention_target"]}


class ChurnPredictionModel:
    """Predict guest churn risk."""

    async def predict(self, tenant_id: str, guest_id: str) -> dict[str, Any]:
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "guest_id": guest_id},
            {"_id": 0, "status": 1, "check_in": 1, "check_out": 1, "created_at": 1},
        ).to_list(500)

        completed = [b for b in bookings if b.get("status") in ("checked_out", "checked_in")]
        cancelled = [b for b in bookings if b.get("status") == "cancelled"]

        risk_score = 0.0
        factors = []

        # Recency - days since last stay
        if completed:
            last_dates = sorted([b.get("check_out", b.get("check_in", "")) for b in completed], reverse=True)
            try:
                last_stay = date.fromisoformat(last_dates[0][:10])
                days_since = (date.today() - last_stay).days
                if days_since > 365:
                    risk_score += 0.35
                    factors.append({"factor": "long_absence", "impact": 0.35, "detail": f"Son konaklama {days_since} gun once"})
                elif days_since > 180:
                    risk_score += 0.20
                    factors.append({"factor": "medium_absence", "impact": 0.20, "detail": f"Son konaklama {days_since} gun once"})
            except (ValueError, TypeError, IndexError):
                risk_score += 0.15
                factors.append({"factor": "unknown_recency", "impact": 0.15, "detail": "Son konaklama tarihi bilinmiyor"})
        else:
            risk_score += 0.30
            factors.append({"factor": "no_completed_stays", "impact": 0.30, "detail": "Tamamlanmis konaklama yok"})

        # Cancellation ratio
        total = len(bookings)
        cancel_ratio = len(cancelled) / max(total, 1)
        if cancel_ratio > 0.5:
            risk_score += 0.25
            factors.append({"factor": "high_cancellation", "impact": 0.25, "detail": f"Iptal orani: {cancel_ratio:.0%}"})
        elif cancel_ratio > 0.3:
            risk_score += 0.15
            factors.append({"factor": "medium_cancellation", "impact": 0.15, "detail": f"Iptal orani: {cancel_ratio:.0%}"})

        # Declining frequency
        if len(completed) >= 3:
            dates = sorted([b.get("check_in", "") for b in completed])
            try:
                recent_gap = (date.fromisoformat(dates[-1][:10]) - date.fromisoformat(dates[-2][:10])).days
                older_gap = (date.fromisoformat(dates[-2][:10]) - date.fromisoformat(dates[-3][:10])).days
                if recent_gap > older_gap * 1.5:
                    risk_score += 0.15
                    factors.append({"factor": "declining_frequency", "impact": 0.15, "detail": "Konaklama sikligi azaliyor"})
            except (ValueError, TypeError, IndexError):
                pass

        # No upcoming reservation
        future = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "guest_id": guest_id,
                "check_in": {"$gte": date.today().isoformat()},
                "status": {"$in": ["confirmed", "guaranteed"]},
            }
        )
        if future == 0 and len(completed) > 0:
            risk_score += 0.10
            factors.append({"factor": "no_future_booking", "impact": 0.10, "detail": "Gelecek rezervasyon yok"})

        # Guest feedback
        complaints = await db.guest_requests.count_documents(
            {
                "tenant_id": tenant_id,
                "guest_id": guest_id,
                "type": {"$in": ["complaint", "issue"]},
            }
        )
        if complaints >= 2:
            risk_score += 0.15
            factors.append({"factor": "complaints", "impact": 0.15, "detail": f"{complaints} sikayet kaydi"})

        risk_score = min(round(risk_score, 3), 1.0)

        return {
            "guest_id": guest_id,
            "churn_risk_score": risk_score,
            "churn_risk_label": "high" if risk_score > 0.5 else ("medium" if risk_score > 0.25 else "low"),
            "risk_factors": factors,
            "next_best_action": self._next_action(risk_score, factors),
        }

    def _next_action(self, score: float, factors: list) -> str:
        if score > 0.5:
            return "Kisisel teklif gonderin - ozel indirim veya sadakat odulu"
        elif score > 0.25:
            return "Hatirlatma iletisimi gonderin - ozel kampanya bilgilendirmesi"
        return "Standart sadakat programi iletisimine devam"


class UpsellRecommendationModel:
    """Generate upsell recommendations based on guest profile."""

    async def recommend(self, tenant_id: str, guest_id: str, booking_id: str | None = None) -> dict[str, Any]:
        # Guest profile
        guest = await db.guests.find_one({"id": guest_id, "tenant_id": tenant_id}, {"_id": 0})
        if not guest:
            return {"guest_id": guest_id, "recommendations": [], "error": "Guest not found"}

        # Past bookings
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "guest_id": guest_id, "status": {"$in": ["checked_out", "checked_in"]}},
            {"_id": 0, "room_type": 1, "total_amount": 1, "special_requests": 1},
        ).to_list(100)

        # Past folio charges (spending patterns)
        charges = await db.folio_charges.find(
            {"tenant_id": tenant_id, "guest_id": guest_id, "voided": False},
            {"_id": 0, "charge_category": 1, "description": 1, "amount": 1},
        ).to_list(500)

        charge_categories = {}
        for c in charges:
            cat = c.get("charge_category", "other")
            if cat not in charge_categories:
                charge_categories[cat] = 0
            charge_categories[cat] += c.get("amount", 0)

        avg_spend = sum(b.get("total_amount", 0) for b in bookings) / max(len(bookings), 1)
        room_types_used = [b.get("room_type", "Standard") for b in bookings]
        current_type = room_types_used[-1] if room_types_used else "Standard"

        recommendations = []

        # Room upgrade
        upgrade_map = {"Standard": "Deluxe", "Deluxe": "Suite", "Superior": "Suite"}
        next_room = upgrade_map.get(current_type)
        if next_room:
            recommendations.append(
                {
                    "type": "room_upgrade",
                    "title": f"{next_room} Oda Upgrade",
                    "description": f"{current_type} odanizi {next_room} odaya yukseltin",
                    "estimated_value": round(avg_spend * 0.3, 2),
                    "confidence": 0.7 if len(bookings) > 2 else 0.5,
                    "reason": f"Misafir genellikle {current_type} tercih ediyor",
                }
            )

        # F&B upsell if they've used it before
        if charge_categories.get("food", 0) > 0 or charge_categories.get("minibar", 0) > 0:
            recommendations.append(
                {
                    "type": "fnb_package",
                    "title": "Gurme Yemek Paketi",
                    "description": "Ozel akam yemegi ve kahvalti paketi",
                    "estimated_value": round(charge_categories.get("food", 100) * 0.5, 2),
                    "confidence": 0.65,
                    "reason": "Onceki konaklamalarda F&B harcamasi mevcut",
                }
            )

        # Spa upsell
        if charge_categories.get("spa", 0) > 0:
            recommendations.append(
                {
                    "type": "spa_package",
                    "title": "Spa & Wellness Paketi",
                    "description": "Ozel spa ve masaj paketi",
                    "estimated_value": round(charge_categories.get("spa", 80) * 0.4, 2),
                    "confidence": 0.60,
                    "reason": "Onceki konaklamalarda spa kullanimi mevcut",
                }
            )

        # Late checkout for frequent guests
        if len(bookings) >= 3:
            recommendations.append(
                {
                    "type": "late_checkout",
                    "title": "Gec Cikis Garantisi",
                    "description": "14:00 yerine 16:00'ya kadar odanizda kalin",
                    "estimated_value": round(avg_spend * 0.15, 2),
                    "confidence": 0.75,
                    "reason": f"Sadik misafir ({len(bookings)} konaklama)",
                }
            )

        # Early checkin for VIP
        tags = guest.get("tags", [])
        if "vip" in tags or avg_spend > 3000:
            recommendations.append(
                {
                    "type": "early_checkin",
                    "title": "Erken Giris Garantisi",
                    "description": "14:00 yerine 10:00'da odaniza girin",
                    "estimated_value": round(avg_spend * 0.1, 2),
                    "confidence": 0.70,
                    "reason": "VIP/yuksek degerli misafir",
                }
            )

        recommendations.sort(key=lambda x: x["confidence"], reverse=True)

        return {
            "guest_id": guest_id,
            "booking_id": booking_id,
            "guest_name": guest.get("name", ""),
            "recommendations": recommendations[:5],
            "total_upsell_potential": round(sum(r["estimated_value"] for r in recommendations), 2),
        }


class GuestIntelligenceDashboard:
    """Unified guest intelligence dashboard."""

    def __init__(self):
        self.ltv = GuestLifetimeValueModel()
        self.segmentation = GuestSegmentationModel()
        self.churn = ChurnPredictionModel()
        self.upsell = UpsellRecommendationModel()

    async def get_guest_summary(self, tenant_id: str, guest_id: str) -> dict[str, Any]:
        """Get complete intelligence for a single guest."""
        ltv_data = await self.ltv.calculate(tenant_id, guest_id)
        segment = await self.segmentation.segment_guest(tenant_id, guest_id)
        churn = await self.churn.predict(tenant_id, guest_id)
        upsell = await self.upsell.recommend(tenant_id, guest_id)

        # Explainability
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "guest_id": guest_id},
            {"_id": 0, "status": 1},
        ).to_list(500)
        sum(1 for b in bookings if b.get("status") in ("checked_out", "checked_in"))
        cancelled = sum(1 for b in bookings if b.get("status") == "cancelled")

        # Recent sentiment from reviews
        reviews = await db.survey_responses.find(
            {"tenant_id": tenant_id, "guest_id": guest_id},
            {"_id": 0, "overall_rating": 1},
        ).to_list(10)
        avg_rating = round(sum(r.get("overall_rating", 3) for r in reviews) / max(len(reviews), 1), 1) if reviews else None

        # Request volume
        requests = await db.guest_requests.count_documents(
            {
                "tenant_id": tenant_id,
                "guest_id": guest_id,
            }
        )

        return {
            "guest_id": guest_id,
            "lifetime_value": ltv_data,
            "segmentation": segment,
            "churn_prediction": churn,
            "upsell_recommendations": upsell,
            "explainability": {
                "stay_frequency": ltv_data.get("stay_frequency_per_month", 0),
                "average_spend": ltv_data.get("avg_spend_per_stay", 0),
                "recent_sentiment": avg_rating,
                "request_volume": requests,
                "cancellation_history": cancelled,
            },
        }

    async def get_dashboard(self, tenant_id: str, limit: int = 50) -> dict[str, Any]:
        """Get aggregate guest intelligence dashboard."""
        started_at = datetime.now(UTC)

        # Get recent active guests
        from security.encrypted_lookup import decrypt_guest_doc

        guests = (
            await db.guests.find(
                {"tenant_id": tenant_id},
                {"_id": 0, "id": 1, "name": 1, "email": 1, "tags": 1},
            )
            .sort("created_at", -1)
            .limit(limit)
            .to_list(limit)
        )
        guests = [decrypt_guest_doc(g) for g in guests]

        # Calculate scores for all guests
        value_distribution = {"platinum": 0, "gold": 0, "silver": 0, "bronze": 0}
        segment_distribution = {}
        churn_risk_summary = {"high": 0, "medium": 0, "low": 0}
        top_value_guests = []
        high_churn_guests = []
        upsell_opportunities = []

        for guest in guests:
            gid = guest["id"]

            # LTV
            ltv = await self.ltv.calculate(tenant_id, gid)
            tier = ltv.get("value_tier", "bronze")
            value_distribution[tier] = value_distribution.get(tier, 0) + 1

            if ltv.get("value_score", 0) > 50:
                top_value_guests.append(
                    {
                        "guest_id": gid,
                        "name": guest.get("name", ""),
                        "value_score": ltv.get("value_score", 0),
                        "total_revenue": ltv.get("total_revenue", 0),
                        "tier": tier,
                    }
                )

            # Segmentation
            seg = await self.segmentation.segment_guest(tenant_id, gid)
            seg_name = seg.get("segment", "occasional")
            segment_distribution[seg_name] = segment_distribution.get(seg_name, 0) + 1

            # Churn
            churn = await self.churn.predict(tenant_id, gid)
            label = churn.get("churn_risk_label", "low")
            churn_risk_summary[label] = churn_risk_summary.get(label, 0) + 1

            if label == "high":
                high_churn_guests.append(
                    {
                        "guest_id": gid,
                        "name": guest.get("name", ""),
                        "churn_score": churn.get("churn_risk_score", 0),
                        "next_action": churn.get("next_best_action", ""),
                    }
                )

            # Upsell
            upsell = await self.upsell.recommend(tenant_id, gid)
            if upsell.get("total_upsell_potential", 0) > 100:
                upsell_opportunities.append(
                    {
                        "guest_id": gid,
                        "name": guest.get("name", ""),
                        "potential": upsell.get("total_upsell_potential", 0),
                        "top_recommendation": upsell.get("recommendations", [{}])[0].get("title", "") if upsell.get("recommendations") else "",
                    }
                )

        top_value_guests.sort(key=lambda x: x["value_score"], reverse=True)
        high_churn_guests.sort(key=lambda x: x["churn_score"], reverse=True)
        upsell_opportunities.sort(key=lambda x: x["potential"], reverse=True)

        # Persist snapshot
        snapshot = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "model_type": "guest_intelligence",
            "input_window": {"guests_analyzed": len(guests)},
            "output_summary": {
                "value_distribution": value_distribution,
                "high_churn_count": churn_risk_summary.get("high", 0),
                "upsell_opportunities": len(upsell_opportunities),
            },
            "confidence_score": 0.70,
            "generated_at": started_at.isoformat(),
            "version": "1.0",
        }
        await db.guest_intelligence_snapshots.insert_one(snapshot)

        # Log execution
        await db.model_execution_logs.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "run_id": snapshot["id"],
                "model_type": "guest_intelligence",
                "status": "success",
                "output_count": len(guests),
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_ms": int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            }
        )

        return {
            "tenant_id": tenant_id,
            "guests_analyzed": len(guests),
            "value_distribution": value_distribution,
            "segment_distribution": segment_distribution,
            "churn_risk_summary": churn_risk_summary,
            "top_value_guests": top_value_guests[:10],
            "high_churn_guests": high_churn_guests[:10],
            "upsell_opportunities": upsell_opportunities[:10],
            "generated_at": started_at.isoformat(),
        }


# Singleton
guest_intelligence = GuestIntelligenceDashboard()
