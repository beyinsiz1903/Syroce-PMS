---
name: Mobile smoke single-role login timeout
description: One role's mobile-smoke login→redirect 100% timeout (others pass) = that role's E2E secret/account, not code.
---
When F10A mobile-web-smoke shows ONE role's `login → group root` waitForURL timing out
100% while the other roles pass, it is that role's `MOBILE_E2E_<ROLE>_EMAIL/PASSWORD`
GitHub Actions secret / account on the deployed backend — NOT the app or backend.

**Why:** AuthGate's post-login redirect is role-agnostic — any successful login lands on
`/` (Expo Web strips the group segment). So a single role failing to redirect 100% means
the login call itself returned non-200 (bad / inactive / locked account). A redirect-code
or backend bug would break every role, not one.

**Verify backend health before touching code (all should be ≤~2s):**
- `GET /api/health/` → 200
- bogus-cred `POST /api/auth/login` → clean 401
- a real account you DO hold (e.g. stress admin) → 200 + access_token
If those pass, the smoke failure is credential/flake, not backend. The mobile prod
backend is a Reserved VM (always-on), so cold-start latency is not the usual cause.

A *flaky* role (passes on Playwright retry) with a fast backend is CI timing jitter —
e.g. the submit click landing before web hydration wires `onPress` — not a real failure.

**How to apply:** the smoke fast-fails on the rendered login error so a 401 surfaces its
real message in ~2s instead of a 30s nav timeout. Do NOT loosen the smoke to make it pass
— fix the operator secret / account.
