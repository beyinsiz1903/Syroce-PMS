# Zoho Mail HTTPS kurulumu

DigitalOcean SMTP çıkışı kapalı olduğunda Mesajlaşma Merkezi e-postaları
`Zoho Mail HTTPS API (443)` üzerinden gönderilebilir. Mevcut SMTP ve WhatsApp
entegrasyonları değişmez; e-posta otomasyonları seçilen yöntemi kullanır.
SMTP'ye otomatik geri dönüş yapılmaz.

## OAuth hazırlığı

1. Gönderen hesabın bölgesindeki Zoho API Console'da bir OAuth istemcisi
   oluşturun. Tek işletmenin kendi hesabı için Self Client kullanılabilir.
2. Yalnız `ZohoMail.accounts.READ,ZohoMail.messages.CREATE` kapsamlarıyla
   gönderen hesabın yetkisini alın. Yetkilendirme kodunu süresi dolmadan aynı
   bölgenin OAuth token uç noktasında refresh token'a dönüştürün.
   Bu adım yönetici tarafından güvenli ortamda yapılmalıdır; anahtarları
   sohbete, Git'e, URL'ye veya loglara koymayın.
3. Zoho hesap ayarlarından hesap kimliğini doğrulayın. Kullanıcı adı, SMTP
   parolası veya uygulama parolası OAuth refresh token yerine geçmez.

Resmî belgeler:
- https://www.zoho.com/mail/help/api/using-oauth-2.html
- https://www.zoho.com/mail/help/api/get-all-users-accounts.html
- https://www.zoho.com/mail/help/api/post-send-an-email.html

## PMS ayarları

Mesajlaşma Merkezi → Ayarlar → Gönderim yöntemi → Zoho Mail HTTPS API.
Bölgeyi (EU/US), hesap kimliğini, Client ID, Client Secret, Refresh Token ve
doğrulanmış gönderen adresini girin. Gizli alanlar şifrelenir; boş bırakılan
gizli alanlar mevcut değerleri korur. Alan şifreleme servisi yoksa yeni Zoho
ayarları kaydedilmez. Gönderen görünen adı Zoho hesabında yönetilir.

Yöntem değişikliği sunucuda zorunlu olarak sandbox modunda kaydedilir.
Önce otomasyonları ve alıcıları kontrol edin. Gerçek bağlantı testi için
sandbox'u kapatıp kaydedin; bağlantı testi e-posta göndermez, OAuth ve hesap
eşleşmesini doğrular. Gönderim kapsamı ve teslimat ancak izinli bir test
alıcısına gönderimle doğrulanabilir. Canlı moda geçiş etkin otomasyonları da
etkiler; test sırasında e-posta otomasyonlarını kapalı tutun.

Access token süre dolmadan önbellekten kullanılır, refresh token ile yeniden
alınır. Yetki iptal edilirse OAuth kurulumu yenilenmelidir. Sunucunun hem
`accounts.zoho.eu` hem `mail.zoho.eu` adreslerine 443 çıkışı gereklidir (US
için `.com`). HTTP yönlendirmeleri izlenmez.

Gönderim POST isteğinden sonra zaman aşımı/bozuk yanıt/5xx oluşursa kayıt
`unknown` olur; otomatik veya manuel yeniden deneme kapatılır. Önce Zoho
Gönderilenler klasöründen sonucu uzlaştırın; aynı mesajı körlemesine yeniden
göndermeyin. API kabulü, alıcının gelen kutusuna teslim edildiği anlamına gelmez.
