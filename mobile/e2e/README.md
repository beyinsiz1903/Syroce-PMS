# Mobile E2E — F10A Smoke Matrix

> **Status:** scaffold (Task #83 / F10A kickoff, 2026-05-27)
> **Surface:** Expo Router (`mobile/app/`), 24 screens across 5 role groups
> **Runner:** Playwright Web hitting the Expo Web dev server on port 8080.
>   Native (iOS/Android) coverage is **out of scope for F10A** — see
>   `docs/F10_MOBILE_COVERAGE_ROADMAP.md` §4 for the Detox/Maestro plan.

## Why Playwright Web, not Detox/Maestro yet

Detox/Maestro need iOS Simulator / Android Emulator runners which aren't
available in the current Replit environment. Expo Web renders the same
component tree from `mobile/app/` and exercises the same auth/storage
flows, so we can lock in:

- Route reachability (no router 404, no white screen)
- Public route auth-gating (protected routes redirect to /login)
- PII/token leak scan on rendered DOM (JWT, card number, e-mail list patterns)
- Console error budget per route

Native-only surfaces (biometric lock, push, signature pad, ID-photo
encrypted upload) **cannot** be proven from web; F10B will add a Detox
harness for those when a runner is provisioned.

## Doctrine (inherits from F8/F9)

- Fake PASS yok, skip-as-pass yok.
- `external_calls = []` per spec — no real outbound to OTAs / Quick-ID.
- Pilot mutation = 0 — smoke is **read-only** (no POST/PUT/DELETE).
- Module-blocked / route-missing → P2 REVIEW, never PASS.
- PII/token leak on any rendered route = P0.

## Run locally

```bash
# 1. Start the Expo Web workflow (already configured)
# Workspace → workflows → "Mobile Web"

# 2. From repo root
cd mobile/e2e && npm install && npx playwright install chromium
E2E_MOBILE_BASE_URL=http://localhost:8080 npx playwright test
```

## Files

- `routes.js` — single source of truth: 24 routes × role group × criticality
- `smoke.spec.js` — navigate every route, run console + PII/token scan
- `playwright.config.js` — chromium-only, 2 viewports (mobile + tablet)

## CI

Not yet wired. Task #94 follow-up: add markdown drill-report reporter,
then Task #93 baseline run on the live pilot environment.
