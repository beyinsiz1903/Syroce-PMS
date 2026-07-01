# REVIEW/SKIP Reduction — Package F Inventory (Frontend/UI Selector & Render Coverage)

- **Baseline:** Run #168 official GREEN BASELINE (PASS/FAIL/REVIEW/SKIP = 1382/0/48/43, P2=57/P3=1). Pointer **NOT moved**.
- **Scope:** Frontend/UI selector drift & render coverage REVIEW/SKIP only. No mobile/F10, no visual redesign, no backend stub. No full stress (operator-dispatched). Targeted/local `node --check` only.
- **Doctrine:** no fake-green, no auth/RBAC weakening, no pilot mutation, external_calls=[], pilot_drift=0, baseline #168 pointer NOT moved. Do NOT downgrade a real UI failure into REVIEW; do NOT skip a failing UI path to reduce counts. data-testid only when a stable user-facing equivalent already exists and the addition is non-behavioral.
- **Method:** 2 parallel explore subagents — (a) which stress specs perform real browser rendering / DOM selectors / TTI, with line+selector evidence; (b) the actual React routes/components behind housekeeping / messaging / frontdesk / admin-settings / POS, to decide drift-fix vs intentional-absence vs auth-gate. Then verified each candidate by reading the spec + component directly.

## Critical scoping finding
Across **all** `frontend/e2e-stress/specs/`, only **ONE** spec performs real browser rendering
(`browser.newContext` + `page.goto` to a UI route + `.locator`/DOM selectors + TTI):
**`08-housekeeping-mass.spec.js`**. Every other "UI-ish" REVIEW/SKIP in the stress suite is an
**API/HTTP probe**, not a DOM-selector check — so there is no selector to "fix" for those; they
were already classified under Packages D (endpoint/surface) and E (data-state). Adding browser
UI-render coverage for messaging/frontdesk/admin/POS would be **new test surface = ROADMAP**, not
a selector-drift fix, and is out of Package F scope.

Evidence: `rg -l "page\.goto\(" .` and `rg -l "browser\.newContext|\.locator\(|getByTestId|getByRole" .`
in `frontend/e2e-stress/specs/` both return only `08-housekeeping-mass.spec.js`.

## Surface-by-surface

| # | Surface | Spec / route (evidence) | Component reality | Verdict |
|---|---------|-------------------------|-------------------|---------|
| 1 | housekeeping FE render TTI selector miss | `08-housekeeping-mass.spec.js`: `page.goto('/housekeeping')` (was L274), selector candidates `room-card`/`hk-room-row`/`tr[data-room-id]`/`div[data-room-id]`/`.room-card` (was L284-290); `noRows → REVIEW` (L372-375) | `/housekeeping` = `HousekeepingDashboard` (quick-action cards, NO room grid). Room grid lives at `/housekeeping-status` → `HousekeepingStatusPage` → `HousekeepingRoomGrid` (`coreOperations.js` L35). Grid container `data-testid="housekeeping-room-grid"`; each room `data-testid="room-card-${room_number}"` (L199); status buttons `data-testid="status-btn-${room_number}-${key}"` (L235). NONE of the spec's selectors could ever match → permanent vacuous `noRows` REVIEW. | **SELECTOR/ROUTE-FIX (DONE)** |
| 2 | notification/messaging UI selector drift | stress `45-notification-batch-dryrun.spec.js` + `98-mobile-staff-surface.spec.js` are **API probes** (`/api/messaging-center/*`), no DOM render | Messaging UI (`/messaging-center`) exists with stable testids, but **no stress spec renders it**. | **CONFIRM-BY-DESIGN** (no UI-render spec; API surface covered in Pkg D Wave 8) |
| 3 | frontdesk operational panels selector drift | no stress spec navigates `/pms-operations` in a browser | `PMSOperationalDashboard` exists with stable testids; no stress UI-render coverage. | **CONFIRM-BY-DESIGN** (no UI-render spec; ROADMAP if coverage desired) |
| 4 | admin/settings screens (route exists, selector stale) | `30-admin-rbac.spec.js`, `31-settings-audit.spec.js` are **API probes** | `AdminHub`/`AdminControlPanel` exist but are **super-admin gated**; stress admin is tenant-scoped (Pkg D fail-closed 404 doctrine). | **CONFIRM-BY-DESIGN** (no UI-render spec; auth-gate correct) |
| 5 | marketplace/POS UI checks | no stress spec renders `/marketplace` or `/pos` in a browser | `MarketplaceModule`/`POSDashboard` exist with stable testids; no stress UI-render coverage. | **CONFIRM-BY-DESIGN** (no UI-render spec; ROADMAP if coverage desired) |

## Outcome
- **1 SELECTOR/ROUTE-FIX implemented** (#1 housekeeping). All others honestly CONFIRM-BY-DESIGN: the
  candidate areas have **no DOM-render stress spec** to carry a stale selector — they are API probes
  (handled in Packages D/E) or super-admin-gated by design. Adding new browser UI-render specs is
  ROADMAP, not a selector fix, and out of Package F scope.
- **No data-testid added** (the grid already exposes stable `room-card-*` / `status-btn-*` testids —
  the spec simply targeted the wrong route + wrong selector). **No backend code, no stub, no redesign,
  no pilot mutation, no auth/RBAC change.**
