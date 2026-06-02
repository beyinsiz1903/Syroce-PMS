---
name: A data-state REVIEW in a detail-probe harvest must not swallow detail-endpoint failures
description: When a stress spec harvests void/charge targets by probing a detail endpoint and falls back to a data-state REVIEW when it finds none, that REVIEW must be gated on the detail calls being HEALTHY — otherwise a systematic 5xx or a serializer shape-drift on the detail endpoint silently downgrades a real regression into an informational REVIEW.
---

A bounded detail-probe harvest (scan up to N folios, void only those exposing a
non-voided payment id) replaces blind `slice()` selection and is the right fix for a
self-inflicted "no target in window" REVIEW. But the harvest introduces a **signal-
quality trap**: if it collapses "found nothing to void" straight into a data-state
REVIEW, then any failure of the *detail endpoint itself* (the thing the harvest depends
on) also produces "found nothing" — and gets mislabeled REVIEW instead of FAIL. That
violates the doctrine "gerçek failure'ı REVIEW'a düşürme YOK".

**Rule:** split the "foundWithPay==0" outcome into three, in priority order:
1. **detailBroken** — `detailFail>0 && foundWithPay==0` (detail GET returned not-ok /
   5xx / auth on every probe) → **FAIL** (endpoint regression).
2. **shapeDrift** — non-voided payment rows were returned but none carried an id under
   any known key (`id||_id||payment_id||paymentId`) → **FAIL** (serializer contract
   regression; mirror the spec's existing C4 `shapeDrift` branch).
3. **allNoPay** — detail calls were HEALTHY (`detailFail==0 && rowsButNoId==0`) and no
   non-voided payment row existed anywhere in the scanned window → genuine data-state
   **REVIEW** (P3), never FAIL/skip-as-pass.

**Why:** the deposit payments the harvest looks for live only on aged folios; a fixed
window can legitimately miss them (true data-state). But "I saw zero" and "the endpoint
I rely on is broken" must be distinguishable, or the harvest becomes a fake-green for
the detail path. Always read an id under multiple key aliases and emit a
`detail_shape` snapshot in the note for CI triage.

**How to apply:** any stress harvest that gates a REVIEW on "no target found" must also
track detail-call health (not-ok count) and shape health (rows-present-but-no-id count),
and FAIL on either before falling back to the data-state REVIEW.
