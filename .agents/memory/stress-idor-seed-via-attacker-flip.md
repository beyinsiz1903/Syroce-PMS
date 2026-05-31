---
name: Exercise cross-tenant IDOR without pilot mutation by flipping attacker/victim
description: How a stress spec proves a cross-tenant IDOR guard when the pilot tenant has no records to harvest and pilot_drift=0 forbids seeding into pilot.
---

A cross-tenant IDOR step that "harvests a pilot record, then attacks it with the
stress token" goes vacuous (SKIP + P2) whenever the pilot tenant has no such
record — and you are NOT allowed to seed into pilot (pilot_drift=0).

**The flip:** make the STRESS tenant the victim instead. Earlier serial steps
already create real records in the stress tenant via real endpoints (e.g. a
hurdle via POST /api/hurdle-rates/, an autopilot queue item via
POST /api/revenue-autopilot/process). Reuse those ids and have the PILOT token
play attacker (PATCH/DELETE/approve them). The tenant guard must deny (≥400/404).

**Why this is safe and honest:** the attacker (pilot) only ever issues denied
mutations, so nothing in pilot changes → pilot_drift stays 0. If the guard were
actually broken, the bleed would land on the *stress* tenant and surface as a
hard FAIL — not as silent pilot corruption. It is deterministic (the victim
records are guaranteed to exist from prior serial steps) so the IDOR vector is
always exercised, never a vacuous skip.

**How to apply:** when a stress IDOR step depends on harvesting victim records
from a tenant you cannot mutate, flip the direction — seed in the writable
tenant, attack from the other token. Guard the block with the seeded-id list and
fall back to P2 only if the upstream create genuinely returned non-2xx that run.
