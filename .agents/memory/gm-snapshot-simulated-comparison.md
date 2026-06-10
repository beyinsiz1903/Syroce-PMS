---
name: GM snapshot-enhanced prior-period comparison
description: How the GM dashboard's today/yesterday/last_week metrics are computed (now real, with caveats).
---

`GET /api/gm/snapshot-enhanced` (backend/domains/pms/dashboard_router/gm.py,
`get_enhanced_snapshot` + helper `_compute_period_metrics`) now computes
yesterday and last_week from REAL per-date queries, not fixed arithmetic
offsets. All three periods go through the same date-parameterised helper so the
deltas are apples-to-apples.

**Why the helper is shared / definitions changed:** booking `status` reflects
*current* state, so you cannot reconstruct a past day's arrivals by filtering
`status=='checked_in'` (a booking that arrived last week is `checked_out` now,
giving ~0). So all periods define:
- arrivals = `check_in == date` & status NOT IN [cancelled, no_show]
- departures = `check_out == date` & status NOT IN [cancelled, no_show]
- occupancy = bookings spanning the night (`check_in <= date < check_out`,
  non-cancelled) / total_rooms (no per-date room-status history exists)
- revenue = payments in [date, date+1) ; complaints = feedback(rating<=2) in [date, date+1)
This changed today's occupancy/arrivals/departures method from the old
room-status / currently-checked-in counts — intentional, required for honest
deltas. Date fields are ISO strings, so range/exact string matches are correct.

**pending_tasks has NO per-date history:** it stays the current high/urgent
backlog count for all three periods (honest 0 delta, flat trend) rather than a
fabricated offset. Do not invent a historical value for it.

**How to apply:** the mobile dashboard (mobile/app/(gm)/index.tsx) consumes
today/yesterday/last_week unchanged and now renders real deltas.
