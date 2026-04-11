"""
PMS Router — DECOMPOSED.

All routes have been extracted to dedicated modules:
  - pms_availability.py  : Room blocks + availability (CRITICAL core)
  - pms_reservations.py  : Reservation details, search, mutations
  - pms_room_details.py  : Room notes, minibar, enhanced details
  - pms_room_queue.py    : Early arrival queue management
  - pms_services.py      : Staff tasks, allotments, groups, setup
  - pms_bookings.py      : Booking CRUD (Stage 2)
  - pms_dashboard.py     : Dashboard endpoints (Stage 2)
  - pms_rooms.py         : Room CRUD (pre-existing)
  - pms_guests.py        : Guest CRUD (pre-existing)
  - pms_shared.py        : Pure helper functions

This file retains the router object for backward compatibility
with any code that imports `from routers.pms import router`.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["pms"])
