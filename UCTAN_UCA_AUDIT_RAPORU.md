# Syroce PMS — Uçtan Uca Audit & Opera Cloud Boşluk (Gap) Analizi Raporu

**Rapor Tarihi:** 1 Temmuz 2026  
**Kapsam:** Teknik Durum Tespiti, Modül Olgunluk Seviyeleri ve Opera Cloud Karşılaştırmalı Analizi

---

## 📌 1. Yönetici Özeti ve Değerlendirme Yaklaşımı

Syroce PMS, modüler kapsam olarak son derece geniş bir yelpazeye sahiptir ve son sprintlerle güvenlik altyapısı (tenant izolasyonu, fail-closed doğrulamaları) ciddi ölçüde güçlendirilmiştir. Ancak, sistemdeki bazı modüllerin varlığı (endpoint/sayfa karşılıkları) doğrudan Oracle Opera Cloud seviyesinde bir üretim olgunluğu (production-ready) anlamına gelmemektedir.

Bu rapor, pazarlama/satış iddialarından uzak, objektif bir **teknik due-diligence (durum tespiti) ve boşluk analizi** olarak hazırlanmıştır. Modüllerin durumlarını sınıflandırmak için aşağıdaki nesnel teknik tanımlar kullanılmıştır:
* **Implemented and tested:** Tamamlanmış ve birim/entegrasyon testleriyle doğrulanmış.
* **Implemented but needs hardening:** Kodlanmış fakat uç senaryolar (edge-case) ve üretim yükü altında olgunlaştırılmalı.
* **UI/API exists but not production-verified:** Arayüz ve endpointler mevcut ancak gerçek tesis simülasyonlarında doğrulanmamış.
* **Prototype:** Temel iskelet/taslak aşamasında.
* **Missing:** Henüz geliştirilmemiş.

---

## 📊 2. Oracle Opera Cloud vs Syroce PMS Modül Haritası

| # | Opera Cloud Modülü | Syroce Karşılığı | Syroce PMS Durumu | Teknik Olgunluk ve Eksikler (Gap) |
|---|---|---|---|---|
| 1 | **PMS Core** (Reservations, Profiles, Rooms) | `/api/pms/{bookings,rooms,guests}` + `ReservationCalendar`, `ArrivalList` | **Implemented but needs hardening** | Check-in/out ve zengin folio özellikleri mevcut; ancak karmaşık fatura bölme (split-folio) ve transfer kombinasyonlarında ek testler gereklidir. |
| 2 | **Folio / Cashier** | `/api/folio/*`, `FolioDetailView`, `FolioRoutingPage`, `PendingAR`, `CityLedgerAccounts` | **Implemented but needs hardening** | Fatura yönlendirme (folio routing) ve acente cari hesapları (city ledger) kodlandı, ancak pilot tesislerde finansal mutabakat doğrulamaları yapılmalıdır. |
| 3 | **Housekeeping** | `/api/housekeeping/*`, `HousekeepingDashboard`, `HousekeepingMobileApp`, `LostFoundPage` | **Implemented but needs hardening** | Oda durumu güncellemeleri ve mobil housekeeping ekranları işlevseldir, ancak zengin iş gücü atama optimizasyonları sertleştirilmelidir. |
| 4 | **Maintenance / Engineering** | `/api/maintenance/*`, `MaintenanceWorkOrders`, `MaintenanceAssets` | **Implemented but needs hardening** | Arıza kayıtları, koruyucu bakım planları ve iş emirleri kodlandı. |
| 5 | **Sales & Catering / MICE** | `/api/mice/*`, `MicePage` (8 tab), `FnbBeoGenerator`, `CateringMenuPage` | **UI/API exists but not production-verified** | BEO ziyafet emirleri ve etkinlik planlama altyapısı mevcuttur; ancak pilot tesis geri bildirimi olmadan üretim kalitesi garanti edilemez. |
| 6 | **F&B / POS** | `/api/pos/*`, `POSDashboard`, `KitchenDisplay`, `FnBComplete`, `MobileFnB` | **Implemented but needs hardening** | Masa transferi, zengin split-folios, Happy Hour ve Loyalty özellikleri kodlandı. Donanımsal yazıcı entegrasyonu simülasyon aşamasındadır. |
| 7 | **Distribution / Channel Manager** | `/api/channel-manager/*` + Exely + HotelRunner, `ChannelHub`, `MappingManager` | **Implemented and tested** | HotelRunner ve Exely iki yönlü senkronizasyonu hazır. ARI drift check mekanizması entegre edildi. |
| 8 | **Revenue Management (RMS)** | `/api/rms/*`, `/api/analytics/{forecast,pace}`, `RMSModule`, `RevenueAutopilot` | **Implemented but needs hardening** | Fiyat kuralları ve dinamik yield kuralları mevcut. AI-tabanlı otomatik fiyatlandırma (autopilot) algoritmik doğrulamadadır. |
| 9 | **Reporting / Analytics** | `/api/reports/*`, `BasicReports`, `ReportBuilder`, `FlashReport`, `AnalitikRaporlarPage` | **Implemented but needs hardening** | Temel raporlar ve Türkiye mevzuatına uygun vergi raporları kodlandı. |
| 10 | **Loyalty** | `/api/loyalty/*`, `LoyaltyModule`, `LoyaltyAdminPage` | **Prototype** | Puan kazanma ve harcama kuralları kodlandı, ancak tier-rules engine zayıftır ve misafir üyelik portalı bulunmamaktadır. |
| 11 | **Guest Experience / Self-Service** | `/api/guest/*`, `GuestPortal`, `SelfCheckin`, `OnlineCheckin`, `DigitalKey`, `UpsellStore` | **Implemented but needs hardening** | Çevrimiçi giriş ve kapı anahtarı (digital key) entegrasyonu kod bazında hazır; donanım saha testleri yapılmalı. |
| 12 | **Multi-Property / Central Office** | `/api/multi-property/dashboard`, `CentralPricingManager`, `CrossPropertyGuests` | **UI/API exists but not production-verified** | Çoklu tesis yönetimi ve merkezi fiyat güncelleyici arayüzleri hazır, ancak kurumsal zincir kullanımı test edilmemiştir. |
| 13 | **Mobile Apps** | 24 mobil route: `MobileDashboard`, `MobileFrontDesk`, `MobileHousekeeping`, `MobileGM` | **Implemented but needs hardening** | Mobil ekranların sayısı geniş olmakla birlikte, zayıf ağ koşullarında offline senkronizasyon yeteneği sertleştirilmelidir. |
| 14 | **Integrations / Marketplace** | `MarketplaceModule`, `ModuleStorePage`, `IntegrationHub`, `IntegrationCredentials` | **Implemented but needs hardening** | Entegrasyon şablonları ve bağlantı hub'ı hazır. |
| 15 | **Activities (Spa, Golf, Aktivite)** | `SpaWellness`, `ActivitySchedulerPage` | **Prototype** | Spa randevuları kodlandı, ancak terapist, kort ve eğitmen gibi kaynak bazlı genel takvim planlama derinliği eksiktir. |
| 16 | **Sales Force CRM** | `/api/sales/*`, `SalesCRM`, `SalesCRMMobile`, `GroupSales` | **Implemented but needs hardening** | Acente teklifleri ve kurumsal firma hesapları yönetilebilir durumda. |
| 17 | **AI / Predictive Engine** | `AIChatbot`, `AIWhatsAppConcierge`, `PredictiveAnalytics`, `RevenueAutopilot` | **UI/API exists but not production-verified** | WhatsApp concierge ve makine öğrenimi modelleri entegre; ancak LLM doğruluğu ve güvenlik filtreleri sertleştirilmelidir. |
| 18 | **Compliance & Security** | `PCIComplianceDashboard`, `GDPRCompliance`, `SecurityHub`, `LockdownDashboard` | **Implemented and tested** | KVKK/GDPR saklama süreleri dolan veriler otomatik ve geri döndürülemez şekilde anonimleştirilir. |
| 19 | **Audit & Observability** | `AuditTimelinePage`, `ObservabilityDashboard`, `LogViewer`, `RuntimeCockpitPage` | **Implemented and tested** | Sistem logları, event bus ve gözetlenebilirlik panelleri aktiftir. |
| 20 | **B2B / Agency Portal** | `AgencyPortalDashboard`, `AgencyManagement`, `B2BApiDocs` | **Implemented and tested** | API anahtar yönetimi ve yetki sınırları aktif. Dinamik `B2BApiDocs` mevcuttur. |
| 21 | **Türkiye Mevzuat** (e-Fatura, KonaklamaVergisi) | `EFaturaModule`, `KonaklamaVergisiModule`, `OfficialGuestList`, `Quick-ID` | **Implemented and tested** | Türkiye'deki yasal zorunluluklar (KBS/Jandarma bildirimi, konaklama vergisi hesabı ve e-Fatura/e-Arşiv gönderimi) entegre edilmiştir. |

---

## ⚡ 3. Performans ve CI Darboğazları (Önceliklendirilmiş Yol Haritası)

Performans darboğazları ve yavaşlık sorunları aciliyetlerine göre yeniden önceliklendirilmiştir:

### 🔴 En Yüksek Öncelik (Sistem Kararlılığı ve Geliştirici Akışı)
1. **Login/Session Hotfix:** Giriş sonrası yaşanan anlık çıkış (immediate logout) döngüsü.
2. **Database Seeding Hardening:** 500-oda seed işleminin timeout süresi (97s → 55s altına çekilmesi).
3. **CI Stress Suite Timeout:** 1 saat 30 dakikayı aşarak CI'ı kilitleyen stress testlerinin sharding yapılarak paralel 4 matrix job'a bölünmesi.
   > [!NOTE]
   > Bu üç ana kararlılık adımı tamamlanmış, test edilmiş ve `main` branch'ine başarıyla entegre edilmiştir.

### 🟡 Yüksek Öncelik (Yavaş API Endpointleri)
Aşağıdaki yavaş okuma sorgularının optimize edilmesi, indekslenmesi veya cache'lenmesi gerekmektedir:
* `/api/channel-manager/v2/dashboard/overview` — **3035 ms** (Provider bazlı paralel fetch ve Redis cache eklenecek)
* `/api/mice/spaces` — **1908 ms** (Sort ve limit parametreleri eklenecek)
* `/api/ai/activity-feed` — **1611 ms** (Tenant_id ve ts DESC compound index doğrulaması yapılacak)
* `/api/rms/dashboard-kpis` — **1253 ms** (Materialized view ve ön-hesaplama mekanizması kurulacak)
* `/api/auth/login` — **1174 ms** (Bcrypt round sayısı ve tenant lookup cache mekanizması incelenecek)
* `/api/mice/events` — **1118 ms** (N+1 count sorguları asyncio.gather ile tek-shot yapılacak)

### 🟢 Orta Öncelik (Frontend Paket Boyutları)
Büyük frontend bileşenlerinin lazy-load edilmesi ve virtualization ile render yükünün hafifletilmesi:
* `HRComplete.jsx` (**101.4 KB**): İK sekmelerinin `React.lazy()` ile dinamik import yapılması.
* `Settings.jsx` (**86.2 KB**): Ayarlar sekmelerinin alt bileşenlere bölünmesi.
* `StaffProfile.jsx` (**80.5 KB**): Personel detay sekmesi verilerinin sayfa açılışında değil, tıklandığında çekilmesi.

---

## 🛠️ 4. Son Kod Denetimi ve Güvenlik Sertleştirmesi

### 1. `door_reader.py` — NameError Giderildi
* **Dosya:** [door_reader.py](file:///Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/door_reader.py)
* **Durum:** ✅ **Düzeltildi**. `get_system_db` import hatası giderildi, kapı entegrasyonu doğrulanabilir durumda.

### 2. POS — Kısmi Masa Transferi Mantığı
* **Dosya:** [pos_core.py](file:///Users/syroce/Documents/GitHub/SyrocePMS/backend/domains/pms/pos_fnb_router/pos_core.py#L1045)
* **Durum:** ✅ **Doğrulandı**. Miktar bazlı kısmi transfer mantığı ve sınır kontrolleri yazılmış, testlerle güvenceye alınmıştır.

### 3. Guest Relations Yetki ve İş Mantığı Güçlendirilmesi
* **Dosya:** [guest_relations.py](file:///Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/guest_relations.py)
* **Durum:** ⚠️ **Hardening Aşamasında** (Branch: `fix-guest-relations-tests-and-query-hardening`).
  * **Yetki Düzeltmesi:** Misafir profil analizi ve hazırlık direktifleri yetkilendirmesi, semantik olarak hatalı olan `view_hr` yerine doğru şekilde `view_guest_list` operasyonel iznine bağlandı.
  * **Güvenlik İzolasyonu:** Doğrudan raw database (`get_system_db()`) kullanımı kaldırıldı. Sorgular, bypass riski içermeyen tenant-aware `db` proxy nesnesine aktarıldı.
  * **Kişiye Özel Minibar Analizi:** Tüm otel postings verilerini tarayan genel mantık yerine, ilgili misafirin geçmiş rezervasyonları (`bookings`) ve ilişkili folyoları (`folios`) üzerinden sadece **misafire özel** minibar postings kayıtları süzülerek analiz edildi.
  * **SPA Tercih Doğruluğu:** SPA analizindeki isim çakışması riskini engellemek için arama kriteri `guest_name` yerine `guest_id` olarak güncellendi (isimle arama sadece geriye uyumluluk için fallback olarak bırakıldı).
  * **Hazırlık Tetikleme İzni:** `/preparations/trigger` yetkisi `manage_sales` yerine `manage_guests` olarak güncellendi.
  * **Veritabanı Seviyesinde Filtreleme:** Python döngüleri ile yapılan check-in tarihi kontrolleri, veritabanı sorgusu düzeyine (`$or`, `$gte`, `$lte` operatörleri ile) çekilerek performans artırıldı.

> [!NOTE]
> **RBAC Semantik Temizlik Notu:**
> `view_guest_list` operasyonel anahtarı şu anda `Permission.VIEW_REPORTS` iznine bağlıdır. Gelecekteki bir RBAC temizlik sprintinde en doğru pratik, bu yetkiyi daha spesifik olan `Permission.VIEW_GUESTS` ve `Permission.VIEW_GUEST_PREFERENCES` izinlerine bağlamaktır.

---

## 🚨 5. Geliştirme Süreç Disiplini ve Kurallar

* **Hiçbir kod değişikliği doğrudan `main` branch'ine pushlanamaz veya doğrudan main'e merge edilemez.**
* Tüm geliştirmeler (`fix-guest-relations-tests-and-query-hardening` örneğindeki gibi) ayrı bir branch üzerinde yapılmalı, yerel testleri tamamlanmalı, pull request oluşturulmalı ve CI onayından sonra merge edilmelidir.
