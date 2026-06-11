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
fake-green. To reconcile such a spec, navigate explicitly into the group
(parens-qualified URL or in-app nav into the group) before asserting; do not
rely on `goto('/')`. The `(home)/today` rol-branch is only a lightweight KPI
summary — it deliberately does NOT mirror the Tier-2 flagship testIDs, so you
cannot satisfy a Tier-2 spec by landing on today.
