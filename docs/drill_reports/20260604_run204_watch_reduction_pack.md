# Run #204 WATCH Reduction Pack — P2 Sınıflandırması (Drill Report)

- **Tarih:** 2026-06-04
- **Baseline:** Run #204 GREEN (current) — 708 test, PASS/FAIL/REVIEW/SKIP=1608/0/9/8, P0/P1/P2/P3=0/0/17/0, GO WITH WATCH. Provenance `docs/baselines/BASELINE_CHAIN.md` "Run #204".
- **Kapsam:** Bu pakette KOD DEĞİŞİKLİĞİ YOK — Murat'ın isteği kalan 17 P2'yi SINIFLANDIRMAK. Her kalem bir sınıfa atanır, azaltılabilirlik (reducible) dürüstçe işaretlenir, sıradaki güvenli aksiyon yazılır. Web/backend; mobile/F10 AYRI ve açık.
- **Doktrin:** no fake-green · reclassify-as-pass YOK · by-design'lar reclassify EDİLEMEZ · vacuous/data-state IDOR'lar yalnızca güvenli stress-tenant seed ile (pilot DEĞİL, pilot_drift=0) exercise edilebilir · agent full stress dispatch EDEMEZ → her aksiyon CI-deferred.

## Sınıf tanımları

- **A — BY-DESIGN (informational):** Assert dürüst, davranış kasıtlı. Reclassify/fix YOK; P2-informational olarak kalır. AZALTILAMAZ (azaltmak fake-green olur).
- **B — VACUOUS / DATA-STATE:** Pilot/stress havuzu boş → IDOR vacuously holds veya harvest empty. Leak DEĞİL. Yalnızca güvenli stress-tenant seed + attacker-flip ile exercise edilebilir (memory `stress-idor-seed-via-attacker-flip.md`); pilot'a yazım YASAK. Azaltma SINIRLI.
- **C — DEPLOY-GAP:** Endpoint/module hedef deploy'da mount EDİLMEMİŞ (404). Kod bug DEĞİL. Yalnızca modülü deploy ederek veya bilinçli N/A işaretleyerek kapanır. Infra kararı.
- **D — ENV/POSTURE:** Ortam flag'i (ör. BACKUP_ENABLED). Hedefte env set edilerek kapanır. Ops kararı, kod DEĞİL.
- **E — NEEDS-INVESTIGATION:** Gerçek azaltma adayı — davranış canlı read-only probe ile incelenmeli; gerçekten kırıksa onarım REVIEW/P2'yi dürüstçe düşürür.

## P2 Kalem Sınıflandırması (17/17)

| # | Modül | Bulgu | Sınıf | Reducible | Gerekçe |
|---|---|---|---|---|---|
| 1 | night-audit | Unresolved exception count yüksek (200) | B | Sınırlı | Stress tenant'ta birikmiş unresolved txn; data-state, kod bug değil. Operasyon dashboard takip eder. |
| 2 | ops_readiness | Backup disabled (BACKUP_ENABLED!=true) | D | Evet (ops) | Hedefte backup env/flag set edilirse posture gate geçer. Kod fix yok. |
| 3 | mice_execution | Event'te payment_schedule yok | B | Sınırlı | event e4a56f19 schedule taşımıyor → mark-paid probe skip. Data-state. |
| 4 | hr_shift | Swap consent RBAC-blocked (informational) | A | Hayır | caller != target_staff email = kasıtlı RBAC. Decision reject-only by-design. |
| 5 | settings_audit | Mutation marker 3 retry'da bulunamadı | E | Olası | Async-deferred audit yazımı VEYA PATCH /admin/tenants/{id}/info audit kapsamı dışı — hangisi olduğu canlı doğrulanmalı. |
| 6 | graphql_isolation | Pilot GraphQL vs REST count farkı (informational) | A | Hayır | REST(500)=50 vs GraphQL(100)=100 limit/filtre semantik farkı. Tenant izolasyon kanıtı resolver tenant_id filtresi (schema.py:328) — leak DEĞİL. |
| 7 | cm_exely_webhook | Exely readiness HR-only N/A | A | Hayır | Exely path prod'da kullanılmıyor (HOTELRUNNER var, EXELY_IP_WHITELIST yok). By-design N/A. |
| 8 | public_kvkk | Digital-key route 404 (endpoint_not_deployed) | C | Evet (deploy) | GET /api/guest/digital-key/<bk> 404 → hedefte mount edilmemiş. Deploy/mount kararı. |
| 9 | reservation_deep | Waitlist add 403 "Module 'pms' access denied" | E | Olası | Stress tenant'ta pms modül erişimi yok → entitlement. Waitlist'in doğru module-gate altında olup olmadığı doğrulanmalı (by-design entitlement olabilir). |
| 10 | reservation_deep | City-ledger folio bulunamadı (folios=0) | B | Sınırlı | booking 642cc9c7 için folio seed edilmemiş → transfer test edilemedi. Seed/data-state. |
| 11 | rate_limit_boundary | Public burst'te 429 yok (auth_login 60→0 throttled) | E | EVET → **ÇÖZÜLDÜ** | **Hipotez (limiter-before-auth ordering) YANLIŞ çıktı** — gerçek kök neden (a) throttle backend dilution (LOGIN_IP/ACCOUNT non-always_on) + (b) spec payload `.invalid` → EmailStr 422 (handler'a hiç ulaşmıyor). Düzeltildi. Detay → "E#11 RESOLUTION" bölümü. |
| 12 | accommodation_tax | Declaration pool empty → IDOR vacuously holds | B | Sınırlı | GET declarations list_len=0; cross-tenant decl probe surface yok. Güvenli stress seed + attacker-flip gerekir. Leak DEĞİL. |
| 13 | marketplace | J1 unexpected status=422 (bogus_tid_fallback) | E | Olası | Bogus tenant-id probe 422 dönüyor — büyük olasılıkla by-design validation reject; mutation/leak OLMADIĞI canlı teyit edilmeli. |
| 14 | webhook_admin_dlq | /api/webhooks/status 404 (module not mounted) | C | Evet (deploy) | Module hedefte mount değil → suite SKIP. Deploy/mount kararı. |
| 15 | revenue_management | Displacement saved-scenario IDOR not exercisable | A | Hayır | Backend /api/displacement'te GET/{id} veya DELETE/{id} yok → path-id IDOR vektörü YOK. Tenant scoping per-tenant /history + pilot_drift invariant ile kapalı. |
| 16 | revenue_management | Pilot hurdle harvest empty → IDOR not exercised | B | Sınırlı | GET /api/hurdle-rates/ pilot boş; cross-tenant guard exercise edilemedi. Güvenli stress seed gerekir. |
| 17 | revenue_management | Pilot autopilot queue empty → IDOR not exercised | B | Sınırlı | GET /api/revenue-autopilot/queue?status=pending boş; cross-tenant approve guard exercise edilemedi. Güvenli stress seed gerekir. |

## Sınıf dağılımı (17)

- **A — BY-DESIGN (4):** #4 hr_shift, #6 graphql_isolation, #7 cm_exely_webhook, #15 rms displacement. → AZALTILAMAZ (reclassify fake-green olur). Kabul edilmiş informational.
- **B — VACUOUS / DATA-STATE (6):** #1 night-audit, #3 mice_execution, #10 city-ledger, #12 accommodation_tax, #16 hurdle, #17 autopilot. → Yalnızca güvenli stress-tenant seed + attacker-flip ile exercise edilebilir; pilot'a yazım YOK. Azaltma SINIRLI, doğrulama full-stress dispatch ister (agent yapamaz).
- **C — DEPLOY-GAP (2):** #8 digital-key 404, #14 webhook_admin_dlq 404. → Modülü deploy/mount etmek veya bilinçli N/A işaretlemek. Infra kararı, kod bug değil.
- **D — ENV/POSTURE (1):** #2 backup disabled. → Hedefte env set. Ops kararı.
- **E — NEEDS-INVESTIGATION (4):** #5 settings_audit, #9 waitlist 403, #11 rate_limit auth_login, #13 marketplace 422. → Gerçek azaltma adayları; canlı read-only probe ile davranış doğrulanmalı.

## Dürüst meta-bulgu (azaltma tavanı)

17 P2'nin yalnızca **4'ü (sınıf E)** kodla dürüstçe azaltılabilir; bunların da içinde net en güçlü aday **#11 rate_limit auth_login ordering** (paterni #194 QR fix'iyle kanıtlı, auth ZAYIFLAMADAN limiter-before-auth reorder). **4'ü (sınıf A) by-design** — azaltmak fake-green. **6'sı (sınıf B) vacuous/data-state** — yalnızca güvenli stress-tenant seed ile exercise edilir, doğrulama full-stress dispatch ister, kazanım sınırlı. **2'si (sınıf C) deploy-gap + 1'i (sınıf D) env-posture** — infra/ops kararı, kod değil. Yani gerçek "kod ile azaltılabilir" havuzu ~4 kalemle sınırlı; bu, digitalocean.md'deki "reduction doğası gereği sınırlı" notuyla tutarlı.

## Önerilen sıra (CI-deferred; agent dispatch ETMEZ)

1. **#11 rate_limit auth_login** (sınıf E, en yüksek değer): login route'unda limiter'ı token-verify ÖNCESİNE al (#194 QR paterni). Auth zayıflamaz (geçersiz cred yine reddedilir), pilot_drift=0. → targeted doğrulama + bir sonraki dispatch'te 429 gözlemi.
2. **#5 / #9 / #13** (sınıf E): canlı read-only probe ile by-design mı gerçek mi ayırt et; by-design çıkarsa gerekçeli kayıt (reclassify YOK), gerçekse onar.
3. **Sınıf C/D** (#2/#8/#14): operatör/infra kararı — deploy/mount + BACKUP_ENABLED. Kod tarafı yok.
4. **Sınıf B** (6 kalem): güvenli stress-tenant seed + attacker-flip ile IDOR guard'ları exercise et (pilot'a DOKUNMA). Düşük öncelik, kazanım sınırlı.
5. **Sınıf A** (4 kalem): değişiklik YOK — informational kabul.

## Doktrin teyidi

no fake-green (sınıflandırma; hiçbir kalem reclassify edilmedi) · no auth/RBAC/PII weakening (kod değişikliği yok) · pilot_drift=0 (yalnızca rapor analizi) · external_calls=[] · FAIL/P0/P1=0 çizgisi korundu · full stress agent tarafından dispatch EDİLMEDİ.

## E#11 RESOLUTION — rate_limit auth_login (2026-06-04)

**Orijinal hipotez YANLIŞ çıktı (dürüst düzeltme).** Tablo satırı #11 ve "Önerilen sıra" #1, root-cause'u "limiter token-verify'dan ÖNCE çalışmıyor → invalid-cred burst 403'te short-circuit" (memory `ratelimit-before-auth-ordering.md` / #194 QR paterni) olarak varsayıyordu. Login route'unun (`backend/routers/auth.py` login()) canlı incelemesi + targeted read-only probe bunu çürüttü: ordering KASITLI olarak verify-first → drain-on-success → record-on-fail'dir (Task-137) ve `enforce` başarısızlıkta zaten çağrılıyor. Gerçek kök neden İKİ ayrı katmandı:

1. **Backend — throttle backend dilution (gerçek latent açık).** `LOGIN_IP` (20/60s) ve `LOGIN_ACCOUNT` (10/300s), tüm peer login yüzeyleri (AGENCY_LOGIN_*, VENDOR_LOGIN_*, CASHIER_*, TWOFA_*, RESET_CODE_*) F8AH P0 / Task-55 dalgalarında `always_on=True` (Mongo-backed, cross-instance) yapılmışken non-always_on (per-instance Redis → per-process in-memory) backend'de KALMIŞ tek brute-force-kritik login yüzeyiydi. Cloud autoscale altında 60'lık fan-out burst her instance/process'e ~60/N < cap düşüyor → 429 ASLA tetiklenmiyor. Dosyanın başındaki 98C-D / 98D-B sistemik dilution notunun login'e uygulanmamış hali. **Fix:** `LOGIN_IP`/`LOGIN_ACCOUNT` → `always_on=True` + stabil `name=` (peer'lerle bire bir aynı pattern). Auth ZAYIFLAMAZ: ordering değişmedi (yanlış cred yine 401, doğru cred hit biriktirmez, drain-on-success korunur), `always_on` yalnızca DISABLE_AUTH_THROTTLE escape'ini yok sayar.

2. **Spec — payload handler'a hiç ulaşmıyordu (vacuous finding).** Spec'in auth_login burst'ü `${prefix}_rl@stress.invalid` gönderiyordu. `.invalid` TLD (RFC 6761 special-use) Pydantic `EmailStr` tarafından **handler'a girmeden 422** ile reddediliyor → `_record_failure_and_raise` içindeki `enforce` HİÇ çağrılmıyor → backend ne olursa olsun throttled=0 GARANTİ. Yani #204'teki "auth_login throttled=0" login yüzeyi için backend açığının kanıtı DEĞİL, request-validation bounce'uydu (vacuous). **Fix:** spec payload'ı `@example.com`'a (RFC 2606 doc domain — geçerli format, var olmayan hesap) çevrildi; istek artık handler'a ulaşıp 401 verir, throttle hit kaydeder, cap tetiklenir. 429 beklentisi DÜŞÜRÜLMEDİ, assertion gevşetilmedi — test artık ölçmesi gereken yüzeye gerçekten ulaşıyor.

**Değişen dosyalar:** `backend/security/auth_throttle.py` (LOGIN_IP/LOGIN_ACCOUNT always_on), `frontend/e2e-stress/specs/97-rate-limit-boundary.spec.js` (login payload `.invalid`→`example.com`), `backend/tests/test_auth_throttle_boundary.py` (regresyon: main login policy always_on+cap+namespace assert).

**Targeted doğrulama (agent full stress dispatch ETMEDİ):**
- `node --check 97-rate-limit-boundary.spec.js` → OK.
- `pytest test_auth_throttle_boundary.py test_peer_login_throttle.py` → 15 passed.
- Canlı read-only probe (localhost:8000, 25× wrong-cred burst, always_on DISABLE'ı yok sayar):
  - `@stress.invalid` → 25×422 (handler'a hiç ulaşmıyor — eski spec'in neden throttled=0 gördüğünün kanıtı).
  - `hotel_id+username` (handler'a ulaşan) → 10×401 + **15×429**.
  - `@example.com` (yeni spec payload) → 10×401 + **15×429**.

**Bir sonraki full stress'te P2 düşer mi?** EVET beklentisi: auth_login burst artık ≥1 429 gözlemleyecek (LOGIN_IP cap=20/60s ya da LOGIN_ACCOUNT cap=10/300s tetiklenir), `throttledAny=true` → #11 P2 recFinding ARTIK FIRE ETMEZ. Doğrulama CI-deferred (operatör dispatch). Diğer 16 P2 etkilenmez. external_calls=[], pilot_drift=0 (login burst anonim, throttle_hits system-scoped, tenant mutasyonu yok).
