---
name: Stress charge/destructive batch high-4xx = list-route path drift
description: A folio/finance stress batch with a high s400 rate can be a dead list-route 404 cascading into a wrong-id fallback, not a backend bug.
---

A destructive stress batch (e.g. folio charge POST) reporting a high `s400`
share is frequently NOT a backend regression. The pattern:

1. Setup harvests targets from a list route that does not exist → 404 →
   `fetchAllByPrefix` returns `[]` (it breaks on any non-2xx page).
2. The spec falls back to a *different* collection (e.g. bookings) and posts
   mutations keyed by an id that is not actually the target id.
3. The backend correctly rejects: e.g. `FolioHardeningService.post_charge`
   returns `{success:False,"Folio not found"}` → the router raises **HTTP 400**.
   This is **legitimate validation** — the validator must NOT be loosened.

**Why:** the 400 is the contract working as designed; the defect is the spec's
path drift, so the fix is to harvest from the *canonical* route (verify it
exists in the router) so mutations target real, correctly-statused rows.

**How to apply:** before treating a high-4xx destructive batch as a finding,
grep the backend router for the exact list path the setup calls. If it's
absent, the batch is running on a fallback id set — fix the harvest path, don't
patch the backend or seed blindly. Seeded folios carry `stress_prefix` and
already have room/tax charges, so harvesting from `/api/folio/list` also gives
void-charge/reconcile steps real data to hard-assert against.
