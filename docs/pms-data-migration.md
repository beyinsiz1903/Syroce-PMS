# PMS'den bağımsız otel veri taşıma merkezi

## Durum ve kullanım sınırı

Giriş: **Ayarlar → Veri Taşıma Merkezi** (`/app/data-migration`). Yalnız seçili
tesisin admin/super_admin kullanıcısı, PMS lisansı, kullanıcı yönetim yetkisi ve
tam misafir veri görünürlüğü ile erişebilir. Süperadmin önce hedef tesisi seçer.
Kaynak dosya veya HTTP gövdesi hedef tenant seçemez.

Bu sürüm **geçmiş arşivi, misafir profili yayınlama, sürümlü son fark aktarımı ve
ayrı onaylı canlı devir** sağlar. Dosyalara ek olarak sunucuda tesis bazında
yetkilendirilmiş JSON anlık görüntü API'leri okunabilir. OPERA/Elektraweb vb. için
sertifikalı/hazır bir API konektörü olduğu iddia edilmez. Satış öncesi
her kaynak çıktısının kapsamı incelenmelidir. Hiçbir kaynak PMS'nin dışarı vermediği
alanlar için kayıpsız aktarım garantisi verilmez.

**Arşiv aktarımı tamamlandı ≠ otelin canlıya geçişi tamamlandı.**

| Veri | Bu sürümde hedef |
| --- | --- |
| Misafirler | Şifreli arşiv; açıkça seçilirse normal misafir listesine de yayınlama |
| Şirket / acente / oda tanımları | Arşiv; canlı devirde mevcut hedeflere açık ID eşleştirmesi, otomatik anlaşma/oda oluşturma yok |
| Geçmiş rezervasyonlar / hareketler | Salt okunur arşiv, yeni işlem olarak tekrar oynatılmaz |
| Gelecek / konaklayan rezervasyonlar | Mutabakat, brüt günlük fiyatlar ve folyo kesim dökümü sonrası atomik oda/gece kilidiyle canlı takvim |
| Aktif folyolar | Eski borç/ödeme ayrı açılış bakiyesi; yeni gelir veya tahsilat kaydı üretilmez |
| Bağımsız cari bakiyeler | Açılış muhasebe fişi taslağı; ayrı muhasebe onay/kayıt akışı zorunlu |
| Ek belgeler | Kayda bağlı şifreli PDF/görsel arşivi, yalnız yetkili indirme |

Mevcut hedef odanın tipi kullanılır; her gecenin gerçek brüt fiyatı açık kaynak
dökümünden gelir. Tarife/sözleşme kuralları, şirket/acente ticari koşulları ve
gelecekteki fiyatlama algoritmaları bu dosyalardan tahmin edilmez. Bunlar hedef
PMS'de ayrıca kurulmalıdır. Cari bakiyelerin acente extranet mutabakatı, vergi
fatura bağlantıları ve diğer özel alt defterlere dönüştürülmesi ayrıca kaynak
ve hedef sözleşmesi gerektirir; GL fişi tek başına bunları tamamlamış sayılmaz.
Şirket/acente bağlantılı aktif rezervasyonlar bu uyarlama olmadan canlıya
alınmaz; güncel hedef komisyonunu geçmiş sözleşmeye uygulayıp yanlış alacak
üretmek yerine inceleme hatası verir. Otomatik canlı devir kapsamı doğrudan
misafir ödemeli rezervasyonlardır. Dolayısıyla gerçek kaynak üzerinde bu
ticari kapsam doğrulanmadan **"tüm geçiş tamamlandı" denemez**.

## Akış

1. Kaynak adını ve kalıcı kaynak anahtarını oluşturun. Aynı eski PMS/tesis
   verisinin tüm parçalarında aynı anahtar kullanılır; başka kaynağa başka anahtar.
2. Veri türü başına dosya ekleyin. CSV/TSV, XLSX, düz JSON nesne listesi veya
   `<records><record><field>value</field></record></records>` biçiminde düz XML.
   Vendor XML şemaları otomatik yorumlanmaz; iç içe yapılar açıkça reddedilir.
3. Alanları ve gerekirse durum/tür/döviz kodlarını eşleştirin. Öneriler yalnız
   adaydır; operatör doğrular. Eşleştirilmeyen sütunlar raporda gösterilir; varsayılan
   olarak taşınmaz. "Ek kaynak alanlarını koru" seçilirse bunlar şifreli
   `source_fields` içinde aynen saklanır ve arşiv detayından okunabilir. Canlı
   profil alanı olarak yorumlanmaz. Bir sütunu iki standart alana bağlama ve
   bilinmeyen standart hedef alanlar engellenir.
4. Dosya başına bağımsız kaynak kayıt sayısını ve parasal kontrol toplamlarını
   girin. Örnek: `{"total:TRY":"1200.00"}`; hareketlerde
   `{"charge:EUR":"100.00","payment:EUR":"20.00"}`. Boş kontrol alanı
   "mutabakat eksik" olarak kalır; dosyanın kendi toplamı kaynak doğrulaması sayılmaz.
5. Deneme çalıştırın. Hatalar aktarımı engeller. Kaynak numarası tekrarları,
   eksik ilişkiler, tarih/durum hataları, döviz ve küsurat sorunları raporlanır.
6. Uyarıları ve yalnız arşiv sınırını onaylayın. Sunucu revizyona ve güncel hedef
   durumuna bağlı inceleme tokenını tekrar doğrular. İşlem 100 kayıtlık parçalarda
   ilerler. Sekme kapanırsa veya hata olursa aynı aktarımı açıp devam edin.
7. Arşivde profil → rezervasyon → folyo → hareket bağlantılarını inceleyin.
   Yayınlanmış/bağlanmış misafirin 360 kartında önceki PMS geçmişine bağlantı bulunur.
   Kısmen taşınmış kaydın aktarım durumu ayrıntıda görünür; tamamlanmış gibi sunulmaz.

## Kimlik ve finans güvenliği

- Ad/soyad tek başına mevcut misafirle birleştirme sebebi değildir. Güçlü kimlik
  eşleşmesi varsa dosyadaki eski misafir no → **mevcut Syroce misafir ID** bağlantısı
  açıkça tanımlanır veya yalnız arşiv aktarılır. Başka tesisin ID'si reddedilir.
- Mevcut profile hiçbir alan yazılmaz. Yeni profillerde KVKK onayı üretilmez;
  pazarlama izni için kaynak tarih ve kanıt referansı zorunludur. Kaynak bir izin
  kaydı işletmenin kendi uygunluk kontrolünün yerine geçmez.
- Tutarlar Decimal ve dövizin hassasiyeti ile doğrulanır; otomatik kur dönüşümü,
  farklı para birimlerini toplama veya binlik ayırıcı tahmini yapılmaz.
- "Tüm folyo hareketleri mevcut" seçilirse önceki arşiv ve yeni dosyalardaki
  borç + iade + düzeltme − ödeme toplamı, folyo bakiyesiyle aynı olmalıdır.
  Bu seçenek yoksa tam folyo mutabakatı yapıldığı iddia edilmez.
- Geçmiş veriler booking, cashier, GL, KBS, mesaj ve kanal işleme fonksiyonlarına
  gönderilmez. Eski faturalar yeniden düzenlenmez, tahsilatlar yeniden yapılmaz.
- Aynı tenant/kaynak/tür/kaynak-no tekrar yüklenirse aynı içerik yeniden oluşturulmaz.
  Değişmiş içerik varsayılan olarak inceleme hatası üretir. Yeni aktarımda
  `allow_archive_updates` açıkça seçilirse önceki şifreli sürüm saklanarak CAS
  ile güncellenir; deneme tokenı eski ve yeni içeriğe bağlanır. Mevcut canlı
  misafir alanları değiştirilmez. Canlı kesim için dondurulmuş kaynakta fark
  aktarımı engellenir; artık değişiklikler operasyonel süreçten yapılmalıdır.
- Kaynak kayıt numaraları için opak HMAC anahtarları ve içerik blind-indexleri
  kullanılır. `FIELD_ENCRYPTION_PEPPER` kalıcıdır; gelişigüzel değiştirilmesi
  idempotency ve mevcut PII aramalarını bozar. Anahtar rotasyonu planlı yapılmalıdır.

## Saklama, limitler ve hata kurtarma

- Dosya: 5 MB / 10.000 satır / 80 sütun / 4096 karakter hücre; başlık en fazla
  160 karakter. Aktarım: 20 dosya / 50.000 satır. Daha büyük geçmişler aynı
  kaynak anahtarıyla ilişki sırasını izleyen ayrı aktarımlara bölünür. İlgili
  kaynak kayıtları indeksli, 1000 anahtarlık sorgularla aranır; tüm arşiv kesilmez.
- Dosya satırları, onaylı plan ve mevcut misafir bağlantıları kalıcı yazımdan önce
  platformun şifreleme servisi ile şifrelenir. Şifreleme kapalıysa fail-closed.
  Aktarım ayarları 2 MB ile sınırlıdır; büyük eşleşme listeleri bölünmelidir.
- Ham dosya diske ayrıca kaydedilmez. Şifreli hazırlık satırları/planı 30 gün sonra
  Mongo TTL ile silinir (TTL asenkrondur). Nihai geçmiş arşivi kendiliğinden silinmez;
  işletmenin saklama/silme politikası ayrıca uygulanmalıdır. Süresi geçmiş ve
  eksik plan sessizce atlanmaz; destek incelemesi veya yeniden hazırlama gerekir.
- Hata raporu ilk 200 hatayı içerir; satır değerleri, kimlikler ve iletişim
  bilgileri rapora yazılmaz. Tüm hata sayısı ayrı gösterilir. JSON/CSV yanıtları
  önbelleğe alınmaz. Audit loglarında yalnız iş kimliği, durum ve revizyon tutulur.
- Tesis yazma kilidi çoklu worker'ı ve farklı kaynaklardan eşzamanlı profil
  yayınlamayı serileştirir. Her çağrı sınırlı bir
  parça işler; ağ yanıtı kaybolsa bile deterministik kayıtlar yeniden çoğalmaz.
- Otomatik geri alma yalnız **arşiv-only** aktarımın kendi oluşturduğu kayıtları
  kaldırır. Aynı kaynaktan başka tamamlanmış/yarım aktarım veya bağımlılık varsa
  destek incelemesi gerektirir. Yayınlanan profiller otomatik silinmez; sonradan
  rezervasyon/mesaj vb. ile kullanılmış bir misafiri silmek güvenli değildir.

## Canlı kesim ve finansal kontrol

1. Önce bir prova aktarımı ve kaynak raporuyla bağımsız sayım/toplam mutabakatı
   yapılır. Asıl kesimde eski PMS'ye yazma durdurulur; son fark dosyası aynı
   kaynak anahtarıyla sürümlü aktarılır. Saat dilimli kesim anı kaydedilir.
2. Tüm kaynak arşiv parçaları tamamlanmış ve mutabık olmalıdır. Açık iş günü ile
   kesim günü eşit olmalıdır; eski iş gününü gizlice ileri alma yapılmaz.
3. `target_links.rooms/companies/agencies`: eski kaynak ID → **aynı tesisteki
   mevcut hedef ID**. Misafir yayınlama/bağlama önce tamamlanır. Her aktif
   rezervasyonun tüm geceleri `daily_rates` türüyle (`rate_date`, brüt `amount`,
   `currency`, `reservation_source_id`) verilir; toplamı sözleşme bedeline eşit
   olmalıdır. Durum pending ise kaynakta kesinleştirme/iptal gerekir.
4. Her aktif rezervasyon için 1–8 folyo: `charged_amount - paid_amount = balance`,
   aynı döviz. Kesimden önceki brüt oda geceleri kaynak borcuna dahil olmalıdır.
   Kısmi komp/indirim/erken çıkış gibi bu eşitliği bozan özel durum otomatik
   yorumlanmaz; inceleme hatası verir.
5. Bağımsız cari bakiyelerin aktif folyoları tekrar içermediği ayrıca onaylanır.
   `receivable/payable/deposit/clearing` aktif bilanço hesapları ve sabit kesim
   kurları açıkça girilir. GL mevcut TRY bazlı, iki ondalıklı sözleşmeyi kullanır;
   farklı baz döviz veya daha hassas tutarlar arşivlenir ama canlı finans devri
   özel uyarlama olmadan durur. Hesaplar/kurlar otomatik tahmin edilmez.
6. Hatasız inceleme sonrası operatör `CANLI DEVRI ONAYLIYORUM` yazar. Sistem
   mevcut muhasebe kurulum servisinden **taslak** açılış fişi oluşturur. Finans
   lisansı gereklidir. Mevcut onay/muhasebeye kayıt akışı atlanmaz. Fiş gerçekten
   posted olmadan ve tarih/tutar/hesap/döviz satırları incelemeyle aynı olmadan
   canlı rezervasyonlar aktive edilmez. Sıfır açılışa sıfır fiş oluşturulmaz.
7. Canlı devir 10 rezervasyonluk çağrılarla, kalıcı kaynak sahipliği ve tenant
   yazma kilidiyle ilerler. Oda/gece benzersiz indeksi doğrulanamazsa durur.
   Sonradan oluşan çakışma da atomik çekirdekte reddedilir. Folyolar ve günlük
   fiyatlar deterministik ID ile oluşturulur; yanıt kaybında çoğalmaz. Bir
   rezervasyonun atomik oda kilidi var; **tüm otelin devri tek transaction değildir**.
   Kesinti halinde kısmi folyolar/rezervasyonlar görülebilir. Kaynak kapalı
   tutulur, job cursor ve bağımsız kontrol raporlarıyla tamamlanır. Sonradan
   operatörün değiştirdiği canlı kayıtlar resume ile ezilmez.
8. Geçmiş ödeme/gelir/fatura/KBS/mesaj/kanal işlerini tekrar üretmez. KBS devrinin
   resmi bildirim durumuyla uzlaşması ayrıca yapılır. Oda müsaitliği canlı
   rezervasyonlardan etkilenir; OTA kanal yayını ayrıca normal entegrasyon
   sürecinde doğrulanmalıdır. Aktif acente rezervasyonlarının komisyon ve kimin
   ödeyeceği mutabakatı olmadan ticari alt defterlerin hazır olduğu söylenemez.

Arşiv-only geri alma dışındaki geri dönüşler otomatik silme değildir. Kaynak
dondurulduğunda ikinci batch'in açılış fişi engellenir. Finansal ters kayıt ve
rezervasyon iptali mevcut yetkili operasyonlar üzerinden, veri kullanımını
inceleyerek yapılır. Aynı kaynağın yeni bir kesimi destek mutabakatı gerektirir.

## Sunucu tarafı JSON API uyarlaması

Sistem yöneticisi `DATA_MIGRATION_API_SOURCES` ortam ayarını tanımlar:

```json
[{"id":"legacy-guests","label":"Yetkili kaynak misafir dökümü",
  "tenant_ids":["hedef-tenant-id"],"entity":"guests",
  "url":"https://partner.example/authorized-snapshot/guests",
  "token_env":"MIGRATION_SOURCE_LEGACY_TOKEN"}]
```

Gerçek token ayrı sunucu secret ayarına konur; JSON'a, Git'e veya tarayıcıya
verilmez. URL yalnız HTTPS, kullanıcı/şifre/query/fragment içermeyen sabit uçtur.
Tenant isteği URL veya credential seçemez. Mevcut egress katmanı DNS/IP'yi
sabitler; yönlendirme izlenmez. Decode edilmiş yanıt akışta sınırlandırılır.
API salt okunur GET `limit=250&cursor=...` sözleşmesini uygulamalıdır:

```json
{"snapshot_id":"sabit-kesim-anahtari","total_count":2,"totals":{},
 "records":[{"source_id":"g1","name":"Yapay Misafir"}],
 "next_cursor":"ikinci-sayfa"}
```

Son sayfada `next_cursor:null`. Snapshot ID, sayı ve toplamlar tüm sayfalarda
aynı kalır. Toplamlar dosya aktarımındaki `total:TRY/charge:EUR` vb. sözleşmeye
uyar. En fazla 40 sayfa, toplam 5 MB / 10.000 kayıt, 80 saniye; eksik/döngülü
veya değişen görüntüde kısmi dosya kabul edilmez. Aynı görüntü tekrar okunursa
ikinci dosya oluşmaz. Herhangi bir vendor'ın API'si bu şemadan farklıysa yetkili
ara uyarlama gerekir; OAuth/proprietary uçlar kendiliğinden keşfedilmez.

## Ek belgeler ve sürümler

Arşiv detayından önceki 100 sürüm, ek belge listesi/yükleme/indirme kullanılabilir.
PDF ve doğrulanmış görseller belge başına 5 MB, kayıt başına 20 adet sınırıyla
tenant bağlı şifreli saklanır; kaynak belge kimliği tekrarı çoğalmaz, değişen
belge için yeni sürüm kimliği gerekir. Ad/kaynak dosya adı da şifrelenir.
İndirme cache kapalı, `attachment`, `nosniff` ve CSP sandbox ile yapılır; dosya
sunucuda çalıştırılmaz. İçerik türü kontrolü antivirüs taraması garantisi değildir;
işletme saklama ve zararlı içerik tarama politikasını ayrıca uygular. Ek belge
bulunan arşivin otomatik silinmesi engellenir.

## Doğrulama

Yerel Mongo dışındaki adresleri reddeden `backend/tests/test_data_migration.py`:
formatlar, şifreleme, tekrar deneme, kayıp yanıt, mevcut misafir eşleşmesi, tesis
ayrımı, mutabakat ve arşiv geri alma. Mevcut misafir geçmişi regresyonları da koşulur.

```sh
cd backend
python3 -m pytest tests/test_data_migration.py tests/test_data_migration_cutover.py tests/test_sentry_legacy_data_regressions.py -q
```

Gerekli standart test ortamı (`JWT_SECRET`, yerel `MONGO_URL`, test şifreleme
ayarları) ayarlanmalıdır; canlı anahtar veya veritabanı kullanılmaz.

```sh
cd frontend
npm test -- src/pages/__tests__/DataMigrationPage.test.jsx src/pages/__tests__/DataMigrationCutover.test.jsx
npm run test:e2e:migration
```

Tarayıcı kabulü gerçek sayfa bileşenini yerel Vite'da **yapay API yanıtlarıyla**
masaüstü, telefon ve tablette çalıştırır; dış ağ istekleri engellenir. Playwright
Chromium kurulu değilse yüklü Chrome ile `PLAYWRIGHT_CHANNEL=chrome npm run
test:e2e:migration` kullanılabilir. Gerçek veritabanı davranışları ayrı backend
kabul testleriyle doğrulanır. Bunlar gerçek otelin kaynak dosyalarıyla yapılmış
canlı kabul veya tam eski-PMS entegrasyonu değildir.
