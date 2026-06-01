---
name: Deterministic stress seed-count drift after a feature merge
description: When a seed/aging feature lands after a green baseline, exact-match seed-count test constants go stale; recompute the deterministic formula offline before changing anything.
---

# Deterministic stress seed-count drift

The 500-room stress seed factory is FULLY deterministic and date-independent:
per-booking `stay_nights = (i%4)+1`; an aging feature adds
`is_aged = (i%8!=0 && i%3==0)` → `nights += aged_offset_days = 2+(i%4)`. So total
room-night-locks = base `125*(1+2+3+4)=1250` + aged extra. Folio charges =
per-night room charges (== sum of nights) + 1 acc-tax charge per folio (== room count).

**Rule:** when a `.toBe(<exact count>)` seed-count assertion starts failing right
after a seed/aging feature merge, it is almost always STALE-CONSTANT spec-drift, not
a backend regression. Recompute the deterministic sum offline (a tiny JS loop over
`i in 0..rc` mirroring the factory) and confirm it equals the live count, THEN update
the constant to the new deterministic value with a comment citing the feature.

**Why:** the count is still exact and correct — only the hardcoded expectation predates
the feature. Updating the exact constant is NOT loosening; switching `.toBe` to a loose
`>=` range WOULD be (it hides future real drift). Keep `.toBe`.

**How to apply:** never blind-update the number to match the log. First derive it from
the factory formula so you can prove the live count is legitimate (no duplicate locks,
no double-charges). If the recomputed value disagrees with the live count, it is a real
backend bug — investigate, do not patch the test.
