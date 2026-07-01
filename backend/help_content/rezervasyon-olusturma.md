# Rezervasyon Oluşturma

## Yeni Rezervasyon

**Rezervasyon > Yeni** veya takvim üzerinde boş bir hücreye tıklayarak yeni rezervasyon penceresi açılır.

### Zorunlu Alanlar

- **Misafir adı, soyadı**
- **Telefon veya e-posta**
- **Giriş ve çıkış tarihi**
- **Oda tipi** (otomatik müsait olanlar listelenir)
- **Yetişkin sayısı**
- **Ödeme şekli**

### Opsiyonel

- Oda numarası (boş bırakılırsa night audit'te otomatik atanır)
- Çocuk sayısı + yaşları
- Özel istekler
- Acente bilgisi
- Diyet kısıtları

## Çift Rezervasyon Koruması

Sistem, aynı oda için tarih çakışan rezervasyon kayda izin vermez. Çakışma durumunda kullanıcıya 409 hatasıyla mevcut rezervasyon detayı gösterilir.

## Hızlı Aksiyonlar

- **Geçici Tutma (Hold)**: 30 dakika boyunca oda kilitlenir, müşteri telefonda karar verirse kullanışlıdır.
- **Garantili / Garantisiz**: kredi kartı garantisi olmayan rezervasyonlar 18:00'a kadar tutulur, sonra serbest bırakılır.
- **Grup Rezervasyon**: 5+ oda için **Grup Rezervasyon** sekmesi kullanılır.
