# Konaklama Vergisi Beyannamesi

Türkiye'de **7194 sayılı Kanun** uyarınca konaklama vergisi, takip eden ayın **26'sına kadar** elektronik ortamda beyan edilip ödenir. Syroce PMS, bu süreci tek ekrandan yönetmenizi sağlar.

## Vergi Oranı

Varsayılan oran **%2**'dir (KDV hariç matrah üzerinden). Diplomatik temsilcilik mensupları, öğrenci yurdu, sağlık tesisleri gibi muafiyetler vardır.

## Aylık İş Akışı

1. **Yapılandırma** sekmesinden vergi oranını ve muafiyet listesini kontrol edin.
2. Ay sonunda **Aylık Rapor** sekmesinden dönemi seçip "Raporu Hesapla" butonuna basın. Sistem oda satırlarını otomatik toplar.
3. **Beyanname** sekmesinden dönemi açın ve **"Beyannameyi Onayla & Kilitle"** butonuna basın. Bu adımdan sonra dönem kapanır, snapshot kalıcı olarak saklanır.
4. GİB e-Beyanname sistemine giriş yaparak beyannameyi gönderin. Aldığınız tahakkuk fiş numarasını **"GİB Tahakkuk Numarası Kaydet"** butonu ile sisteme girin.
5. Bankaya ödeme yaptıktan sonra **"Ödeme Kaydet"** butonu ile dekont referansını işleyin.

## XML Çıktısı (Muhasebe Yazılımına Aktarım)

Kilitli her beyanname için **XML İndir (GİB)** butonu, GİB form alanlarıyla 1-1 eşleşen XML çıktısı üretir. Bu dosyayı muhasebe yazılımınıza içe aktarabilirsiniz.

## Geçmiş

**Geçmiş** sekmesinde tüm dönemleri durum etiketleriyle (Taslak / Onaylı / Gönderildi / Ödendi) görebilirsiniz.

## Sık Sorulanlar

- **"Beyanname kilitlendikten sonra düzeltebilir miyim?"** Hayır, kilitli dönem değişmez. Hatalı kilitleme durumunda bir yöneticiyle iletişime geçin; revizyon için yeni bir snapshot alınması gerekir.
- **"Ödendikten sonra tekrar gönderim kaydedebilir miyim?"** Hayır, sistem 409 hatası verir. Durum makinesi yalnızca: Taslak → Onaylı → Gönderildi → Ödendi yönünde ilerler.
