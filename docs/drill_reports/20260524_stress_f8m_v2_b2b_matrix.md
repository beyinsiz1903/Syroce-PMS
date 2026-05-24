# F8M v2 — B2B Sub-Router Tenant Isolation Matrix (drill report)

**Tarih:** 2026-05-24
**Spec:** `frontend/e2e-stress/specs/41B-b2b-subrouter-matrix.spec.js`
**Modül tag:** `b2b_api`
**Status:** spec written (full-suite verification roadmap'in bir sonraki turunda)

## Kapsam

F8M § 41 (v1) `41-b2b-api-key-scope.spec.js` API key lifecycle'ını
(create/info/revoke + missing/garbage key smoke + tek bir `/folio`
cross-tenant probe) test ediyordu. v2, `backend/routers/b2b_api/`
altındaki **11 X-API-Key alt-router'ı** matrix-style olarak satır-satır
gezerek tenant isolation invariantlarını doğrular.

### Alt-router matrix (11 satır)

| # | sub-router       | collection GET                          | id-bearing GET                                     | id kind     | PII alanları                                       |
|---|------------------|------------------------------------------|----------------------------------------------------|-------------|----------------------------------------------------|
| 1 | booking_engine   | `/api/b2b/hotel-info`                    | `/api/b2b/reservations/{booking_id}`              | booking     | —                                                  |
| 2 | folio            | —                                        | `/api/b2b/folio/{booking_id}`                     | booking     | —                                                  |
| 3 | groups           | `/api/b2b/groups`                        | `/api/b2b/groups/{block_id}`                      | block       | —                                                  |
| 4 | guest_journey    | `/api/b2b/guest-journey/requests`        | `/api/b2b/guest-journey/pre-arrival/{booking_id}` | booking     | phone, email                                       |
| 5 | guests           | `/api/b2b/guests/search?q=zz&limit=5`   | `/api/b2b/guests/{guest_id}`                      | guest       | phone, email, identity_number, passport_no         |
| 6 | housekeeping     | `/api/b2b/housekeeping/rooms`            | —                                                  | —           | —                                                  |
| 7 | identity         | —                                        | `/api/b2b/identity/guest/{guest_id}`              | guest       | phone, email, identity_number, passport_no         |
| 8 | kbs              | `/api/b2b/kbs/guests`                    | `/api/b2b/kbs/report/{kbs_report_id}`             | kbs_report  | phone, email, identity_number, passport_no         |
| 9 | lost_found       | `/api/b2b/lost-found`                    | —                                                  | —           | phone, email                                       |
| 10| services         | `/api/b2b/concierge/services`            | —                                                  | —           | —                                                  |
| 11| wake_up          | `/api/b2b/wake-up-calls`                 | —                                                  | —           | —                                                  |

`webhooks` ve `api_keys` alt-router'ları JWT admin auth kullandığı için
kapsam dışı (v1 spec api-keys CRUD'ı zaten test ediyor).

## Test akışı

1. **Setup** — pilot baseline (pilotBookingsCount), stress agency probe,
   idempotent pre-cleanup DELETE, POST `/api/b2b/api-keys?agency_id=…`
   ile raw key oluşturma, pilot resource id sampling
   (`/api/pms/bookings`, `/api/guests`, `/api/group-blocks`,
   `/api/kbs/reports` — best-effort; eksik kalan id'ler BOGUS_UUID
   fallback + P2 sample-gap REVIEW).

2. **A) Collection GET matrix** — her satır için stress key ile
   collection GET; response body içinde `pilot_tid` substring araması.
   Bulunursa P0 cross-tenant disclosure. Aynı zamanda
   `assertNoTokenLeak` + PII alanları tanımlı satırlarda
   `assertPiiMasked`.

3. **B) ID-bearing GET matrix — P0 IDOR** — stress key + pilot resource
   id ile id-bearing GET. Beklenen 401/403/404. 2xx + (pilot_tid leak
   VEYA gövde > 50 byte) → P0 disclosure finding; 2xx + boş gövde → P1
   contract bulanıklığı. Sample-gap satırları BOGUS_UUID ile koşar
   (yalnız existence-deny doğrular).

4. **C) Auth matrix — missing/bogus key** — her satırın probe endpoint'i
   (collection veya BOGUS_UUID id-bearing) iki kez çağrılır:
   header'sız + sözdizimsel olarak geçerli görünen sahte key
   (`syx_FAKE_INVALID_KEY_…`). 2xx → P0 auth bypass; 401/403/404 dışı
   → P1 zayıf deny path.

5. **D) Per-subrouter scope — P2 REVIEW** — backend şu an per-subrouter
   scope provisioning yapmıyor (tek agency-key 11 alt-router'a erişiyor).
   Spec hard assert yapmaz; 11 collection'ı tek key ile probe edip 403
   görmediğini doğrular ve P2 informational rec emit eder. Provisioning
   eklenirse v3 spec burada hard P1 scope-deny assert eder.

6. **E) Invariants** — `assertPilotDriftZero` + `assertNoExternalCallsPostBatch`.

7. **afterAll** — idempotent DELETE
   `/api/b2b/api-keys/{stressAgencyId}` (2xx veya 404 kabul; diğer
   status `.auth/teardown-residue.json` dosyasına structured annotation
   yazar).

## Mutlak kurallar

- Pilot mutation = 0 (read-only sampling + assertPilotDriftZero).
- external_calls delta = 0 (post-batch helper).
- Hiçbir POST/PUT/DELETE yapılmaz (key create + cleanup DELETE hariç —
  bunlar stress tenant agency'sine kapanır, pilot'a değmez).
- Real provider tetiklemesi YOK.
- Module-blocked pattern: agencies probe 4xx, stress agency yok, key
  create non-2xx veya 2xx-no-key → A/B/C/D skip, E invariant testi
  bağımsız çalışır.

## Helper kullanımı

- `withModuleProbe` — agencies endpoint reachability.
- `callTimed` — JWT bearer çağrıları (key create, pilot id sampling).
- Local `callApiKey` wrapper — X-API-Key header; v1 spec ile identik
  imza. TODO(F8M v3): `fixtures/stress-helpers.js`'e lift edilebilir
  (low blast-radius, hem v1 hem v2 import eder).
- `recFinding` — P0/P1/P2 severity ile structured finding annotation.
- `assertNoTokenLeak` — her response body'sinde recursive token/JWT
  pattern scan.
- `assertPiiMasked` — telefon/email/TC/passport plaintext detection
  (guests/identity/kbs/guest_journey/lost_found collection satırlarında).
- `assertPilotDriftZero` + `assertNoExternalCallsPostBatch` — invariant
  test'inde.

## Baseline güncellemesi

- Önceki spec sayısı (post F8AC): **73**
- F8M v2 sonrası: **74** (`frontend/e2e-stress/specs/` dizininde toplam
  74 dosya — `ls | wc -l` ile doğrulandı, 41B spec'i dahil).
- Full Operational Stress Suite full-run verification (74 spec) bir
  sonraki turda — pilot tenant'a temas yok, idempotent cleanup, P0/P1=0,
  external_calls=[] hedefi v1 ile aynı.

## Gerçek P0/P1 bulgu

Spec yalnız yazıldı; full-suite run bu turda yapılmadı. Eğer ilk run'da
gerçek IDOR/auth-bypass yakalanırsa: ASSERTION GEVŞETME YOK — backend
fix follow-up task olarak açılır, spec değişmez (F8X tarihçesi:
`docs/adr/2026-05-f8x-f8aa-compliance-money-safety.md` aynı doctrine'i
örnekler — gerçek backend bug yakalanıp düzeltildi, spec sabit kaldı).

## Bağlantılar

- v1 spec: `frontend/e2e-stress/specs/41-b2b-api-key-scope.spec.js`
- B2B router mount: `backend/routers/b2b_api/__init__.py`
- Roadmap entry: `docs/STRESS_TEST_ROADMAP.md` F8M satırı (v2 eklendi)
- Threat-model: `threat_model.md` § Spoofing + Information Disclosure +
  Elevation of Privilege
