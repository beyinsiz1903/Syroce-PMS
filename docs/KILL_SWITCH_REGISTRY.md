# Kill-Switch / Feature Flag Registry

**Audience:** pilot operator, on-call engineer, security review.
**Updated:** 12 May 2026 (Production Safety #6).
**Helper:** `backend/infra/feature_flags.py` (`is_enabled`, `is_disabled`, `production_guard`, `snapshot`).

---

## §0 — 30 saniyede ne öğrenmeliyim?

- **Kill-switch nedir?** Bir özelliği koddaki yerinden değil, env-var'dan
  kapatma. Operatör Replit Secrets vault'undan flip eder, restart ile
  uygulanır (60s'de canlı).
- **Naming standardı:** `ENABLE_*` opt-in (default OFF, fail-closed) /
  `DISABLE_*` opt-out (default ON). Production guard'lı `DISABLE_*`
  switch'ler production'da YOKSAYILIR (sadece dev/test/sandbox).
- **Acil durum:** "Bir şeyi kapatmam lazım" → §3 envanter; flag'i Replit
  Secrets'a ekle, ilgili workflow'u restart et, `/api/production-golive/readiness`
  ile doğrula.

---

## §1 — Standart (yeni kill-switch eklerken)

### 1.1 Parsing

Tüm kill-switch okumaları `backend/infra/feature_flags.py` üzerinden geçer:

```python
from infra.feature_flags import is_enabled, is_disabled, production_guard

# Opt-in feature (default OFF):
if is_enabled("ENABLE_QUICKID_DEMO"):
    ...

# Opt-out feature (default ON):
if is_disabled("DISABLE_EXPO_PUSH"):
    return  # push devre dışı

# Security guard (DISABLE_* but ignored in production):
if production_guard("DISABLE_AUTH_THROTTLE"):
    return  # throttle bypass — sadece dev/test/sandbox
```

Truthy tokens: `1`, `true`, `yes`, `on`, `y`, `t` (case-insensitive,
stripped). Diğer her şey → falsy. Bilinmeyen token → WARNING log + default.

### 1.2 Naming

| Ön ek         | Anlam                                   | Default | Use case                              |
|---------------|-----------------------------------------|---------|---------------------------------------|
| `ENABLE_*`    | Opt-in özellik (fail-closed)            | OFF     | Demo modlar, setup endpoint'leri      |
| `DISABLE_*`   | Opt-out özellik (kapatma switch'i)      | ON      | Expo push, OTA push, audit            |
| `DISABLE_*` + `production_guard` | Güvenlik bypass'ı (prod'da yoksayılır) | ON | Auth throttle, tenant guard, rate limit |

**Yasak naming:** `FEATURE_*`, `FLAG_*`, `USE_*`, `TURN_OFF_*`, `BYPASS_*` —
hep `ENABLE_*` veya `DISABLE_*` kullan. Mevcut tutarlılık önemli.

### 1.3 Default fail-closed

- **Yeni güvenlik özelliği:** `ENABLE_*` koy, default OFF, açıkça aç.
- **Mevcut güvenlik kontrolü:** `DISABLE_*` koy + `production_guard` —
  prod'da bypass'lanamasın.
- **Yeni iş özelliği:** `ENABLE_*` ile kademeli rollout (canary).

### 1.4 Registry'e ekle

`backend/infra/feature_flags.py` içindeki `KNOWN_FLAGS` tuple'ına satır ekle:

```python
KNOWN_FLAGS = (
    ...
    ("DISABLE_OUTBOX_DISPATCHER", "disable", False),
)
```

Aynı PR'da bu doc §3'e satır ekle. Kod ↔ doc lock-step.

### 1.5 Audit log

İlk okumada (genelde modül import'unda) bir INFO log düşür:

```python
if is_disabled("DISABLE_EXPO_PUSH"):
    logger.info("kill_switch.active flag=DISABLE_EXPO_PUSH")
```

`feature_flags.py` per-call WARNING üretmez (gürültü olur); sadece
production_guard leak'i veya bilinmeyen token için WARNING basar.

---

## §2 — Operatör akışı (kill-switch çekme)

```
1. Sorunu tespit et   → SystemHealthDashboard / Sentry / Slack alarmı
2. Doğru flag'i seç   → §3 envanter (etkisi + side-effect kolonları)
3. Replit Secrets'a   → Workspace → Tools → Secrets → New Secret
   "DISABLE_X" = "1"
4. Workflow restart   → ilgili workflow'u tek-tık restart (Backend API)
5. Doğrula            → curl /api/production-golive/readiness
                        → checks.kill_switches.flags[].active==true mi?
                        → SystemHealthDashboard "Pilot Production Safety" §
6. Geri açma          → Secret'ı sil veya "0" yap, restart
```

**Kural:** ASLA terminal'den `export DISABLE_X=1` yapma — Replit workflow
restart'ında kaybolur. SADECE Secrets vault.

---

## §3 — Envanter (mevcut 5 kill-switch — wire'lı)

Tüm flag'ler `feature_flags.snapshot()` ile programatik okunabilir.

### 3.1 `ENABLE_QUICKID_DEMO` (opt-in)

| Alan          | Değer                                                       |
|---------------|-------------------------------------------------------------|
| Kind          | `enable` (default OFF)                                      |
| Wire noktası  | `backend/routers/quick_id_proxy.py:32`                      |
| Etki          | Quick-ID demo mod (gerçek QuickID servisi yerine fake data) |
| Pilot kullanım| **KAPALI** — pilot'ta gerçek Quick-ID servis kullanılır     |
| Açma süresi   | Anında (modül import'unda okunur, restart gerekli)          |
| Side-effect   | Demo data prod DB'ye yazılır → ASLA prod'da açma            |

### 3.2 `ENABLE_SETUP_ENDPOINTS` (opt-in)

| Alan          | Değer                                                       |
|---------------|-------------------------------------------------------------|
| Kind          | `enable` (default OFF)                                      |
| Wire noktası  | `backend/routers/auth.py:134`                               |
| Etki          | İlk-kurulum endpoint'lerini açar (POST /auth/setup/*)       |
| Pilot kullanım| **KAPALI** — pilot tenant ilk-kurulumu deploy öncesi yapıldı|
| Açma süresi   | Anında (her request'te okunur)                              |
| Side-effect   | Açıkken `SETUP_SECRET` mutlaka set olmalı (yoksa 503)       |

### 3.3 `ENABLE_LEGACY_SECRET_FALLBACK` (opt-in, default ON)

| Alan          | Değer                                                       |
|---------------|-------------------------------------------------------------|
| Kind          | `enable` (default **ON** — istisna)                         |
| Wire noktası  | `backend/controlplane/security_ops_router.py:126` (display) |
| Etki          | Vault provider başarısız olursa env-var'dan secret oku      |
| Pilot kullanım| AÇIK — Replit Secrets vault güvenilir, yine de fallback iyi |
| Açma süresi   | Anında (her secret read'inde okunur)                        |
| Side-effect   | KAPATMA: vault outage'ında auth/payment/CM kırılır          |

### 3.4 `DISABLE_EXPO_PUSH` (opt-out)

| Alan          | Değer                                                       |
|---------------|-------------------------------------------------------------|
| Kind          | `disable` (default OFF — push aktif)                        |
| Wire noktası  | `backend/services/expo_push.py:60`                          |
| Etki          | Mobil push notification gönderme tamamen susar              |
| Pilot kullanım| Operatör isterse panik anında kapatabilir (push spam)       |
| Açma süresi   | Anında (her gönderim öncesi okunur, restart gerekmez)       |
| Side-effect   | VIP welcome / housekeeping alert / shift handover sessiz    |

### 3.5 `DISABLE_AUTH_THROTTLE` (production-guarded)

| Alan          | Değer                                                       |
|---------------|-------------------------------------------------------------|
| Kind          | `guard` (default OFF — throttle aktif)                      |
| Wire noktası  | `backend/security/auth_throttle.py:161`                     |
| Etki          | Login/refresh/setup throttle bypass (test için)             |
| Pilot kullanım| **KAPALI** — pilot prod, prod guard zaten yoksayar          |
| Açma süresi   | Anında (her check'te okunur)                                |
| Side-effect   | Prod'da set edilse bile YOKSAYILIR + WARNING log            |

---

## §4 — Önerilen yeni kill-switch'ler (DEFER, wire EDİLMEDİ)

Pilot operatöre faydalı olur ama bu turda wire etmedik (scope creep,
runtime side-effect testi gerekir). Hangi kullanım senaryosunda
gerekirse o turda eklenir:

| Aday flag                     | Wire noktası (öneri)                          | Senaryo                                                           |
|-------------------------------|-----------------------------------------------|-------------------------------------------------------------------|
| `DISABLE_OUTBOX_DISPATCHER`   | `backend/workers/outbox_dispatcher.py`        | OTA provider tüm-pazar outage; CM dispatcher'ı durdur, queue biriksin |
| `DISABLE_CM_PUSH`             | `backend/channel_manager/services/event_sync_service.py` | Tek connector outage dışında full CM push'u kes                   |
| `DISABLE_NIGHT_AUDIT`         | `backend/workers/night_audit_worker.py`       | Audit batch hata veriyor, manuel müdahale öncesi otomatiği durdur |
| `DISABLE_AI_UPSELL`           | `backend/domains/ai/router.py`                | AI sağlayıcı (OpenAI) outage; upsell endpoint'leri sus            |
| `DISABLE_PUBLIC_BOOKING`      | `backend/domains/public_booking/router.py`    | DDoS / spam; public booking page'i 503'e döndür                   |
| `DISABLE_KVKK_PHOTO_ALERTS`   | `backend/services/kvkk_photo_alert.py`        | Pilot ilk gün alarm spam'i kontrol altında olsun                  |

**Kural:** Yeni flag eklerken §1.4 (KNOWN_FLAGS güncelle) + bu doc'a satır
ekle. PR review sırasında "neden bu kill-switch?" sorusu cevaplanmalı —
gereksiz flag operasyonel yük.

---

## §5 — Programmatik snapshot (admin UI / readiness)

```python
from infra.feature_flags import snapshot
print(snapshot())
# {
#   "flags": [
#     {"name": "ENABLE_QUICKID_DEMO", "kind": "enable", "active": false,
#      "default": false, "requested": false},
#     ...
#   ],
#   "active_count": 1,    # şu an non-default state'de olan flag sayısı
#   "non_default_count": 1,
# }
```

**Privacy:** snapshot ASLA raw env value döndürmez — sadece flag adı
(zaten public, registry'de doc'lu) + boolean state. Tenant_id veya
secret içermez.

`requested != active` farkı: production_guard'lı flag set edilmiş ama
prod'da yoksayılmış demektir → operatör leak'i fark eder.

**Wire önerisi (DEFER):** `readiness_validator.py` 12. check'i:
```python
checks["kill_switches"] = feature_flags.snapshot()
```
Wire edilirse SystemHealthDashboard'a yeni KpiCard "Kill-Switches"
eklenebilir (active_count > 0 → warning intent).

---

## §6 — Çapraz-link

- **Genel pilot ops:** `docs/REPLIT_OPS_CHEATSHEET.md`
- **24h izleme:** `docs/PILOT_FIRST_24H_MONITORING.md`
- **Sentry alert routing:** `docs/SENTRY_ALERT_POLICY.md` (kill-switch
  flip'leri Sentry'ye INFO event olarak düşmeli — ileri tur)
- **Production safety planı:** `docs/PRODUCTION_SAFETY_PLAN.md` (#6)
- **Rollback runbook:** `docs/ROLLBACK.md` (kill-switch yetersiz kalırsa
  rollback)
