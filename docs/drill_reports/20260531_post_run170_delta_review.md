# Post-Run #170 Delta Review (analiz-only)

**Tarih:** 2026-05-31
**Tür:** Analiz / sınıflandırma (kod değişikliği YOK)
**Tetikleyen:** Operatör (Murat) — Run #170 SUCCESS geldi ama #168'den net daha iyi değil.
**Doktrin:** no fake-green · no baseline move · no GO claim · no /100 claim · no full stress dispatch (agent) · assertion gevşetme YOK · skip-as-pass YOK.

---

## 0. TL;DR

- **Promote? → HAYIR.** #168 current GREEN BASELINE olarak KALIR. #170 = *post-packages verification run* olarak arşivlenir.
- **Neden:** #170 başarılı (failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0, cleanup idempotent) ama **#168'den daha iyi değil** — REVIEW +2, PASS −2, P2 aynı. Baseline yükseltmek için en az eşit + daha yeni provenance ile *anlamlı* iyileşme gerekir; burada REVIEW arttı.
- **Paket provenance:** A+B/C/D/E/F **CI'a ULAŞTI** (hepsi #170 commit `b3d3bdb`'nin atası). Yani #168→#170 deltası gerçekten paket etkisini ölçüyor.
- **Metrik düşmedi çünkü:** kalan REVIEW/P2 kalemlerinin çoğu **OPERATOR-ENV** (stress backend / CI secret eksikleri — kod doğru). İki kalem **SPEC-DRIFT** (e-Fatura geçersiz veri; housekeeping stale not metni). Bir kalem **kesin teşhis için CI snapshot bekliyor** (folio void-charge).

---

## 1. #168 vs #170 Delta Tablosu

| Metrik | #168 (current GREEN) | #170 (verification) | Delta |
|---|---|---|---|
| Toplam test | 702 | 702 | 0 |
| failedTests | 0 | 0 | 0 |
| PASS | 1382 | 1380 | **−2** |
| FAIL | 0 | 0 | 0 |
| REVIEW | 48 | 50 | **+2** |
| SKIP | 43 | 43 | 0 |
| P0 / P1 | 0 / 0 | 0 / 0 | 0 |
| P2 | 57 | 57 | 0 |
| P3 | 1 | 1 | 0 |
| external_calls | [] | [] | — |
| pilot_drift | 0 | 0 | — |
| cleanup#2 | idempotent | idempotent | — |
| verdict | GO WITH WATCH | GO WITH WATCH | — |
| commit | `52575268` | `b3d3bdb` | — |

**Okuma:** Kırılma yok; suite paketler sonrası sağlam kaldı. Ancak beklenen REVIEW/P2 düşüşü metriklere yansımadı; aksine REVIEW +2.

---

## 2. Hangi paket değişiklikleri CI'a ulaştı? (git provenance — DOĞRULANDI)

Commit zinciri (eskiden yeniye):

```
52575268  ← Run #168 commit (current GREEN BASELINE)
9e9796d1  imports
266a5ada  docs/baseline
5c858cbe  Package C — customer tax number validation
76f57095  Package D — messaging path drift fix
12452add  Package E — void sample window
443b2093  Package F — housekeeping route+selector fix
0daab6ec  docs hygiene
b3d3bdb   ← Run #170 commit (HEAD) "Published your App"
```

Anlamlı kontrol: `git merge-base --is-ancestor 52575268 b3d3bdb` = YES (yani #168 commit'i, #170 commit'inin atası) **ve** yukarıdaki açık zincirde C/D/E/F commit'leri tam olarak `52575268` ile `b3d3bdb` arasında yer alıyor. (`b3d3bdb` zaten HEAD olduğu için `... b3d3bdb HEAD` kontrolü tek başına trivialdir; provenance açık zincir + #168→#170 ancestry'ye dayanır.) **Sonuç: #168, paket C/D/E/F'in HEPSİNDEN ÖNCE; #170 hepsini İÇERİYOR.** Delta gerçekten paket etkisini ölçüyor — "eski commit kullanıldı" ihtimali ELENDİ.

Spot-check (Package F): `b3d3bdb:08-housekeeping-mass.spec.js` → `/housekeeping-status` (L278) + `[data-testid^="room-card-"]` (L289) MEVCUT. Route+selector fix CI'da gerçekten vardı.

---

## 3. Eksen-Eksen Sınıflandırma

Etiketler: **OPERATOR-ENV** (kod doğru, stress backend/CI env veya secret eksik — bu repl'de değil) · **SPEC-DRIFT** (test geçersiz veri/route/metin) · **REAL PRODUCT GAP** (ürün kodu eksik/yanlış).

### 3.1 Housekeeping (Package F) — **OPERATOR-ENV (FE-render) + minör SPEC-DRIFT (stale not)**

- Fix CI'a ulaştı: G testi `/housekeeping-status`'a navigate ediyor, whitelist `[data-testid^="room-card-"]` ile başlıyor (L288–295).
- REVIEW devam ediyor çünkü `noRows` (desktop+mobile `total_rows=0`, L354) → REVIEW (L366, L377). Yani route doğru ama **CI ortamında grid 0 satır render ediyor**. Olası kök: `E2E_FE_BASE_URL`/`REPLIT_DEV_DOMAIN`'in gösterdiği FE'de `stress_token` ile `/housekeeping-status` grid'inin auth/data ile dolmaması (FE-render env / data-state) → **OPERATOR-ENV**, ürün route fix'i değil.
- **Murat'ın "eski mesaj" gözlemi açıklandı:** REVIEW not string'i (L379) hâlâ ESKİ selector listesini hardcode ediyor (`[data-testid="room-card"], tr[data-room-id], ...`) — denenen selector listesi (L288) yeni olmasına rağmen. Yani "eski string" = **stale not metni**, drift'li route değil. Bu küçük **SPEC-DRIFT** (yanıltıcı log).

### 3.2 Exely webhook (Package A+B) — **OPERATOR-ENV**

- `stress.yml` `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` env'ini **set ETMİYOR** (grep boş). Backend çok-koşullu fail-closed gate kodu mevcut; env olmadığı için `auth_mode=fail_closed_503` (doğru, güvenli davranış).
- Bu env webhook'u doğrulayan **stress BACKEND deployment'ında** olmalı (CI runner'da değil) → bu repl/CI dışı, operatör-kontrollü. Honest REVIEW; fake YOK.

### 3.3 HotelRunner webhook secret — **OPERATOR-ENV**

- `stress.yml` L105 `HOTELRUNNER_WEBHOOK_SECRET: ${{ secrets.STRESS_HOTELRUNNER_WEBHOOK_SECRET }}` repo secret'ından okuyor; secret **unset** → CI'da boş geliyor → imza doğrulanamıyor → REVIEW.
- Operatör kasıtlı/eksik. Doktrin gereği configure edilene kadar REVIEW kalır; fake YOK.

### 3.4 GraphQL introspection — **OPERATOR-ENV**

- `stress.yml` `GRAPHQL_INTROSPECTION` / `SENTRY_ENVIRONMENT` set ETMİYOR (grep boş). Backend kodu prod/stress'te introspection'ı fail-closed kapatıyor; ama stress backend deployment'ında `SENTRY_ENVIRONMENT=stress` (veya `GRAPHQL_INTROSPECTION=false`) set edilmediği için ortam "stress" algılanmıyor → `introspection_open=true`.
- Kod doğru, **backend-env eksik** → OPERATOR-ENV.

### 3.5 e-Fatura / accounting_expenses invoice 422 (Package C) — **SPEC-DRIFT** (REVIEW +2'nin güçlü adayı)

- Endpoint `POST /api/accounting/invoices`, schema `AccountingInvoiceCreateRequest`, alan adı **`customer_tax_number`** (eski "`customer_tax_id` mismatch" hipotezi YANLIŞ — bu create path'i `customer_tax_number` bekliyor).
- Stress spec `26-accounting-expenses.spec.js` L139 doğru alan adını gönderiyor AMA **geçersiz değer**: `` `${prefix}ITX${i+1}00000` `` → örn `STRESS_ITX100000` (alfabetik + 11 hane değil).
- Package C validator'ı (`_normalize_customer_tax_number`) artık 10/11-hane numeric olmayan değeri **doğru şekilde 422 ile reddediyor** (gerçek compliance fix).
- **Sonuç:** Package C ürün davranışı DOĞRU; metriği düşürmedi çünkü **spec, C öncesi kabul edilen geçersiz veriyi göndermeye devam ediyor → şimdi 422 → yeni REVIEW**. Yani Package C, bir spec'i (en az +1 REVIEW) yan-etkiyle REVIEW'a soktu. **SPEC-DRIFT** (testin verisi düzeltilmeli, ürün değil). Benzer örüntü `tax_number` (L89 `${prefix}TXB${i+1}00000`) için de geçerli olabilir.

### 3.6 Folio void-charge `charges_empty=5/5` (Package E) — **TEŞHİS AÇIK (CI snapshot gerekli) — SPEC-DRIFT veya REAL PRODUCT GAP**

- Package E window kaymasını yaptı: `voidSampleWindow = src.length>=16 ? slice(10,15) : slice(0,5)` (L19). Test A charges'ı folio[0..99]'a yazıyor; C4 hedefi (10..14) bu aralık içinde — yani **window-depletion hipotezi artık geçerli değil**, ama hâlâ `charges_empty=5/5`.
- Seed gerçeği (doğrulandı): `folio_charges` `folio_id`+`booking_id` ile linkleniyor, `voided=False`. Finance endpoint `GET /api/folio/{folio_id}` → `{folio, charges[], payments[], balance}`, `@cached(ttl=180)`.
- AMA spec **farklı path** çağırıyor: `GET /api/pms-core/folio/detail/{fid}` (04-folio-mass L276), `body.charges` okuyor. Bu pms-core path'inin charges'ı aynı key/shape ile döndürüp döndürmediği (veya hiç döndürmediği) **bu repl'den kesinleştirilemedi**.
- Spec zaten teşhis için snapshot topluyor: `detailShapeSnap` (http + body keys + charges_len, L279–282) ve `chargeShapeSnap`. **Aksiyon:** Run #170 raporundaki bu snapshot'ı oku:
  - `charges_len=0` + `keys` charges içermiyor → pms-core/folio/detail endpoint charges döndürmüyor = **SPEC-DRIFT** (spec finance `/api/folio/{id}`'e geçmeli) veya endpoint **REAL PRODUCT GAP**.
  - `keys` içinde charges var ama field-adı drift (`_id`/`charge_id`...) → zaten tolere ediliyor (L286), bu ihtimal düşük.
- **Önemli ders:** Package E doğru teşhise (depletion) değil, eski hipoteze dayanıyordu; gerçek kök detail-endpoint görünürlüğü. Bu, void-charge REVIEW'inin neden düşmediğini açıklıyor.

---

## 4. REVIEW 48 → 50 (+2) atfı

Kesin satır-satır kırılım Run #170 rapor breakdown'ını gerektirir (bu repl'de yok). En güçlü adaylar:
1. **e-Fatura accounting_expenses 422** (§3.5) — Package C öncesi PASS iken sonrası REVIEW/finding → net yeni REVIEW. **Birincil aday.**
2. **Housekeeping G** (§3.1) — selector_miss zaten bir REVIEW satırı; not metni yanıltıcı olduğu için "yeni" gibi algılanmış olabilir.

Diğer kalemler (Exely/HotelRunner/GraphQL) #168'de de REVIEW'di (OPERATOR-ENV, kalıcı) → +2'ye katkıları olası değil; bunlar "düşmedi" kalemleri, "arttı" değil.

---

## 5. Minimal Sıradaki Nokta-Atışı Düzeltmeler (öncelik sırası)

> Hepsi delta-sınıflandırma sonrası önerilerdir; bu raporda kod DEĞİŞTİRİLMEDİ. Doktrin: assertion gevşetme/skip-as-pass YOK.

1. **[SPEC-DRIFT, en yüksek değer] e-Fatura test verisi:** `26-accounting-expenses.spec.js` L139 (ve L89) `customer_tax_number`/`tax_number` değerini **geçerli 10-hane VKN** üretsin (örn. zero-padded numeric: `String(i+1).padStart(10,'0')`). Bu, ürün doğruluğunu zayıflatmadan REVIEW'i geri PASS'e çevirir (gerçek compliance fix korunur). Tahmini etki: −1…−2 REVIEW.
2. **[SPEC-DRIFT, kozmetik] Housekeeping stale not:** L379 REVIEW not string'i gerçek `candidates` listesini yansıtsın (yanıltıcı log giderme). Metrik etkisi yok ama yanlış teşhisi önler.
3. **[TEŞHİS] Folio void-charge:** Run #170 raporundaki `detailShapeSnap`/`chargeShapeSnap`'i incele → SPEC-DRIFT mi (spec `/api/folio/{id}`'e geçmeli) yoksa REAL PRODUCT GAP mı (pms-core/folio/detail charges döndürmüyor) karar ver. Önce teşhis, sonra tek düzeltme.
4. **[OPERATOR-ENV — kod değil, operatör aksiyonu]** Stress backend/CI ortamı (bu repl dışı):
   - `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` (+ mevcut gate'ler zaten true) stress backend env'inde set edilirse Exely REVIEW kalkar.
   - `STRESS_HOTELRUNNER_WEBHOOK_SECRET` repo secret'ı set edilirse HotelRunner REVIEW kalkar.
   - `SENTRY_ENVIRONMENT=stress` (veya `GRAPHQL_INTROSPECTION=false`) stress backend'de set edilirse introspection REVIEW kalkar.
   - `E2E_FE_BASE_URL`'in stress FE'ye doğru auth ile çözüldüğü doğrulanırsa housekeeping grid render olur (REVIEW kalkar).

---

## 6. Karar & Baseline Durumu

- **Baseline pointer DEĞİŞMEDİ:** Run #168 (`52575268`) current GREEN BASELINE.
- **#170** = post-packages *verification run* (`b3d3bdb`), başarılı ama promote edilmedi.
- **GO iddiası YOK · /100 iddiası YOK · full stress agent tarafından dispatch EDİLMEDİ.**
- Tek "gerçek ürün" şüphesi (folio void-charge) bile teşhis-bekler durumda; geri kalan açıklar OPERATOR-ENV veya SPEC-DRIFT.

**Net mesaj:** A+B/C/D/E/F sistemi kırmadı (sağlamlık kanıtı). Beklenen REVIEW/P2 düşüşünün gelmemesinin nedeni metrik kapanışın çoğunlukla **operatör-kontrollü stress backend env'ine** ve **iki spec-veri/metin drift'ine** bağlı olması — bu repl'deki ürün koduna değil.
