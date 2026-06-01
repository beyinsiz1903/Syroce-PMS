---
name: Booking cross-check by id must use full-detail, not list search
description: Why /pms/bookings?search=<UUID> can never find a booking, and the reliable id-based lookup
---

# Cross-check a booking by id via /reservations/{id}/full-detail, not the list search

To verify a single booking's state (e.g. status==checked_out after checkout),
GET `/api/pms/reservations/{booking_id}/full-detail` — it does a direct
`find_one({id, tenant_id})` and returns `{"booking": {...status...}}`, tenant-
scoped, no search/cache. Wrong-tenant token → 404 (no cross-tenant leak).

**Do NOT** use `GET /pms/bookings?search=<bookingUUID>`:
- The `search` param is index-serviceable PREFIX-only on the `guest_name_lower`
  and `booking_number_lower` companion fields (the id/room_number substring
  branches were dropped). A booking UUID never prefix-matches those → 0 results.
- Worse, the quick-booking create path does NOT store `guest_name` (nor
  `guest_name_lower`) on the booking document — `guest_name` is enriched at
  READ time from the guests collection. So even searching by the guest name
  won't find a freshly created booking.

**Why:** a stress/e2e cross-check that searched by UUID always got
`found=undefined` and false-FAILed as "state drift" — it was test-drift from a
legitimate backend search-indexing change, not a real regression.

**How to apply:** any test/probe needing one booking by id uses full-detail (or
another id-keyed endpoint). Reserve list `search` for guest-name/booking-number
prefix UX only. A non-ok full-detail after a successful checkout is a HARD fail
(booking must exist) — do not soft-skip it.
