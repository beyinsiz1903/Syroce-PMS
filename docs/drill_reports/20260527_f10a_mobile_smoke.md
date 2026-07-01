# F10A Mobile Web Smoke Drill — 20260527

> **Phase:** F10A — render-only Playwright matrix over `mobile/app/` against the deployed Expo Web bundle.
> **Scaffold:** commit `74142f05` (2026-05-27) · workflow `de46f2bf` (`.github/workflows/mobile-web-smoke.yml`, re-applied via GitHub UI 2026-05-27).
> **Workflow:** `Mobile Web Smoke (F10A render-only matrix)` (manual `workflow_dispatch` only at F10A).
> **Companion docs:** `docs/F10_MOBILE_COVERAGE_ROADMAP.md` §5 F10A · `docs/DAILY_CHANGE_REVIEW_20260527_POST_F9C.md` §5.
> **Doctrine:** fatal console errors = 0 · PII/token leak count = 0 · auth redirect honoured · no fake PASS · no skip-as-pass.

---

## 1) Executive summary

| Field | Value |
|---|---|
| Drill verdict | **BLOCKED — OPERATOR DISPATCH REQUIRED** |
| Workflow run URL | _none — dispatch has not yet occurred_ |
| Artifact | _none — no run, no `mobile-web-smoke-report` artifact_ |
| Routes exercised | 0 / 25 (matrix defined in `mobile/e2e/routes.ts`; see §3) |
| Per-role render result | n/a — no execution evidence |
| Fatal console error count | n/a |
| PII/token leak count | n/a |
| Auth redirect result | n/a |
| Baseline move | ❌ Not moved — F10A remains **scaffolded but unverified** in `docs/F10_MOBILE_COVERAGE_ROADMAP.md` |

**Honest accounting.** Per task #119 step 3, this drill requires a manual `workflow_dispatch` of `Mobile Web Smoke (F10A render-only matrix)` from the GitHub Actions UI, with `base_url` set to the deployed Expo Web bundle URL (e.g. `https://mobile-stress.syroce.com` or pilot equivalent) and all eight `MOBILE_E2E_*` secrets configured in the repo settings. The task agent runs in an isolated sandbox with no GitHub Actions dispatch API access, no visibility into repository secrets, and no confirmed pointer to a deployed Expo Web bundle URL. Doctrine (`fake PASS yok`, `skip-as-pass yok`) forbids fabricating evidence, so this drill report records the run as **BLOCKED** and hands the dispatch action back to the operator.

The companion doc `docs/DAILY_CHANGE_REVIEW_20260527_POST_F9C.md` §5 explicitly lists "F10A mobile smoke run" with status "❌ Cannot run from this environment — proposed as Project Task", confirming the gap is structural, not a task-agent error.

---

## 2) Pre-flight check (what the operator must verify before dispatch)

| Item | Source of truth | Operator action |
|---|---|---|
| Workflow file present on default branch | `.github/workflows/mobile-web-smoke.yml` (115 lines) | Confirm visible in **Actions** tab as `Mobile Web Smoke (F10A render-only matrix)` |
| Eight repo secrets set | `Settings → Secrets and variables → Actions` | `MOBILE_E2E_FRONTDESK_EMAIL` · `MOBILE_E2E_FRONTDESK_PASSWORD` · `MOBILE_E2E_GM_EMAIL` · `MOBILE_E2E_GM_PASSWORD` · `MOBILE_E2E_HK_EMAIL` · `MOBILE_E2E_HK_PASSWORD` · `MOBILE_E2E_GUEST_EMAIL` · `MOBILE_E2E_GUEST_PASSWORD`. Workflow has fail-fast guard at step `Fail-fast on missing secrets` (lines 54–68) that exits before Playwright install if any are missing. |
| Deployed Expo Web bundle URL reachable | Operator-supplied | `curl -sSf $BASE_URL` returns 200 and HTML contains Expo Router bootstrap |
| `mobile-stress-tenant` seed present | per `docs/F10_MOBILE_COVERAGE_ROADMAP.md` §7 | Pilot mutation budget = 0; the four `MOBILE_E2E_*` accounts must belong to `mobile-stress-tenant`, never the pilot tenant |

If any of the above are missing, the operator must remedy them **before** dispatch; the workflow itself fail-fasts on missing secrets but cannot detect mis-tenanted accounts or an unreachable bundle URL — those would surface as smoke failures.

---

## 3) Matrix scope (what would have been exercised)

Source of truth: `mobile/e2e/routes.ts` (25 surfaces, 1 auth + 24 role-grouped). Matches roadmap §2.1.

| Role | Surfaces (path) | Criticality mix |
|---|---|---|
| `auth` | `/login` | 1×P0 |
| `frontdesk` (6) | `/` · `/checkin` · `/checkout` · `/guests` · `/walkin` · `/more` | 3×P0 · 2×P1 · 1×P3 |
| `gm` (2) | `/` · `/more` | 1×P1 · 1×P3 |
| `housekeeping` (3) | `/` · `/damage` · `/more` | 2×P1 · 1×P3 |
| `guest` (13) | `/` · `/booking` · `/checkin` · `/cart` · `/orders` · `/roomservice` · `/digitalKey` · `/earlylate` · `/loyalty` · `/messages` · `/messageThread` · `/qrBadge` · `/more` | 8×P0 · 3×P1 · 1×P2 · 1×P3 |
| **Total** | **25 surfaces** | **12×P0 · 8×P1 · 1×P2 · 4×P3** |

Console-error allowlist (intentional, tight) lives in `mobile/e2e/routes.ts` `CONSOLE_ERROR_ALLOWLIST` (8 entries — Expo/Metro dev banners, RN-Web shim warnings, TanStack Query info logs). Per doctrine no leak class is allowlisted.

---

## 4) Doctrine evaluation

| Constraint | Status this drill | Notes |
|---|---|---|
| Fatal console errors = 0 | n/a (no run) | Will be measured by `mobile/e2e/smoke.spec.ts` observer when dispatched |
| PII / token leak count = 0 | n/a (no run) | DOM scanner pattern equivalent to `frontend/e2e-smoke/fixtures.js` JWT/bearer/PAN regex |
| Auth redirect honoured | n/a (no run) | Per-role login fixture asserts redirect into expected group root |
| Fake PASS | ❌ none produced | This report records BLOCKED, not PASS |
| Skip-as-pass | ❌ none produced | Matrix not run; not declared skipped-clean |
| Pilot mutation | 0 | No execution → no mutation possible |

---

## 5) What ships in this commit

- This drill report (BLOCKED status, honest).
- `docs/F10_MOBILE_COVERAGE_ROADMAP.md` §5 F10A row clarified: status stays **scaffolded — operator dispatch pending**, with pointer to this report. Status does **not** move to **verified** until a green run artifact is in hand.

What does **not** ship: any change to `digitalocean.md` Gotchas baseline pointer, any roadmap row claiming F10A is verified, any change to coverage counts.

---

## 6) Next action (operator)

1. Confirm the eight `MOBILE_E2E_*` repo secrets are set (Settings → Secrets and variables → Actions).
2. Confirm deployed Expo Web bundle URL is reachable and is **not** the pilot tenant.
3. From GitHub UI: **Actions → Mobile Web Smoke (F10A render-only matrix) → Run workflow** with `base_url` and an optional `note`.
4. On completion, download the `mobile-web-smoke-report` artifact (Playwright HTML report + `mobile-smoke.log`).
5. Replace this report's §1, §3 per-role columns, and §4 with measured results; flip the roadmap status to **verified** with a link back to this file only if every doctrine constraint passes (fatal console errors = 0, PII/token leak = 0, auth redirect OK, no fake/skip PASS).
6. If any route hard-fails, keep the verdict at **NO-GO** for that route, open per-defect follow-up Project Tasks, and re-dispatch only after fixes.

---

## 7) Closing note

F10A scaffold is sound (workflow file 115 lines, fail-fast secret guard wired, 25-surface matrix faithful to `mobile/app/` tree, console-error allowlist tight). The only gate remaining for F10A → verified is one successful operator-driven `workflow_dispatch` against a real deployed bundle. Until that artifact exists, F10 mobile coverage stays at **scaffolded** and cannot be counted toward pilot coverage claims.
