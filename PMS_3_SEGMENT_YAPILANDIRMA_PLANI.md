# 🏨 PMS 3-SEGMENT YENİDEN YAPILANDIRMA PLANI
## Uygulanabilir Teknik Adımlar + Öncelik Sıralaması

**Tarih:** Temmuz 2025  
**Hedef:** Basic → hızlı müşteri kazanımı, Professional → 6-12 ay, Enterprise → paralel  
**Mevcut Altyapı:** Multi-tenant, MODULE_DEFAULTS, get_tenant_modules(), AdminTenants.js

---

## 1. SEGMENT TANIMLARI VE HEDEF KULLANICI PROFİLLERİ

### 1.1 Segment Tablosu

| Boyut | 🟢 BASIC (1-15 oda) | 🔵 PROFESSIONAL (15-80 oda) | 🟣 ENTERPRISE (80+ / zincir) |
|-------|---------------------|----------------------------|------------------------------|
| **Hedef** | Pansiyon, butik, apart otel | Şehir oteli, tatil köyü, 3-4★ | 5★, zincir, resort |
| **Kullanıcı** | Otel sahibi (tek kişi) | GM + 3-5 departman müdürü | 20+ çok departmanlı ekip |
| **IT Bilgisi** | Düşük (Excel'den geçiş) | Orta (PMS deneyimi var) | Yüksek (IT departmanı) |
| **Personel** | 1-5 kişi | 10-40 kişi | 50-500+ kişi |
| **Bütçe** | 79-149€/ay | 249-499€/ay | 799€+/ay (custom) |
| **Karar Süreci** | 1-2 hafta, self-service | 2-4 hafta, demo gerekir | 3-12 ay, RFP/POC |
| **Onboarding** | 30dk self-service wizard | 1-2 gün guided setup | 2-6 ay implementation |
| **Max Oda** | 15 | 80 | Sınırsız |
| **Max Kullanıcı** | 3 | 15 | Sınırsız |
| **Destek** | Email + chat | Öncelikli email + telefon | 7/24 dedicated AM |

### 1.2 Kritik İhtiyaçlar

| İhtiyaç | BASIC | PROFESSIONAL | ENTERPRISE |
|---------|-------|-------------|------------|
| Hızlı rezervasyon girişi | 🔴 Kritik | 🔴 Kritik | 🔴 Kritik |
| Takvim görünümü | 🔴 Kritik | 🔴 Kritik | 🔴 Kritik |
| OTA senkronizasyonu | 🟡 2-3 kanal | 🔴 10+ kanal | 🔴 50+ kanal + GDS |
| Basit check-in/out | 🔴 Kritik | 🔴 Kritik | 🔴 Kritik |
| Fiyat yönetimi | 🟡 Basit | 🔴 Rate plans | 🔴 Dynamic + AI |
| Raporlama | 🟡 Günlük özet | 🔴 Detaylı | 🔴 USALI + Custom BI |
| Grup rezervasyon | ❌ | 🟡 Temel | 🔴 Full MICE |
| Multi-property | ❌ | ❌ | 🔴 Kritik |
| Revenue management | ❌ | 🟡 Temel | 🔴 AI-powered |
| Folio management | ❌ | 🔴 Full | 🔴 Advanced routing |
| Loyalty program | ❌ | ❌ | 🟡 Tier-based |
| API access | ❌ | ❌ | 🔴 Open API |
| Night audit | ❌ | 🔴 Kritik | 🔴 Kritik |
| RBAC (çoklu rol) | ❌ (sadece admin) | 🔴 5-6 rol | 🔴 15+ granüler rol |
| Audit trail | ❌ | 🟡 Temel | 🔴 Full compliance |

---

## 2. FEATURE GATING MATRİSİ

### 2.1 Modül → Plan Eşleştirme Tablosu

| Modül Anahtarı | Modül Adı | BASIC | PROFESSIONAL | ENTERPRISE | Kategori |
|----------------|-----------|-------|-------------|------------|----------|
| `pms` | PMS Core (Rez, Check-in/out, Oda) | ✅ | ✅ | ✅ | CORE |
| `reservation_calendar` | Rezervasyon Takvimi | ✅ | ✅ | ✅ | CORE |
| `dashboard` | Dashboard | ✅ | ✅ | ✅ | CORE |
| `guests` | Misafir Yönetimi (Temel) | ✅ | ✅ | ✅ | CORE |
| `settings` | Ayarlar | ✅ | ✅ | ✅ | CORE |
| `basic_reporting` | Temel Raporlar (doluluk, gelir) | ✅ | ✅ | ✅ | CORE |
| `housekeeping` | Kat Hizmetleri (Temel) | ✅ | ✅ | ✅ | CORE |
| `pms_mobile` | PMS Mobil Erişim | ✅ | ✅ | ✅ | CORE |
| `invoices_basic` | Basit Fatura (PDF) | ✅ | ✅ | ✅ | CORE |
| --- | --- | --- | --- | --- | --- |
| `channel_manager` | Channel Manager (OTA sync) | ❌ | ✅ | ✅ | PRO |
| `folio_management` | Folio Yönetimi (split, routing) | ❌ | ✅ | ✅ | PRO |
| `night_audit` | Gece Denetimi | ❌ | ✅ | ✅ | PRO |
| `invoices` | Gelişmiş Fatura & Finans | ❌ | ✅ | ✅ | PRO |
| `cost_management` | Maliyet Yönetimi | ❌ | ✅ | ✅ | PRO |
| `reports` | Gelişmiş Raporlar | ❌ | ✅ | ✅ | PRO |
| `mobile_housekeeping` | Mobil Housekeeping (task mgmt) | ❌ | ✅ | ✅ | PRO |
| `rate_management` | Rate Plan Yönetimi | ❌ | ✅ | ✅ | PRO |
| `booking_engine` | Direkt Rezervasyon Motoru | ❌ | ✅ (add-on) | ✅ | PRO |
| `guest_advanced` | Gelişmiş Misafir Profili (VIP) | ❌ | ✅ | ✅ | PRO |
| --- | --- | --- | --- | --- | --- |
| `revenue_management` | Revenue Management (RMS) | ❌ | ❌ | ✅ | ENTERPRISE |
| `multi_property` | Çoklu Otel Yönetimi | ❌ | ❌ | ✅ | ENTERPRISE |
| `group_sales` | Grup Satış & MICE | ❌ | ❌ | ✅ | ENTERPRISE |
| `sales_crm` | Satış CRM & Pipeline | ❌ | ❌ | ✅ | ENTERPRISE |
| `loyalty_program` | Sadakat Programı | ❌ | ❌ | ✅ | ENTERPRISE |
| `gm_dashboards` | GM & Executive Dashboard | ❌ | ❌ | ✅ | ENTERPRISE |
| `mobile_revenue` | Mobil Revenue | ❌ | ❌ | ✅ | ENTERPRISE |
| `advanced_analytics` | Gelişmiş Analitik (BI) | ❌ | ❌ | ✅ | ENTERPRISE |
| `api_access` | API Erişimi (webhook, 3rd party) | ❌ | ❌ | ✅ | ENTERPRISE |
| `white_label` | White Label (özel branding) | ❌ | ❌ | ✅ | ENTERPRISE |
| `audit_trail` | Audit Trail (compliance) | ❌ | ❌ | ✅ | ENTERPRISE |
| --- | --- | --- | --- | --- | --- |
| `ai` | AI Genel Anahtar | ❌ | ❌ | ✅ (add-on tüm planlara) | AI |
| `ai_chatbot` | AI Chatbot | ❌ | ❌ | ✅ | AI |
| `ai_pricing` | AI Dynamic Pricing | ❌ | ❌ | ✅ | AI |
| `ai_whatsapp` | AI WhatsApp Concierge | ❌ | ❌ | ✅ | AI |
| `ai_predictive` | AI Tahminler | ❌ | ❌ | ✅ | AI |
| `ai_reputation` | AI Reputation | ❌ | ❌ | ✅ | AI |
| `ai_revenue_autopilot` | AI Revenue Autopilot | ❌ | ❌ | ✅ | AI |
| `ai_social_radar` | AI Social Radar | ❌ | ❌ | ✅ | AI |

### 2.2 Core Modüller (Tüm Planlarda)

Her otel, planı ne olursa olsun, aşağıdaki modülleri kullanabilir:
- PMS Core (rezervasyon, check-in/out, oda yönetimi)
- Rezervasyon Takvimi (drag & drop)
- Dashboard (basitleştirilmiş)
- Misafir Yönetimi (temel)
- Kat Hizmetleri (temel)
- Temel Raporlar (günlük doluluk + gelir)
- Ayarlar
- Mobil PMS Erişimi
- Basit Fatura (PDF)

### 2.3 Sadece Enterprise'a Gizli Kalacak Özellikler

Bu özellikler Professional ve Basic kullanıcılarına **hiç gösterilmez** (menüde bile yer almaz):
1. Multi-Property Dashboard
2. AI Modülleri (tümü)
3. Revenue Management (RMS)
4. Grup Satış & MICE
5. Satış CRM
6. Loyalty Program
7. GM Executive Dashboard
8. API Access / Webhook
9. White Label
10. Advanced Analytics / BI

---

## 3. TEKNİK DÜZENLEME ÖNERİLERİ

### 3.1 Backend Değişiklikleri

| # | Değişiklik | Dosya | Öncelik | Efor |
|---|-----------|-------|---------|------|
| 1 | Subscription tier'ları 3'e düşür (Basic/Professional/Enterprise) | `subscription_models.py` | 🔴 P0 | 1 saat |
| 2 | `MODULE_DEFAULTS`'ı genişlet (yeni modül anahtarları) | `server.py` | 🔴 P0 | 30dk |
| 3 | `PLAN_MODULE_MAP` oluştur (plan → default modüller) | `subscription_models.py` | 🔴 P0 | 1 saat |
| 4 | Tenant oluşturulurken plan'a göre default modüller set et | `server.py` (create_tenant) | 🔴 P0 | 30dk |
| 5 | `/admin/tenants/{id}/plan` - plan değiştirme endpoint'i | `server.py` | 🟡 P1 | 1 saat |
| 6 | RBAC basitleştirme: Basic → sadece ADMIN rolü | `server.py` | 🟡 P1 | 2 saat |
| 7 | Multi-property endpoint'lerine Enterprise guard ekle | `server.py` | 🟡 P1 | 1 saat |
| 8 | Rapor endpoint'lerini plan bazlı ayır | `server.py` | 🟢 P2 | 2 saat |

### 3.2 Frontend Değişiklikleri

| # | Değişiklik | Dosya | Öncelik | Efor |
|---|-----------|-------|---------|------|
| 1 | AdminTenants.js'ye plan seçimi ekle (Basic/Pro/Enterprise) | `AdminTenants.js` | 🔴 P0 | 2 saat |
| 2 | Plan değişince default modülleri otomatik set et | `AdminTenants.js` | 🔴 P0 | 1 saat |
| 3 | NavItems'ı plan bazlı filtrele | `navItems.js` | 🔴 P0 | 1 saat |
| 4 | Basic kullanıcı için sadeleştirilmiş sidebar | `Layout.js` | 🟡 P1 | 2 saat |
| 5 | Upgrade teşvik banner'ları (kilitli modüller) | Yeni component | 🟢 P2 | 2 saat |
| 6 | Plan bazlı dashboard widget'ları | `Dashboard.js` | 🟢 P2 | 2 saat |

### 3.3 RBAC Sadeleştirme

| Plan | Kullanılabilir Roller | Açıklama |
|------|----------------------|----------|
| **BASIC** | `admin` | Tek kullanıcı, tüm temel yetkiler |
| **PROFESSIONAL** | `admin`, `supervisor`, `front_desk`, `housekeeping`, `finance` | 5 departman rolü |
| **ENTERPRISE** | Tüm roller (15+) + custom roller | Granüler izinler |

---

## 4. UX DÜZENLEME PLANI

### 4.1 Progressive Disclosure Stratejisi

```
BASIC Kullanıcı:
┌──────────────────────────────────┐
│ Sidebar (5 öğe)                  │
│ ├── 📊 Dashboard                 │
│ ├── 📅 Takvim                    │
│ ├── 🏨 PMS                      │
│ ├── 📋 Raporlar (basit)         │
│ └── ⚙️ Ayarlar                  │
│                                  │
│ [🔒 Pro'ya yükselt - daha fazla │
│  özellik için]                   │
└──────────────────────────────────┘

PROFESSIONAL Kullanıcı:
┌──────────────────────────────────┐
│ Sidebar (10 öğe)                 │
│ ├── 📊 Dashboard                 │
│ ├── 📅 Takvim                    │
│ ├── 🏨 PMS                      │
│ ├── 🧹 Housekeeping             │
│ ├── 📋 Raporlar (gelişmiş)      │
│ ├── 💰 Fatura & Finans          │
│ ├── 📡 Channel Manager          │
│ ├── 💵 Maliyet Yönetimi         │
│ ├── 🌙 Night Audit              │
│ └── ⚙️ Ayarlar                  │
│                                  │
│ [🔒 Enterprise - AI, RMS, CRM]  │
└──────────────────────────────────┘

ENTERPRISE Kullanıcı:
┌──────────────────────────────────┐
│ Sidebar (15+ öğe)               │
│ ├── 📊 Dashboard                 │
│ ├── 📅 Takvim                    │
│ ├── 🏨 PMS                      │
│ ├── 🧹 Housekeeping             │
│ ├── 📋 Raporlar (full)          │
│ ├── 💰 Fatura & Finans          │
│ ├── 📡 Channel Manager          │
│ ├── 💵 Maliyet Yönetimi         │
│ ├── 🌙 Night Audit              │
│ ├── 📈 Revenue Management       │
│ ├── 🤖 AI Modülleri             │
│ ├── 👥 Grup Satış               │
│ ├── 💼 Satış CRM                │
│ ├── 🎁 Loyalty                  │
│ ├── 🏢 Multi-Property           │
│ └── ⚙️ Ayarlar                  │
└──────────────────────────────────┘
```

### 4.2 Plan Bazlı UX Kuralları

| UX Öğesi | BASIC | PROFESSIONAL | ENTERPRISE |
|----------|-------|-------------|------------|
| Sidebar öğe sayısı | 5 | 10 | 15+ |
| Rezervasyon formu | 5 alan (basit) | 12 alan (detaylı) | 20+ alan (full) |
| Dashboard | 4 KPI kartı | 8 KPI + grafikler | Full executive dashboard |
| Menü derinliği | 1 seviye | 2 seviye (alt menüler) | 3 seviye (mega menü) |
| Kısayol tuşları | ❌ | Temel (F2, F5) | Full keyboard shortcuts |
| Toplu işlemler | ❌ | Temel | Full batch operations |
| Export formatları | PDF | PDF + Excel | PDF + Excel + API |
| Tema/branding | Standart | Standart | Özelleştirilebilir |

---

## 5. FİYATLANDIRMA YAPISI

### 5.1 Ana Plan Tablosu

| | 🟢 BASIC | 🔵 PROFESSIONAL | 🟣 ENTERPRISE |
|--|----------|-----------------|---------------|
| **Aylık** | **79€/ay** | **299€/ay** | **799€/ay** (başlangıç) |
| **Yıllık** | **790€/yıl** (2 ay ücretsiz) | **2.990€/yıl** | **Custom** |
| **Oda Limiti** | 15 oda | 80 oda | Sınırsız |
| **Kullanıcı** | 3 | 15 | Sınırsız |
| **Ek oda ücreti** | +5€/oda/ay | +3€/oda/ay | Toplu anlaşma |
| **Destek** | Email (iş saati) | Öncelikli email + telefon | 7/24 dedicated |
| **Onboarding** | Self-service | Guided (1 seans) | Full implementation |
| **SLA** | %99 | %99.5 | %99.9 |

### 5.2 Add-on Modüller

| Add-on | Fiyat | Uygun Plan | Açıklama |
|--------|-------|-----------|----------|
| AI Paket (tümü) | +149€/ay | Pro + Enterprise | Chatbot, pricing, prediction |
| Booking Engine | +49€/ay | Pro + Enterprise | Direkt rezervasyon motoru |
| Channel Manager | +79€/ay | Basic (add-on) | Sadece Basic'e add-on |
| Advanced Analytics | +99€/ay | Pro + Enterprise | BI dashboard'lar |
| WhatsApp Business | +49€/ay | Pro + Enterprise | Otomatik mesajlaşma |
| White Label | +199€/ay | Enterprise only | Özel branding |

### 5.3 Fiyatlandırma Modeli Kararı

**Önerilen: Hibrit Model (Sabit + Oda Bazlı)**

- **Sabit baz fiyat** (plana göre) → minimum garanti gelir
- **Oda bazlı ek ücret** (limit aşımında) → büyüme ile orantılı
- **Add-on modüller** → isteğe bağlı gelir artışı

Bu model, Basic müşteriyi düşük fiyatla çekerken, büyüdükçe otomatik olarak Professional'a yönlendirir.

---

## 6. RİSK ANALİZİ

### 6.1 Feature Bloat Riski

| Risk | Olasılık | Etki | Mitigation |
|------|----------|------|-----------|
| Basic kullanıcı "çok basit" bulur | %30 | Orta | Temel modüller yeterli kapsamda olmalı |
| Enterprise kullanıcı "yeterli değil" bulur | %20 | Yüksek | Mevcut 85+ modül zaten güçlü |
| Modül sayısı yönetilemez hale gelir | %40 | Yüksek | Modül grupları ile organize et |
| Add-on karmaşası (ne almalıyım?) | %50 | Orta | Max 5-6 add-on tut |

**Önlem:** Modülleri GRUPLAR halinde yönet (PMS, Finance, AI, Revenue...), tek tek değil.

### 6.2 Kod Karmaşıklığı Riski

| Risk | Olasılık | Etki | Mitigation |
|------|----------|------|-----------|
| `if plan == basic` her yere yayılır | %60 | Yüksek | Feature flag pattern + `require_module()` middleware |
| Test coverage düşer | %40 | Yüksek | Plan bazlı test senaryoları |
| UI kod tekrarı (3 farklı sidebar) | %30 | Orta | Tek component + conditional rendering |
| Backend endpoint'leri planla çelişir | %20 | Orta | Middleware-level gating (mevcut `require_module`) |

**Önlem:** Mevcut `require_module()` middleware'i zaten doğru pattern'ı kullanıyor. Bunu genişletmek yeterli.

### 6.3 Test Yükü Riski

| Risk | Olasılık | Etki | Mitigation |
|------|----------|------|-----------|
| Her planı ayrı test etmek gerekir | %80 | Yüksek | Parametrized test suite |
| Module toggle kombinasyonları patlama yapar | %50 | Orta | Default presets + override test |
| Regression risk artar | %60 | Yüksek | CI/CD pipeline + smoke tests |

**Önlem:** 3 test tenant oluştur (basic_test, pro_test, enterprise_test), her release'de smoke test.

---

## 7. ÖNCELİK SIRALI UYGULAMA PLANI

### Faz 1: Altyapı (Hemen) 🔴 P0

| # | Adım | Dosya | Test |
|---|------|-------|------|
| 1.1 | `subscription_models.py`'yi 3 tier'a düzenle | `subscription_models.py` | Unit test |
| 1.2 | `MODULE_DEFAULTS`'ı genişlet | `server.py` | Backend API test |
| 1.3 | `PLAN_MODULE_DEFAULTS` map oluştur | `subscription_models.py` | Unit test |
| 1.4 | Admin: Plan seçimi + modül toggle | `AdminTenants.js` | Frontend test |
| 1.5 | Admin: Plan değişince default modüller set et | Backend + Frontend | E2E test |

### Faz 2: Frontend Gating (1-2 hafta) 🟡 P1

| # | Adım | Dosya | Test |
|---|------|-------|------|
| 2.1 | navItems'ı modül bazlı filtrele | `navItems.js` + `Layout.js` | Visual test |
| 2.2 | Plan bazlı sidebar sadeleştirme | `Layout.js` | Visual test |
| 2.3 | Kilitli modül upgrade banner'ları | Yeni component | Visual test |

### Faz 3: Detay Düzenlemeleri (2-4 hafta) 🟢 P2

| # | Adım | Dosya | Test |
|---|------|-------|------|
| 3.1 | RBAC plan bazlı sınırlama | `server.py` | Backend test |
| 3.2 | Rapor endpoint'lerini plan bazlı ayır | `server.py` | Backend test |
| 3.3 | Plan bazlı dashboard widget'ları | `Dashboard.js` | Frontend test |
| 3.4 | 3 test tenant oluştur (smoke test) | `seed_data.py` | E2E test |

---

*Bu plan, mevcut altyapı üzerine minimum değişiklikle uygulanabilir. Mevcut `get_tenant_modules()`, `require_module()`, ve `AdminTenants.js` altyapısı doğru pattern'ı kullanıyor - sadece genişletilmesi gerekiyor.*
