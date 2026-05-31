---
name: charges_empty in a void/charge harvest — confirm path+shape, then it's data-state vs 404
description: When a void/charge stress test reports charges_empty=N/N, don't keep re-blaming endpoint path/shape drift; once those are confirmed to match the backend, the only remaining split (genuinely-empty 200 vs folio-not-found 404) is decided by the spec's CI detailShapeSnap, not by anything reproducible in the repl.
---

A stress void/refund test reporting `charges_empty=N/N` (no charges on every sampled
folio) tends to get blamed, in order, on (1) serial sample-window depletion, then
(2) detail-endpoint path/shape drift. Both are seductive but were *ruled out* for the
folio-mass spec: the detail path the spec calls and the `charges[]` key it reads were
each confirmed to match the backend route and the service's return shape. So treat
"the spec calls the wrong path / parses the wrong shape" as **already disproven** —
re-verify quickly, then stop re-deriving it.

Once path+shape match, `charges_empty=N/N` is exactly one of two things, and a
well-written spec already classifies it correctly (data-state → REVIEW+P2, *not* FAIL;
a separate id-resolution failure on non-empty charges → P1 FAIL):

1. **HTTP 200 with an empty `charges` array** → the harvested folios genuinely have no
   charges (an earlier destructive batch consumed them, or they were created without
   charges). Legitimate data-state REVIEW.
2. **HTTP 404 / `success:false`** → the harvested folio id doesn't resolve for that
   tenant (a harvest / id-source problem, not a path or serializer bug).

**How to apply:** the only signal that separates (1) from (2) is the spec's own
`detailShapeSnap` (the captured `{http, keys, charges_len}`), which is a **CI-run
artifact** — it cannot be produced in the repl without a full stress dispatch, which the
agent is not allowed to run. Until that snapshot is read from the run report, do not
patch the spec, do not reshuffle the sample window, do not seed, and do not fake PASS.
Document it as "needs CI detailShapeSnap" and stop.
