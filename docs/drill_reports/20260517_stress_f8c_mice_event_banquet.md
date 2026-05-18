# F8C Drill — MICE / Event / Banquet / Group Operations (2026-05-17)

| Field                  | Value                                                         |
| ---------------------- | ------------------------------------------------------------- |
| Drill name             | F8C — MICE / Event / Banquet / Group Operations stress suite  |
| Specs                  | 14 (mice-events), 15 (sales-opportunities), 16 (sales-leads), 17 (banquet-competitor) |
| Total tests            | 19 (4+5+5+5)                                                  |
| Stress tenant          | dedicated isolated tenant (E2E_STRESS_TENANT_ID)              |
| Pilot tenant           | DO NOT TOUCH — `pilot_drift=0` gate her spec'in son testi     |
| External dispatch      | NONE — `E2E_EXTERNAL_DRY_RUN=true`, `external_calls=[]` gate  |
| Backed-by safety       | Events seeded with `reservation_id=None` → `_post_event_to_folio` + `bus.publish` short-circuit. Tests asla `completed` status'una geçmez. |
| Seed factory           | `_build_f8c_docs` — 8 spaces + 8 menus + 10 accounts + 10 contacts + 5 resources + 30 events + 30 opportunities + 20 leads + 10 competitors (5 rates each) + 3 packages |
| Cleanup                | `STRESS_COLLECTIONS` + orphan_cleanup loop'a 9 yeni mice koleksiyonu eklendi. `stress_seed=True` + `stress_prefix` etiketi ile idempotent. |
| Report file regex      | `| Final verdict |` literal — parser uyumlu                  |

## Scope

F8A (frontoffice/folio/HK, CI #55 PASS) + F8B (guest experience, CI #55 PASS)
üstüne dördüncü stress paketi. Hedef yüzeyler:

- **MICE Events** (`/api/mice/events`, payment-schedule, mark-paid).
- **Sales-catering Opportunities** (`/api/sales-catering/opportunities`,
  transitions, activities, pipeline aggregation).
- **Sales Leads** (`/api/sales/leads`, stage transitions, funnel aggregation,
  activity log).
- **Banquet Competitor** (`/api/banquet/competitors`, rates push,
  positioning aggregation).

## Dry-run safety guarantees

| Surface                  | External-call risk                  | Mitigation                                                              |
| ------------------------ | ----------------------------------- | ----------------------------------------------------------------------- |
| `mice/events/{id}/status`| `completed` → `_post_event_to_folio` + `bus.publish(POSTING_CHARGE)` | Test asla `completed`'a geçmez; max transition = `definite`. Seed events `reservation_id=None` → posting short-circuits even on `completed`. |
| `mice/events/{id}/payment-schedule/{i}/mark-paid` | `require_finance` rol check + DB-only positional `$set` | Stress admin rolü finance kapsamı dışındaysa 403 → P2 informational (FAIL değil). |
| `sales-catering/opportunities/{id}/transition`    | won/lost lifecycle event riski | Test sadece lead→qualified→proposal→contract. won/lost yok. |
| `sales/leads/{id}/stage`                          | DB-only + audit activity insert | Riski yok. |
| `banquet/competitors[/{id}/rates]`                | Pure DB CRUD | Riski yok. |

## Specs

### 14-mice-events.spec.js (5 test)
- A) Catalog read (spaces/menus/accounts/resources/events/diary)
- B) Bulk create 10 events status=lead, unique (space, date) tuple → conflict-free transitions
- C) Status transitions lead→tentative→definite (10×2=20 calls)
- D) Payment schedule replace (5 events × 3 items) + mark-paid (5 events × 1 item)
- E) Pilot drift = 0

### 15-sales-opportunities.spec.js (5 test)
- A) List + pipeline + packages read
- B) Bulk create 10 opportunities stage=lead
- C) Stage transitions qualified→proposal→contract (10×3=30 calls)
- D) Activity log (10 calls)
- E) Pilot drift = 0

### 16-sales-leads.spec.js (5 test)
- A) List + funnel aggregation read
- B) Bulk create 10 leads
- C) Stage transitions contacted→qualified→proposal_sent (10×3=30 calls)
- D) Activity log (10 calls)
- E) Pilot drift = 0

### 17-banquet-competitor.spec.js (4 test)
- A) List + positioning aggregation read
- B) Bulk create 5 competitors
- C) Rate snapshots push (5 competitors × 3 rates = 15 calls)
- D) Pilot drift = 0

## Rate-limit / timing budget

- Tüm spec serial mode, inter-call gap = 1500ms.
- `callTimedWithBackoff` (F8B tur-24 helper): 429 yakalar, 1 kez retry
  (`retry_after` veya 15s fallback).
- En geniş loop: 15-C ve 16-C, 30 call × ~2.0s = ~60s; `test.setTimeout(240_000)`
  4dk budget.
- 14-D iki ardışık batch (5+5=10 call) → `test.setTimeout(180_000)`.

## Acceptance gates

- `failedTests === 0`
- `external_calls === []` her batch sonrası (`assertNoExternalCallsPostBatch`)
- `pilot_drift === 0` her spec'in son testi
- P0 = 0, P1 = 0
- Final verdict ≥ `GO WITH WATCH`

## Known watch items

- 14-D mark-paid `require_finance` 403 → P2 informational (rol-bağımlı; stress
  admin finance rolüne sahip değilse beklendik, FAIL değil).
- F8A/F8B'den taşınan P2 observation: `active connectors lookup failed:
  TenantViolationError` query_errors — ground truth `calls=[]` PASS,
  NO-GO etmez, izleme önerisi.
- Workflow timeout: `.github/workflows/stress.yml` `timeout-minutes: 30`
  (F8B'de tur-26'da yükseltildi). F8C ~+15dk ekler → toplam ≈ 30-40dk;
  geri planda izlenir, gerekirse 45'e çıkarılır.

## Outcomes

| Run    | Spec status                                                        | Verdict                                              | Notes                              |
| ------ | ------------------------------------------------------------------ | ---------------------------------------------------- | ---------------------------------- |
| tur-1  | 14/15/16/17 first push                                             | (pending CI dispatch — bu rapor build-time itibarıyla yazıldı) | İlk drill turu. |

| Final verdict | PENDING | first-push baseline — CI dispatch sonrası güncellenir |
