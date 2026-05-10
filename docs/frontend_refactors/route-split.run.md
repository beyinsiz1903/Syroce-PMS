# Route Definitions Split — Run Artifact

**Date**: 2026-05-10
**Commit**: `a63d6630` — `routes: split routeDefinitions.jsx into 14 semantic sections + lazy registry`
**File**: `frontend/src/routes/routeDefinitions.jsx` (596 → 98 lines composer)

## Goal

Split monolithic `routeDefinitions.jsx` (596 lines, ~232 lazy imports + 258
route entries inside `getRouteConfigs()`) into a lazy registry plus 14
semantic section files, while preserving the public API consumed by
`App.jsx` and `pages/ModuleDiscovery.jsx`.

## Public API (preserved)

Still exported by `frontend/src/routes/routeDefinitions.jsx`:

- `AuthPage`, `Dashboard`, `LandingPage`, `PrivacyPolicy`, `GuestPortal`
- `getRouteConfigs({ user, tenant, modules, isAuthenticated, onLogout, hasFeature })`

The `isAuthenticated` and `hasFeature` parameters are kept in the signature
(marked `void` in the body) for forward compatibility — no current consumer
reads them inside the route builder.

## New layout

```
frontend/src/routes/
├── routeDefinitions.jsx          # 98 lines — thin composer
├── lazyWithPreload.js            # unchanged
├── ProtectedRoute.jsx            # unchanged
├── preload.js                    # unchanged
└── sections/
    ├── lazyPages.js              # central lazy registry (5 named exports)
    ├── public.js                 # 12 routes
    ├── coreOperations.js         # 41 routes
    ├── reservations.js           # 11 routes
    ├── financeReports.js         # 17 routes
    ├── channelManager.js         # 25 routes
    ├── revenueRms.js             # 13 routes
    ├── marketplaceLoyalty.js     #  8 routes
    ├── guestStaff.js             # 17 routes
    ├── frontdeskMaintenance.js   #  4 routes
    ├── mobile.js                 # 21 routes
    ├── executiveOps.js           # 20 routes
    ├── infrastructure.js         # 13 routes
    ├── hotelFeaturesAi.js        # 22 routes
    ├── securityAdmin.js          # 30 routes
    └── operaParity.js            # 11 routes
```

Each section file exports a `<name>Routes({ p, pa, pm, modules })` builder
that closes over the per-render helpers built once in
`getRouteConfigs()`.

## Verification

| Check                               | Result      |
|-------------------------------------|-------------|
| Path parity (old vs new)            | **258 = 258** |
| Duplicate paths                     | **0**         |
| `git diff` of sorted unique paths   | empty (no drift) |
| `yarn build`                        | pass (architect-run) |
| Vite hot-reload after split         | clean       |
| `/landing` render                   | OK          |
| Browser console errors              | none        |
| App.jsx import surface (untouched)  | OK          |
| `ModuleDiscovery.jsx` consumer      | OK (unchanged) |

Reproduce path parity locally:

```bash
diff \
  <(git show HEAD~1:frontend/src/routes/routeDefinitions.jsx \
      | grep -oE 'path: "[^"]+"' | sort -u) \
  <(grep -hoE 'path: "[^"]+"' frontend/src/routes/sections/*.js | sort -u)
# expected: empty diff
```

Reproduce duplicate check:

```bash
grep -hoE 'path: "[^"]+"' frontend/src/routes/sections/*.js \
  | sort | uniq -d
# expected: empty output
```

## Notes / dikkat noktaları

- `/b2b/docs` lives in `public.js` for URL-namespace grouping but is wired
  with `pa(...)` (super-admin protected) — preserves original behavior; a
  comment marker was added in the section file to flag this on next read.
- Section ordering inside `getRouteConfigs()` follows the original visual
  order of the comment headers in the pre-split file. React Router v6
  ranks by path specificity, so reordering would not affect correctness,
  but ordering is preserved to keep diffs reviewable.
- All `wrapLayout: true` / `layoutModule: "..."` flags preserved verbatim
  per the M5 layout convention (Routes own the Layout wrap, not pages).

## Architect verdict

**Pass** — public API contract preserved, helper closure semantics intact,
no security regression, build green. Optional (not done): CI guard test for
route-count + duplicate paths + exported API key stability.

## Follow-ups (deferred)

- Optional: snapshot test for `{path, type, featureKey/moduleKey,
  wrapLayout, layoutModule}` keys to prevent silent drift in section files.
- Sıradaki refactor adayı: `requirements.txt` split (daha riskli — küçük
  ve kontrollü yapılmalı).
