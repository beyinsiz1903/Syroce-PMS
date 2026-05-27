# Mobile E2E — F10A Smoke Matrix

> **Status:** scaffold (Task #83 / F10A kickoff, 2026-05-27)
> **Surface:** Expo Router (`mobile/app/`), 24-25 screens across 5 role groups
> **Runner:** Playwright Web hitting the Expo Web dev server on port 8080/8081.
>   Native (iOS/Android) coverage is **out of scope for F10A** — see
>   `docs/F10_MOBILE_COVERAGE_ROADMAP.md` §4 for the Detox/Maestro plan.

## Tooling decision (F10A)

| Layer | Tool | Why |
|---|---|---|
| **F10A render-only smoke matrix** | **Playwright on Expo Web bundle** | Linux-runnable CI (no Mac/Android emulator), reuses existing PII/console-error patterns from `frontend/e2e-smoke`, render-only acceptance fits the web bundle perfectly. |
| **F10B+ deep native flows** | Maestro (already at [`mobile/.maestro/`](../.maestro/)) | Native-only flows: biometric lock, push registration, offline banner, camera. EAS-built artifacts run on iOS Simulator / Android Emulator. |
| Detox | _Rejected_ for F10A | Requires native build + Mac runner; over-spec for render-only smoke. Re-evaluate in F10G if Maestro deep flows are insufficient. |

The Maestro suite is **complementary** — F10A does not replace it. The
two suites run on separate CI workflows and share zero credentials.

## What this suite covers

Per role (`frontdesk`, `gm`, `housekeeping`, `guest`):

1. UI login via `(auth)/login` (env-driven credentials, no fallbacks).
2. Visit every screen for that role (25 surfaces total — every file
   under `mobile/app/`).
3. Per screen: empty/error UI inspection, console error scan, JWT /
   PAN / bearer leak scan against the DOM source.

Acceptance (matches F10_MOBILE_COVERAGE_ROADMAP.md §5 F10A):

- All screens render (no empty / error UI).
- Runtime errors = 0 (allowlist-filtered — see `routes.ts`).
- No JWT / PAN / bearer pattern in DOM.

## Run locally

```bash
# 1. Start the Expo Web bundle in another terminal:
# Workspace → workflows → "Mobile Web"
# or:
cd mobile
yarn web   # or: npx expo start --web

# 2. From repo root or mobile/ directory, install Playwright and run smoke:
cd mobile/e2e && npm install && npx playwright install chromium
# or if using yarn:
# cd mobile && yarn add -D @playwright/test && npx playwright install chromium

MOBILE_E2E_BASE_URL=http://localhost:8081 \
MOBILE_E2E_FRONTDESK_EMAIL=qa-frontdesk@syroce.com \
MOBILE_E2E_FRONTDESK_PASSWORD=*** \
MOBILE_E2E_GM_EMAIL=qa-gm@syroce.com \
MOBILE_E2E_GM_PASSWORD=*** \
MOBILE_E2E_HK_EMAIL=qa-hk@syroce.com \
MOBILE_E2E_HK_PASSWORD=*** \
MOBILE_E2E_GUEST_EMAIL=qa-guest@syroce.com \
MOBILE_E2E_GUEST_PASSWORD=*** \
npx playwright test --config=playwright.config.ts
```

Reports land in `mobile/playwright-mobile-smoke-report/` (HTML + JSON).

## Env vars (no fallbacks)

| Var | Purpose |
|---|---|
| `MOBILE_E2E_BASE_URL` | Expo Web bundle URL (no trailing slash). |
| `MOBILE_E2E_FRONTDESK_EMAIL` / `_PASSWORD` | front_desk role login. |
| `MOBILE_E2E_GM_EMAIL` / `_PASSWORD` | gm role login. |
| `MOBILE_E2E_HK_EMAIL` / `_PASSWORD` | housekeeping role login. |
| `MOBILE_E2E_GUEST_EMAIL` / `_PASSWORD` | guest_app role login. |

Missing any required var → `setup()` throws (env-hijack protection).

## Doctrine (inherits from F10_MOBILE_COVERAGE_ROADMAP.md §7)

- Pilot mutation = 0 — smoke is **read-only** (no POST/PUT/DELETE).
- `external_calls = []` per spec — no real outbound to OTAs / Quick-ID / Expo push.
- Module-blocked / route-missing → P2 REVIEW, never PASS.
- PII/token leak scan zorunlu — same patterns as `frontend/e2e-smoke/fixtures.js` (JWT / PAN / bearer / api-key).
- Fake PASS yok, skip-as-pass yok — empty screens, console errors, and PII leaks all hard-fail the spec.

## Files

- `routes.ts` — single source of truth: 25 routes × role group × criticality
- `smoke.spec.ts` — navigate every route, run console + PII/token scan
- `playwright.config.ts` — chromium-only, 2 viewports (mobile + tablet)

## CI

Not yet wired. Task #94 follow-up: add markdown drill-report reporter, then Task #93 baseline run on the live pilot environment. See `docs/F10_MOBILE_COVERAGE_ROADMAP.md` §5 (F10B–F10G).
