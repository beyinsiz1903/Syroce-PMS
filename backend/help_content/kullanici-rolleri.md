# Kullanıcı Rolleri ve Yetkilendirme

Syroce PMS, **rol-tabanlı erişim kontrolü (RBAC)** kullanır. Her kullanıcı bir veya birden çok role atanır; her rolün belirli modüllere ve aksiyonlara erişim hakları vardır.

## Standart Roller

| Rol | Açıklama |
|-----|----------|
| **Super Admin** | Tüm modüller, tenant yönetimi, sistem ayarları |
| **Genel Müdür (GM)** | Operasyonel + finansal raporlar, KPI dashboard |
| **Ön Büro Müdürü** | Rezervasyon, check-in/out, fiyat ayarları |
| **Resepsiyonist** | Check-in/out, folio, ödeme alma |
| **Muhasebe** | Folio, fatura, vergi beyannamesi, raporlar |
| **Housekeeping Şefi** | Oda durumu, görev atama, kayıp eşya |
| **Satın Alma** | PR, RFQ, PO, GRN, tedarikçi yönetimi |
| **Misafir İlişkileri** | Misafir profili, şikayet, mesajlaşma |

## Yeni Kullanıcı Ekleme

**Yönetim > Kullanıcılar** ekranından "Yeni Kullanıcı" butonuna basın. Zorunlu alanlar:

- E-posta (giriş için kullanılacak)
- Tam ad
- Rol (yukarıdaki listeden)
- 2FA gerekli mi (önerilir)

Sistem, kullanıcıya geçici şifre ile e-posta gönderir. İlk girişte şifre değiştirme zorunludur.

## İzin Devri

Bir kullanıcı izine ayrıldığında, **Yönetim > Kullanıcılar > [kullanıcı] > İzin Devri** ekranından geçici olarak başka bir kullanıcıya izinleri devredilebilir. Devir tarihi geldiğinde otomatik olarak iptal edilir.

## Audit

Kullanıcıların yaptığı tüm önemli işlemler **Audit Timeline**'da kaydedilir. Sağ üstteki tarih ikonundan herhangi bir kayıt için kim/ne/ne zaman bilgisini görebilirsiniz.
