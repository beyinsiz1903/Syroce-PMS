# Post-Run #170 — Minimal Fix Pack (Candidate)

**Tarih:** 2026-05-31
**Kapsam:** Yalnızca onaylanmış düşük-riskli SPEC-DRIFT kalemlerinin düzeltilmesi +
OPERATOR-ENV kalemlerinin operatör-aksiyon olarak dokümante edilmesi.
**Baseline:** Run #168 (`52575268…`) **CURRENT GREEN BASELINE olarak KALIR.** Promote=Yok.
Run #170 verification-only; baseline pointer taşınmadı.

## Doktrin (bu pakette mutlak)

no fake-green · no assertion weakening · no validator/RBAC/auth weakening · no PII
exposure · no pilot mutation · external_calls=[] · skip-as-pass YOK · baseline taşıma
YOK · düz "GO"/"/100" iddiası YOK · mobile/F10'a dokunma YOK. **Full stress agent
tarafından dispatch EDİLMEZ** — doğrulama yalnızca targeted pytest + `node --check` +
statik backend route/shape okuması ile yapıldı; CI-deferred.

---

## SPEC-DRIFT düzeltmeleri (uygulandı)

### FIX 1 — e-Fatura: geçersiz `customer_tax_number` → geçerli 10-hane VKN

- **Dosya:** `frontend/e2e-stress/specs/26-accounting-expenses.spec.js`
- **Drift:** B testi (Bulk invoices) `customer_tax_number` olarak alfabetik
  `${prefix}ITX${i+1}00000` gönderiyordu. Package C ile sertleştirilen backend
  validator `_normalize_customer_tax_number` (`backend/routers/finance/accounting.py`)
  `v.isdigit()` **ve** `len ∈ {10, 11}` zorunlu kılıyor; alfabetik değer →
  `ValueError` → **422**. Bu, Package C sonrası ortaya çıkan SPEC-DRIFT REVIEW'in
  birincil kaynağı.
- **Düzeltme:** test verisi geçerli 10-hane VKN'ye çevrildi
  (`String(1000000001 + i)`). **Backend validator GEVŞETİLMEDİ.**
- **Anti-fake-green guard (yeni B2 testi):** `B2) VKN validator strict` —
  - Negatif: alfabetik `customer_tax_number` POST → **422/400 beklenir** (hard
    `expect`: geçersiz VKN asla 2xx olamaz).
  - Pozitif: geçerli 10-hane VKN → RBAC perm-gate yoksa kabul beklenir.
  - `assertNoExternalCallsPostBatch` invariant korunur.
  Bu test, sayım düşürmek için validator'ı gevşetmediğimizi kanıtlar; tersine
  validator'ın strict kaldığını assert eder.
- **Doğrulama:** `pytest tests/test_invoice_tax_id_contract.py` → **26 passed**
  (validator sözleşmesi kilitli). `node --check` 26-spec → OK.

### FIX 2 — Housekeeping: stale selector-miss REVIEW notu

- **Dosya:** `frontend/e2e-stress/specs/08-housekeeping-mass.spec.js`
- **Drift:** `noRows` durumundaki selector-miss REVIEW notu eski/sabit bir selector
  dizesi (`[data-testid="room-card"], tr[data-room-id], ...`) ve route bilgisi
  içermiyordu; gerçek route `/housekeeping-status` ve güncel `candidates` whitelist'i
  yansıtmıyordu (kozmetik ama yanıltıcı).
- **Düzeltme:** `candidates` whitelist'i viewport loop'undan **test-scope'a** taşındı
  (tek kaynak); loop hâlâ aynı listeyi kullanıyor ve selector-miss notu artık
  `candidates.join(', ')` + `/housekeeping-status` route'unu yazıyor. Böylece liste
  her değiştiğinde not da otomatik güncellenir (gelecekteki not-drift'i engellenir).
- **Değişmeyen (bilinçli):** status merdiveni (`noRows → REVIEW`, `slow → FAIL`),
  TTI gate'leri (rows_50<3s / 200<6s / 500<10s, dom<10s, first_row<8s), uygulama
  `data-testid`'leri. REVIEW→PASS downgrade YOK.
- **Doğrulama:** `node --check` 08-spec → OK.

### FIX 3 — Folio C4 void-charge: charges_empty=5/5 — KOD DEĞİŞTİRİLMEDİ (dokümante)

- **Dosya:** `frontend/e2e-stress/specs/04-folio-mass.spec.js` (C4, satır ~261-359)
- **İddia edilen drift:** spec yanlış detail endpoint/path çağırıyor veya yanlış
  response shape parse ediyor.
- **Statik bulgu (yanlış path/shape iddiası ELENDİ):**
  - **Path birebir doğru.** Spec `GET /api/pms-core/folio/detail/{id}` çağırıyor;
    backend route `backend/routers/pms_hardening.py:789`
    `@router.get("/folio/detail/{folio_id}")`, router `prefix="/api/pms-core"` →
    tam path aynı string.
  - **Shape doğru.** `FolioDetailService.get_folio_detail`
    (`backend/modules/pms_core/folio_detail_service.py`) top-level `charges` key
    döndürüyor (voided dahil) — spec `body.charges` ile birebir okuyor.
  - Spec **zaten** `charges_empty=N/N` durumunu **data-state REVIEW + P2** olarak
    doğru sınıflandırıyor (`allEmpty → REVIEW`), serializer-drift durumunu ayrı
    P1 FAIL'e ayırıyor (`shapeDrift`).
- **Geriye kalan ayrım (sadece CI ile):** `charges_empty=5/5` iki olasılıktan biri:
  1. **HTTP 200 + `charges:[]`** → harvest edilen folio'larda gerçekten charge yok
     (data-state; önceki C/C3 split/refund batch tüketmiş olabilir). Meşru REVIEW+P2.
  2. **HTTP 404 (`success:false`)** → harvest edilen `fid` (`it.folio_id || it.id`)
     o tenant'ta folio olarak çözülmüyor (fid kaynağı / id-kind uyumsuzluğu).
  Bu ikisini ayıran tek veri spec'in kendi `detailShapeSnap` (`{http, keys,
  charges_len}`) alanıdır → **CI-run artifact'i; repl'de full stress dispatch
  olmadan üretilemez** (agent dispatch edemez).
- **Karar:** güvenli statik bir spec parser/path fix'i **yok** (path+shape zaten
  doğru). Kör seed / window reshuffle / fake PASS **yapılmadı**. Kök sebep ayrımı
  **OPEN — needs CI `detailShapeSnap.http`** olarak bırakıldı.

---

## OPERATOR-ENV kalemleri (kod ile çözülmez — operatör aksiyonu)

Bu kalemler kodun doğru ama stress backend / CI ortamında env/secret eksik olduğu
için REVIEW üretir. Kod ile etrafından dolaşılmaz (fail-closed doktrini korunur).
Gerekli env/secret'lar (stress/E2E ortamı):

| Kalem | Gerekli ayar | Not |
|---|---|---|
| Exely test webhook auth | `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` | Yalnız non-prod; ayrıca `E2E_EXTERNAL_DRY_RUN=true` + `E2E_ALLOW_DESTRUCTIVE_STRESS=true` + `E2E_STRESS_TENANT_ID` ister (çok-koşullu fail-closed). Prod 503 kalır. |
| HotelRunner webhook imza | `STRESS_HOTELRUNNER_WEBHOOK_SECRET` (workflow'un beklediği şekilde) veya `HOTELRUNNER_WEBHOOK_SECRET` | İmza HMAC doğrulaması; eksikse webhook testi REVIEW. |
| GraphQL introspection | `GRAPHQL_INTROSPECTION=false` **veya** `SENTRY_ENVIRONMENT=stress` | Introspection prod/stress'te default kapalı; spec posture beklentisiyle hizalanmalı. |
| Housekeeping FE render | FE auth + data (geçerli `E2E_FE_BASE_URL`, grid'i besleyen oturum/veri) | `/housekeeping-status` grid'i CI'da 0 satır render ederse selector-miss REVIEW; selector/route doğru (FIX 2), eksik olan FE oturum/veri. |

`stress.yml` şu an Exely/GraphQL env'lerini set etmiyor; bu kalemler operatör
tarafından stress run öncesi ayarlanmalı.

---

## Doğrulama özeti

- `node --check frontend/e2e-stress/specs/26-accounting-expenses.spec.js` → OK
- `node --check frontend/e2e-stress/specs/08-housekeeping-mass.spec.js` → OK
- `pytest backend/tests/test_invoice_tax_id_contract.py` → 26 passed (validator strict)
- Full stress **dispatch edilmedi** (doktrin; operatör sonra koşturur).

## Beklenen etki (hipotez — kanıt DEĞİL; full stress ile doğrulanır)

- e-Fatura B invoice 422→2xx ile SPEC-DRIFT REVIEW'i kapanır; +1 yeni anlamlı PASS
  test (B2 strict-validator guard).
- Housekeeping selector-miss notu artık doğru route+selector yansıtır; **status
  değişmez** (REVIEW koşulları aynı), yalnızca tanı kalitesi artar.
- Folio C4: değişiklik yok; REVIEW+P2 (data-state) kalır, ayrım CI'a ertelenir.

**Promote=No. #168 current GREEN BASELINE. Sıradaki: operatör tarafından final full
stress dispatch (GREEN doğrulama sonrası baseline pointer değerlendirmesi).**
