# Ortak acente finans ekranı

`/travel-agent-arap` içindeki **Acente Defteri**, seçili tesisin Extranet
acentelerini merkezi kimlikleriyle listeler. Yerel `agencies` kartı oluşturmak
gerekmez. Onaylı sözleşmesi bulunan, henüz rezervasyonu olmayan acente de
görünür. Sona eren sözleşmeler ve finans geçmişi ödeme takibi için korunur.
Başka tesisin sözleşmesi/ekstresi listeye alınmaz.

## Tek ödeme kaynağı

- Extranet bakiyeleri `core.agency_reports` üzerinden, portalın kullandığı
  `agency_statements` kayıtlarından hesaplanır.
- **Mutabakat ve ödeme**, ortak `StatementsWorkspace` bileşenini ilgili
  acenteye sabitler. Ödeme bildirimi, dekont, doğrulama ve tahsilat mevcut
  ekstre uçlarını kullanır; `agency_transactions` içine ikinci ödeme yazmaz.
- Acente → otel ve otel → acente ayrı gösterilir. TRY/EUR/USD birbirine
  çevrilmez veya eklenmez. Doğrulanmamış bildirim borçtan düşmez.
- Ekstreye henüz alınmamış tutar ve gelecek rezervasyon satışları, açık
  ekstre bakiyesinden ayrı gösterilir. Ödeme sonrası bakiye yeniden okunur.
- Eski ödeme/taksit API'leri, merkezi kimliği veya açık geçiş eşlemesi olan
  acenteye yeni yerel hareket yazılmasını 409 ile reddeder.

## Yerel geçmiş ve görünürlük

Eski manuel cariler ayrı etiketlenir; toplamları Extranet bakiyelerine
eklenmez. Merkezi kimliğiyle aynı olan veya açık migration eşlemesi bulunan
yerel kart, varsayılan listede tekrar gösterilmez. Geçmişi arşiv görünümünden
salt okunur incelenebilir. Sadece isim/e-posta benzerliğiyle eşleştirme yoktur.

Pasif, işaretli test/demo kartlar ve tam eski demo seed parmak iziyle eşleşen
örnek kayıtlar varsayılan görünümden çıkarılır. **Pasif / test / örnek
kayıtları göster** seçeneği geçmişlerini açar. Sadece aynı acente adına
sahip olmak demo sayılmak için yeterli değildir. `Test Acente E2E` gibi gerçek
test kabul hesabı normal bir merkezi acente olarak listelenir.

Gerçek pasif yerel acentenin geçmiş borcu kapatılabilir. Test/demo ve geçiş
yapılmış yerel kayıtlarına yeni finans hareketi yazılmaz. Kayıtlar, ödemeler
ve rezervasyonlar bu değişiklikle silinmez, iptal edilmez veya otomatik
mahsuplaştırılmaz. Mevcut bağımsız eski hareketler kanıtsız biçimde merkezi
ekstrelere aktarılmaz.

## Tarih kapsamı

Performans raporu giriş tarihine göre satış gösterir. Örneğin Ekim dönemi
sıfırken Kasım rezervasyonu varsa, rapor bunu açıklar ve **Gelecek
rezervasyonları göster** ile ileri satış görünümüne geçer. Açık bakiyeler ve
gelecek 30/60/90 gün hesabı seçilen satış döneminden bağımsızdır.

Kod dağıtımı dışında canlı veri temizliği veya veri taşıma komutu gerekmez.
