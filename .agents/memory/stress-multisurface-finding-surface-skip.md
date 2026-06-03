---
name: Multi-surface stress finding can survive your fix via surface-skip
description: Why a rate-limit/boundary-style finding persists after you fixed one of its surfaces — the spec skipped that surface and the residual finding is a sibling.
---

A single stress finding (e.g. rate_limit_boundary "no 429 observed on public burst")
often aggregates several SURFACES under one entry, each probed independently. Read the
finding's `surfaces=[...]` array before claiming your fix cleared it.

**Why:** After fixing Room QR submit rate-limit ordering (limiter before auth verify),
the next full run still showed the same P2. Detail:
`surfaces=[{"key":"qr_submit","skipped":"no_room"},{"key":"auth_login","n":60,"throttled":0,...}]`.
The QR surface was SKIPPED (`no_room` — the spec couldn't construct a QR token), so the
fix was never stress-exercised; the residual finding was a *different* sibling surface
(`auth_login`) with the **same** limiter-before-auth ordering bug, not a regression of the
QR fix.

**How to apply:**
- A persisting boundary/DoS-sentinel finding after a targeted fix is NOT proof the fix
  failed. Check which surface in the array is actually red, and whether your fixed surface
  was `skipped`.
- If your surface is `skipped`, your CI-run validation is missing — fall back to the live
  read-only probe as the evidence, and say so honestly (don't claim the run validated it).
- A login/auth burst showing `throttled=0, clientErr=N` is the SAME pattern as
  `ratelimit-before-auth-ordering.md`: token-verify short-circuits before the counter.
  The QR reorder fix applies to the login surface too (separate, scope-gated).
