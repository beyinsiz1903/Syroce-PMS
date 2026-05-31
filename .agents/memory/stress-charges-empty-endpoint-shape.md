---
name: Persistent charges_empty is an endpoint-shape problem, not sample depletion
description: If a void/charge harvest still finds empty charges after shifting the sample window, the real cause is the detail endpoint shape/path, not window overlap.
---

A stress void/refund test that reports `charges_empty=N/N` (no charges on every
sampled folio) is often *first* blamed on serial sample-window depletion (an
earlier destructive batch consumed the same `slice(0,N)` folios). Shifting the
window (e.g. `slice(10,15)`) is the depletion fix.

**But if it stays empty after the window shift**, depletion was the wrong root
cause. The real issue is usually that the *detail endpoint the spec calls* does
not return the charges in the shape/path the spec reads.

**How to apply:** before shifting windows again or seeding, verify the detail
endpoint actually returns `charges[]`. Concrete trap: the folio-mass spec calls
`GET /api/pms-core/folio/detail/{id}` and reads `body.charges`, while the seeded
charges are confirmed present (linked by `folio_id`+`booking_id`, `voided=false`)
and the *finance* endpoint `GET /api/folio/{id}` returns `{folio,charges,payments,
balance}`. A path/shape mismatch yields empty charges regardless of the window.
The specs already capture `detailShapeSnap`/`chargeShapeSnap` — read that snapshot
from the CI report to decide SPEC-DRIFT (wrong path) vs REAL PRODUCT GAP (endpoint
omits charges). Don't reshuffle windows blind.
