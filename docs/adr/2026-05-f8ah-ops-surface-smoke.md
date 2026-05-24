# ADR: F8AH Ops Surface Smoke Stress

**Status:** Accepted — spec written 2026-05-24
**Series:** F8 Stress Test (ops-surface bundle, sister of F8R–F8W)
**Spec:** `frontend/e2e-stress/specs/98-ops-surface-smoke.spec.js`

## Context

Beş düşük-yüzey ama yüksek-risk operasyonel uç noktayı (her biri 3-5
endpoint) tek tek tam lifecycle stress'i hak etmiyordu; ancak hepsi
tenant isolation + admin-only guard + cross-tenant IDOR risklerini
taşıyor:

| Modül | Endpoint(ler) | Yapısal risk |
|---|---|---|
| `cross_property_rollup` | `GET /api/cross-property/guests/search` | Chain-rollup `get_system_db()` bypass, chain_id mis-link guest leak |
| `shift_handover` | `POST/GET/PATCH ack/DELETE /api/pms/shift-handover` | find_one_and_update/delete_one tenant_id filter bypass |
| `webhook_admin_dlq` | `/api/webhooks/{status,deliveries,dlq}` | Router-wide `require_super_admin_guard` bypass |
| `eod_report` | `/api/pms/eod-report/{preview,pdf,send}` | `_collect(tenant_id)` filter; `/send` external mail |
| `booking_holds` | `/api/booking-holds[/confirm,/status,/sweep]` | room_night_locks tenant_id filter bypass |

F8R–F8W'nin "ops-readiness" doktrini bu beş yüzeyi birleştirip tek
spec'te smoke + P0 IDOR + post-batch invariants ile kapatmaya uygundu.

## Decision

Tek spec, 5 module-block + Setup + Cleanup. Her blok:

1. **Module-blocked probe** — endpoint 403/404 ise `test.skip(true)` +
   P2 informational (`A/B/C/D/E` test'leri tekil skip; `Z` cleanup +
   final invariants her durumda çalışır).
2. **Smoke** — happy-path read + en güvenli write (handover create,
   booking_hold create, ack/delete self).
3. **P0 cross-tenant IDOR** — pilot bearer ile stress kaynağına mutate
   veya read; 2xx → `recFinding('P0', ...)` + `expect().toBeGreaterThanOrEqual(400)`
   hard-fail.
4. **Negative validation** — invalid `shift`, 5xx → P1.
5. **Cleanup idempotent** — DELETE round-trip; ikinci pass 404/200-no-op
   zorunlu (booking_holds release service idempotent by construction).
6. **try/finally** — her test `assertNoExternalCallsPostBatch` +
   `assertPilotDriftZero`.

### Modüle özgü kararlar

**A) cross_property_rollup** — `_chain_tenant_ids` super_admin path'inde
ALL tenants döndürür. Pilot bearer super_admin ise stress data görmesi
"intended" olabilir. Spec defensive: pilot probe'da returned `tenant_id`
=== `stressTid` ise P0 finding kaydet — operatör super_admin policy'sini
review etsin (false-positive değil, "yetki açık mı?" sorusu).

**B) shift_handover** — IDOR sırası: B5 (pilot ack/delete) → B6 (self ack).
B5 sonrası B6 sadece IDOR `find_one_and_update`'in DİKKATLİCE ack
etmediğini doğrulamak için (ack'lenmiş bir kayıt iki kez ack'lenebilir,
sorun değil; mesele tenant_id filter).

**C) webhook_admin_dlq** — stress_token tenant admin'dir (super_admin
DEĞİL). `require_super_admin_guard` 403 dönmeli; 2xx = P0. Pilot super_admin
beklenir; 401/403 olursa "pilot is NOT super_admin" P2 informational
(IDOR probe SKIP). `tenant_id` filter widening (stress_filtered > global)
= P1.

**D) eod_report** — `/send` external mail tetikler →
`external_calls=[]` invariant'ı kırılır. **Spec'te `/send` ASLA çağrılmaz.**
`_collect(current_user.tenant_id, ...)` yapısal filtre → leak yapısal
olarak imkânsız; sadece defensive `body.tenant_id == stress_tid` probe.
`/pdf` 5xx (weasyprint crash) = P1.

**E) booking_holds** — service opaque tag (FK yok); synthetic
`booking_id`/`room_id` (stress_prefix tagged) → orphan-scrub safety net.
IDOR pattern özel: confirm/delete genelde 200 dönüyor (best-effort, no
lock found → no-op). Breach signature = post-mutation stress side
`has_hold` `true→false` flip → P0.

### STRESS_COLLECTIONS

`shift_handovers` eklendi (orphan-scrub; spec-side DELETE primary).
`room_night_locks` zaten F8A altında (booking_holds residue kapsıyor).
cross_property/webhook_admin/eod read-only → ek koleksiyon yok.

## Consequences

- **Pozitif:** 5 düşük-yüzey ops endpoint tek spec'te kapatıldı; baseline
  73 → 74 spec. F8R–F8W doktrini paylaşılabilir paterne dönüştü
  (5-modül-tek-spec bundle).
- **Negatif:** cross_property pilot-side IDOR finding super_admin policy
  decision'a bağlı (false-positive olabilir); operatör review gerektirir.
  Webhook DLQ retry/dismiss write yüzeyi out-of-scope kaldı (F8AC-benzeri
  ayrı destructive spec gerektirir).
- **Risk:** booking_holds IDOR confirm/delete signatures 200-no-op
  döndüğü için detection sadece post-state re-check ile mümkün; service
  davranışı değişirse (e.g. 404 dönmeye başlar) re-check overhead'i
  gereksiz olur ama doğruluğu bozmaz.

## References

- `frontend/e2e-stress/specs/09-ops-readiness-smoke.spec.js` (F8R–F8W
  pattern source)
- `frontend/e2e-stress/specs/98-golf-operational.spec.js` (F8AC IDOR +
  cleanup pattern)
- `backend/routers/{cross_property,shift_handover,webhook_admin,eod_report,booking_holds}.py`
- `backend/core/booking_hold_service.py` (lock service contract)
- `backend/domains/admin/router/stress.py` (`STRESS_COLLECTIONS`)
