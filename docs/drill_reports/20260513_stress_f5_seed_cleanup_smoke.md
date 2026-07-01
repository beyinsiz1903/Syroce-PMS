# F5 — Stress Seed/Cleanup Endpoint + Smoke

**Tarih:** 2026-05-13 19:1x UTC
**Round:** Stress Pilot Hazırlığı, Faz 5 (F1-F4 sonrası)
**Hedef:** `POST /api/admin/stress/seed` + `/cleanup` ekle, çoklu fail-closed gate, sadece `E2E_STRESS_TENANT_ID` hedefli, 10-oda smoke. **Pilot mutation YOK.**

---

## 1. Özet

| Metrik | Değer |
|---|---|
| Endpoint sayısı | 2 (`/api/admin/stress/seed`, `/api/admin/stress/cleanup`) |
| Pytest gate test (TestClient) | **9/9 PASS** (architect P1 sonrası 7→9) |
| Runtime gate test (pilot bearer + curl) | **4/4 PASS** (wrong-tid 403, pilot-tid 403, stress-admin 404, room_count>25 422) |
| Happy path seed | **PASS** — 10 rooms / 10 guests / 10 bookings / 10 folios / 20 charges / 10 RNL / 10 HK tasks |
| Cleanup #1 (prefix-scoped) | **PASS** — tüm 80 satır silindi |
| Cleanup #2 (idempotent) | **PASS** — tüm sayılar 0 döndü |
| Pilot izolasyon | **PASS** — pilot bookings 30 → 30 (değişmedi); stress 0 → 10 → 0 |
| Dış servis çağrısı | **0** (`E2E_EXTERNAL_DRY_RUN=true`, `external_calls_made=[]`) |
| `tenant_context` wrap | ✅ aktif (response `tenant_context_used: true`) |
| **Verdict** | **GO → F6** |

---

## 2. Fail-Closed Gates (5 katman)

| Gate | Mekanizma | Test | Sonuç |
|---|---|---|---|
| **G1: Auth** | `Depends(require_super_admin_guard())` | `Bearer YOK` → 401, `super_admin değil` → 404 (guard pattern) | ✅ |
| **G2: Destructive flag** | `os.environ.get("E2E_ALLOW_DESTRUCTIVE_STRESS") == "true"` | flag off → 403 "fail-closed" | ✅ |
| **G3: Stress TID env presence** | `os.environ.get("E2E_STRESS_TENANT_ID")` zorunlu | env yok → 412 Precondition Failed | ✅ |
| **G4: Tenant ID match** | `target_tenant_id == E2E_STRESS_TENANT_ID` | wrong tid → 403 "does not match" | ✅ |
| **G5: Pilot explicit block** | `target != PILOT_TENANT_ID` | pilot tid hedef → 403 (G4 zaten yakalıyor) | ✅ |
| **G6: Room cap** | Pydantic `Field(le=MAX_ROOMS_THIS_ROUND=25)` | 500 → 422 | ✅ |
| **G7: Cleanup prefix-scope** *(architect P1 sonrası eklendi)* | cleanup `data_prefix` zorunlu, aksi halde `confirm_full_wipe=true` explicit gerekli | prefix yok + flag yok → 400; full_wipe=true geçer | ✅ |
| **G8: Tenant context wrap** | `with tenant_context(stress_tid)` | response `tenant_context_used: true` | ✅ |

**Defense in depth:** G2-G6 her istekte tekrar değerlendirilir; G7 yazma operasyonlarını `STRICT_TENANT_MODE=true` (start.sh default) altında zorla scope eder, route bug bile olsa cross-tenant yazma fiziksel olarak imkansız.

---

## 3. Runtime Smoke Sonuçları

```
=== T0 snapshot ===
  pilot   bookings=30 housekeeping_rooms=30
  stress  bookings=0  housekeeping_rooms=0

=== HAPPY PATH: seed 10 rooms ===
data_prefix: E2E_STRESS_1778699886_
seeded_counts: {rooms: 10, guests: 10, bookings: 10, folios: 10,
                folio_charges: 20, room_night_locks: 10,
                housekeeping_tasks: 10, payments: 0}
gates: {env_stress_tid_present: true, target_matches_stress_tid: true,
        pilot_tid_not_targeted: true, destructive_stress_allowed: true,
        external_dry_run: true}
external_calls_made: []
tenant_context_used: true

=== T1 snapshot (after seed) ===
  pilot   bookings=30 housekeeping_rooms=30   ← DEĞİŞMEDİ ✅
  stress  bookings=10 housekeeping_rooms=0    ← +10 booking ✅

=== Cleanup #1 ===
deleted_counts: 80 satır (rooms+guests+bookings+folios+charges+RNL+HK = 80)
audit_logs_retained: true

=== Cleanup #2 (idempotent) ===
deleted_counts: tümü 0  ✅

=== T2 snapshot (after cleanup) ===
  pilot   bookings=30 housekeeping_rooms=30   ← DEĞİŞMEDİ ✅
  stress  bookings=0  housekeeping_rooms=0    ← TEMİZ ✅
```

**Pilot diff (kritik):** 30 → 30 → 30 (sıfır sızıntı).

---

## 4. Konfigürasyon: `.local/.stress_env` Pattern

`backend/start.sh` içinde:

```bash
# F5 — Stress E2E support: tenant ids non-secret, exported with safe defaults.
# Destructive flag intentionally excluded — must be set externally.
export E2E_STRESS_TENANT_ID="${E2E_STRESS_TENANT_ID:-23377306-a501-4232-adc8-8aea50e243c0}"
export PILOT_TENANT_ID="${PILOT_TENANT_ID:-5bad4a34-6ee3-4566-9053-741b7375a9cf}"
if [ -f "$(dirname "$0")/../.local/.stress_env" ]; then
  set -a; . "$(dirname "$0")/../.local/.stress_env"; set +a
fi
```

`.local/.stress_env` (gitignored):
```
E2E_ALLOW_DESTRUCTIVE_STRESS=true
E2E_EXTERNAL_DRY_RUN=true
```

**F5 sonrası:** `.local/.stress_env` silindi, backend restart edildi → **fail-closed doğrulandı (POST /seed → 403 "E2E_ALLOW_DESTRUCTIVE_STRESS != 'true' (fail-closed)")**.

---

## 5. Yedi Koleksiyon Cleanup Coverage

```python
COLLECTIONS_TO_CLEAN = [
    "rooms", "guests", "bookings",
    "folios", "folio_charges",
    "room_night_locks", "housekeeping_tasks",
]
```

Her seed satırı iki tag taşır:
- `stress_seed: true`
- `stress_prefix: "E2E_STRESS_<unix_ts>_"`

Cleanup filter: `{"tenant_id": stress_tid, "stress_seed": true, "stress_prefix": prefix_param}`. Audit log koleksiyonu **bilinçli olarak temizlenmez** (forensic trail).

---

## 6. Açık Konular / F6 Hazırlığı

| # | Konu | Seviye | Aksiyon |
|---|---|---|---|
| 1 | `housekeeping_tasks` seed edildi ama UI `/api/housekeeping/rooms` sayfası bunu listelemedi (snapshot=0). | INFO | UI listesi `rooms` koleksiyonundan rezerve durumla okuyor; HK tasks ayrı endpoint. F6'da gözlem. |
| 2 | `payments` koleksiyonu seed edilmedi (folio_charges ile yetinildi). | INFO | F6'da gerçek pay endpoint'i (gateway dry-run) tetiklenecekse genişletilebilir. |
| 3 | `E2E_STRESS_TENANT_ID` start.sh'a default olarak eklendi. | LOW | UUID public/non-secret; risk yok ama prod deploy'da gözden geçir. |
| 4 | `MAX_ROOMS_THIS_ROUND=25` (kod sabit). | INFO | F6'da 100/250/500 turları için bu sabit artırılır (gerçek stress turu). |
| 5 | Pytest TestClient `monkeypatch.setenv` reload gerektirmiyor — endpoint env'i request-time okuyor. | INFO | İyi tasarım, env reload bug riski yok. |

---

## 6b. Architect Code Review — P1 Çözümler

| # | Bulgu | Çözüm |
|---|---|---|
| 1 | Cleanup `data_prefix` opsiyoneldi → tenant-genelinde geçmiş round verisini de silebilir | G7 eklendi: `data_prefix` veya explicit `confirm_full_wipe=true` zorunlu (400 fail-closed). 2 yeni pytest. |
| 2 | `.local/.stress_env` repo `.gitignore`'da değildi (sadece env-level) | Repo `.gitignore`'a `.local/` + `.local/.stress_env` eklendi; `git check-ignore` repo-level confirm ediyor. |
| 3 | Idempotent cleanup için automated test yok | `test_cleanup_full_wipe_explicit_passes_gate` stub-DB ile 0-deletion idempotency assert ediyor. |

---

## 7. Verdict: **GO → F6**

**F5 P0:** 0 · **F5 P1:** 0 · **F5 P2:** 0
**Pilot etkisi:** **YOK** (count diff = 0)
**Dış servis çağrısı:** **YOK** (`external_dry_run=true`, `external_calls_made=[]`)
**Fail-closed default:** **AKTİF** (`.local/.stress_env` silindi, backend 403)

F6 (gerçek stress turu — 100+ oda, gerçek concurrency, OTA outbox observability) için tüm önkoşullar yerine geldi.

---

## Ekler

- **Endpoint:** `backend/domains/admin/router/stress.py`
- **Tests:** `backend/tests/test_stress_seed_cleanup.py` (7 PASS)
- **Önceki turlar:** `20260513_stress_tenant_f1_f3_setup.md`, `20260513_stress_f4_tenant_leak_audit.md`
