# REVIEW/SKIP Reduction — Package E Candidate (Seed / Data-state / Harvest)

- **Baseline:** Run #168 official GREEN BASELINE. Pointer **NOT moved**. Full stress **NOT run** (operator-dispatched). CI-deferred verification.
- **Change footprint:** spec-only, **1 file**. No backend code, no seed added, no stub, no pilot mutation, no auth/RBAC change.
- **Validation:** `node --check frontend/e2e-stress/specs/04-folio-mass.spec.js` → PASS. Architect: see review.

## The single safe fix — folio-mass void-target harvest window

**File:** `frontend/e2e-stress/specs/04-folio-mass.spec.js`

**Problem (data-state, documented in-spec):** tests run serial. C (split-by-amount) and
C3 (refund) both operate on `(folios||bookings).slice(0,10)` — folios[0..9]. C4
(void-charge) and C5 (void-payment) then sampled the **same** `slice(0,5)` =
folios[0..4]. By the time C4/C5 ran, those folios' charges/payments had already been
consumed by C/C3, so the void path never executed and the spec emitted a vacuous
data-state finding (C4 `allEmpty` → P2, C5 `allNoPay` → P3). The void assertions were
trivially-skipped, i.e. coverage was not actually exercised.

**Fix:** added `voidSampleWindow(src)` — samples `src.slice(10,15)` (a window PAST the
C/C3 destructive range 0..9 but INSIDE the A creation range 0..99 and the B creation
range 0..49), falling back to the original `src.slice(0,5)` when the pool is too small
(`length < 16`). C4 and C5 now call `voidSampleWindow(...)` instead of `.slice(0,5)`.

**Why it is by-construction safe (no baseline regression, no assertion loosening):**
- The status ladders of C4 (`all403`/`allEmpty`→REVIEW, `voided===0`→FAIL, else PASS)
  and C5 (`all403`/`allNoPay`→REVIEW, `voided===0`→FAIL, else PASS) are **unchanged**.
- The `5xx → FAIL` invariant and every REVIEW fallback are preserved verbatim.
- The fix does NOT self-create a void target, so it introduces **no new FAIL class**:
  void was already FAIL-able whenever charges/payments existed; the change only makes
  the intended void path run by sampling folios that still hold their A/B-created data.
- When the pool is small the window degrades to the exact prior `slice(0,5)` behaviour
  (including the allEmpty/allNoPay REVIEW outputs) → strictly additive.

**Effect (expected):** in the seeded full-suite run C4/C5 now exercise the real void
path → the vacuous C4 P2 / C5 P3 close and the void assertions become genuine
coverage. This is strengthening, not fake-green. Cannot be confirmed locally (full
stress is operator-dispatched); verdict is CI-deferred.

## Everything else — honest classification (no code)

- **CONFIRM-BY-DESIGN (6):** finance_folio `no_created_payment_to_void` (create→void
  lifecycle; SKIP honest when upstream create blocked) · notification_batch activity
  feed empty (distinct surface from enqueue; empty in baseline → not async lag → poll
  would not help; already P2-flagged, never FAILs) · VCC no stress booking
  (factory-seed dependency; bookings-by-`stress_prefix` harvest proven elsewhere = not
  drift) · full_24h data scarcity (integration smoke needs healthy seed) ·
  revenue_management hurdle/queue IDOR (self-sufficient stress create; pilot IDOR probe
  by-design) · city ledger transfer pre-req (self-created via real product flow +
  `_build_f8e_docs` seed).
- **DO_NOT_TOUCH-pilot (2):** payment_pos_reconciliation open-shift (blind-seed
  prohibition; `uniq_tenant_open_shift`; self-open is correct) · accommodation_tax
  pilot declaration pool (success read needs a PILOT declaration; pilot must not be
  mutated).
- **ROADMAP (1 + 1 sub):** POS recipe/BOM seed (out of scope per Task #11; cleanup
  supports it but adding a recipe/inventory seed has unverifiable green-spec safety →
  blind-seed risk → deferred, NOT stubbed) · public_token rotation endpoint (genuinely
  absent in backend; env-only `ROOM_QR_SECRET`).

## Doctrine compliance
external_calls=[] (unchanged), pilot_drift=0 (unchanged), no seed/stub/RBAC/auth
change, baseline #168 pointer not moved, no full stress run, no mobile/F10, no
skip-as-pass, no assertion loosening.
