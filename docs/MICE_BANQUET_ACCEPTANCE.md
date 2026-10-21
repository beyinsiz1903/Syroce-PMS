# MICE ve Banquet incelemesi ve kabul kapsamı

21 Ekim 2026. Bu çalışma satış, salon tahsisi, menü, mutfak, müşteri onayı ve finansal devir arasındaki veri tutarlılığını güçlendirir. Kaynak kodu ve izole test ortamındaki doğrulama, canlı otelde tamamlanmış kabul veya ürünün dünyadaki tüm rakiplerinden üstün olduğu anlamına gelmez. Bu dal üretime dağıtılmadı.

## Ürün hedefi

Hedef akış talep → müşteri ve fırsat → teklif → salon tahsisi → müşteri onayı → operasyon ve mutfak → gerçekleşen hizmet → finansal kapanıştır. Aynı müşteri, salon, para birimi ve etkinlik kimliği bu akış boyunca korunmalıdır.

Pazar karşılaştırmasında [Amadeus Delphi](https://www.amadeus-hospitality.com/sales-catering-software/delphi/) müşteri/fırsat takibi, BEO, grup oda blokları, menü ve AV gereksinimleri, raporlama ve müşteri işbirliğini birlikte ele alır. Buradaki hedef de bu işlevlerin birbirinden kopmaması; yalnız sekme ve buton sayısının artması değildir.

## Ekran ve işlem envanteri

| Alan | Kullanıcı işlemleri | Bu daldaki durum | Kalan kabul |
| --- | --- | --- | --- |
| Etkinlik listesi | Arama, durum/tarih filtresi, sayfalama, oluşturma, düzenleme, durum geçişi, silme, geçmiş | Filtre kapsamı, toplam kayıt sayısı, açık pipeline ve geçerli durum seçenekleri düzeltildi | Büyük canlı otel listesinde performans ve görev bazlı yetkiler |
| Etkinlik formu | Müşteri, tarih, salon, kapasite, kaynak, program, teknik gereksinim, personel, ödeme planı | Ters/çakışan aralık, negatif/sonlu olmayan tutar ve sahte ödeme engelleri; kayıt tekrarına karşı istek kimliği | Kurulum/söküm tamponları ve zaman dilimi göçü |
| Mekanlar | Ekle, düzenle, sil, pasiflik, düzen kapasiteleri, kira tarifesi | Etkinlikle aynı `mice_spaces` kataloğunda doğrudan yönetim eklendi | Bölünebilir/birleşebilir salonlar, çizim ve masa yerleşimi |
| Function Diary | Aylık, liste, gün bazlı saat çizelgesi, tarih gezinme | İptal/lead kayıtları doluluk sayılmıyor; salonun gerçek kullanım günü ve gece saatleri hesaba katılıyor | Tüm zaman dilimleri, tamponlar, sürükle bırak ve çakışma önizlemesi |
| Müşteriler | Kurumsal hesap oluştur/düzenle/sil, ilgili kişi ekleme/listeleme | Eksik hesap düzenleme arayüzü bağlandı | İlgili kişi düzenleme/silme arayüzü, tek birincil kişi kuralı, gelişmiş CRM takibi |
| Menüler | Ekle/düzenle/sil, fiyat, alerjen, diyet, asgari kişi, hazırlık süresi | Servis sırası/içerik düzenleme eklendi; çift fiyat tabanı engellendi | Kişiye özel diyet sayıları ve reçete maliyeti |
| Envanter | Ekle/düzenle/sil, stok ve birim fiyat | Eksik düzenleme bağlandı; eşzamanlı en yüksek kullanım ve aktif tahsis koruması | Tedarikçi kiralama, sevkiyat/iade, dış mekan için ayrı kullanım penceresi |
| Satış Pipeline | Fırsat, aşama değişikliği, faaliyet, özet | Yükleme hatası artık boş liste olarak gizlenmiyor | Fırsattan etkinliğe tek işlemli dönüşüm, sürümlü teklif, takip SLA ve kayıp neden analizi |
| Paketler | Oluştur/düzenle/sil, kişi sayısıyla teklif hesapla | Pasif paket/minimum/maksimum kişi, negatif tutar ve ondalık hesap kontrolleri | Paket teklifini tüm satırlarıyla etkinliğe aktarma |
| Rakip Analizi | Rakip ve fiyat kaydı, karşılaştırma | Farklı para birimleri ayrı gruplarda; pasif rakipler karşılaştırmaya alınmıyor | Fiyat güncelliği, tarih/sezon ve aynı kapsam karşılaştırması |
| BEO | Görüntüle, PDF indir/gönder, yazdır, müşteri onayı, muhasebeleştir | Müşteri onay arayüzü ve belgeye özel yazdırma; finans butonlarında rol/durum görünürlüğü | Sürümlü BEO değişiklik listesi, departman teslim/onay takibi |
| Müşteri onay sayfası | Bağlantıyla görüntüle, ad ve açık rıza ile onayla | Özel, süreli bağlantı; genel değişiklik eski daveti iptal eder; imzalı kayıt kilitlenir | Nitelikli elektronik imza sağlayıcısı entegrasyonu ayrı kapsamdır |
| Mutfak siparişleri | Gönder, listele, teslim alındı, tamamla | Sıfır miktarın tüm kişi sayısına dönüşmesi önlendi; durum yazımı karşılaştırmalı; sipariş dövizi korunuyor | Etkinlik değişikliği/iptali sonrası revizyon ve iptal iş emri |
| Günlük operasyon | Tarih seç, fonksiyonları görüntüle/yazdır | Başka günün salon saatleri seçilen güne taşınmıyor | Departman bazlı görev atama, teslim ve gerçekleşen kişi/sarf kaydı |
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

Mevcut satış bedeli salon kiraları ve kaynak satırlarının toplamıdır. Vergi dahil/hariç fiyat, servis bedeli, indirim, minimum harcama, komisyon, gerçekleşen tüketim ve eğlence bedelinin gelir/maliyet ayrımı henüz tek bir fiyatlandırma motorunda tanımlı değildir. Bu alanlarda oran veya muhasebe politikası varsayılmadı.

Ödeme takvimindeki ödendi işareti kasa/banka hareketi üretmez. Genel Muhasebeye İşle ve bağlı PMS rezervasyonuna folyo devri ayrı yüzeylerdir; canlı kabulde aynı satışın iki kez gelirleşmediği ve gerçek folyo bakiyesine doğru geçtiği birlikte doğrulanmalıdır.

Üst düzey ürün için kalan geliştirme sırası:

1. Vergi/servis/indirim ve gerçek tahsilat–iade sözleşmesi; hesap, tarih, döviz ve ters kayıt kuralları.
2. Teklif ve BEO sürümleri; imzalı sürümden kontrollü ek protokol; müşteri ve departmanlara değişiklik bildirimi.
3. Birleşen/bölünen salon hiyerarşisi, kurulum/söküm tamponları ve tesisin saat diliminde ortak takvim.
4. Gerçekleşen kişi/tüketim, garanti kişi, reçete ve personel maliyetiyle etkinlik kârlılığı.
5. Mutfak revizyonu/iptali, ekipman teslim/iade ve departman görev/onay süreçleri.
6. Fırsat–teklif–etkinlik–grup oda bloğu dönüşümünün tek kayıt üzerinden yürütülmesi.
7. Mobil operasyon, çok tesis, erişilebilirlik ve tüm dillerde metin/çıktı kabulü.

## Doğrulama yöntemi

Son yerel test turu: 119 backend testi, 30 frontend testi ve 10 masaüstü/telefon tarayıcı testi geçti. Backend turu gerçek BEO PDF üretimini de içerdi; atlanan test yoktu. Üretim derlemesi, Ruff, değişen arayüzlerin ESLint kontrolü ve tema kontrolü başarılıydı. Bu sayılar tüm PMS testlerinin veya canlı kabulün tamamı değildir.

Backend testleri gerçek kurum, e-posta veya misafir kaydı göndermez. Yerel MongoDB kabul veritabanı her çalışmada benzersiz ad alır ve yalnız o veritabanı temizlenir. Replica set üzerinde salon yarışında bir işlem kazanmalı; standalone MongoDB üzerinde atomik garanti verilemiyorsa iki işlem de kapalı kalmalıdır.

- `backend/tests/unit/test_mice_integrity.py`: girdi, zaman, para, değişmez ödeme ve fiyat koruması.
- `backend/tests/test_mice_mongo_acceptance.py`: gerçek sorgular, tesis ayrımı, stok, ödeme, durum yarışı, folyo tekilleştirme, rakip dövizi ve operasyon günü.
- Mevcut MICE döviz, kota, BEO PDF/e-posta ve müşteri onay regresyon testleri.
- `frontend/src/components/mice/__tests__/MiceWorkflow.test.jsx` ve mevcut MICE sayfa/sipariş testleri.
- `frontend/playwright.mice-local.config.js`: masaüstü ve telefon boyutunda gerçek Chrome; yapay API cevaplarıyla salon, etkinlik, teklif, kontrol listesi, müşteri onayı ve yazdırma yüzeyleri. Bu, gerçek backend ile uçtan uca canlı kabul değildir.

Tarayıcı doğrulaması:

```sh
cd frontend
MICE_BROWSER_CHANNEL=chrome npx playwright test --config=playwright.mice-local.config.js
```

Canlı kabulde tek bir yapay otel kullanılarak talep, teklif, tahsis, müşteri onayı, mutfak teslimi, gerçekleşen hizmet ve finansal kapanış aynı etkinlik üzerinde karşılaştırılmalıdır. Gerçek e-posta gönderimi ve gerçek finansal kayıt oluşturma, ayrı onay ve kontrollü test verisi gerektirir.
