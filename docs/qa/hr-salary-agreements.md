# Ücret anlaşmaları — 7 Eylül 2026

## Kullanım ve kapsam

Personel Yönetimi → Düzenle → Ücret anlaşması: aylık/saatlik ve net/brüt.
Net ve brüt karşılığı sunucudaki tek hesaplayıcıdan otomatik gösterilir.
Yetki: manage_hr; önizleme salt okunur, bordro veya muhasebe fişi oluşturmaz.

Standart özel sektör 4/a, 45 saat/hafta, emekli olmayan çalışan, TRY, 2026, aynı ay tek
toplu ücret tahakkuku kapsamındadır. Kullanıcı bu profili açıkça doğrular.
SGDP, stajyer, engellilik/şahıs sigortası/sendika indirimi, BES, özel yardım
istisnaları, geçmiş dönem SGK prim devri ve işveren maliyeti hesaplanmaz.
Bu sürüm bir yasal beyanname/SGK gönderim sistemi değildir.

Gerçek açılış GV matrahı ve asgari ücret istisna matrahı önceki bordro/devir
belgesinden girilir; kaynak notu zorunludur. Boş giriş sıfır sayılmaz.
Eski yaklaşık bordrolardan gerçek matrah türetilmez. Ocakta önceki yıl matrahı
taşınamaz. Kaydedilen bağlam yalnız seçili ay için geçerlidir; sonraki ay
matrah/gün/saat tekrar doğrulanmadan hesap engellenir. Otomatik matrah devri
bu değişiklikte yoktur. Önizleme girdinin doğruluğunu dış kaynaktan doğrulayamaz.

Aylık tutar 30 günlük anlaşmadır; doğrulanmış SGK/ücret günü ile orantılanır.
Ücretsiz izin günleri bu güne önceden yansıtılmalıdır; çelişki bloklanır.
Saatlik anlaşmada ücretli normal saat + onaylı mesainin devam toplamıyla eşleşmesi
istenir. Mesai ikinci kez normal saat olarak girilirse hesap bloklanır.
Ücretli izin saatlerinin kayıt düzeni de personel bazında doğrulanmalıdır.
Aylık anlaşmada devam kaydı olmasa da ücret satırı oluşturulur.

Onaylı mesai %50 zamla, aylık anlaşmada 30 × 7,5 saat üzerinden hesaplanan
saat ücretinden eklenir. Net anlaşma önce temel dönem ücreti için brütleştirilir;
ek brüt prim/mesai sonra aynı ay matrahına dahil edilerek vergi bir kez hesaplanır.
Avans/diğer kesinti vergi sonrasında düşer. Yemek/yolun istisna şekli belirsiz
olduğu için yeni model bu ekleri bloklar. SGK tavanını aşan prim sonraki aylara
devir gerektirebildiğinden bloklanır. SGK tabanı altındaki ücret de işveren
tarafından karşılanan farkı hatalı işçi kesintisine çevirmek yerine reddedilir.

## Hesap yöntemi ve birincil kaynaklar

- Decimal ve ROUND_HALF_UP, kuruş hassasiyeti; net→brüt kuruş üzerinde arama.
- Ücret gelirleri için 2026 kademeli tarife; dönem vergisi toplam matrah vergisi
  farkından hesaplanır. [GİB 2026 tarifesi](https://cdn.gib.gov.tr/api/gibportal-file/file/getFileResources?objectKey=arsiv/yardim-kaynaklar/yararli-bilgiler/gelir-vergisi-tarifeleri/gelir-vergisi-tarifesi-2026.pdf).
- SGK işçi %14, işsizlik %1; brüt asgari ücret 33.030 TL.
  [ÇSGB 2026 hesabı](https://www.csgb.gov.tr/Media/gm2fekds/asgari-%C3%BCcret-2026.pdf).
- SGK günlük tavan 9.909 TL, aylık tavan 297.270 TL.
  [SGK 2026 prime esas kazanç sınırları](https://www.sgk.gov.tr/Content/Post/2e0c9e1a-2cfe-4456-af10-49d3de0c58ba/Prime-Esas-Kazanc-Miktarlari-2026-01-14-10-35-39).
- Asgari ücret istisnası gerçek hesaplanan vergiyi aşamaz; kıst ayda tam uygulanır,
  çoklu işverende aynı istisna mükerrer uygulanamaz.
  [GİB ücret istisnaları açıklaması](https://gib.gov.tr/mevzuat/kanun/433/ozelge/21388),
  [GİB 2026 ücret rehberi](https://cdn.gib.gov.tr/api/gibportal-file/file/getFile?objectKey=DUYURU%2FUNIVERSAL%2F2026%2F2026_Ucret_Geliri.pdf).
- Damga binde 7,59; asgari ücret istisnası dikkate alınır.
  [Kamu kurumu 2026 oran tablosu](https://strateji.erdogan.edu.tr/Files/Images/damga-vergisi-oranlari-212026091729.pdf).
- 45 saat/hafta için aylık ücretin saatliğe dönüşümünde 225 saat esası.
  [ÇSGB teftiş raporu](https://www.csgb.gov.tr/medias/6048/2014_63.pdf).

## Veri güvenliği ve uyumluluk

Mevcut personel zorla dönüştürülmez. Gerçek matrah tanımlanmayanlar legacy_approximate
etiketiyle kalır; önizleme uyarı gösterir. Tenant'ın eski sabit oran override'ları
yeni gerçek modelde kullanılmaz. Kilitli bordrolar değiştirilmez; yeni taslakta
hesap sürümü, anlaşma ve matrah bileşenleri snapshot içinde saklanır.
Ücret/matrah nesneleri personel PII ve departman-only yanıtlarında gizlenir;
genel audit before/after içine ham maaş/matrah yazılmaz. CSV/JSON ihracatı
bordro yetkisi olmadan reddedilir. Eski saatlik zam endpoint'i yeni anlaşmalı
personeli sessizce değiştiremez.

## Doğrulama sınırları

Yerel doğrulamalar: tarife sınırları, net/brüt geri dönüşü, asgari ücret,
SGK tavanı, kısmi ay, eksik/geçersiz matrah, ay/yıl kilidi, MongoDB personel
güncelleme, mesai/prim vergisi, tenant ayrımı, kilitli snapshot korunması,
PII maskeleri ve yetkisiz CSV/JSON reddi. Arayüzde otomatik önizleme, seçenekler,
eski sonucun temizlenmesi, hata gösterimi ve sekme navigasyonu test edilir.
Üretim build'i ve hedefli Ruff / diff kontrolü çalıştırılır.

Geniş taramada 7 mevcut HTTP gece-vardiyası testi localhost:8000 servisi açık
olmadığından bağlantı hatası verdi; bu testler geçmiş gibi raporlanmaz ve
çalışan izole regresyon grubundan ayrı tutulur. Openpyxl UTC deprecation ve
Browserslist veri yaşı uyarıları mevcut bağımlılıklardan gelir.

Testler gerçek üretim veritabanına bağlanmaz; Mongo senaryoları geçici localhost
replica set kullanır. Canlı Operator oturumu erişilebilir. Aynı test oteline ait
farklı rol oturumları sağlanmadığından canlı rol matrisi tamamlanmış sayılmaz.
Canlı CSV/XLSX indirmesinin dosya içeriği tarayıcı aracı üzerinden yakalanamadı;
yerel içerik/parite testleri canlı indirme kanıtı değildir. Yeni ücret kodunun
canlı uçtan uca doğrulaması PR merge ve deployment sonrasında yapılmalıdır.
