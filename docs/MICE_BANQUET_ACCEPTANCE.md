# MICE ve Banquet incelemesi ve kabul kapsamı

21 Ekim 2026. Bu çalışma satış, salon tahsisi, menü, mutfak, müşteri onayı ve finansal devir arasındaki veri tutarlılığını güçlendirir. Kaynak kodu ve izole test ortamındaki doğrulama, canlı otelde tamamlanmış kabul veya ürünün dünyadaki tüm rakiplerinden üstün olduğu anlamına gelmez. Bu dal üretime dağıtılmadı.

## Ürün hedefi

Hedef akış talep → müşteri ve fırsat → teklif → salon tahsisi → müşteri onayı → operasyon ve mutfak → gerçekleşen hizmet → finansal kapanıştır. Aynı müşteri, salon, para birimi ve etkinlik kimliği bu akış boyunca korunmalıdır.

Pazar karşılaştırmasında [Amadeus Delphi](https://www.amadeus-hospitality.com/sales-catering-software/delphi/) müşteri/fırsat takibi, BEO, grup oda blokları, menü ve AV gereksinimleri, raporlama ve müşteri işbirliğini birlikte ele alır. Buradaki hedef de bu işlevlerin birbirinden kopmaması; yalnız sekme ve buton sayısının artması değildir.

## Ekran ve işlem envanteri

| Alan | Kullanıcı işlemleri | Bu daldaki durum | Kalan kabul |
| --- | --- | --- | --- |
| Etkinlik listesi | Arama, durum/tarih filtresi, sayfalama, oluşturma, düzenleme, durum geçişi, silme, geçmiş | Filtre kapsamı, toplam kayıt sayısı, açık pipeline ve geçerli durum seçenekleri düzeltildi | Büyük canlı otel listesinde performans ve görev bazlı yetkiler |
| Etkinlik formu | Müşteri, tarih, salon, kapasite, kaynak, program, teknik gereksinim, personel, ödeme planı | Kurulum/söküm tamponlarıyla salon ve stok müsaitliği; servis süresinden kira; girdi, tekrar ve ödeme korumaları | Tesis saat diliminde ortak veri göçü |
| Mekanlar | Ekle, düzenle, sil, pasiflik, düzen kapasiteleri, kira tarifesi | Etkinlikle aynı `mice_spaces` kataloğunda doğrudan yönetim eklendi | Bölünebilir/birleşebilir salonlar, çizim ve masa yerleşimi |
| Function Diary | Aylık, liste, gün bazlı saat çizelgesi, tarih gezinme | İptal/lead doluluk sayılmıyor; kurulum/söküm tamponları önceki/sonraki günde de müsaitliği etkiliyor | Tüm zaman dilimleri, sürükle bırak ve çakışma önizlemesi |
| Müşteriler | Kurumsal hesap oluştur/düzenle/sil, ilgili kişi ekleme/listeleme | Eksik hesap düzenleme arayüzü bağlandı | İlgili kişi düzenleme/silme arayüzü, tek birincil kişi kuralı, gelişmiş CRM takibi |
| Menüler | Ekle/düzenle/sil, fiyat, alerjen, diyet, asgari kişi, hazırlık süresi | Servis sırası/içerik düzenleme eklendi; çift fiyat tabanı engellendi | Kişiye özel diyet sayıları ve reçete maliyeti |
| Envanter | Ekle/düzenle/sil, stok ve birim fiyat | Eksik düzenleme bağlandı; eşzamanlı en yüksek kullanım ve aktif tahsis koruması | Tedarikçi kiralama, sevkiyat/iade, dış mekan için ayrı kullanım penceresi |
| Satış Pipeline | Fırsat, aşama değişikliği, faaliyet, özet | Yükleme hatası artık boş liste olarak gizlenmiyor | Fırsattan etkinliğe tek işlemli dönüşüm, sürümlü teklif, takip SLA ve kayıp neden analizi |
| Paketler | Oluştur/düzenle/sil, kişi sayısıyla teklif hesapla | Pasif paket/minimum/maksimum kişi, negatif tutar ve ondalık hesap kontrolleri | Paket teklifini tüm satırlarıyla etkinliğe aktarma |
| Rakip Analizi | Rakip ve fiyat kaydı, karşılaştırma | Farklı para birimleri ayrı gruplarda; pasif rakipler karşılaştırmaya alınmıyor | Fiyat güncelliği, tarih/sezon ve aynı kapsam karşılaştırması |
| BEO | Görüntüle, PDF indir/gönder, yazdır, sürüm kaydet, müşteri onayı, revizyon aç, muhasebeleştir | Kayıtlı içerikten PDF, atomik sürüm numarası, eski onayın arşivlenmesi ve yeni onay gereksinimi | Ayrıntılı satır farkı ve departman teslim/onay takibi |
| Katılım ve maliyet | Gerçek/garanti kişi, bütçe, tüketim ve personel maliyeti gir, teklif bazlı katkıyı gör | Finans yetkisi ve gelişmiş raporlama özelliğiyle korunur; veri eksikse maliyeti sıfır olarak sunmaz | Reçeteden otomatik sarf, bordro maliyeti, gerçekleşmiş muhasebe geliriyle kârlılık |
| Müşteri onay sayfası | Bağlantıyla görüntüle, ad ve açık rıza ile onayla | Özel, süreli bağlantı; genel değişiklik eski daveti iptal eder; imzalı kayıt kilitlenir | Nitelikli elektronik imza sağlayıcısı entegrasyonu ayrı kapsamdır |
| Mutfak siparişleri | Gönder, listele, teslim alındı, tamamla, iptal talebi, iptali kabul et, yeni sürüm gönder | Aynı içerik tek emir; değişen/iptal etkinlik için uyarı; açık eski emir iptal edilmeden revizyon gönderilemez; kayıtlı içerik/alerjen dökümü gösterilir | Gerçek mutfak ekibi kabulü, kişi bazlı diyet dağılımı ve otomatik reçete/stok sarfı |
| Günlük operasyon | Tarih seç, fonksiyonları görüntüle/yazdır; BEO'dan görev ve ekipman teslim/iade planı | Görev atama, teslim alma, tamamlama ve gerekçeli iptal; rezervasyon miktarını aşmayan ekipman planı | Departmana özel kullanıcı/izin matrisi, otomatik bildirim, kısmi teslim ve iade |
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

Ödeme takvimindeki ödendi işareti kasa/banka hareketi üretmez. Bağlı rezervasyon varsa doğrudan yevmiye oluşturma kapalıdır; tamamlanma folyo devrini kullanır. Bağımsız etkinlik yevmiyesinde vergi 391, net gelir/servis 600 hesabına ayrılır; hesapların aktif olması gerekir. Aktarım süresince satış düzenlemesi kilitlenir, belirsiz sonuç aynı anahtar/kurla tekrar edilir. Gerçek tahsilat/iade ve folyo bakiyesi için canlı mutabakat halen gereklidir.

Her etkinlikte en fazla 25 değişmez BEO içerik sürümü saklanır. Onay bağlantısı belirli sürüme bağlıdır. Muhasebeleşmemiş açık onaylı etkinliğe gerekçeli revizyon açılınca eski belge ve müşteri onayı arşivde kalır; yeni içeriğe otomatik onay taşınmaz. Bu geçmişi bulunan etkinlik silinemez. Katılım/maliyet analizi gerçekleşmiş gelir veya muhasebe kârı değil, vergisiz teklif üzerinden katkı hesabıdır. Tüm maliyetlerin girildiği ayrıca onaylanmadan katkı tutarı gösterilmez.

Kurulum ve söküm tamponları salonun yanı sıra ayrılan envanterin müsaitliğine de dahildir; kira yalnız servis süresindendir. Yeni arayüzde açıkça girilen 0 veya 1 menü miktarı korunur. Eski API istemcilerinin kişi başı menüde `quantity=1` ile tam etkinlik pax seçme sözleşmesi yalnız `quantity_mode` belirtilmemiş isteklerde korunur; yeni arayüz `explicit` gönderir.

Mutfak emri menü ve alerjen içeriğini gönderildiği haliyle saklar. Aynı içerik tekrar gönderildiğinde ikinci üretim emri oluşmaz. Revizyon öncesinde açık eski emir için iptal talebi gönderilir ve mutfak iptali kabul eder; yeni sürüm eski emri referanslayabilir. Departman görevleri ve ekipman teslim/iade kayıtları BEO'dan yönetilir; fiziksel stok sayımı veya gerçek tahsilat yerine geçmez.

Üst düzey ürün için kalan geliştirme sırası:

1. Gerçek tahsilat–iade sözleşmesi; karma vergi, minimum harcama, komisyon ve ters kayıt kuralları.
2. Sürümler arası satır farkı ve müşteri/departmanlara değişiklik bildirimi.
3. Birleşen/bölünen salon hiyerarşisi ve tesisin saat diliminde ortak takvim.
4. Reçeteden stok sarfı ve personel/bordro maliyetiyle gerçekleşmiş muhasebe kârlılığı.
5. Departmanlara özel görev yetkileri, otomatik bildirim ve kısmi ekipman teslim/iade süreçleri.
6. Fırsat–teklif–etkinlik–grup oda bloğu dönüşümünün tek kayıt üzerinden yürütülmesi.
7. Mobil operasyon, çok tesis, erişilebilirlik ve tüm dillerde metin/çıktı kabulü.

## Doğrulama yöntemi

Son birleşik yerel test turu: 145 backend testi, 36 frontend testi ve 12 masaüstü/telefon tarayıcı testi geçti. Backend turu gerçek BEO PDF üretimini de içerdi; atlanan test yoktu. Üretim derlemesi, Ruff, değişen arayüzlerin ESLint kontrolü ve tema kontrolü başarılıydı. Bu sayılar tüm PMS testlerinin veya canlı kabulün tamamı değildir.

PR sırası: #1379 temel bütünlük → #1380 ticari belge/fiyat/maliyet → salon ve departman operasyonları. Son paket, feature dalını hedefleyen bağlı PR'lerde sessizce atlanan CI tetikleyicisini de düzeltir; dağıtım koşulları değişmez.

Backend testleri gerçek kurum, e-posta veya misafir kaydı göndermez. Yerel MongoDB kabul veritabanı her çalışmada benzersiz ad alır ve yalnız o veritabanı temizlenir. Replica set üzerinde salon yarışında bir işlem kazanmalı; standalone MongoDB üzerinde atomik garanti verilemiyorsa iki işlem de kapalı kalmalıdır.

- `backend/tests/unit/test_mice_integrity.py`: girdi, zaman, para, değişmez ödeme ve fiyat koruması.
- `backend/tests/test_mice_mongo_acceptance.py`: gerçek sorgular, tesis ayrımı, stok, ödeme, durum yarışı, folyo tekilleştirme, rakip dövizi ve operasyon günü.
- `backend/tests/test_mice_commercial_workflows.py`: değişmez belge, onay revizyonu, fiyat bileşenleri, maliyet ve muhasebe aktarım korumaları.
- `backend/tests/test_mice_function_operations.py`: hazırlık tamponları, görev/ekipman adımları, mutfak iptal/revizyonu ve paralel gönderim.
- Mevcut MICE döviz, kota, BEO PDF/e-posta ve müşteri onay regresyon testleri.
- `frontend/src/components/mice/__tests__/MiceWorkflow.test.jsx` ve mevcut MICE sayfa/sipariş testleri.
- `frontend/playwright.mice-local.config.js`: masaüstü ve telefon boyutunda gerçek Chrome; yapay API cevaplarıyla salon, etkinlik, teklif, kontrol listesi, müşteri onayı ve yazdırma yüzeyleri. Bu, gerçek backend ile uçtan uca canlı kabul değildir.

Tarayıcı doğrulaması:

```sh
cd frontend
MICE_BROWSER_CHANNEL=chrome npx playwright test --config=playwright.mice-local.config.js
```

Canlı kabulde tek bir yapay otel kullanılarak talep, teklif, tahsis, müşteri onayı, mutfak teslimi, gerçekleşen hizmet ve finansal kapanış aynı etkinlik üzerinde karşılaştırılmalıdır. Gerçek e-posta gönderimi ve gerçek finansal kayıt oluşturma, ayrı onay ve kontrollü test verisi gerektirir.
