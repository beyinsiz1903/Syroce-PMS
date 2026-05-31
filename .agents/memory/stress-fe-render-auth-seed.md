---
name: Stress FE-render specs need token AND user seeded
description: Why a real-DOM stress spec sees 0 rows even with a valid token, and how the SPA auth gate decides isAuthenticated.
---

A browser-based stress spec that opens a real Playwright page, seeds the JWT into
`localStorage`, and navigates to a protected route can still render an EMPTY grid
(0 rows → vacuous REVIEW) even though the token is valid.

**Why:** the SPA's boot auth gate flips `isAuthenticated=true` only when BOTH
`localStorage.token` AND `localStorage.user` exist (and the token isn't locally
expired). With only `token` seeded it calls `clearAuthStorage()` → redirect to
`/auth` → the protected page never mounts → its data fetch never fires → grid is
empty. The page's own axios calls separately read `localStorage.token` for the
Bearer header, so people assume seeding `token` is enough — it is not for the
*route guard*.

**How to apply:** when a real-DOM stress/E2E spec must render a protected page,
seed `localStorage.user` (a minimal placeholder object is enough — the canonical
user is re-fetched from `/auth/me` with the token) in addition to `token` +
`token_ts`. Then a 0-row grid is a *real* auth/data/selector failure worth a hard
FAIL — but only gate the hard-assert on the FE actually serving the page
(navigation succeeded); a totally unreachable FE is an env/infra REVIEW, not a
product defect.
