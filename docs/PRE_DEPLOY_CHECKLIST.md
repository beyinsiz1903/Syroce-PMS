# Pre-Deploy Quick Checklist (v107)

Last updated: 24 Apr 2026 — after v106 round-9 closure + v107 P0 mini-batch.

## Sistem Sağlık Özeti

| Bileşen | Durum | Not |
|---------|-------|-----|
| Backend API | ✅ Çalışıyor | port 8000, `Application startup complete`, tüm router'lar yüklü |
| Quick-ID API | ✅ Çalışıyor | port 8099, `/api/health` → 200 |
| Frontend (Vite) | ✅ Render oluyor | landing page sorunsuz açılıyor |
| MongoDB Atlas | ✅ Bağlı | DB: `syroce-pms`, indexes ensured |
| Redis | ✅ Bağlı | localhost:6380, Event Bus REDIS modunda |
| HotelRunner v2 | ✅ Aktif | pull scheduler 180s, push queue 120s, 200 OK |
| Exely | ✅ Aktif | pull scheduler 180s, SOAP 200 OK |
| Night Audit | ✅ Aktif | 60s scheduler |
| ARI Push | ✅ Aktif | HotelRunner + Exely adapters |

## Test Skoru

- ✅ 24/24 güvenlik regression (rebinding 9 + egress guard 3 + production blockers 12)
- ✅ 87/87 pure unit testleri (audit wiring + core lockdown + hardening)
- ⚠ Tests in `battle/test_sprint2_*` ve `test_atomic_checkin_checkout` — fixture infra eksikliği (replica-set MongoDB + live test server). **Pre-existing, regression değil.**

## Kod Kalite

- ✅ `ruff check .` — All checks passed (warning'ler hariç, error 0)
- ✅ Architect round-9 verdict: **PASS — release-ready**

## Production Hardening (Round-7/8'den)

- ✅ JWT_SECRET fail-closed: `STRICT_JWT_SECRET=1` enforced
- ✅ Egress allowlist: 1901 endpoints + 3 SMTP sites + CI guard
- ✅ DNS rebinding: 9 regression test, mixed A-record reject doğrulandı
- ✅ Hardcoded secrets: `infra/production_config.startup_check` 5 known-leaked hash karşı boot-refuse
- ✅ Demo seed gating: `auto_seed` prod'da skip, `ALLOW_AUTO_SEED_IN_PROD=1` opt-in
- ✅ Field encryption, file uploads (Pillow magic-byte), 2FA throttle, idempotency hepsi aktif

## Pre-Deploy Operator Adımları

### 1. Secrets Rotation (kritik)

Production deploy'dan ÖNCE DigitalOcean Secrets vault'tan **mutlaka** rotate edilmeli:

- `JWT_SECRET` — şu an dev/leaked hash listesinde, prod'da boot'u reddeder
- `QUICKID_SERVICE_KEY` — aynı şekilde
- `AFSADAKAT_ADMIN_TOKEN` — aynı şekilde
- `CM_MASTER_KEY_CURRENT` — aynı şekilde
- `HR_TOKEN` — demo HotelRunner token, prod'da gerçek token gerekir

Yöntem: DigitalOcean → Tools → Secrets → her birini sil + yeni `openssl rand -base64 32` ile değer üret.

### 2. Environment Matrix

Production deploy'da bu env'ler tutarlı olmalı:

| Var | Beklenen Değer |
|-----|----------------|
| `APP_ENV` | `production` |
| `ENVIRONMENT` | `production` |
| `NODE_ENV` | `production` |
| `STRICT_JWT_SECRET` | `1` |
| `STRICT_TENANT_MODE` | `1` |
| `ALLOW_AUTO_SEED_IN_PROD` | (boş — açık değil) |
| `CORS_ORIGINS` | gerçek prod domain'leri |
| `RESEND_API_KEY` | ✅ var |
| `RESEND_FROM` | ✅ var |
| `MONGO_URL` | Atlas prod cluster |
| `DB_NAME` | `syroce-pms` |
| `REDIS_URL` | prod Redis (TLS varsa `rediss://`) |

### 3. Önerilen Polish (zorunlu değil)

- `httpx` INFO logger'ı `WARNING`'e çek (query string token leak'i azaltmak için):
  ```python
  logging.getLogger("httpx").setLevel(logging.WARNING)
  ```
- MongoDB Atlas IP allowlist'inde DigitalOcean deployment IP'leri ekli olduğunu doğrula.

### 4. Smoke Test (deploy sonrası)

Production URL üzerinden:

```bash
curl -i https://YOUR-DEPLOY.syroce.com/api/health        # 307 bekleniyor
curl -i https://YOUR-DEPLOY.syroce.com/api/auth/me       # 403 (auth yok)
```

İlk login + dashboard render testi tarayıcıdan yapılmalı.

## Açık (deploy-blocker olmayan) Backlog

- `docs/SECURITY_HARDENING_BACKLOG.md` — ~97 defense-in-depth tenant-pin closure (P0: 19, P1: ~40, P2: 9, P3: 6). Hiçbiri bilinen exploit değil; kademeli temizlik.
- `tests/battle/test_sprint2_*` fixture infrastructure (test ortamı için replica-set MongoDB).

## Sonuç

🟢 **Production'a yayınlamaya hazır.** Yukarıdaki Secrets Rotation adımı operatör tarafından yapılınca `Publish` → `Deploy` ile canlıya alınabilir.
