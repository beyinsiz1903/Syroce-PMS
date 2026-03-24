"""
Operational AI - Predictive models for hotel operations.
Models: check-in load, housekeeping workload, room readiness ETA, maintenance failure risk.
Integrates with existing housekeeping, front desk, maintenance, and event systems.
"""
import logging
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import db

logger = logging.getLogger(__name__)


class CheckInLoadPredictor:
    """Predict check-in volume by hour to optimize front desk staffing."""

    async def predict(self, tenant_id: str, target_date: Optional[str] = None) -> Dict[str, Any]:
        target = date.fromisoformat(target_date) if target_date else date.today()
        target_s = target.isoformat()

        # Arrivals for target date
        arrivals = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": target_s,
             "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "room_type": 1,
             "estimated_arrival_time": 1, "source": 1, "check_in": 1},
        ).to_list(500)

        total_arrivals = len(arrivals)

        # Build hourly distribution from historical patterns
        dow = target.weekday()
        hist_start = (target - timedelta(days=90)).isoformat()
        hist_bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": {"$gte": hist_start, "$lt": target_s},
             "status": {"$in": ["checked_in", "checked_out"]}},
            {"_id": 0, "check_in": 1, "checked_in_at": 1},
        ).to_list(5000)

        # Count check-ins by hour historically for same day-of-week
        hour_counts = dict.fromkeys(range(24), 0)
        hist_total = 0
        for b in hist_bookings:
            ci_date_str = b.get("check_in", "")
            try:
                ci_date = date.fromisoformat(ci_date_str[:10])
                if ci_date.weekday() == dow:
                    ci_at = b.get("checked_in_at", "")
                    if ci_at and "T" in ci_at:
                        hour = int(ci_at.split("T")[1][:2])
                        hour_counts[hour] += 1
                        hist_total += 1
            except (ValueError, IndexError):
                continue

        # Default distribution if no history
        if hist_total < 5:
            hour_counts = dict.fromkeys(range(24), 0)
            for h in [14, 15, 16]:
                hour_counts[h] = 30
            for h in [12, 13, 17, 18]:
                hour_counts[h] = 15
            for h in [10, 11, 19, 20]:
                hour_counts[h] = 5
            hist_total = sum(hour_counts.values())

        # Distribute today's arrivals across hours
        hourly_forecast = {}
        for h in range(8, 23):  # Only operating hours
            pct = hour_counts[h] / max(hist_total, 1)
            predicted = round(total_arrivals * pct, 1)
            hourly_forecast[f"{h:02d}:00"] = {
                "predicted_arrivals": predicted,
                "pressure": "high" if predicted > total_arrivals * 0.2 else (
                    "medium" if predicted > total_arrivals * 0.1 else "low"),
            }

        # Peak hour
        peak_hour = max(hourly_forecast.items(), key=lambda x: x[1]["predicted_arrivals"])[0] if hourly_forecast else "15:00"

        # Arrival pressure score (0-100)
        pressure_score = min(100, round(total_arrivals / max(
            await db.rooms.count_documents({"tenant_id": tenant_id}), 1) * 100))

        return {
            "tenant_id": tenant_id,
            "target_date": target_s,
            "total_expected_arrivals": total_arrivals,
            "peak_hour": peak_hour,
            "arrival_pressure_score": pressure_score,
            "hourly_forecast": hourly_forecast,
            "staffing_recommendation": self._staffing_rec(total_arrivals, pressure_score),
        }

    def _staffing_rec(self, arrivals: int, pressure: int) -> Dict[str, Any]:
        if arrivals <= 5:
            agents = 1
            note = "Dusuk yogunluk - minimum personel yeterli"
        elif arrivals <= 15:
            agents = 2
            note = "Normal yogunluk - standart kadro"
        elif arrivals <= 30:
            agents = 3
            note = "Yuksek yogunluk - ek personel gerekli"
        else:
            agents = max(4, arrivals // 10)
            note = "Cok yuksek yogunluk - tam kadro + destek"
        return {"recommended_agents": agents, "note": note, "pressure_score": pressure}


class HousekeepingWorkloadPredictor:
    """Predict housekeeping workload for staffing and scheduling."""

    async def predict(self, tenant_id: str, target_date: Optional[str] = None) -> Dict[str, Any]:
        target = date.fromisoformat(target_date) if target_date else date.today()
        target_s = target.isoformat()
        (target + timedelta(days=1)).isoformat()

        # Departures (rooms needing deep clean)
        departures = await db.bookings.count_documents({
            "tenant_id": tenant_id, "check_out": target_s,
            "status": {"$in": ["checked_in", "confirmed", "guaranteed"]},
        })

        # Stayovers (rooms needing refresh)
        stayovers = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "check_in": {"$lt": target_s}, "check_out": {"$gt": target_s},
            "status": {"$in": ["checked_in"]},
        })

        # Arrivals (rooms needing preparation)
        arrivals = await db.bookings.count_documents({
            "tenant_id": tenant_id, "check_in": target_s,
            "status": {"$in": ["confirmed", "guaranteed"]},
        })

        await db.rooms.count_documents({"tenant_id": tenant_id})

        # Workload calculation (minutes)
        departure_time = 45  # minutes per departure clean
        stayover_time = 20   # minutes per stayover
        arrival_prep_time = 30  # minutes per arrival prep

        total_minutes = (departures * departure_time +
                        stayovers * stayover_time +
                        arrivals * arrival_prep_time)
        total_hours = round(total_minutes / 60, 1)

        # Staff needed (8-hour shifts)
        staff_needed = max(1, math.ceil(total_hours / 7))  # 7 effective hours per shift

        # Priority rooms
        priority_rooms = []
        # VIP arrivals get priority
        vip_bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": target_s,
             "status": {"$in": ["confirmed", "guaranteed"]},
             "$or": [{"vip": True}, {"tags": "vip"}]},
            {"_id": 0, "room_id": 1, "guest_name": 1},
        ).to_list(50)
        for vb in vip_bookings:
            priority_rooms.append({
                "room_id": vb.get("room_id"), "reason": "VIP arrival",
                "priority": "critical",
            })

        # Workload heatmap by floor/zone
        rooms_data = await db.rooms.find(
            {"tenant_id": tenant_id}, {"_id": 0, "id": 1, "floor": 1, "room_type": 1}
        ).to_list(1000)

        floor_workload = {}
        for r in rooms_data:
            floor = str(r.get("floor", "1"))
            if floor not in floor_workload:
                floor_workload[floor] = {"rooms": 0, "estimated_minutes": 0}
            floor_workload[floor]["rooms"] += 1
            floor_workload[floor]["estimated_minutes"] += 25  # avg

        # Shift pressure score (0-100)
        max_capacity = staff_needed * 7 * 60  # max minutes available
        shift_pressure = min(100, round(total_minutes / max(max_capacity, 1) * 100))

        return {
            "tenant_id": tenant_id,
            "target_date": target_s,
            "workload": {
                "departures": departures,
                "stayovers": stayovers,
                "arrivals": arrivals,
                "total_rooms_to_clean": departures + stayovers + arrivals,
                "total_minutes": total_minutes,
                "total_hours": total_hours,
            },
            "staffing_recommendation": {
                "staff_needed": staff_needed,
                "shift_pressure_score": shift_pressure,
                "note": self._hk_note(shift_pressure),
            },
            "priority_rooms": priority_rooms,
            "floor_heatmap": floor_workload,
        }

    def _hk_note(self, pressure: int) -> str:
        if pressure > 80:
            return "Kritik yogunluk - ekstra personel cagirin"
        elif pressure > 60:
            return "Yuksek yogunluk - tum personel aktif olmali"
        elif pressure > 40:
            return "Normal yogunluk - standart kadro yeterli"
        return "Dusuk yogunluk - personel rotasyonu mumkun"


class RoomReadinessPredictor:
    """Predict when rooms will be ready based on housekeeping status."""

    async def predict(self, tenant_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        today_s = date.today().isoformat()

        # Rooms needing cleaning
        dirty_rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "status": {"$in": ["dirty", "inspected", "occupied"]}},
            {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "status": 1, "floor": 1},
        ).to_list(500)

        # Active HK tasks
        active_tasks = await db.housekeeping_tasks.find(
            {"tenant_id": tenant_id, "status": {"$in": ["assigned", "in_progress"]}},
            {"_id": 0, "room_id": 1, "status": 1, "assigned_to": 1, "started_at": 1},
        ).to_list(500)
        task_map = {t.get("room_id"): t for t in active_tasks}

        # Today's arrivals needing rooms
        arriving_bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": today_s,
             "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "room_id": 1, "guest_name": 1, "estimated_arrival_time": 1},
        ).to_list(500)
        arrival_room_ids = {b.get("room_id") for b in arriving_bookings}

        predictions = []
        for room in dirty_rooms:
            rid = room["id"]
            task = task_map.get(rid)

            # ETA calculation
            if task and task.get("status") == "in_progress" and task.get("started_at"):
                try:
                    started = datetime.fromisoformat(task["started_at"])
                    elapsed = (now - started).total_seconds() / 60
                    avg_clean_time = 35  # minutes
                    remaining = max(avg_clean_time - elapsed, 5)
                except Exception:
                    remaining = 30
            elif task and task.get("status") == "assigned":
                remaining = 45  # assigned but not started
            else:
                remaining = 60  # not yet assigned

            eta_time = now + timedelta(minutes=remaining)
            is_arrival_room = rid in arrival_room_ids

            predictions.append({
                "room_id": rid,
                "room_number": room.get("room_number", rid),
                "room_type": room.get("room_type", "Standard"),
                "floor": room.get("floor", 1),
                "current_status": room.get("status", "unknown"),
                "has_hk_task": bool(task),
                "task_status": task.get("status") if task else "unassigned",
                "estimated_ready_minutes": round(remaining),
                "estimated_ready_time": eta_time.strftime("%H:%M"),
                "is_arrival_room": is_arrival_room,
                "priority": "critical" if is_arrival_room else "normal",
            })

        predictions.sort(key=lambda x: (not x["is_arrival_room"], x["estimated_ready_minutes"]))

        return {
            "tenant_id": tenant_id,
            "timestamp": now.isoformat(),
            "total_rooms_pending": len(predictions),
            "arrival_rooms_pending": sum(1 for p in predictions if p["is_arrival_room"]),
            "avg_eta_minutes": round(
                sum(p["estimated_ready_minutes"] for p in predictions) / max(len(predictions), 1)),
            "predictions": predictions,
        }


class MaintenanceFailureRiskPredictor:
    """Predict equipment/room maintenance failure risk."""

    async def predict(self, tenant_id: str) -> Dict[str, Any]:
        # Get maintenance history
        cutoff = (date.today() - timedelta(days=180)).isoformat()
        work_orders = await db.maintenance_work_orders.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "room_id": 1, "category": 1, "priority": 1,
             "status": 1, "created_at": 1},
        ).to_list(2000)

        # Count issues per room
        room_issues: Dict[str, List] = {}
        for wo in work_orders:
            rid = wo.get("room_id", "unknown")
            if rid not in room_issues:
                room_issues[rid] = []
            room_issues[rid].append(wo)

        # Risk scoring
        risk_items = []
        for rid, issues in room_issues.items():
            risk_score = 0.0
            factors = []

            # Frequency factor
            count = len(issues)
            if count >= 5:
                risk_score += 0.35
                factors.append({"factor": "high_frequency", "impact": 0.35,
                               "detail": f"{count} bakim talebi (6 ay)"})
            elif count >= 3:
                risk_score += 0.20
                factors.append({"factor": "medium_frequency", "impact": 0.20,
                               "detail": f"{count} bakim talebi (6 ay)"})

            # Recency factor
            recent = sorted(issues, key=lambda x: x.get("created_at", ""), reverse=True)
            if recent:
                last_date = recent[0].get("created_at", "")
                try:
                    days_since = (date.today() - date.fromisoformat(last_date[:10])).days
                    if days_since < 14:
                        risk_score += 0.25
                        factors.append({"factor": "recent_issue", "impact": 0.25,
                                       "detail": f"Son ariza {days_since} gun once"})
                except (ValueError, TypeError):
                    pass

            # Priority escalation
            high_priority = sum(1 for i in issues if i.get("priority") in ("high", "critical", "urgent"))
            if high_priority >= 2:
                risk_score += 0.20
                factors.append({"factor": "priority_escalation", "impact": 0.20,
                               "detail": f"{high_priority} yuksek oncelikli ariza"})

            risk_score = min(round(risk_score, 3), 1.0)
            if risk_score >= 0.3:
                risk_items.append({
                    "room_id": rid,
                    "risk_score": risk_score,
                    "risk_level": "high" if risk_score > 0.6 else (
                        "medium" if risk_score > 0.3 else "low"),
                    "issue_count": count,
                    "risk_factors": factors,
                    "recommendation": self._maint_rec(risk_score),
                })

        risk_items.sort(key=lambda x: x["risk_score"], reverse=True)

        return {
            "tenant_id": tenant_id,
            "total_rooms_analyzed": len(room_issues),
            "at_risk_rooms": len(risk_items),
            "high_risk_count": sum(1 for r in risk_items if r["risk_level"] == "high"),
            "risk_items": risk_items[:30],
            "alert_candidates": [r for r in risk_items if r["risk_level"] == "high"][:10],
        }

    def _maint_rec(self, score: float) -> str:
        if score > 0.6:
            return "Acil onleyici bakim planlayin - tekrarlayan ariza riski yuksek"
        elif score > 0.3:
            return "Yakin donemde bakim kontrolu onerilir"
        return "Normal bakim takvimine devam"


class OperationalAIDashboard:
    """Unified operational AI dashboard."""

    def __init__(self):
        self.checkin = CheckInLoadPredictor()
        self.housekeeping = HousekeepingWorkloadPredictor()
        self.readiness = RoomReadinessPredictor()
        self.maintenance = MaintenanceFailureRiskPredictor()

    async def get_dashboard(self, tenant_id: str,
                            target_date: Optional[str] = None) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc)

        checkin_data = await self.checkin.predict(tenant_id, target_date)
        hk_data = await self.housekeeping.predict(tenant_id, target_date)
        readiness_data = await self.readiness.predict(tenant_id)
        maint_data = await self.maintenance.predict(tenant_id)

        # Persist snapshot
        snapshot = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "model_type": "operational_ai",
            "input_window": {"target_date": target_date or date.today().isoformat()},
            "output_summary": {
                "expected_arrivals": checkin_data.get("total_expected_arrivals", 0),
                "hk_rooms_to_clean": hk_data.get("workload", {}).get("total_rooms_to_clean", 0),
                "rooms_pending_readiness": readiness_data.get("total_rooms_pending", 0),
                "maintenance_at_risk": maint_data.get("at_risk_rooms", 0),
            },
            "confidence_score": 0.75,
            "generated_at": started_at.isoformat(),
            "version": "1.0",
        }
        await db.operational_ai_snapshots.insert_one(snapshot)

        # Log execution
        await db.model_execution_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "run_id": snapshot["id"],
            "model_type": "operational_ai",
            "status": "success",
            "output_count": 4,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
        })

        return {
            "tenant_id": tenant_id,
            "check_in_load": checkin_data,
            "housekeeping_workload": hk_data,
            "room_readiness": readiness_data,
            "maintenance_risk": maint_data,
            "generated_at": started_at.isoformat(),
        }

    async def get_staffing_recommendations(self, tenant_id: str,
                                            target_date: Optional[str] = None) -> Dict[str, Any]:
        checkin = await self.checkin.predict(tenant_id, target_date)
        hk = await self.housekeeping.predict(tenant_id, target_date)

        return {
            "tenant_id": tenant_id,
            "front_desk": checkin.get("staffing_recommendation", {}),
            "housekeeping": hk.get("staffing_recommendation", {}),
            "combined_pressure": round(
                (checkin.get("arrival_pressure_score", 0) +
                 hk.get("staffing_recommendation", {}).get("shift_pressure_score", 0)) / 2),
        }

    async def get_workload_heatmap(self, tenant_id: str,
                                    target_date: Optional[str] = None) -> Dict[str, Any]:
        hk = await self.housekeeping.predict(tenant_id, target_date)
        checkin = await self.checkin.predict(tenant_id, target_date)

        return {
            "tenant_id": tenant_id,
            "housekeeping_floors": hk.get("floor_heatmap", {}),
            "checkin_hourly": checkin.get("hourly_forecast", {}),
            "workload_summary": hk.get("workload", {}),
        }


# Singleton
operational_ai = OperationalAIDashboard()
