# RoomOps PMS - Yönetici Kılavuzu

## İçindekiler
1. [Giriş ve İlk Kurulum](#giriş)
2. [Dashboard Kullanımı](#dashboard)
3. [Oda Yönetimi](#oda-yönetimi)
4. [Rezervasyon Yönetimi](#rezervasyon)
5. [Misafir Yönetimi](#misafir)
6. [Raporlama](#raporlama)
7. [Ayarlar](#ayarlar)
8. [Güvenlik](#güvenlik)

---

## 1. Giriş ve İlk Kurulum

### Sisteme Giriş
1. Web tarayıcınızda RoomOps PMS adresine gidin
2. E-posta adresinizi ve şifrenizi girin
3. "Giriş Yap" butonuna tıklayın
4. 2FA aktifse, doğrulama kodunuzu girin

### İlk Kurulum Adımları
1. **Otel Bilgileri**: Ayarlar > Otel Bilgileri'nden otel adı, adres, telefon bilgilerini girin
2. **Oda Tanımları**: PMS > Odalar'dan oda tiplerini ve odaları ekleyin
3. **Fiyat Tanımları**: Merkezi Fiyatlandırma'dan oda tiplerinin fiyatlarını belirleyin
4. **Kullanıcı Oluşturma**: Ayarlar > Kullanıcılar'dan personel hesaplarını oluşturun

## 2. Dashboard Kullanımı

### Ana Dashboard
- **Doluluk Oranı**: Günlük doluluk yüzdesi
- **Bugünkü Check-in/Check-out**: Beklenen varış ve ayrılış sayıları
- **Gelir Özeti**: Günlük/Haftalık/Aylık gelir
- **Oda Durumu**: Müsait, dolu, temizlik bekleyen oda sayıları

### Merkez Ofis Dashboard (Zincir Oteller)
- Tüm otellerin konsolide KPI'ları
- Otel bazında doluluk karşılaştırması
- Zincir genelinde gelir raporu
- Uyarılar (düşük doluluk, bakım birikimi)

## 3. Oda Yönetimi

### Oda Ekleme
1. PMS > Odalar menüsüne gidin
2. "Yeni Oda Ekle" butonuna tıklayın
3. Oda numarası, tipi, kat, fiyat bilgilerini girin
4. Kaydedin

### Oda Durumu Güncelleme
- **Müsait**: Misafir kabul edebilir
- **Dolu**: Check-in yapılmış
- **Temizlik**: Temizlik bekliyor
- **Bakım**: Bakımda/Devre dışı

## 4. Rezervasyon Yönetimi

### Yeni Rezervasyon
1. Takvim veya Rezervasyonlar sayfasından "Yeni" butonuna tıklayın
2. Misafir bilgilerini girin (veya mevcut misafiri seçin)
3. Tarih aralığını, oda tipini, fiyatı seçin
4. Onaylayın

### Check-in İşlemi
1. Rezervasyonu bulun
2. "Check-in" butonuna tıklayın
3. Kimlik bilgilerini doğrulayın
4. Oda ataması yapın
5. Onaylayın

### Check-out İşlemi
1. Aktif konaklamayı bulun
2. "Check-out" butonuna tıklayın
3. Folio'yu kontrol edin
4. Ödeme durumunu onaylayın
5. İşlemi tamamlayın

## 5. Misafir Yönetimi

### Misafir Profili
- Kişisel bilgiler (ad, e-posta, telefon)
- Geçmiş konaklamalar
- Tercihler ve notlar
- VIP durumu
- KVKK onay durumu

### Cross-Property Profil
- Zincirinize ait tüm otellerdeki konaklamaları görüntüleyin
- Toplam harcama ve gece sayısı
- Birleşik misafir profili

## 6. Raporlama

### Mevcut Raporlar
- Doluluk raporu (günlük/haftalık/aylık)
- Gelir raporu
- Misafir istatistikleri
- Housekeeping raporu
- Finansal özet

## 7. Ayarlar

- Otel bilgileri
- Kullanıcı yönetimi
- Rol ve yetki atama
- Abonelik planı
- Bildirim tercihleri

## 8. Güvenlik

### 2FA Kurulumu
1. Profil > Güvenlik > 2FA Ayarları
2. "2FA Etkinleştir" butonuna tıklayın
3. QR kodu Google Authenticator ile tarayın
4. Doğrulama kodunu girin
5. Yedek kodlarınızı güvenli yere kaydedin

### IP Erişim Kontrolü
1. Ayarlar > Güvenlik > IP Kuralları
2. Beyaz listeye güvenilir IP adreslerini ekleyin
3. Kara listeye şüpheli IP adreslerini ekleyin
