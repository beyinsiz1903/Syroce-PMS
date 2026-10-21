# KBS: Jandarma sunucu gönderimi ve EGM sınırı

## Durum ve sınır

Jandarma için tarayıcıdan bağımsız SOAP göndericisi, otel bazlı güvenli ayarlar
ve mevcut Celery kuyruğu kullanılır. İstek telefondan PMS web ekranında kuyruğa
alınabilir; telefon ve resepsiyon bilgisayarı kapalıyken sunucu işi yürütür.
Bu, native iOS uygulamasına ayrıca bir KBS ekranı eklendiği anlamına gelmez.
Bu geliştirme tek başına canlı kurulum veya resmi kabul testi değildir.

EGM/Polis bağlantısı aynı servis değildir. Mevcut `egm-session` adaptörü
kullanıcının Chrome profilinde açtığı EGM oturumuna dayanır; sunucuya oturum
çerezi, e-Devlet parolası veya EGMSEC sırrı aktarılmaz. Açık ve güncel bir
sunucu yetkilendirme sözleşmesi doğrulanmadan EGM için bilgisayarsız gönderim
hazır olarak sunulmaz. EGM oturumunu otomatik yenileme/ikinci faktör atlama yoktur.

Kaynaklar:

- [Jandarma uygulama kılavuzu, Web Servis İşlemleri (s.10)](https://www.jandarma.gov.tr/kurumlar/jandarma.gov.tr/Jandarma/Uygulamalar/KBS/KBS_Tesis_2_Uygulama_TD.pdf)
- [Canlı SOAP sözleşmesi](https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc?wsdl)
- [Emniyet KBS iki faktör kılavuzu](https://m.egm.gov.tr/EGMSEC/KBS-K%C4%B1lavuz.pdf)
- [Manisa Emniyet hizmet standartları: KBS kaydı / sabit IP](https://www.manisa.pol.tr/kurumlar/manisa.pol.tr/KAMU-STANDARTTI/Kamu-Hizmet-Standartlari-2023.pdf)

## Canlıya alma — The Canyon Kartepe / Jandarma

1. API ve `celery_tasks.kbs_dispatch_task` worker'ının dışarı çıktığı sabit,
   genel IP'yi altyapıda doğrulayın. DNS/load balancer'ın gelen trafik IP'si
   ile worker'ın **çıkış** IP'si aynı olmak zorunda değildir. Egress değişirse
   önce yeni IP için kurum yetkisi ve yeni bağlantı testi gerekir.
2. Operatör `KBS_PUBLIC_EGRESS_IP` ortam değişkenini gerçek sabit çıkış IP'si
   olarak yapılandırır. Bu değer otomatik ölçüm değil, yönetici beyanıdır.
   Worker ayrıca kendi ağından `ParametreListele` çağrısı ile erişimini doğrular.
3. Tesis yetkilisi, Jandarma KBS → Web Servis İşlemleri'nde kullanılacak IP'yi
   ve ilgili kullanıcıyı yetkilendirir. Mevcut çalışan otel IP kaydı sessizce
   değiştirilmez; geçiş ilgili tesis/yetkili ile koordine edilir.
4. Üretim şifrelemesi hazır olmalı: `CRYPTO_V2_ENABLED=true`, gerçek
   `CM_MASTER_KEY_CURRENT` ve `CM_KEY_VERSION_CURRENT` (önceki anahtarlar
   rotasyon politikasına göre). Legacy şifreleme yalnız gerçek, en az 32
   karakterli `CM_CREDENTIAL_KEY` ile desteklenir. Şifreleme bypass veya
   anahtar yoksa bilgiler kaydedilmez; düz metin fallback yoktur.
5. Otel yöneticisi PMS → KBS → Jandarma sunucu bağlantısı → Bağlantı ayarları
   bölümüne kullanıcı T.C., tesis kodu ve **ayrı web servis şifresini** girer.
   Sohbet, Git, ekran görüntüsü ve uygulama loglarına secret koymayın.
6. Kaydetmek gönderimi etkinleştirmez. `Bağlantıyı doğrula` yalnız
   `ParametreListele(ULKELER)` çağırır; sahte misafir bildirimi oluşturmaz.
7. Doğrulama sonrasında tesis için gerçek bildirim onayı verilerek gönderici
   ayrıca etkinleştirilir. Değişen bilgiler önceki doğrulamayı geçersiz kılar.
8. Celery worker ve beat çalışmalı; mevcut görev dakikada bir kuyruğu tarar.
   UI son worker zamanını gösterir, 3 dakikayı aşınca uyarır. Sayfanın açık
   kalmasına ihtiyaç yoktur. `KBS_AUTO_DISPATCH=0` tüm sunucu gönderimini
   kapatır; `KBS_TEST_MODE=1` cloud üzerinden gerçek kuruma çıkışı engeller.
9. İlk gerçek kabul testi yalnız meşru bir giriş/çıkış kaydıyla, tesis
   yetkilisinin gözetiminde yapılır. Kurum ekranındaki kayıtla PMS'deki kabul
   sonucu uzlaştırılır. Bu adım olmadan canlı çalışıyor denmez.

## Güvenlik ve işlemsel davranış

- Ayar/verify uçları `manage_secrets`, durum okuma `view_reports` izni ister.
- Gizli bilgiler şifreli, tenant'a bağlıdır; GET cevaplarında geri verilmez.
- Kaydedilen cloud konfigürasyonu bu tesisin kuyruğunu sahiplenir; duraklatılmış
  veya doğrulanmamış olsa bile başka otelin/generic göndericinin kimlik
  bilgilerine ya da eklentiye otomatik fallback yapılmaz.
- Kuyruk işi atomik claim edilir. Giriş/çıkış öncesi güncel, ilgili misafirin
  verisi okunur; ek misafirin rezervasyon bağlantısı da doğrulanır.
- Yabancı ülke sembolleri kurum enum'una uygun olmalıdır; bilinmeyen kısa
  kodlar tahmin edilmez. Desteklenmeyen değer hata verir, başarılı sayılmaz.
- `Basarili=true` **ve** `HataKodu=Basarili/100` olmadan kabul yazılmaz.
  `JANDARMA-CLOUD-*` yerel teslim makbuzudur, kurumun verdiği bir referans
  numarası olarak sunulmaz (`official_reference=false`).
- Zaman aşımı, bozuk cevap veya gönderim sırasında çöken worker'ın süresi
  dolmuş lease'i belirsiz teslimat olarak tutulur. Otomatik tekrar yoktur;
  force/requeue/temizleme belirsiz kaydı aşamaz. Kurumda gerçek kayıt kontrolü
  ve destek uzlaştırması gerekir. Kontrol etmeden yeni iş/sahte kabul üretmeyin.
- Açık kurum reddi de başarı değildir; düzeltilmiş veriyle kullanıcı kontrollü
  yeniden kuyruğa alma mümkündür. Gerçek bildirimler test verisiyle denenmez.

## Testler

`backend/tests/unit/test_kbs_cloud.py`: WSDL alan sırası, TR/yabancı giriş/çıkış,
XML escaping, saat dilimi, hata/timeout, şifreleme ve tenant ayrımı.

`backend/tests/test_kbs_cloud_config.py`: gerçek yerel Mongo üzerinde
kaydet/doğrula/etkinleştir/rotasyon, yarışan doğrulama, eklenti engeli ve belirsiz
lease'in tekrar gönderilmemesi. Kurum çağrıları tüm testlerde mock'tur.

`frontend/src/components/pms/__tests__/KBSCloudSettings.test.jsx`: kullanıcı
onayı, yetki görünürlüğü, gizli alanların temizlenmesi ve yanlış başarı engeli.
