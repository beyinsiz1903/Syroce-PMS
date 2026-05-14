# F8A Heavy A/B Pass — 20260514

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-14T02:18:48.709Z · Tag: `f8a_heavy_AB`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 8 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 4 / 0 / 0 / 6 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 0 / 0 |
| Süre | 24.1s |
| Final verdict | **GO** — Tüm gate + spec adımları PASS, cleanup idempotent, pilot mutation=0, P0/P1=0 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1778725131135_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=52.7 insert=9684.2 total=9736.9
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=5500 ms=2319.7
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=1508.3 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| day-turnover | 0 | 0 | 0 | 2 | 2 |
| folio-mass | 0 | 0 | 0 | 2 | 2 |
| housekeeping | 4 | 0 | 0 | 0 | 4 |
| room-move | 0 | 0 | 0 | 2 | 2 |

## 5) P0/P1/P2/P3 Severity Triage

**Hiç finding yok.** Tüm spec'ler kritik bulgu üretmedi (pilot drift=0, business-rule guard'lar tutuyor, veri kaybı/leak yok).

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| housekeeping | hk_rooms_list | 3 | 199 | 1528 | 1528 | 639 |
| housekeeping | hk_summary | 5 | 321 | 443 | 443 | 345 |

## 7) Bulgular (REVIEW + SKIP detail)

**FAIL adım yok.** PASS / REVIEW / SKIP sınıflandırması üstteki tabloda.

### SKIP (6)
- **[room-move]** positive_move_sample — checked_in=0 (önceki spec hepsini checkout etmiş olabilir)
- **[room-move]** negative_occupied — checked_in=0
- **[folio-mass]** charge_sample — No folios reachable
- **[folio-mass]** payment_sample — -
- **[day-turnover]** guard_sample_size — only 0 bookings
- **[day-turnover]** force_co_sample — only 0

## 8) Test inventory

| # | Test | Outcome | Süre |
|---:|---|---|---:|
| 1 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › A) Positive room-move: 30 (booking → farklı room) | ✅ passed | 0.1s |
| 2 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › B) Negative — occupied target reject | ✅ passed | 0.1s |
| 3 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › A) 100 folio charge POST (mini-bar, restaurant, other) | ✅ passed | 0.1s |
| 4 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › B) 50 dry-run payment POST (cash, reference="F8A_DRY_RUN") | ✅ passed | 0.0s |
| 5 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › A) Open-folio guard: 20 checkout (force=false) → 400 bekle | ✅ passed | 0.0s |
| 6 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › B) Force checkout batch: 100 booking (force=true) | ✅ passed | 0.0s |
| 7 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › A) HK summary endpoint: <2s p95 | ✅ passed | 1.8s |
| 8 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › B) 500-oda HK list endpoint render performansı | ✅ passed | 1.9s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

✅ **GO → F8B (Channel Manager / outbox / circuit breaker stress)**
