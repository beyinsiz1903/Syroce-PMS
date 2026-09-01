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
- **CSV** olarak indirilebilir (KTB web giriş ekranına aktarma için uygun)
- **PDF** olarak yazdırılabilir

## Gönderim

Her ayın 1-10'u arasında [KTB Konaklama İstatistikleri Sistemine](https://is.kultur.gov.tr/public/login.xhtml) giriş yapıp ekrandaki form alanlarına rapor değerlerini girin. Syroce resmî portalda otomatik onay veya gönderim yapmaz.

Ay sonunda tesiste kalmaya devam eden ziyaretçiler Bakanlık kuralına göre ay sonunda çıkmış, takip eden ayın 1'inde yeniden giriş yapmış kabul edilir. Syroce "Ay Başında Devreden" sayacını bu kuralla hesaplar.

## İpuçları

- "Belirtilmemiş" uyruk hücresi 0 olmalıdır; aksi takdirde check-in sırasında uyruk girilmeyen misafirler vardır.
- Aylık raporu kapanmadan önce **gece denetimi (night audit)**'in tüm günler için tamamlanmış olduğundan emin olun.
