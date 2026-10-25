# Muhasebe fişi onay politikası

Genel Muhasebe → Hızlı Fiş Girişi ekranındaki **Fiş onay politikası** yalnız seçili tesise aittir.

- **Yetkili kendisi kesinleştirebilir** (varsayılan): muhasebe yetkili rolleri (`finance`, `admin`, `super_admin`) kendi taslaklarını veya incelemedeki fişlerini **Gerekçeyle Kesinleştir** ile yevmiyeye işler. Ayrı kullanıcı gerekmez.
- **İkinci kişi onayı zorunlu**: taslak incelemeye gönderilir. Hazırlayan dışında muhasebe yetkili bir kullanıcı gerekçeyle onaylar; ardından yevmiyeye işlenir. Süperadmin dâhil hazırlayan kullanıcı bu modda kendi fişini onaylayamaz.

Yalnız `admin` / `super_admin` politikayı değiştirebilir. Değişiklik gerekçesi ve önceki/yeni politika sürümü denetim kaydında saklanır. Eski ekrandan eşzamanlı ayar değişikliği reddedilir. Ayar alınamaz veya bozuksa arayüz kesinleştirmeyi açmaz. Politika kaydı olmayan mevcut tesisler de varsayılan tek-yetkili modelini kullanır; çift kontrol isteyen tesisler bunu açıkça seçmelidir.

Fişin kullanıcı, zaman, gerekçe, tutarlar, kendi fişini onaylama bilgisi ve işlem geçmişi korunur. Kapalı dönem, aktif hesap, borç/alacak dengesi, tesis ayrımı, tekrar işlem güvenliği ve mühürlü yevmiye kontrolleri kaldırılmaz. Kesinleşmiş kayıt değiştirilmez; düzeltme bağlı ters kayıtla yapılır.

Politika ikinci kişi moduna geçirilmeden önce kendi hazırlayanı tarafından onaylanmış ama henüz işlenmemiş fişler, farklı yetkili tarafından yeniden onaylanmalıdır. Başlamış bir yevmiye işleminin güvenli kurtarma/tekrar akışı korunur. Politikayı değiştirmek eski yevmiyeleri veya finansal dayanakları değiştirmez.

Hediye kartı / cüzdan fonlaması misafir tahsilatıyla aynı şey değildir. Kaynak hakkı ancak muhasebede önceden kesinleşmiş, mühürlü yükümlülük fişinden ayrılır. Onay akışını sadeleştirmek karşılıksız bakiye yaratmaya izin vermez; fonlama belgesi, para birimi ve kullanılmamış kaynak bakiyesi yine doğrulanır. Yapay sunum fonlamaları gerçek banka tahsilatı olarak sunulmamalıdır.

## Folyo gösterim düzeltmesi

Mahsup ve bağlı ters kayıtlar ortak imzalı ödeme hesabını kullanır. Ters kayıt borcu geri getirir; bakiyeyi yeniden azaltmaz. Net tahsilat ile nakit dışı mahsup ayrı gösterilir. Kaynaklı işlemler genel nakit iade düğmesiyle değil, özgün kaynağa bağlı ters kayıtla düzeltilir. Ekran ve yazdırma aynı bakiye etkisini kullanır.

Bu değişikliğin yayına alınması, canlı hediye kartı/cüzdan kabulünün tamamlandığı anlamına gelmez. Demo fonlama fişleri yayından sonra normal yetkili API/ekran akışıyla kesinleştirilmeli; uygulama, tekrar deneme, ters kayıt ve rapor mutabakatı ayrıca doğrulanmalıdır. Online ödeme sağlayıcısı kapsam dışıdır.

## Kaynaklı yevmiyelerde genel ters kayıt koruması

Hediye kartı/cüzdan/sadakat/barter/alacaktan silme/çek mahsuplarının yevmiyeleri Genel Muhasebe'den tek başına ters çevrilemez. Rezervasyondaki özgün mahsuba bağlı akış, folyo, hak/puan, muhasebe ve gerekçeyi birlikte düzeltir. Kaynak haklarına tahsis edilmiş fonlama fişi de bağımsız ters çevrilemez; haklar hâlâ etkin olduğundan yalnız muhasebeyi çevirmek karşılıksız hak bırakır.

Genel muhasebe ters kaydı transaction içinde, hak açma/mahsup işlemleriyle aynı tesis kilidini kullanır. İlk hak tahsisiyle fonlamanın ters kaydı yarışırsa yalnız biri kesinleşir. Audit zinciri, ters yevmiye ve özgün fişin bağlantı alanları birlikte kesinleşir; audit kaydı başarısızsa finansal yazılar da geri alınır. Transaction desteği yoksa güvenli olmayan işleme düşülmez.

Henüz hak tahsis edilmemiş sıradan bir fonlama kaydı normal muhasebe akışıyla ters çevrilebilir. Ancak böyle bir fişten daha sonra hediye kartı/cüzdan hakkı üretilemez. Eski veya haricî yoldan ters çevrilmiş fonlama kaynakları da yeni kullanımda reddedilir; mevcut bağlı operasyonların mutabakatı bu durumu hata olarak gösterir. Ekrandaki genel ters kayıt düğmesi yerine açıklama gösterilir; API kontrolü düğmeden bağımsızdır.

Yıllık bütünlük kontrolü, eski fişlerde `fiscal_year` veya posting sırası bulunmamasını kaydı kapsamdan çıkarmak için kullanmaz: kanonik muhasebe tarihi ilgili yıl içindeyse mühürsüz fiş uyarıya dahil edilir. Eski kayıtlar yeniden mühürlenmez veya değiştirilmez; "tam mühürlü" durumu eksikler varken yeşil gösterilmez.
