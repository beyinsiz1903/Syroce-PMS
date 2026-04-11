# Penetrasyon Testi & Güvenlik Audit Planı

## 1. Kapsam

### Test Edilecek Bileşenler
- API Endpoints (1161+ endpoint)
- Authentication & Authorization
- Data Isolation (multi-tenant)
- Frontend Security
- Infrastructure Security

### Test Dışı
- Üçüncü parti hizmetler (Stripe, MongoDB Atlas)
- CDN altyapısı

## 2. Test Metodolojisi

### OWASP Top 10 (2025)

| # | Risk | Test Yöntemi | Araç |
|---|------|-------------|------|
| A01 | Broken Access Control | Manual + Auto | Burp Suite |
| A02 | Cryptographic Failures | Config review | SSL Labs |
| A03 | Injection | Fuzz testing | SQLMap, wfuzz |
| A04 | Insecure Design | Architecture review | Manual |
| A05 | Security Misconfiguration | Scanner | Nmap, Nikto |
| A06 | Vulnerable Components | Dependency scan | Snyk, safety |
| A07 | Auth Failures | Brute force test | Hydra |
| A08 | Software Integrity | Supply chain check | Manual |
| A09 | Logging Failures | Log review | Manual |
| A10 | SSRF | Request testing | Burp Suite |

### Multi-Tenant İzolasyon Testleri

1. **Horizontal Privilege Escalation**
   - Tenant A kullanıcısı ile Tenant B verilerine erişim denemesi
   - Booking/Guest/Room ID manipulation
   - API parameter tampering

2. **Vertical Privilege Escalation**
   - staff → admin yetki yükseltme
   - admin → super_admin yetki yükseltme
   - Role bypass testleri

3. **Data Leakage**
   - Error message bilgi sızıntısı
   - API response'larda cross-tenant veri
   - Debug endpoint'leri

## 3. Test Takvimi

| Hafta | Aktivite | Sorumlu |
|-------|---------|--------|
| 1 | Kapsam belirleme, bilgi toplama | Security Team |
| 2 | Otomatik tarama (Nmap, Nikto, OWASP ZAP) | Security Team |
| 3 | Manuel test (auth, authz, injection) | Pen Tester |
| 4 | Multi-tenant izolasyon testleri | Pen Tester |
| 5 | Rapor hazırlama | Security Team |
| 6 | Düzeltme ve re-test | Dev + Security |

## 4. Araçlar

- **Burp Suite Professional**: Ana pen test aracı
- **OWASP ZAP**: Otomatik tarama
- **Nmap**: Port/servis tarama
- **Nikto**: Web server tarama
- **SQLMap**: Injection testi
- **Hydra**: Brute force testi
- **SSL Labs**: SSL/TLS değerlendirme
- **Snyk/Safety**: Bağımlılık güvenlik tarama

## 5. Kabul Kriterleri

- Kritik bulgu: 0
- Yüksek bulgu: 0
- Orta bulgu: < 5 (düzeltme planı ile)
- Düşük bulgu: < 20 (risk kabul edilebilir)
