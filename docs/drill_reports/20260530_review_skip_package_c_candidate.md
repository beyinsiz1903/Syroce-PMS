# Package C — Candidate Drill Report (2026-05-30)

> Product Contract / Compliance REVIEW/SKIP Reduction over Run #168 (official
> GREEN BASELINE). Inventory: `20260530_review_skip_package_c_inventory.md`.
> Doktrin korundu: no fake-green, no broad RBAC grant, no auth weakening, no
> pilot mutation, external_calls=[]. Baseline pointer TAŞINMAZ; full stress
> KOŞTURULMADI (operatör dispatch); CI-deferred targeted regression.

## DONE (tek kod = e-Fatura compliance parite)

**Target 1 — `customer_tax_number` VKN/TCKN validator (create + update parite)**
- `backend/routers/finance/accounting.py`: ortak modül-yardımcı
  `_normalize_customer_tax_number` (strip → boş=None → digit+len∈{10,11} değilse
  `ValueError`→422). `AccountingInvoiceCreateRequest` `field_validator`'ı bunu
  çağırır; ham-dict alan `update_accounting_invoice` da çağırıp `ValueError`'ı
  422'ye sarar (post-create malformed yazım kapatıldı). `InvoiceCreate.customer_tax_id`
  sözleşmesinin paritesi, tek doğruluk kaynağı.
- **Additive + geriye-uyumlu:** None/boş kabul; yalnız malformed değer reddedilir.
- **Kapsam sınırı:** from-folio yolu (`GenerateInvoiceFromFolioRequest`)
  `customer_tax_number` KABUL/SET ETMEZ → validator gereksiz; türetilmiş/legacy
  veri retroaktif 422'lenmesin diye bilinçli dokunulmadı.
- **Test:** `backend/tests/test_invoice_tax_id_contract.py` +13 case → **26/26 PASS**.

## CONFIRM-BY-DESIGN (kod yok, doküman netleştirme)
- **Target 5 KVKK:** anonymize-only + audit (`db.gdpr_requests`) + fail-closed
  (`ENABLE_GUEST_ANONYMIZATION`); hard-delete kasıtlı yok (finansal bütünlük).
- **Target 6 NPS:** Wave 9 409 dedup; `test_nps_duplicate_guard.py` **3/3 PASS**.
- **Target 8 Admin RBAC:** super_admin guard fail-closed 404 (Wave 8); stres admin
  tenant-scoped → 404 doğru; 2xx yapmak auth-weakening (YASAK).
- **Target 4 (agency):** agency contract state machine zaten tam.

## OPERATOR-ENV (backend kod fail-closed doğru)
- **Target 7 GraphQL introspection:** `_introspection_enabled()` env'e göre
  prod/stress/staging'de kapalı. Stres backend deployment env'i "stress" set
  etmiyor → dev default açık. Operatör: `SENTRY_ENVIRONMENT=stress` (veya
  `GRAPHQL_INTROSPECTION=false`). Yeni env değişkeni eklenmedi.

## SCOPED-FOLLOW-UP (büyük/breaking — zorlanmadı)
- **Target 2:** Revenue global dry_run kill-switch (çok-endpoint; tenant
  shadow_mode/write_enabled zaten fail-safe).
- **Target 3:** B2B per-subrouter scope provisioning (key scope alanı + 13 router +
  migration).
- **Target 4:** CRM corporate-contract formal approval state machine.
- **Target 1b:** e-Fatura `customer_type` zorunlu (geriye-uyum + migration).

## Doğrulama
- `node --check` gerekli değil (kod backend Python). AST parse PASS.
- pytest targeted: `test_invoice_tax_id_contract.py` 18/18, `test_nps_duplicate_guard.py` 3/3.
- external_calls=[], pilot mutation=0, RBAC grant yok, auth weakening yok.
- Full stress suite operatör dispatch'ine bırakıldı (#168 official kalır).
