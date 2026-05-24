# F8Z v2 — POS Deep Lifecycle Stress (spec written 2026-05-24)

**Type:** spec-written drill (backend kodu değişmedi)
**Spec:** `frontend/e2e-stress/specs/98-pos-deep-lifecycle.spec.js`
**Module:** `pos_deep_lifecycle`
**Sibling specs:** `98-spa-wellness-operational.spec.js` (F8AB) ·
`98-golf-operational.spec.js` (F8AC) · `98-payment-pos-reconciliation-dryrun.spec.js` (F8Z v1, untouched)
**Roadmap reference:** `docs/STRESS_TEST_ROADMAP.md` § "F8Z v2 — POS Deep Lifecycle Stress"

## Hedef

POS v2 (`backend/domains/pms/pos_fnb_router_v2.py` +
`backend/domains/pms/pos_fnb/pos_fnb_service_v2.py`) lifecycle yüzeyini stress
suite'in defans baseline'ı altında doğrulamak: create → close → void replay,
split-check toplamı, table-transfer negative contract, validate-room-charge
PII/cross-tenant guard, idempotency-key replay, terminal-state guard, P0
cross-tenant IDOR, folio-safety (`post_to_folio=false` zorunlu) — tüm bunlar
F8AB spa + F8AC golf pattern'inin birebir POS kardeşi.

## Kapsam (test başlıkları)

| Test | Doğrulanan |
|---|---|
| Setup | `GET /api/pos/orders` module probe (403/404 → A–I skip + P2). Table-layout informational probe. pilot_baseline snapshot. |
| A | Catalog read smoke (`/api/pos/orders`, `/api/pos/transactions`). Non-2xx → P2. |
| B | Happy lifecycle: create (`OrderItemSchema`: `item_id/name/quantity/price/station`) → close (`post_to_folio=false`, `booking_id=null`, drops `payment_amount`). 200 zorunlu. `transaction_id` close response'undan yakalanır (D ve H'da kullanılır). |
| C | Atomic conflict guard — aynı payload + aynı `idempotency_key` ile 2 create → ya same id (service-level idempotency) ya 4xx; distinct 2xx = P1. |
| D | Split-check equal/by_item/custom — `POST /api/pos/check-split` (QUERY: `transaction_id/split_type/split_count`, BODY: `split_details`). Real `transaction_id` B'den seeded close + dedicated D close ile. `Σ amounts ≤ original_amount + 0.05` invariant; ihlal P1. 403/404 → P2 informational. |
| E | Table-transfer (QUERY: `from_table/to_table/outlet_id/transfer_all`): **E1 happy-path attempt** — `/pos/transaction` seed (status='completed') + transfer → ≥400 zorunlu çünkü filter `status='open'` arar; bu yapısal gap P2 informational ("no production write surface creates pos_transactions.status='open'"). E2 negative — bogus from_table → 4xx zorunlu. |
| F | Close idempotency replay — aynı `idempotency_key` ile 2 close → c1=200, c2 ya 200+`idempotent:true` ya 4xx terminal; aksi P1. |
| G | Terminal-state guard — create → void (v1=200) → re-void (200+`idempotent:true` ya 4xx, aksi P1); close-after-void → 4xx zorunlu, aksi P1. |
| H | **P0 cross-tenant IDOR** (hard-fail 4xx zorunlu): pilot bearer stress order üzerinde (H1) close → 4xx, (H2) void → 4xx, (H3) transfer-table stress outlet+table → 4xx, (H4) check-split stress `transaction_id` → 4xx. Her dördü `expect(...).toBeGreaterThanOrEqual(400)` ile hard-fail; 2xx = P0 finding + assertion failure. |
| I | validate-room-charge (QUERY: `booking_id/amount/category`) — bogus booking_id (stress + pilot aynı çağrı): stress yanıtında PII regex (`identity_number|passport_no|iban`) bulunursa P1; pilot yanıtında stress prefix bulunursa P0. |
| Z | Cleanup — created order'ları void et; ikinci pass 200+`idempotent:true` ya 4xx terminal-state; aksi P1. `pos_orders/pos_transactions/table_layouts/kitchen_orders/pos_outlets/pos_menu_items/happy_hour_rules/pos_room_charge_restrictions` orphan-scrub `STRESS_COLLECTIONS` unified sweep ile. |

Her test `try/finally` ile `assertNoExternalCallsPostBatch` +
`assertPilotDriftZero` çağırır (mutlak baseline).

## Folio safety (kritik invariant)

`close_order(post_to_folio=False, booking_id=null)` lifecycle'da:

- `folio_charges` koleksiyonuna insert YOK.
- `bus.publish("POSTING_CHARGE")` event'i tetiklenmiyor.
- Xchange dispatch yok → `external_calls=[]` post-batch invariant bu güvenceyi
  kapsar.

Spec her create+close lifecycle'ı `post_to_folio=false` ile çalıştırır
(B, F, H test'leri). C/D/G/I akışlarında close/void zaten folio'ya bağlı
değil. G test'inin "close-after-void" probu sadece terminal-state guard'ı
doğrular (state-machine), bağımsız bir folio-post path'i değildir.

## API contract reference (kanonik — code review tur-1 sonrası fix'lendi)

Spec yorumlarında embedded; özet:

- **CreateOrderRequest**: `outlet_id, table_number, items[], guest_name, booking_id, order_type, idempotency_key`. `OrderItemSchema` zorunlu alanları: `item_id, name, quantity, price, station, special_instructions`. Spec `unit_price/total/menu_item_id/subtotal/notes` göndermiyor (router reddeder 422).
- **CloseOrderRequest**: `order_id, payment_method, post_to_folio, booking_id, tip_amount, idempotency_key`. `payment_amount` schema'da YOK — spec göndermiyor.
- **POST /api/pos/check-split**: QUERY `transaction_id, split_type, split_count`; BODY `split_details` (dict). Spec her scenario için query-string + body kullanır.
- **POST /api/pos/transfer-table**: QUERY `from_table, to_table, outlet_id, transfer_all`. Body boş.
- **POST /api/pos/validate-room-charge**: QUERY `booking_id, amount, category`. `category` zorunlu — spec `'food'` gönderir.

## Transfer-table happy-path gap (compensating assertion rationale)

`transfer_table` filtresi: `pos_transactions` koleksiyonunda `status='open'` arar. Production write yüzeylerinde:

- `/pos/transaction` (legacy line 536) → `status='completed'` yazar.
- v2 `close_order` (pos_fnb_service_v2.py L210) → `status='completed'` yazar.
- v92 `/pos/create-order` → `pos_orders` yazar, `pos_transactions`'a hiç dokunmaz.

Sonuç: **hiçbir production endpoint** `pos_transactions.status='open'` row üretmez. Transfer-table v2 lifecycle için yapısal olarak dead-code. Spec E1 bu gap'i deterministik PROVES (seed via `/pos/transaction` → transfer → 404 expected çünkü status='completed' ≠ 'open'); P2 informational + compensating: E2 negative contract (bogus → 4xx) ve H3 cross-tenant guard (pilot bearer → 4xx) ile transfer-table'ın tenant-isolation + 404 contract'ı tam test edilir. Backend hardening önerisi: ya transfer-table'ı v2 lifecycle'a bağla ya endpoint'i deprecate/remove et — bu spec scope'u dışı (yeni task gerekirse).

## Module-blocked doctrine

`GET /api/pos/orders?limit=5` ilk probe 403/404 dönerse:

- `moduleBlocked = true` → A/B/C/D/E/F/G/H/I `test.skip(true, ...)` ile atlar.
- Z (cleanup) atlanmaz; createdOrderIds boş olacağı için no-op ama final
  invariants (external_calls + pilot_drift) yine doğrulanır.
- P2 informational finding emit edilir (gerçek bug değil; environment gate).

## STRESS_COLLECTIONS additions

`backend/domains/admin/router/stress.py` (L196-211, golf block'unun hemen
ardından, sentinel `bookings/guests/rooms` öncesi):

```python
# F8Z v2 (2026-05-24): POS Deep Lifecycle stress.
"pos_orders",
"pos_transactions",
"table_layouts",
"kitchen_orders",
"pos_outlets",
"pos_menu_items",
"happy_hour_rules",
"pos_room_charge_restrictions",
```

Tüm row'lar `stress_seed=True` + `stress_prefix` tagged konvansiyonuyla
unified cleanup loop'a düşer. Spec-side primary cleanup yolu void'dir;
bu liste yalnız orphan-scrub safety net (run mid-flight abort edilirse).

## Doctrine notları (sibling pattern'lerden devralınan)

- **F8AB spa**: catalog-blocked module-skip, P0 cross-tenant IDOR, atomic
  conflict idempotency-key replay.
- **F8AC golf**: cross-tenant status mutation + delete + folio-post 4xx
  baseline, idempotency replay (same id OR 409), money-safety folio-guard.
- **F8Z v1** (`98-payment-pos-reconciliation-dryrun.spec.js`): read-only +
  validation + cross-tenant IDOR doctrine (dokunulmadı; v2 sister spec).

## Beklenen invariant

| Metric | Hedef |
|---|---|
| failedTests | 0 |
| P0 / P1 | 0 / 0 |
| external_calls (her batch) | `[]` |
| pilot_drift (her test) | 0 |
| Cleanup idempotent | ✅ ikinci pass = idempotent flag ya 4xx terminal |
| Module-blocked fallback | A–I skip + P2 informational; Z + final invariants enforce |

## Önceki/sonraki

- **Önceki tur:** F8AC golf operational stress (spec 98-golf-operational,
  baseline 72) — `docs/drill_reports/20260524_stress_f8ac_golf_operational.md`
  (eq. roadmap section).
- **Bu tur:** F8Z v2 POS deep lifecycle — yeni spec, baseline 72 → **73**.
- **Sonraki:** Full Operational Stress Suite tek run verification (F8AB +
  F8AC + F8Z v2 ilk kez birlikte koşacak); F8AD/F8AE/F8AF/F8AG/F8AH
  roadmap'in devamı.

## Backend impact

**Sıfır.** Yalnız `backend/domains/admin/router/stress.py` `STRESS_COLLECTIONS`
listesine 8 koleksiyon ismi eklendi (orphan-scrub safety net). POS v2 router
ya da service kodu değişmedi; v1 spec dokunulmadı.
