# Stress Coverage Gap Report — 2026-05-26

> Audit period: 2026-05-24 (last GREEN baseline) → 2026-05-26.
> Audit scope: F8 stress series (`frontend/e2e-stress/specs/`) — production
> readiness signal across PMS, POS, Spa, Compliance, Channel Manager,
> Identity, Finance, RMS, B2B sub-router matrix.
> Suite root: `frontend/e2e-stress/specs/` (84 spec files present on disk;
> verified baseline still 68 — see "Pending verification" below).

---

## 1) Current verified baseline

| Field | Value |
|---|---|
| Date | **2026-05-24** |
| Commit | `ee7573b3` |
| Spec count | **68** |
| failedTests | **0** |
| P0 finding | **0** |
| P1 finding | **0** |
| P2 / P3 finding | enumerated in drill report |
| external_calls_made | **`[]`** |
| pilot_drift | **0** |
| cleanup#1 status | 200 (OK) |
| cleanup#2 (idempotency) | idempotent |
| Final verdict | **GO** |
| Drill report | `docs/drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md` |
| Roadmap reference | `docs/STRESS_TEST_ROADMAP.md` "Latest verified baseline (2026-05-24)" |

This baseline is the **only** GREEN reference in production trust narrative;
any later "GREEN" must be reproduced end-to-end through full-suite run + drill
report + verdict gate before it replaces the 68-spec line.

---

## 2) New specs pending full-suite verification (16 new spec files)

Specs added after `ee7573b3` but **not yet** included in a GREEN full-suite
baseline. Each was written with F8 doctrine (try/finally, recFinding,
assertNoExternalCallsPostBatch, assertPilotDriftZero, module-blocked → SKIP
+ P2 only for true 403/404/fixture absence) and individually targeted-run
verified — but suite-level ordering, state-sharing, cleanup interaction must
still be proven.

### Local Compliance & Money Safety Pack (F8X–F8AA)

| Spec | Module | Verified status |
|---|---|---|
| `98-efatura-earsiv-dryrun.spec.js` | `compliance_efatura` | targeted-run only |
| `65-identity-reporting-kbs-jandarma-dryrun.spec.js` | `identity_reporting` | targeted-run only |
| `98-payment-pos-reconciliation-dryrun.spec.js` | `payment_pos_recon` | targeted-run only |
| `66-kvkk-retention-deletion-anonymization.spec.js` | `kvkk_retention` | targeted-run only |

### Spa & Wellness Operational Stress (F8AB)

| Spec | Module | Verified status |
|---|---|---|
| `98-spa-wellness-operational.spec.js` | `spa_wellness_ops` | targeted-run only |

### POS KDS + F&B Inventory Stress (F8Z.2)

| Spec | Module | Verified status |
|---|---|---|
| `98-pos-kds-inventory.spec.js` | `pos_kds_fnb_inventory` | targeted-run caught backend P0 (KDS `/complete` cross-tenant) — **fix already in place, see §3** |

### RMS Revenue Deep (F8AF)

| Spec | Module | Verified status |
|---|---|---|
| `98-rms-revenue-deep.spec.js` | `revenue_management` | targeted-run only |

### Konaklama Vergisi Dryrun (F8AD)

| Spec | Module | Verified status |
|---|---|---|
| `98-konaklama-vergisi-dryrun.spec.js` | `konaklama_vergisi` | targeted-run only |

### B2B Sub-Router Matrix (F8M v2)

| Spec | Module | Verified status |
|---|---|---|
| `41B-b2b-subrouter-matrix.spec.js` | `b2b_subrouter_matrix` | targeted-run only |

### Newer additions written this session (post-roadmap)

| Spec | Module | Verified status |
|---|---|---|
| `99-pos-extensions.spec.js` | `pos_extensions` | written, **not** targeted-run verified |

### Other specs present on disk but not in 68-baseline (delta inspection needed)

`98-ops-surface-smoke.spec.js`, `98-vcc-pci-compliance.spec.js`,
`98-golf-operational.spec.js`, `99-full-24h-hotel-simulation.spec.js`,
`98C-twofa-totp-lifecycle.spec.js`, `98-pos-deep-lifecycle.spec.js` —
require provenance audit to confirm each is targeted-run verified or
explicitly noted as draft.

---

## 3) Known blocker — resolution status

### KDS `/complete` cross-tenant mutate gap (P0)

**Predicted by:** `98-pos-kds-inventory.spec.js` C test (L292–L360).
**Affected endpoints (3):** all KDS mutation paths in
`backend/domains/pms/pos_fnb_router/kitchen.py`.

| Endpoint | Line | Tenant filter present? |
|---|---:|---|
| `PUT /fnb/kitchen-order/{order_id}/status` | 587–589 | ✅ `{'tenant_id': current_user.tenant_id, 'id': order_id}` |
| `POST /fnb/kitchen-order/{order_id}/complete` | 604–606 | ✅ `{'id': order_id, 'tenant_id': current_user.tenant_id}` |
| `POST /pos/kds/update-order-status` | 628–630 | ✅ `{'id': order_id, 'tenant_id': current_user.tenant_id}` |

Hardening comment at `kitchen.py:600–603` documents the prior gap and the
fix intent. Spec C test asserts `expect(xComplete.status).toBeGreaterThanOrEqual(400)`
at L357 — hard-fails any regression. **No severity downgrade applied. No
assertion loosened.** The fix is in place; full-suite re-baseline (Step 3)
must confirm GREEN end-to-end before the 68 → 74+ rollover.

---

## 4) POS remaining gaps (after 99-pos-extensions and F8Z.2)

| Gap | Severity | Notes |
|---|---|---|
| Receipt re-print audit chain (after fiscal CB rollback) | P2 | Print spool + fiscal queue exist; no spec proves "reprint must reference original ÖKC receipt no" |
| Multi-cashier same-station hand-off (close → reopen by next operator) | P2 | Shift close added (`pos_shift_close.py`); hand-off race not exercised |
| Negative tip / over-tender refund path | P2 | Multi-currency payment added; explicit refund-with-tip path not covered |
| Loyalty redeem vs Happy-Hour stacking precedence | P3 | Both modules added independently; stacking order not asserted in spec |
| Barcode scan with EAN-13 check-digit failure | P3 | `pos_barcode.py` lookup tested; malformed-input rejection not asserted |
| ESC/POS adapter timeout/disconnect retry semantics | P2 | Simulator driver covered; real `escpos_tcp` adapter path requires hardware fixture |
| TR ÖKC EOD totals reconciliation against folio mass | P2 | `pos_fiscal.py` EOD simulator covered; cross-check against `folio_charges` aggregate not asserted |
| Coupon redemption replay under network retry (idempotency-key absent) | P1 candidate | `pos_coupons.py` uses atomic `findOneAndUpdate`; replay safety verified via race-guard test but Idempotency-Key header path not exercised |

---

## 5) Spa remaining gaps (after F8AB)

| Gap | Severity | Notes |
|---|---|---|
| Therapist commission accrual under cancellation race | P2 | Lifecycle covered; commission ledger not exercised |
| Package multi-service booking atomicity (all-or-nothing) | P2 | Single-service appt covered; package atomicity not asserted |
| Resource (room + therapist) double-book under sub-second concurrency | P2 | 409 conflict guard tested in serial; concurrent burst not asserted |
| Waitlist FIFO promotion when multiple slots open simultaneously | P3 | Promote covered for single slot; multi-slot ordering not asserted |
| Spa upsell folio post replay-vs-charge_to_room=false branch | P2 | `charge_to_room=True + reservation_id=null` short-circuit covered; folio-charge path untested |
| KVKK guest-pref retention (allergy/medical notes) deletion path | P1 candidate | `spa_appointments` cleanup covered; PII retention rule for medical notes not asserted |
| Cross-tenant spa_services catalog read | P1 candidate | Cross-tenant appt mutate covered (P0 expect); catalog leak path needs explicit assert |

---

## 6) Next module candidates (priority order, ETA per spec ≈ 0.5–1 day)

| # | Module | Coverage gap rationale | Suggested spec id |
|---:|---|---|---|
| 1 | **Laundry** | Guest laundry orders + in-house linen turnover share folio-posting + housekeeping handoff; no current spec | `98-laundry-operational.spec.js` |
| 2 | **Maintenance** | Maintenance work orders intersect HK OOO state and inventory parts consumption; no current spec | `98-maintenance-workorder.spec.js` |
| 3 | **Lost & Found** | Guest data + retention + chain-of-custody; KVKK overlap; no current spec | `98-lost-found-kvkk.spec.js` |
| 4 | **Concierge** | Reservation requests + 3rd-party vendor outbox; SSRF + external_calls invariant exposure | `98-concierge-vendor-outbox.spec.js` |
| 5 | **Multi-property** | Cross-property folio split, group billing, central reservation; multi-tenant boundary at property granularity | `98-multiproperty-folio-split.spec.js` |
| 6 | **Migration / Import** | Bulk CSV/Excel import (guests/reservations/rates); tenant scope + dedup + idempotency | `98-migration-import-bulk.spec.js` |

Doctrinal constraints for new specs (all of the below are MANDATORY,
non-negotiable, per F8 series rules):

- `pilot mutation = 0` — every batch asserts via `assertPilotDriftZero`.
- `external_calls = []` — every batch asserts via `assertNoExternalCallsPostBatch`.
- `failedTests = 0`, `P0 = P1 = 0` at suite verdict.
- `try/finally` around every mutate path; cleanup idempotent on second pass.
- Module-blocked (403/404/fixture absent) → SKIP + P2 REVIEW only; never
  used as a fake PASS shortcut.
- Any `recFinding('P0', …)` or `recFinding('P1', …)` MUST be paired with
  an `expect()` hard-fail in the same test; severity downgrade is forbidden.

---

## 7) Pending follow-up (this report → next action)

1. **Unblock full-suite execution path** (one of):
   - Repair GitHub Actions: workflow file change (`checkout@v5` → `@v4`)
     pending push because Replit OAuth lacks `workflow` scope. Resolution
     paths: (a) edit `.github/workflows/stress.yml` directly on github.com;
     (b) reconnect Replit ↔ GitHub with `workflow` scope.
   - Run locally against `http://localhost:8000` — requires
     `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` (pilot super_admin) which
     are not currently provisioned as workspace secrets.
2. **Run targeted re-verification** of the 8 specs listed in §2 against
   chosen execution venue. Capture per-spec drill report; promote to
   §1 baseline only if all 8 → failedTests=0, P0=P1=0.
3. **Run full suite** — expected next baseline ≈ 74+ specs (68 baseline
   + 16 pending − any spec quarantined). Verdict ≥ GO WITH WATCH required.
4. **Promote baseline** in `docs/STRESS_TEST_ROADMAP.md`, write new
   `docs/drill_reports/YYYYMMDD_stress_full_stress_suite_GREEN_*.md`,
   touch ADR verified-status sections, update
   `docs/PILOT_TRUST_NARRATIVE.md` and `replit.md` Gotchas pointer.

Until §7.1 is unblocked, this report is the audit of record. **The 68-spec
2026-05-24 GREEN baseline remains the only line eligible for production
trust narrative.**
