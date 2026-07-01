# Syroce PMS — Uçtan Uca Audit & Opera Cloud Boşluk (Gap) Analizi Raporu

**Rapor Tarihi:** 1 Temmuz 2026  
**Kapsam:** Teknik Durum Tespiti, Modül Olgunluk Seviyeleri ve Opera Cloud Karşılaştırmalı Analizi

---

## 📌 1. Yönetici Özeti ve Değerlendirme Yaklaşımı

Syroce PMS, modüler kapsam olarak son derece geniş bir yelpazeye sahiptir ve son sprintlerle güvenlik altyapısı (tenant izolasyonu, fail-closed doğrulamaları) ciddi ölçüde güçlendirilmiştir. Ancak, sistemdeki bazı modüllerin varlığı (endpoint/sayfa karşılıkları) doğrudan Oracle Opera Cloud seviyesinde bir üretim olgunluğu (production-ready) anlamına gelmemektedir.

Bu rapor, pazarlama/satış iddialarından uzak, objektif bir **teknik due-diligence (durum tespiti) ve boşluk analizi** olarak hazırlanmıştır. Rapor, Opera ile net bir karşılaştırma sunmak ve Syroce'nin "all-in-one" vizyonunu yansıtmak amacıyla iki katmanlı olarak yapılandırılmıştır:
* **A) Opera Cloud Ana Karşılaştırma:** Geleneksel Opera Cloud kapsamına giren 21 temel modül üzerinden değerlendirme.
* **B) Syroce Genişletilmiş All-in-One Modül Envanteri:** Opera Cloud'u aşan veya Syroce'nin kendi içinde barındırdığı ek 14 operasyon alanı ile toplam 35 başlıklı tam envanter.

Modüllerin durumlarını sınıflandırmak için aşağıdaki nesnel teknik tanımlar kullanılmıştır:
* **Implemented and tested:** Tamamlanmış ve birim/entegrasyon testleriyle doğrulanmış.
* **Implemented but needs hardening:** Kodlanmış fakat uç senaryolar (edge-case) ve üretim yükü altında olgunlaştırılmalı.
* **UI/API exists but not production-verified:** Arayüz ve endpointler mevcut ancak gerçek tesis simülasyonlarında doğrulanmamış.
* **Prototype:** Temel iskelet/taslak aşamasında.
* **Missing:** Henüz geliştirilmemiş.

---

## 📊 2. A) Opera Cloud Ana Karşılaştırma — 21 Ana Başlık

| # | Opera Cloud Modülü | Syroce Kod/Test Karşılığı | Syroce PMS Durumu | Teknik Olgunluk ve Eksikler (Gap) | Pilot Öncesi Yapılacak İş |
|---|---|---|---|---|---|
| 1 | **PMS Core** (Reservations, Profiles, Rooms) | `/api/pms/{bookings,rooms,guests}` + `ReservationCalendar`, `ArrivalList` | **Implemented but needs hardening** | Check-in/out ve zengin folio özellikleri mevcut; ancak karmaşık fatura bölme (split-folio) ve transfer kombinasyonlarında ek testler gereklidir. | Edge-case (ödenmeyen folio iptalleri vb.) testlerinin yazılması. |
| 2 | **Folio / Cashier** | `/api/folio/*`, `FolioDetailView`, `FolioRoutingPage`, `PendingAR`, `CityLedgerAccounts` | **Implemented but needs hardening** | Fatura yönlendirme (folio routing) ve acente cari hesapları (city ledger) kodlandı, ancak pilot tesislerde finansal mutabakat doğrulamaları yapılmalıdır. | Pilot tesis finansal mutabakat (night audit) döngülerinin takibi. |
| 3 | **Housekeeping** | `/api/housekeeping/*`, `HousekeepingDashboard`, `HousekeepingMobileApp`, `LostFoundPage` | **Implemented but needs hardening** | Oda durumu güncellemeleri ve mobil housekeeping ekranları işlevseldir, ancak zengin iş gücü atama optimizasyonları sertleştirilmelidir. | Mobil web uygulamasında offline state testleri. |
| 4 | **Maintenance / Engineering** | `/api/maintenance/*`, `MaintenanceWorkOrders`, `MaintenanceAssets` | **Implemented but needs hardening** | Arıza kayıtları, koruyucu bakım planları ve iş emirleri kodlandı. Parça sarfiyat takibi, SLA escalation. | Otomatik arıza atama algoritmalarının test edilmesi. |
| 5 | **Sales & Catering / MICE** | `/api/mice/*`, `MicePage` (8 tab), `FnbBeoGenerator`, `CateringMenuPage` | **UI/API exists but not production-verified** | BEO ziyafet emirleri ve etkinlik planlama altyapısı mevcuttur; ancak pilot tesis geri bildirimi olmadan üretim kalitesi garanti edilemez. | Gerçek tesis BEO iterasyonları, resource clash testleri. |
| 6 | **F&B / POS** | `/api/pos/*`, `POSDashboard`, `KitchenDisplay`, `FnBComplete`, `MobileFnB` | **Implemented but needs hardening** | Masa transferi, zengin split-folios, Happy Hour ve Loyalty özellikleri kodlandı. Donanımsal yazıcı entegrasyonu simülasyon aşamasındadır. | Gerçek bir termal yazıcı ağında (ESC/POS) saha testi. |
| 7 | **Distribution / Channel Manager** | `/api/channel-manager/*` + Exely + HotelRunner, `ChannelHub`, `MappingManager` | **Implemented and tested** | HotelRunner ve Exely iki yönlü senkronizasyonu hazır. ARI drift check mekanizması entegre edildi. | Rate parity ve overbooking stress testlerinin artırılması. |
| 8 | **Revenue Management (RMS)** | `/api/rms/*`, `/api/analytics/{forecast,pace}`, `RMSModule`, `RevenueAutopilot` | **Implemented but needs hardening** | Fiyat kuralları ve dinamik yield kuralları mevcut. AI-tabanlı otomatik fiyatlandırma (autopilot) algoritmik doğrulamadadır. | Algoritmanın geçmiş verilerle (backtest) 1 yıllık simülasyonu. |
| 9 | **Reporting / Analytics** | `/api/reports/*`, `BasicReports`, `ReportBuilder`, `FlashReport`, `AnalitikRaporlarPage` | **Implemented but needs hardening** | Temel raporlar ve Türkiye mevzuatına uygun vergi raporları kodlandı. Büyük veri çekimlerinde timeout riskleri mevcuttur. | Rapor sorgularının asenkron (background job) hale getirilmesi. |
| 10 | **Loyalty** | `/api/loyalty/*`, `LoyaltyModule`, `LoyaltyAdminPage` | **UI/API exists but not production-verified** | Puan kazanma ve harcama kuralları kodlandı, ancak tier-rules engine zayıftır ve misafir üyelik portalı bulunmamaktadır. | Çok tesisli (cross-property) puan birleştirme ve fraud kontrolü. |
| 11 | **Guest Experience / Self-Service** | `/api/guest/*`, `GuestPortal`, `SelfCheckin`, `OnlineCheckin`, `DigitalKey`, `UpsellStore` | **Implemented but needs hardening** | Çevrimiçi giriş ve kapı anahtarı (digital key) entegrasyonu kod bazında hazır; donanım saha testleri yapılmalı. | Android/iOS Safari/Chrome farklı versiyonlarda UAT. |
| 12 | **Multi-Property / Central Office** | `/api/multi-property/dashboard`, `CentralPricingManager`, `CrossPropertyGuests` | **UI/API exists but not production-verified** | Çoklu tesis yönetimi ve merkezi fiyat güncelleyici arayüzleri hazır, ancak kurumsal zincir kullanımı test edilmemiştir. | Tesisler arası cari virman ve borç transferi yasal takibi. |
| 13 | **Mobile Apps** | 24 mobil route: `MobileDashboard`, `MobileFrontDesk`, `MobileHousekeeping`, `MobileGM` | **Implemented but needs hardening** | Mobil ekranların sayısı geniş olmakla birlikte, zayıf ağ koşullarında offline senkronizasyon yeteneği sertleştirilmelidir. | `Weak Network Mode` test senaryolarının işletilmesi. |
| 14 | **Integrations / Marketplace** | `MarketplaceModule`, `ModuleStorePage`, `IntegrationHub`, `IntegrationCredentials` | **Implemented but needs hardening** | Entegrasyon şablonları ve bağlantı hub'ı hazır. | 3. parti API kesintilerinde retry mekanizmalarının audit edilmesi. |
| 15 | **Activities (Spa, Golf, Aktivite)** | `SpaWellness`, `ActivitySchedulerPage` | **UI/API exists but not production-verified** | Spa randevuları kodlandı, ancak terapist, kort ve eğitmen gibi kaynak bazlı genel takvim planlama derinliği eksiktir. | Aktivite eğitmen/alan takvimi çakışmaları test edilmeli. |
| 16 | **Sales Force CRM** | `/api/sales/*`, `SalesCRM`, `SalesCRMMobile`, `GroupSales` | **Implemented but needs hardening** | Acente teklifleri ve kurumsal firma hesapları yönetilebilir durumda. | KVKK/GDPR izin geçmişi takibi. |
| 17 | **AI / Predictive Engine** | `AIChatbot`, `AIWhatsAppConcierge`, `PredictiveAnalytics`, `RevenueAutopilot` | **UI/API exists but not production-verified** | WhatsApp concierge ve makine öğrenimi modelleri entegre; ancak LLM doğruluğu ve güvenlik filtreleri sertleştirilmelidir. | Prompt injection ve PII maskeleme katmanının eklenmesi. |
| 18 | **Compliance & Security** | `PCIComplianceDashboard`, `GDPRCompliance`, `SecurityHub`, `LockdownDashboard`, `kvkk-retention-deletion` | **Implemented and tested** | KVKK/GDPR saklama süreleri dolan veriler otomatik ve geri döndürülemez şekilde anonimleştirilir. | Manuel override'lar için 4-göz onay (maker-checker) akışı. |
| 19 | **Audit & Observability** | `AuditTimelinePage`, `ObservabilityDashboard`, `LogViewer`, `night_audit_module.py` | **Implemented and tested** | Sistem logları, event bus ve gözetlenebilirlik panelleri aktiftir. 500+ odada eşzamanlı işlem limitleri ve rollback senaryoları. | Kilitlenme (deadlock) durumlarında tam rollback stress testleri. |
| 20 | **B2B / Agency Portal** | `AgencyPortalDashboard`, `AgencyManagement`, `B2BApiDocs` | **UI/API exists but not production-verified** | API anahtar yönetimi ve yetki sınırları aktif. Dinamik `B2BApiDocs` mevcuttur. Toplu (bulk) acenta faturası kesimi. | B2B fatura mutabakat modülünün muhasebe entegrasyonu. |
| 21 | **Türkiye Mevzuat** | `KBS`, `Jandarma`, `OfficialGuestList`, `Quick-ID`, e-Fatura, Konaklama Vergisi | **UI/API exists but not production-verified** | KBS/Jandarma gerçek format dosyası, e-Fatura provider entegrasyonu, Konaklama vergisi hesap testleri, Quick-ID doğrulama, Resmi bildirim E2E testleri eksik. | e-Fatura, KBS ve Konaklama Vergisi uçtan uca simülasyonlarının gerçek XML/JSON yapıları ile doğrulanması. |

---

## 🚀 3. B) Syroce Genişletilmiş All-in-One Modül Envanteri — 35 Başlık

Aşağıdaki modüller, Syroce PMS'in standart PMS kurulumlarını aşan veya kendi mimarisi içinde ayrı bir ürün seviyesinde yönetilen spesifik operasyon alanlarını listelemektedir.

| # | Modül / Özellik | Syroce Kod/Test Karşılığı | Maturity | Ana Gap | Pilot Öncesi Yapılacak İş |
|---|---|---|---|---|---|
| 22 | **Reservation Waitlist / Availability Queue** | `reservation_waitlist.py` + reservation lifecycle stress tests | **UI/API exists but not production-verified** | Waitlist → otomatik oda açılınca öneri, öncelik skoru, OTA/direct ayrımı ve revenue-priority logic sertleştirilmeli. | Bekleme listesi puanlama (scoring) algoritmasının simülasyonu. |
| 23 | **Physical Security / Door Lock / Keycard** | `door_reader.py`, lock bridge, physical security tests | **Implemented but needs hardware field validation** | Gerçek kapı kilidi/kart cihazlarıyla saha testi, offline kart üretimi, failed-open/closed senaryoları, audit trail derinliği. | Seçilen bir kilit markası ile fiziksel donanım test laboratuvarı kurulumu. |
| 24 | **Guest Profile UDF / Duplicate Detection / Merge** | `profile_udf_router.py`, `cross_property.py` | **UI/API exists but not production-verified** | Duplicate matching score, merge wizard, auditli merge rollback, cross-property profile governance eksik. | Birleştirilen misafir folyolarının muhasebe uyuşmazlığı testleri. |
| 25 | **Golf Operations / Tee Time Management** | `domains/golf/router.py`, `98-golf-operational.spec.js` | **Implemented but needs hardening** | Tee time kapasite, oyuncu profili, folio charge, ekipman/kiralama, saha/kort kaynak takvimi ve weather disruption senaryoları güçlendirilmeli. | Operasyonel "No-show" ve iptal cezalarının folio'ya yansıması testleri. |
| 26 | **Spa & Wellness Operations** | `domains/spa/router.py`, spa operational stress specs | **Implemented but needs hardening** | Terapist kaynak takvimi, oda/ekipman uygunluğu, paket satış, folio bağlantısı, no-show/cancel policy ve mobile therapist flow. | Terapist komisyonlarının İK/Bordro modülüyle senkronizasyonu. |
| 27 | **HR / Workforce / Payroll** | HR staff, attendance, leave, shift, payroll, performance, coverage planning | **Implemented but needs hardening** | Bordro mevzuatı, vardiya çakışma optimizasyonu, çalışan mobil uygulaması, PII masking, onay akışları ve muhasebe entegrasyonu pilotta doğrulanmalı. | PDKS cihazlarıyla entegrasyon POC yapılması. |
| 28 | **Procurement / Purchasing / Inventory** | `inventory_items`, `stock_movements`, procurement purchase request/order/goods receipt akışları | **UI/API exists but not production-verified** | Satın alma onay zinciri, teklif karşılaştırma, tedarikçi performans skoru, minimum stok uyarısı, reçete/consumption bağlantısı pilotta test edilmeli. | Maliyet analizleri ve depo sayım işlemlerinin doğrulanması. |
| 29 | **Finance Backoffice / Cashier Shift / Accounting** | cashier shifts, cashier transactions, city ledger, expenses, suppliers, bank accounts, accounting invoices | **Implemented but needs hardening** | Gün sonu kasa mutabakatı, yetkili onay, muhasebe fişi, banka hareketi eşleştirme, şehir cari yaşlandırma ve denetim raporu doğrulanmalı. | Gerçek bir ERP (SAP/Logo) e-Defter aktarım testinin çalıştırılması. |
| 30 | **Contact Center / Messaging / Omnichannel** | messaging, room QR requests, service requests, complaints, delivery logs | **Implemented but needs hardening** | WhatsApp/SMS/email provider failover, SLA routing, agent queue, escalation, guest consent, delivery receipt ve KVKK saklama politikası. | Yüksek trafikli dönemlerde mesaj gecikmelerinin stress testi. |
| 31 | **Guest Service Requests / Room QR Operations** | room QR requests, service request staff view, SLA stats | **Implemented and tested** | Departman bazlı otomatik atama, SLA escalation, mobil push, misafir memnuniyet dönüşü ve dashboard KPI sertleştirilmeli. | Yanlış atanan taleplerin manuel yeniden atama testleri. |
| 32 | **Reputation / Reviews / Feedback** | public reviews, guest feedback, external reviews, complaint compensation reports | **UI/API exists but not production-verified** | Google/OTA yorum çekme, sentiment analizi, cevap önerisi, aksiyon task’ı ve departman sorumluluk takibi. | Sahte/spam yorum filtrelenmesi ve alert sisteminin kurulması. |
| 33 | **Event Bus / Outbox / Webhook Reliability** | outbox status, webhooks status, circuit breaker, external_calls invariant | **Implemented and tested** | DLQ, retry policy, idempotency keys, provider outage replay, message ordering ve alerting dashboard olgunluğu artırılmalı. | 1 saatlik dış ağ kesintisi senaryosunda message replay testi. |
| 34 | **Mobile Offline / Weak Network Mode** | mobile routes, mobile housekeeping/frontdesk/GM/finance | **Prototype / needs hardening** | Offline queue, conflict resolution, local cache encryption, reconnect replay, idempotent mutation, weak-network E2E testleri eksik. | Çatışan verilerin senkronizasyonu (Conflict resolution). |
| 35 | **Rate Code / Packages / Promotions / Restrictions** | `rate_plans`, `rate_periods`, `rate_overrides`, `packages`, cancellation policies | **Implemented but needs hardening** | Rate code inheritance, market/segment/channel restrictions, package component split, cancellation policy inheritance, yield audit açıklaması. | Farklı sezon/promosyon çakışmalarında en iyi fiyat algoritmasının E2E doğrulanması. |

---

## ⚡ 4. Performans ve CI Darboğazları (Önceliklendirilmiş Yol Haritası)

Performans darboğazları ve yavaşlık sorunları aciliyetlerine göre yeniden önceliklendirilmiştir:

### 🔴 En Yüksek Öncelik (Sistem Kararlılığı ve Geliştirici Akışı)
* **Login/session hotfix doğrulandı, merge/deploy sonrası canlı test bekleniyor. Stress suite timeout ve seed performance ayrı task olarak açık.**

### 🟡 Yüksek Öncelik (Yavaş API Endpointleri)
Aşağıdaki yavaş okuma sorgularının optimize edilmesi, indekslenmesi veya cache'lenmesi gerekmektedir:
* `/api/channel-manager/v2/dashboard/overview` — **3035 ms**
* `/api/mice/spaces` — **1908 ms**
* `/api/ai/activity-feed` — **1611 ms**
* `/api/rms/dashboard-kpis` — **1253 ms**
* `/api/auth/login` — **1174 ms** 

### 🟢 Orta Öncelik (Frontend Paket Boyutları)
Büyük frontend bileşenlerinin lazy-load edilmesi ve virtualization ile render yükünün hafifletilmesi:
* `HRComplete.jsx`, `Settings.jsx` ve `StaffProfile.jsx` bileşenlerinin lazy-load edilmesi planlanmalıdır.

---

## 🛠️ 5. Son Kod Denetimi ve Güvenlik Sertleştirmesi

### 1. `door_reader.py` — NameError Giderildi
* **Dosya:** [door_reader.py](file:///Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/door_reader.py)
* **Durum:** ✅ **Düzeltildi**. `get_system_db` import hatası giderildi.

### 2. POS — Kısmi Masa Transferi Mantığı
* **Dosya:** [pos_core.py](file:///Users/syroce/Documents/GitHub/SyrocePMS/backend/domains/pms/pos_fnb_router/pos_core.py#L1045)
* **Durum:** ✅ **Doğrulandı**. Miktar bazlı kısmi transfer mantığı testlerle güvenceye alındı.

### 3. Guest Relations Yetki ve İş Mantığı Güçlendirilmesi
* **Dosya:** [guest_relations.py](file:///Users/syroce/Documents/GitHub/SyrocePMS/backend/routers/guest_relations.py)
* **Durum:** ⚠️ **Hardening Aşamasında** (Branch: `fix-guest-relations-tests-and-query-hardening`).
  * **Yetki Düzeltmesi:** Misafir profil analizi için `view_guest_list` operasyonel iznine geçildi.
  * **Güvenlik İzolasyonu:** `get_system_db()` kullanımı kaldırılarak tenant-aware `db` proxy nesnesine aktarıldı.
  * **Kişiye Özel Minibar Analizi:** Sadece misafire özel minibar kayıtları filtrelenerek analiz edildi.
  * **SPA Tercih Doğruluğu:** Arama kriteri `guest_id` olarak güncellendi.
  * **Hazırlık Tetikleme İzni:** `/preparations/trigger` yetkisi `manage_guests` olarak güncellendi.
  * **Veritabanı Seviyesinde Filtreleme:** Tarihsel analizler DB düzeyine çekildi.

---

## 🚨 6. Geliştirme Süreç Disiplini ve Kurallar

* **Hiçbir kod değişikliği doğrudan `main` branch'ine pushlanamaz veya doğrudan main'e merge edilemez.**
* Tüm geliştirmeler ayrı bir branch üzerinde yapılmalı, yerel testleri tamamlanmalı, pull request oluşturulmalı ve CI onayından sonra merge edilmelidir.
