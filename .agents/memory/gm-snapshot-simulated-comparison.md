---
name: GM snapshot-enhanced simulated comparison
description: The GM dashboard's prior-period metrics are fabricated offsets, not real history.
---

`GET /api/gm/snapshot-enhanced` (backend/domains/pms/dashboard_router/gm.py,
get_enhanced_snapshot) computes the `today` block from live DB reads, but the
`yesterday` and `last_week` blocks are produced by applying fixed arithmetic
offsets to today's numbers (e.g. occupancy−3, revenue×0.95). They are NOT
queried from historical data.

**Why:** any "vs yesterday" / "vs last week" comparison rendered in a client
(mobile GM dashboard, web) will look plausible but is synthetic — it cannot
show a real trend. Don't present it as truth to stakeholders without flagging.

**How to apply:** to make comparisons real, change the backend to compute prior
periods from bookings/payments/feedback for those dates; the mobile dashboard
(mobile/app/(gm)/index.tsx) already consumes today/yesterday/last_week and will
reflect real numbers with no client change.
