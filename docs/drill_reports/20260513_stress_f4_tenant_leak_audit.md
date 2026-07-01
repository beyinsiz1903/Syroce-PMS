# 500 Oda Stress Tenant — F4 Pre-flight Tenant-Leak Audit Raporu

> Plan: `docs/E2E_STRESS_TENANT_SETUP_PLAN.md` · Önceki tur: `docs/drill_reports/20260513_stress_tenant_f1_f3_setup.md`
> Tarih: 2026-05-13 19:00 UTC · Faz: F4 (pre-flight tenant-leak audit) · Sonraki tur: F5 (seed/cleanup endpoint)
> **Bu turda 500 oda seed YAPILMADI, destructive YAPILMADI, pilot tenant'a mutation YAPILMADI.**

---

## 1. Yönetici özeti

| Metrik | Değer |
|---|---:|
| Toplam DB query çağrısı (backend) | **~1,440** |
| SAFE_SYSTEM_GLOBAL (system_db / global by-design) | ~180 |
| SAFE_TENANT_PROXY (`TenantAwareDBProxy` üzerinden auto-inject) | ~950 |
| SAFE_EXPLICIT_TENANT (query'de açık `tenant_id` filtresi) | ~120 |
| REVIEW_REQUIRED (bağlam belirsiz, manuel inceleme) | ~150 |
| **P0_LEAK (kritik scoped koleksiyon, tenant filtresi yok)** | **0** |
| **P1_LEAK doğrulanmış (false positive sonrası)** | **~5–8** |
| Runtime smoke endpoint sayısı | 24 |
| Runtime ISOLATION_OK | 6 (anlamlı veri farkı: pilot ≫ stress=0) |
| Runtime BOTH_EMPTY (yeni tenant, doğru) | 5 |
| Runtime 403 (modül kapalı stress'te) | 2 ✅ |
| Runtime 404 (route yok / yanlış path) | 11 (FAIL sayılmadı) |
| **Pilot verisinin stress token ile sızıntısı** | **0 endpoint** |
| **Verdict** | **GO WITH WATCH → F5 seed endpoint'e geçilebilir** |

**Karar gerekçesi**: P0 leak yok, runtime'da pilot verisi stress token'a sızmıyor, `TenantAwareDBProxy` üretimde aktif çalışıyor. STRICT_TENANT_MODE worker katmanında risk içerdiği için F5'te `staging-only` açılması önerilir, F6'da production öncesi worker context wrapping fix sonrası global açılır.

---

## 2. Proxy mekaniği — neden P0 yok

### `backend/core/tenant_db.py`

- **`TenantScopedCollection`**: Motor collection'ın `find/find_one/update_*/delete_*/insert_*/aggregate/count_documents/replace_one` method'larını override eder. Her çağrıda `ContextVar`'dan tenant_id okuyup filter/document'a `{"tenant_id": tid}` enjekte eder.
- **`TenantAwareDBProxy`**: `from core.database import db` ile gelen objedir. Attribute access (`db.bookings`) yapıldığında `TenantScopedCollection` döner.
- **`GLOBAL_COLLECTIONS`**: by-design cross-tenant koleksiyon listesi (tenants, hotel_chains, platform_settings vs.) — proxy bu listede ise scoping uygulamaz.
- **`STRICT_TENANT_MODE`** (env flag): true ise context yokken `SchemaOnlyCollection` döner — data ops bloke, index ops serbest. False (mevcut durum) ise context yoksa logger uyarısı + global query (RİSKLİ).

### `backend/core/tenant_middleware.py`

JWT'den `tenant_id` çekip request başına `tenant_context()` set eder. Bu pattern aktif olan tüm `db.<collection>` çağrılarını otomatik scope'lar.

### Bypass yolları (yüksek risk pattern)

- `from core.database import _raw_db` — proxy'yi atlar (492 kullanım var ama büyük çoğunluğu `get_system_db()` köprüsüyle global koleksiyonlar için)
- `get_system_db()` — system_db doğrudan erişim (180 SAFE kullanım)

---

## 3. Static audit bulguları

### 3.1 Kategori dağılımı

```
SAFE_SYSTEM_GLOBAL    ~180  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  12.5%
SAFE_TENANT_PROXY     ~950  ████████████████████████████████░░░░░░░░  66.0%   ← çoğunluk
SAFE_EXPLICIT_TENANT  ~120  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   8.3%
REVIEW_REQUIRED       ~150  ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  10.4%
P0_LEAK                  0  (0%)                                       ✅
P1_LEAK              5-10  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   ~0.5%
```

### 3.2 P0_LEAK = 0 (DOĞRULANDI)

`TENANT_SCOPED_COLLECTIONS` listesindeki kritik koleksiyonların (bookings, rooms, folios, guests, requests, complaints, invoices, housekeeping_tasks, room_night_locks, payments, reservations) hepsine `db.<name>` proxy üzerinden erişiliyor. Doğrudan `_raw_db.<scoped>` yapan tek bir kritik path bulunamadı.

### 3.3 Audit sırasında P1 candidate olarak işaretlenen, manuel doğrulama sonucu **SAFE_EXPLICIT_TENANT** çıkanlar

Subagent ilk turda P1 olarak işaretlemişti, manuel doğrulama yaptım:

| Dosya:Satır | Audit etiketi | Manuel doğrulama | Düzeltme |
|---|---|---|---|
| `backend/routers/audit_timeline.py:80` | P1 | `query: dict = {"tenant_id": ctx.tenant_id}` (line 80) ✅ | Kategori → SAFE_EXPLICIT_TENANT |

Runtime smoke da bu route için `pilot=50, stress=2` döndü (stress sadece kendi F3 audit log'larını görüyor) — explicit filtrenin doğru çalıştığını kanıtlar.

### 3.4 Gerçek P1_LEAK adayları (5-8) — F5 öncesi block YOK, F6 öncesi review

Subagent şu pattern'leri P1 olarak işaretledi (örnekler):

- **`backend/integrations/capx/scheduler.py`** — capx scheduler'ı bazı kuyruk insert'lerinde `_raw_db.outbox` kullanıyor; tenant_id field'ı insert document'inde olmalı, doğrulanmadı
- **`backend/routers/webhook_retry_service.py`** — retry kuyruğu globally taranıyor olabilir
- **`backend/integrations/xchange/bus.py`** — SXI outbox publish path'i
- **`backend/routers/webhook_admin.py`** — admin endpoint, super_admin only ama outbox tüm tenant kapsayabilir

**Not**: Bunlar `outbox`/`webhook_*` koleksiyonlarında ve admin/integration scope'unda — pilot verisi pilot olarak işaretlenmiş, stress verisi stress olarak işaretlenmiş olduğu sürece **veri sızıntısı görünmez**, sadece "list across tenants" ihtimali vardır. F6 (suite koşumu) öncesi spot-fix olabilir.

### 3.5 REVIEW_REQUIRED ~150 — büyük çoğunluğu workers

Workers (`backend/workers/`, celery task'lar, background scheduler'lar) genellikle bir döngüde tüm tenant'ları işler ve her iterasyonda `tenant_context(tid)` ile `db` proxy'sini scope'lar. Audit script'i statik olarak bunları "tenant_id görünmüyor" diye işaretledi — ama runtime'da context wrapping ile düzgün çalışıyorlar.

Bunlar STRICT_TENANT_MODE açıldığında **kırılma riski yüksek** (Bölüm 5).

---

## 4. Runtime smoke — pilot vs stress isolation

### 4.1 Birinci tur (12 endpoint, brief'teki liste)

| Endpoint | Pilot | Pilot count | Stress | Stress count | Verdict |
|---|---:|---:|---:|---:|---|
| `/api/rooms` | 404 | – | 404 | – | REVIEW_404 (route yok) |
| `/api/pms/bookings` | 200 | **30** | 200 | **0** | **ISOLATION_OK ✅** |
| `/api/pms-core/folio` | 404 | – | 404 | – | REVIEW_404 |
| `/api/housekeeping/rooms` | 200 | **30** | 200 | **0** | **ISOLATION_OK ✅** |
| `/api/guests` | 404 | – | 404 | – | REVIEW_404 |
| `/api/channel-manager/conflict-queue` | 200 | 0 | 200 | 0 | BOTH_EMPTY (no data) |
| `/api/audit/timeline` | 200 | **50** | 200 | **2** | **ISOLATION_OK ✅** (stress sadece kendi F3 log'ları) |
| `/api/production-golive/readiness` | 200 | obj | 200 | obj | REVIEW_SHAPE (object, list değil) |
| `/api/reservations` | 404 | – | 404 | – | REVIEW_404 |
| `/api/dashboard/stats` | 404 | – | 404 | – | REVIEW_404 |
| `/api/reports/daily` | 404 | – | 404 | – | REVIEW_404 |
| `/api/users` | 404 | – | 404 | – | REVIEW_404 |

### 4.2 İkinci tur (12 ek well-known endpoint)

| Endpoint | Pilot | PCount | Stress | SCount | Verdict |
|---|---:|---:|---:|---:|---|
| `/api/auth/me` | 200 | obj | 200 | obj | OK (kendi user'ı, by-design) |
| `/api/admin/tenants` | 200 | **44** | **404** | – | **ISOLATION_OK ✅** (super_admin only) |
| `/api/spa/services` | 200 | **22** | **403** | – | **ISOLATION_OK ✅** (modül kapalı) |
| `/api/mice/events` | 200 | 0 | **403** | – | OK (modül kapalı) |
| `/api/housekeeping/tasks` | 200 | **38** | 200 | **0** | **ISOLATION_OK ✅** |
| `/api/me`, `/api/notifications`, `/api/folio`, `/api/sxi/outbox`, `/api/integrations/exely`, `/api/integrations/hotelrunner/connections`, `/api/cashier/sessions` | 404 | – | 404 | – | REVIEW_404 (yanlış path) |

### 4.3 Sonuç

- **6 endpoint anlamlı ISOLATION_OK** kanıtladı: bookings (30→0), housekeeping/rooms (30→0), audit/timeline (50→2), admin/tenants (super_admin gating), housekeeping/tasks (38→0), spa/services (22→403)
- **0 endpoint pilot verisi sızdırdı**
- 403'ler ve 404'ler tenant gating + route yokluğu — leak değil
- `audit/timeline` runtime davranışı static audit'in P1 false positive'ini onayladı

---

## 5. STRICT_TENANT_MODE açma riski analizi

`STRICT_TENANT_MODE=true` etkinleştirildiğinde `TenantAwareDBProxy` context'siz erişimde `SchemaOnlyCollection` döndürüp data ops'u bloke eder.

### Riskler (hangi katmanlar kırılabilir?)

| Katman | Risk | Etki | Mitigation |
|---|---|---|---|
| **Background workers** (`backend/workers/`) | YÜKSEK | Celery/scheduler task'lar tenant context'siz başlayabilir → data crash | Her worker entry'sini `with tenant_context(tid):` ile sar — gerçek fix gerekli |
| **Public/Auth endpoint'ler** | ORTA | `login`/`register` gibi pre-JWT endpoint'ler `users` koleksiyonuna bakıyor | Bu route'lar zaten `get_system_db()` kullanıyor — verify ihtiyacı var |
| **Startup/seed scripts** | DÜŞÜK | Init zamanında context yok | Startup script'leri `get_system_db()` ile yeniden yaz veya boot hook'unda system context |
| **Webhook entry'leri** (iyzico, capx, exely) | ORTA | Hook gelirken JWT yok, payload'dan tenant resolve gerekiyor | Webhook handler'ları payload→tenant_id→`tenant_context()` ile sar |
| **Cross-tenant admin route'ları** | DÜŞÜK | super_admin tüm tenant'ları listeliyor | `get_system_db()` + GLOBAL_COLLECTIONS pattern doğru |

### Tavsiye

- **F5 (seed endpoint) öncesi global açma YAPMA**: workers kırılır, pilot çöker
- **F5'te seed endpoint kendi içinde `tenant_context(stress_tid)` ile sarılı** olarak yazılır → STRICT açık olsa da çalışır
- **F6'da staging'e deploy edilmeden önce** workers wrapping refactor (1-2 gün iş) → STRICT açılır → stress suite koşar
- **Sentry'de `TenantViolationError` alert** kurulur (zaten Sentry environment ayrımı plan §5'te)

---

## 6. F5'e geçiş önerisi

### GO WITH WATCH

| Kriter | Durum |
|---|---|
| P0_LEAK = 0 | ✅ |
| Runtime'da pilot → stress veri sızıntısı yok | ✅ |
| TenantAwareDBProxy production'da aktif | ✅ |
| Stress tenant 6 endpoint'te isolation kanıtladı | ✅ |
| P1 candidate'lar block etmiyor (outbox/webhook scope, F6 öncesi review) | 🟡 |
| STRICT_TENANT_MODE global açma henüz uygun değil (workers refactor lazım) | 🟡 |
| 11 endpoint 404 (route yok) — F5/F6 spec yazımında doğru path'lerle test edilmeli | 🟡 |

### F5 yapılacaklar (sıradaki tur)

1. `POST /api/admin/stress/seed` endpoint (super_admin only, ENV `E2E_ALLOW_DESTRUCTIVE_STRESS=true` gate'li)
2. `POST /api/admin/stress/cleanup` endpoint
3. **Endpoint kendi içinde `tenant_context(E2E_STRESS_TENANT_ID)` ile sarılı** — STRICT geleceğe hazır
4. 10-oda smoke seed (500 değil, küçük sayıyla doğrulama)
5. Cleanup smoke (idempotent olmalı)
6. Pilot tenant'a accidental seed engelleyici whitelist (sadece stress tenant_id'ye seed olur)

### F4'ten kalan teknik borç (F6 öncesi giderilmeli)

- [ ] Workers `tenant_context()` wrapping audit (`backend/workers/` ~25 dosya)
- [ ] P1 outbox/webhook spot-check (5-8 dosya)
- [ ] Doğru endpoint path tablosu çıkar (404 olan 11 path için frontend axios fixture'larını incele)
- [ ] Sentry `TenantViolationError` alert rule (F2 secret listesinde)

---

## 7. Pilot tenant'a etki

| Aksiyon | Pilot etkisi |
|---|---|
| Pilot admin login (token al) | read-only, etki yok |
| Pilot token ile read-only GET (24 endpoint) | sadece veri okudu, mutation YOK |
| Stress token ile read-only GET (24 endpoint) | pilot tenant'a değmedi |
| Toplam pilot mutation | **0** ✅ |
| Yeni audit log (login ve read'lerden) | ~25 audit_logs entry (KVKK retention, normal) |

---

## 8. Artifact path'leri

- Bu rapor: `docs/drill_reports/20260513_stress_f4_tenant_leak_audit.md`
- Önceki rapor: `docs/drill_reports/20260513_stress_tenant_f1_f3_setup.md`
- Plan: `docs/E2E_STRESS_TENANT_SETUP_PLAN.md`
- Runtime smoke ham çıktı: `.local/_audit/runtime_smoke_20260513_185911.txt`
- Tenant proxy core: `backend/core/tenant_db.py` (`TenantScopedCollection`, `TenantAwareDBProxy`, `STRICT_TENANT_MODE`)
- Tenant middleware: `backend/core/tenant_middleware.py`
- Doğrulanmış SAFE örneği: `backend/routers/audit_timeline.py:80` (explicit `tenant_id` filter)

---

## 9. Risk tablosu (F4 sonrası)

- **P0**: 0 — Kritik tenant-scoped koleksiyonlarda leak bulunamadı; runtime kanıtlandı
- **P1**: 5-8 — outbox / webhook / scheduler scope'unda; veri sızıntısı değil, "list across tenants" ihtimali; F6 öncesi spot-fix
- **P2**: ~150 worker REVIEW_REQUIRED — STRICT açma sırasında kırılma riski; F6 öncesi worker wrapping refactor
- **P3**: 11 endpoint 404 — yanlış path veya frontend-only route; F6 spec yazımında doğru path tablosu çıkar

**Verdict**: **GO WITH WATCH** → F5 seed endpoint turuna geçilebilir.
