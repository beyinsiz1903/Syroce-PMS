---
name: Expo Tier-2 group-index reachability + shell-landing staleness
description: Why goto('/') no longer reaches a Tier-2 role group index, and how that staleness breaks e2e specs after the staff shell unification.
---

# Tier-2 group index screens are NOT reachable via a plain goto('/')

In the mobile app, each role's dedicated Tier-2 area is an Expo Router group:
`app/(housekeeping)/index.tsx`, `app/(gm)/index.tsx`, `app/(frontdesk)/index.tsx`.
Parenthesized group segments are hidden from the clean URL, so every one of
these group `index.tsx` files maps to the bare path `/` — they collide. The
only unambiguous way to land on a specific group's index is the
parens-qualified Href (e.g. `ROUTES.housekeeping = '/(housekeeping)'`) via an
in-app `router.push` / role switcher / module button — NOT a clean `/`.

**Why:** Staff landing was unified into the common `(home)` shell, and
`rootForRole` returns the `(home)` landing for every non-guest role (it returns
the "Bugün"/today tab after the P5 role-based bar change; earlier it returned
the index/notifications screen). Either way, an authenticated staff session that
hits `/` is redirected by AuthGate INTO `(home)`, never into a Tier-2 group.

**How to apply:** Any e2e/spec that does `page.goto('/')` and then waits for a
Tier-2-only signal (a testID or an endpoint that only the group index fires,
e.g. housekeeping room-card testIDs `hk-room-assign`/`hk-room-status`, or the GM
`/api/gm/snapshot-enhanced` snapshot) is STALE — it now lands on the `(home)`
shell and will fail honestly (timeout / wrong empty-state), it does NOT
fake-green. The `(home)/today` rol-branch is only a lightweight KPI summary — it
deliberately does NOT mirror the Tier-2 flagship testIDs, so you cannot satisfy
a Tier-2 spec by landing on today.

**Canonical reconciliation (verified):** drive the REAL in-app path a single-role
user takes — `goto('/profile')` (a NAMED route inside `(home)`, so its clean URL
works; proven in `home-shell.spec`), then click the Profile module-grid button
`smoke-module-housekeeping` / `smoke-module-manager` (note: the GM module key is
`manager`, testID `smoke-module-manager`, routing to `ROUTES.gm`). Those buttons
call `router.push(ROUTES.housekeeping|gm)` CLIENT-SIDE — that client push is what
resolves the parens Href, NOT a fresh-document `goto('/(gm)')`. `hk-gm.spec` uses
an `openProfileModule(page, testid)` helper for exactly this. For a spec whose
target endpoint fires on the group-index MOUNT (e.g. GM snapshot), arm the
`waitForResponse` AFTER `/profile` settles but BEFORE the module click — the
request fires on the pushed group index, not on the profile landing. Module
visibility is entitlement-gated (`allAccess || role==='housekeeping'` /
`role==='gm'`), and `normalizeRole` collapses manager/gm/admin/super_admin → `gm`,
so a plain-manager or all-access CI account both see the manager module.
