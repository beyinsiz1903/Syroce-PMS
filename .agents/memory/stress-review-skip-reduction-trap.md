---
name: REVIEW/SKIP reduction trap — unblocking a SKIP often raises REVIEW
description: Widening a harvest/page limit to "unblock" a SKIPped stress step doesn't reduce counts; the unblocked step hits a by-design 409/403/422/data-scarcity and becomes a REVIEW.
---

# REVIEW/SKIP reduction trap

When asked to "reduce the REVIEW/SKIP count" of a stress suite, the intuitive move
is to unblock SKIPped steps (widen a `limit=`/`maxPages=` harvest window, open a
gated step). **This rarely lowers the total and frequently RAISES REVIEW.** A step
was usually SKIPped because it had no data/target; once you give it data, it runs
and lands on a by-design condition — 409 (open-folio/duplicate), 403 (perm not
granted), 422 (validation), or data-scarcity — which the harness records as a
REVIEW. Net effect: SKIP→REVIEW conversion, count goes UP.

**Real count reduction comes from only two sources:**
1. Fixing something genuinely broken (e.g. an endpoint that times out / 500s).
2. A legitimate reclassification — and **by-design items cannot be reclassified**
   without faking the result.

So a "REVIEW/SKIP reduction" goal is inherently bounded: most remaining items are
by-design, and they are floor, not slack.

**Why:** verified in practice — a harvest reduction pack (finance_folio
`limit=5→50` + full_24h `maxPages 8→60`) added ~+20 PASS but pushed REVIEW UP by
~6 with SKIP unchanged. The unblocked steps hit exactly the by-design 409/403/422
surfaces the drill had already justified, so SKIP just converted to REVIEW.

**How to apply:**
- Do NOT revert the unblock to shrink the count — that re-hides a real path as a
  SKIP = skip-as-pass = doctrine violation. Keep the fix; the REVIEW rise is the
  honest outcome.
- Set expectations up front: tell the operator that unblocking SKIPs will likely
  move them into by-design REVIEW, not erase them.
- Before projecting a count drop, classify each target: "is the unblocked step
  going to hit a by-design gate?" If yes, it's a SKIP→REVIEW move, not a removal.
