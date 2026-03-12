"""
Competitive Set Analysis - Competitor price tracking, market positioning,
and ADR adjustment suggestions based on competitive intelligence.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from core.database import db


class CompetitorPriceTracker:
    """Track and analyze competitor pricing."""

    async def add_competitor(self, tenant_id: str, name: str, star_rating: int = 4,
                              room_types: Optional[List[str]] = None,
                              location: Optional[str] = None) -> Dict[str, Any]:
        """Add a competitor hotel to the comp set."""
        competitor = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": name,
            "star_rating": star_rating,
            "room_types": room_types or ["Standard", "Deluxe", "Suite"],
            "location": location,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.competitors.insert_one(competitor)
        return {"success": True, "competitor_id": competitor["id"], "name": name}

    async def get_competitors(self, tenant_id: str) -> Dict[str, Any]:
        """Get all competitors in the comp set."""
        competitors = await db.competitors.find(
            {"tenant_id": tenant_id, "active": True}, {"_id": 0}
        ).to_list(50)
        return {"count": len(competitors), "competitors": competitors}

    async def record_competitor_rate(self, tenant_id: str, competitor_id: str,
                                      room_type: str, rate: float, date_str: str,
                                      source: str = "manual") -> Dict[str, Any]:
        """Record a competitor's rate for a specific date."""
        record = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "competitor_id": competitor_id,
            "room_type": room_type,
            "rate": rate,
            "date": date_str,
            "source": source,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.competitor_rates.insert_one(record)
        return {"success": True, "rate_id": record["id"]}

    async def get_competitor_rates(self, tenant_id: str, target_date: Optional[str] = None,
                                    competitor_id: Optional[str] = None) -> Dict[str, Any]:
        """Get competitor rates with optional filters."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if target_date:
            query["date"] = target_date
        if competitor_id:
            query["competitor_id"] = competitor_id

        rates = await db.competitor_rates.find(
            query, {"_id": 0}
        ).sort("recorded_at", -1).to_list(500)

        # Enrich with competitor names
        competitors = {c["id"]: c["name"] for c in await db.competitors.find(
            {"tenant_id": tenant_id}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(50)}

        for r in rates:
            r["competitor_name"] = competitors.get(r.get("competitor_id"), "Bilinmeyen")

        return {"count": len(rates), "rates": rates}

    async def bulk_record_rates(self, tenant_id: str, rates: List[Dict]) -> Dict[str, Any]:
        """Bulk record competitor rates."""
        recorded = 0
        for r in rates:
            await self.record_competitor_rate(
                tenant_id, r["competitor_id"], r.get("room_type", "Standard"),
                r["rate"], r["date"], r.get("source", "bulk_import")
            )
            recorded += 1
        return {"success": True, "recorded": recorded}


class MarketPositioning:
    """Analyze hotel's position relative to competitors."""

    async def get_market_position(self, tenant_id: str, room_type: str = "Standard") -> Dict[str, Any]:
        """Analyze market position relative to comp set."""
        # Our rates
        our_rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "room_type": room_type},
            {"_id": 0, "base_price": 1},
        ).to_list(100)
        our_avg_rate = sum(r.get("base_price", 0) for r in our_rooms) / max(len(our_rooms), 1)

        # Competitor rates (most recent)
        competitors = await db.competitors.find(
            {"tenant_id": tenant_id, "active": True}, {"_id": 0}
        ).to_list(50)

        comp_rates = []
        for comp in competitors:
            latest_rate = await db.competitor_rates.find_one(
                {"tenant_id": tenant_id, "competitor_id": comp["id"], "room_type": room_type},
                {"_id": 0},
                sort=[("recorded_at", -1)],
            )
            if latest_rate:
                comp_rates.append({
                    "competitor_id": comp["id"],
                    "competitor_name": comp["name"],
                    "star_rating": comp.get("star_rating", 4),
                    "rate": latest_rate["rate"],
                    "date": latest_rate.get("date"),
                })

        if not comp_rates:
            return {
                "tenant_id": tenant_id,
                "room_type": room_type,
                "our_rate": round(our_avg_rate, 2),
                "market_data": "no_competitor_data",
                "recommendation": "Rakip fiyat verisi ekleyin",
            }

        market_avg = sum(c["rate"] for c in comp_rates) / len(comp_rates)
        market_min = min(c["rate"] for c in comp_rates)
        market_max = max(c["rate"] for c in comp_rates)

        # Position index: our rate vs market avg
        position_index = round((our_avg_rate / market_avg) * 100, 1) if market_avg > 0 else 100
        if position_index > 115:
            position = "premium"
        elif position_index > 105:
            position = "above_market"
        elif position_index >= 95:
            position = "at_market"
        elif position_index >= 85:
            position = "below_market"
        else:
            position = "budget"

        # Rate index per competitor
        comp_analysis = []
        for c in comp_rates:
            diff = round(our_avg_rate - c["rate"], 2)
            diff_pct = round((diff / c["rate"]) * 100, 1) if c["rate"] > 0 else 0
            comp_analysis.append({
                **c,
                "rate_difference": diff,
                "difference_pct": diff_pct,
            })

        comp_analysis.sort(key=lambda x: x["rate"])

        return {
            "tenant_id": tenant_id,
            "room_type": room_type,
            "our_rate": round(our_avg_rate, 2),
            "market_average": round(market_avg, 2),
            "market_min": round(market_min, 2),
            "market_max": round(market_max, 2),
            "position_index": position_index,
            "market_position": position,
            "competitors": comp_analysis,
        }

    async def get_rate_parity_check(self, tenant_id: str) -> Dict[str, Any]:
        """Check rate parity across competitors and channels."""
        room_types = await db.rooms.distinct("room_type", {"tenant_id": tenant_id})
        if not room_types:
            room_types = ["Standard"]

        parity_results = []
        for rt in room_types:
            position = await self.get_market_position(tenant_id, rt)
            parity_results.append({
                "room_type": rt,
                "our_rate": position.get("our_rate", 0),
                "market_average": position.get("market_average", 0),
                "position_index": position.get("position_index", 100),
                "market_position": position.get("market_position", "unknown"),
            })

        return {"tenant_id": tenant_id, "room_types": parity_results}


class ADRAdjustmentEngine:
    """Generate ADR adjustment suggestions based on competitive intelligence."""

    async def get_adr_suggestions(self, tenant_id: str) -> Dict[str, Any]:
        """Generate ADR adjustment suggestions per room type."""
        positioning = MarketPositioning()
        room_types = await db.rooms.distinct("room_type", {"tenant_id": tenant_id})
        if not room_types:
            room_types = ["Standard"]

        suggestions = []
        for rt in room_types:
            market_pos = await positioning.get_market_position(tenant_id, rt)
            our_rate = market_pos.get("our_rate", 0)
            market_avg = market_pos.get("market_average", 0)
            position = market_pos.get("market_position", "unknown")

            if position == "premium" and market_avg > 0:
                suggested = round(market_avg * 1.12, 2)
                action = "slight_decrease"
                reason = "Premium konumdasiniz ama cok yuksek fark gelir kaybina yol acabilir"
            elif position == "above_market":
                suggested = round(our_rate, 2)
                action = "maintain"
                reason = "Pazarin ustunde iyi bir konumdasiniz"
            elif position == "at_market":
                suggested = round(market_avg * 1.05, 2)
                action = "slight_increase"
                reason = "Pazar ortalamasinda, hafif fiyat artisi deneyin"
            elif position == "below_market":
                suggested = round(market_avg * 0.98, 2)
                action = "increase"
                reason = "Pazarin altindasiniz, fiyat artisi onerilir"
            elif position == "budget":
                suggested = round(market_avg * 0.92, 2)
                action = "increase"
                reason = "Cok dusuk fiyatta, deger alginizi dusurmeyin"
            else:
                suggested = our_rate
                action = "no_data"
                reason = "Yeterli rakip verisi yok"

            revenue_impact = round((suggested - our_rate) * 30, 2)  # Estimated 30 room-nights

            suggestions.append({
                "room_type": rt,
                "current_rate": our_rate,
                "market_average": market_avg,
                "suggested_rate": suggested,
                "action": action,
                "reason": reason,
                "estimated_monthly_impact": revenue_impact,
                "market_position": position,
            })

        total_impact = sum(s["estimated_monthly_impact"] for s in suggestions)
        return {
            "tenant_id": tenant_id,
            "suggestions": suggestions,
            "total_estimated_monthly_impact": round(total_impact, 2),
        }

    async def apply_suggestion(self, tenant_id: str, room_type: str,
                                new_rate: float, user_id: str) -> Dict[str, Any]:
        """Apply an ADR adjustment suggestion."""
        result = await db.rooms.update_many(
            {"tenant_id": tenant_id, "room_type": room_type},
            {"$set": {"base_price": new_rate, "rate_updated_at": datetime.now(timezone.utc).isoformat()}},
        )

        # Audit
        await db.competitive_rate_adjustments.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "room_type": room_type,
            "new_rate": new_rate,
            "applied_by": user_id,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "rooms_affected": result.modified_count,
        })

        return {"success": True, "room_type": room_type, "new_rate": new_rate,
                "rooms_updated": result.modified_count}


class CompetitiveSetDashboard:
    """Unified competitive intelligence dashboard."""

    def __init__(self):
        self.tracker = CompetitorPriceTracker()
        self.positioning = MarketPositioning()
        self.adr_engine = ADRAdjustmentEngine()

    async def get_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        """Get comprehensive competitive analysis dashboard."""
        competitors = await self.tracker.get_competitors(tenant_id)
        parity = await self.positioning.get_rate_parity_check(tenant_id)
        suggestions = await self.adr_engine.get_adr_suggestions(tenant_id)

        return {
            "tenant_id": tenant_id,
            "comp_set": competitors,
            "rate_parity": parity,
            "adr_suggestions": suggestions,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
