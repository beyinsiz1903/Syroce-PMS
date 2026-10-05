# KTB Aylık Konaklama İstatistikleri

Kültür ve Turizm Bakanlığı, belgeli konaklama tesislerinden bir önceki aya ait tesise geliş ve geceleme verilerini ister. Syroce PMS bu raporu Bakanlığın ay sınırı kuralıyla üretir.

## Rapor İçeriği

- **Oda kapasitesi** (toplam oda, toplam yatak)
- **Aylık doluluk oranı** (oda gece × satılan / oda gece × kapasite)
- **Tesise geliş** (yerli + yabancı)
- **Toplam kişi-gece** (yerli + yabancı)
- **Uyruk dağılımı** (ilk 20 ülke + diğer)
- **Ortalama kalış süresi**
- **Çift kişi başı geceleme**

## Üretme

**Raporlar > Mevzuat Raporları > KTB Aylık Konaklama** sekmesinden dönemi seçin ve "Raporu Hesapla" butonuna basın. Ekran varsayılan olarak bir önceki ayı açar. Çıktı:

- **Ekranda tablo** olarak görüntülenir
- **CSV** olarak indirilebilir
- TGA v6 aylık API gönderimi aynı ekranda önizlenebilir
- **PDF** olarak yazdırılabilir

## Gönderim

TGA API ayarlarında TGA tarafından verilen `X-API-Key` ile resmî il ve ilçe kodlarını kaydedin. Ardından aylık rapor ekranında vergiler hariç net ortalama oda fiyatını EUR olarak girip v6 gönderim gövdesini önizleyin. Syroce yalnız kullanıcı ayrıca onayladığında `POST /tesis-aylik-rapor/` üzerinden gönderir; arka planda onaysız resmî bildirim yapmaz.

TGA v6 artık tesis belge numarası veya vergi numarasını payload içinde kullanmaz. Tesis Syroce tarafından üretilen sabit UUID ile anonim olarak tanımlanır.

Ay sonunda tesiste kalmaya devam eden ziyaretçiler Bakanlık kuralına göre ay sonunda çıkmış, takip eden ayın 1'inde yeniden giriş yapmış kabul edilir. Syroce "Ay Başında Devreden" sayacını bu kuralla hesaplar.

## İpuçları

- "Belirtilmemiş" uyruk hücresi 0 olmalıdır; aksi takdirde check-in sırasında uyruk girilmeyen misafirler vardır.
- Aylık raporu kapanmadan önce **gece denetimi (night audit)**'in tüm günler için tamamlanmış olduğundan emin olun.
