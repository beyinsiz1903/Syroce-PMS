---
name: Playwright reporter retry dedup
description: Custom Playwright reporters that aggregate verdicts must collapse retry attempts by test identity, or flaky-pass-on-retry produces a false NO-GO.
---

# Playwright custom reporters: dedup attempts by test.id

When a custom Playwright reporter builds PASS/FAIL/verdict counts in `onTestEnd`,
it must key results by stable test identity (`test.id`, fallback to titlePath)
and let the **last** attempt win — not append one row per attempt.

**Why:** With `retries > 0` (mobile/e2e CI uses `retries: 1`), Playwright fires
`onTestEnd` once per attempt. A test that fails attempt 0 then passes attempt 1
emits two events. Naive `results.push(...)` counts the failed attempt too, so a
flaky pass-on-retry inflates `FAIL`/`failedTests` and forces a false **NO-GO**
in a GO-WITH-WATCH/GO doctrine. (Caught by architect review on the F10A mobile
smoke drill-report reporter.)

**How to apply:** In any aggregating reporter (mobile `markdown-reporter.mjs`,
and the analogous `frontend/e2e-stress/markdown-reporter.mjs` which has the same
naive `push` shape and would suffer the same bug under retries), store rows in a
`Map` keyed by `test.id` and materialize `[...map.values()]` in `onEnd` before
counting. Verify with a synthetic failed-then-passed same-id sequence: expect
one logical row and verdict GO, not NO-GO.
