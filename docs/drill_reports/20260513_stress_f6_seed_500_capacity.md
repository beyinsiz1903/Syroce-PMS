# F6 — Stress Seed Extension, 500-Room Capacity Smoke

**Tarih:** 2026-05-13
**Tur:** F6 (kapsam: backend seed/cleanup motorunun 500 odaya genişletilmesi + 25→100→250→500 basamaklı doğrulama)
**Kaynak:** `docs/E2E_STRESS_TENANT_SETUP_PLAN.md` · F1-F5 raporları
**Stress Tenant:** `23377306-a501-4232-adc8-8aea50e243c0`
**Pilot Tenant (target_blocked):** `5bad4a34-6ee3-4566-9053-741b7375a9cf`

---

## 1) Yönetici Özeti

| Kriter | Sonuç |
| --- | --- |
| 25 / 100 / 250 / 500 oda seed | **4/4 PASS** |
| 25 / 100 / 250 / 500 oda cleanup | **4/4 PASS** |
| Cleanup idempotent (her basamakta 2. çağrı) | **4/4 PASS** |
| Pilot tenant mutation (`bookings`) | **0 / 0 / 0 / 0** (baseline 30 → final 30) |
| `external_calls_made` her cevapta | **`[]`** |
| `tenant_context_used` her cevapta | **`true`** |
| Fail-closed gates (4 reddetme + env miss) | **5/5 PASS** |
| Pytest (toplam 11 test) | **11/11 PASS** (3.83s) |
| Backend ERROR / BulkWriteError / Sentry | **0** (fix sonrası) |
| Audit log koruması (`audit_logs_retained`) | **true** (her cleanup) |

**Final verdict: GO → F7 (Stress E2E Scaffold)**

Toplam motor performansı (500 oda, full round-trip):
- Seed (factory + chunked insert_many ×7 koleksiyon): **9.08 s**
- Cleanup (prefix-scoped delete_many ×8 koleksiyon): **1.87 s**
- Idempotent cleanup #2: ~0.6 s (boş silme)

---

## 2) Gate Sonuçları

`_gates()` fail-closed yığını + Pydantic Field doğrulamaları:

| Gate | Trigger | Beklenen | Sonuç |
| --- | --- | --- | --- |
| `target_tenant_id != E2E_STRESS_TENANT_ID` | `target_tenant_id="not-it"` | 403 | **PASS** |
| Pilot tenant explicitly blocked | `target_tenant_id=<pilot_tid>` | 403 | **PASS** |
| `E2E_ALLOW_DESTRUCTIVE_STRESS != "true"` | env unset | 403 | **PASS** |
| `E2E_STRESS_TENANT_ID` env missing | env unset | 412 | **PASS** |
| `room_count > MAX_ROOMS_THIS_ROUND` | `room_count=600` | 422 (`Input should be less than or equal to 500`) | **PASS** |
| Cleanup unbounded (no prefix, no `confirm_full_wipe`) | bare body | 400 | **PASS** |

`gates` dict her başarılı response'ta:
```json
{ "env_stress_tid_present": true,
  "target_matches_stress_tid": true,
  "pilot_tid_not_targeted": true,
  "destructive_stress_allowed": true,
  "external_dry_run": true }
```

---

## 3) Basamak Tablosu

### 3a) Seed Counts × Timing

| n | rooms | guests | bookings | folios | charges | rnl | hk | factory_ms | insert_ms | total_ms |
| --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| 25  | 25  | 25  | 25  | 25  | 86   | 61   | 25  | 1.8  | 1195.4 | 1197.2 |
| 100 | 100 | 100 | 100 | 100 | 350  | 250  | 100 | 7.8  | 2564.9 | 2572.7 |
| 250 | 250 | 250 | 250 | 250 | 873  | 623  | 250 | 15.6 | 5090.7 | 5106.3 |
| 500 | 500 | 500 | 500 | 500 | 1750 | 1250 | 500 | 32.4 | 9046.2 | 9078.6 |

**Beklenen vs gözlenen sayım doğrulaması (500 oda):**

| Koleksiyon | Beklenen | Gözlenen | Açıklama |
| --- | --: | --: | --- |
| rooms / guests / bookings / folios / hk | 500 | 500 | 1:1 |
| `room_night_locks` (RNL) | 1250 | 1250 | sum(stay_nights cycle 1..4 × 500) = 125·(1+2+3+4) = 1250 ✓ |
| `folio_charges` | 1750 | 1750 | RNL (1250 per-night room charge) + 500 acc-tax = 1750 ✓ |

### 3b) Cleanup × Idempotency × Pilot Diff

| n | cleanup_total | cleanup_ms | idempotent #2 | pilot bookings (before/after_seed/after_clean) | diff |
| --: | --: | --: | :--: | :---: | :--: |
| 25  | 272  | 1213.7 | **PASS** | 30 / 30 / 30 | **0** |
| 100 | 1100 | 1356.3 | **PASS** | 30 / 30 / 30 | **0** |
| 250 | 2746 | 1505.3 | **PASS** | 30 / 30 / 30 | **0** |
| 500 | 5500 | 1870.5 | **PASS** | 30 / 30 / 30 | **0** |

`audit_logs_retained=true` her response'ta ✓; `audit_logs` koleksiyonu hiç dokunulmadı.

---

## 4) Variety Axes (F6 factory genişletmesi)

`_build_factory_docs()` her oda için aşağıdaki çeşitliliği dağıtır:

| Eksen | Değer |
| --- | --- |
| `room_type` | 20 tip (standard, deluxe, junior_suite, …, accessible) |
| `block` | 5 (A-E) |
| `floor` | 10 (1-10) |
| `room_number` formatı | `{prefix}{block}{floor:02d}{i:03d}` |
| `vip_status` | her 7'inci misafir |
| `late_checkout_requested` | her 11'inci |
| `allergy` (`preferences.allergy_notes`) | her 13'üncü |
| `accessibility_needed` | her 17'inci VEYA `room_type=="accessible"` |
| `stay_nights` | döngü 1..4 (RNL fan-out aynı sayıda) |
| `base_price` | 800 + (i % 20) · 50 → 800..1750 ₺ |
| `capacity` | 2 + (i % 3) → 2..4 |
| `priority` (HK) | `high` (VIP), `normal` (diğer) |

500-oda response içindeki `variety` raporu:
```json
{ "room_types": 20, "blocks": 5, "floors": 10,
  "vip_modulo": 7, "late_checkout_modulo": 11,
  "allergy_modulo": 13, "accessibility_modulo": 17,
  "stay_nights_cycle": "1..4" }
```

---

## 5) Performans Notları

- **Insert:** Chunked `insert_many` (`INSERT_CHUNK_SIZE=100`, `ordered=False`).
  500-oda toplam yazılı doc sayısı = 500+500+500+500+1750+1250+500 = **5,500 doc / 9.05 s ≈ 608 doc/s** Atlas üzerinden, tek-bağlantı.
- **Cleanup:** 8 koleksiyon × `delete_many({stress_seed:true, stress_prefix:<p>})`; 5,500 doc / 1.87 s ≈ 2,941 doc/s (delete_many BulkOps tek round-trip).
- **Memory:** Faktöri her basamakta linear; 500 oda peak in-process = ~2.0 MB doc listesi (göz tarafından).
- **Atlas observability:** `[WARNING] observability.middleware: SLOW REQUEST` yalnızca 500-oda seed'inde 9 s eşiğini aştı (kabul edilebilir, seed bir admin operasyonu). Diğer normal pilot trafiği bundan etkilenmedi.

---

## 6) Pilot Before/After Diff & Stress Before/After

### 6a) Pilot tenant — full round (4 basamak)

| Snapshot | bookings (pilot) | rooms | guests |
| --- | --: | --: | --: |
| Baseline | 30 | (pilot rooms unchanged) | (unchanged) |
| 25-seed sonrası | 30 | unchanged | unchanged |
| 100-seed sonrası | 30 | unchanged | unchanged |
| 250-seed sonrası | 30 | unchanged | unchanged |
| 500-seed sonrası | 30 | unchanged | unchanged |
| Final (500 cleanup sonrası) | 30 | unchanged | unchanged |

**Pilot mutation = 0** — `tenant_context(stress_tid)` + tagged-row cleanup ikisi birlikte çalışıyor.

### 6b) Stress tenant — son cleanup sonrası
Pre-clean stragglers (önceki F6-debug round'larından): `rooms=2 guests=2 bookings=2 folios=2 rnl=2 charges=5 hk=0`.
Final (500 round cleanup sonrası): all stress collections @ 0 — **wipe complete**.

---

## 7) External Calls / Outbox / Sentry Gözlemi

| Gözlem | Durum |
| --- | --- |
| `external_calls_made` her response'ta | **`[]`** |
| Payment / OTA push / SMS / email / KVKK çağrısı | **0** |
| Outbox events (stress prefix) | **0** (seed/cleanup hiçbir domain event yayınlamıyor) |
| Sentry capture (yeni) | **0** (loglarda `Sentry initialized` dışında stress kaynaklı capture yok) |
| Backend `ERROR` lines (fix sonrası) | **0** |
| Tenant violation (`TenantAwareDBProxy`) | **0** |

---

## 8) Test Pass Matrix

`pytest backend/tests/test_stress_seed_cleanup.py -v` (11 / 11 PASS, 3.83s):

| Test | Durum |
| --- | --- |
| `test_seed_rejects_wrong_tenant_id` | PASS |
| `test_seed_rejects_pilot_tenant_id` | PASS |
| `test_seed_rejects_when_destructive_flag_off` | PASS |
| `test_seed_rejects_when_stress_tid_env_missing` | PASS |
| `test_seed_accepts_room_count_at_cap` (F6 yeni, n=500) | PASS |
| `test_seed_rejects_room_count_above_cap` (F6, n=501→422) | PASS |
| `test_seed_factory_counts_at_25` (F6 yeni) | PASS |
| `test_cleanup_rejects_wrong_tenant_id` | PASS |
| `test_cleanup_rejects_when_destructive_flag_off` | PASS |
| `test_cleanup_rejects_unbounded_delete_without_prefix` | PASS |
| `test_cleanup_full_wipe_explicit_passes_gate` | PASS |

---

## 9) Bulgular ve Severity

### P0 — Blocker
**0 bulgu.**

### P1 — High
**0 bulgu.**

### P2 — Medium
**0 bulgu.**

### P3 — Observation / debt

1. **F6-debug-1 (FIXED bu turda) — `room_night_locks` `night_date` field-name mismatch.**
   F5 seed kodu `stay_date` kullanıyordu; Atlas'taki UNIQUE index `ux_room_night = (tenant_id, room_id, night_date)`. n=2'den itibaren tüm RNL doc'larında `night_date=null` olduğu için 2. insert duplicate-null nedeniyle BulkWriteError veriyordu. Düzeltildi: doc artık her üç field'ı (`night_date`, `date`, `stay_date`) yazıyor. Sonuç: F5 küçük (n=10) round'larda hiç tetiklenmemiş bir gizli buga; F6 progressive smoke ortaya çıkardı.
   - `idx_rnl_tenant_date_room` da `date` field'ını okuyor, ikisini birlikte set etmek doğru.

2. **Single-thread Atlas insert throughput.** 500 oda / 9 s tek-bağlantıda makul; F7 stress E2E suite'i paralel tarayıcı session'larıyla çalışırken seed/cleanup ihtiyacı tek admin operasyonu olarak kalmalı (paralel seed gerekirse `asyncio.gather` ile koleksiyon-başına paralelize edilebilir, P2 backlog).

3. **Cleanup koleksiyon listesi `payments`'i içeriyor ama factory `payments` üretmiyor.** Bu intentional (advance-payment senaryolarında F7'de eklenebilir); cleanup tarafı 0 silmesi normal.

4. **`MAX_ROOMS_THIS_ROUND` artık 500.** Bunu `2000`'e çıkarmak Atlas Tier'a göre seed'i ~36 s'a uzatabilir. F7 sadece 500 ile koşulacak; daha büyüğü ayrı tur.

### Eylem
P0/P1/P2 yok → **action item: yok**. P3'ler bilgi amaçlı backlog.

---

## 10) F7 Stress E2E Scaffold'a Geçilebilir mi?

**Evet — F7'ye geçişe açık.** Backend motoru:
- 500 odayı tek POST'ta ~9 s içinde seed ediyor,
- prefix-scoped cleanup ~1.9 s'de geri alıyor,
- pilot izolasyonu hala 0 mutation,
- external IO sıfır,
- fail-closed gates intakt,
- 11 pytest koruyucu testi yeşil.

F7 önerilen kapsam:
- Playwright "stress" project'i (yeni `playwright.stress.config.js`, `frontend/e2e-stress/`).
- Globalsetup'da `POST /api/admin/stress/seed` (n=500) → suite çalışır → globalteardown'da prefix cleanup.
- 4-6 paralel worker × yüksek-volume okuma akışları (front-desk grid render, calendar paint, HK liste, RNL availability).
- Pilot tenant'ı **read-only allowlist** ile izole, stress tenant'a yazma yapan akışlar `STRESS_TID` bearer'ıyla.
- Outbox sayacı her test başında snapshot → testte +0 increment beklenecek (fail-closed dış servis).

---

## 11) Kapanış (Sandbox)

- `.local/.stress_env` F6 koşumu sonrasında **silindi**.
- Backend restart sonrası `POST /api/admin/stress/seed` → **403 "E2E_ALLOW_DESTRUCTIVE_STRESS != 'true' (fail-closed)"** doğrulandı.
- F6 deliverable'ları: yenilenmiş `backend/domains/admin/router/stress.py` (variety + chunked + timing + 500 cap), 11 pytest, runtime smoke 4/4, bu rapor.
- **Final verdict: GO → F7.**
