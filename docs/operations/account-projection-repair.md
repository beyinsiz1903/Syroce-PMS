# Cari kaynak farkları ve yönetici performans göstergeleri

## Günlük performans kapsamı

`GET /api/reports/daily-flash` yanıtındaki `performance`, rapor iş gününde
gerçekten geceleyen, aktif fiziksel odaya bağlı rezervasyonları kullanır.
Kişi sayısı, oda sayısı, geliş sayısı veya tahsilat payı değildir.
İptal/no-show, henüz giriş yapmamış kayıtlar, çıkış günü, sanal ve pasif
odalar hariçtir. Ortalama süre aynı rezervasyonların tam planlanan kalış
gecelerinin ortalamasıdır; geçen süre değildir.

OTA/doğrudan/acente/belirsiz paylarının paydası aynı rezervasyon sayısıdır.
Bilinen OTA kaynağı ithal edilen varsayılan `direct` değerinden önceliklidir.
Yalnız Exely/HotelRunner gibi kanal yöneticisi adı biliniyorsa OTA veya direkt
kanal uydurulmaz. Kayıt yoksa oran ve ortalama `null`; arayüzde `—` görünür.
Ölçülmeyen departmanların durumu “Operasyonel” gibi onaylanmış gösterilmez.

## Kaynak-bakiye farkı

Bu sürüm mevcut finansal hareketleri otomatik değiştirmez. İki eski Demo
kaydında bulunan farklar kaynakların doğruluğu/eksiksizliği incelendikten
sonra **yalnız türetilmiş hesap bakiyesi** yenilenerek giderilebilir.
Eksik kaynak ihtimali varsa bu yol kullanılmamalı; asıl belgenin düzeltilmesi
veya eksik açılış/aktarım geçmişinin kanıtlı tamamlanması gerekir.

Normal yetkili iş akışı:

1. Genel Müdür ekranında **Bekleyen AR → Cari kaynak farklarını incele**.
   Düğme yalnız admin/super_admin kullanıcıya ve kaynak-bakiye farkı varsa görünür.
2. Doğru hesabı seçip kayıtlı bakiye, kaynak bakiyesi ve hareket sayısını oku.
3. Hesap ekstresini/kaynak dökümünü bağımsız olarak incele. Tam ve doğru
   olduğunu kabul etmiyorsan uygulama. Bu ekran tek başına mali belge değildir.
4. Anlamlı gerekçe ve incelenen kaynak belge/döküm referansını yaz; açık
   kaynak doğruluğu onayını ver; yeniden kurma düğmesine bas.
5. Yenilenen finans özetinde kaynak farkını, para birimlerini ve yaşlandırma
   uyarılarını kontrol et. Vadesi belirsiz alacak hâlâ ayrı gösterilir.

API:

- `GET /api/pms/account-projections/{source}/{account_id}/preview`
- `POST /api/pms/account-projections/{source}/{account_id}/repair`
- Kaynaklar: `cari_accounts`, `city_ledger_accounts`.
- Uygulama gövdesi: UUID `request_id`, önizlemedeki `source_fingerprint`,
  `reason`, `source_review_reference`, `confirm_sources_authoritative: true`.
  Kullanıcının seçebileceği serbest bakiye/tutar alanı yoktur.
- Önizleme mali okuma/ödeme yetkisi ister. Uygulama ayrıca sistem yönetimi
  yetkisi (`manage_night_audit` / SYSTEM_SETTINGS) ister; süperadmin bypass'ı yok.
- Kaynaklar veya hesap önizlemeden sonra değişirse 409 döner; yeniden incele.
- Cevap kaybolursa aynı UUID ve aynı içerikle tekrar kontrol et. Farklı
  içerikle UUID tekrarı 409'dur. Sonuç ve değişiklik tek transaction'dadır.

Yeniden kurma ödeme, iade, gelir, borç silme, ikram veya yevmiye üretmez.
Kaynak satırları değişmez. Negatif kaynak bakiyesi müşteri alacağıdır;
sıfıra kırpılmaz, başka hesabın borcuna otomatik mahsup edilmez. Yeni doğrudan
borç bu kredi bakiyesini tüketebilir; aynı hesabın limit/tenant kontrolleri kalır.

Audit: `account_projection_rebuilt`. Önceki bakiyeler, kaynak parmak izi,
sonraki bakiye, para birimi, kullanıcı, gerekçe, belge referansı ve istek
kimliği kayıtlıdır. Gerekçe ve önce/sonra değerleri hash zincirinin mühürlü
snapshot alanlarına da alınır. Zincir kurulamazsa bakiye ve işlem makbuzu
birlikte geri alınır; zincirsiz “başarı” verilmez.

Belirsiz/eksik kaynak geçmişi, bekleyen işlem, çoğul kimlik, geçersiz tutar
ve farklı para birimli kaynaklar otomatik yeniden kurmayı engeller.
Tesisler arası veri veya başka hesaplara toplu düzeltme yapılmaz.
