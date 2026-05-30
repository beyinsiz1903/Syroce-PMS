---
name: Stress FE-render selector-miss may be route drift, not "UI changed"
description: A browser-render stress check that reports noRows/selector-miss REVIEW may be pointing at the wrong route (a dashboard instead of the grid page); verify the component's real route + data-testid before trusting the REVIEW.
---

# A stress FE-render REVIEW ("selector miss / noRows / UI changed") may be route+selector drift

When a browser-rendering stress check (page.goto a UI route, then count rows by a
selector whitelist, then measure TTI) reports a "selector miss / noRows" REVIEW, do
NOT assume the UI changed or auth failed. First confirm the test is on the route that
actually renders the target component.

**Why:** dashboards and their data grids are frequently split across two routes — e.g.
a `/x` dashboard of quick-action cards vs a `/x-status` page that renders the actual
grid component. A check pointed at the dashboard route will never find grid rows, so
its perf/coverage assertions stay vacuous (perpetual REVIEW) even though nothing is
broken. Compounding this, hand-written selector whitelists drift from the component's
real `data-testid` values (grids often emit *suffixed* ids like `room-card-<id>` /
`status-btn-<id>-<state>`, which an exact `[data-testid="room-card"]` never matches).

**How to apply:**
1. Trace the route -> page -> component (route config sections, navItems) to find which
   route renders the grid, and read the component to get its real `data-testid` strings.
2. Fix the route and use a prefix selector (`[data-testid^="room-card-"]`) when ids are
   suffixed; keep legacy selectors as defensive fallbacks.
3. Do NOT add new data-testid to the app if the grid already exposes stable ones — this
   is pure test drift, not an app change.
4. Caveat: fixing such drift *activates* a previously-vacuous gate. A non-virtualized
   grid (maps over all rows) may then breach a perf/TTI gate at high row counts and flip
   REVIEW->FAIL. That is intended detection of real perf debt, not a test regression —
   the remedy is a product decision (virtualization/pagination) or an explicit gate
   re-baseline, never loosening the assertion. Disclose this CI-deferred risk when the
   full suite cannot be run locally.
