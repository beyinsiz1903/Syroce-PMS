# KBS: Jandarma sunucu gönderimi ve EGM sınırı

## Durum ve sınır

Jandarma için tarayıcıdan bağımsız SOAP göndericisi, otel bazlı güvenli ayarlar
ve mevcut Celery kuyruğu kullanılır. İstek telefondan PMS web ekranında kuyruğa
alınabilir; telefon ve resepsiyon bilgisayarı kapalıyken sunucu işi yürütür.
Native uygulamada Ön büro → Diğer → KBS bildirimleri ve rezervasyondan KBS
kısayolu bulunur. Native değişikliklerin cihazlara ulaşması yeni uygulama
sürümünün dağıtılmasını gerektirir; yalnız backend deploy'u yeterli değildir.
Bu geliştirme tek başına canlı kurulum veya resmi kabul testi değildir.

EGM/Polis bağlantısı aynı servis değildir. Mevcut `egm-session` adaptörü
kullanıcının Chrome profilinde açtığı EGM oturumuna dayanır; sunucuya oturum
çerezi, e-Devlet parolası veya EGMSEC sırrı aktarılmaz. Açık ve güncel bir
sunucu yetkilendirme sözleşmesi doğrulanmadan EGM için bilgisayarsız gönderim
hazır olarak sunulmaz. EGM oturumunu otomatik yenileme/ikinci faktör atlama yoktur.

### Polis — sayfadan bağımsız, tarayıcı oturumuna bağlı gönderim (eklenti 1.5.0)

- PMS → KBS → Bağlantı ve gönderim ayarları bölümünde **Polis arka plan
  göndericisi** ayrı ve açık bir tesis doğrulamasıyla etkinleştirilir. Önceki
  sayfa içi otomatik gönderim ayarı yeni göndericiyi kendiliğinden açmaz.
- Normal giriş/çıkışın oluşturduğu kuyruğu eklentinin `chrome.alarms` worker'ı
  dakikada bir tarar. PMS sayfası gizli/kapalı olabilir; Chrome/Edge ve
  bilgisayar çalışıyor olmalıdır. Uyku sırasında zamanında gönderim garantisi
  yoktur. Telefon yalnız normal PMS üzerinden işi kuyruğa alır; telefonun
  kendi tarayıcısına eklenti veya EGM oturum sırrı taşınmaz.
- Yeni izin: yalnız `https://pms.syroce.com/*` için normal API isteği ve
  `alarms`. `cookies`, `tabs`, oturum okuma veya parola toplama izni istenmez.
  HTTP isteklerinde tarayıcı normal HttpOnly PMS erişim çerezini kendisi
  ekler. Token/çerez JavaScript'e okunmaz, kopyalanmaz veya saklanmaz.
- Yetki normal PMS erişim oturumu ve `view_reports` kontrolünden geçer.
  Extension API isteklerinin her birinde etkinleştirilen kullanıcı/otel
  bağlamı sunucuda doğrulanır. Oturum süresi, çıkış, kullanıcı/otel değişimi
  veya cloud sahipliği göndericiyi durdurur; otomatik refresh/login yoktur.
  Tarayıcı çerez politikası erişimi engellerse gönderim başarısı varsayılmaz;
  güvenlik politikası otomatik gevşetilmez.
- `KBS_TEST_MODE=1` iken sunucu canlı Polis arka plan işini vermez; zaten
  etkin bir gönderici de bir sonraki yetki kontrolünde durur.
- Tesis/kullanıcı bağı ve opt-in yalnız `chrome.storage.session` içindedir.
  Worker askıya alınıp yeniden başlarsa alarm yenilenir; tarayıcı yeniden
  başlatılırsa, eklenti güncellenir/devre dışı bırakılırsa opt-in kaybolur.
  Kullanıcı yeniden giriş yapıp doğru EGM tesisini doğrulayarak etkinleştirir.
  Otel değiştirmek önce mevcut göndericiyi durdurmayı gerektirir.
- Arka plan işi aynı atomik claim/complete/fail sözleşmesini kullanır. Taze
  payload yalnız claim anında alınır, eklenti depolamasına misafir bilgisi
  yazılmaz. Adil tarih+id imleci, engellenen ilk 20 kaydın arkadakileri sürekli
  bloke etmesini engeller. Test sonucu veya açık EGM kabulü olmayan 200 yanıtı
  başarı sayılmaz. Mutasyon timeout/bozuk cevap/5xx belirsiz tutulur; yerel
  complete kaybolursa kurum isteği tekrarlanmaz. Diğer işler ilerler.
- Canlı kurulum bu kodun deploy edilmesiyle açılmaz. Yeni eklenti sürümü,
  kurumun izin verdiği tesis/ağ ve yetkilinin normal EGMSEC oturumu gerekir.
  Kurum ekranıyla ilk meşru giriş/çıkış uzlaştırılmadan resmî canlı kabul
  tamamlanmış sayılmaz. Bu, EGM için bilgisayarsız sunucu göndericisi değildir.

Teknik dayanaklar: [Chrome alarms](https://developer.chrome.com/docs/extensions/reference/api/alarms),
[oturumluk depolama](https://developer.chrome.com/docs/extensions/reference/api/storage),
[uzantılarda çerez davranışı](https://developer.chrome.com/docs/extensions/develop/concepts/storage-and-cookies).

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

## Otomatik giriş / çıkış ve iki görünüm

- Normal, atomik, kiosk ve v2 giriş/çıkış yolları her konaklayan için ayrı iş
  oluşturur. Gerçek giriş olmadan onaylı/garantili rezervasyon gece taramasında
  kuruma bildirilmez. Rezervasyon formları kimlik bilgilerini toplar; cloud KBS
  akışını benimsemiş tesislerde backend de girişten önce tüm konaklayanları
  denetler. Eksik kayıtta oda, folyo veya giriş durumu değiştirilmez.
- Çıkış, aynı kişinin giriş kabulü alınana kadar saklanır; düşürülmez.
  Diğer misafirlerin işleri işlenmeye devam eder. Eksik veri, açık ret,
  zaman aşımı ve kabul sonrası yerel rapor yazma hatası ayrı ele alınır.
- Web ve native yalnız **Gönderilen** / **Gönderilmeyen** görünümlerini kullanır.
  Gönderilmeyen satır gerçek nedeni gösterir: eksik/geçersiz alan, henüz
  alınmamış kabul, önceki girişin kabulünü bekleme, kurumda aynı kimlik için
  açık kayıt, açık ret veya belirsiz teslimat. Test sonucu gönderilmiş sayılmaz.
- Kurumda zaten açık kimlik kaydı, sırf bu yanıttan dolayı bizim yeni
  bildirimimiz kabul edilmiş sayılmaz. Otomatik ve manuel tekrar engellenir;
  kurum kaydı uzlaştırılmalıdır. Başarılı kalıcı makbuz da yeniden gönderilmez.
- Ana KBS ekranında gerçek çıkıştan **24 saat** sonra kişi satırları gizlenir.
  Erken çıkan ek kişi kendi çıkış saatine göre gizlenir; otelde kalan kişi,
  planlı çıkış tarihi eskidi diye kaybolmaz. Bu bir ekran görünürlük tercihidir,
  yasal veri saklama süresi değildir.
- Süre dolması kuyruğu, makbuzu, denetimi veya belirsiz teslim kilidini SİLMEZ.
  Sonuçlanmamış eski bildirimler ana ekranda kimliksiz toplam uyarısı olarak
  kalır; yetkili yönetici denetim/operasyon kayıtlarından takip eder.
- Ortak liste kimlik/pasaport numarası, ham kurum cevabı veya bağlantı sırrı
  döndürmez. Ad görünürlüğü personelin veri profiline uyar. Kimlik tamamlama
  otel/rezervasyon/kişi ilişkisini ve düzenleme yetkisini denetler, normal
  şifreli misafir yazma yolunu kullanır. Native KBS sorguları çevrimdışı diske
  kaydedilmez; form alanları ekrandan çıkışta temizlenir.

## Testler

`backend/tests/unit/test_kbs_cloud.py`: WSDL alan sırası, TR/yabancı giriş/çıkış,
XML escaping, saat dilimi, hata/timeout, şifreleme ve tenant ayrımı.

`backend/tests/test_kbs_cloud_config.py`: gerçek yerel Mongo üzerinde
kaydet/doğrula/etkinleştir/rotasyon, yarışan doğrulama, eklenti engeli ve belirsiz
lease'in tekrar gönderilmemesi. Kurum çağrıları tüm testlerde mock'tur.

`frontend/src/components/pms/__tests__/KBSCloudSettings.test.jsx`: kullanıcı
onayı, yetki görünürlüğü, gizli alanların temizlenmesi ve yanlış başarı engeli.

`backend/tests/test_kbs_mobile_lifecycle.py`: yerel replica üzerinde çok
konaklayan, giriş-çıkış bağımlılığı, arızalı ilk kişiden sonra ilerleme,
mükerrer/uncertain koruması, eşzamanlı enqueue, kimlik yetkileri, iki görünüm
ve 24 saatlik gizleme. Tüm kurum çağrıları mock; hiçbir resmî bildirim yapılmaz.

`frontend/src/components/pms/__tests__/KBSNotification.identity-edit.test.jsx`
iki görünüm, nedenler, kimlik tamamlama ve eklenti kabul/ret/belirsizlik
davranışını kapsar. Native kimlik/izin/PII-cache sözleşmeleri
`mobile/src/utils/__tests__/kbs.test.ts` içinde doğrulanır.

`backend/tests/test_kbs_background_agent.py`: bağlam/politika kontrolü,
HTTP claim/complete/fail korumaları, PII içermeyen adil yerel Mongo beslemesi.
`extension/tests/police-agent.test.js` ve `egm-background.test.js`: sayfa
bağımsızlığı, alarm/oturum yaşam döngüsü, hatalı kayıttan sonra ilerleme,
belirsizlik, mükerrer engeli, hesap değişimi ve saklanan verinin kapsamı.
`KBSBackgroundSender.test.jsx`: açık opt-in, hesap/otel kontrolü, belirsiz
etkinleştirmeyi canlı durumla uzlaştırma ve ikinci worker'ın engellenmesi.
Bu testler resmî KBS servislerine bildirim göndermez.
