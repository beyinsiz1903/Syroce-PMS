# F10 — Mobile App Coverage Program

> **Açılış:** 2026-05-27
> **Sahip yüzey:** `mobile/` (Expo / React Native, role-based app)
> **Status:** OPEN — coverage = **ZERO** (web stress suite mobile native app'i kapsamaz)
> **Doktrin:** F8/F9 ile aynı — fake PASS yok, skip-as-pass yok, P2/REVIEW downgrade yok, `external_calls=[]`, `pilot_drift=0`, destructive POST pilot tenant'a yok.

---

## 1) Why a separate surface

Bugüne kadarki tüm stress + business + smoke spec'leri **web frontend** (React/Vite) ve **backend** üzerinde koşuyor. `mobile/` Expo uygulaması:

- Bağımsız bundle (React Native + Expo Router, web React 19 kod tabanını paylaşmıyor).
- Kendi auth/storage akışları (`mobile/src/components/BiometricLockGate.tsx`, AsyncStorage tabanlı oturum).
- Kendi `EXPO_PUBLIC_API_URL` / `EXPO_PUBLIC_QUICKID_URL` env'leri.
- Native-only yetenekler (biyometrik kilit, imza pad, kamera, OS push, offline banner).
- KVKK/PII kabul yüzeyleri (`(guest)/checkin`, ID photo akışı, `qrBadge`, `digitalKey`).
- Cashier brute-force throttle (`Task #51 b7186604`) gibi backend-side kontroller mobile'dan da tetikleniyor ama mobile-side test YOK.

**Sonuç:** Mobile, web suite'in altında **ayrı bir test yüzeyi**; "web stress yeşil" mobile için **hiçbir şey kanıtlamaz**.

---

## 2) Mobile surface inventory (kaynaklı)

`mobile/app/` Expo Router yapısı:

### 2.1 Role gruplarına göre route'lar (24 ekran)

| Grup | Route | Kritiklik | Ana endpoint(ler) |
|---|---|:---:|---|
| `(auth)` | `login` | **P0** | `POST /api/auth/login`, `POST /api/auth/2fa/verify`, `POST /api/auth/refresh` |
| `(frontdesk)` | `index` | **P0** | `GET /api/pms/rooms`, `GET /api/reservations/today`, `GET /api/pms/arrivals` |
| `(frontdesk)` | `checkin` | **P0** | `POST /api/reservations/{id}/check-in`, `POST /api/guest/checkin/submit` (ID upload) |
| `(frontdesk)` | `checkout` | **P0** | `POST /api/reservations/{id}/check-out`, `POST /api/folio/{id}/payment`, `POST /api/folio/{id}/close` |
| `(frontdesk)` | `guests` | P1 | `GET /api/guests`, `GET /api/guests/{id}` |
| `(frontdesk)` | `walkin` | P1 | `POST /api/reservations/walkin` |
| `(frontdesk)` | `more` | P3 | misc settings |
| `(gm)` | `index` | P1 | `GET /api/analytics/dashboard`, `GET /api/finance/kpis` |
| `(gm)` | `more` | P3 | misc |
| `(housekeeping)` | `index` | P1 | `GET /api/housekeeping/tasks`, `POST /api/housekeeping/tasks/{id}/complete` |
| `(housekeeping)` | `damage` | P1 | `POST /api/housekeeping/damage-report` |
| `(housekeeping)` | `more` | P3 | misc |
| `(guest)` | `index` | **P0** (guest PII) | `GET /api/guest/me`, `GET /api/guest/booking/{id}` |
| `(guest)` | `booking` | **P0** | `GET /api/guest/booking/{id}` |
| `(guest)` | `checkin` | **P0** (KVKK) | `POST /api/guest/checkin/submit`, ID photo upload (encrypted blob) |
| `(guest)` | `cart` | **P0** (finansal) | `POST /api/guest/purchase-upsell/{bid}`, `GET /api/guest/purchased-upsells/{bid}` |
| `(guest)` | `orders` | P1 | `GET /api/guest/orders` |
| `(guest)` | `roomservice` | P1 | `POST /api/guest/room-service` |
| `(guest)` | `digitalKey` | **P0** | `POST /api/guest/digital-key/issue`, `POST /api/guest/digital-key/revoke` |
| `(guest)` | `earlylate` | P1 | `POST /api/guest/early-late-checkout` |
| `(guest)` | `loyalty` | P2 | `GET /api/guest/loyalty/balance` |
| `(guest)` | `messages` | **P0** (PII) | `GET /api/guest/messages`, `POST /api/guest/messages/send` |
| `(guest)` | `messageThread` | **P0** | `GET /api/guest/messages/{id}` |
| `(guest)` | `qrBadge` | **P0** (room QR + jwt) | `GET /api/guest/room-qr/{token}` (signed, `ROOM_QR_SECRET`) |
| `(guest)` | `more` | P3 | misc |

### 2.2 Cross-cutting components

| Component | Yüzey | Mevcut web spec eşleniği |
|---|---|---|
| `BiometricLockGate.tsx` | OS biometric auth | YOK |
| `OfflineBanner.tsx` | Network resilience | YOK |
| `SignaturePad.tsx` | Guest signature canvas (KVKK consent) | YOK |
| `ui.tsx` | Shared design primitives | n/a |

### 2.3 Native env / secrets

- `EXPO_PUBLIC_API_URL` — backend
- `EXPO_PUBLIC_QUICKID_URL` — Quick-ID service
- `DISABLE_EXPO_PUSH` — push toggle
- `MOBILE_PUSH_SCAN_SECONDS`, `MOBILE_PUSH_VIP_WINDOW_MINUTES` — push schedule
- `KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS` — ID photo retention

---

## 3) Backend endpoints mobile hits (gap matrix)

> Aşağıdaki listede **mobile'dan çağrılan ama mobile-side automated test'i olmayan** endpoint'leri işaretledik. Web stress spec'leri bu endpoint'lerin çoğunu kapsıyor — ama mobile-spesifik akışlar (header, payload shape, auth flow, refresh token rotation, biometric guard, offline replay) **mobile suite'i olmadan kanıtlanmaz**.

| Endpoint sınıfı | Web stress kapsamı | Mobile-side test | Risk |
|---|:---:|:---:|---|
| `/api/auth/*` (login, 2fa, refresh) | ✅ `98-auth-token-lifecycle.spec.js` | ❌ | **HIGH** (refresh token rotation farklı storage) |
| `/api/guest/checkin/*` (ID photo) | ⚠️ partial | ❌ | **HIGH** (KVKK + native camera) |
| `/api/guest/purchase-upsell/*` | ✅ `99-finance-folio-surface.spec.js` (IDOR) | ❌ | **HIGH** (cart UX bug ≠ web) |
| `/api/guest/room-qr/{token}` | ⚠️ partial | ❌ | **HIGH** (token-bound, replay risk) |
| `/api/guest/digital-key/*` | ❌ | ❌ | **CRITICAL** (fiziksel erişim) |
| `/api/guest/messages/*` | ⚠️ partial | ❌ | HIGH (PII) |
| `/api/housekeeping/tasks/*` | ⚠️ partial | ❌ | MEDIUM |
| `/api/housekeeping/damage-report` | ❌ | ❌ | MEDIUM (foto upload) |
| `/api/reservations/*/check-in`, `/check-out` | ✅ business suite | ❌ | HIGH |
| `/api/folio/*/payment`, `/close` | ✅ `99-finance-folio-surface.spec.js` | ❌ | HIGH (cashier brute-force mobile path) |
| Cashier shift handover throttle (`Task #51`) | ⚠️ backend unit only | ❌ | HIGH (mobile cashier mobile-only akış) |

---

## 4) Missing coverage map (ZERO / PARTIAL / COVERED)

| Mobile akış | Durum | Açıklama |
|---|:---:|---|
| Auth login (happy path) | ZERO | mobile detox/maestro test YOK |
| Auth 2FA prompt | ZERO | |
| Auth refresh rotation | ZERO | |
| Biometric lock gate | ZERO | OS-API mock'lu detox test gerekli |
| Frontdesk dashboard render | ZERO | |
| Walk-in reservation create | ZERO | |
| Guest check-in ID photo upload | ZERO | KVKK kritik |
| Guest digital key issue/revoke | ZERO | fiziksel kapı kritik |
| Guest cart upsell purchase | ZERO | finansal kritik |
| Guest QR badge token validation | ZERO | signed-token replay |
| Guest message thread (PII) | ZERO | |
| Housekeeping task list / complete | ZERO | |
| Housekeeping damage report (foto) | ZERO | |
| GM analytics view | ZERO | |
| Offline banner / cache replay | ZERO | OfflineBanner + AsyncStorage |
| Signature pad (KVKK consent) | ZERO | |

**Toplam mobile akış:** ~24 ekran + 4 cross-cutting component → **28 yüzey, 0 dedicated test.**

---

## 5) F10 Sprint plan (öneri — multi-session)

### F10A — Mobile smoke matrix (1 session) — **OPENED 2026-05-27 (Task #83)**

**Tooling decision (locked):** **Playwright on Expo Web bundle**, primary.
- Linux-runnable CI (no Mac runner / Android emulator required for first smoke).
- Reuses PII/console-error patterns from `frontend/e2e-smoke/fixtures.js`.
- Render-only acceptance fits the web bundle perfectly.
- Native deep flows (biometric, push, offline, camera) stay on **Maestro**
  at `mobile/.maestro/` — already wired, EAS-build driven, complementary
  rather than overlapping. **Detox rejected** for F10A: requires native
  build + Mac runner, over-spec for render-only smoke; re-evaluate at F10G
  if Maestro is insufficient for native deep flows.

**Delivered:**
- `mobile/e2e/` scaffold: `playwright.config.ts`, `routes.ts` (25 surfaces
  — every file under `mobile/app/`, faithful to §2.1), `fixtures.ts`
  (env-driven per-role login, observers, PII scanner), `smoke.spec.ts`
  (per-role login + render-only matrix).
- `mobile/package.json` script: `yarn test:e2e:smoke`.
- CI workflow stub: `.github/workflows/mobile-web-smoke.yml`
  (workflow_dispatch only at F10A; gated promotion to PR-required at F10G).
  The existing `.github/workflows/mobile-smoke.yml` continues to drive
  Maestro post-EAS-build flows and is **not** modified.
- README at `mobile/e2e/README.md` documenting decision + run instructions.

**Acceptance (per spec):** 25 surfaces render, console errors = 0
(allowlist-filtered), no JWT / PAN / bearer / api-key pattern in DOM.
Empty screen, error UI, console error, and PII leak each hard-fail the
spec — no skip-as-pass.

**Out of scope for F10A (handed to F10B+):** real auth lifecycle / refresh
rotation, biometric gate, native camera / signature pad, offline replay,
digital key issue/revoke, cashier brute-force throttle.

**Open follow-ups (not blocking F10A landing):**
- First green run against a live `mobile-stress-tenant` (needs seeded
  per-role accounts + Expo Web bundle URL).
- Markdown reporter parity with `frontend/e2e-smoke/markdown-reporter.mjs`
  for drill-report integration.

### F10B — Mobile auth lifecycle deep (1 session)
- Login → 2FA → refresh rotation → logout
- Token storage validation (SecureStore, AsyncStorage rejection of plaintext)
- Biometric lock gate (OS API mock)
- Acceptance: auth full lifecycle PASS, refresh token rotation kanıtlı, biometric gate enforced

### F10C — Mobile guest critical path (2 session)
1. Guest check-in (ID photo, signature, KVKK consent)
2. Guest cart upsell purchase (finansal IDOR + idempotency)
3. Guest digital key issue/revoke
4. Guest QR badge token replay test

### F10D — Mobile frontdesk / cashier deep (1 session)
- Walk-in reservation create
- Check-in / check-out lifecycle
- Cashier shift handover brute-force (mobile path)
- Folio payment + close

### F10E — Mobile housekeeping (1 session)
- Task list / complete
- Damage report with photo upload

### F10F — Mobile offline / resilience (1 session)
- OfflineBanner trigger
- AsyncStorage replay queue
- Network throttle/error injection

### F10G — Full mobile suite CI + baseline drill (1 session)
- GitHub Actions iOS simulator + Android emulator
- Drill report `docs/drill_reports/{date}_f10_mobile_full_suite.md`
- Acceptance: failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0, verdict ≥ GO WITH WATCH

---

## 6) Tooling decision (open)

| Aday | Pro | Con |
|---|---|---|
| **Detox** | Native, fast, gerçek RN render | iOS + Android ayrı setup, CI Mac runner |
| **Maestro** | Yaml flow, basit | Native interaction limited |
| **Playwright Web (Expo Web)** | Mevcut Playwright tooling reuse | Native API'ları (biometric, camera, push) kapsamaz |

**Öneri:** Detox primary + Playwright Web (Expo Web build) destekleyici smoke. Karar F10A açılışında verilecek.

---

## 7) Doctrine guardrails (mobile-spesifik)

- Pilot tenant'a mutation YOK → mobile suite kendi `mobile-stress-tenant` seed'i kullanacak (web stress-tenant'tan ayrı, çünkü mobile akışları farklı state assume edebilir).
- `external_calls=[]` → push provider (Expo Push) ve QuickID mobile suite'te mock'lanacak.
- Secret leak scan zorunlu (JWT pattern, kart PAN, bearer header) — web smoke ile aynı pattern (`frontend/e2e-smoke/fixtures.js`'den kopyala).
- Biometric / OS API'ları mock'lu test edilecek (gerçek cihaz kabul edilmez CI'da).
- Mobile-only secret'lar (Expo push tokens, biometric public keys) kayıt edilmeyecek.

---

## 8) Açılış sonrası ilk aksiyon

- [ ] F10A spec iskeleti task agent paketi (Detox vs Maestro karar dahil)
- [ ] `mobile/package.json`'a Detox dev dep + iOS/Android config
- [ ] `mobile/e2e/jest.config.js` + ilk smoke spec
- [ ] CI workflow stub (`.github/workflows/mobile-smoke.yml`)
- [ ] Mobile-stress-tenant seed scripti (pilot drift = 0 garantili)

**F10 koşumu F9E (full web stress baseline) drill report'u kapanmadan resmi baseline ilan etmez.**
