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

**Vacuous-404 trap (fake-green):** the flipped victim id MUST be a REAL resource
owned by the writable tenant, harvested from that tenant's own list/detail
endpoint. A *synthesized* or wrong-keyed id (e.g. using a booking_id as a
folio_id when the backend resolves folios strictly by `{id, tenant_id}` and ids
are uuid4) produces a 404 by non-existence — which the guard-PASS branch happily
counts as "tenant guard enforced" even though the guard was never exercised.
Always confirm the harvest endpoint path resolves (probe it) and returns the
victim collection's real id; `/api/folio/list` returns `{folios:[{id}]}`, while
`/api/folios` is a dead route (404) that silently yields an empty harvest →
vacuous SKIP.

**Don't count 5xx/0 as PASS:** a cross-tenant guard PASS branch must require a
4xx (`>=400 && <500`); classifying *any* non-2xx as PASS lets a 5xx/timeout
fake-green. Route 5xx/0 to REVIEW, not PASS.
