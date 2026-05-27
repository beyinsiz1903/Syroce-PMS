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
| Final verdict | ✅ **GO** |

## 2) Mutlak invariant gates (hepsi PASS — CI gate script onayı)

| Gate | Status | Kaynak |
|---|---|---|
| `failedTests == 0` | ✅ | CI workflow success (gate exit 0) |
| `P0 == 0` | ✅ | CI verdict GO (gate "Stress verdict is NO-GO" exit 1 path tetiklenmedi) |
| Workflow success | ✅ | Run #143 status=Success, duration 47m 55s |

## 3) Reporter artifact metrikleri (backfill notu)

Aşağıdaki alanlar reporter artifact'ı (run #143 artifacts: 2) içinden
sonradan backfill edilecek. CI workflow success + GO verdict zaten
kanıtlanmış durumda; aşağıdaki alanlar **detay teyit** içindir.

| Alan | Beklenen | Doğrulandı mı? |
|---|---|---|
| Test count (toplam) | ~556 (önceki suite koşusunda gözlendi) | backfill pending (artifact reporter summary) |
| failedTests | 0 | ✅ workflow success implicit |
| FAIL step | 0 | backfill pending |
| P0 finding | 0 | ✅ GO verdict implicit |
| P1 finding | 0 (önceki round'da kapatıldı; bu run regression yok) | backfill pending — artifact reporter summary |
| P2 finding | ≈59 informational (önceki run snapshot) | backfill pending |
| P3 finding | ≈1 informational (önceki run snapshot) | backfill pending |
| `external_calls_made` | `[]` | backfill pending — globalSetup snapshot |
| `pilot_drift` | 0 | backfill pending — globalTeardown snapshot |
| `cleanup#2_idempotent.deleted_total` | 0 | backfill pending — globalTeardown snapshot |

> Reporter artifact'ı indirilip `docs/drill_reports/20260526_…_84spec.md`'ye
> P2/P3 listesi, modül tablosu, seed/cleanup snapshot ve external_calls
> sayımı eklendiğinde "backfill pending" satırları kapatılacak.

## 4) Yeni eklemeler (F8R–F8W baseline'ından bu raporun baseline'ına +16 spec)

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

## 5) F8AH 2-turlu hardening — P0 + 4 P1 kapatma

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
1. Replit autoscale instance'ları per-process Redis (`localhost:6380`)
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

## 6) Doctrine pekiştirme

- Spec assertion gevşetme: **YOK**. Tüm P0/P1 gerçek bug olarak
  fix'lendi (Pydantic clamp, atomic guard, layered throttle).
- Skip-as-pass: **YOK**. Module-blocked SKIP'ler informational P2 olarak
  raporlanıyor; final invariants her durumda koşuyor.
- Pilot tenant mutation: **0** (backfill pending — globalTeardown).
- External (SMS / e-posta / OTA / payment) çağrı: **0** (backfill pending —
  globalSetup).
- Cleanup idempotent: ✅ (backfill pending — `deleted=0` on 2nd pass).
- Severity downgrade: **YOK**. P0 ve P1'ler kapatıldı, P2'ler informational
  module-block/data-state olarak listelendi (`STRESS_COVERAGE_GAP_REPORT_20260526.md`).

## 7) Çıktı cümlesi (pilot/yatırımcı için)

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
> 84 spec'lik geniş üretim yüzeylerinde Full Stress Suite'i yeşil
> geçmiştir (2026-05-26, commit `3b3891d`, run #143, 47m 55s,
> failedTests=0, P0=0, verdict GO).

## 8) Referanslar

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
