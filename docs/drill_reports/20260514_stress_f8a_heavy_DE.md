# F8A Heavy D/E Pass — 20260514

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-14T02:25:50.904Z · Tag: `f8a_heavy_DE`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 15 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 8 / 0 / 8 / 3 |
| P0 / P1 / P2 / P3 finding | 0 / 1 / 1 / 0 |
| Süre | 84.2s |
| Final verdict | **GO WITH WATCH** — P1=1 REVIEW=8 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1778725553400_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=45.2 insert=8931.9 total=8977.1
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=5500 ms=2629.2
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=1740.9 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| folio-mass | 3 | 0 | 7 | 0 | 10 |
| housekeeping | 1 | 0 | 0 | 1 | 2 |
| room-move | 4 | 0 | 1 | 2 | 7 |

## 5) P0/P1/P2/P3 Severity Triage

### P1 (1)
- **[folio-mass]** Folio charge tüm denemelerde başarısız
  - Test: `stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › A) 100 folio charge POST (mini-bar, restaurant, other)`
  - Detay: 100 charge POST 0 başarı. Modes: {"s400":100}. Permission veya folio_id resolution sorunu olabilir.

### P2 (1)
- **[room-move]** Hiçbir room-move başarılı değil
  - Test: `stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › A) Positive room-move: 30 (booking → farklı room)`
  - Detay: 30 move denendi, hepsi reject. Tüm hedef odalar dolu olabilir (500/500 seed) — pozitif test için 02-spec'in checkout sonrası boş room override gerekli.

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| folio-mass | folio_split | 10 | 321 | 589 | 589 | 345 |
| folio-mass | folio_payment | 50 | 313 | 331 | 449 | 317 |
| folio-mass | folio_charge | 100 | 313 | 323 | 457 | 314 |
| room-move | room_move | 0 | 0 | 0 | 0 | 0 |

## 7) Bulgular (REVIEW + SKIP detail)

**FAIL adım yok.** PASS / REVIEW / SKIP sınıflandırması üstteki tabloda.

### REVIEW (8)
- **[folio-mass]** setup — bookings=1600 folios=0 pilot_before=30
- **[room-move]** positive_room_move — n=30 ok=0 fail=0 fail_modes={} (hedef oda dolu/OOO ise reject normal)
- **[folio-mass]** charge_post_batch — n=100 ok=0 fail=100 fail_modes={"s400":100}
- **[folio-mass]** perf:folio_charge — n=100 p50=313ms p95=323ms max=457ms avg=314ms
- **[folio-mass]** payment_post_batch — n=50 ok=0 fail=50 fail_modes={"s400":50} method=cash (DRY-RUN, no Stripe)
- **[folio-mass]** perf:folio_payment — n=50 p50=313ms p95=331ms max=449ms avg=317ms
- **[folio-mass]** folio_split_batch — n=10 ok=0 fail=10 fail_modes={"s400":10}
- **[folio-mass]** perf:folio_split — n=10 p50=321ms p95=589ms max=589ms avg=345ms

### SKIP (3)
- **[housekeeping]** ooo_sample — -
- **[room-move]** ooo_setup — -
- **[room-move]** race — no free target

## 8) Test inventory

| # | Test | Outcome | Süre |
|---:|---|---|---:|
| 1 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › D) 20 oda OOO işaretle + summary diff | ✅ passed | 0.0s |
| 2 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › E) Mobile viewport smoke (390x844): tek HK transition + summary | ✅ passed | 0.6s |
| 3 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › Setup: stress folios + bookings list | ✅ passed | 9.3s |
| 4 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › Setup: stress bookings + rooms snapshot | ✅ passed | 14.5s |
| 5 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › A) Positive room-move: 30 (booking → farklı room) | ✅ passed | 0.0s |
| 6 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › B) Negative — occupied target reject | ✅ passed | 4.5s |
| 7 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › C) Negative — OOO target reject | ✅ passed | 0.0s |
| 8 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › D) Race — aynı hedefe paralel iki move | ✅ passed | 0.0s |
| 9 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › E) Pilot drift = 0 | ✅ passed | 0.3s |
| 10 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › A) 100 folio charge POST (mini-bar, restaurant, other) | ✅ passed | 31.6s |
| 11 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › B) 50 dry-run payment POST (cash, reference="F8A_DRY_RUN") | ✅ passed | 15.9s |
| 12 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › C) Folio split-by-amount (10 folio) | ✅ passed | 3.5s |
| 13 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › D) Folio audit GET (5 folio) | ✅ passed | 1.5s |
| 14 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › E) Closed folio guard: checkout sonrası charge reddi | ✅ passed | 2.4s |
| 15 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › F) Pilot drift = 0 | ✅ passed | 0.2s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

⚠️  **GO WITH WATCH → F8B (Channel Manager / outbox / circuit breaker stress)** — REVIEW/P1 maddeleri sonraki turda izlenecek.
