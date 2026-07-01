# REVIEW/SKIP Reduction — Package A+B Candidate (Post-Run #167)

**Baseline:** Run #167 (official), commit `0b99607fe3a64a7ada660d1f1bcb8607bd47f5dd`,
702 test, PASS/FAIL/REVIEW/SKIP=1379/0/48/44, P0/P1/P2/P3=0/0/58/1, GO WITH WATCH.
**Envanter:** `docs/drill_reports/20260530_review_skip_reduction_package_ab_inventory.md`.

**Durum:** ADAY (CANDIDATE). Full suite KOŞTURULMADI (operatör dispatch eder).
Baseline pointer #167 TAŞINMAZ. Doğrulama CI-DEFERRED (stress backend + secret'lar
sandbox'ta yok). Backend kod pytest + spec `node --check` ile yerelde doğrulandı.

---

## Bu turda YAPILAN (kod)

### A1 — Exely test webhook auth mode (backend kod) ✅
`backend/domains/channel_manager/providers/exely/exely_webhook_router.py`

- Yeni `_exely_test_auth_open()` çok-koşullu **fail-closed** gate. IP-allowlist
  bypass'ı YALNIZ şu beş koşul AYNI ANDA sağlanırsa açılır:
  1. `EXELY_TEST_WEBHOOK_AUTH_MODE == "open_for_testing"`
  2. environment prod DEĞİL (`ENVIRONMENT`/`APP_ENV` ∉ {production,prod,live})
  3. `E2E_EXTERNAL_DRY_RUN == "true"`
  4. `E2E_ALLOW_DESTRUCTIVE_STRESS == "true"`
  5. `E2E_STRESS_TENANT_ID` non-empty
- Operatörün yasakladığı tek-bayrak `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK`'tan
  AYRI ve ondan bağımsız. Prod default: hiçbir koşul sağlanamaz → fail-closed 503.
- Tenant hâlâ server-side `HotelCode → exely_connections` ile çözülür; body'deki
  tenant ipuçları güvenilmez. **EK (architect Round-1 bulgusu):** bypass aktifken
  IP-allowlist kalktığı için tenant koruması da kalkardı → çözülen tenant artık
  `E2E_STRESS_TENANT_ID`'ye **hard-bind** edilir (`_exely_test_tenant_allowed`);
  başka tenant'a (ör. aynı non-prod deployment'ta pilot) map eden HotelCode 404
  ile reddedilir → bypass YALNIZ stres tenant'a dokunabilir, pilot drift imkânsız.
- Test: `backend/tests/test_exely_test_auth_mode.py` (20 PASS): active path, her
  tek-koşul eksiğinde fail-closed, prod denial (ENVIRONMENT + APP_ENV + live), +
  tenant-binding (eşleşen stres tenant allow, başka/boş tenant + stres-tenant
  unset/blank deny, whitespace-trim).
- **Etki:** spec § 50 "G" (valid-payload + idempotency) `auth_mode` live-probe ile
  `open_for_testing`'e döner → REVIEW+P2'den gerçek PASS'e. **Yalnız** stress backend
  bu kodu + beş env'i taşıdığında gerçekleşir (CI-deferred). Auth zayıflatma YOK.

### B1 — payment recon idempotency: spec self-open shift ✅
`frontend/e2e-stress/specs/98-payment-pos-reconciliation-dryrun.spec.js`

- "manual-transaction X-Idempotency-Key replay" testi: açık vardiya yoksa stress
  token ile `/api/cashier/open-shift` (opening_amount=0) ile **izole** vardiya açar,
  probe'u koşar, `finally` içinde `/api/cashier/close-shift` ile kapatır.
- `open-shift` zaten `uniq_tenant_open_shift` ile guard'lı → başka açık vardiya
  varsa 400 → eski SKIP path'ine düşer (yarış güvenli). `close-shift` difference
  kaydeder. **EK (architect Round-1):** close best-effort olduğundan `finally`
  sonrası `/api/cashier/current-shift` ile yeniden probe edilir; self-açılan
  vardiya hâlâ açıksa step **FAIL** verir (sessiz açık-vardiya residue engellenir).
- Stress tenant only, pilot mutation yok. Kalan kapalı-vardiya + 1.00 TL txn
  benign stress-tenant residue (yeşili/pilotu etkilemez).
- **Etki:** SKIP×1 + P2×1 → PASS (stress tenant'ta açık vardiya çakışması yoksa).
  CI-deferred doğrulama.

---

## Operatör devops env tablosu (A2/A3/A4 — KOD YOK, backend zaten doğru)

Bu üç item agent-kod gerektirmez; backend zaten fail-closed/doğru. Eksik olan
**stress BACKEND deployment** env'idir (operatör-kontrollü, repl dışı). CI runner
env'i backend'i etkilemez → kör runner-wiring fake-green olurdu, EKLENMEDİ.

| Item | Stress backend deployment env | Backend referansı | Not |
|---|---|---|---|
| A1 Exely valid-path | `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` + (zaten set) `E2E_EXTERNAL_DRY_RUN=true`, `E2E_ALLOW_DESTRUCTIVE_STRESS=true`, `E2E_STRESS_TENANT_ID`, non-prod env | `exely_webhook_router.py:_exely_test_auth_open()` | Bu beş olmadan fail-closed 503 sürer |
| A2 KBS test mode | `KBS_TEST_MODE=1` | `routers/kbs.py:_kbs_test_mode()` | Backend zaten TEST- prefix zorlar; sadece env eksik |
| A3 GraphQL introspection | `GRAPHQL_INTROSPECTION` unset VEYA `false` | `graphql_api/schema.py:_introspection_enabled()` | Default zaten OFF; stress'te `true` drift varsa kaldır |
| A4 HotelRunner imzalı path | `HOTELRUNNER_WEBHOOK_SECRET` = CI runner ile AYNI değer | `stress.yml:105` runner-side mevcut | Backend mirror operatör devops |

**Prod:** A1–A4 gerçek prod secret/whitelist; fail-closed davranış DEĞİŞMEZ.

---

## Reclassify / DEFER (bu turda DOKUNULMADI — honest)

| Item | Önceki | Yeni sınıf | Gerekçe |
|---|---|---|---|
| B2 24h sim scarcity | SEED_DATA_STATE | TEST_EXPECTATION_DRIFT (CI-investigation) | Kök sebep `stress_prefix` harvest/projection drift olabilir; gerçek Run #167 per-item artifact + DB erişimi olmadan kör seed YASAK. Stress backend doğrulaması gerek. |
| B3 folio-mass folio surface | SEED_DATA_STATE | ENDPOINT_SURFACE | `/api/pms/folios=[]` + bookings.folio_id drop = serializer projection sorunu (`modules/reservations/repository.py`), seed değil. API response-shape değişimi geniş blast-radius → ayrı scoped follow-up. |
| B5 city ledger transfer | ROADMAP_BACKLOG | (değişmedi) | Transfer endpoint yok; seed anlamsız. |
| B6 POS recipe/BOM | DO_NOT_TOUCH | (değişmedi) | Entitlement module-blocked. |
| B7 VCC stress booking | RBAC_POLICY | (değişmedi) | cashier_supervisor rol + PCI mask → Paket C/RBAC turu. |
| B8 konaklama vergisi pilot | DO_NOT_TOUCH | (değişmedi) | Pilot mutation riski; read-only anchor onaylı, REVIEW kalır. |

PRODUCT_CONTRACT/RBAC/ROADMAP yüzeyleri (e-Fatura customer_type, revenue dry_run
kill-switch, B2B scope, CRM contract, KVKK anonymize, admin/settings, digital key)
→ **Paket C** (bu turda DEĞİL).

---

## Projeksiyon (CI-deferred, stress backend env + kod deploy şartıyla)

| Metrik | #167 | Bu paket sonrası (tahmini) |
|---|---|---|
| REVIEW | 48 | ~46 (Exely G + payment idemp) |
| SKIP | 44 | ~43 (payment idemp self-open) |
| P2 | 58 | ~55 (Exely G + payment idemp informational düşer) |
| FAIL/P0/P1 | 0/0/0 | 0/0/0 (değişmez) |

A2/A3/A4 operatör backend env'i ayarlanırsa ek REVIEW/P2 düşüşü (KBS/GraphQL/HR
yüzeyleri). Bu paket gerçekçi hedefin (REVIEW→38-42) ilk dilimidir; tek turda
sıfırlama amaçlanmadı.

## Mutlak kurallar (korundu)

pilot mutation=0 · external_calls=[] · fake-green YOK · auth/RBAC zayıflatma YOK ·
gerçek prod secret YOK · skip-as-pass YOK · baseline #167 pointer TAŞINMAZ ·
verdict ≥ GO WITH WATCH (operatör full suite ile teyit eder).
