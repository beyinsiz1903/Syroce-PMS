# Syroce PMS - Changelog

### Session 27 (Mar 20, 2026)
- [x] **Kiracı Yönetimi Sayfası Tam İyileştirme (Tenant Management Overhaul)**
  - **Yeni Otel Ekleme**: "Yeni Otel Ekle" butonu ile modal form (ad, e-posta, şifre, telefon, adres, konum, açıklama, plan, süre)
  - **Otel Bilgi Düzenleme**: Kalem ikonuyla edit modal (ad, e-posta, telefon, adres, konum, oda sayısı, açıklama)
  - **Ekip Yönetimi**: Her otel için "Ekip" butonu ile kullanıcı listesi, üye ekleme formu, rol değiştirme (inline dropdown), üye silme
  - **Tüm Kullanıcılar Görünümü**: "Tüm Kullanıcılar" butonu ile tablo görünüm, rol filtresi, arama, otel adı eşleştirmesi
  - **İstatistik Paneli**: Otel genişletildiğinde oda, kullanıcı, misafir, toplam/bu ay rezervasyon, check-in sayıları
  - **Sıralama**: Ada göre A-Z / Z-A sıralama
  - **Refactoring**: AdminTenants.js 740 satırdan ~300 satıra düşürüldü, 6 alt bileşene ayrıldı
  - Backend: 7 yeni endpoint (info, team CRUD, role, stats)
  - Backend Bug Fix: `create_tenant` duplicate email check artık `contact_email` ve `email` alanlarını kontrol ediyor, kullanıcı email çakışması da kontrol ediliyor
  - Modified: `AdminTenants.js`, `admin/router.py`, `admin/schemas.py`
  - New: `admin/tenantConstants.js`, `CreateTenantModal.js`, `EditTenantModal.js`, `TeamManagementModal.js`, `AllUsersView.js`, `TenantStatsPanel.js`
  - Tested: Backend 18/20 (90%) + Frontend 100% (iteration_105.json)

### Session 26 (Mar 20, 2026)
- [x] **Feature: Rooms Tab Hizli Rezervasyon (Quick Booking)**
- [x] Tested: Backend 7/7 + Frontend 100% (iteration_104.json)

### Session 25 (Mar 20, 2026)
- [x] **Feature: Otel İş Günü Bazlı Rezervasyon (Business Date Validation)**
- [x] **Feature: Takvim 3 Gün Geriden Başlıyor**
- [x] Tested: Backend 6/6 + Frontend 100% (iteration_103.json)

### Session 24 (Mar 20, 2026)
- [x] **Bug Fix: ReservationDetailModal Check-in/Checkout Bypass**
- [x] Tested: Backend 11/12 + Frontend verified

### Session 23 (Mar 19, 2026)
- [x] **Hızlı Ödeme Modalı (Quick Payment from Rooms Tab)**

### Session 22 (Mar 19, 2026)
- [x] **Misafir Adına Tıklama → Rezervasyon Detay Modalı**
- [x] **Misafir Durumuna Göre Renkli Oda Kartları**

### Session 21 (Mar 19, 2026)
- [x] **Feature: Kirli Oda Check-in Uyarısı**

### Session 20 (Mar 19, 2026)
- [x] **P0 FIX: Checkout with Outstanding Balance Prevention**

### Session 19 (Mar 19, 2026)
- [x] **Odalar Sekmesi Hızlı İşlemler (Quick Room Actions)**

### Session 18 (Mar 19, 2026)
- [x] **P0: Oda Yönetimi Erişim Kontrolü**

### Session 17 (Mar 19, 2026)
- [x] **Bug Fix: Rate Manager Para Birimi Sembolü**
- [x] **Odalar Sekmesinde Misafir Bilgisi**

### Session 16 (Mar 19, 2026)
- [x] **P0 FIX: Exely Reservation Delivery Confirmation (Critical)**
- [x] **Exely Webhook Endpoint**

### Session 15 (Mar 19, 2026)
- [x] **Bug Fix: /api/invoices/stats 500 Error**
- [x] **Bug Fix: Exely Currency USD→TRY**
- [x] **Feature: Configurable Currency per Hotel**
- [x] **Performance: Rate Manager Bulk Update ~6.5x Faster**
