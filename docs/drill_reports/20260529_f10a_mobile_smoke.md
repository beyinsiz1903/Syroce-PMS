# F10A Mobile Web Smoke Drill — 20260529

> **Phase:** F10A — render-only Playwright matrix over `mobile/app/` against the Expo Web bundle.
> **Scope guardrail:** This is the **F10A mobile render-only smoke** effort. It is **not** mobile-complete, **not** F10 closed, **not** /100. Native biometric / camera / push / offline are explicitly out of scope and live in F10B–F10G.
> **Workflow:** `Mobile Web Smoke (F10A render-only matrix)` — `.github/workflows/mobile-web-smoke.yml` (manual `workflow_dispatch` only at F10A).
> **Companion docs:** `docs/TEST_COVERAGE_SCORECARD_100.md` (central /100 reference) · prior drill `docs/drill_reports/20260527_f10a_mobile_smoke.md` (BLOCKED, no run).
> **Doctrine:** fatal console errors = 0 · PII/token leak = 0 · auth redirect honoured · no fake PASS · no skip-as-pass · official artifact ⇒ GitHub Actions run, not local.

---

## 1) Executive summary

| Field | Value |
|---|---|
| Drill verdict | **PARTIAL — INFRA HARDENED + RENDER PROOF; FULL MATRIX BLOCKED (operator dispatch + role secrets required)** |
| Workflow run URL | _none — official GitHub Actions dispatch has not yet occurred_ |
| Official artifact | _none — no `mobile-web-smoke-report` artifact produced; official F10A evidence requires a GitHub Actions run_ |
| Surfaces in matrix | 25 (1 auth + 24 role-grouped) → 28 Playwright tests (4 login + 24 screen), confirmed by `--list` |
| Surfaces actually rendered this drill | **1 / 25** — `/login` only (credential-free; see §3) |
| Per-role render result (full matrix) | n/a — blocked on 4 role credentials (see §4) |
| Fatal console error count (this drill, `/login`) | **0** |
| PII/token leak count (this drill, `/login`) | **0** |
| Auth redirect result | n/a — requires role login (blocked) |
| Run #159 baseline pointer | ❌ **Not moved.** Run #159 (`e23a4ec603cc32984b741d77d67d57a0abba698b`) stays the official web/backend baseline. F10A does not touch it. |

**Honest accounting.** This drill made real, verifiable progress on F10A infrastructure and produced a genuine (but partial) render proof. It did **not** produce the official F10A artifact, because the full 28-test matrix needs the four mobile role accounts (`MOBILE_E2E_*`) and the official evidence must come from a GitHub Actions `workflow_dispatch` (this environment has no Actions dispatch API and no visibility into repo secrets). Doctrine forbids substituting the stress-admin credential across all four roles (that would conflate frontdesk/gm/housekeeping/guest into one user and produce misleading green), and forbids declaring a local run as the official artifact. So the full matrix is recorded as **BLOCKED**, while the infra hardening and `/login` render proof are recorded as **DONE** with evidence.

---

## 2) Infra hardening completed this drill (real changes)

| Item | Before | Action | After |
|---|---|---|---|
| Stale `.js` / `.ts` duplicate collision | `mobile/e2e/` had both `playwright.config.{js,ts}`, `routes.{js,ts}`, `smoke.spec.{js,ts}`. Playwright's ESM loader resolved `import './routes'` to the **older** `routes.js` (an earlier F10A iteration exporting `MOBILE_ROUTES`/`PII_LEAK_PATTERNS`, **not** `CONSOLE_ERROR_ALLOWLIST`), so `--list` failed with `SyntaxError: ... does not provide an export named 'CONSOLE_ERROR_ALLOWLIST'`. | Removed the stale `.js` trio (`playwright.config.js`, `routes.js`, `smoke.spec.js`). Nothing references them — the workflow and `mobile/package.json` `test:e2e:smoke` both target `playwright.config.ts` with `testMatch=/smoke\.spec\.ts$/`. | `--list` clean: **28 tests in 1 file**. |
| Playwright not installed in `mobile/` | `@playwright/test` absent (intentionally not a prod dep — would pull into the RN/Expo bundle). | Installed ad-hoc (`npm install --no-save @playwright/test@^1.49.0`) + `npx playwright install chromium`, mirroring the CI workflow's own install step. | Harness runs locally. |

Both fixes match the CI workflow's design (the workflow installs Playwright ad-hoc at lines 70–77); the `.js` removal eliminates a latent failure the CI run would also have hit on the TS specs.

---

## 3) Render proof produced this drill (`/login`, credential-free)

A throwaway Playwright check (Pixel 7 viewport, `tr-TR`, `Europe/Istanbul`, against `http://localhost:8080` Expo Web) opened `/login` with the **same** console-error allowlist and PII/token regex as `mobile/e2e/fixtures.ts`. Result:

```json
{
  "base": "http://localhost:8080",
  "login_testids": { "email": true, "password": true, "submit": true },
  "body_len": 185,
  "console_errors": [],
  "pii_findings": []
}
```

What this proves (and only this):
- Expo Web bundle is healthy and serves the login surface.
- The harness selectors (`smoke-login-email` / `-password` / `-submit`) are present in the hydrated DOM — so `loginAsRole()` would find them.
- `/login` renders with **0 fatal console errors** and **0 JWT/bearer/PAN leaks**.

What this does **not** prove: any authenticated surface, any role redirect, any of the 24 role-grouped screens. Those are blocked (§4). The throwaway script was deleted after the run; it is not committed.

---

## 4) Why the full matrix is BLOCKED (explicit gap list)

| Blocker | Detail | Who can clear it |
|---|---|---|
| 4 role credentials missing | `fixtures.ts` requires `MOBILE_E2E_FRONTDESK_EMAIL/PASSWORD`, `MOBILE_E2E_GM_*`, `MOBILE_E2E_HK_*`, `MOBILE_E2E_GUEST_*`. None are present in this environment; only `E2E_STRESS_ADMIN_EMAIL/PASSWORD` exist. `requireEnv()` throws before any nav. **Substituting the stress admin for all four roles is forbidden** (conflates roles → misleading green). | Operator: provision 4 mobile test accounts on a non-pilot tenant and set the 8 secrets. |
| Official artifact needs GitHub Actions | F10A official evidence = a `mobile-web-smoke-report` artifact from `workflow_dispatch`. This environment has no Actions dispatch API and no repo-secret visibility. | Operator: dispatch from GitHub UI. |
| Deployed Expo Web `base_url` | Workflow input `base_url` requires a reachable deployed Expo Web bundle URL (not the local `:8080` dev server, not the pilot tenant). | Operator: supply deployed bundle URL. |
| Pilot mutation budget = 0 | The 4 `MOBILE_E2E_*` accounts must belong to a non-pilot tenant; render-only smoke must not write to pilot data. | Operator: confirm tenant of the 4 accounts. |

---

## 5) Matrix scope (what a full run would exercise)

Source of truth: `mobile/e2e/routes.ts` (25 surfaces). Confirmed by `--list` (28 Playwright tests = 4 per-role login + 24 screens).

| Role | Surfaces (path) | Criticality mix |
|---|---|---|
| `auth` | `/login` | 1×P0 |
| `frontdesk` (6) | `/` · `/checkin` · `/checkout` · `/guests` · `/walkin` · `/more` | 3×P0 · 2×P1 · 1×P3 |
| `gm` (2) | `/` · `/more` | 1×P1 · 1×P3 |
| `housekeeping` (3) | `/` · `/damage` · `/more` | 2×P1 · 1×P3 |
| `guest` (13) | `/` · `/booking` · `/checkin` · `/cart` · `/orders` · `/roomservice` · `/digitalKey` · `/earlylate` · `/loyalty` · `/messages` · `/messageThread` · `/qrBadge` · `/more` | 8×P0 · 3×P1 · 1×P2 · 1×P3 |
| **Total** | **25 surfaces** | **12×P0 · 8×P1 · 1×P2 · 4×P3** |

---

## 6) Doctrine evaluation

| Constraint | Status this drill | Notes |
|---|---|---|
| Fatal console errors = 0 | ✅ for `/login` (0); n/a for the other 24 (not run) | Measured by the same observer logic as `smoke.spec.ts`. |
| PII / token leak = 0 | ✅ for `/login` (0); n/a for the other 24 (not run) | Same JWT/bearer/PAN regex as `fixtures.ts`. |
| Auth redirect honoured | n/a (no role login possible) | Blocked on credentials. |
| Fake PASS | ❌ none produced | Full matrix recorded BLOCKED, not PASS. |
| Skip-as-pass | ❌ none produced | 24 screens not declared skipped-clean. |
| Pilot mutation | 0 | `/login` render is read-only; no authenticated writes attempted. |
| Run #159 pointer moved | ❌ no | Official baseline untouched. |
| "/100" or "mobile complete" claimed | ❌ no | This is F10A render-only smoke, first partial mobile evidence only. |

---

## 7) What ships in this commit

- This drill report (PARTIAL / BLOCKED, honest).
- Removal of the stale `mobile/e2e/*.js` trio (`playwright.config.js`, `routes.js`, `smoke.spec.js`) — collision fix; `.ts` specs are the source of truth.
- `mobile/.gitignore`: ignore rules for generated local Playwright reports (`e2e/playwright-mobile-smoke-report/`, `test-results-mobile-smoke/`) so local evidence is never confused with the official GitHub Actions `mobile-web-smoke-report` artifact.
- `docs/TEST_COVERAGE_SCORECARD_100.md`: F10 row + Sprint-1 note updated to "scaffolded + locally runnable + partially proven; full matrix BLOCKED; NOT verified".
- `docs/F10_MOBILE_COVERAGE_ROADMAP.md`: added 2026-05-29 F10A update note; reconciled §6 tooling decision to match the §5 locked decision (Playwright primary / Maestro native / Detox rejected for F10A).

What does **not** ship: no committed Playwright report artifact (generated dir removed + gitignored), any baseline-pointer change (`replit.md` Run #159 stays), any roadmap/scorecard row claiming F10A verified, any coverage-count change, any claim that mobile/F10 is closed.

---

## 8) Next action (operator) to flip F10A → verified

1. Provision 4 mobile test accounts on a **non-pilot** tenant; set the 8 `MOBILE_E2E_*` repo secrets (Settings → Secrets and variables → Actions). Workflow fail-fasts (lines 54–68) if any are missing.
2. Confirm a reachable **deployed** Expo Web bundle `base_url` (not `:8080` dev, not pilot tenant).
3. GitHub UI: **Actions → Mobile Web Smoke (F10A render-only matrix) → Run workflow** with `base_url` + optional `note`.
4. Download the `mobile-web-smoke-report` artifact (Playwright HTML + `mobile-smoke.log`).
5. Replace §1 / §3 / §6 here with measured results (run URL, run number, commit SHA, artifact name+digest, surface count, PASS/FAIL/REVIEW/SKIP, console-error count, PII count, verdict). Flip F10A status to **verified** in `docs/TEST_COVERAGE_SCORECARD_100.md` **only if** every doctrine constraint passes across all 25 surfaces.
6. If any surface hard-fails: keep that surface **NO-GO**, open per-defect follow-up tasks, re-dispatch after fixes. Do **not** move any baseline pointer on the strength of F10A.

---

## 9) Closing note

F10A scaffold is sound and now **locally runnable**: the duplicate-file collision is gone, Playwright is wired, `--list` shows the full 28-test matrix, and `/login` renders clean (0 console errors, 0 PII). The only gates remaining for F10A → verified are operator-owned: 4 role accounts + 8 repo secrets + a deployed bundle URL + one green GitHub Actions `workflow_dispatch`. Until that artifact exists, F10 mobile coverage stays **scaffolded + partially proven**, counts toward **nothing** in pilot/`/100` claims, and Run #159 remains the sole official baseline.
