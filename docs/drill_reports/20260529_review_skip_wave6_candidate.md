# Wave 6 Candidate — ENV / SECRET / TEST-POSTURE

> **Program:** REVIEW/SKIP Zeroing (web/backend Full Stress Suite).
> **Baseline (FIXED — taşınmaz):** Run #162 · commit
> `bde7662744c9b94a5c9294fa778202d813319dfc` · REVIEW 46 / SKIP 61 / P2 60 ·
> GO WITH WATCH.
> **Envanter:** `docs/drill_reports/20260529_review_skip_zeroing_inventory.md`.
> **Doctrine:** fake-green YOK · güvenlik gevşetme YOK · gerçek prod secret YOK ·
> "GO"/"/100" iddia YOK · bu turda full stress KOŞULMAZ.

---

## 0) TL;DR — Wave 6 bulgusu

Backend kodu, hedeflenen **5 alanda zaten doğru ve fail-closed**. REVIEW
kalemleri prod **bug değil**; stres **ortam posture**'ı (env/secret) eksik
olduğu için signed/valid path exercise edilemiyor ve spec'ler dürüstçe REVIEW
kaydediyor (fake-green yapmıyorlar). Dolayısıyla Wave 6:

1. **Repo değişikliği (yapıldı):** `stress.yml` job env'ine runner-side
   test-only HMAC secret referansı eklendi.
2. **Operatör/devops işi (runbook aşağıda):** stres **backend** deployment'ı
   ilgili env'leri set etmeli (repl'den canlı backend secret'ı set EDİLMEZ).
3. **Backend kod değişikliği:** Wave 6 için **gerekmiyor** (zaten fail-closed).
4. **AI recommend-rates:** N+1 perf bulgusu → PERFORMANCE_WATCH, ayrı task
   (bu env wave'inin dışında; prod revenue-pricing koduna bu wave'de
   dokunulmuyor).

---

## 1) Alan-alan durum

| Alan | Backend kodu | Spec | Wave 6 aksiyonu |
|---|---|---|---|
| **Exely webhook** | `exely_webhook_router.py` — `EXELY_IP_WHITELIST` unset → **503 fail-closed**; literal IP | `50-cm-webhooks-exely` (G/H `auth_mode=open_for_testing` şartlı) | Backend stres env: whitelist=runner egress IP **VEYA** stres-only test-auth mode (§4a — `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK` DEĞİL) |
| **HotelRunner webhook** | `hotelrunner_webhook.py` `_verify_hotelrunner_signature` — secret unset → **503**; HMAC-SHA256 `f"{ts}.".encode()+raw` | `51-cm-hotelrunner-outbox` F (secret şartlı) | Runner+backend AYNI `HOTELRUNNER_WEBHOOK_SECRET` (test-only) |
| **CM outbox idempotency** | unique `idempotency_key` index (kod doğru) | `52-cm-outbox-idempotency` E (secret şartlı) | HotelRunner secret'a bağlı (aynı çift-taraf) |
| **KBS dry-run** | `routers/kbs.py` `_kbs_test_mode()` — `KBS_TEST_MODE=1` → `TEST-` prefix guard | `65-identity-reporting-kbs-...` | Backend stres env: `KBS_TEST_MODE=1` |
| **GraphQL introspection** | `graphql_api/schema.py` `_introspection_enabled()` — prod/prod/stress/staging **default OFF** (mount: `server.py:458`) | `40-graphql-tenant-isolation` | Backend stres env: `SENTRY_ENVIRONMENT=stress` (zaten OFF yapar) veya `GRAPHQL_INTROSPECTION=false` |
| **AI recommend-rates** | `autopilot_reco.py` — salt-DB occupancy (no-network), competitor fetch simüle | `43-ai-pricing-dryrun` | **Env değil** — N+1 perf (room_type×gün `count_documents`). PERFORMANCE_WATCH; ayrı perf task |

---

## 2) İmza uyum kanıtı (false-P0 önleme)

- Backend (`hotelrunner_webhook.py:73`): `signed_payload = f"{ts_header}.".encode() + raw`
- Spec (`51-...spec.js`): `signed = "{ts}.".concat(raw)` → `HMAC-SHA256(secret, signed)`
- **Eşleşir.** Runner ve backend AYNI secret'i tuttuğunda imza geçerli →
  2xx PASS. Secret farklı/eksik olursa spec 401 → P0 (kasıtlı sinyal). Bu
  yüzden runner secret'ı **backend ile birebir aynı** olmalı.

---

## 3) Repo değişikliği (bu turda yapıldı)

`.github/workflows/stress.yml` job env:
```yaml
HOTELRUNNER_WEBHOOK_SECRET: ${{ secrets.STRESS_HOTELRUNNER_WEBHOOK_SECRET }}
```
- GH secret unset → spec'ler **honest REVIEW** kalır (fake-green yok).
- Bu runner-side; payload'ı **imzalamak** için gerekir. Backend doğrulaması
  için stres backend AYNI değeri tutmalı (§4).

---

## 4) OPERATÖR RUNBOOK — stres backend env (repl dışı, devops)

> Bu env'ler stres **deployment**'ında (E2E_BASE_URL'in işaret ettiği backend)
> set edilir. **Repl'den canlı backend secret'ı set EDİLMEZ.** Hepsi
> **test-only**; **PROD gerçek secret + gerçek whitelist** kullanır.

| Env | Stres değeri (test-only) | Prod | Etki |
|---|---|---|---|
| `HOTELRUNNER_WEBHOOK_SECRET` | GH secret `STRESS_HOTELRUNNER_WEBHOOK_SECRET` ile **birebir aynı** | Gerçek secret | 51-F/52-E signed valid-path PASS |
| `EXELY_IP_WHITELIST` | Runner egress IP (literal, CIDR değil) — **tercih edilen yol** | Gerçek Exely IP'leri | 50-G/H open path |
| Exely test-auth mode (§4a) | stres-only, çok-koşullu gated | **set EDİLMEZ** | 50 auth_mode=open_for_testing (whitelist mümkün değilse) |
| `KBS_TEST_MODE` | `1` | `0`/unset | 65 `TEST-` prefix guard 422 |
| `GRAPHQL_INTROSPECTION` | `false` (veya `SENTRY_ENVIRONMENT=stress`) | unset/`false` | 40 introspection closed → PASS |

Fail-closed korunur: env unset kalırsa backend 503/REVIEW verir (güvenli);
hiçbir değişiklik güvenliği gevşetmez.

---

## 4a) Exely stres posture — KARAR (Murat, 2026-05-30)

> **KARAR:** `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1` **KULLANILMAYACAK**. Webhook
> gibi dışarı açık bir yüzeyde adı "unauthenticated allow" olan bir bayrak,
> stres-only olsa bile prod/staging'e sızma riski taşır. Yerine **stres-only,
> çok-koşullu test-auth mode** tercih edilir.

**Tercih sırası:**
1. **Birincil:** `EXELY_IP_WHITELIST` = runner egress IP (literal). Mümkünse
   bununla yetin — yeni bayrak gerekmez, en güvenli yol.
2. **İkincil (whitelist mümkün değilse):** stres-only test-auth mode
   `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing`.

**`EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` etkinleşme koşulları (HEPSİ
doğru olmalı — AND):**
- `E2E_EXTERNAL_DRY_RUN=true`
- `E2E_STRESS_TENANT_ID` set
- `E2E_ALLOW_DESTRUCTIVE_STRESS=true`
- ortam CI/stres/test (prod/staging **DEĞİL**)

**Değişmez kurallar:**
- Prod/varsayılan davranış **fail-closed 503** kalır (`EXELY_IP_WHITELIST`
  yoksa). Bu mode prod'da ASLA etkin olmaz.
- Payload yine tenant/prefix guard'dan geçer (kör kabul yok).
- `external_calls=[]` kalır; pilot tenant mutasyonu YASAK.
- Valid-payload / idempotency testleri (50-G/H) yalnız bu explicit stres-only
  mode altında koşar.

**Durum:** Bu bir **backend kod görevi** (yeni gated mode `exely_webhook_router.py`).
Wave 6 env posture'ının dışında, ayrı follow-up olarak takip edilir — bu turda
implement edilmez (doktrin: güvenlik-hassas webhook auth değişikliği kendi
odaklı turunu + architect review'unu hak eder). Karar burada kilitlendi.

---

## 5) Validation matrix (dürüst)

| Kontrol | Burada doğrulanabilir mi? | Sonuç |
|---|---|---|
| Backend 5-alan fail-closed/doğru | Evet (kod incelemesi) | **DOĞRULANDI** |
| İmza tabanı runner=backend | Evet (kod karşılaştırma) | **DOĞRULANDI** (false-P0 yok) |
| `stress.yml` secret unset → spec REVIEW (no fake-green) | Evet (spec mantığı) | **DOĞRULANDI** |
| `stress.yml` YAML geçerli | Evet | **DOĞRULANDI** (parse) |
| Targeted spec'ler gerçek PASS (signed/valid path) | **Hayır** — canlı stres backend env + seeded stress tenant ister | **CI-DEFERRED** (operatör §4 set edince) |
| Full stress suite | Hayır (doctrine: bu turda koşulmaz) | Wave 6–9 sonrası |

> **Neden CI-deferred:** Targeted stress spec'leri uzak `E2E_BASE_URL` backend'e
> ve seeded stress tenant'a koşar; lokal repl backend'inde stress tenant yok ve
> globalSetup fail-closed gate'leri gerçek stres secret'larını ister. Bu yüzden
> "targeted spec PASS" iddiası **CI'da** (operatör §4 env'lerini set ettikten
> sonra) doğrulanır — burada fake-green ÜRETİLMEZ.

---

## 6) Beklenen etki (Wave 6 tamamlandığında, CI'da)

| Kalem | #162 | Wave 6 sonrası beklenti |
|---|---|---|
| `cm_hotelrunner_webhook` signed-path | REVIEW | PASS (secret çift-taraf) |
| `cm_outbox` active idempotency | REVIEW | PASS |
| `cm_exely_webhook` valid-payload/cancel | REVIEW×2 | PASS (open_for_testing) |
| `identity_reporting_dryrun` KBS guard | REVIEW | PASS (`KBS_TEST_MODE=1`) |
| `graphql_isolation` introspection | REVIEW | PASS (introspection closed) |
| **REVIEW toplam** | 46 | ~40 (Wave 7–8 ile <25 hedefi) |

> Bu **tahmindir**; gerçek sayı CI Run'da ölçülür. Baseline pointer (#162)
> bu turda **taşınmaz**.

---

## 7) Kararlar (kapandı — Murat, 2026-05-30)

- **AI recommend-rates N+1**: ✅ Wave 6 dışında ayrı follow-up perf task olarak
  açıldı (PERFORMANCE_WATCH). Prod revenue-pricing koduna bu env wave'inde
  dokunulmaz.
- **Exely stres modu**: ✅ KARAR §4a — `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK`
  KULLANILMAYACAK. Birincil yol `EXELY_IP_WHITELIST`=runner-IP; whitelist mümkün
  değilse stres-only çok-koşullu `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing`
  (backend kod görevi, ayrı tur). Prod fail-closed 503 değişmez.
