# Syroce hesabıyla bağlan

Bu akış Syroce Agency ile Syroce PMS Marketplace hesabını, kullanıcıya kalıcı
API anahtarı göstermeden bağlar. OAuth 2.0 authorization-code davranışını PKCE
S256 ile uygular.

## İstemci kaydı

Üretimde PMS backend ortamına tam eşleşen istemci ve dönüş adresleri tanımlanır:

```env
SYROCE_AGENCY_CONNECT_CLIENTS_JSON={"syroce_agency":{"name":"Syroce Agency","redirect_uris":["https://agency.syroce.com/auth/syroce/callback"]}}
```

Wildcard dönüş adresi desteklenmez. Yapılandırma verilmezse yalnızca Syroce
Agency üretim dönüş adresi ve yerel geliştirme adresi kullanılabilir.

## Syroce Agency tarafı

1. Agency backend 43–128 karakterlik rastgele `code_verifier` üretir ve oturumda
   kısa süreli saklar. `code_challenge`, verifier'ın SHA-256 sonucunun base64url
   (padding olmadan) karşılığıdır.
2. Tarayıcı şu adrese yönlendirilir:

   ```text
   https://pms.syroce.com/agency-connect/authorize?client_id=syroce_agency&redirect_uri=...&code_challenge=...&state=...
   ```

3. Dönüşte Agency backend `state` değerini doğrular.
4. Agency backend (tarayıcı değil) aşağıdaki isteği yapar:

   ```http
   POST /api/marketplace/v1/connect/token
   Content-Type: application/json

   {
     "client_id": "syroce_agency",
     "redirect_uri": "https://agency.syroce.com/auth/syroce/callback",
     "code": "...",
     "code_verifier": "..."
   }
   ```

5. Dönen `access_token` Agency backend secrets vault'unda şifreli saklanır ve
   Marketplace isteklerinde `X-API-Key` başlığıyla kullanılır. Token tarayıcıya,
   mobil uygulamaya, loglara veya analitik olaylara gönderilmez.

Kod beş dakika geçerlidir, tek kullanımlıktır ve kayıtlı dönüş adresine bağlıdır.
Yeniden bağlantı aynı acente/istemci için eski etkin anahtarı iptal eder.
