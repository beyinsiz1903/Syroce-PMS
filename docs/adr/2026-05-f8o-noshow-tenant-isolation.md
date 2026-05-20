# ADR — F8O AI No-Show Cross-Tenant Leak (P0, Task #214)

**Date:** 2026-05-20
**Status:** Accepted (fix landed)
**Severity:** P0 — tenant-boundary violation (threat-model top invariant)

## Context

The full stress suite (20260520) `ai_noshow_risk` module raised a P0:

> `44-ai-noshow-risk-dryrun.spec.js § C — Cross-tenant — pilot token
> stress booking_id leak guard`
> Detail: `leak_hits=2/2 sample=["BK001…","BK002…"]`.

The stress harness called `GET /api/predictions/no-shows` with
`stress_token`, collected the returned `booking_id`s, then re-called the
same endpoint with `pilot_token` and looked for any of those IDs in the
pilot response. Two IDs leaked across the tenant boundary.

## Root Cause

`backend/domains/ai/router/predictions.py` `predict_no_shows()` (the GET
handler at `/api/predictions/no-shows`) returned a hardcoded mock payload
for every caller:

```python
predictions = [
    {'booking_id': 'BK001', 'guest_name': 'John Doe', ...},
    {'booking_id': 'BK002', 'guest_name': 'Jane Smith', ...},
]
```

There was no `tenant_id` filter, no DB query, and no use of
`current_user.tenant_id`. Every tenant — pilot, stress, real production
operators — received the same two fabricated IDs. The stress detector
correctly classified this as a cross-tenant leak because the same IDs
were observable across two distinct tenant tokens. The POST sibling
(`/api/ai/predict-no-shows`) was already tenant-scoped; only the GET
shortcut was the offender.

Even though the leaked values were synthetic (not real production data),
this is still a P0 because:

1. It collapses the tenant-boundary contract the threat model places at
   the top of the priority list. A future refactor that wires this
   resolver to a real shared store would have leaked real booking IDs
   without any new code review.
2. Stress detectors that watch for cross-tenant ID echo will fire
   constantly, masking real future leaks.
3. The endpoint is reachable by any authenticated user (no `require_op`
   gate on the GET, unlike the POST).

## Fix

Rewrote `predict_no_shows()` to:

1. Use `current_user.tenant_id` as the authoritative tenant scope.
2. Query `db.bookings` with `{tenant_id, check_in, status ∈ {confirmed,
   guaranteed}}` and a tight projection.
3. Compute risk with the same factor logic the POST handler already
   uses (channel, payment model, value), simplified for the GET shape.
4. Apply a **defence-in-depth** post-filter: any returned doc whose
   `tenant_id` does not match the requesting user is dropped before it
   reaches the response. This guards against a future shared cache or
   query helper silently dropping the Mongo-level filter.
5. Return an empty `predictions` array when there are no arrivals —
   never fall back to mock data.

No response-shape change for existing fields used by the frontend
(`predictions[*].booking_id|risk_score|risk_level`,
`high_risk_count`, `total_at_risk`, `target_date` all preserved). The
`guest_name` field was only ever populated in the mock fallback and
intentionally omitted now (the frontend reads guest data via the
dedicated guest endpoints, which are tenant-scoped and PII-masked).

**API contract — `risk_score` semantics:** the pre-fix mock returned
fractional scores (`0.75`, `0.45`) in the `[0, 1]` range. The frontend
consumer `frontend/src/pages/PredictiveAnalytics.jsx` displays the
value as `Math.round(pred.risk_score * 100)`, so the fix MUST keep
`risk_score` in `[0, 1]`. An initial revision of this fix accidentally
shipped percentage-scale integers (`0..100`) which would have rendered
as "2500%" in the UI — caught in code review, corrected, and pinned by
the new `test_risk_score_is_fractional_0_to_1` regression test.
`risk_level` thresholds: `high ≥ 0.70`, `medium ≥ 0.50`, else `low`.

No cache layer was involved in this leak (no caching was wired on the
GET handler), so no cache-key change was needed. The follow-up note
below covers cache-key tenant-scoping as a defensive convention if a
future PR adds caching here.

## Regression Coverage

`backend/tests/test_ai_noshow_tenant_isolation.py` — 6 tests, all pass:

* `test_no_mock_placeholders_returned` — pins that `BK001`/`BK002`
  never appear in the response again.
* `test_tenant_a_sees_only_tenant_a_bookings` — asserts the Mongo
  filter includes `tenant_id` and the response contains only tenant A
  IDs.
* `test_tenant_b_sees_only_tenant_b_bookings` — symmetric.
* `test_empty_arrivals_returns_empty_predictions_not_mocks` — no
  fallback mock payload when arrivals=0.
* `test_defence_in_depth_filter_drops_mismatched_tenant_doc` —
  poisons the fake DB to return a cross-tenant doc despite the
  query filter; the in-handler `tenant_id` check still drops it.
* `test_default_target_date_is_today_and_tenant_scoped` — covers
  the `target_date=None` branch.

Stress-suite §C is expected to flip to `leak_hits=0` on the next CI
run; backend regression locks the contract independent of CI.

## Out of Scope

* AI model accuracy / scoring algorithm changes.
* Tenant audit of other AI surfaces (upsell, pricing, complaint risk)
  — the stress suite only observed the no-show leak; a sweep should be
  a separate task if/when those modules raise findings.
* Frontend changes — response shape is back-compat for the consumed
  fields.

## Production Audit Note

The leaked IDs were synthetic (`BK001`/`BK002` are not valid booking
IDs in production), so the audit-log review for "real ID leak in last
30 days" is naturally vacuous — no real ID was ever in the response.
No security incident report opened.
