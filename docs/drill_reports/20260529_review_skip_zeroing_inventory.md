# REVIEW / SKIP Zeroing Program — Phase A Inventory

> **Baseline (FIXED — do not move):** Run **#162**, commit
> `bde7662744c9b94a5c9294fa778202d813319dfc`, web/backend Full Stress Suite.
> 702 test · `failedTests=0` · PASS/FAIL/REVIEW/SKIP = **1316 / 0 / 46 / 61** ·
> P0/P1/P2/P3 = **0 / 0 / 60 / 1** · `external_calls=[]` · `pilot_drift=0` ·
> cleanup idempotent · verdict **GO WITH WATCH**.
>
> **Doctrine (değişmez):** REVIEW/SKIP **PASS'e downgrade edilmez**, fake-green
> yok, güvenlik gevşetme yok, gerçek prod secret yok, Run #162 pointer'ı
> taşınmaz, "GO" iddia edilmez, "/100" iddia edilmez, bu programda full stress
> koşulmaz (Wave 6–9 sonrası).
>
> **Kapsam notu:** Bu envanter, web/backend stress suite'inin 46 REVIEW + 61
> SKIP kalemini sınıflandırır. Sayım ve modül dağılımı için ground-truth
> kaynak: `docs/STRESS_P2_REVIEW_TRIAGE_20260526.md` §5–§8 (Run #143 modül
> tablosu; #162'de REVIEW 48→46, SKIP 73→61, P2 65→60 — kategori dağılımı
> değişmez, sadece sayılar daha düşük). Adım-seviye kanıt: `frontend/e2e-stress`
> spec annotation'ları + `fixtures/stress-helpers.js` `withModuleProbe`.

---

## 1) Sınıflandırma şeması (10 kategori)

| # | Kategori | Tanım | Tipik aksiyon |
|---|---|---|---|
| 1 | **ENV_SECRET_MISSING** | Stres backend/CI'da env veya test-secret unset → fail-closed 503/404 | Test-only env/secret provision (prod gerçek secret) |
| 2 | **SEED_MISSING** | Stres tenant'ta gerekli kayıt yok (agency, recipe, folio, payment, role-user) | Seed factory'e idempotent + cleanup-safe ekleme |
| 3 | **ENDPOINT_NOT_DEPLOYED** | API yolu stres env'de 404 / mount değil | Route mount veya observability endpoint |
| 4 | **FEATURE_FLAG_OFF** | Bilinçli kapalı feature (guard ile) | Flag + test ile kontratı netleştir |
| 5 | **PRODUCT_CONTRACT_DECISION** | Teknik eksik değil, ürün kararı (lifecycle, unique, duplicate guard) | Karar → schema/test'e bağla |
| 6 | **TEST_EXPECTATION_DRIFT** | HTTP 2xx ama body/contract beklenenden farklı | Spec adapter veya backend contract düzelt |
| 7 | **PERFORMANCE_WATCH** | p95 bütçesi aşıldı ama hard-timeout içinde | Deterministik dry-run / fast-path |
| 8 | **INTENTIONAL_SECURITY_FAIL_CLOSED** | RBAC by-design 403 / fail-closed 503 — kasıtlı güvenlik | Doctrine: out-of-scope kabul VEYA alt-role spec |
| 9 | **ROADMAP_BACKLOG** | Ürün kapsamında ama henüz implemente değil | Backend feature work (bu programın dışında) |
| 10 | **TRUE_BUG** | Gerçek defect | Hemen düzelt + regression test |

---

## 2) Master envanter (modül × kalem)

Sütunlar: **Sev** (P2=module-blocked SKIP bulgusu / REVIEW=adım-seviye) ·
**Kat** (yukarıdaki 1–10) · **Kök sebep** · **Prod kod?** (prod davranış
değişikliği gerekli mi) · **Seed?** · **Env/Secret?** · **Targeted cmd**
(spec) · **Risk** · **Wave**.

### Wave 6 — ENV / SECRET / TEST-POSTURE (kategori 1, 7)

| Modül | Kalem | Sev | Kat | Kök sebep | Prod kod? | Seed? | Env/Secret? | Targeted spec | Risk | Wave |
|---|---|:--:|:--:|---|:--:|:--:|:--:|---|:--:|:--:|
| `cm_exely_webhook` | valid-payload + cancellation idempotency coverage gap | REVIEW×3 | 1 | `EXELY_IP_WHITELIST` stres backend'de unset → 503 fail-closed (kod doğru) | Hayır | Hayır | Evet (stres whitelist posture) | `50-cm-webhooks-exely` | Düşük | 6 |
| `cm_hotelrunner_webhook` | signed-path coverage gap | REVIEW×1 | 1 | `HOTELRUNNER_WEBHOOK_SECRET` unset → 503 (kod doğru) | Hayır | Hayır | Evet (test-only HMAC) | `cm_hotelrunner_webhook` | Düşük | 6 |
| `cm_outbox` | active idempotency coverage gap | REVIEW×1 | 1 | Signed webhook secret unset → outbox signed path sürülemiyor | Hayır | Hayır | Evet (yukarıdakine bağlı) | `52-cm-outbox-idempotency` | Düşük | 6 |
| `identity_reporting_dryrun` | KBS prefix guard not enforced | REVIEW×1 | 1 | `KBS_TEST_MODE` off → `TEST-` prefix guard exercise edilmiyor (kod doğru) | Hayır | Hayır | Evet (`KBS_TEST_MODE=1`) | `identity_reporting_dryrun` | Düşük | 6 |
| `graphql_isolation` | introspection 2xx | REVIEW×1 | 1 | Stres backend `SENTRY_ENVIRONMENT`/`GRAPHQL_INTROSPECTION` posture → introspection açık (kod default-off) | Hayır | Hayır | Evet (env posture + verify) | `graphql_isolation` | Düşük | 6 |
| `ai_pricing` | recommend-rates 10s timeout / network posture | P2×3 | 7→1 | Ağır path / ML engine yokluğu; competitor fetch zaten simüle | Olası (dry-run fast-path) | Hayır | Hayır | `ai_pricing` | Orta | 6 |

> **Wave 6 doğrulama gerçeği:** Webhook imza + KBS + introspection
> davranışını **stres backend** kendi env'inden okur (CI runner değil).
> Repo tarafı: spec'ler env varsa signed/valid path'i sürer, yoksa REVIEW
> kalır (fake-green YOK). Stres backend env provisioning operatör/devops
> işidir; targeted spec'lerin gerçek PASS'i CI'da (stres env set edildikten
> sonra) doğrulanır. Prod gerçek secret kullanır (test-secret DEĞİL).

### Wave 7 — SEED / DATA-STATE (kategori 2)

> **Wave 7 yürütme gerçeği (2026-05-30):** Seed kodu birebir okununca 14
> item'dan yalnız **2'si gerçek, güvenli, endpoint-bağımsız seed gap** çıktı
> (b2b agencies + pilot payroll IDOR fixture → **DONE**). Geri kalanı zaten
> seedli (duplicate-seed = false-green riski → eklenmedi) ya da gerçek blocker
> endpoint/env/RBAC. Yeniden sınıflandırıldı. Tam analiz:
> `docs/drill_reports/20260530_review_skip_wave7_candidate.md`.

| Modül | Kalem | Sev | Kök sebep (revize) | Durum / Gerçek Wave |
|---|---|:--:|---|---|
| `b2b_api` | agencies_list_len=0 | P2×10 | `agencies` koleksiyonu stres seedli değildi | **✅ DONE (W7)** `_build_agency_docs` |
| `export_artifact_idor` | hr_payroll_run pilot_list_empty | SKIP×1 | pilot `payroll_runs` IDOR anchor yoktu | **✅ DONE (W7)** `_ensure_payroll_run` |
| `folio-mass` | charges[] boş + payment yok | REVIEW×9 | ZATEN SEEDLİ (factory folio+charge+tax); okuma endpoint eksik | → **W8** (`/api/folios` alias) |
| `finance_reports_currency` | currency convert 0/2 | REVIEW×2 | ZATEN SEEDLİ (spec kendi rate'ini POST eder); convert endpoint | → **W8** (endpoint) |
| `housekeeping` | OOO transition guard inconclusive | REVIEW×2 / SKIP×1 | ZATEN SEEDLİ (rooms); OOO transition state-machine/endpoint | → **W8** (HK transition) |
| `reservation_deep` | waitlist promote / city ledger | (REVIEW/SKIP) | generic `/api/waitlist` yok (`spa_waitlist` var); boş seed 404'ü çözmez | → **W8** (endpoint) |
| `pos_kds_inventory` | inventory deplete + concurrent close | SKIP | `pos` modül entitlement yok → dataset module-probe SKIP | → **W8** (POS mount) |
| `spa_operations` | services/therapists/rooms | SKIP×1 | `spa` modül entitlement yok → katalog module-probe SKIP | → **W8** (SPA mount) |
| `payment_pos_reconciliation` | manual txn idempotency | SKIP | seed shift'ler **bilinçli closed** (`uniq_tenant_open_shift`; spec self-open). OPEN seed spec'i kırardı → eklenmedi. Blocker `pos_tables` endpoint | → **W8** (pos_tables); spec self-open |
| `vcc_pci_compliance` | VCC attach booking | SKIP×1 | ZATEN SEEDLİ (500 booking; spec kendi VCC); reveal `cashier_supervisor` rolü | → **W9** (RBAC alt-rol) |
| `full_24h` | full-day simulation review | REVIEW×7 / SKIP×1 | ZATEN SEEDLİ (500 booking/oda/guest); review env-gate `STRESS_FULL_SUITE` | → env-gate (operatör) |
| `ai_noshow_risk` | no stress bookings | SKIP×1 | ZATEN SEEDLİ (500 booking gelecek check_in); review env-gate `E2E_AI_DRY_RUN` | → env-gate (operatör) |
| `hr_rbac_pii` | team_create per-role 404 | P2×7 | 404 = endpoint cevabı (veri değil); auth-hassas `users` seed lokal doğrulanamaz | → **W8** (endpoint teyidi) |
| `cross_tenant_pentest` | sample assertion | SKIP×1 | ZATEN OK (`pilot_fixtures` room_blocks/kbs/sales-lead anchor üretiyor) | aksiyon yok |
| `public_token_rotation` | QR token rotation | SKIP | Stres room harvest + rooms/digital-key endpoint | → **W8** (endpoint) |

### Wave 8 — ENDPOINT / MODULE MOUNT — **CANLI PROBE İLE ÇÖZÜLDÜ (2026-05-30)**

> **Ground truth:** lokal backend → shared Atlas, `E2E_STRESS_ADMIN_*` login,
> **yalnız GET / mutasyon yok**. Headline: `ENDPOINT_NOT_DEPLOYED` büyük ölçüde
> MİSCLASSIFICATION — endpoint'ler mount'lu; 404 kök sebep = (8) super-admin
> guard fail-closed, (4) spec path-drift, (3) gerçek absent roadmap. Detay:
> `docs/drill_reports/20260529_review_skip_wave8_candidate.md`.

| Modül | Endpoint | Probe HTTP | Yeni Kat | KARAR | Wave |
|---|---|:--:|:--:|---|:--:|
| `admin_rbac` | `/api/admin/tenants` | **404** | **8** | By-design: platform-super-admin guard 404 (stres admin tenant-scoped). Mount VAR. Auth zayıflatma YOK. | 8 ✔ |
| `settings_audit` | `/api/admin/tenants` | **404** | **8** | Aynı (super_admin global). | 8 ✔ |
| admin feature-flags | `/api/admin/feature-flags` | **404** | **8** | Aynı (super_admin global). | 8 ✔ |
| `webhook_admin_dlq` | `/api/webhooks/status`+`/dlq` | **404** | **8** | Aynı (super_admin ops yüzeyi). | 8 ✔ |
| `messaging` | `/api/messaging-center/settings` | 200 | 4 | Spec path-drift (gerçek `messaging-center`). Endpoint çalışıyor. | 8 ✔ |
| `notification_batch` | messaging path+field drift | — | **4** | **DÜZELTİLDİ** — spec `/api/messaging-center/*` + `recipient` alanı; SKIP×3+P2×3 → güvenlik assert'leri gerçek-koşar. | 8 ✅ DONE |
| `ops_readiness` / `bulk-seed-500` | outbox depth | **404** | **8/4** | `/api/outbox/status` super_admin (out-of-scope); "manuel doğrula" REVIEW dürüst. | 8 ✔ |
| `payment_pos_reconciliation` | `/api/pos/tables`; `/api/pms/folios` | 404; drift | **3/4** | pos_tables list roadmap (yalnız `POST /api/pos/v2/tables/reserve`); folio gerçek `/api/finance/folio/list`. SKIP "no open shift" = Wave 7 by-design. | 8 ✔ |
| `public_token_rotation` | `/api/rooms`; QR rotate | 404; env | **3** | Rooms staff-only; QR rotation HTTP yok (env `ROOM_QR_SECRET`). REVIEW dürüst; tampered-token P0 assert public QR'da koşar. | 8 ✔ |
| `reservation_deep` | waitlist `/promote` | **404** | **3** | Generic promote roadmap (yalnız `/api/spa/waitlist`). Group rooming-list + city-ledger VAR. | 8 ✔ |
| `ws_tenant_isolation` | `/api/enterprise/ws/{stats,live}` | 200 | **4/env** | Mounted; WS 404 ise runner Upgrade/handshake env meselesi, mount değil. | 8 ✔ |
| `mice_execution` | F&B order-send | absent | **3/8** | F&B order-send roadmap; mice module entitlement 403 by-design. | 8 ✔ |

### Wave 9 — PRODUCT CONTRACT / BY-DESIGN / ROADMAP (kategori 5, 8, 9)

| Modül | Kalem | Sev | Kat | Kök sebep | Karar | Targeted spec | Wave |
|---|---|:--:|:--:|---|---|---|:--:|
| `crm_offers` | mice/accounts 403 + duplicate tax_no | SKIP×4 | 8/5 | RBAC by-design + ürün kararı | **DONE**: tax_no tenant-içi unique → **409** (create+update, whitespace-only None, tek insert path); test `test_company_tax_no_unique.py` | `crm_offers` | 9 |
| `public_nps` | NPS duplicate guard | REVIEW×1 | 5 | Ürün kararı | **DONE**: (survey,booking) UTC-gün başına tek → **409**, booking_id'siz muaf; test `test_nps_duplicate_guard.py` | `public_nps` | 9 |
| `identity_reporting` (e-Fatura) | VKN/TCKN schema | — | 5 | Ürün kararı | **DEFER (scoped follow-up)**: `customer_type`-zorunlu geriye-uyum bozar + migration; targeted-only doğrulanamaz (Wave 6/8 emsali). Karar kayıtlı. | `identity_reporting_dryrun` | 9 |
| `kvkk_retention` | hard-delete vs anonymize | SKIP×2 | 5/8 | Ürün/compliance kararı + RBAC | **CONFIRM by-design**: hard-delete YOK kasıtlı; anonymize + audit + fail-closed zaten var (`test_kvkk_anonymize_contract.py`) | `kvkk_retention` | 9 |
| `revenue_management` | auto-publish dry_run kill-switch | REVIEW×1 / SKIP×2 | 5/8 | Ürün kararı + RBAC | **DEFER (scoped follow-up)**: çok-endpoint mutation-suppression feature; targeted-only doğrulanamaz. Karar kayıtlı. | `revenue_management` | 9 |
| `mice_events` | spaces 403 (A/B/C/D) | REVIEW×1 / SKIP×4 | 8 | RBAC by-design (sales-catering rolü yok) | Alt-role spec `98-mice-as-sales-manager` VEYA out-of-scope kabul | `mice_events` | 9 |
| `mice_opportunities` | sales-catering 403 | SKIP×4 | 8 | RBAC by-design | Aynı | `mice_opportunities` | 9 |
| `accommodation_tax` | RBAC | SKIP×3 | 8 | tax_officer rolü yok | Alt-role spec VEYA out-of-scope kabul | `accommodation_tax` | 9 |
| `vcc_pci_compliance` | RBAC | SKIP×1 | 8 | cashier_supervisor rolü yok | Alt-role spec | `vcc_pci_compliance` | 9 |
| `public_kvkk` | RBAC step | REVIEW×1 / SKIP×1 | 8 | RBAC by-design | Alt-role spec | `public_kvkk` | 9 |
| `hr_shift` (swap consent) | caller ≠ target_staff | (REVIEW) | 8 | By-design (consent self-grant engeli) | target_staff token alt-test | `hr_shift` | 9 |
| `inventory_transfer_procurement` | warehouse-transfer + supplier credit_limit | P2×2 | 9 | Feature implemente değil (E9/E10) | Backend feature work — program dışı backlog | `70-inventory-stock` | 9 |
| `crm_offers` (contract approval) | contract approval lifecycle | — | 5 | Ürün kararı (açık) | **Karar gerekli** (user'a sorulacak) | `crm_offers` | 9 |

### TEST_EXPECTATION_DRIFT (kategori 6) — review-step kabulü

| Modül | Kalem | Sev | Not |
|---|---|:--:|---|
| `gates` | env contract REVIEW | REVIEW×2 | Env contract acceptance — Wave 6 posture ile netleşir |
| `pos_deep_lifecycle` | transfer happy_path 422 | REVIEW×1 | Gap documented — contract adapter veya backend düzelt (Wave 8 ile) |
| `reports_export` | dashboard_kpi review | REVIEW×1 | KPI shape acceptance |
| `reservation-lifecycle` | review step | REVIEW×1 | Lifecycle acceptance |
| `twofa_lifecycle` | lifecycle review step | REVIEW×1 | Acceptance (güvenlik PASS) |
| `revenue_management` | RMS review | REVIEW×1 | RMS acceptance |
| `hr_shift_coverage_planning` | coverage planning | REVIEW×2 | Coverage acceptance |

> **TRUE_BUG (kategori 10):** Bu envanterde **0** kalem TRUE_BUG. Hiçbir
> REVIEW/SKIP gerçek defect'e işaret etmiyor — tamamı env/seed/endpoint/
> contract/by-design. (P0=P1=0 invariantı ile tutarlı.)

---

## 3) Kategori rollup

| Kategori | Yaklaşık kalem | Birincil Wave | Prod kod riski |
|---|:--:|:--:|:--:|
| 1 ENV_SECRET_MISSING | ~7 (5 modül) | 6 | Yok (env posture) |
| 2 SEED_MISSING | ~40 | 7 | Yok (test seed) |
| 3 ENDPOINT_NOT_DEPLOYED | ~25 | 8 | Olası (mount) |
| 4 FEATURE_FLAG_OFF | ~3 | 8 | Yok |
| 5 PRODUCT_CONTRACT_DECISION | ~6 | 9 | Evet (schema/guard) |
| 6 TEST_EXPECTATION_DRIFT | ~9 | 6/8 | Düşük |
| 7 PERFORMANCE_WATCH | ~3 | 6 | Olası (dry-run) |
| 8 INTENTIONAL_SECURITY_FAIL_CLOSED | ~20 | 9 | Yok (by-design) |
| 9 ROADMAP_BACKLOG | ~5 | 9 | Program dışı |
| 10 TRUE_BUG | 0 | — | — |

> Sayılar §5 modül tablosundan türetilmiş **yaklaşıktır** (bir modülde
> birden çok kategori olabilir). Kesin per-finding CSV'si CI artifact
> `playwright-stress-report` reason= alanlarından üretilebilir (operatör
> indirir; anonim erişimle indirilemiyor).

---

## 4) Gerçekçi ara hedef (user direktifi)

| Metrik | #162 | İlk tur hedefi | Nihai hedef |
|---|:--:|:--:|:--:|
| REVIEW | 46 | < 25 | → 0 |
| SKIP | 61 | < 35 | → 0 |
| P2 | 60 | < 35 | → 0 |

Sıralama: Wave 6 (env/secret) → Wave 7 (seed) → Wave 8 (endpoint) → Wave 9
(ürün kararı/by-design). Her wave sonunda **targeted** spec'ler; full stress
suite en son.

---

## 5) Doctrine guard (her wave'de)

- REVIEW/SKIP → PASS downgrade **YASAK** (gerçek env/seed/route/role/karar ile kapanır).
- Skip-as-pass **YASAK** (by-design out-of-scope açıkça işaretlenmedikçe).
- `pilot_drift=0` · `external_calls=[]` · `failedTests=0` · `P0=P1=0` her run invariant.
- Gerçek prod secret **YOK** (test-only HMAC/whitelist; prod ayrı sağlar).
- Run #162 pointer **taşınmaz**; "GO"/"/100" iddia **edilmez**.
- Architect review her wave sonunda zorunlu.
