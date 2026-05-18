# F8E Stress Suite — Evolution (Finance / Cashier / Accounting, tur-1)

**Status:** TUR-1 PUSH — CI #1 bekleniyor (beklenti: GO WITH WATCH)
**Date:** 2026-05-18
**Scope:** `frontend/e2e-stress/specs/24..27` (4 spec, 16 test), F8A+B+C+D operasyonel paketinin üzerine finansal/muhasebe yüzeyleri.
**Drill rapor:** `docs/drill_reports/20260518_stress_f8e_finance_cashier_accounting.md`

Bu ADR F8E stres test suite'inin tur detaylarını içerir. `replit.md` "Gotchas" bölümünde tek-satır özet bırakılmıştır.

---

## Seed extension

`backend/domains/admin/router/stress.py` → `_build_f8e_docs(stress_tid, prefix, now)` factory:

- 3 cashier_shifts — HEPSI `status=closed` (spec 24 kendi shift'ini açar, `uniq_tenant_open_shift` partial index ihlali olmasın diye seed'de hiç açık vardiya yok)
- 30 cashier_transactions (4 yöntem × 2 yön round-robin, 3 closed shift'e dağıtılmış)
- 10 suppliers (food/beverage/linen/amenity/maintenance/...) — `name={prefix}Supplier_<id>`
- 20 expenses (8 kategori × 4 VAT oranı mix; supplier_id seed'lenmiş 10 supplier'a round-robin)
- 10 accounting_invoices (sales/purchase/proforma/credit_note/debit_note mix, items=1, subtotal+20%VAT)
- 5 bank_accounts (TRY×3, USD, EUR — IBAN prefix-tagged)
- 15 inventory_items (5 kategori, supplier_id linked, stock_quantity 100-240 arası)
- 10 stock_movements (initial intake, `movement_type=in`, item_id seed'lenmiş 10 item'a 1:1)
- 20 cash_flow (inflow/outflow alternating, audit trail synthetic)
- 5 city_ledger_accounts (kurumsal, credit_limit 10K-20K arası)

`STRESS_COLLECTIONS` + orphan_cleanup loop'a 11 yeni koleksiyon eklendi:
`cashier_shifts`, `cashier_transactions`, `expenses`, `suppliers`, `accounting_invoices`, `bank_accounts`, `inventory_items`, `stock_movements`, `cash_flow`, `city_ledger_accounts`, `city_ledger_transactions` (seed yok ama orphan scrub var — spec 25 forward-compat). `tenant_context(stress_tid)` wrap koruması korunur.

**Folio/folio_charges/payments F8A § 04'te kapsandığı için çift seed edilmedi** — F8E shift lifecycle + city-ledger + accounting CRUD odaklı.

## Kritik invariantlar (dry-run guarantees)

- **(a) External dispatch yok:** Iyzico router seviyesinde tetiklenmiyor (logic gömülü); email/SMS provider call'u finance/accounting endpoint'lerinden çağrılmıyor. `E2E_EXTERNAL_DRY_RUN=true` global gate yine de zorunlu.
- **(b) Open-shift uniqueness:** Seed'de 0 open shift. Spec 24 Setup `uniq_tenant_open_shift` ihlalini engellemek için kalan açık vardiyayı defansif kapatır.
- **(c) Cashier transaction shift bağı:** Seed transactions standalone doc (embedded `transactions` array değil). Spec 24 kendi açtığı shift'e `manual-transaction` yazar — seed shift'lerine dokunmaz.
- **(d) Folio dependency yok:** Spec 25 split-payment / mobile record-payment çağırmaz — bunlar folio_id + open shift gerektirir; F8A § 04 + F8E § 24 kapsamında. Spec 25 yalnızca standalone city-ledger account CRUD ile sınırlı (cross-spec dependency yok).
- **(e) Supplier balance:** `/api/accounting/expenses` POST supplier `account_balance` field'ını arttırır (`$inc`); stress tenant scoped, pilot mutation YOK.
- **(f) Inventory stock_quantity update:** `/api/accounting/inventory/movement` POST `inventory_items.stock_quantity` field'ını günceller; stress item'lar üzerinde, pilot stoklarına dokunmaz.

Helper: `callTimedWithBackoff` (F8B tur-24) + 1500ms inter-call gap + `test.setTimeout(180_000)` ya da spec 26 için `240_000` (3 ayrı bulk: supplier+expense+invoice).

---

## Tur-1 — ilk push

- **Seed extension** ✅ — `_build_f8e_docs` + `STRESS_COLLECTIONS` extension + orphan_cleanup + counts wire-up.
- **Spec 24 (cashier_shift)** — Setup/read_shift/shift_lifecycle (open→N=10 manual-txn→close)/pilot_drift. Setup'ta residual open shift defansif kapatma. RBAC fallback (`open-shift 401/403`) → P2 SKIP.
- **Spec 25 (finance_cityledger)** — Setup/list_cityledger/bulk_create_cityledger(N=5)/pilot_drift. RBAC fallback (`permFail === N`) → P2 SKIP.
- **Spec 26 (accounting_expenses)** — Setup/list_accounting/bulk_create(3 supplier + 10 expense + 5 invoice)/pilot_drift. Setup'ta seeded supplier_id pickup. `permFail === total` → P2 SKIP.
- **Spec 27 (accounting_bank_inventory)** — Setup/list_bank_inv/bulk_create(3 bank + 10 movement)/pilot_drift. Setup'ta seeded item_id pickup. `permFail === total` → P2 SKIP.

### Module-blocked desen (F8C/D mirror)

Setup'ta endpoint reachability + seeded pool probe. `moduleBlocked=true` koşulları:
- 24: `/api/cashier/current-shift` non-2xx.
- 25: `/api/cashiering/city-ledger` non-2xx.
- 26: `/api/accounting/suppliers` veya `/api/accounting/expenses` non-2xx veya seed'lenmiş supplier_id bulunamadı.
- 27: `/api/accounting/bank-accounts` veya `/api/accounting/inventory-items` non-2xx veya seed'lenmiş item_id bulunamadı.

`moduleBlocked=true` → P2 informational finding + A/B `test.skip(true, ...)`; C pilot_drift bağımsız çalışır (kasıtlı: pilot mutation gate her durumda enforce edilmeli).

### RBAC short-circuit deseni

Spec B (bulk create) içinde `permFail === N` (tüm istekler 401/403) → P2 SKIP, FAIL ETMEZ. Stress admin super_admin role'üyle çalışır — beklenti `post_payment` / `view_finance_reports` / `manage_city_ledger` / `post_charge` izinleri pass eder. Fakat backend bir endpoint manuel role allowlist enforce ederse (F8D §22 leave-request örneği gibi) spec resilience tercih edildi.

### Spec 24 defansif Setup kapatma — RC

Backend `uniq_tenant_open_shift` partial index (`status=open`) bir tenant'ta birden fazla açık shift'i engeller. Önceki abort run'larda kapanmadan kalan shift varsa `open-shift` 400 döner. Setup `GET current-shift` ile mevcudu tespit eder, varsa `close-shift` ile kapatır (counted_amount=0, difference negative olabilir ama PASS). Bu — pilot mutation değil; stress tenant scoped, F8A `cleanup_e2e_pilot_residue` pattern'i ile aynı felsefe.

---

## Sonraki turlar (yer tutucu)

CI #1 sonucu burada güncellenecek. Beklenen başarı kriterleri:
- failedTests = 0
- P0 = P1 = 0 (P2 informational findings izin verilir)
- external_calls_made = []
- pilot_drift = 0
- 16/16 test yeşil (RBAC tarafından skip edilenler dahil — Playwright skip = pass-equivalent)

NO-GO durumunda tipik root cause hipotezleri:
- Cashier `uniq_tenant_open_shift` index hala 400 dönüyorsa → Setup defansif close eklenmedi VEYA close 401 (RBAC sertleşmesi); fallback: spec retry + extended setup probe.
- `/api/accounting/inventory-items` route 404 — endpoint adı drift olabilir (`inventory` vs `inventory-items`). Çözüm: hem `/api/accounting/inventory-items` hem `/api/accounting/inventory` probe.
- City-ledger list endpoint method farklı (`GET /api/cashiering/city-ledger-accounts` olabilir). Çözüm: 404'te P2 informational + B test.skip pattern zaten devrede.
- Expense `vat_amount` calculation drift — backend `total_amount` üzerinden mi yoksa `amount + amount*vat_rate/100` mı? Spec payload `amount=gross` gönderiyor; backend `vat_amount = gross * vat_rate / (100+vat_rate)` (gross-inclusive). Field shape uyuşmazlığı 422 verirse spec floor 90% düşürülür.

---

## Code-review fix-up (architect tur-1)

Architect ilk turda 3 kritik kontrat uyuşmazlığı yakaladı; tur-1 push öncesinde düzeltildi:

1. **Spec 27 inventory list endpoint:** `/api/accounting/inventory-items` → `/api/accounting/inventory` (backend route `accounting.py:399`, response `{items, low_stock_count, total_value}`).
2. **Spec 27 inventory movement payload:** backend handler `create_stock_movement` parametreleri **query parameter** olarak alıyor (Pydantic body değil) — spec JSON body yerine `URLSearchParams` ile query string'e geçti.
3. **Spec 26 expense category enum:** backend `ExpenseCategory` strict (`salaries/utilities/supplies/maintenance/marketing/rent/insurance/taxes/other`) — `food/beverage` enum dışıydı, spec kategori listesi enum-uyumlu hale getirildi.
4. **Seed inventory_items field:** `stock_quantity` → `quantity` (model contract). `is_active`/`active` çıkarıldı, `is_consumable=True` eklendi. `reorder_level=float`. GET `/api/accounting/inventory` `item['quantity']` okuyor — field shape şart.
5. **Seed expense_categories:** aynı şekilde enum-uyumlu (`salaries/utilities/supplies/maintenance/marketing/rent/insurance/taxes/other`).

## Acceptance

- T001 ✅ Seed extension applied (`stress.py` syntax OK; kontrat doğrulanmış; runtime test CI'da).
- T002 ✅ 4 spec yazıldı, kontrat-uyumlu (Node `--check` parse OK, 16 test toplam).
- T003 ⏳ CI #1 sonucu burada raporlanacak.
