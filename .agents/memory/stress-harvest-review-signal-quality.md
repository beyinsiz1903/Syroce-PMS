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

**Rule:** split the "foundWithPay==0" outcome — but split detail failures BY HTTP
STATUS, not by a blunt `detailFail>0`. A blanket "any detail not-ok → FAIL" is itself a
**fake-RED**: a heavy detail endpoint returns fast 404s (harvested id didn't resolve in
this data-state) or 0/429 (timeout/throttle under full-suite load), neither of which is
a void-path regression. Priority order:
1. **shapeDrift** — non-voided rows returned but none carried an id under any known key
   (`id||_id||payment_id||paymentId`) → **FAIL** (serializer contract regression).
2. **detail5xxFail** — `detail5xx>0 && foundWithPay==0` (detail GET returned a genuine
   **5xx** server error) → **FAIL** (real backend regression on the dependency).
3. **detailStateMiss** — detail failed only with **4xx / 0 / 429** (not-found / state /
   timeout / throttle), `detail5xx==0`, never reached a payment folio → **REVIEW** (P2,
   data-state/env — NOT a regression).
4. **allNoPay** — detail calls HEALTHY and no non-voided row anywhere → data-state
   **REVIEW** (P3).

**Why:** the deposit payments live only on aged folios, so a window can legitimately
miss them. But three things must stay distinguishable: "endpoint 5xx" (FAIL), "I saw
zero / 4xx-timeout" (REVIEW), and "shape drift" (FAIL). Collapsing all detail failures
to FAIL fake-REDs on environmental latency; collapsing all to REVIEW fake-greens a 5xx.
You CANNOT classify without capturing the failing status — snapshot `detailFailModes`
(`{s500,s404,s0,...}`) AND `detail_shape` (incl. http + body keys) on the FIRST failure,
or an all-fail run logs `detail_shape=null` and the next run can't tell 5xx from 404.

**How to apply:** give the heavy detail probe generous per-call timeout (e.g. 60s) so a
slow-but-healthy response isn't miscounted as a failure; capture status distribution;
FAIL only on 5xx or shape-drift or a real void-POST error; REVIEW on 4xx/timeout/state.
Apply the SAME split to every sibling harvest in the file (C4 void-charge + C5
void-payment) so one isn't a fake-green while the other is hardened.

**Two masking traps the partial-success case adds (both fake-green):**
1. **detail5xxFail must NOT be gated on `foundWithPay==0` / `voided==0`.** Use
   `detail5xxFail = detail5xx > 0` unconditionally. If you gate it on "found nothing",
   then a run that voids one folio AND hits a 5xx on another silently PASSes — a real
   backend 5xx hidden by a partial success.
2. **A `realVoidFail` (a void POST error on an OPEN folio after the closed/empty skip)
   must FAIL even when `voided>=1`.** `voided>=1 ? PASS` masks a void-POST error mixed
   with successes. Use `realVoidFail = postErrors>0 && !all403` and put it in the FAIL
   group. `all403` (voided==0 AND every error is 403) is the only RBAC-short-circuit
   that stays REVIEW.
3. **Status-ladder precedence: evaluate the FAIL group BEFORE `all403`.** If `all403 ?
   REVIEW` is the first ternary branch, an `all403 + detail5xx>0` run is downgraded to
   REVIEW — a 5xx masked by an RBAC short-circuit. Correct order:
   `(shapeDrift||detail5xxFail||realVoidFail) ? FAIL : all403 ? REVIEW : dataState ? REVIEW : ...`.
   Verify the full truth table offline (node) before trusting it: partial-success+5xx
   and all403+5xx must both be FAIL; all403-only and data-state must be REVIEW.
