# Saha Hazirlik Cantasi - Pilot Otel Veri Aktarimi (Dirty Data)

Bu belge, pilot oteli ZIYARET ETMEDEN ve "bana eski verilerini ver" DEMEDEN
once hazirlanir. Amac: otelden gelecek dagimik/eksik/hatali eski veriyi
(legacy/dirty data) Syroce'ye sorunsuz girilebilecek "Syroce-Ready" hale
getirmek icin onceden plan, sablon ve kurallari hazirda tutmak.

## ONEMLI ON BULGU (cantayi bunun uzerine kuruyoruz)

Syroce'de hazir, genel amacli bir "CSV/Excel yukle" ekrani YOKTUR. Veri iki
mesru yoldan girer:

1. Uygulama API'si uzerinden (misafir PII'si SIFRELI yazim yolundan gecer;
   dogrudan veritabanina kayit YAPMAYIN - sifrelenmez ve arama icin gereken
   `_hash_` blind-index uretilmez, yani misafir aranamaz hale gelir).
2. OTA/Kanal Yoneticisi import koprusu uzerinden (eslesmeyen kayitlar otomatik
   "inceleme bekliyor" - review hold - durumuna duser).

Bu yuzden aktarim, eski veriyi temizleyip API'ye besleyen kucuk bir yukleme
betigiyle (script) yapilir. Cantanin tamami bu gercege gore kurgulanmistir.

---

## Cantanin Icindekiler (5 Madde - Ozet)

1. Syroce-Ready Sablon Seti + Zorunlu Alan Sozlugu (otele verilecek)
2. "Once Iskelet" Kurulum Kontrol Listesi (veri girmeden once yapilandirma)
3. Kirli -> Temiz Donusum Cetveli (Syroce dogrulama kurallarina gore)
4. Tekillestirme (Dedup) ve Cakisma Cozum Kilavuzu
5. KVKK/PII Guvenli Aktarim + Asamali Yukleme ve Geri-Alma Plani

---

## 1) Syroce-Ready Sablon Seti + Zorunlu Alan Sozlugu

Amac: Oteliden "ne verirse" almak yerine, Syroce'nin tam olarak bekledigi
alanlara sahip BOS sablonlari (Excel/CSV) onceden hazirlayip otele gondermek.
Boylece kirli veri kaynakta hizalanir.

Sablonlari su SIRAYLA doldurtun (Syroce kurulum sirasi referans alinir:
hesap -> otel bilgisi -> odalar -> oda tipleri -> fiyatlar -> ilk misafir):

- ODA TIPLERI (room_types): tip adi (orn. Standart, Deluxe, Suite).
- ODALAR (rooms) - ZORUNLU alanlar: `room_number`, `room_type`, `floor` (sayi),
  `capacity` (sayi), `base_price` (sayi).
- FIYAT PLANLARI (rate plans): en az bir "Standart" plan adi/kodu.
- MISAFIRLER (guests) - ZORUNLU: `name`, `phone`, `id_number` (TC/pasaport);
  `email` istege bagli AMA doluysa gecerli olmali.
- REZERVASYONLAR (bookings) - ZORUNLU: misafir referansi, oda referansi,
  `check_in`/`check_out` (tarih), `adults` (0-50), `children` (0-50),
  `guests_count` (1-100), `total_amount` (0 - 1e12), `status`
  (yalniz su degerler: confirmed, checked_in, checked_out, cancelled, no_show).
- FOLYO/EK HARCAMALAR (varsa): kategori (orn. ROOM, FNB), `amount` (0 - 1e9),
  aciklama (1-500 karakter); indirim varsa indirim NEDENI zorunlu.

Sahada kullanim: Otelci eski sistemden disa-aktarim (export) yaparken bu
sablona kopyalar; siz daha gelmeden alan eslestirmesinin yarisi bitmis olur.

## 2) "Once Iskelet" Kurulum Kontrol Listesi

Amac: Misafir/rezervasyon verisi girmeden ONCE tenant iskeletini kurmak.
Rezervasyonlar oda ve misafire referans verir; oda tipi/fiyat eslesmezse kayit
"inceleme bekliyor" (review hold) durumuna duser. Bu yuzden once iskelet.

Veri yuklemeden once tamamlanacaklar (Admin/Setup uzerinden):

1. Tenant olusturma + dogru `property_type` (orn. city_hotel) - bu, modulleri
   ve limitleri belirler.
2. Oda tipleri (room_types) tanimlanir.
3. Odalar girilir (oda numaralari tekil olmali - bkz. madde 4).
4. En az bir "Standart" fiyat plani tanimlanir.
5. (OTA/CM uzerinden aktarim olacaksa) oda ve fiyat plani eslestirmeleri
   (mappings) aktif edilir; aksi halde gelen rezervasyonlar review hold'a duser.

Sahada kullanim: Bu listeyi otele varmadan, demo/pilot tenant uzerinde provasini
yapin; sahada yalnizca gercek degerleri girersiniz.

## 3) Kirli -> Temiz Donusum Cetveli

Amac: Syroce dogrulayicilarinin REDDEDECEGI tipik kirli desenleri, gelmeden
once normalize kurallariyla eslestirmek. Asagidaki donusumleri yukleme
betiginize onceden yazin:

- TARIHLER: tum tarihler ISO formatina (YYYY-MM-DD); `check_out` > `check_in`
  olmali; bos/gecersiz tarih satiri reddedilir.
- DURUM (status) ESLEME: eski sistemdeki serbest metni enum'a cevirin -
  "Onaylandi/Confirmed" -> confirmed; "Giris yapti" -> checked_in;
  "Cikti/Tamamlandi" -> checked_out; "Iptal" -> cancelled; "Gelmedi" -> no_show.
  Listede olmayan her deger reddedilir.
- E-POSTA: bos olabilir; AMA doluysa gecerli olmali. Gecersiz/"yok@yok" gibi
  cop degerleri BOS birakin (uydurma adres girmeyin).
- TELEFON: tutarli formata getirin (ulke kodu + rakam); harf/bosluk temizleyin.
- KIMLIK (id_number): ZORUNLU. Eksik olanlar icin "uydurma TC" URETMEYIN; bunu
  bir istisna listesine alin ve madde 5'teki KVKK/eksik-kimlik stratejisini
  uygulayin.
- SAYISAL SINIRLAR: adults/children 0-50, guests_count 1-100,
  total_amount 0 - 1e12, harcama amount 0 - 1e9 araliklarina sigdirin;
  negatif/asiri degerleri ayiklayin.
- INDIRIM: bir harcamada indirim tutari > 0 ise indirim NEDENI zorunlu - eski
  veride neden yoksa "Aktarim - eski sistem indirimi" gibi sabit bir neden yazin.
- ZORUNLU ALAN BOSLUKLARI: yukaridaki zorunlu alanlardan biri bos olan satir
  reddedilir; bunlari ayri "eksik veri" sekmesine ayirin.

Sahada kullanim: Bu cetvel = yukleme betiginizin "temizleme katmani"nin
spesifikasyonu. Otelin verisi gelince satir satir bu kurallardan gecirilir.

## 4) Tekillestirme (Dedup) ve Cakisma Cozum Kilavuzu

Amac: Eski sistemler ayni kaydi defalarca tutar (ayni misafir 5 kez, ayni oda
iki kez). Syroce'nin tekil (unique) kisitlari bu mukerrerleri REDDEDER; o yuzden
gelmeden once "altin kayit" (golden record) secim kurallarinizi belirleyin.

Syroce'nin uygulayacagi tekil kisitlar:

- Oda: (tenant_id, room_number) TEKIL - ayni oda numarasi iki kez giremez.
- Tenant: hotel_id TEKIL.
- Ice-aktarilan rezervasyon: `external_reservation_id` TEKIL (mukerrer import'u
  engeller).
- Genel: `idempotency_key` birden cok koleksiyonda tekil (ayni islem iki kez
  yazilmaz).
- Misafir: e-posta/telefon icin `_hash_email` / `_hash_phone` blind-index
  uzerinden eslestirme yapilir - ayni misafir tek kayda baglanir.

Cakisma cozum kurallari (onceden karara baglayin):

- Mukerrer misafir: e-posta VEYA telefon ayni ise tek "altin kayit"; en dolu/
  en guncel kaydi esas alin, rezervasyon gecmisini o tek misafire baglayin.
- Mukerrer oda numarasi: gercek fiziksel oda mi yoksa kayit hatasi mi - otelciyle
  netlestirin; ikisi de gercekse numaralandirmayi otelle birlikte duzeltin.
- Mukerrer rezervasyon: ayni oda + cakisan tarih = catisma; en guncel/dogru olani
  tutun, digerini iptal/arsiv olarak isaretleyin.
- Eslesmeyen oda tipi/fiyat: review hold'a duser - madde 2'deki eslestirmeleri
  tamamlayin, sonra yeniden isleyin.

Sahada kullanim: Dedup kararlarini otelci ONAYIYLA verin (hangi kayit "dogru");
betik otomatik birlestirir, siz sadece istisnalari elle cozulursunuz.

## 5) KVKK/PII Guvenli Aktarim + Asamali Yukleme ve Geri-Alma

Amac: Misafir verisi kisisel veridir (KVKK). Hem guvenli alinmali hem dogru
(sifreli) yazim yolundan girmeli; ve aktarim geri alinabilir olmali.

PII ve guvenlik kurallari:

- Misafir PII'si (ad/e-posta/telefon) MUTLAKA uygulamanin sifreli yazim yolundan
  girilir. Dogrudan veritabanina toplu insert YAPMAYIN: sifrelenmez ve arama
  icin gereken `_hash_` index uretilmez (misafir aranamaz + cigil acikta kalir).
- Her kayit dogru `tenant_id` ile yazilir (sistem bunu giris token'indan turetir;
  STRICT_TENANT_MODE altinda tenant'siz yazim reddedilir). Bu yuzden aktarim,
  o otelin yetkili hesabiyla API uzerinden yapilir.
- Eski veriyi otelden ACIK e-posta/mesajla DEGIL, sifreli bir kanalla alin
  (parolali arsiv / guvenli paylasim). KVKK rizasi olmayan veya kimligi eksik
  misafirleri ayri tutun; uydurma kimlik URETMEYIN.

Asamali yukleme ve geri-alma:

1. Once kucuk bir ORNEK (10-20 kayit) yukleyin (dry-run mantigi) ve dogrulayin:
   misafir aranabiliyor mu, rezervasyon dogru odaya/misafire bagli mi, folyo
   tutarlari tutuyor mu.
2. Dogrulama gecerse toplu yukleme yapin; betik tekrar calistirilabilir
   (idempotent) olmali - ayni kayit iki kez yazilmamali.
3. GERI-ALMA: yuklemeden ONCE yedek alin (otomatik gunluk yedek + bu aktarim
   icin elle bir yedek). Sorun cikarsa tenant-bazli temizlikle geri donun.
4. Pilot/test denemelerinde test kayitlarini ayirt edilebilir bir on-ekle
   (orn. belirgin bir test etiketi) yukleyin ki canli veriden ayrilabilsin ve
   temizlenebilsin; pilot tenant'in gercek verisi kirletilmemeli.

Sahada kullanim: "Ornek -> dogrula -> toplu -> yedek/geri-al" dongusu, sahada
panik yasamadan ilerlemenizi saglar; her adim geri alinabilir.

---

## Hizli On-Ziyaret Kontrol Listesi (yola cikmadan)

- [ ] 6 sablon (oda tipi, oda, fiyat, misafir, rezervasyon, folyo) hazir ve otele
      gonderildi.
- [ ] Zorunlu alan + enum (status) sozlugu yazdirildi.
- [ ] Demo/pilot tenant uzerinde "once iskelet" kurulum provasi yapildi.
- [ ] Temizleme/donusum kurallari yukleme betigine yazildi (tarih, status, telefon,
      indirim nedeni, sayisal sinirlar).
- [ ] Dedup/golden-record karar kurallari otelciyle gorusulecek sekilde hazir.
- [ ] Sifreli veri alim kanali + KVKK/eksik-kimlik istisna plani hazir.
- [ ] Yedek + geri-alma plani ve ornek->toplu asamalandirmasi netlesti.
