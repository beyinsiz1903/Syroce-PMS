# F8AD — Konaklama Vergisi (TR Accommodation Tax) Dry-run — Spec Written (2026-05-24)

> **Status:** Spec written + `node --check` PASS + `STRESS_COLLECTIONS`
> forward-compat orphan-scrub entries eklendi. Full-suite GREEN verification
> bir sonraki CI turunda yapılacak (F8X–F8AA + F8AB + F8AC + F8AD birlikte
> baseline 72 → **73 spec**). Bu rapor "spec-written" milestone'unu kaydeder;
> resmi GREEN baseline raporu CI run sonrası ayrıca eklenecek.

## 1) Run künyesi

| Alan | Değer |
|---|---|
| Tarih | 2026-05-24 |
| Faz | F8AD — Konaklama Vergisi (TR Accommodation Tax) Dryrun |
| Module | `accommodation_tax` |
| Spec dosyası | `frontend/e2e-stress/specs/98-konaklama-vergisi-dryrun.spec.js` |
| Test sayısı | 4 (read-only smoke + success-path detail/export + calculate/report validation + write negative + P0 cross-tenant IDOR + config/finalize IDOR snapshot) |
| Backend değişikliği | `backend/domains/admin/router/stress.py` `STRESS_COLLECTIONS` += `konaklama_vergisi_declarations`, `konaklama_vergisi_postings`, `tga_outbox` (forward-compat orphan-scrub safety net) |
| Baseline | 72 → **73 spec** (full-suite verification pending) |
| 4xx-strict gating | Tüm negatif gate'ler SADECE 4xx kabul eder; 5xx fail-open YOK (REVIEW + P2 finding emit). |
| KVB-spesifik drift | `assertKvbPilotDriftZero` custom helper pilot tenant'ın `declarations` + `postings` count'unu test başı/sonu snapshot karşılaştırır; `assertPilotDriftZero` (bookings) ile birlikte iki-katmanlı drift guard. |

## 2) Threat-model bağlamı

`threat_model.md` § Tampering + Information Disclosure + DoS:
Türkiye Konaklama Vergisi Kanunu (7194) iki **canlı** zamanlayıcı arkasında:

- `backend/workers/konaklama_vergisi_scheduler.py` — aylık beyanname otomatik
  finalize + PDF + Resend e-posta gönderimi (`auto_finalize=true` + `auto_email=true`
  + `email_recipients` aktif olan tenant'lar için).
- `backend/workers/tga_scheduler.py` — TGA outbound batch + retry,
  `integration_tga_outbox` koleksiyonu üzerinden gerçek HTTP push.

Stres testi gerçek beyanname/posting/folio mutasyonu YARATMAMALI, TGA / Resend
outbound çağrısı TETİKLEMEMELİ, cross-tenant IDOR'a karşı sert (P0 hard-fail)
kapı olmalıdır.

## 3) Kapsam

### A) Read-only surface smoke + module probe + success-path detail/export

- Module probe: `GET ${BASE}/config` (en ucuz GET, cron coupling YOK). 403/404
  → tüm test blokları SKIP + P2 REVIEW.
- Surfaces (her biri 2xx + minimum şekil): `config`, `report`, `declaration`,
  `declarations?limit=5`, `postings?limit=5`. Non-2xx + non-block = P2 REVIEW
  (5xx fail-open YOK).
- `config` body `rate_percent` field tipi `number` zorunlu (shape regression
  P2).
- **Success-path detail + export** (cross-tenant DEĞİL — pilot kendi decl'ini
  okur): pilot harvest decl_id → `pilot_token` ile `GET /declarations/{id}`,
  `GET .../export?format=json`, `GET .../export?format=xml` her biri 2xx
  ground truth. Pool boşsa SKIP (vacuous).

### B) Calculate + Report validation + idempotency

- `POST /calculate` matrix (her satır 4xx zorunlu; 2xx = P1, 5xx = P2):
  amount=0 (`gt=0`), amount=-100 (money safety), nights=0/-3 (`ge=1`),
  oversized amount=1e18, oversized nights=1e7. Ek: `calc_bogus_folio_id_ignored`
  — schema'da `folio_id` field'ı YOK; lenient Pydantic 2xx kabul edilir
  (informational), strict 422 da PASS.
- `GET /report?year=2025&month=13` → 4xx zorunlu (date-range gate;
  `_period_bounds` raises 400). 2xx = P1.
- Idempotency: aynı `{amount, nights, exempt}` input iki kez çağrılır,
  `tax_amount + base_amount` identik dönmeli. Drift = P1.

### C) Write surface NEGATIVE probes (no mutation)

- `PUT /config` `rate_percent=999` (`le=100` ihlali) → 422 zorunlu. Geçerli
  payload KASITLI gönderilmez (stress tenant config mutation yasak).
- `POST /declaration/finalize` `year=1999` (`ge=2020` ihlali) → 422. Geçerli
  finalize kasıtlı gönderilmez (cron decoupling, `tax_declarations` insert YOK).
- Bogus decl_id probes (stress_token + UUID): `GET /declarations/{id}`,
  `POST .../submit`, `.../pay`, `.../email`, `GET .../export?format=json` —
  her biri 4xx (404/403/400/422); 2xx = P1 silent no-op / accounting IDOR
  sınıfı regression.
- Bogus folio probe: `POST /post-folio/{bogus_folio_id}` → 404 zorunlu.
- Idempotency-Key replay: aynı bogus folio + aynı `Idempotency-Key` iki kez
  → her ikisi 4xx; biri 2xx = P1.

### D) P0 cross-tenant IDOR — stress_token vs pilot resources (hard-fail)

- Pilot decl harvest: `pilot_token` ile `GET /declarations?limit=5`. İlk
  decl_id alınır; pool boşsa SKIP + P2 (vacuously holds).
- stress_token bearer + pilot decl_id → `GET /declarations/{id}`,
  `POST .../submit`, `.../pay`, `.../email`, `GET .../export?format=json` her
  biri için `expect(status).toBeGreaterThanOrEqual(400)`. 2xx = KESIN P0 tenant
  breach + assertion ile hard-fail.
- Pilot folio harvest (`/api/folios?limit=5`) → stress_token
  `POST /post-folio/{pilotFolioId}` → 4xx zorunlu, 2xx = P0 (finansal mutation
  + tenant breach).
- **Config PUT + finalize IDOR snapshot guard**: bu endpoint'ler tenant_id
  input ALMAZ (current_user.tenant_id'den türer); structural olarak
  cross-tenant breach yapamazlar. Defense-in-depth: stress_token ile invalid
  PUT /config (rate=999) + invalid finalize (year=1999) çağrıları yapılır;
  pilot config'in `updated_at` field'ı (snapshot) ve pilot
  declarations/postings count'u DEĞİŞMEMELİ. Drift = P0 hard-fail
  (`expect(afterStamp).toBe(beforeStamp)` + `assertKvbPilotDriftZero` finally
  bloğunda).

### Cron coupling guard

Her test'in `finally` bloğunda üç-katmanlı invariant:
- `assertNoExternalCallsPostBatch(...)` — `external_calls` delta=0 zorunlu.
  TGA push veya Resend e-posta tetiklenmiş olsaydı burada P0 verir.
- `assertPilotDriftZero(...)` — `pilot_bookings_count` baseline'dan sapmadı.
- `assertKvbPilotDriftZero(...)` — pilot `declarations` + `postings` count
  baseline'dan sapmadı (KVB-spesifik drift; bookings sayacı bunları yakalayamaz).
  Drift = P0 finding (`pilot konaklama vergisi drift tespit edildi`). Endpoint
  unreachable ise REVIEW (fake PASS yok).

> **NOT — `tga_outbox` count direkt API'den okunamaz** (router exposing yok;
> `integration_tga_outbox` internal koleksiyon). `external_calls` delta=0
> guard'ı TGA outbound HTTP'nin tetiklenmediğini garanti eder; tetiklenmediği
> sürece outbox row'u yazılmaz. Bu, doğrudan count snapshot'tan daha güçlü
> bir invariant'tır (provider'a giden trafiği bizzat gözler).

## 4) STRESS_COLLECTIONS forward-compat doctrine

Eklenen üç entry (`konaklama_vergisi_declarations`, `konaklama_vergisi_postings`,
`tga_outbox`) **gerçek backend koleksiyon adları değildir** — backend
`db.tax_declarations`, `db.accommodation_tax_postings`,
`db.integration_tga_outbox` kullanır. Bu task'ın getirdiği spec mutation
YAPMAZ (sadece negative validation + bogus id + cross-tenant IDOR P0
hard-fail); dolayısıyla orphan-scrub aktif olarak hiçbir satır toplamaz.

Forward-compat amaçlı eklendi: gelecekte konaklama vergisi seed faktöryesi
(stress_seed=True + stress_prefix tag'li) eklenirse unified cleanup loop
zaten kapsayacak. `performance_review_checkins` (F8D-v2) ve
`leave_balance_adjustments` aynı forward-compat alias pattern'inin
örnekleridir.

## 5) Doğrulama

- `node --check frontend/e2e-stress/specs/98-konaklama-vergisi-dryrun.spec.js`
  → PASS (syntax-clean).
- Mutlak invariants spec içinde her test'in `try/finally`'sinde re-asserted:
  `external_calls=[]`, `pilot_drift=0`.
- Targeted local re-run + full-suite verification (72 → 73 spec) bir sonraki
  CI turunda; sonuç bu raporun "GREEN" eki olarak iliştirilecek.

## 6) Beklenen bulgular

| Beklenti | Sebep |
|---|---|
| Module-block ihtimali düşük | `/finance/konaklama-vergisi/config` super_admin RBAC altında; stress admin super_admin → 2xx. |
| Calculate gate'leri sağlam | `CalculateRequest` Pydantic `gt=0` + `ge=1` zorunlu; backend cleanly 422. |
| PUT /config rate>100 gate'i sağlam | `KonaklamaVergisiConfig.rate_percent: Field(le=100)`. |
| Finalize year ge=2020 gate'i sağlam | `FinalizeRequest.year: Field(ge=2020, le=2100)`. |
| Bogus decl_id → 404 | `_load_decl` tenant-scoped find_one + `raise HTTPException(404)`. |
| **Cross-tenant IDOR**: pilot decl_id submit/pay/email/get/export → 4xx | `_load_decl` query `tenant_id` filtreli; stress_token tenant=stress_tid, pilot decl tenant=pilot_tid → mismatch → 404. **Eğer 2xx dönerse F8X'in accounting/invoices bulgusunun KARDEŞİDİR** (router'da `_load_decl` tenant filter eksiği, `update_one` `tenant_id` filter eksiği vb.) → backend fix gerekli, ayrı task. |
| Cross-tenant post-folio IDOR | `post_konaklama_vergisi_to_folio(tenant_id=current_user.tenant_id, folio_id=…)` — core fonksiyon folio'yu tenant filtresiyle arar; pilot folio_id + stress tenant_id → folio_not_found → 404. |
| `external_calls` delta=0 | Spec hiçbir yerde `auto_email=true` config'i set etmiyor, finalize çağrısı YOK (year=1999 invalid), TGA push tetiklenmiyor. |
| `pilot_drift=0` | Spec pilot tenant'a yalnız read (GET /declarations + GET /folios) yapar. |

## 7) Out of scope (bu task)

- Backend bug fix'leri — P0/P1 yakalanırsa ayrı task açılır.
- TGA gerçek e-bildirim provider entegrasyonu değişikliği.
- Konaklama vergisi config UI / frontend değişikliği.
- Cron schedule değişikliği (`konaklama_vergisi_scheduler` /
  `tga_scheduler` davranışı aynen kalır).
- Yeni helper extraction — mevcut F8X–F8AA helper konvansiyonları
  (`stressTokens`, `recFinding`, `withModuleProbe`,
  `assertNoExternalCallsPostBatch`, `assertPilotDriftZero`, `fetchSingle`,
  `callTimed`) aynen kullanıldı.
