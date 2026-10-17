# Acente web sitesi rezervasyon widget'ı

## Kurulum

1. Acente Extranet → Ayarlar → Web sitesi ve API bölümünde izinli web sitesi
   kök adreslerini kaydedin. Her satıra tam bir HTTPS origin yazın:
   `https://acente.example` ve gerekiyorsa `https://www.acente.example` ayrı
   adreslerdir. Sayfa yolu, joker alan adı, kullanıcı bilgisi veya sorgu kabul
   edilmez. HTTP yalnız `localhost` / `127.0.0.1` geliştirme testi içindir.
2. Oluşan iframe kodunu izin verdiğiniz web sitesine ekleyin. Kodun
   `referrerpolicy="strict-origin"` özelliğini koruyun; API çağrılarında üst
   sayfanın origin'i kullanılır. Tüm iframe üst atalarının izinli olması gerekir.
3. Acente sözleşmesinin aktif, fiyat/kontenjanın paylaşılmış, kredi limitinin
   yeterli olduğunu doğrulayın. Widget aynı ortak rezervasyon servisini kullanır;
   online kart tahsilatı sağlamaz, acente sözleşmesi üzerinden rezervasyon açar.

E-posta isteğe bağlıdır. Boş değer `null` olarak gönderilir; sunucu da boş/yalnız
boşluk içeren e-postayı bu şekilde yorumlar. Girilen geçersiz e-posta reddedilir.

## İframe güvenlik sınırı

- Yalnız tam `/agency-widget` sayfası cross-origin iframe'e açılır. PMS'nin diğer
  sayfalarının `X-Frame-Options: SAMEORIGIN` politikası değiştirilmez.
- Frontend Nginx, HTML'i vermeden önce dahili auth subrequest ile public widget
  anahtarını doğrulatır. Backend aktif acenteyi, anahtar sürümünü ve güncel izinli
  adresleri kontrol ederek `frame-ancestors` CSP üretir. HTML ve API aynı origin
  normalizasyonunu kullanır. API anahtarı veya kullanıcı oturumu gerekmez.
- Geçersiz/yenilenmiş anahtar, pasif acente veya boş izin listesi HTML'i engeller.
  Backend erişilemiyorsa başarısız olur; eksik politika bütün iframe'leri engeller.
- Dış Nginx katmanı yalnız bu sayfada SAMEORIGIN eklemez ve frontend'in CSP'sini
  korur. Ortak CSP ve HSTS devam eder. Politika HTML'e aittir; yalnız API yanıtına
  CSP eklemek iframe engelini çözmez.
- Widget HTML'i ve widget API okumaları service worker/offline shell cache'inden
  kullanılmaz. Başka acentenin CSP'si yeniden kullanılamaz ve widget HTML'i PMS
  çevrimdışı kabuğunun üstüne yazılmaz. Belgede `Cache-Control: no-store` vardır.

## Dağıtım ve kabul kontrolü

Backend, frontend imajı ve `infra/nginx/prod.conf` birlikte dağıtılmalıdır.
Mevcut `Deploy to Droplet` akışı Nginx bind-mount değişikliğini `nginx -t` ve
reload ile uygular. Yalnız frontend JS güncellemesi yeterli değildir.

Dağıtımdan sonra kontrollü test tesisinde doğrulayın:

- İzinli HTTPS sitede iframe açılır; izinli olmayan sitede tarayıcı CSP nedeniyle
  engeller. Belge yanıtında `frame-ancestors` yalnız kaydedilen origin'leri içerir,
  `X-Frame-Options: SAMEORIGIN` bulunmaz. PMS sayfalarında SAMEORIGIN hâlâ vardır.
- Tarih/oda/fiyat planı araması ve e-posta boş/dolu rezervasyon denemeleri doğru
  sonuç verir. Yapılandırılmış API hatası okunabilir metin olur; sayfa çökmez.
- Anahtar sürümü / origin izni değişikliği bir sonraki belge yüklemesinde etkilidir.
- Önce gerçek misafire ait olmayan test rezervasyonuyla PMS kaydı, kontenjan ve
  kredi etkisi kontrol edilir; üretim verisiyle otomatik test yapılmaz.

Yerel testler:

```sh
cd backend
NGINX_BIN=/path/to/nginx pytest tests/unit/test_agency_widget_embedding.py tests/unit/test_agency_widget_nginx.py -q
```

Nginx `http_auth_request` ve SSL modülleriyle derlenmiş olmalıdır. Test, iki gerçek
Nginx yapılandırmasını yalnız loopback geçici portlarda ve sahte backend ile
çalıştırır. Nginx yoksa atlanmaz, hata verir. CI iki backend kapısında Nginx kurar.

```sh
cd frontend
yarn vitest run src/pages/__tests__/AgencyBookingWidget.test.jsx src/utils/__tests__/serviceWorkerWidget.test.js src/utils/__tests__/serviceWorkerOfflineShell.test.js
```
