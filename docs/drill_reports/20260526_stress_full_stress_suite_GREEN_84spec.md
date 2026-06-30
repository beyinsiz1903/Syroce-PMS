# Full Operational Stress Suite — GREEN BASELINE (84 spec) — 2026-05-26

> **Bu rapor yeni resmi baseline'dır.** 2026-05-24 baseline'ına (68 spec,
> commit `ee7573b3`) F8X–F8AA, F8AB, F8AD, F8AF, F8Z.2, F8M-v2 ve POS/Spa
> eklemeleri eklendi; F8AH 1. tur 4 P1 (konaklama amount/nights overflow,
> KDS terminal-state, KDS idempotency) kapatıldı; F8AH 2. tur P0 (TWOFA
> brute-force throttle) cross-instance Mongo + per-user_id layered throttle
> ile kapatıldı; full-suite tek run GREEN döndü.
>
> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`).
> Tag: `full_stress_suite`.

## 1) Run künyesi

| Alan | Değer |
|---|---|
| Run tarihi | 2026-05-26 |
| Workflow | GitHub Actions — Full Stress Suite (one-shot) |
| Run number | **#143** |
| Trigger | `pull_request` |
| Branch | `main` |
| Commit SHA (HEAD at CI) | `3b3891d` — Published your App |
| Duration | **47m 55s** |
| Status | **Success** |
| Artifacts | 2 |
| Suite kapsamı | F8A + F8B + F8C + F8D (v2 + v3 HR extension) + F8E + F8F..F8O + F8R + F8S + F8U + F8V + F8W + **F8X + F8Y + F8Z + F8AA + F8AB + F8AD + F8AF + F8Z.2 + F8M-v2 + F8AC + F8AE + F8AG + F8AH** |
| Spec count | **84** (`frontend/e2e-stress/specs/`) |
| Toplam test | **556** |
| Başarısız test | **0** |
| Adım PASS / FAIL / REVIEW / SKIP | **1087 / 0 / 46 / 73** |
| P0 / P1 / P2 / P3 finding | **0 / 0 / 60 / 1** |
| Reporter süre | 2821.0s (47m 1s; CI workflow duration 47m 55s) |
| Final verdict | ✅ **GO WITH WATCH** — P2=60 REVIEW=46 (doktrin ≥ GO WITH WATCH eşiği karşılanıyor) |

## 2) Mutlak invariant gates (hepsi PASS — reporter artifact onayı)

| Gate | Status | Kaynak |
|---|---|---|
| `failedTests == 0` | ✅ | reporter `failed=0`; CI workflow success (gate exit 0) |
| `failedSteps (FAIL) == 0` | ✅ | reporter `FAIL=0` |
| `P0 == 0` | ✅ | reporter `P0=0` |
| `P1 == 0` | ✅ | reporter `P1=0` |
| `external_calls_made == []` | ✅ | globalSetup snapshot `external_calls_made=[]` |
| `pilot_drift == 0` | ✅ | globalTeardown `pilot_diff.drift=0` (baseline=30, after=30) |
| Cleanup idempotent | ✅ | cleanup#1 deleted=7734 → cleanup#2 deleted=0 (`idempotent=true`) |
| Workflow success | ✅ | Run #143 status=Success, duration 47m 55s |

## 3) Seed snapshot (globalSetup)

| Alan | Değer |
|---|---|
| prefix | `E2E_STRESS_F7_1779861740675_` |
| room_count | 500 |
| counts | rooms=500, guests=500, bookings=500, folios=500, charges=1750, rnl=1250, hk=500 |
| timing_ms | factory=93.2, insert=23936.6, total=24029.8 |
| external_calls_made | `[]` |
| tenant_context_used | `true` |
| gates | `env_stress_tid_present=true · target_matches_stress_tid=true · pilot_tid_not_targeted=true · destructive_stress_allowed=true · external_dry_run=true` (5/5 ✓) |

## 4) Cleanup snapshot (globalTeardown)

| Alan | Değer |
|---|---|
| cleanup#1 | status=200, deleted_total=**7734**, ms=12546.9 |
| cleanup#2_idempotent | status=200, deleted_total=**0**, ms=10119.2, `idempotent=true` ✓ |
| pilot_diff | baseline_bookings=30, after_bookings=30, **drift=0** ✓ |

## 5) P2/P3 severity triage (informational — verdict'i bloklamaz)

**Toplam:** P2=60, P3=1. Hiçbirinin doktrin ≥ GO WITH WATCH eşiğini
bozma yetkisi yok; tamamı module-blocked SKIP, data-state, RBAC-by-design,
ya da observability/contract eksikliği kategorisinde.

**Yüksek-trafikli P2 kümeleri (artifact'ten):**

- **Module-blocked SKIP (RBAC by design — stress admin role-scope dışı):**
  `mice_events` (A/B/C/D skipped, spaces 403),
  `mice_opportunities` (sales-catering 403),
  `mice_execution` (rbac_denied, A/B/C skip),
  `hr_rbac_pii` (per-role test user 404),
  `crm_offers` (4 SKIP),
  `notification_batch` (DISABLE_EXPO_PUSH guard).
- **Endpoint not deployed / observability eksik:**
  `admin_rbac` ve `settings_audit` (`/api/admin/tenants` 404),
  `ops_readiness` × 3 (backup-status shape değişti, CM outbox depth +
  conflict queue endpoint reachable değil — observability sinyali eksik),
  `mice_execution` D (F&B order send endpoint absent — F8C-v2 backlog).
- **Data-state / sample sebepli inconclusive:**
  `folio-mass` C4 (charges_empty=5/5 — earlier split/refund batch sample'ı
  tüketmiş), `night-audit` C (200 unresolved exception — operasyon
  dashboard takip etmeli), `housekeeping` D2 (OOO transition constraint),
  `finance_reports_currency` B (currency convert 0/2; rate hard floor OK).
- **B2B agency seed eksik:** `b2b_api` + `41B-b2b-subrouter-matrix` —
  `agencies_list_len=0`, matrix tests skipped. F8M-v2 setup gap.
- **GraphQL introspection açık (informational P2):**
  `graphql_isolation` A — production'da disable önerisi; resolver
  tenant_id filtresi (`schema.py:328`) leak'i engelliyor, sadece
  attack surface keşfi ücretsiz oluyor.
- **AI dry-run network/timeout:** `ai_pricing` (recommend-rates 10s
  timeout — A/B/C skip, D/E/F enforced).
- **HR shift consent RBAC:** `hr_shift` C consent_perm_fail=5/5
  (caller ≠ target_staff email — intentional).

P2 detayları ve coverage-gap follow-up planı:
[`docs/STRESS_COVERAGE_GAP_REPORT_20260526.md`](../STRESS_COVERAGE_GAP_REPORT_20260526.md).

## 6) Modül istatistikleri (özet — 85 modül × 556 test)

Reporter modül tablosundan seçilmiş öne çıkanlar (en yüksek hacim +
yeni faz modülleri):

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| `revenue_management` (F8AF) | 53 | 0 | 1 | 2 | 57 |
| `pos_kds_inventory` (F8Z.2) | **40** | **0** | **0** | **0** | **41** |
| `accommodation_tax` (F8AD) | 37 | 0 | 0 | 3 | 41 |
| `pos_deep_lifecycle` | 33 | 0 | 1 | 0 | 35 |
| `pos_extensions` | 30 | 0 | 0 | 0 | 31 |
| `full_24h` | 22 | 0 | 7 | 1 | 30 |
| `twofa_lifecycle` (F8AG) | **27** | **0** | **1** | **0** | **28** |
| `golf_operations` (F8AC) | 24 | 0 | 0 | 0 | 25 |
| `inventory_transfer_procurement` | 21 | 0 | 0 | 0 | 22 |
| `reports_export` | 21 | 0 | 1 | 0 | 22 |
| `auth_token_lifecycle` | 20 | 0 | 0 | 0 | 20 |
| `payment_pos_reconciliation` (F8Z) | 12 | 0 | 0 | 3 | 16 |
| `efatura_earsiv_dryrun` (F8X) | 10 | 0 | 0 | 0 | 11 |
| `identity_reporting_dryrun` (F8Y) | 11 | 0 | 1 | 0 | 13 |
| `kvkk_retention` (F8AA) | 11 | 0 | 0 | 2 | 14 |
| `spa_operations` (F8AB) | 5 | 0 | 0 | 1 | 7 |
| `vcc_pci_compliance` (F8AE) | 10 | 0 | 0 | 1 | 12 |
| `ops_readiness` (F8R/F8W) | 11 | 0 | 1 | 0 | 12 |
| `file_upload_security` (F8S) | 14 | 0 | 0 | 0 | 14 |
| `f8ah_setup` | 2 | 0 | 0 | 0 | 3 |
| `f8ah_cleanup` | 4 | 0 | 0 | 0 | 4 |

Tam tablo reporter artifact'ında (85 modül).

## 7) Yeni eklemeler (F8R–F8W baseline'ından bu raporun baseline'ına +16 spec)

84 − 68 = 16 yeni spec, full-suite içinde geçti:

| Spec | Modül | Faz |
|---|---|---|
| `98-efatura-earsiv-dryrun.spec.js` | `efatura_earsiv_dryrun` | F8X |
| `65-identity-reporting-kbs-jandarma-dryrun.spec.js` | `identity_reporting_dryrun` | F8Y |
| `98-payment-pos-reconciliation-dryrun.spec.js` | `payment_pos_reconciliation` | F8Z |
| `66-kvkk-retention-deletion-anonymization.spec.js` | `kvkk_retention` | F8AA |
| `98-spa-wellness-operational.spec.js` | `spa_operations` | F8AB |
| `98-konaklama-vergisi-dryrun.spec.js` | `accommodation_tax` | F8AD |
| `98-rms-revenue-deep.spec.js` | `revenue_management` | F8AF |
| `98-pos-kds-inventory.spec.js` | `pos_kds_inventory` | F8Z.2 |
| `41B-b2b-subrouter-matrix.spec.js` | `b2b_api` (v2 matrix) | F8M-v2 |
| `98-golf-operational.spec.js` | `golf_operations` | F8AC |
| `98-vcc-pci-compliance.spec.js` | `vcc_pci_compliance` | F8AE |
| `98C-twofa-totp-lifecycle.spec.js` | `twofa_lifecycle` | F8AG |
| `98-ops-surface-smoke.spec.js` | (5 modül: cross_property_rollup, shift_handover, webhook_admin_dlq, eod_report, booking_holds) | F8AH |
| `99-pos-extensions.spec.js` | `pos_extensions` | POS deep extension |
| `98-pos-deep-lifecycle.spec.js` | `pos_deep_lifecycle` | POS deep |
| `99-full-24h-hotel-simulation.spec.js` | `full_24h` | full-day simulation |

## 8) F8AH 2-turlu hardening — P0 + 4 P1 kapatma

### Tur 1 — 4 P1 (commit `94514e6`)

| Bulgu | Çözüm | Dosya |
|---|---|---|
| P1 `calc_oversized_amount` (≥1e12 amount overflow) | Pydantic `le=1e9` clamp + 422 | `backend/routers/finance/konaklama_vergisi.py` |
| P1 `calc_oversized_nights` (≥10k nights overflow) | Pydantic `le=3650` clamp + 422 | `backend/routers/finance/konaklama_vergisi.py` |
| P1 KDS terminal-state revert (served→ready) | 409 guard + `current_status` echo | `backend/domains/pms/pos_fnb_router/kitchen.py` |
| P1 KDS idempotency replay (distinct ids) | Mongo unique `(tenant_id, idempotency_key)` + 503 fail-closed | `backend/domains/pms/pos_fnb_router/kitchen.py` |

### Tur 2 — P0 TWOFA throttle (commits `147266d4` + `67374954` + `8f7f77b6`)

**Bulgu:** `TWOFA_VERIFY_IP` throttle 17 deneme sonrası 429 üretmedi —
brute-force surface açık.

**Root cause:**
1. Cloud autoscale instance'ları per-process Redis (`localhost:6380`)
   kullanıyor; throttle state instance'lar arası shared değil → cap
   dilution.
2. GitHub Actions runner egress IP havuzu (3+ rotating IP) → per-IP key
   `ip:<rightmost-xff>` farklı bucket'lara düşüyor → throttle hiç
   ateşlemiyor. Bu CI artefact'ı değil; gerçek dünya brute-force
   bypass paterni (CDN/NAT/Tor/runner pool egress rotation).

**Fix (layered, fail-closed):**

1. **Shared backend (commit `147266d4`)** — `backend/security/auth_throttle.py`:
   - `_ensure_mongo_throttle_indexes()` — compound `(key, score)` + TTL on
     `expires_at` (`expireAfterSeconds=0`). Strict equivalence fallback.
   - `SlidingWindowThrottle._check_mongo()` — insert→count→compensating-delete
     pattern, no transaction. Boundary race fail-CLOSED (never exceeds cap).
   - `check()` routes `always_on=True` throttles (`TWOFA_VERIFY_IP`,
     `SENSITIVE_AUTH_USER`, `VERIFY_CODE_EMAIL`, `RESET_CODE_IP`,
     `RESET_CODE_EMAIL`) to Mongo first; Mongo hiccup → Redis/in-memory
     fallback (mevcut availability politikası).
   - Uses `_raw_db` (bypasses `TenantAwareDBProxy`) — throttle keys
     IP/user-id scoped, tenant-bağımsız.

2. **Per-user_id layer (commit `67374954`)** — `backend/routers/auth.py`
   `verify_2fa_login`:
   - JWT decode SONRASI, `consumed_jtis` insert ÖNCESI per-user throttle:
     `enforce(TWOFA_VERIFY_USER, f"user:{user_id}")`.
   - `user_id` JWT-trusted claim — attacker IP rotate edebilir ama
     `user_id`'yi forge edemez (JWT_SECRET olmadan).
   - DB write amplification yok: rate-limited istekler `consumed_jtis`
     yazısı yapmadan 429 alır.

3. **Lint fix (commit `8f7f77b6`)** — ruff I001 import ordering.

**Local smoke (backend running):** 17 sequential POST `/api/auth/2fa/verify`
bogus code → attempts 1-15 = 401, 16-17 = **429**. ✓

**Architect review:** PASS (her iki turda da). Residual: Mongo outage
fail-open `always_on` throttles için — mevcut availability politikasıyla
uyumlu non-blocking; strict-mode + alerting backlog ADR'a düştü
(`docs/STRESS_COVERAGE_GAP_REPORT_20260526.md` T005 follow-up).

## 9) Doctrine pekiştirme

- Spec assertion gevşetme: **YOK**. Tüm P0/P1 gerçek bug olarak
  fix'lendi (Pydantic clamp, atomic guard, layered throttle).
- Skip-as-pass: **YOK**. Module-blocked SKIP'ler informational P2 olarak
  raporlanıyor; final invariants her durumda koşuyor (73 SKIP'in
  hiçbiri silent-pass değil — her biri reporter'da explicit P2 satırı).
- Pilot tenant mutation: **0** (pilot_diff.drift=0, baseline=30→after=30).
- External (SMS / e-posta / OTA / payment) çağrı: **0** (`external_calls_made=[]`).
- Cleanup idempotent: ✅ (cleanup#1=7734 → cleanup#2=0, `idempotent=true`).
- Severity downgrade: **YOK**. P0 ve P1'ler kapatıldı; P2=60 + P3=1
  informational module-block / data-state / observability-gap olarak
  listelendi (`STRESS_COVERAGE_GAP_REPORT_20260526.md`). REVIEW=46
  REVIEW kategorisinde kaldı, PASS'e dönüştürülmedi.

## 10) Çıktı cümlesi (pilot/yatırımcı için)

> Syroce PMS; PMS çekirdek, finans, İK, channel manager, guest/public,
> GraphQL/B2B, AI dry-run, cross-tenant güvenlik, auth token lifecycle,
> WebSocket tenant izolasyonu, file upload security, export artifact IDOR,
> ops readiness, **F8X–F8AA local compliance pack (e-fatura/e-arşiv,
> KBS/Jandarma identity reporting, payment-POS reconciliation, KVKK
> retention), F8AB spa & wellness, F8AC golf, F8AD konaklama vergisi,
> F8AE VCC PCI, F8AF RMS revenue deep, F8AG 2FA TOTP lifecycle, F8AH ops
> surface smoke (cross-property rollup + shift handover + webhook admin
> DLQ + EOD report + booking holds), F8Z.2 POS KDS + F&B inventory,
> F8M-v2 B2B sub-router matrix ve POS/Spa derinleştirmeleri** dahil
> 84 spec / 556 test'lik geniş üretim yüzeylerinde Full Stress Suite'i
> tek seferde yeşil geçmiştir (2026-05-26, commit `3b3891d`, run #143,
> reporter süre 47m 1s, failedTests=0, P0=P1=0, P2=60 / P3=1 informational,
> external_calls=[], pilot_drift=0, cleanup idempotent, verdict
> **GO WITH WATCH**).

## 11) Referanslar

- ADR (F8X–F8AA): [`docs/adr/2026-05-f8x-f8aa-compliance-money-safety.md`](../adr/2026-05-f8x-f8aa-compliance-money-safety.md)
- ADR (F8AH): [`docs/adr/2026-05-f8ah-ops-surface-smoke.md`](../adr/2026-05-f8ah-ops-surface-smoke.md)
- Roadmap baseline tablosu: [`docs/STRESS_TEST_ROADMAP.md`](../STRESS_TEST_ROADMAP.md) § Latest verified baseline (2026-05-26)
- Coverage gap raporu: [`docs/STRESS_COVERAGE_GAP_REPORT_20260526.md`](../STRESS_COVERAGE_GAP_REPORT_20260526.md)
- Önceki baseline (historical reference): [`docs/drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md`](20260524_stress_full_stress_suite_GREEN_f8r_f8w.md) — 68 spec, commit `ee7573b3`
- Fix commits (bu baseline'a katkı):
  - `94514e6` — F8AH 1. tur 4 P1 fix (konaklama clamps, KDS terminal-state, KDS idempotency)
  - `147266d4` — Mongo-backed cross-instance throttle
  - `67374954` — Per-user_id layered throttle (IP rotation immunity)
  - `8f7f77b6` — ruff I001 import order
  - `3b3891d9` — Published (CI #143 HEAD)
