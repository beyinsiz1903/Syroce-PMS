"""
HotelRunner Mapper - Transforms between HotelRunner data and canonical models.
This is the central translation layer that absorbs all provider-specific quirks.

Supports:
  - REST/JSON reservation payloads → CanonicalReservation
  - Canonical inventory/rates → HotelRunner push format
"""
from typing import Dict, Any, Optional, List

from ...domain.models.canonical import (
    CanonicalReservation, CanonicalGuest, ReservationStatus,
    MealPlan, PriceBreakdown, TaxBreakdown,
    CanonicalRoomType, CanonicalRatePlan, InventorySlice, RestrictionSet,
)


_MEAL_PLAN_MAP = {
    "": MealPlan.RO,
    "RO": MealPlan.RO,
    "BB": MealPlan.BB,
    "HB": MealPlan.HB,
    "FB": MealPlan.FB,
    "AI": MealPlan.AI,
    "room-only": MealPlan.RO,
    "bed-breakfast": MealPlan.BB,
    "half-board": MealPlan.HB,
    "full-board": MealPlan.FB,
    "all-inclusive": MealPlan.AI,
    "1": MealPlan.BB,
    "2": MealPlan.HB,
    "3": MealPlan.FB,
    "4": MealPlan.AI,
    "14": MealPlan.RO,
}

# HotelRunner REST/JSON state → canonical status
_STATE_MAP = {
    "reserved": ReservationStatus.CONFIRMED,
    "confirmed": ReservationStatus.CONFIRMED,
    "canceled": ReservationStatus.CANCELLED,
    "cancelled": ReservationStatus.CANCELLED,
    # Legacy OTA status codes (backward compat)
    "Commit": ReservationStatus.CONFIRMED,
    "Modify": ReservationStatus.MODIFIED,
    "Cancel": ReservationStatus.CANCELLED,
    "Book": ReservationStatus.CONFIRMED,
    "Provisional": ReservationStatus.PROVISIONAL,
}


class HotelRunnerMapper:
    """Maps HotelRunner-specific data to/from canonical domain models."""

    def reservation_to_canonical(self, raw: Dict[str, Any]) -> CanonicalReservation:
        """
        Convert HotelRunner REST/JSON reservation dict to CanonicalReservation.

        Handles the full JSON payload structure from GET /api/v2/apps/reservations:
          reservation_id, hr_number, state, modified, requires_response,
          guest/firstname/lastname, address, billing_address, rooms, daily_prices,
          payments, total/currency/tax_total/extras_total, message_uid
        """
        # ── Guest mapping ───────────────────────────────────────────
        address = raw.get("address") or {}
        billing_addr = raw.get("billing_address") or {}

        guest = CanonicalGuest(
            first_name=raw.get("firstname", ""),
            last_name=raw.get("lastname", ""),
            email=address.get("email", ""),
            phone=address.get("phone", ""),
            nationality=raw.get("country", ""),
            national_id=raw.get("guest_national_id", ""),
            is_citizen=raw.get("guest_is_citizen", False),
            city=address.get("city", ""),
            state=address.get("state", ""),
            country=address.get("country", ""),
            country_code=address.get("country_code", ""),
            street=address.get("street", ""),
            street_2=address.get("street_2", ""),
            postal_code=address.get("postal_code", ""),
            billing_address=billing_addr,
        )

        # ── Status mapping ──────────────────────────────────────────
        hr_state = raw.get("state", "reserved")
        is_modified = raw.get("modified", False)
        status = _STATE_MAP.get(hr_state, ReservationStatus.CONFIRMED)
        if is_modified and status != ReservationStatus.CANCELLED:
            status = ReservationStatus.MODIFIED

        # ── Rooms extraction ────────────────────────────────────────
        rooms = raw.get("rooms") or []
        first_room = rooms[0] if rooms else {}

        # Primary room/rate codes from first room
        room_type_id = first_room.get("inv_code", "") or first_room.get("code", "")
        rate_plan_id = first_room.get("rate_plan_code", "") or first_room.get("rate_code", "")
        room_type_name = first_room.get("name", "") or first_room.get("name_presentation", "")

        # Occupancy from first room
        adult_count = first_room.get("total_adult", 0) or 1
        child_count = len(first_room.get("child_ages", []))
        child_ages = first_room.get("child_ages", [])

        # Meal plan from first room
        meal_plan_raw = first_room.get("meal_plan", "")
        meal_plan = _MEAL_PLAN_MAP.get(meal_plan_raw, MealPlan.RO)

        non_refundable = first_room.get("non_refundable", False)

        # ── Daily prices aggregation ────────────────────────────────
        all_daily_prices = []
        price_breakdown = []
        for room in rooms:
            for dp in room.get("daily_prices") or []:
                all_daily_prices.append(dp)
                price_breakdown.append(PriceBreakdown(
                    date=dp.get("date", ""),
                    base_rate=float(dp.get("original_price", 0) or 0),
                    sell_rate=float(dp.get("price", 0) or 0),
                    net_rate=float(dp.get("price", 0) or 0),
                    currency=raw.get("currency", "TRY"),
                ))

        # ── Tax breakdown from room extras ──────────────────────────
        tax_breakdown = []
        for room in rooms:
            for extra in room.get("extras") or []:
                if extra.get("included_in_price") and not extra.get("is_extra"):
                    tax_breakdown.append(TaxBreakdown(
                        tax_name=extra.get("name", ""),
                        tax_amount=float(extra.get("price", 0) or 0),
                        is_inclusive=True,
                        currency=raw.get("currency", "TRY"),
                    ))

        # ── Special requests from room comments ─────────────────────
        special_requests_parts = []
        if raw.get("note"):
            special_requests_parts.append(raw["note"])
        for room in rooms:
            for comment in room.get("comments") or []:
                body = comment.get("body", "")
                if body and body not in special_requests_parts:
                    special_requests_parts.append(body)
        special_requests = "; ".join(special_requests_parts)

        # ── Dates from reservation or first room ────────────────────
        arrival = raw.get("checkin_date", "") or first_room.get("checkin_date", "")
        departure = raw.get("checkout_date", "") or first_room.get("checkout_date", "")

        # ── Pricing ─────────────────────────────────────────────────
        total_amount = float(raw.get("total", 0) or 0)
        sub_total = float(raw.get("sub_total", 0) or 0)
        tax_total = float(raw.get("tax_total", 0) or 0)
        extras_total = float(raw.get("extras_total", 0) or 0)
        paid_amount = float(raw.get("paid_amount", 0) or 0)
        currency = raw.get("currency", "TRY")

        # ── Payment ─────────────────────────────────────────────────
        payment_type = raw.get("payment", "")
        payments = raw.get("payments") or []

        # ── Build canonical reservation ─────────────────────────────
        return CanonicalReservation(
            external_id=str(raw.get("reservation_id", "")),
            hr_number=raw.get("hr_number", ""),
            confirmation_number=raw.get("hr_number", ""),
            channel_name=raw.get("channel_display", "") or raw.get("channel", ""),
            channel_code=raw.get("channel", ""),
            status=status,
            message_uid=raw.get("message_uid", ""),
            requires_ack=bool(raw.get("requires_response", False)),
            modified=is_modified,
            guest=guest,
            arrival_date=arrival,
            departure_date=departure,
            room_type_id=room_type_id,
            room_type_name=room_type_name,
            rate_plan_id=rate_plan_id,
            adult_count=adult_count,
            child_count=child_count,
            child_ages=child_ages,
            room_count=int(raw.get("total_rooms", 1) or 1),
            total_amount=total_amount,
            sub_total=sub_total,
            tax_total=tax_total,
            extras_total=extras_total,
            paid_amount=paid_amount,
            currency=currency,
            price_breakdown=price_breakdown,
            tax_breakdown=tax_breakdown,
            daily_prices=all_daily_prices,
            payment_type=payment_type,
            payments=payments,
            meal_plan=meal_plan,
            non_refundable=non_refundable,
            special_requests=special_requests,
            rooms=rooms,
            booked_at=raw.get("completed_at"),
            modified_at=raw.get("updated_at") if is_modified else None,
            raw_provider_data=raw,
        )

    def extract_room_references(self, raw: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract external room/rate/inventory references from HotelRunner rooms.

        Returns list of dicts with:
          - code: room code
          - inv_code: inventory allocation group code
          - rate_code: rate code
          - rate_plan_code: rate plan code
        """
        refs = []
        for room in raw.get("rooms") or []:
            refs.append({
                "code": room.get("code", ""),
                "inv_code": room.get("inv_code", ""),
                "rate_code": room.get("rate_code", ""),
                "rate_plan_code": room.get("rate_plan_code", ""),
                "availability_group": room.get("availability_group", ""),
                "room_name": room.get("name", ""),
            })
        return refs

    # ─── Inventory Push (unchanged) ──────────────────────────────────

    def inventory_to_push_updates(
        self,
        slices: List[InventorySlice],
        mapping_lookup: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Convert canonical inventory slices to HotelRunner push format."""
        updates = []
        for sl in slices:
            external_code = mapping_lookup.get(sl.room_type_id)
            if not external_code:
                continue
            updates.append({
                "room_type_code": external_code,
                "date_start": sl.date,
                "date_end": sl.date,
                "available": sl.available,
            })
        return updates

    def rates_to_push_updates(
        self,
        rates: List[Dict[str, Any]],
        room_mapping: Dict[str, str],
        rate_mapping: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Convert canonical rate data to HotelRunner push format."""
        updates = []
        for r in rates:
            ext_room = room_mapping.get(r.get("room_type_id", ""))
            ext_rate = rate_mapping.get(r.get("rate_plan_id", ""))
            if not ext_room or not ext_rate:
                continue
            updates.append({
                "room_type_code": ext_room,
                "rate_plan_code": ext_rate,
                "date_start": r.get("date", ""),
                "date_end": r.get("date", ""),
                "amount_after_tax": r.get("sell_rate", 0.0),
                "currency": r.get("currency", "TRY"),
            })
        return updates

    def restrictions_to_push_updates(
        self,
        restrictions: List[RestrictionSet],
        room_mapping: Dict[str, str],
        rate_mapping: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Convert canonical restrictions to HotelRunner push format."""
        updates = []
        for r in restrictions:
            ext_room = room_mapping.get(r.room_type_id)
            ext_rate = rate_mapping.get(r.rate_plan_id)
            if not ext_room or not ext_rate:
                continue
            update = {
                "room_type_code": ext_room,
                "rate_plan_code": ext_rate,
                "date_start": r.date,
                "date_end": r.date,
                "available": 0 if r.closed else None,
                "restriction_status": "Close" if r.closed else "Open",
            }
            if r.min_stay is not None:
                update["min_stay"] = r.min_stay
            if r.max_stay is not None:
                update["max_stay"] = r.max_stay
            updates.append(update)
        return updates
