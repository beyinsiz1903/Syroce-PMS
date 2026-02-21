# PCI DSS Uyumluluk Rehberi

## Ödeme Kartı Bilgisi Saklama/İşleme Standartları

### 1. PCI DSS Kapsamı

RoomOps PMS, doğrudan kart bilgisi saklamaz. Ödeme işlemleri için PCI DSS Level 1
sertifikalı üçüncü parti ödeme sağlayıcıları (Stripe, iyzico, vb.) kullanılır.

### 2. Uyumluluk Kontrol Listesi

#### Gereksinim 1: Güvenlik Duvarı
- [x] Ağ segmentasyonu uygulandı
- [x] Kubernetes NetworkPolicy tanımlı
- [x] WAF (Web Application Firewall) aktif

#### Gereksinim 2: Varsayılan Şifreler
- [x] Tüm varsayılan şifreler değiştirildi
- [x] Güçlü şifre politikası uygulandı (bcrypt hashing)
- [x] JWT secret ortam değişkeninden alınıyor

#### Gereksinim 3: Kart Verisi Koruma
- [x] PAN (Primary Account Number) saklanmıyor
- [x] CVV hiçbir zaman saklanmıyor
- [x] Tokenization kullanılıyor (Stripe/iyzico token)
- [x] Sadece son 4 hane ve kart tipi saklanıyor

#### Gereksinim 4: Şifreleme
- [x] TLS 1.2+ zorunlu (tüm API iletişimi)
- [x] MongoDB at-rest encryption aktif
- [x] Hassas veriler AES-256 ile şifreli

#### Gereksinim 5: Anti-Malware
- [x] Container image scanning (CI/CD)
- [x] Dependency vulnerability scanning
- [x] Regular security patches

#### Gereksinim 6: Güvenli Geliştirme
- [x] Secure SDLC uygulandı
- [x] Code review zorunlu
- [x] Input validation (Pydantic models)
- [x] SQL/NoSQL injection koruması
- [x] XSS koruması (React auto-escaping)

#### Gereksinim 7: Erişim Kontrolü
- [x] RBAC (Role-Based Access Control)
- [x] Principle of least privilege
- [x] API rate limiting
- [x] IP bazlı erişim kontrolü

#### Gereksinim 8: Kimlik Doğrulama
- [x] Benzersiz kullanıcı kimliği
- [x] 2FA (TOTP) desteği
- [x] Oturum zaman aşımı (7 gün)
- [x] Hesap kilitleme (brute-force koruması)

#### Gereksinim 9: Fiziksel Erişim
- [x] Cloud altyapı (AWS/GCP fiziksel güvenlik)
- [x] Kubernetes pod isolation

#### Gereksinim 10: İzleme ve Loglama
- [x] Kapsamlı audit log sistemi
- [x] APM ve performans izleme
- [x] Hata loglama
- [x] Güvenlik olayı uyarıları

#### Gereksinim 11: Güvenlik Testi
- [x] Düzenli penetrasyon testi
- [x] Vulnerability scanning
- [x] Intrusion detection

#### Gereksinim 12: Güvenlik Politikası
- [x] Bilgi güvenliği politikası
- [x] Olay müdahale planı
- [x] Personel güvenlik eğitimi

### 3. Ödeme Entegrasyonu Mimarisi

```
[Kullanıcı] → [RoomOps Frontend] → [Stripe.js / iyzico Widget]
                                           ↓
                                    [Ödeme Sağlayıcı]
                                           ↓
                                    [Token oluşturma]
                                           ↓
[RoomOps Backend] ← [Token] ← [Frontend]
        ↓
[Ödeme Sağlayıcı API] (Token ile işlem)
        ↓
[Sonuç] → [RoomOps Backend] → [Veritabanı (sadece token, son 4 hane)]
```

### 4. SAQ (Self-Assessment Questionnaire)

RoomOps PMS, **SAQ A** kapsamındadır:
- Tüm ödeme sayfaları üçüncü parti tarafından barındırılır
- Kart verileri sunucularımızdan hiç geçmez
- Yıllık öz-değerlendirme yeterlidir
