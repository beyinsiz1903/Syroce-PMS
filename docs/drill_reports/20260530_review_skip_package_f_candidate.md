# REVIEW/SKIP Reduction — Package F Candidate (Frontend/UI Selector & Render Coverage)

- **Baseline:** Run #168 official GREEN BASELINE. Pointer **NOT moved**. Full stress **NOT run** (operator-dispatched). CI-deferred verification.
- **Change footprint:** spec-only, **1 file**. No backend code, no data-testid added (grid already exposes them), no stub, no pilot mutation, no auth/RBAC change, no visual redesign.
- **Validation:** `node --check frontend/e2e-stress/specs/08-housekeeping-mass.spec.js` → PASS. Architect: see review.

## The single safe fix — housekeeping FE render TTI selector + route drift

**File:** `frontend/e2e-stress/specs/08-housekeeping-mass.spec.js`

**Problem (genuine selector + route drift):** the FE render/TTI test navigated to
`/housekeeping`, which is the `HousekeepingDashboard` (quick-action cards) and renders
**no room grid**. The actual room grid lives at `/housekeeping-status`
(`HousekeepingStatusPage` → `HousekeepingRoomGrid`, registered in
`frontend/src/routes/sections/coreOperations.js` L35). Worse, the spec's selector
whitelist (`[data-testid="room-card"]`, `hk-room-row`, `tr[data-room-id]`,
`div[data-room-id]`, `.room-card`) matched **none** of the grid's real selectors —
the grid emits `data-testid="room-card-${room_number}"` (suffixed, L199) and status
buttons `data-testid="status-btn-${room_number}-${key}"` (L235). So `total_rows`
was always 0 → the test fell into the `noRows → REVIEW` branch every run (a vacuous
selector-miss; the TTI/perf coverage never actually ran).

**Fix (3 spec edits, no logic/assertion change):**
1. Route: `page.goto('/housekeeping')` → `page.goto('/housekeeping-status')`.
2. Selector whitelist: prepended `[data-testid^="room-card-"]` (matches the real
   suffixed testid); legacy candidates kept as defensive fallbacks.
3. Mobile transition action: prepended `[data-testid^="status-btn-"]` to the existing
   `button:has-text("Temiz")/("Clean")/[data-testid="hk-action"]` locator.
4. Cosmetic: the `rec` endpoint note `/housekeeping (FE)` → `/housekeeping-status (FE)`.

**Why no fake-green / no assertion loosening:**
- The verdict ladder is **byte-for-byte unchanged**:
  `status = noRows ? 'REVIEW' : (slow ? 'FAIL' : 'PASS')`, the `ROW_GATES`
  (50<3s / 200<6s / 500<10s), `dom_ms<10s`, `first_row_ms<8s`, and the `slow → P2
  recFinding` are all untouched.
- No data-testid was added — the grid already exposes stable user-facing testids; the
  spec was simply pointed at the wrong route with the wrong selector. This is pure
  drift correction, not a behavioral change to the app.
- The `external_calls` post-batch invariant (`assertNoExternalCallsPostBatch`, hard
  `expect(...).toBe(true)`) and the pilot-drift test are unchanged.

**Effect (expected) + transparent CI-deferred risk:** in the seeded full suite the test
now targets the real grid, so the **previously-vacuous `noRows` REVIEW closes** and the
TTI gate runs for real. This is **strengthening, not fake-green**. Honest risk
disclosure: this *activates a previously-vacuous FAIL gate*. The grid renders rooms
**without virtualization** (`filteredRooms.map(...)`), and the spec itself anticipates
this ("500-oda render için virtualization/pagination gerekli olabilir"). Therefore, in
the seeded full run the outcome is one of:
- TTI within gates → `PASS` (REVIEW→PASS, clean strengthening), or
- a real 500-room render breach → `P2` finding + `status=FAIL` (a **genuine perf
  finding**, i.e. intended detection — *not* a test-logic regression; consistent with
  the architect's Package E ruling that a now-executing real path surfacing a real
  problem is detection, not a new fail class).

Because full stress is operator-dispatched, the outcome cannot be confirmed locally
(CI-deferred). If the operator wants to keep the suite strictly GREEN and the 500-room
render genuinely breaches, the remedy is a **product decision (grid virtualization)** or
an explicit perf-gate re-baseline — **not** loosening this test. Per doctrine, the test
must report the truth; the perf gate was deliberately left intact.

## Everything else — honest classification (no code)

- **CONFIRM-BY-DESIGN (4):** notification/messaging, frontdesk panels, admin/settings,
  marketplace/POS — none of these has a **DOM-render stress spec** carrying a stale
  selector. In the stress suite they are **API/HTTP probes** (`/api/messaging-center/*`,
  admin/settings audit endpoints) already classified in Packages D (endpoint/surface) and
  E (data-state), or are **super-admin-gated by design** (admin hub; Package D fail-closed
  404 doctrine, stress admin is tenant-scoped). There is no selector to fix.
- **ROADMAP (implicit):** adding browser UI-render coverage (page.goto + selectors + TTI)
  for messaging/frontdesk/POS would be **new test surface**, not a selector-drift fix, and
  is out of Package F scope. No stub added.

## Doctrine compliance
external_calls=[] (unchanged), pilot_drift=0 (unchanged), no backend/seed/stub/RBAC/auth
change, no data-testid added, no visual redesign, baseline #168 pointer not moved, no full
stress run, no mobile/F10, no skip-as-pass, no real-UI-failure downgrade, no assertion
loosening.
