# F8AH Ops Surface Smoke Stress — Drill Report

**Date:** 2026-05-24
**Series:** F8 Stress Test (ops-surface bundle)
**Spec:** `frontend/e2e-stress/specs/98-ops-surface-smoke.spec.js`
**Status:** Spec written; full-suite verification next round.

## Summary

Beş düşük-yüzey ops endpoint'i tek spec'te birleştirildi (5 module-block
+ Setup + Cleanup = 7 test). F8R–F8W "ops-readiness" doktrini + F8AC IDOR
+ cleanup pattern birebir uygulandı. Baseline 73 → **74 spec**.

## Modules covered

| Block | Module | Endpoint(ler) | IDOR vektörü |
|---|---|---|---|
| A | `cross_property_rollup` | `GET /api/cross-property/guests/search` | tenant_id-cross-leak (stress↔pilot) |
| B | `shift_handover` | full lifecycle | pilot bearer ack/delete |
| C | `webhook_admin_dlq` | `/api/webhooks/{status,deliveries,dlq}` | non-super-admin bypass |
| D | `eod_report` | `/preview` + `/pdf` (`/send` YASAK) | structural (body.tenant_id probe) |
| E | `booking_holds` | create/status/confirm/delete/sweep | pilot status/confirm/delete + post-state re-check |

## Doctrine confirmation

- ✅ Module-blocked pattern (her blok ayrı probe → SKIP + P2)
- ✅ P0 cross-tenant IDOR (`expect(...).toBeGreaterThanOrEqual(400)` hard-fail)
- ✅ try/finally `assertNoExternalCallsPostBatch` + `assertPilotDriftZero`
- ✅ Cleanup idempotent (DELETE round-trip)
- ✅ `STRESS_COLLECTIONS` += `shift_handovers` (orphan-scrub safety net)
- ✅ EOD `/send` ASLA çağrılmaz (external_calls invariant guarantee)

## Decisions worth noting

1. **cross_property pilot-side IDOR**: `_chain_tenant_ids` super_admin
   path'inde ALL tenants döndürür. Pilot bearer super_admin ise stress
   data görmesi "intended" — spec defensive (P0 finding emit eder,
   operator review).

2. **webhook_admin role-guard**: stress_token = tenant admin (NOT
   super_admin). 2xx → P0. Pilot super_admin: 401/403 olursa
   "fixture not super_admin" P2 (cross-tenant filter probe SKIP).

3. **booking_holds IDOR**: confirm/delete service'i best-effort 200
   döner. Breach signature = post-mutation stress side `has_hold`
   `true→false` flip (re-check ile detect).

4. **EOD `/send`**: source-level discipline (call yok) + runtime
   guarantee (post-batch external_calls=[]).

## Next steps

- Targeted local run: `yarn test:e2e:stress --grep "F8AH"`.
- Full Operational Stress Suite re-run (74 spec) → republish if green.
- F8AH-specific bug bulgusu varsa ayrı fix task (F8X pattern: spec
  görevi spec yazmak, fix değil).

## Files touched

- `frontend/e2e-stress/specs/98-ops-surface-smoke.spec.js` (NEW)
- `backend/domains/admin/router/stress.py` (`STRESS_COLLECTIONS` += `shift_handovers`)
- `docs/adr/2026-05-f8ah-ops-surface-smoke.md` (NEW)
- `docs/STRESS_TEST_ROADMAP.md` (F8AH section)
- `digitalocean.md` (Gotchas one-liner)
