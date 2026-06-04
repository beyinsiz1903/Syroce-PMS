---
name: F10 mobile baseline true blockers
description: What actually blocks the "mobile/F10" open option and where the only agent-doable progress lever is
---

The "mobile/F10 baseline" open option is NOT a single agent-runnable task. Split it honestly:

- **F10A full render-only matrix (25 surfaces / 28 Playwright tests):** OPERATOR-BLOCKED, agent cannot progress. Needs all three: (a) 4 `MOBILE_E2E_*` role accounts on a non-pilot tenant → 8 repo secrets, (b) a GitHub Actions `workflow_dispatch` (this env has no Actions dispatch API / no repo-secret visibility), (c) a reachable DEPLOYED Expo Web `base_url` (not `:8080` dev). The Playwright config fail-fasts on missing `MOBILE_E2E_BASE_URL`; substituting the stress-admin cred for all 4 roles is forbidden (conflates roles → misleading green).
  - Scaffold health check (agent-doable, read-only): `cd mobile && MOBILE_E2E_BASE_URL=http://localhost:8080 npx playwright test --config e2e/playwright.config.ts --list` should print `Total: 28 tests in 1 file`.
  - GOTCHA: the md-reporter writes a drill report even on `--list` (0 tests run) with `Final verdict: GO` — that is a VACUOUS fake-green artifact. Delete any `docs/drill_reports/*_f10a_mobile_smoke.md` produced by a `--list`; official F10A evidence = a real GH Actions run only.

- **The real mobile-adjacent gate was 3 backend P1s (F9C deep specs), now RESOLVED + verified (2026-06-04):** maintenance work-orders 500, mobile_staff `GET /api/notifications/preferences` 500, mobile_cashier PIN brute-force no-429. The agent's only mobile-progress lever is fixing/verifying these backend P1s (targeted pytest + live read-only probe), NOT running the F10A matrix.

**Why:** repeatedly "continuing the open option" wastes turns re-discovering that the matrix itself is operator-only. **How to apply:** when asked to advance mobile/F10, verify scaffold health + backend P1 status; do not attempt to dispatch/secret-provision the matrix, and never let a `--list` report stand as evidence.
