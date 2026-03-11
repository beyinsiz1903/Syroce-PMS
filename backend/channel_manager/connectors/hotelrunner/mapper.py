"""
HotelRunner Mapper - Transforms between HotelRunner data and canonical models.
This is the central translation layer that absorbs all provider-specific quirks.
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
    "1": MealPlan.BB,
    "2": MealPlan.HB,
    "3": MealPlan.FB,
    "4": MealPlan.AI,
    "14": MealPlan.RO,
}

_STATUS_MAP = {
    "Commit": ReservationStatus.CONFIRMED,
    "Modify": ReservationStatus.MODIFIED,
    "Cancel": ReservationStatus.CANCELLED,
    "Book": ReservationStatus.CONFIRMED,
    "Provisional": ReservationStatus.PROVISIONAL,
}


class HotelRunnerMapper:
    """Maps HotelRunner-specific data to/from canonical domain models."""

    def reservation_to_canonical(self, raw: Dict[str, Any]) -> CanonicalReservation:
        """Convert parsed HotelRunner reservation dict to CanonicalReservation."""
        guest_data = raw.get("guest", {})
        guest = CanonicalGuest(
            first_name=guest_data.get("first_name", ""),
            last_name=guest_data.get("last_name", ""),
            email=guest_data.get("email", ""),
            phone=guest_data.get("phone", ""),
        )

        status = _STATUS_MAP.get(raw.get("res_status", "Commit"), ReservationStatus.CONFIRMED)
        meal_plan = _MEAL_PLAN_MAP.get(raw.get("meal_plan", ""), MealPlan.RO)

        return CanonicalReservation(
            external_id=raw.get("external_id", ""),
            confirmation_number=raw.get("confirmation_number", ""),
            channel_name="HotelRunner",
            status=status,
            guest=guest,
            arrival_date=raw.get("arrival_date", ""),
            departure_date=raw.get("departure_date", ""),
            room_type_id=raw.get("room_type_code", ""),
            rate_plan_id=raw.get("rate_plan_code", ""),
            adult_count=raw.get("adult_count", 1),
            child_count=raw.get("child_count", 0),
            total_amount=raw.get("total_amount", 0.0),
            currency=raw.get("currency", "TRY"),
            payment_type=raw.get("payment_type", ""),
            meal_plan=meal_plan,
            special_requests=raw.get("special_requests", ""),
            raw_provider_data=raw,
        )

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
