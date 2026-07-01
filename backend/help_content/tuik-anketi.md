# TÜİK Aylık Konaklama İstatistikleri

Türkiye İstatistik Kurumu (TÜİK), turizm konaklama tesislerinden aylık olarak doluluk, gelen turist sayısı ve uyruk dağılımı verisi ister. Syroce PMS bu raporu otomatik üretir.

## Rapor İçeriği

- **Oda kapasitesi** (toplam oda, toplam yatak)
- **Aylık doluluk oranı** (oda gece × satılan / oda gece × kapasite)
- **Toplam geceleme** (yerli + yabancı)
- **Uyruk dağılımı** (ilk 20 ülke + diğer)
- **Ortalama kalış süresi**
- **Çift kişi başı geceleme**

## Üretme

**Raporlar > Mevzuat Raporları > TÜİK Aylık** sekmesinden dönemi seçin ve "Raporu Hesapla" butonuna basın. Çıktı:

- **Ekranda tablo** olarak görüntülenir
- **CSV** olarak indirilebilir (TÜİK web giriş ekranına yapıştırma için uygun)
- **PDF** olarak yazdırılabilir

## Gönderim

TÜİK'in **e-Anket** sistemine giriş yapıp ekrandaki form alanlarına bu raporun değerlerini girebilirsiniz. Sistem, anket dönem bitiş tarihinden 3 gün önce kullanıcıyı uyarır.

## İpuçları

- "Belirtilmemiş" uyruk hücresi 0 olmalıdır; aksi takdirde check-in sırasında uyruk girilmeyen misafirler vardır.
- Aylık raporu kapanmadan önce **gece denetimi (night audit)**'in tüm günler için tamamlanmış olduğundan emin olun.
