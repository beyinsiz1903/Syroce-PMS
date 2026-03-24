"""
Guest Journey Layer - Pre-Arrival, Stay Management, Messaging, Review Capture, Guest Dashboard.
Enterprise guest experience management integrated with PMS.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from core.database import db


class GuestJourneyService:
    """Manages the complete guest journey from pre-arrival to post-departure."""

    # ── PRE-ARRIVAL ──

    async def submit_online_checkin(self, tenant_id: str, booking_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit online check-in with preferences and arrival details."""
        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        record = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": booking.get("guest_id"),
            "arrival_time": data.get("arrival_time"),
            "flight_number": data.get("flight_number"),
            "room_preference": data.get("room_preference"),
            "bed_type": data.get("bed_type"),
            "floor_preference": data.get("floor_preference"),
            "special_requests": data.get("special_requests"),
            "dietary_restrictions": data.get("dietary_restrictions"),
            "accessibility_needs": data.get("accessibility_needs"),
            "passport_number": data.get("passport_number"),
            "nationality": data.get("nationality"),
            "status": "submitted",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.guest_journey_checkins.insert_one(record)

        await db.bookings.update_one(
            {"id": booking_id},
            {"$set": {
                "online_checkin_status": "submitted",
                "estimated_arrival_time": data.get("arrival_time"),
            }},
        )

        return {"success": True, "checkin_id": record["id"], "status": "submitted"}

    async def get_pre_arrival_status(self, tenant_id: str, booking_id: str) -> Dict[str, Any]:
        """Get pre-arrival status for a booking."""
        record = await db.guest_journey_checkins.find_one(
            {"tenant_id": tenant_id, "booking_id": booking_id}, {"_id": 0}
        )
        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "room_id": 1, "status": 1},
        )
        return {
            "booking": booking,
            "online_checkin": record,
            "checkin_completed": record is not None,
        }

    # ── STAY MANAGEMENT ──

    async def create_guest_request(self, tenant_id: str, booking_id: str,
                                    request_type: str, description: str,
                                    priority: str = "normal", room_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a guest request (housekeeping, maintenance, concierge, room service)."""
        valid_types = ["housekeeping", "maintenance", "concierge", "room_service", "amenity", "complaint"]
        if request_type not in valid_types:
            return {"success": False, "error": f"Invalid request type. Valid: {valid_types}"}

        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        request = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": booking.get("guest_id"),
            "room_id": room_id or booking.get("room_id"),
            "request_type": request_type,
            "description": description,
            "priority": priority,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "assigned_to": None,
            "resolved_at": None,
            "resolution_notes": None,
        }
        await db.guest_requests.insert_one(request)

        return {"success": True, "request_id": request["id"], "status": "open"}

    async def update_request_status(self, tenant_id: str, request_id: str,
                                     new_status: str, user_id: str,
                                     notes: Optional[str] = None) -> Dict[str, Any]:
        """Update guest request status."""
        valid_statuses = ["open", "assigned", "in_progress", "resolved", "closed", "escalated"]
        if new_status not in valid_statuses:
            return {"success": False, "error": f"Invalid status. Valid: {valid_statuses}"}

        update = {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user_id}
        if new_status == "resolved":
            update["resolved_at"] = datetime.now(timezone.utc).isoformat()
        if notes:
            update["resolution_notes"] = notes

        result = await db.guest_requests.update_one(
            {"id": request_id, "tenant_id": tenant_id},
            {"$set": update},
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Request not found"}
        return {"success": True, "request_id": request_id, "new_status": new_status}

    async def assign_request(self, tenant_id: str, request_id: str, assignee_id: str, user_id: str) -> Dict[str, Any]:
        """Assign a guest request to a staff member."""
        result = await db.guest_requests.update_one(
            {"id": request_id, "tenant_id": tenant_id},
            {"$set": {
                "assigned_to": assignee_id,
                "status": "assigned",
                "assigned_at": datetime.now(timezone.utc).isoformat(),
                "assigned_by": user_id,
            }},
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Request not found"}
        return {"success": True, "request_id": request_id, "assigned_to": assignee_id}

    async def get_guest_requests(self, tenant_id: str, booking_id: Optional[str] = None,
                                  status: Optional[str] = None, request_type: Optional[str] = None,
                                  limit: int = 50) -> Dict[str, Any]:
        """Get guest requests with optional filters."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if booking_id:
            query["booking_id"] = booking_id
        if status:
            query["status"] = status
        if request_type:
            query["request_type"] = request_type

        requests = await db.guest_requests.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

        return {"count": len(requests), "requests": requests}

    # ── MESSAGING ──

    async def send_message(self, tenant_id: str, booking_id: str, channel: str,
                            message_type: str, content: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Send a message to a guest via email/SMS/WhatsApp."""
        valid_channels = ["email", "sms", "whatsapp", "in_app"]
        if channel not in valid_channels:
            return {"success": False, "error": f"Invalid channel. Valid: {valid_channels}"}

        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"_id": 0, "guest_id": 1, "guest_name": 1},
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        msg = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": booking.get("guest_id"),
            "channel": channel,
            "message_type": message_type,
            "content": content,
            "direction": "outbound",
            "status": "sent",
            "sent_by": user_id,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.guest_messages.insert_one(msg)

        return {"success": True, "message_id": msg["id"], "channel": channel, "status": "sent"}

    async def get_messages(self, tenant_id: str, booking_id: str) -> Dict[str, Any]:
        """Get all messages for a booking."""
        messages = await db.guest_messages.find(
            {"tenant_id": tenant_id, "booking_id": booking_id},
            {"_id": 0},
        ).sort("sent_at", -1).to_list(200)

        return {"booking_id": booking_id, "count": len(messages), "messages": messages}

    async def get_auto_message_templates(self, tenant_id: str) -> Dict[str, Any]:
        """Get automated message templates for guest journey touchpoints."""
        templates = await db.guest_message_templates.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(100)

        if not templates:
            # Return default templates
            templates = [
                {"id": "tpl_pre_arrival", "name": "Pre-Arrival Welcome", "trigger": "pre_arrival_3d",
                 "channel": "email", "subject": "Hosgeldiniz! Konaklamaniz yaklasti",
                 "body": "Sayin {guest_name}, {check_in} tarihindeki konaklamaniz icin heyecanla bekliyoruz."},
                {"id": "tpl_checkin_confirm", "name": "Check-in Confirmation", "trigger": "check_in",
                 "channel": "email", "subject": "Check-in Onaylandi",
                 "body": "Sayin {guest_name}, {room_number} numarali odaniza basariyla giris yaptiniz."},
                {"id": "tpl_mid_stay", "name": "Mid-Stay Satisfaction", "trigger": "mid_stay",
                 "channel": "in_app", "subject": "Konaklamaniz nasil gidiyor?",
                 "body": "Sayin {guest_name}, herhangi bir ihtiyaciniz var mi?"},
                {"id": "tpl_checkout", "name": "Checkout Thank You", "trigger": "checkout",
                 "channel": "email", "subject": "Tesekkurler!",
                 "body": "Sayin {guest_name}, konaklamaniz icin tesekkur ederiz. Gorusleriniz bizim icin onemli."},
                {"id": "tpl_review_request", "name": "Review Request", "trigger": "post_checkout_1d",
                 "channel": "email", "subject": "Deneyiminizi paylasir misiniz?",
                 "body": "Sayin {guest_name}, konaklamanizi degerlendirmenizi rica ederiz."},
            ]
        return {"count": len(templates), "templates": templates}

    # ── REVIEW CAPTURE ──

    async def request_review(self, tenant_id: str, booking_id: str) -> Dict[str, Any]:
        """Send a post-checkout review request."""
        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"_id": 0, "guest_id": 1, "guest_name": 1, "check_out": 1},
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        review_request = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": booking.get("guest_id"),
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "responded": False,
        }
        await db.guest_review_requests.insert_one(review_request)

        return {"success": True, "review_request_id": review_request["id"]}

    async def submit_review(self, tenant_id: str, booking_id: str, rating: int,
                             comment: Optional[str] = None, categories: Optional[Dict] = None) -> Dict[str, Any]:
        """Submit a guest review."""
        if not (1 <= rating <= 5):
            return {"success": False, "error": "Rating must be 1-5"}

        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"_id": 0, "guest_id": 1, "guest_name": 1, "room_id": 1},
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        review = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": booking.get("guest_id"),
            "room_id": booking.get("room_id"),
            "overall_rating": rating,
            "comment": comment,
            "category_ratings": categories or {},
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.guest_reviews.insert_one(review)

        # Update review request if exists
        await db.guest_review_requests.update_one(
            {"tenant_id": tenant_id, "booking_id": booking_id},
            {"$set": {"responded": True, "responded_at": datetime.now(timezone.utc).isoformat()}},
        )

        return {"success": True, "review_id": review["id"], "rating": rating}

    async def get_reputation_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get reputation tracking summary."""
        reviews = await db.guest_reviews.find(
            {"tenant_id": tenant_id}, {"_id": 0, "overall_rating": 1, "category_ratings": 1, "submitted_at": 1}
        ).to_list(5000)

        if not reviews:
            return {"total_reviews": 0, "average_rating": 0, "distribution": {}, "recent_trend": []}

        total = len(reviews)
        avg = round(sum(r.get("overall_rating", 0) for r in reviews) / total, 2)

        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in reviews:
            rating = r.get("overall_rating", 3)
            if rating in dist:
                dist[rating] += 1

        # Monthly trend
        monthly = {}
        for r in reviews:
            month = (r.get("submitted_at") or "")[:7]
            if month:
                if month not in monthly:
                    monthly[month] = {"count": 0, "total_rating": 0}
                monthly[month]["count"] += 1
                monthly[month]["total_rating"] += r.get("overall_rating", 0)

        trend = [{"month": m, "avg_rating": round(d["total_rating"] / d["count"], 2), "count": d["count"]}
                 for m, d in sorted(monthly.items())[-12:]]

        return {
            "total_reviews": total,
            "average_rating": avg,
            "distribution": dist,
            "recent_trend": trend,
        }

    # ── GUEST DASHBOARD ──

    async def get_guest_satisfaction_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        """Comprehensive guest satisfaction dashboard."""
        # Open requests
        open_requests = await db.guest_requests.count_documents(
            {"tenant_id": tenant_id, "status": {"$in": ["open", "assigned", "in_progress"]}}
        )
        # Average resolution time
        resolved = await db.guest_requests.find(
            {"tenant_id": tenant_id, "status": {"$in": ["resolved", "closed"]}, "resolved_at": {"$exists": True}},
            {"_id": 0, "created_at": 1, "resolved_at": 1, "request_type": 1},
        ).to_list(1000)

        resolution_times = []
        for r in resolved:
            try:
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                res = datetime.fromisoformat(r["resolved_at"].replace("Z", "+00:00"))
                minutes = (res - created).total_seconds() / 60
                resolution_times.append({"type": r.get("request_type"), "minutes": minutes})
            except Exception:
                pass

        avg_resolution_min = round(sum(rt["minutes"] for rt in resolution_times) / len(resolution_times), 1) if resolution_times else 0

        # By type
        by_type = {}
        for rt in resolution_times:
            t = rt["type"]
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(rt["minutes"])
        avg_by_type = {t: round(sum(mins) / len(mins), 1) for t, mins in by_type.items()}

        # Request queue
        queue = await db.guest_requests.find(
            {"tenant_id": tenant_id, "status": {"$in": ["open", "assigned", "in_progress"]}},
            {"_id": 0},
        ).sort("created_at", 1).limit(30).to_list(30)

        # Reputation
        reputation = await self.get_reputation_summary(tenant_id)

        # Today's arrivals with online checkin status
        today = date.today().isoformat()
        today_arrivals = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": today, "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "room_id": 1, "online_checkin_status": 1, "vip": 1},
        ).to_list(200)

        online_checkin_count = sum(1 for a in today_arrivals if a.get("online_checkin_status") == "submitted")

        return {
            "open_requests": open_requests,
            "avg_resolution_minutes": avg_resolution_min,
            "avg_resolution_by_type": avg_by_type,
            "request_queue": queue,
            "reputation": reputation,
            "today_arrivals": len(today_arrivals),
            "online_checkins": online_checkin_count,
        }
