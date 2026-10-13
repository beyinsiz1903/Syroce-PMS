# Acente fiyat politikası ve kurtarma

- Temel fiyat varsayılan olarak kapalıdır. Otel sözleşme onayında açıkça
  izin verebilir. Eski portalda Acente Yönetimi → acenteyi genişlet → Sözleşme
  fiyat politikası üzerinden mevcut sözleşmenin izni kaydedilir.
- Arama ve rezervasyon aynı tarih aralığını kapsayan aktif sözleşmeyi kullanır.
  Hiç takvim ürünü yoksa BASE yalnız açık izinle üretilir. Mevcut dağıtılmış
  ürünlerde eksik gece, stop-sell ve minimum konaklama korumaları devam eder.
- Değişiklik tamamlanınca teklif üzerinde uygulanan ürün/finansal durumun
  kopyası tutulur. Bu kayıt ancak PMS, marketplace ve oda/gece işlemlerinden
  sonra yazılır. Kurtarma, iki rezervasyon kaydını bu kanıtla karşılaştırır.
  Eski veya yarım değişiklikte kanıt yoksa kilit açılmaz; operatör kayıtları
  uzlaştırmalıdır. Bu sürüm yarım değişikliği otomatik yeniden fiyatlandırmaz
  veya otomatik geri almaz.
- Kilit silinmeden önce denetim kaydı kalıcılaştırılır. Silme cevabı veya son
  durum yazımı kaybolursa pending_release kaydı kurtarma ekranında görünür.
  Tekrar çağrı eski owner için denetim kaydını tamamlar; aynı ilişkiye ait yeni
  owner kilidine dokunmaz. Tamamlanmış çağrı yeniden gönderilebilir.
- Her kilit açma için özgün yazıcının durduğunun operatör tarafından
  doğrulanması zorunludur. Süre dolması serbest bırakma gerekçesi değildir.
