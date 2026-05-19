# F8E v2 Push — Finance Reports + Currency Extension (Drill Report)

**Date:** 2026-05-19
**Task:** #189 (F8E v2 Push + F8D Scope Open)
**Scope:** `frontend/e2e-stress/specs/28-finance-reports-currency.spec.js` (yeni, 4 test)
**Verdict beklentisi:** GO WITH WATCH (CI #42+ — push sonrası nightly stress)

## Hedef

F8E tur-1 (specs 24-27) operasyonel finance/cashier/accounting yüzeylerini kapsadı ama **analytics/reporting + currency module**'üne dokunmadı. Bu kapatma turu, kullanıcının açık tuttuğu finance gap'lerini kapatır.

## Coverage gap haritası (backend route tarama)

| Endpoint | Tur-1 status | v2 action |
|---|---|---|
| `GET /api/accounting/reports/vat-report` | NOT covered | ✅ spec 28 A |
| `GET /api/accounting/reports/profit-loss` | NOT covered | ✅ spec 28 A |
| `GET /api/accounting/reports/balance-sheet` | NOT covered | ✅ spec 28 A |
| `GET /api/accounting/dashboard` | NOT covered | ✅ spec 28 A |
| `GET /api/accounting/cash-flow` | seed only | ✅ spec 28 A (read probe) |
| `GET /api/accounting/currencies` | NOT covered | ✅ spec 28 A (no-perm reachability probe) |
| `POST /api/accounting/currency-rates` | NOT covered | ✅ spec 28 B |
| `GET /api/accounting/currency-rates` | NOT covered | ✅ spec 28 B |
| `POST /api/accounting/convert-currency` | NOT covered | ✅ spec 28 B |
| `GET /api/finance/invoices/stats` | NOT covered | DEFERRED (folio-bound) |
| `POST /api/accounting/invoices/from-folio` | NOT covered | DEFERRED (F8A § 04 territory) |
| `POST /api/accounting/invoices/multi-currency` | NOT covered | DEFERRED (F8E v3) |
| `POST /api/accounting/invoices/{id}/generate-efatura` | EXCLUDED | **YASAK** (GİB dispatch) |
| `POST /api/efatura/send/{id}` | EXCLUDED | **YASAK** (GİB dispatch) |
| `POST /api/efatura/send-to-gib/{id}` | EXCLUDED | **YASAK** (GİB dispatch) |
| `POST /api/efatura/generate/{id}` | EXCLUDED | **YASAK** (GİB dispatch) |

## Bilinçli dışarıda tutulanlar (rationale)

- **E-fatura paths**: Production'da gerçek GİB API'sine HTTP POST yapar (Türkiye e-Devlet entegrasyonu). `E2E_EXTERNAL_DRY_RUN=true` global gate'i e-fatura backend handler'ında **enforce edilmiyor** (legacy entegrasyon, F8 pre-flight'ın dışında). Spec hiçbir koşulda bu route'lara dokunmaz.
- **Folio-bound invoice paths** (`/invoices/from-folio`, `/invoices/multi-currency`): F8A § 04 (folio-mass) zaten folio CRUD yüzeyini test ediyor; çift kapsama olur. F8E v3'e ertelendi.
- **Invoice stats**: GET-only, basit aggregation, düşük öncelik. F8E v3 backlog.

## Spec 28 yapısı

- **Setup**: `/api/accounting/currencies` (no-perm) reachability probe → `moduleBlocked` flag. Pilot baseline `bookings` count.
- **A) Reports read** (6 GET): VAT + P&L + balance-sheet + dashboard + cash-flow + currencies. Hard floor = VAT + currencies + cash-flow (no-perm). P&L/BS/dashboard `view_finance_reports` gate → super_admin geçer; perm_gated_fails ayrı raporlanır (RBAC short-circuit informational).
- **B) Currency lifecycle**: 3 rate POST (her biri unique `(from, to, effective_date)`), list GET, 2 convert POST. Floor 90%, hard guard `okRate >= rateFloor`. RBAC-tolerant: permFail === total → SKIP (P2 informational).
- **C) Pilot drift = 0**: bookings count delta = 0 hard expect.

## Defansif invariants

- `assertNoExternalCallsPostBatch` her B testi sonunda çağrılır (currency module'ün gerçekten external olmadığını doğrular).
- 1500ms inter-call gap + `callTimedWithBackoff` (F8B tur-24).
- `test.setTimeout(180_000)` B testi için (3 rate + 1 list + 2 convert + gap = ~13s baseline, retry'la max 60s).
- Currency rates **tenant-scoped** cleanup: `STRESS_COLLECTIONS` += `currency_rates`. Spec runtime'da `stress_seed=True` flag eklemiyor (backend payload contract'i sınırlı) — orphan scrub `tenant_id` filter ile temizler.

## Roadmap F8D scope açma (Task #189 ikinci yarısı)

`docs/STRESS_TEST_ROADMAP.md` "F8D pre-flight" bölümü genişletildi. Kullanıcının 9 maddesi açıkça enümere edildi:
1. Personel (Staff) — bulk + lifecycle + PII guard
2. Departman — hierarchy + traversal + cascade
3. Vardiya (Shift) — schedule + swap + conflict + coverage
4. İzin (Leave) — request → decision + accrual + carry-over
5. Görev (Task) — assignment + status + escalation
6. Housekeeping-Personel ilişkisi — coverage + role binding
7. Yetki izolasyonu (RBAC) — cross-department reject
8. Audit — actor + before/after snapshot
9. Cleanup — 10 HR koleksiyonu prefix-scoped scrub idempotent

F8D v2 başlatma için backend route taraması notu da eklendi (`hr/*`, `operations/tasks*`, `audit_logs` triggers, `core/rbac.py` manager scope).

## Acceptance kriterleri (CI #42+ beklentisi)

- `failedTests = 0`
- `P0 = P1 = 0` (P2 informational permitted)
- `external_calls_made = []`
- `pilot_drift = 0`
- 20/20 test yeşil (4 yeni spec 28 + 16 mevcut spec 24-27; skip-by-RBAC pass-equivalent)
- `currency_rates` koleksiyonu prefix-tagged değil ama tenant-scoped → cleanup test count = N_RATE (delta=3)
- Re-run cleanup = no-op (idempotent)

## NO-GO hipotezleri (CI doğrulaması bekliyor)

- **Currency rate POST 422**: Payload `{from_currency, to_currency, rate, effective_date}` — `CreateCurrencyRateRequest` Pydantic model'i farklı field isimleri bekliyorsa. Backend `accounting.py:982-1002` doğrulandı, field shape match.
- **`view_finance_reports` cache stale**: P&L/balance-sheet `@cached(ttl=300/900)` — RBAC değişiklikleri sonrası cache invalidate edilmediyse super_admin yine 403 alabilir. RBAC-tolerant pattern fallback: perm_gated_fails raporlanır, hard floor yine VAT + currencies + cash-flow (hepsi no-perm).
- **Currencies endpoint 404**: Router mount kontrolü; muhtemel kök neden `accounting.py` import'unun bootstrap'a girmemesi — F8E tur-1 spec 26/27 zaten aynı router'ı kullanıyor, mevcut CI yeşilse 404 ihtimali yok.

## Sonraki adımlar

- CI #42 izlenecek (nightly stress one-shot).
- NO-GO durumunda hot-fix: ADR'a tur-7 entry, kök neden + düzeltme.
- GO WITH WATCH durumunda Task #189 close → follow-up: F8D v2 başlat (9 madde, ayrı task).
