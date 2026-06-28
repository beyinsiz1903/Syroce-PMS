"""
Displacement Analysis Engine
=============================
Calculates whether accepting a group/discounted booking is more profitable
than selling those room-nights at the expected transient (rack) rate.

Core metrics:
  - Displaced Revenue: Revenue lost from transient bookings that would have occupied the rooms
  - Proposed Revenue: Revenue from the group/discount scenario
  - Net Displacement: Proposed - Displaced (positive = profitable)
  - Ancillary Revenue: Estimated F&B / Spa / MICE uplift from group bookings
  - RevPAR Impact: How the scenario affects Revenue Per Available Room
  - Opportunity Cost: What the hotel gives up by accepting the block
"""

from datetime import date, timedelta
from typing import Any

from core.database import db


class DisplacementEngine:
    async def _get_total_rooms(self, tenant_id: str) -> int:
        count = await db.rooms.count_documents(
            {
                "tenant_id": tenant_id,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            }
        )
        return max(count, 1)

    async def _get_day_occupancy(self, tenant_id: str, day_str: str) -> dict[str, Any]:
        booked = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "check_in": {"$lte": day_str},
                "check_out": {"$gt": day_str},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            }
        )
        blocked = await db.room_blocks.count_documents(
            {
                "tenant_id": tenant_id,
                "status": "active",
                "start_date": {"$lte": day_str},
                "$or": [{"end_date": None}, {"end_date": {"$gt": day_str}}],
            }
        )
        return {"booked": booked, "blocked": blocked}

    async def _get_historical_adr(self, tenant_id: str, days_back: int = 90) -> float:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        charges = await db.folio_charges.find(
            {
                "tenant_id": tenant_id,
                "category": "room",
                "voided": {"$ne": True},
                "created_at": {"$gte": cutoff},
            },
            {"_id": 0, "amount": 1},
        ).to_list(5000)
        if not charges:
            plans = await db.rate_plans.find(
                {"tenant_id": tenant_id, "is_active": True},
                {"_id": 0, "base_price": 1},
            ).to_list(10)
            return plans[0].get("base_price", 150) if plans else 150.0
        total = sum(c.get("amount", 0) for c in charges)
        return round(total / len(charges), 2)

    async def _get_adr_by_dow(self, tenant_id: str, days_back: int = 90) -> dict[int, float]:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        pipeline = [
            {
                "$match": {
                    "tenant_id": tenant_id,
                    "category": "room",
                    "voided": {"$ne": True},
                    "created_at": {"$gte": cutoff},
                }
            },
            {
                "$addFields": {
                    "parsed_date": {
                        "$dateFromString": {
                            "dateString": {"$substr": ["$created_at", 0, 10]},
                            "format": "%Y-%m-%d",
                            "onError": None,
                        }
                    }
                }
            },
            {"$match": {"parsed_date": {"$ne": None}}},
            {
                "$group": {
                    "_id": {"$dayOfWeek": "$parsed_date"},
                    "avg_amount": {"$avg": "$amount"},
                    "count": {"$sum": 1},
                }
            },
        ]
        try:
            results = await db.folio_charges.aggregate(pipeline).to_list(10)
            dow_map = {}
            for r in results:
                dow_map[r["_id"]] = round(r["avg_amount"], 2)
            return dow_map
        except Exception:
            return {}

    async def _get_cancellation_rate(self, tenant_id: str, days_back: int = 90) -> float:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        total = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "created_at": {"$gte": cutoff},
            }
        )
        cancelled = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "created_at": {"$gte": cutoff},
                "status": "cancelled",
            }
        )
        if total == 0:
            return 0.05
        return round(cancelled / total, 4)

    async def _get_channel_mix(self, tenant_id: str, days_back: int = 90) -> dict[str, Any]:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        bookings = await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "created_at": {"$gte": cutoff},
                "status": {"$nin": ["cancelled"]},
            },
            {"_id": 0, "source": 1, "channel": 1, "total_amount": 1},
        ).to_list(5000)
        channels: dict[str, dict] = {}
        for b in bookings:
            ch = b.get("channel") or b.get("source") or "direct"
            if ch not in channels:
                channels[ch] = {"count": 0, "revenue": 0}
            channels[ch]["count"] += 1
            channels[ch]["revenue"] += b.get("total_amount", 0)
        for ch in channels:
            cnt = channels[ch]["count"]
            channels[ch]["avg_rate"] = round(channels[ch]["revenue"] / cnt, 2) if cnt else 0
        return channels

    async def analyze_displacement(
        self,
        tenant_id: str,
        check_in: str,
        check_out: str,
        rooms_requested: int,
        proposed_rate: float,
        group_name: str = "",
        ancillary_per_room: float = 0,
        commission_pct: float = 0,
    ) -> dict[str, Any]:
        total_rooms = await self._get_total_rooms(tenant_id)
        try:
            ci = date.fromisoformat(check_in)
            co = date.fromisoformat(check_out)
        except (ValueError, TypeError):
            return {"error": "Invalid date format. Use YYYY-MM-DD."}
        num_nights = (co - ci).days
        if num_nights <= 0:
            return {"error": "Check-out must be after check-in"}
        if num_nights > 90:
            return {"error": "Analysis limited to 90 nights maximum"}

        historical_adr = await self._get_historical_adr(tenant_id)
        dow_adr = await self._get_adr_by_dow(tenant_id)
        cancel_rate = await self._get_cancellation_rate(tenant_id)

        daily_analysis = []
        total_displaced_revenue = 0
        total_proposed_revenue = 0
        total_ancillary = 0
        total_opportunity_cost = 0

        for i in range(num_nights):
            night = ci + timedelta(days=i)
            night_str = night.isoformat()
            occ_data = await self._get_day_occupancy(tenant_id, night_str)

            booked = occ_data["booked"]
            blocked = occ_data["blocked"]
            available = max(total_rooms - booked - blocked, 0)
            occ_pct = round((booked / total_rooms) * 100, 1) if total_rooms else 0

            dow = night.isoweekday()
            mongo_dow = dow % 7 + 1
            day_adr = dow_adr.get(mongo_dow, historical_adr)
            if day_adr == 0:
                day_adr = historical_adr

            if occ_pct >= 90:
                demand_mult = 1.35
            elif occ_pct >= 80:
                demand_mult = 1.20
            elif occ_pct >= 70:
                demand_mult = 1.10
            elif occ_pct >= 50:
                demand_mult = 1.0
            elif occ_pct >= 30:
                demand_mult = 0.90
            else:
                demand_mult = 0.80

            expected_transient_rate = round(day_adr * demand_mult, 2)

            sellable_group_rooms = min(rooms_requested, available)
            probability_factor = min(occ_pct / 100, 0.95) * (1 - cancel_rate)
            displaced_rooms = round(rooms_requested * probability_factor, 1)

            displaced_rev = round(displaced_rooms * expected_transient_rate, 2)
            proposed_rev = round(sellable_group_rooms * proposed_rate, 2)
            commission = round(proposed_rev * commission_pct / 100, 2)
            net_proposed = round(proposed_rev - commission, 2)
            ancillary = round(rooms_requested * ancillary_per_room, 2)
            net_displacement = round(net_proposed + ancillary - displaced_rev, 2)
            opp_cost = round(displaced_rev - net_proposed, 2)

            total_displaced_revenue += displaced_rev
            total_proposed_revenue += net_proposed
            total_ancillary += ancillary
            total_opportunity_cost += max(opp_cost, 0)

            daily_analysis.append(
                {
                    "date": night_str,
                    "day_of_week": night.strftime("%A"),
                    "current_occupancy_pct": occ_pct,
                    "available_rooms": available,
                    "total_rooms": total_rooms,
                    "expected_transient_rate": expected_transient_rate,
                    "demand_multiplier": demand_mult,
                    "displaced_rooms": displaced_rooms,
                    "displaced_revenue": displaced_rev,
                    "proposed_revenue": net_proposed,
                    "ancillary_revenue": ancillary,
                    "net_displacement": net_displacement,
                    "recommendation": "accept" if net_displacement > 0 else "reject",
                }
            )

        total_net = round(total_proposed_revenue + total_ancillary - total_displaced_revenue, 2)
        total_room_nights = num_nights * rooms_requested
        proposed_revpar = round(total_proposed_revenue / (total_rooms * num_nights), 2) if total_rooms else 0
        displaced_revpar = round(total_displaced_revenue / (total_rooms * num_nights), 2) if total_rooms else 0
        roi_pct = round((total_net / total_displaced_revenue) * 100, 1) if total_displaced_revenue > 0 else 0

        if total_net > 0:
            overall_rec = "accept"
            confidence = "high" if total_net > total_displaced_revenue * 0.15 else "medium"
        elif total_net > -(total_displaced_revenue * 0.05):
            overall_rec = "conditional"
            confidence = "low"
        else:
            overall_rec = "reject"
            confidence = "high" if abs(total_net) > total_displaced_revenue * 0.15 else "medium"

        return {
            "scenario": {
                "group_name": group_name or "Unnamed Group",
                "check_in": check_in,
                "check_out": check_out,
                "nights": num_nights,
                "rooms_requested": rooms_requested,
                "proposed_rate": proposed_rate,
                "ancillary_per_room": ancillary_per_room,
                "commission_pct": commission_pct,
                "total_room_nights": total_room_nights,
            },
            "summary": {
                "total_displaced_revenue": round(total_displaced_revenue, 2),
                "total_proposed_revenue": round(total_proposed_revenue, 2),
                "total_ancillary_revenue": round(total_ancillary, 2),
                "total_opportunity_cost": round(total_opportunity_cost, 2),
                "net_displacement": total_net,
                "roi_pct": roi_pct,
                "proposed_revpar_impact": proposed_revpar,
                "displaced_revpar_impact": displaced_revpar,
                "revpar_delta": round(proposed_revpar - displaced_revpar, 2),
                "historical_adr": historical_adr,
                "cancellation_rate": round(cancel_rate * 100, 2),
            },
            "recommendation": {
                "action": overall_rec,
                "confidence": confidence,
                "reason": self._get_recommendation_reason(overall_rec, total_net, total_displaced_revenue, confidence),
            },
            "daily_analysis": daily_analysis,
        }

    def _get_recommendation_reason(self, action: str, net: float, displaced: float, confidence: str) -> str:
        if action == "accept":
            return f"Net positive displacement of {net:,.2f}. Group revenue exceeds expected transient displacement."
        elif action == "conditional":
            return f"Marginal scenario ({net:,.2f} net). Consider negotiating higher rate or ancillary commitments."
        else:
            return f"Net negative displacement of {net:,.2f}. Transient demand would generate more revenue."

    async def get_market_overview(self, tenant_id: str, days_forward: int = 14) -> dict[str, Any]:
        total_rooms = await self._get_total_rooms(tenant_id)
        historical_adr = await self._get_historical_adr(tenant_id)
        cancel_rate = await self._get_cancellation_rate(tenant_id)
        channel_mix = await self._get_channel_mix(tenant_id)

        import asyncio as _asyncio

        today = date.today()
        days = [today + timedelta(days=i) for i in range(days_forward)]
        # Run all per-day occupancy lookups in parallel.
        occ_results = await _asyncio.gather(*[self._get_day_occupancy(tenant_id, d.isoformat()) for d in days])
        forecast = []
        for d, occ in zip(days, occ_results, strict=True):
            booked = occ["booked"]
            blocked = occ["blocked"]
            available = max(total_rooms - booked - blocked, 0)
            occ_pct = round((booked / total_rooms) * 100, 1)
            if occ_pct >= 85:
                displacement_risk = "high"
            elif occ_pct >= 65:
                displacement_risk = "medium"
            else:
                displacement_risk = "low"
            forecast.append(
                {
                    "date": d.isoformat(),
                    "day_of_week": d.strftime("%A"),
                    "booked": booked,
                    "blocked": blocked,
                    "available": available,
                    "occupancy_pct": occ_pct,
                    "displacement_risk": displacement_risk,
                }
            )

        total_channel_bookings = sum(c["count"] for c in channel_mix.values())
        channel_summary = []
        for ch, data in channel_mix.items():
            channel_summary.append(
                {
                    "channel": ch,
                    "bookings": data["count"],
                    "share_pct": round((data["count"] / total_channel_bookings) * 100, 1) if total_channel_bookings else 0,
                    "avg_rate": data["avg_rate"],
                    "revenue": round(data["revenue"], 2),
                }
            )
        channel_summary.sort(key=lambda x: x["revenue"], reverse=True)

        return {
            "total_rooms": total_rooms,
            "historical_adr": historical_adr,
            "cancellation_rate_pct": round(cancel_rate * 100, 2),
            "forecast": forecast,
            "channel_mix": channel_summary,
        }

    async def compare_scenarios(
        self,
        tenant_id: str,
        check_in: str,
        check_out: str,
        rooms_requested: int,
        scenarios: list[dict],
    ) -> dict[str, Any]:
        results = []
        for sc in scenarios[:5]:
            analysis = await self.analyze_displacement(
                tenant_id=tenant_id,
                check_in=check_in,
                check_out=check_out,
                rooms_requested=rooms_requested,
                proposed_rate=sc.get("rate", 100),
                group_name=sc.get("name", ""),
                ancillary_per_room=sc.get("ancillary", 0),
                commission_pct=sc.get("commission", 0),
            )
            results.append(
                {
                    "scenario_name": sc.get("name", ""),
                    "proposed_rate": sc.get("rate", 100),
                    "net_displacement": analysis["summary"]["net_displacement"],
                    "roi_pct": analysis["summary"]["roi_pct"],
                    "recommendation": analysis["recommendation"]["action"],
                    "confidence": analysis["recommendation"]["confidence"],
                    "total_proposed": analysis["summary"]["total_proposed_revenue"],
                    "total_displaced": analysis["summary"]["total_displaced_revenue"],
                    "total_ancillary": analysis["summary"]["total_ancillary_revenue"],
                }
            )

        results.sort(key=lambda x: x["net_displacement"], reverse=True)
        best = results[0] if results else None

        return {
            "check_in": check_in,
            "check_out": check_out,
            "rooms_requested": rooms_requested,
            "scenarios": results,
            "best_scenario": best["scenario_name"] if best else None,
        }

    async def get_history(self, tenant_id: str, limit: int = 20) -> list[dict]:
        analyses = (
            await db.displacement_analyses.find(
                {"tenant_id": tenant_id},
                {"_id": 0},
            )
            .sort("created_at", -1)
            .to_list(limit)
        )
        return analyses

    async def save_analysis(self, tenant_id: str, analysis: dict, user_email: str) -> dict:
        import uuid
        from datetime import UTC, datetime

        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": user_email,
            **analysis,
        }
        await db.displacement_analyses.insert_one(doc)
        return {"id": doc["id"], "status": "saved"}
