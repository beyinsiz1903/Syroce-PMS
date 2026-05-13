# 500 Oda Stress Tenant — F1-F3 Setup Raporu

> Plan referansı: `docs/E2E_STRESS_TENANT_SETUP_PLAN.md`
> Tarih: 2026-05-13 18:31 UTC
> Faz: F1 (pattern finalizasyonu) + F2 (secret checklist) + F3 (tenant create + admin login)
> Sonraki tur: F4 (pre-flight tenant-leak audit)
> **Bu turda 500 oda seed YAPILMADI, hiçbir destructive stress koşulmadı.**

---

## 1. Yönetici özeti

| Metrik | Değer |
|---|---|
| F1 Pattern finalizasyonu | ✅ Pattern A (aynı Atlas + ayrı tenant_id) |
| F2 Secret readiness | 🟡 6 var, 5 manuel set gerekli, 3 backend env (restart gerekli) |
| F3 Tenant create | ✅ tenant_id=`23377306-a501-4232-adc8-8aea50e243c0` |
| F3 Admin user create | ✅ user_id=`a5eeaa5f-8104-4f0a-a804-b5164ea0cfe5`, role=`admin` |
| F3 Yeni admin login | ✅ JWT 324-char token alındı |
| Cross-tenant isolation smoke | ✅ Stress tenant `GET /api/rooms` → count=0 (pilot odaları sızmadı) |
| **Verdict** | **F1-F3 GO → F4 tenant-leak audit'e geçilebilir** |

**Pilot tenant'a sıfır mutasyon yapıldı**: tek API çağrısı `POST /api/admin/tenants` (system_db.tenants ve system_db.users insert), pilot tenant'ın hiçbir scoped koleksiyonuna dokunulmadı.

---

## 2. F1 — Pattern A finalizasyonu

**Karar**: Pattern A (aynı Atlas cluster + ayrı `tenant_id` + STRICT_TENANT_MODE).

Gerekçe (kullanıcı kararı):
- Maliyet sıfır (mevcut Atlas cluster, ayrı M10 yok).
- Hızlı kurulum (~saat değil, dakika).
- `TenantScopedCollection` (`backend/core/tenant_db.py:48`) zaten her query'e `{tenant_id: ...}` enjekte ediyor — STRICT mode + pre-flight audit ile ekstra güvenlik katmanı.
- Sentry tag-based ayrım yeterli (ayrı project gerekmiyor).

**Risk**: Pre-flight tenant-leak audit (F4) yapılmadan stress koşulamaz. Plan §6'daki `rg` script'i F4'te koşacak.

---

## 3. F2 — Secret readiness tablosu

### 3.1 Mevcut secret'lar (kullanılacak — yeni iş yok)

| Secret | Kaynak | Durum | Kullanım |
|---|---|---|---|
| `MONGO_ATLAS_URI` | mevcut | ✅ | Aynı cluster, Pattern A |
| `JWT_SECRET` | mevcut | ✅ | Tüm tenant'lar için ortak imza key'i |
| `RESEND_API_KEY` | mevcut | ✅ | Stress'te `EXTERNAL_DRY_RUN` ile bypass |
| `RESEND_FROM` | mevcut | ✅ | Aynı |
| `VITE_SENTRY_DSN` | mevcut | ✅ | Tag-based env ayrımı |
| `E2E_BASE_URL` / `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` | mevcut (process env) | ✅ | F3 tenant create için pilot admin token alındı |

### 3.2 F3'te oluşturulan, manuel Replit secret olarak eklenmesi gerekenler

| Secret | Değer | Hassasiyet | Nereye |
|---|---|---|---|
| `E2E_STRESS_TENANT_ID` | `23377306-a501-4232-adc8-8aea50e243c0` | düşük | Suite env'i |
| `E2E_STRESS_HOTEL_ID` | (response'ta dönmedi — Mongo'dan çekilmeli) | düşük | Suite env'i |
| `E2E_STRESS_TENANT_NAME` | `E2E Stress 500-Room Hotel` | düşük | Display |
| `E2E_STRESS_ADMIN_EMAIL` | `stress-admin@e2e-stress.example.com` | düşük | Login |
| `E2E_STRESS_ADMIN_PASSWORD` | (28-char güçlü random — `.local/stress_tenant_credentials.txt`) | **YÜKSEK** | Login |

> **Önemli**: Şifre + tenant ID `.local/stress_tenant_credentials.txt` dosyasında saklı (gitignored). Bu turdan sonra **kullanıcı manuel olarak** Replit Secrets UI'sından bu 5 değeri ekleyecek. Agent secret yazma yetkisini kullanmadı çünkü değerler zaten dosyada hazır ve user kontrolünde olmalı.

### 3.3 Suite-time env'leri (CI/local `.env` ya da Replit secrets, kullanıcı tercihine göre)

| Env | Değer | Anlam |
|---|---|---|
| `E2E_ALLOW_DESTRUCTIVE_STRESS` | `false` (F1-F3 sonrası `true` yapılacak) | Brief gate #3 |
| `E2E_EXTERNAL_DRY_RUN` | `true` | Brief gate #4 |
| `E2E_ROOM_COUNT` | `500` | Seed boyutu |
| `E2E_OCCUPANCY_RATE` | `1.0` | Active stay yüzdesi |
| `E2E_PAYMENT_SANDBOX_REQUIRED` | `true` | Suite-içi guard |
| `E2E_OTA_DRY_RUN_REQUIRED` | `true` | Suite-içi guard |
| `E2E_SMS_MOCK_REQUIRED` | `true` | Suite-içi guard |
| `E2E_EMAIL_MOCK_REQUIRED` | `true` | Suite-içi guard |
| `E2E_KVKK_MOCK_REQUIRED` | `true` | Suite-içi guard |

### 3.4 Backend restart gerektiren env'ler (F4 öncesi karar)

| Env | Değer | Etki | Karar |
|---|---|---|---|
| `STRICT_TENANT_MODE` | `true` | Tenant context'siz scoped DB erişimi → `TenantViolationError` | **F4 audit ÖNCESİNDE açılmalı** — leak'leri görünür yapar |
| `SENTRY_ENVIRONMENT` | mevcut → `pilot` (zaten set) | Stress run'da `stress` override | Suite koşumu sırasında subprocess env override |
| `ENABLE_SETUP_ENDPOINTS` | `0` (kapalı) | Setup endpoint açıcı | **AÇILMAYACAK** — F3'te kanıtlandı: `POST /api/admin/tenants` super_admin token ile çalışıyor, setup endpoint'lere ihtiyaç yok |
| `SETUP_SECRET` | — | Setup endpoint koruması | Gereksiz |
| `ROOM_QR_SECRET` | missing_secrets'te | QR guest request bölümü | F7-F8 (Bölüm 6 spec'i öncesi) |
| `PUBLIC_APP_URL` | missing_secrets'te | QR + mail link | F7-F8 |

**STRICT_TENANT_MODE notu**: Bu env true yapılınca pilot tenant da etkilenir. Eğer pilot kodda tenant context göndermeden çalışan bir admin route varsa (F4'te bulunacak) o route 500 dönebilir. Bu yüzden F4 audit **STRICT_TENANT_MODE off** durumda yapılır, audit raporu temizlenir, sonra true'ya geçilir.

---

## 4. F3 — Tenant create + admin login (gerçek aksiyon)

### 4.1 Pilot admin login (super_admin doğrulaması)

```
POST $E2E_BASE_URL/api/auth/login (E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD)
→ 200, JWT token alındı (324 char)

GET /api/auth/me
→ 200, role=super_admin ✅ (tenant create yetkisi onaylandı)
   pilot tenant_id=5bad4a34-6ee3-4566-9053-741b7375a9cf
```

### 4.2 İlk deneme — `.local` TLD reddedildi

```
POST /api/admin/tenants {email: "stress-admin@e2e.local", ...}
→ 422 value_error: "The part after the @-sign is a special-use or reserved name"
```

**Düzeltme**: `e2e-stress.example.com` (RFC 2606 reserved-for-documentation TLD, validator kabul ediyor).

### 4.3 Başarılı tenant create

```
POST /api/admin/tenants
Authorization: Bearer <pilot super_admin token>
Body:
{
  "property_name": "E2E Stress 500-Room Hotel",
  "email": "stress-admin@e2e-stress.example.com",
  "password": "<28-char random, secrets.choice generated>",
  "name": "Stress Admin",
  "phone": "+900000000000",
  "property_type": "city_hotel",
  "total_rooms": 500,
  "subscription_tier": "enterprise",
  "address": "E2E Stress Test (no real address)",
  "location": "stress-test",
  "description": "Isolated tenant for 500-room stress E2E suite"
}

Response 200:
{
  "success": true,
  "message": "Hotel created successfully",
  "tenant_id": "23377306-a501-4232-adc8-8aea50e243c0",
  "user_id": "a5eeaa5f-8104-4f0a-a804-b5164ea0cfe5",
  "subscription_start": "2026-05-13T18:31:10.800557+00:00",
  "subscription_end": "Unlimited",
  "subscription_days": "Unlimited"
}
```

### 4.4 Yeni admin login doğrulaması

```
POST /api/auth/login (stress-admin@e2e-stress.example.com / <pwd>)
→ 200, JWT 324-char ✅

GET /api/auth/me
→ 200
   id: a5eeaa5f-8104-4f0a-a804-b5164ea0cfe5
   tenant_id: 23377306-a501-4232-adc8-8aea50e243c0  (pilot'tan FARKLI ✅)
   email: stress-admin@e2e-stress.example.com
   role: admin
   is_active: true
   email_verified: false  (önemli değil, login engellemiyor)
```

### 4.5 Cross-tenant isolation smoke

```
GET /api/rooms (Authorization: Bearer <stress admin token>)
→ 200, rooms count=0 ✅
```

Pilot tenant'ta gerçek odalar var; stress admin token ile çekildiğinde **0 oda** dönüyor — `TenantScopedCollection` proxy doğru çalışıyor, otomatik `{tenant_id: "23377306-..."}` filtresi enjekte edildi. Cross-tenant sızıntı yok.

---

## 5. Pilot tenant'a etki

| Aksiyon | Pilot etkisi |
|---|---|
| Pilot admin login | read-only token alma — etki yok |
| `POST /api/admin/tenants` | **system_db.tenants + system_db.users insert** (cross-tenant koleksiyonlar — by-design global) |
| Pilot scoped koleksiyonlara dokunma | **YOK** — hiçbir `bookings`/`rooms`/`folios`/`guests`/`audit_logs` write |
| Pilot tenant kullanıcı sayısı | Değişmedi |
| Pilot tenant modules/settings | Değişmedi |

Doğrulama önerisi (kullanıcı opsiyonel kontrol için):
```
GET /api/admin/tenants  (super_admin)
→ Listede şimdi 2 tenant olmalı: pilot (5bad4a34...) + stress (23377306...)
```

---

## 6. Test verileri envanteri

| Koleksiyon | Yaratılan | Cleanup yapılabilir mi |
|---|---:|---|
| `system_db.tenants` | 1 (stress tenant) | Evet — `delete_one({_id: "23377306-..."})` super_admin ile |
| `system_db.users` | 1 (stress admin) | Evet — `delete_one({_id: "a5eeaa5f-..."})` |
| Stress tenant scoped koleksiyonlar | 0 | — (boş) |
| `audit_logs` | 1-2 (tenant create + login) | KVKK/audit retention — silinmez (fake data, sorun değil) |

Stress tenant'ı tamamen rollback etmek isterseniz: 2 silme ve 2 audit log kalır (zarar yok, fake data).

---

## 7. F4 — Tenant-leak audit komut listesi (sonraki tur)

Plan §6'daki audit script'i, pre-flight olarak F4 turunda koşturulacak:

```bash
# 1. Tüm Mongo query'lerini topla
rg "\.find\(|\.find_one\(|\.update_one\(|\.update_many\(|\.delete_many\(|\.delete_one\(|\.insert_one\(|\.insert_many\(|\.aggregate\(|\.count_documents\(|\.replace_one\(" \
   backend/ --type=py -n > /tmp/_db_queries.txt
wc -l /tmp/_db_queries.txt

# 2. system_db kullanımları (cross-tenant by-design — OK)
grep -c "get_system_db\|sys_db\.\|system_db\." /tmp/_db_queries.txt

# 3. Proxy üzerinden olanlar (auto-inject — OK)
#    `from core.database import db` veya `db = await get_db()` üzerinden geliyorsa otomatik tenant_id ekleniyor.

# 4. Kalanlar — manuel review
grep -v "system_db\|sys_db\|get_system_db" /tmp/_db_queries.txt > /tmp/_potential_leaks.txt
wc -l /tmp/_potential_leaks.txt

# 5. STRICT_TENANT_MODE=true ile entegrasyon test
#    Her route'a hem pilot hem stress token ile aynı GET request gönder, count'lar farklı/sıfır olmalı.
#    Bu işin spec versiyonu F4-audit'in çıktısı olur.

# 6. Audit raporu: docs/drill_reports/YYYYMMDD_stress_f4_tenant_leak_audit.md
#    - Toplam query sayısı
#    - system_db (OK) sayısı
#    - Auto-inject proxy (OK) sayısı
#    - Manuel review gereken sayısı
#    - P0/P1/P2 leak listesi (dosya:satır)
#    - Fix önerileri
```

**F4 kabul kriteri**:
- 0 P0 leak (kritik scoped koleksiyonda tenant_id'siz query)
- ≤ 5 P1 leak (audit_log/log koleksiyonunda tenant_id'siz query)
- Tüm P2/P3'ler dokümante

P0 bulgu çıkarsa **F4'te düzeltme yapılır, F5'e (seed endpoint) geçilmez**.

---

## 8. Sonraki adımlar (F4 → F10)

| Faz | İş | Tahmini süre | Çıktı |
|---|---|---:|---|
| **F4** | Tenant-leak audit + STRICT_TENANT_MODE switch | 2-3 saat | Audit raporu, kalan leak fix |
| **F5** | `POST /api/admin/stress/seed` + `/cleanup` endpoint + 10-oda smoke | 2-3 saat | API hazır |
| **F6** | `backend/seed/stress/` extension (rooms_500, guests_500, bookings_500, folios_500) | 3-4 saat | 500-oda seed çalışıyor |
| **F7** | `frontend/e2e-stress/` scaffold + `00-gates.spec` + `01-bulk-seed.spec` | 2-3 saat | İlk 2 spec PASS |
| **F8** | Bölüm 2-11 spec implementation | 8-12 saat | 11 spec hazır |
| **F9** | İlk full koşum + konsolide rapor | 1-2 saat | `docs/drill_reports/YYYYMMDD_500room_full_operational_stress.md` |
| **F10** | Triyaj + iyileştirme + ikinci koşum | değişken | Final verdict |

Toplam kalan: ~18-27 saat (F4-F10).

---

## 9. Kullanıcı için aksiyon listesi (F4 öncesi)

1. ✅ Plan §11 karar noktaları yanıtlandı (Pattern A, Sentry tag-based, dış servisler dry-run, F1-F3 → F4 sırası)
2. ⏳ `.local/stress_tenant_credentials.txt` dosyasını gözden geçirip **5 stress secret'ı** Replit Secrets UI'sına ekle (F7'de suite koşumu öncesi gerekli, F4 için zorunlu değil)
3. ⏳ F4 turunu açtığında: agent tenant-leak audit'i çalıştırır, raporu dropper, varsa P0/P1 fix önerileri sunar
4. ⏳ STRICT_TENANT_MODE=true backend restart kararı F4 audit sonrası verilir (P0 yoksa açılır)

---

## 10. Artifact path'leri

- Plan: `docs/E2E_STRESS_TENANT_SETUP_PLAN.md` (önceki tur)
- Bu rapor: `docs/drill_reports/20260513_stress_tenant_f1_f3_setup.md`
- Stress tenant credentials (gitignored): `.local/stress_tenant_credentials.txt`
- Tenant create endpoint: `backend/domains/admin/router/tenants.py:466` (`POST /admin/tenants`)
- Tenant scoping proxy: `backend/core/tenant_db.py:169` (`TenantScopedCollection`)
- Tenant middleware: `backend/core/tenant_middleware.py:42`

---

## 11. Risk sınıflandırması (F1-F3 sonrası)

- **P0**: 0 — F3 hiçbir destructive aksiyon yapmadı, sadece system_db'ye 2 insert
- **P1**: 0
- **P2**: 1 — `email_verified=false` stress admin için; bazı flow'lar (örn. invitation/2FA setup) bunu istiyor olabilir, F8'de spec yazarken karşılaşılırsa email-verify endpoint'i çağırılır veya seed sırasında flag set edilir
- **P3**: 1 — `HOTEL_ID` response'ta dönmüyor (sadece tenant_id ve user_id); F4 öncesi Mongo'dan tek query ile çekilebilir, kritik değil

**Verdict: F1-F3 GO** — F4 tenant-leak audit turu açılabilir.
