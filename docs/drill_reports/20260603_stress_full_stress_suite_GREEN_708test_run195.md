# Run #195 — Full Stress Suite GREEN Baseline Promotion Drill

- **Tarih:** 2026-06-03
- **Run:** #195, run ID 26879084806, job ID 79274137231, event=workflow_dispatch, run_attempt=1, branch main.
- **Commit:** `a3d43a1cf71dbda61b9795539da127e845727974` ("Published your App"; WATCH Reduction Pack parent `c40c277f`).
- **Sonuç:** 708 test, status=Success (conclusion=success), failedTests=0, PASS/FAIL/REVIEW/SKIP=1570/0/15/11, P0=P1=0, P2=23 / P3=0, external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict **GO WITH WATCH**.
- **Süre:** 4146.8s (job ~70dk, 1h10m8s).

## 1) Provenance (fabrike EDİLMEDİ)

- Anonim public GitHub Actions API ile doğrulandı:
  - run #195: head_sha=`a3d43a1cf71dbda61b9795539da127e845727974`, status=completed, conclusion=**success**, event=workflow_dispatch, run_attempt=1.
  - job 79274137231: conclusion=success, started 2026-06-03T10:31:52Z → completed 11:41:57Z.
  - artifacts (2, expired=false):
    - stress-drill-report (30547 B) — digest sha256:`d67b9615cf547531da2abc532f7afc3f8a84602aff4884a8fae133e5b67de228`.
    - playwright-stress-report (809220 B) — digest sha256:`83160fb57dd4ba012a5ea9b68a5057f28fda157bef692124e4c02fb8deed36c5`.
- head_sha = local HEAD = origin/main. WATCH pack (parent `c40c277f`) bu run'a dahil.
- **Yöntem dürüstlüğü:** artifact ZIP gövdesi auth-gated → REVIEW gövde-toplamı satır-satır re-türetilmedi; operatör raporu + granülarite-modeli + #190 §5'e dayanır. Ekran görüntüsü tek başına kanıt sayılmadı; API metadata esas alındı.

## 2) #194 → #195 delta

| Metrik | #194 | #195 | Δ |
|---|---:|---:|---:|
| Toplam test | 708 | 708 | 0 |
| failedTests | 0 | 0 | 0 |
| PASS | 1565 | 1570 | +5 |
| FAIL | 0 | 0 | 0 |
| REVIEW | 17 | 15 | −2 |
| SKIP | 11 | 11 | 0 |
| P0 / P1 | 0 / 0 | 0 / 0 | 0 |
| P2 | 24 | 23 | −1 |
| P3 | 0 | 0 | 0 |

Temiz, pozitif, regresyonsuz ilerleme.

## 3) WATCH Reduction Pack kanıtı (#195 ile çapraz okuma)

- **T001 `/api/security/audit-logs` 500-hardening — LANDED.** #194'te WATCH'ta görünen audit-logs 500 yüzeyi #195'in P2 (§5) ve REVIEW (§7) listelerinde ARTIK YOK.
- **T002 `/api/hr/staff` 500-hardening — LANDED.** hr/staff serialization 500 yüzeyi #195 P2/REVIEW listelerinde YOK.
- **T003 Room QR submit rate-limit reorder — kodda LANDED, bu run'da stress-exercise EDİLMEDİ.** rate_limit_boundary P2 sürüyor ama detay: `surfaces=[{"key":"qr_submit","skipped":"no_room"}, {"key":"auth_login","n":60,"ok":0,"throttled":0,"clientErr":60,...}]`. Yani spec 97 §A QR yüzeyini "no_room" ile atladı → QR fix'i sadece canlı probe ile doğrulandı (önceki drill: 20×403 + 5×429). Kalan finding ayrı yüzey: `auth_login` burst (0 throttled).
- **T004 activity-PII — BY-DESIGN, sürüyor (beklenen).** notification_batch P2/REVIEW: `freetext_pii=5, pii_masked=true`, /activity `view_guest_list`-gated değil → ürün-kontrat (Wave 9), kod gap değil.

## 4) Açık WATCH adayları (#195 P2=23 / REVIEW=15 / SKIP=11)

- **Yeni aday — login-throttle ordering:** rate_limit_boundary `auth_login` 60 istek → 0 throttled, 60 clientErr, retryAfterSeen=false. Memory `ratelimit-before-auth-ordering.md` ile aynı kalıp (token-verify limiter'dan önce → sayaç artmıyor). T003'ün QR'da yaptığı reorder login yüzeyine uygulanabilir. **Bu pakette ele ALINMADI (scope dışı).**
- Sürenler: night-audit unresolved (200), backup posture (BACKUP_ENABLED!=true), housekeeping soft cold-boot TTI (rows_50 ~3067ms, soft), admin_rbac `/api/system/db-stats` non-2xx, settings_audit async audit marker, reservation_deep waitlist 403 (module 'pms' access denied) + city-ledger folios=0, finance_folio 409 (open-folio guard + payment perm — by-design), digital-key 404 (not deployed), webhook_admin_dlq 404 (not mounted), full_24h data scarcity, çeşitli IDOR-vacuous (harvest empty).
- Sıradaki seçenek: mobile/F10 baseline (ayrı ve açık, doğrulanmadı).

## 5) Doktrin teyidi

no fake-green (CI conclusion=success + metadata API doğrulandı) · provenance fabrike EDİLMEDİ · external_calls=[] · pilot_drift=0 · failedTests=0 · P0=P1=0 · verdict GO WITH WATCH (düz "GO"/"/100" iddiası YOK) · mobile/F10 ayrı · agent full stress dispatch ETMEDİ (run operatör tarafından workflow_dispatch ile koşuldu, agent yalnızca provenance doğruladı).
