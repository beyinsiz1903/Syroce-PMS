# MICE ve Banquet incelemesi ve kabul kapsamı

21 Ekim 2026. Satış fırsatından etkinliğe dönüşüm, grup ana folyosu, gerçek tahsilat ve kısmi iade, birleşik salon, masa planı, reçete sarfı ve departman teslim takibi eklendi. İzole kabul senaryosu satış, stok, kasa ve folyo toplamlarını aynı etkinlikte uzlaştırır. Canlı otel kabulü ve üretim dağıtımı bu doğrulamanın dışında kalır.

## Ürün hedefi

Hedef akış talep → müşteri ve fırsat → teklif → salon tahsisi → müşteri onayı → operasyon ve mutfak → gerçekleşen hizmet → finansal kapanıştır. Aynı müşteri, salon, para birimi ve etkinlik kimliği bu akış boyunca korunmalıdır.

Pazar karşılaştırmasında [Amadeus Delphi](https://www.amadeus-hospitality.com/sales-catering-software/delphi/) müşteri/fırsat takibi, BEO, grup oda blokları, menü ve AV gereksinimleri, raporlama ve müşteri işbirliğini birlikte ele alır. Buradaki hedef de bu işlevlerin birbirinden kopmaması; yalnız sekme ve buton sayısının artması değildir.

## Ekran ve işlem envanteri

| Alan | Kullanıcı işlemleri | Bu daldaki durum | Kalan kabul |
| --- | --- | --- | --- |
| Etkinlik listesi | Arama, durum/tarih filtresi, sayfalama, oluşturma, düzenleme, durum geçişi, silme, geçmiş | Filtre kapsamı, toplam kayıt sayısı, açık pipeline ve geçerli durum seçenekleri düzeltildi | Büyük canlı otel listesinde performans ve görev bazlı yetkiler |
| Etkinlik formu | Müşteri, tarih, salon, kapasite, kaynak, program, teknik gereksinim, personel, ödeme planı | Tesis saat diliminde yeni kayıt; kurulum/söküm tamponları; gerçek tahsilat geçmişini genel formdan değiştirememe | Eski saat kayıtlarının kontrollü veri göçü |
| Mekanlar | Ekle, düzenle, sil, pasiflik, düzen kapasiteleri, kira tarifesi | Birleşik salon ve alt salon çakışması; metrik masa planı, sınır/çakışma/koltuk kontrolü; BEO çizim ve koordinat dökümü | Sürükle bırak CAD, kaçış yolu ve erişilebilirlik için yetkili tesis kontrolü |
| Function Diary | Aylık, liste, gün bazlı saat çizelgesi, tarih gezinme | İptal/lead doluluk sayılmıyor; kurulum/söküm tamponları önceki/sonraki günde de müsaitliği etkiliyor | Tüm zaman dilimleri, sürükle bırak ve çakışma önizlemesi |
| Müşteriler | Kurumsal hesap oluştur/düzenle/sil, ilgili kişi ekleme/listeleme | Eksik hesap düzenleme arayüzü bağlandı | İlgili kişi düzenleme/silme arayüzü, tek birincil kişi kuralı, gelişmiş CRM takibi |
| Menüler | Ekle/düzenle/sil, fiyat, alerjen, diyet, asgari kişi, hazırlık süresi | Servis sırası/içerik düzenleme eklendi; çift fiyat tabanı engellendi | Kişiye özel diyet sayıları ve reçete maliyeti |
| Envanter | Ekle/düzenle/sil, stok ve birim fiyat | Eksik düzenleme bağlandı; eşzamanlı en yüksek kullanım ve aktif tahsis koruması | Tedarikçi kiralama, sevkiyat/iade, dış mekan için ayrı kullanım penceresi |
| Satış Pipeline | Fırsat, aşama değişikliği, faaliyet, özet | Aynı fırsattan tek etkinlik; müşteri/döviz korunur; kazanıldı aşaması gerçek etkinliğe bağlı; mevcut grup bloğu seçilebilir | Yeni oda bloğunu dönüşüm ekranında oluşturma, takip SLA ve kayıp neden analizi |
| Paketler | Oluştur/düzenle/sil, kişi sayısıyla teklif hesapla | Pasif paket/minimum/maksimum kişi, negatif tutar ve ondalık hesap kontrolleri | Paket teklifini tüm satırlarıyla etkinliğe aktarma |
| Rakip Analizi | Rakip ve fiyat kaydı, karşılaştırma | Farklı para birimleri ayrı gruplarda; pasif rakipler karşılaştırmaya alınmıyor | Fiyat güncelliği, tarih/sezon ve aynı kapsam karşılaştırması |
| BEO | Görüntüle, PDF indir/gönder, yazdır, sürüm kaydet, müşteri onayı, revizyon aç, muhasebeleştir | Kaydedilmiş sürümler arası alan/satır farkı; atanmış departman personeline uygulama içi bildirim ve kişisel teslim onayı | Dış e-posta teslimatı ve gerçek departman ekibi kabulü |
| Katılım ve maliyet | Gerçek/garanti kişi, bütçe, tüketim ve personel maliyeti gir, katkıyı gör | Tamamlanmış mutfak üretiminden onaylı reçete partisiyle atomik stok sarfı; sabit maliyet; kayıtlı net gelir ve teklif ayrı; tam maliyet onayı olmadan katkı yok | Otomatik bordro ve tedarikçi faturası aktarımı, maliyetin genel muhasebeye bağlanması |
| Gerçek tahsilat ve iade | Nakit/kart/havale makbuzu, kısmi/tam iade, bekleyen işlemi kurtar | Gerçek GL, ödeme, nakit akışı, banka/kasa ve açık folyo güncellemesi; asıl tahsilat kuru ve iade sınırı; çift kayıt ve gece denetiminde çift muhasebeleşme koruması | Banka/kart sağlayıcısına gerçek ödeme emri ayrı entegrasyondur; canlı mutabakat gerekir |
| Müşteri onay sayfası | Bağlantıyla görüntüle, ad ve açık rıza ile onayla | Özel, süreli bağlantı; genel değişiklik eski daveti iptal eder; imzalı kayıt kilitlenir | Nitelikli elektronik imza sağlayıcısı entegrasyonu ayrı kapsamdır |
| Mutfak siparişleri | Gönder, listele, teslim alındı, tamamla, iptal talebi, iptali kabul et, yeni sürüm gönder | Aynı içerik tek emir; açık eski emir için iptal kabulü; kayıtlı menü/alerjen; tamamlanmış satır için bir kez reçete sarfı | Gerçek mutfak ekibi kabulü, kişi bazlı diyet ve hatalı sarf için kontrollü düzeltme akışı |
| Günlük operasyon | Tarih seç, fonksiyonları görüntüle/yazdır; görev ve ekipman teslim/iade | Atanmış kullanıcı/departman yetkisi; hedefli bildirim; kısmi teslim ve iade; benzersiz hareket anahtarı | Otomatik SLA eskalasyonu ve gerçek ekip kabulü |
| Operasyon kontrolü | Eksikleri ve ödeme planı durumunu incele, etkinliği aç | Sorumlu, iletişim, salon, program ve gecikmiş plan satırı kontrolleri eklendi | Gerçek banka/kasa mutabakatı değildir; sayfa kapsamı açıkça belirtilir |

## Düzeltilen veri ve hesap sözleşmeleri

- Boş katalog GET çağrısı artık gerçek otele örnek salon veya menü eklemez. Önceden oluşmuş kayıtlar kullanıcı verisi kabul edilerek otomatik silinmedi.
- Mevcut kira kuralı açıklaştırıldı: minimum bir saat; altı saatten itibaren günlük ücret; her başlayan 24 saat için bir günlük kira. 25 saat tek günlük ücretlenmez.
- Yeni salon satırında kira tarifesi sunucuda saklanır. Tarifesi saklanmış mevcut satır düzenlenirken bu tarife korunur. Eski, tarifesi saklanmamış satırlar düzenlenirse mevcut katalog esas alınır; tarihsel özgün tarife uydurulmaz ve mevcut kayıtlar topluca yeniden hesaplanmaz.
- Satır tutarları ondalık aritmetik ve yarım yukarı yuvarlamayla hesaplanır. Toplam, yuvarlanmış satırların toplamıyla uzlaşır.
- TRY, EUR ve USD toplanıp tek para birimi gibi sunulmaz. Rakip fiyatı farklı dövizdeki otel teklifiyle karşılaştırılmaz.
- Eksik/pasif veya başka otele ait salon, menü, envanter, müşteri ve PMS rezervasyon bağlantıları kabul edilmez.
- Aynı etkinlikte aynı salonun üst üste binmesi, bitişin başlangıçtan önce olması ve programın etkinlik tarihleri dışında kalması engellenir.
- Envanter hesabı zaman zarfındaki bütün etkinlikleri toplamaz; gerçekten aynı anda gereken miktarın tepesini kullanır. Sıfır stok sınırsız stok değildir.
- Aktif etkinlik tahsislerini ihlal eden salon kapasitesi/stok azaltımı ve envanter silme engellenir. Salon ve envanter değişiklikleri aynı kaynak kilitlerini kullanır.
- Genel PUT ile durum atlatılamaz; geçerli durum endpointi, kota ve finans yetkileri kullanılır. Form açıldıktan sonra değişen kayıt sessizce ezilmez.
- İptal/tamamlanmış etkinlik açık pipeline değerine katılmaz. Üst toplam, yalnız yüklenen ilk 500 satırın uzunluğu değildir; sonraki sayfalar erişilebilirdir.
- Genel formdan `paid=true` üretilemez. Ödenmiş taksit silinemez/değiştirilemez; ödeme penceresindeki vazgeçme işlem oluşturmaz. Tekrarlanan işaretleme eski tarih/referansı bozmaz.
- İmzalı veya muhasebeleştirilmiş etkinliğin genel düzenlemesi kapalıdır. Sözleşme değişikliği için ayrı sürüm/ek protokol akışı gerekir.
- Eşzamanlı terminal durum değişikliğinde yalnız bir işlem kazanır. Folyo aktarımı başarısızsa etkinlik başarılı tamamlanmış halde bırakılmaz; kota serbest bırakılmaz.
- Folyo devri MongoDB kimliğiyle tekilleştirilir. Paralel tekrar iki ücret oluşturmaz.
- Müşteri daveti her üretimde farklıdır; davet/gösterim/onay ayrı işlemlerdir. Bağlantı oluşturmak e-posta göndermek değildir. Onay kaydı nitelikli elektronik imza olarak sunulmaz.

## Finansal sınırlar ve tamamlanması gereken işler

Satış teklifi net salon ve kaynak fiyatlarından hesaplanır. İsteğe bağlı politika sırası ara toplam → yüzde indirim → servis → vergidir. Servisin vergi matrahına dahil edilmesi seçilebilir; bileşenler kuruşa yuvarlanır ve ekranda/PDF'de aynı sunucu toplamı gösterilir. Oranlar varsayılmaz. Karma satır vergi oranı, vergi dahil katalog fiyatı, minimum harcama ve komisyon henüz bu motorda yoktur; teklif dökümü mali fatura yerine geçmez.

Ödeme takvimindeki ödendi işareti kasa/banka hareketi üretmez. Ayrı gerçek hareket ekranı alınmış veya iade edilmiş parayı kaydeder; bankaya/kart kuruluşuna ödeme emri göndermez. Nakit için açık vardiya, banka/kart için aynı dövizde hesap, döviz için açık TRY kayıt kuru gerekir. Tahsilat 100/102/108 karşılığında 120 hesabını kapatır; gelir değildir. Kısmi iade asıl yöntemi, hesabı ve kayıt kurunu kullanır. Son iadede kuruş bakiyesi kapanır; temsil edilemeyen kuruş altı parça yerine kalan tutarın birlikte iadesi istenir.

Önce kurtarılabilir finans isteği saklanır, sonra tekil GL kaydı, ardından ödeme/nakit akışı/kasa/banka/folyo atomik yazımı yapılır. Belirsiz sonuçta yeni istek kabul edilmez; arayüz kayıtlı isteği değiştirilemez biçimde geri yükler. Bekleyen işlem varken vardiya kapatma/devir engellenir. Kasa mutabakatı ve gece denetimi aynı hareketi ikinci kez yazmaz. Banket ödemesi genel ödeme silme/void işlemiyle izsiz düzeltilemez; iade akışı gerekir.

Rezervasyon veya grup ana folyosuna bağlı etkinlik doğrudan satış yevmiyesi yerine tamamlanma devrini kullanır. Grup devri tek bir `folio_charges` kaydı oluşturur; sahte oda rezervasyonu üretmez. Grup ekstresi tüm satırları tesis filtresiyle okur, geçersiz ödemeyi dışlar, iadeyi doğru işaretle toplar; farklı dövizleri birleştirmez. Bağımsız etkinlik satış yevmiyesinde vergi 391, net gelir/servis 600 hesabına ayrılır; hesaplar aktif olmalıdır. Bu akışların canlı muhasebe kabulü halen gereklidir.

Her etkinlikte en fazla 25 değişmez BEO içerik sürümü saklanır. Onay bağlantısı belirli sürüme bağlıdır. Gerekçeli revizyonda önceki belge/onay arşivde kalır; yeni içerik eski onayı devralmaz. Sürüm farkı kaydedilmiş içerikten hesaplanır. Departman bildirimi yalnız atanmış kullanıcılara gider; teslim onayı yalnız güncel sürümün alıcısı tarafından verilir.

Reçete sarfı yalnız tamamlanmış üretim için yetkili finans kullanıcısının onayladığı parti sayısıyla yapılır. Bir parti reçetedeki malzeme miktarıdır, pax değildir. Yetersiz stok, birim veya döviz uyuşmazlığında bütün işlem geri alınır. Sarf ve maliyet aynı işlemde kaydedilir; aynı üretim satırı ikinci kez tüketilemez. İnsan tarafından girilen personel maliyeti ile otomatik reçete maliyeti ayrı gösterilir. Kaydedilmiş net gelir eksi onaylanmış tam maliyet, operasyon katkısıdır; maliyetlerin muhasebeleştiği veya bordro entegrasyonunun tamamlandığı anlamına gelmez.

Kurulum ve söküm tamponları salonun yanı sıra ayrılan envanterin müsaitliğine de dahildir; kira yalnız servis süresindendir. Yeni arayüzde açıkça girilen 0 veya 1 menü miktarı korunur. Eski API istemcilerinin kişi başı menüde `quantity=1` ile tam etkinlik pax seçme sözleşmesi yalnız `quantity_mode` belirtilmemiş isteklerde korunur; yeni arayüz `explicit` gönderir.

Mutfak emri menü ve alerjen içeriğini gönderildiği haliyle saklar. Aynı içerik tekrar gönderildiğinde ikinci üretim emri oluşmaz. Revizyon öncesinde açık eski emir için iptal talebi gönderilir ve mutfak iptali kabul eder; yeni sürüm eski emri referanslayabilir. Departman görevleri ve ekipman teslim/iade kayıtları BEO'dan yönetilir; fiziksel stok sayımı veya gerçek tahsilat yerine geçmez.

Kalan geliştirme ve kabul kapsamı:

1. Karma satır vergisi, vergi dahil katalog, minimum harcama ve komisyon; müşteri sözleşmesi ve muhasebe politikasının açık tanımı gerekir.
2. Paket teklifindeki tüm salon/menü/oda satırlarını etkinliğe dönüştürme ve dönüşüm sırasında yeni oda bloğu oluşturma.
3. Bordro/tedarikçi faturası otomasyonu ve maliyet muhasebesi; mevcut personel maliyeti elle girilir.
4. Eski saat verilerinin kontrollü göçü, sürükle bırak salon tasarımı, kişiye özel diyet ve sarf düzeltme akışı.
5. Gerçek departman ekibi, büyük veri, eşzamanlı kullanım, dış e-posta teslimatı, çok tesis, erişilebilirlik ve dil kabulü.

## Doğrulama yöntemi

Son birleşik yerel test turu: 187 backend testi, 35 frontend testi ve 18 masaüstü/telefon tarayıcı testi geçti. Backend turu gerçek MongoDB, yerel HTTP sunucusu ve gerçek BEO PDF üretimini içerdi; atlanan test yoktu. Üretim derlemesi, Ruff, değişen arayüzlerin ESLint kontrolü, import sınırı, atlama bütçesi ve tema kontrolü başarılıydı. Bu sayılar tüm PMS testlerinin veya canlı kabulün tamamı değildir.

Birleşmiş temel: #1379 veri bütünlüğü, #1380 ticari belge/fiyat/maliyet, #1381 salon ve departman operasyonları. Bu devam dalı finans, satış dönüşümü, grup, reçete, masa planı ve departman teslim takibini ekler. Üretim ayarı veya canlı kayıt değiştirilmez.

Yerel Python ortamında API/worker bağımlılık kapanışı denetimleri yeşil değildir: API tarafında 4 eşlenemeyen modül; worker tarafında aynı 4 modül ve 9 dağıtım uyarısı vardır. Aynı denetimler değişmemiş `7a5c46c34` temelinin geçici kopyasında da aynı sonucu verdi; bu dal yeni üçüncü taraf bağımlılığı eklemez. PR CI ve Docker açılış kontrolleri ayrıca değerlendirilmelidir.

CI sırasında yayınlanan SDK uyumluluk yamaları için mobil `expo` ve `expo-router` bağımlılıkları güncellendi. Mobil yapılandırma/TypeScript, 185 birim testi ve Expo Doctor 21/21 kontrolü yerelde geçti. Yeni IPA veya mağaza yayını yapılmadı.

Backend testleri gerçek kurum, e-posta veya misafir kaydı göndermez. Yerel MongoDB kabul veritabanı her çalışmada benzersiz ad alır ve yalnız o veritabanı temizlenir. Replica set üzerinde salon yarışında bir işlem kazanmalı; standalone MongoDB üzerinde atomik garanti verilemiyorsa iki işlem de kapalı kalmalıdır.

- `backend/tests/unit/test_mice_integrity.py`: girdi, zaman, para, değişmez ödeme ve fiyat koruması.
- `backend/tests/test_mice_mongo_acceptance.py`: gerçek sorgular, tesis ayrımı, stok, ödeme, durum yarışı, folyo tekilleştirme, rakip dövizi ve operasyon günü.
- `backend/tests/test_mice_commercial_workflows.py`: değişmez belge, onay revizyonu, fiyat bileşenleri, maliyet ve muhasebe aktarım korumaları.
- `backend/tests/test_mice_function_operations.py`: hazırlık tamponları, görev/ekipman adımları, mutfak iptal/revizyonu ve paralel gönderim.
- `backend/tests/test_mice_settlements.py`: gerçek GL, banka/kasa/folyo, kısmi iade, kur yuvarlaması, tekrar ve kaybolan cevap sonrası kurtarma.
- `backend/tests/test_mice_extended_operations.py`: birleşik salon yarışı, departman erişimi, bildirim görünürlüğü, kısmi teslim/iade, masa sınırı ve bekleyen işlemde kasa kapanış engeli.
- `backend/tests/test_mice_completion_acceptance.py`: aynı etkinlikte gerçek HTTP handler/Mongo/GL üzerinden fırsat → masa/BEO → sarf → tahsilat/iade → grup ana folyosu. 168 TRY satış, 90 TRY net tahsilat, 78 TRY bakiye; 140 TRY net gelirden 12 TRY reçete ve 20 TRY personel maliyeti sonrası 108 TRY operasyon katkısı.
- Mevcut MICE döviz, kota, BEO PDF/e-posta ve müşteri onay regresyon testleri.
- `frontend/src/components/mice/__tests__/MiceWorkflow.test.jsx`, `MiceCompletion.test.jsx` ve mevcut MICE sayfa/sipariş testleri.
- `frontend/playwright.mice-local.config.js`: masaüstü ve telefon boyutunda gerçek Chrome; yapay API cevaplarıyla salon, etkinlik, teklif, kontrol listesi, müşteri onayı, tahsilat, masa planı, reçete sarfı ve yazdırma. Bu, gerçek backend ile uçtan uca canlı kabul değildir.

Tarayıcı doğrulaması:

```sh
cd frontend
MICE_BROWSER_CHANNEL=chrome npx playwright test --config=playwright.mice-local.config.js
```

Canlı kabulde tek bir yapay otel kullanılarak talep, teklif, tahsis, müşteri onayı, mutfak teslimi, gerçekleşen hizmet ve finansal kapanış aynı etkinlik üzerinde karşılaştırılmalıdır. Gerçek e-posta gönderimi ve gerçek finansal kayıt oluşturma, ayrı onay ve kontrollü test verisi gerektirir.
