# F8B Stress Suite — Evolution (Guest Experience, tur-1 → tur-26)

**Status:** Active — GO WITH WATCH after tur-26 workflow timeout fix
**Date:** 2026-05-17
**Scope:** `frontend/e2e-stress/specs/10..13` (4 spec, 22 test), F8A operasyonel paketin üstüne QR/complaints/messaging yüzeyleri.
**Drill rapor:** `docs/drill_reports/20260517_stress_f8b_guest_experience_qr_requests.md`

Bu ADR F8B stres test suite'inin tur detaylarını içerir. `replit.md` "Gotchas" bölümünde tek-satır özet bırakılmıştır.

---

## Seed extension

`backend/domains/admin/router/stress.py` → `_build_f8b_docs(rooms, bookings, guests, stress_tid, prefix, now)` factory:

- `room_qr_requests`: her gerçek odaya 1 open + 1/4 ~25h yaşlı
- `service_complaints`: her 5 odadan 1, 1/10 escalation eligible
- `messages`: her odaya inbound+outbound
- `notifications`: her odaya 1 broadcast + 1/7 escalation

`STRESS_COLLECTIONS` += 4 yeni koleksiyon → unified cleanup + orphan scrub loop'u otomatik tarar (kod duplikasyonu yok).

## Kritik invariant savunmaları

- **(a)** Complaint seed `guest_id=None` → resolve `_notify_guest_resolved` "no guest_id" guard'ında erken döner → Resend HTTP hiç tetiklenmez (RESEND_API_KEY env'de set ama silent).
- **(b)** Messaging spec sadece `/api/messaging/send-{email,sms,whatsapp}` (yalın `db.messages.insert_one`) çağırır — legacy `/api/whatsapp/send-confirmation` (gerçek provider) hiç dokunulmaz.
- **(c)** Folio compensation adjustment booking_id ile lokal Mongo update.
- **(d)** Public QR submit rate-limit 20/10min per (room+IP) → spec 10-A 50 farklı oda kullanır (oda başına 1 submit).

Tüm spec'lerin son testi `pilot_drift=0` gate, batch'lerden sonra `assertNoExternalCallsPostBatch` çağrılır.

---

## Tur-23 (CI #48 NO-GO)

- 10-A bulk endpoint URL `?t=` regex parse refactor + 700ms gap 10-B/11-B/12-A/13-A POST/PATCH loop'larına eklendi.
- 13-A PASS (50/50 send) doğruladı; 10-A 0/50, 11-B 9/20, 12-A 19/30 hala FAIL.

---

## Tur-24 (CI #49) — Tenant ID parse + 429 backoff helper

Deployment log evidence (`fetch_deployment_logs`) iki ayrı root cause:

1. **10-A spec `stressState.target_tenant_id` undefined**: URL `/api/public/room-qr/undefined/<rid>/submit` → 403×50. `global-setup.js:159` state file'a `stress_tid` key'i yazıyor; spec'i `stress_tid || seed_response.target_tenant_id`'e çevirdik (`10-qr-requests.spec.js:59,199`).
2. **11-B 7 OK→13×429 ve 12-A 19/30 ile 11×429 cascade**: prod `apm_middleware` write 120/min/token, 700ms gap'la setup writes ile bucket dolu kalıyor.

Yeni `callTimedWithBackoff` helper (`fixtures/stress-helpers.js:104-126`): 429 yakalar, `retry-after` header'ı parse eder, 1 kez retry (cap 65s — bir tam sliding window). Spec 11-B + 12-A inter-call gap 700→1500ms ve `callTimed`→`callTimedWithBackoff`. Throttle count rec note'a (`throttled_429=N`). 13-A davranışı değişmez (50 send <120 limit).

**Sandbox:** `npx playwright --list` 75 test load, syntax temiz. **P2 watch:** `stress.external_calls active connectors lookup failed:TenantViolationError` tekrarlıyor (ground truth `calls=[]` PASS, NO-GO etmiyor).

---

## Tur-25 — 10-B fix

tur-24 push CI'sinde 10-B `ok=83/90 floor=86` (7×429 retry'sız fail). 10-B en geniş budget (30 req × 3 step = 90 PATCH); tur-24'te bu spec'e backoff uygulanmamıştı.

**Fix:** 10-B PATCH loop `callTimed→callTimedWithBackoff`, gap 700→1500ms, `throttled_429=N` rec note'a; 11-B/12-A ile aynı pattern.

---

## Tur-26 — 10-B timeout + workflow timeout fix

### 10-B timeout
tur-25 push CI'sinde 10-B `Test timeout 180000ms exceeded`. Math: 90×(500ms latency + 1500ms gap) = 180s baseline = Playwright default timeout, retry penceresinde aşılıyor.

**Fix:**
- (a) `test.setTimeout(300_000)` 10-B'ye — 5dk budget.
- (b) Gap 1500→1000ms (60/min ceiling vs 120 limit %50 marj; serial mode → eş zamanlı same-token writer yok).
- (c) `callTimedWithBackoff.fallbackSleepMs` cap 65000→15000ms (`fixtures/stress-helpers.js:117`); 65s heavy loop'larda test budget'i tüketiyordu.

Yeni baseline 135s, worst ~200s, 300s güvenli. Reporter onEnd 10-B timeout'unda serial cascade nedeniyle çalışmıyordu → gate 0516 fallback'inden NO-GO veriyor (fail-closed doğru davranış).

### Workflow timeout
tur-26 push sonrası gate hâlâ 0516 NO-GO veriyordu, Playwright fail annotation yoktu. **Root cause:** `.github/workflows/stress.yml:51` job-level `timeout-minutes: 15` F8A-only için planlanmıştı; F8B 4 spec serial mode + rate-limit gap'leri ile toplam ≈25dk (10-B tek başına 3-5dk). 15dk limitinde job iptal → reporter onEnd hiç çalışmıyor → bugünün dosyası yok → gate stale fallback.

**Fix:** `timeout-minutes: 30` + neden yorumu.

### CI verdict gate fix
`docs/drill_reports/20260516_stress_f8a_frontoffice_folio_hk.md` `| Final verdict (run #20) |` row format `^| Final verdict |` regex'ine uydurulamıyordu (`.github/workflows/stress.yml:134`) → reporter fresh file yazmadığında gate "missing or unparseable" exit 1. Row literal `| Final verdict | NO-GO | ...` yapıldı (historik truth, fail-closed fallback signal).
