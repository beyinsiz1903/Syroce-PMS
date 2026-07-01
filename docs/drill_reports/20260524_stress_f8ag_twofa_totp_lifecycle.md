# F8AG — 2FA TOTP Lifecycle Stress (spec written 2026-05-24)

## Özet

Yeni stress spec'i — `frontend/e2e-stress/specs/98C-twofa-totp-lifecycle.spec.js`
(module key `twofa_lifecycle`) — yazıldı. F8U auth_token_lifecycle ve
F8AA kvkk_retention doctrine'larının kardeşi: shared stress bearer'a
dokunmadan TOTP enrollment lifecycle'ı baştan sona test eder, brute-force
boundary'yi (TWOFA_VERIFY_IP 15/60s) doğrular, same-window TOTP replay
guard'ını (Bug CB `consumed_totp` unique index) ve challenge_token
single-use kuralını (Bug AS `consumed_jtis`) regression-test eder, P0
cross-tenant IDOR matrisi kurar.

Suite baseline `73 → 74 spec`. Full-suite verification bir sonraki turdur
(Workflows kapalı, e2e CI sandbox'ta runnable değil).

## Kapsam

### Lifecycle (A-H)
- **Setup:** pilot baseline + module probe (GET `/api/2fa/status`) +
  status snapshot. Probe 403/404/0 → module-blocked + P2 + skip; 2FA
  already enabled (önceki run residue) → P1 + hard fail (secret elde
  değil, manuel operator cleanup gerekir).
- **A) `/setup`:** pending secret (≥16 chars base32) + otpauth URI
  (`otpauth://` prefix) + QR data URL (`data:image/`) shape kontratı.
  Sonra `/status` ile `pending_setup=true` + `enabled=false` doğrulanır.
- **B) `/setup/confirm`:** wrong code `000000` → 400/401 zorunlu (2xx =
  P0, "zero-knowledge enrollment bypass"). Correct code → `enabled=true`
  + `backup_codes.length ≥ 8`. `twofaEnabled=true` flag açılır,
  `usedConfirmCode` saklanır (same-window collision avoidance için).
- **C) `/auth/login` → `/auth/2fa/verify`:** Fresh login → `requires_2fa=true`
  + `challenge_token` + `access_token=""` (yoksa P0, "2FA enforcement
  bypass"). Verify happy-path → `access_token` issued. Aynı challenge
  ikinci verify → 4xx zorunlu (2xx = P0, "consumed_jtis unique index
  regression"). Verify response token-leak guard.
- **D) Brute-force boundary:** 17 invalid burst (`111111`) → ≥1× 429
  zorunlu. Threshold endpoint-scoped (TWOFA_VERIFY_IP, sadece
  `/api/auth/2fa/verify`), bleed yok; 60s pencere doğal expire eder,
  ek sleep yok. 17 deneme = 15+2 → minimum 2 tane 429 görülmeli; tek
  bir 429 bulamazsa P0 ("brute-force surface açık, 1M code space ~5dk").
- **E) Backup code single-use:** İlk backup code ile fresh login →
  challenge → `/2fa/verify`. Backend backup'ı /verify path'inde kabul
  ediyorsa → ikinci fresh login + aynı code → 4xx zorunlu (2xx = P0,
  "single-use bozuk"). Kabul etmiyorsa (401) → P2 REVIEW (informational;
  single-use guard /disable + /regenerate path'lerinde
  `consume_backup_code` hash-pop pattern üzerinden, bu spec onları
  ayrıca test ediyor; backup code ASLA "consumed" sayılmaz, leak yok).
- **F) `/regenerate-backup-codes`:** wrong `000000` → 4xx (2xx = P0).
  Correct TOTP → ≥8 yeni code. Aynı code ile anında ikinci /regenerate
  → 4xx zorunlu (2xx = P0 = Bug CB `consumed_totp` unique index
  regression). Yeni backup codes afterAll cleanup fallback için saklanır.
- **G) Policy + P0 IDOR matrix:** `/policy` GET + pilot bearer ile
  /status read + setup/disable/regenerate mutate (bogus password +
  `000000` code). Endpoints `current_user`-scoped — pilot kendi state'ini
  görür/etkiler, stress user state'ini ASLA etkilemez. Invariant:
  `(enabled_before, backup_remaining_before) == (enabled_after,
  backup_remaining_after)` stress user için; ihlal = P0 cross-user
  tampering. Ek hard-fail: `expect(pilotDisable.status).toBeGreaterThanOrEqual(400)`
  + `expect(pilotRegen.status).toBeGreaterThanOrEqual(400)` (bogus
  creds için 2xx = P0 IDOR-class auth-bypass).
- **H) Disable cleanup + final invariants:** Stress user'da next 30s
  TOTP slot ile `/disable` çağrısı (primary cleanup path, suite
  raporunda PASS olarak görünür). pilot_drift=0 + external_calls=[]
  final assert.

### afterAll fallback
Test H başarısız olursa veya test başka bir adımda çökerse `afterAll`
tetiklenir: stress_token + password + secret ile birkaç TOTP window
(now, now+30, now+60, now-30) dener, hâlâ açıksa **backup code** ile
disable etmeyi dener. CRITICAL: 2FA enabled bırakılırsa stress admin'in
bir sonraki login'i `requires_2fa: true` döner ve paylaşılan bearer
refresh path'i (globalSetup) çöker → tüm full-suite başarısız.

### TOTP üretimi (client-side)
Self-contained `node:crypto` HMAC-SHA1 + base32 decode helper (`totpAt`
/ `currentTotp`); pyotp/otplib dependency YOK. `/setup` response'unun
`secret` field'ı plaintext (manual fallback) — bu spec onu doğrudan
TOTP üretimi için kullanır. Confirm + Regen aynı 30s window'unda
collision olmasın diye `usedConfirmCode == currentTotp(secret)` ise
sonraki slot'a kadar (≤31s) sleep eder.

## Mutlak invariantlar (her test'te)
- `failedTests = 0`
- `FAIL adım = 0`
- `P0 = P1 = 0`
- `external_calls = []` (her batch sonunda `assertNoExternalCallsPostBatch`)
- `pilot_drift = 0` (H'de `assertPilotDriftZero` final)
- cleanup idempotent (afterAll best-effort fallback)
- shared stress bearer ASLA logout/refresh edilmez

## Backend değişiklikleri
- `backend/domains/admin/router/stress.py` — `STRESS_COLLECTIONS` listesine
  `consumed_totp` eklendi (orphan-scrub forward-compat safety net;
  Mongo TTL 180s ile auto-clean, backend writes `stress_seed`/`stress_prefix`
  tag konvansiyonunu uygulamıyor → entry observability-only, cleanup
  no-op).

Gerçek backend bug YAKALANMADI — 2FA surface'ı F8U'nun bir parçası olarak
zaten `consumed_jtis` (Bug AS) + `consumed_totp` (Bug CB) + SENSITIVE_AUTH_USER
(Bug CE) + TWOFA_VERIFY_IP (Bug AT companion) ile sertleştirilmişti.
F8AG bu sertleştirmenin regression-guard'ıdır.

## Verification durumu
- Spec dosyası yazıldı ✅
- `STRESS_COLLECTIONS` extended ✅
- Roadmap F8AG section + baseline note güncellendi ✅
- `digitalocean.md` gotcha line eklendi ✅
- **Targeted run + full-suite run BEKLEMEDE** — Workflows kapalı,
  Backend API + Mongo + Redis sandbox'ta çalışmıyor; CI workflow'u
  (`github actions full operational stress suite`) bir sonraki turda
  manual trigger edilecek.

## Bir sonraki adım
1. Republish.
2. Targeted run: `yarn playwright test specs/98C-twofa-totp-lifecycle.spec.js`.
3. Full Operational Stress Suite re-run (74 spec baseline).
4. Architect verdict ≥ GO WITH WATCH.
5. Drill report bu dosyayı güncelle (full-suite green pointer + commit SHA).

## Risk notları
- **2FA cleanup CRITICAL.** Spec sonunda 2FA disabled olmazsa downstream
  tüm stress login'leri patlar. afterAll fallback (backup code) ek
  emniyet ama tek bir başarısızlık penceresi yok — secret/backupCodes
  module scope'ta tutulur, afterAll erişebilir.
- **Throttle window leak.** TWOFA_VERIFY_IP 15/60s **endpoint-scoped**;
  diğer spec'ler `/auth/2fa/verify` çağırmıyor (bunu yalnız F8AG
  kullanıyor) → bleed teknik olarak mümkün değil. SENSITIVE_AUTH_USER
  5/900s ise `/2fa/disable` + `/2fa/regenerate-backup-codes` için
  per-user (`2fadis:` / `2farb:` key prefix) — başarılı çağrıda
  `reset()` edildiği için budget sınırlamaz.
- **Shared bearer impact.** /setup, /setup/confirm, /disable, /regen
  çağrıları shared stress_token kullanır (current_user-scoped, F8U
  fresh-login doctrine'ine UYGUN: logout/refresh dokunulmuyor, sadece
  user state mutate ediliyor → bearer geçerli kalır). Fresh login
  sadece verify/throttle/backup test'leri için (her test kendi
  challenge'ını alır).
