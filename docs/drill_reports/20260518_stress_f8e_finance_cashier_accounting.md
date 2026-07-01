# F8E Stress Drill — Finance / Cashier / Accounting (tur-1)

**Date:** 2026-05-18
**Suite:** `frontend/e2e-stress/specs/24..27`
**Phase:** F8E — Finance / Cashier / Accounting
**ADR:** `docs/adr/2026-05-f8e-finance-stress-evolution.md`
**Status:** TUR-1 PUSH (seed + 4 spec, 16 test), CI #1 bekleniyor

## Kapsam

| Spec | Modül | Endpoint kümesi | Test sayısı |
|------|-------|-----------------|-------------|
| 24-cashier-shift | `cashier_shift` | `/api/cashier/{current-shift, period-report, open-shift, manual-transaction, close-shift}` | 4 (Setup + A read + B lifecycle + C drift) |
| 25-finance-cityledger | `finance_cityledger` | `/api/cashiering/city-ledger` (GET + POST) | 4 (Setup + A list + B bulk_create + C drift) |
| 26-accounting-expenses | `accounting_expenses` | `/api/accounting/{suppliers, expenses, invoices}` | 4 (Setup + A list + B bulk_create(sup+exp+inv) + C drift) |
| 27-accounting-bank-inventory | `accounting_bank_inventory` | `/api/accounting/{bank-accounts, inventory-items, inventory/movement}` | 4 (Setup + A list + B bulk_create(bank+mov) + C drift) |

**Toplam:** 4 spec, 16 test.

## Seed kapsamı (stress tenant scoped)

- 3 cashier_shifts (hepsi closed)
- 30 cashier_transactions
- 10 suppliers
- 20 expenses (8 kategori × 4 VAT oran mix)
- 10 accounting_invoices (5 type mix)
- 5 bank_accounts (TRY/USD/EUR multi-currency)
- 15 inventory_items + 10 stock_movements (initial intake)
- 20 cash_flow audit-trail entry
- 5 city_ledger_accounts

Tüm doküman `stress_seed=True` + `stress_prefix=<prefix>` etiketli, orphan scrub döngüsüne 11 yeni koleksiyon eklendi (`city_ledger_transactions` seed yok ama scrub var — spec 25 forward-compat).

## Dry-run garantiler

- **External dispatch:** Iyzico router seviyesinde tetiklenmiyor, finance/accounting endpoint'lerinden email/SMS provider call'u yok. `E2E_EXTERNAL_DRY_RUN=true` global gate aktif.
- **Open-shift uniqueness:** Seed'de 0 open shift. Spec 24 Setup defansif kapatma yapıyor.
- **Pilot mutation:** Tüm yazımlar `tenant_id=stress_tid` ile gates ile zorlanır; spec C testleri pilot drift = 0 enforce eder.
- **Folio dependency yok:** Spec 25 split-payment / mobile record-payment çağırmaz (folio_id + open shift gerektirir — F8A § 04 + F8E § 24'te kapsandı).

## Acceptance kriterleri

- failedTests = 0
- P0 = P1 = 0 (P2 informational allowed)
- external_calls_made = []
- pilot_drift = 0
- final verdict ≥ GO WITH WATCH

## Risk matrisi

| Risk | Olasılık | Etki | Mitigasyon |
|------|----------|------|------------|
| Open-shift partial index 400 (residue) | Düşük | Spec 24 SKIP | Setup defansif close + module-blocked fallback |
| `/api/accounting/inventory-items` route 404 | Orta | Spec 27 SKIP | module-blocked pattern → P2 informational |
| `manage_city_ledger` perm denied | Düşük (super_admin pass eder) | Spec 25 SKIP | RBAC short-circuit (`permFail === N` → SKIP) |
| Expense `vat_amount` field shape drift (422) | Orta | floor 9/10 başarısız | Spec payload backend kontratıyla doğrulandı; aksi halde floor 80% düşürülür |
| city_ledger_transactions cleanup miss | Düşük | Orphan birikir | STRESS_COLLECTIONS'a eklendi, full_wipe sıfırlar |

## Sonraki turlar

CI #1 sonucu ADR'a yansıtılacak. F8E DONE durumuna geçtikten sonra:
- **F8F (Inventory/Stock/Purchasing/Supplier):** F8E'nin stock_movements/suppliers altyapısı üstüne purchasing workflow + PO/GRN lifecycle.
- **F8G (Sales/CRM):** F8C MICE-sales üstünde devam, contract/proposal full lifecycle.
