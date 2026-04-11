# 🔐 RoomOps - Kullanıcı Rolleri ve Yetkileri

## 📋 İçindekiler
1. [Rol Özeti](#rol-özeti)
2. [Detaylı Yetki Tablosu](#detaylı-yetki-tablosu)
3. [Departman Bazlı Erişim](#departman-bazlı-erişim)
4. [Yetki Değişikliği Prosedürü](#yetki-değişikliği-prosedürü)

---

## Rol Özeti

### 1. 👑 ADMIN (Yönetici)
**Tam Yetki** - Sistemdeki tüm işlemleri gerçekleştirebilir

**Kullanım Alanı:**
- Otel Genel Müdürü
- IT Yöneticisi
- Sistem Administratörü

**Temel Özellikler:**
- ✅ Tüm modüllere erişim
- ✅ Kullanıcı yönetimi
- ✅ Sistem ayarları
- ✅ Finansal raporlar
- ✅ Audit log görüntüleme
- ✅ Backup/Restore işlemleri

---

### 2. 👔 SUPERVISOR (Süpervizör)
**Yönetim Yetkisi** - Departman yönetimi ve operasyonel kararlar

**Kullanım Alanı:**
- Front Office Manager
- Housekeeping Supervisor
- F&B Manager

**Temel Özellikler:**
- ✅ Rezervasyon yönetimi
- ✅ Oda tahsisi
- ✅ Rate override (limit dahilinde)
- ✅ Rapor görüntüleme
- ✅ Staff task atama
- ⛔ Kullanıcı oluşturma
- ⛔ Sistem ayarları

---

### 3. 🏨 FRONT_DESK (Ön Büro Görevlisi)
**Operasyonel Yetki** - Günlük rezervasyon ve check-in/out işlemleri

**Kullanım Alanı:**
- Resepsiyon Görevlisi
- Night Auditor
- Guest Relations

**Temel Özellikler:**
- ✅ Rezervasyon oluşturma
- ✅ Check-in / Check-out
- ✅ Oda değişikliği
- ✅ Guest profil görüntüleme
- ✅ Folio görüntüleme
- ⚠️ Charge posting (sınırlı)
- ⛔ Rate override
- ⛔ Ödeme iptali

---

### 4. 🧹 HOUSEKEEPING (Kat Hizmetleri)
**Housekeeping Yetkileri** - Oda durumları ve temizlik yönetimi

**Kullanım Alanı:**
- Housekeeping Staff
- Room Attendant
- Housekeeping Supervisor

**Temel Özellikler:**
- ✅ Oda durumu güncelleme
- ✅ Task görüntüleme ve tamamlama
- ✅ Lost & Found kayıt
- ✅ Maintenance request
- ⛔ Rezervasyon görüntüleme
- ⛔ Guest bilgileri
- ⛔ Finansal işlemler

---

### 5. 💼 SALES (Satış)
**Satış Yetkileri** - Corporate ve grup rezervasyonları

**Kullanım Alanı:**
- Sales Manager
- Corporate Sales Executive
- Group Coordinator

**Temel Özellikler:**
- ✅ Company profil yönetimi
- ✅ Contracted rate tanımlama
- ✅ Group booking oluşturma
- ✅ Block reservation
- ✅ Sales raporları
- ⚠️ Rate override (approval gerekli)
- ⛔ Check-in/Check-out
- ⛔ Folio işlemleri

---

### 6. 💰 FINANCE (Finans/Muhasebe)
**Finansal Yetki** - Muhasebe ve finansal raporlar

**Kullanım Alanı:**
- Muhasebe Müdürü
- Accountant
- Accounting Clerk

**Temel Özellikler:**
- ✅ Tüm finansal raporlar
- ✅ Invoice oluşturma
- ✅ E-Fatura işlemleri
- ✅ Company aging report
- ✅ Payment posting
- ✅ Charge void (with reason)
- ✅ Export işlemleri
- ⛔ Rezervasyon oluşturma
- ⛔ Check-in işlemleri

---

### 7. 👤 STAFF (Genel Personel)
**Temel Yetki** - Kendi görevleri ve bildirimler

**Kullanım Alanı:**
- Engineering
- F&B Staff
- Maintenance

**Temel Özellikler:**
- ✅ Kendi task'larını görüntüleme
- ✅ Task durumu güncelleme
- ✅ Issue reporting
- ⛔ Başkalarının task'ları
- ⛔ Rezervasyon görüntüleme
- ⛔ Guest bilgileri

---

### 8. 🎫 GUEST (Misafir)
**Guest Portal Yetkileri** - Kendi rezervasyon ve servisler

**Kullanım Alanı:**
- Otel Misafirleri
- Loyalty Program Üyeleri

**Temel Özellikler:**
- ✅ Kendi rezervasyonları görüntüleme
- ✅ Self check-in
- ✅ Digital key
- ✅ Upsell mağazası
- ✅ Service request
- ⛔ Diğer misafir bilgileri
- ⛔ Operasyonel veriler

---

## Detaylı Yetki Tablosu

### Modül Bazlı Erişim Matrisi

| Modül/Özellik | Admin | Supervisor | Front Desk | Housekeeping | Sales | Finance | Staff | Guest |
|---------------|-------|------------|------------|--------------|-------|---------|-------|-------|
| **RESERVATIONS** |
| Rezervasyon Oluşturma | ✅ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ | ⛔ |
| Rezervasyon Görüntüleme | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ | ⛔ | ✅* |
| Rezervasyon Değiştirme | ✅ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ | ⛔ |
| Rezervasyon İptal | ✅ | ✅ | ⚠️ | ⛔ | ⚠️ | ⛔ | ⛔ | ⛔ |
| Rate Override | ✅ | ⚠️ | ⛔ | ⛔ | ⚠️ | ⛔ | ⛔ | ⛔ |
| **CHECK-IN/OUT** |
| Check-in İşlemi | ✅ | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ✅* |
| Check-out İşlemi | ✅ | ✅ | ✅ | ⛔ | ⛔ | ⚠️ | ⛔ | ⛔ |
| Oda Değişikliği | ✅ | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| Force Checkout | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| **FOLIO/BILLING** |
| Folio Görüntüleme | ✅ | ✅ | ✅ | ⛔ | ⛔ | ✅ | ⛔ | ✅* |
| Charge Posting | ✅ | ✅ | ⚠️ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| Payment Posting | ✅ | ✅ | ✅ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| Charge Void | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| Folio Transfer | ✅ | ✅ | ⚠️ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| Folio Close | ✅ | ✅ | ⚠️ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| **HOUSEKEEPING** |
| Oda Durumu Güncelleme | ✅ | ✅ | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| Task Atama | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| Task Tamamlama | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ | ⚠️* | ⛔ |
| Housekeeping Board | ✅ | ✅ | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| **REPORTS** |
| Daily Flash Report | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ | ⛔ | ⛔ |
| Financial Reports | ✅ | ⚠️ | ⛔ | ⛔ | ⚠️ | ✅ | ⛔ | ⛔ |
| Market Segment Report | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ | ⛔ | ⛔ |
| Company Aging Report | ✅ | ⚠️ | ⛔ | ⛔ | ✅ | ✅ | ⛔ | ⛔ |
| Housekeeping Efficiency | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| Export to CSV | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| **USER MANAGEMENT** |
| Kullanıcı Oluşturma | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| Kullanıcı Düzenleme | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| Rol Atama | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| Audit Log Görüntüleme | ✅ | ⚠️ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| **ACCOUNTING** |
| Invoice Oluşturma | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| E-Fatura Generate | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| Currency Management | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| Tax Configuration | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| **RMS (REVENUE)** |
| Pricing Recommendations | ✅ | ✅ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ | ⛔ |
| Competitor Analysis | ✅ | ✅ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ | ⛔ |
| Demand Forecast | ✅ | ✅ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ | ⛔ |
| Auto-Pricing | ✅ | ⚠️ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| **MARKETPLACE** |
| Purchase Order Oluşturma | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| PO Onaylama | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| Inventory Yönetimi | ✅ | ✅ | ⛔ | ⚠️ | ⛔ | ⛔ | ⛔ | ⛔ |
| Supplier Yönetimi | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |

**Lejant:**
- ✅ = Tam Yetki
- ⚠️ = Sınırlı Yetki / Onay Gerekli
- ⛔ = Erişim Yok
- ✅* = Sadece kendi kayıtları
- ⚠️* = Sadece atanan task'lar

---

## Departman Bazlı Erişim

### Front Office Department
**Roller:** ADMIN, SUPERVISOR, FRONT_DESK

**Günlük İşlemler:**
```
06:00 - Night Audit close
07:00 - Check-out başlangıç
14:00 - Check-in başlangıç
15:00 - Room assignment peak
22:00 - Late arrivals
```

**Özel Yetkiler:**
- Early check-in: Supervisor approval
- Late check-out: Supervisor approval
- Rate override >10%: Manager approval
- No-show fee waive: Supervisor approval

---

### Housekeeping Department
**Roller:** ADMIN, SUPERVISOR, HOUSEKEEPING, STAFF

**Günlük İşlemler:**
```
07:00 - Task assignment
08:00 - Cleaning starts
12:00 - Due-out priority
14:00 - Arrivals preparation
16:00 - Final inspection
```

**Özel Yetkiler:**
- Room status override: Supervisor only
- Out of order rooms: Supervisor approval
- Task reassignment: Supervisor only

---

### Finance Department
**Roller:** ADMIN, FINANCE

**Günlük İşlemler:**
```
09:00 - A/R review
10:00 - Invoice generation
14:00 - Payment posting
16:00 - Daily reconciliation
17:00 - Reports preparation
```

**Özel Yetkiler:**
- Charge void >$100: Manager approval
- Credit limit increase: CFO approval
- Bad debt write-off: GM approval

---

### Sales & Marketing
**Roller:** ADMIN, SALES

**Günlük İşlemler:**
```
09:00 - Lead follow-up
10:00 - Rate quotation
14:00 - Contract negotiation
15:00 - Group booking coordination
16:00 - Market analysis
```

**Özel Yetkiler:**
- Contracted rate >20% off: Manager approval
- Group block >20 rooms: Manager approval
- Credit terms: Finance approval

---

## Yetki Değişikliği Prosedürü

### 1. Yeni Kullanıcı Oluşturma

**Adımlar:**
1. Admin paneline giriş yapın
2. User Management → Create User
3. Gerekli bilgileri doldurun:
   - Full Name
   - Email
   - Department
   - Role
   - Employee ID
4. Initial password: `Welcome123!`
5. "Force Password Change" seçeneğini aktif edin
6. Save User

**Audit Log Kaydı:**
```json
{
  "action": "CREATE_USER",
  "user_id": "admin-123",
  "target_user": "john.doe@hotel.com",
  "changes": {
    "role": "front_desk",
    "department": "Front Office",
    "active": true
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### 2. Rol Değiştirme

**Adımlar:**
1. User Management → Select User
2. Edit User Information
3. Change Role dropdown
4. Add change reason (mandatory)
5. Save Changes
6. Notify user via email

**Audit Log Kaydı:**
```json
{
  "action": "UPDATE_USER_ROLE",
  "user_id": "admin-123",
  "target_user": "john.doe@hotel.com",
  "changes": {
    "old_role": "front_desk",
    "new_role": "supervisor",
    "reason": "Promotion to Front Office Supervisor"
  },
  "timestamp": "2025-01-15T14:20:00Z"
}
```

---

### 3. Kullanıcı Deaktivasyonu

**Ne Zaman:**
- Personel işten ayrılması
- Uzun süreli izin
- Security concern

**Adımlar:**
1. User Management → Select User
2. Status → Inactive
3. Add deactivation reason
4. Session'ları sonlandır
5. Access revoke

**Audit Log Kaydı:**
```json
{
  "action": "DEACTIVATE_USER",
  "user_id": "admin-123",
  "target_user": "john.doe@hotel.com",
  "changes": {
    "active": false,
    "reason": "Employee resignation",
    "last_login": "2025-01-14T18:30:00Z"
  },
  "timestamp": "2025-01-15T16:00:00Z"
}
```

---

## Güvenlik Politikaları

### Password Kuralları
- Minimum 8 karakter
- En az 1 büyük harf
- En az 1 küçük harf
- En az 1 rakam
- 90 günde bir değişiklik zorunlu
- Son 3 password tekrar kullanılamaz

### Session Yönetimi
- Otomatik logout: 30 dakika inaktivite
- Concurrent session limit: 1 device
- Login attempt limit: 5 başarısız deneme
- Account lock duration: 30 dakika

### Audit Trail
- Tüm kritik işlemler loglanır
- Log retention: 2 yıl
- Immutable logs (değiştirilemez)
- Daily backup

---

## Yardım ve Destek

**Yetki ile ilgili sorunlar için:**
- IT Support: support@hotel.com
- Extension: 100
- Emergency: +1-555-0100

**Dokümantasyon güncellenme tarihi:** 15 Ocak 2025
