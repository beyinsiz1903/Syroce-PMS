# Otel kullanıcısı erişim yönetimi

## Kullanım

Otel yöneticisi **Ayarlar → Ekip → Kullanıcıya özel modül ve sayfa
yetkilerini düzenle** bağlantısını açar. Kullanıcı listesindeki **Yetkileri
düzenle** eylemi üç katmanı yönetir:

1. Modül erişimi.
2. Modül içindeki sayfa grupları (20 grup; aynı ekranın eski/yeni URL'leri
   ve PMS sekmeleri birlikte değerlendirilir).
3. Role ek operasyon izinleri. Örneğin rapor görüntüleme, ödeme kaydetme
   yetkisi değildir. Eksik işlem izinleri editörde belirtilir.

Ekran açılması, paketin satın alınmış olması ve endpointin işlem/nesne
kontrollerini geçme gerekliliğini kaldırmaz. Bazı yönetim ekranları ayrıca
rol kontrolüne tabidir; modül seçimi bunları yönetici olmayanlara açmaz.

## Rol incelemesi

| Rol | Varsayılan operasyon alanları | Temel sınırlar |
| --- | --- | --- |
| super_admin | Platform ve otel yönetimi | Platform rolü otel editöründen verilemez |
| admin | Otel modülleri ve kullanıcı yönetimi | Otel kapsamı ve paket kısıtları korunur |
| supervisor | Geniş operasyon, rapor, İK, gün sonu | Admin kullanıcı yönetimi ve otomatik gün sonu ayarları yok |
| front_desk | Ön büro, takvim, rezervasyon, misafir, kasa, gece denetimi, iletişim | Genel muhasebe, İK ve yönetici ayarları varsayılan kapalı |
| housekeeping | Kat hizmetleri ve görevler | Tahsilat, muhasebe, yönetici ayarları yok |
| sales | Satış ve operasyon raporları | Tahsilat, gün sonu, yönetici ayarları yok |
| finance | Kasa, muhasebe, fatura, rapor, İK okuma, gece denetimi okuma | Gün sonu çalıştırma ve İK yönetimi varsayılan yok |
| procurement | Satınalma ve stok | Ön büro, kasa, gün sonu varsayılan kapalı |
| staff | Açık operasyon modülü yok | Admin kullanıcıya gereken modülleri/sayfaları/işlemleri verir |
| call_center_agent | İletişim merkezi | Muhasebe ve yönetici işlemleri yok |
| guest | Otel iç operasyon modülleri yok | Misafir portalı ayrı akış |
| agency_admin | Otel iç operasyon modülleri yok | Acente portalı ayrı akış |
| agency_agent | Otel iç operasyon modülleri yok | Acente portalı ayrı akış |

Tablo özet niteliğindedir. Backend kataloğunun döndürdüğü rol matrisi,
mevcut Permission enum/ROLE_PERMISSIONS ve modül varsayılanlarından üretilir;
editörde tüm işlem izinleri görülebilir. Geniş modül kapsamı her işlemi
yapabilme anlamına gelmez. UI'da olup backend enum'unda bulunmayan
revenue/maintenance/fnb/spa/concierge/night_auditor rol seçenekleri kaldırıldı;
bu departmanlar personel rolü ve kullanıcıya özel erişim kullanabilir.

## Güvenlik ve çalışma şekli

- Kendi hesabı, admin/platform yöneticisi ve misafir/acente portal hesapları
  bu editörle değiştirilemez; yanlışlıkla yönetici kilitlemesi önlenir.
- Hedef kullanıcı hem kimlik hem otel kimliğiyle aranır.
- İzinler yalnızca tanımlı katalog/izin listesi içinden seçilebilir.
- Eşzamanlı admin değişiklikleri revision/CAS ile 409 döner.
- Değişiklik isteği eski/yeni değerlerle yazma öncesinde denetim kaydına
  alınır; denetim kaydı yazılamazsa izin değişikliği uygulanmaz.
- Başarıda kullanıcı yetki önbelleği mevcut invalidation mekanizmasıyla
  temizlenir. API'nin mevcut kullanıcı önbelleği TTL'i 30 saniyedir; dağıtık
  invalidation arızasında bu gecikme dikkate alınmalıdır.
- Arayüz açılışta, odaklanınca ve görünürken 60 saniyede bir /auth/me ile
  yenilenir; izin değişince uygulama veri önbellekleri temizlenir.
- Menü, dashboard modül kartı, modül keşfi, arama, PMS sekmesi ve doğrudan
  rota erişimi aynı frontend erişim yardımcılarını kullanır.
- Katalogdaki API kaynakları get_current_user içinde değerlendirilir;
  cached endpoint gövdesine girmeden sayfa erişimi kontrol edilir.
- Paylaşılan oda/rezervasyon/misafir kaynakları izinli başka bir ekran için
  gerekli olabilir. Oda sayfasını kapatmak, takvim açıkken takvimin oda
  isimlerini okuyamaması anlamına gelmez. İşlem/otel kontrolleri korunur.
- Önceden var olan endpoint operasyon kontrolleri kaldırılmadı. Eski kasa,
  folyo, rezervasyon ve rapor gövde kontrolleri kullanıcıya özel ek izinleri
  dikkate alacak şekilde uyumlandı.

## Kapsam ve doğrulama sınırı

Bu çalışma tüm endpointlere yeni bir yetki modeli uygulandığı iddiasında
değildir. Katalog dışındaki API'ler mevcut rol/modül/nesne korumalarını
kullanmaya devam eder. Sınıflandırılmamış korumalı UI sayfaları sıradan
personele varsayılan olarak kapalıdır. Yeni sayfa eklenirken katalog/rota
eşlemesi ve endpoint yetki testi birlikte eklenmelidir.

Testler ayrı test verileri/mocks ile çalıştırılır. Canlı kullanıcı izinleri,
rezervasyonlar ve otel verileri değiştirilmez; PR'nin merge/deploy edilmesi
ayrı bir adımdır. Canlı ortamda her rolün gerçek hesabıyla uçtan uca kabul
testi bu kod testlerinin yerine geçmez ve henüz yapılmamıştır.
