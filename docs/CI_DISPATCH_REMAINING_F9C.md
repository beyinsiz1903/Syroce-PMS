# CI Dispatch — Remaining 5 F9C Specs (Task #82)

> **Status:** READY — awaiting GitHub Actions dispatch by a maintainer with repo access.
> **Doctrine:** failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0 per spec.
> **Path unblocked by:** Task #59 (`spec_pattern` workflow_dispatch input wired to `.github/workflows/stress.yml`).

The DigitalOcean Agent environment cannot dispatch GitHub Actions workflows.
The 7 F9C specs are all green locally (`node --check` + `--list` clean)
and the BEO (#99) + Sales (#98-sales-basic) runs are already in the
drill report archive. The 5 specs below need an explicit dispatch on
the deploy CI before F9E (full re-baseline) can run.

## How to dispatch (per spec)

1. GitHub Actions → **Full Stress Suite (one-shot)** → **Run workflow**.
2. Fill the dispatch inputs from the table below.
3. Wait for the run to finish (~3–6 minutes per spec).
4. Download the `stress-drill-report` artifact and verify in the JSON summary:
   - `failedTests == 0`
   - `P0 == 0` and `P1 == 0`
   - `external_calls == []`
   - `pilot_drift.bookings_delta == 0`
   - `verdict ∈ {GO, GO WITH WATCH}`
5. Commit the drill-report markdown into `docs/drill_reports/`.

## The 5 remaining specs

| # | Spec | `spec_pattern` | `report_tag` |
|--:|---|---|---|
| 1 | Maintenance work-order lifecycle | `specs/98-maintenance-workorder-lifecycle.spec.js` | `f9c_maintenance` |
| 2 | Messaging template lifecycle (amended: J3/J4 doctrine IDOR, D2 delete-lifecycle, A1 automation CRUD, S1 scheduler probe) | `specs/98-messaging-template-lifecycle.spec.js` | `f9c_messaging` |
| 3 | Mobile staff surface | `specs/98-mobile-staff-surface.spec.js` | `f9c_mobile_staff` |
| 4 | Mobile cashier surface | `specs/98-mobile-cashier-surface.spec.js` | `f9c_mobile_cashier` |
| 5 | Marketplace deep lifecycle | `specs/98-marketplace-deep-lifecycle.spec.js` | `f9c_marketplace` |

## Pre-flight (must be true before each run)

- `E2E_STRESS_TENANT_ID` ≠ `PILOT_TENANT_ID` (assertion lives in `.github/workflows/stress.yml`).
- Stress tenant has the right modules enabled — for #2 (messaging) the
  template + automation collections exist; for #3/#4 (mobile) the mobile
  module is on; for #5 (marketplace) the marketplace module is on.
- For #2 the **pilot tenant** must also have at least one messaging
  template so the doctrine-direction IDOR probes (J3/J4) hit a real
  pilot id instead of the bogus UUID fallback — otherwise those steps
  emit a REVIEW row instead of the clean PASS that proves the boundary.

## After all 5 are green

→ Dispatch the full suite (empty `spec_pattern`) with `report_tag=f9e_full_app_rebase`
→ Write `docs/drill_reports/20260527_f9e_full_app_rebase.md`
→ Move F9C row in `docs/STRESS_TEST_ROADMAP.md` from 🟡 to ✅
→ Close Task #82.

## If a spec fails

Do **not** downgrade P0/P1 to P2/REVIEW (doctrine: F9 absolute rules).
Open a follow-up task with the drill-report artifact attached and the
spec/step that failed. Cleanup must still pass (idempotent `--apply`
sweep via `backend/scripts/cleanup_e2e_pilot_residue.py`).
