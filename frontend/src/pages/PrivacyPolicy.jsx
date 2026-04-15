import React from 'react';
import { useTranslation } from 'react-i18next';

export default function PrivacyPolicy() {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-white" data-testid="privacy-policy-page">
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="flex items-center gap-3 mb-8">
          <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/></svg>
          <h1 className="text-3xl font-bold text-gray-900">Gizlilik Politikasi / Privacy Policy</h1>
        </div>
        <p className="text-sm text-gray-500 mb-8">Son guncelleme / Last updated: 25 Subat 2026</p>

        <div className="space-y-8 text-gray-700 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">1. Giris / Introduction</h2>
            <p>Syroce PMS ("Uygulama", "Biz") olarak kullanicilarimizin gizliligini korumaya onem veriyoruz. Bu Gizlilik Politikasi, kisisel verilerinizi nasil topladigimizi, kullandigimizi, paylasitigimizi ve korudigimizi aciklar.</p>
            <p className="mt-2">Syroce PMS ("App", "We") values the privacy of our users. This Privacy Policy explains how we collect, use, share, and protect your personal data.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">2. Toplanan Veriler / Data We Collect</h2>
            <p className="font-medium mb-2">Asagidaki kisisel verileri topluyoruz / We collect the following personal data:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li><strong>Hesap Bilgileri / Account Info:</strong> Ad, soyad, e-posta adresi, sifre (sifrelenmis / encrypted)</li>
              <li><strong>Otel Bilgileri / Hotel Info:</strong> Otel adi, oda bilgileri, rezervasyon verileri</li>
              <li><strong>Misafir Bilgileri / Guest Info:</strong> Misafir adi, iletişim bilgileri, kimlik numarası, konaklama geçmişi</li>
              <li><strong>Finansal Veriler / Financial Data:</strong> Fatura bilgileri, ödeme kayitlari, folio detayları</li>
              <li><strong>Kullanim Verileri / Usage Data:</strong> Uygulama kullanim istatistikleri, cihaz bilgileri, IP adresi</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">3. Verilerin Kullanimi / How We Use Data</h2>
            <p>Topladimiz verileri asagidaki amaclarla kullaniyoruz / We use collected data for:</p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>Otel yonetim hizmetlerini saglamak / Providing hotel management services</li>
              <li>Hesap olusturma ve kimlik dogrulama / Account creation and authentication</li>
              <li>Rezervasyon ve misafir yonetimi / Booking and guest management</li>
              <li>Raporlama ve analitik / Reporting and analytics</li>
              <li>Uygulama performansini iyilestirmek / Improving app performance</li>
              <li>Yasal yukumlulukleri yerine getirmek / Complying with legal obligations</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">4. Veri Paylasimi / Data Sharing</h2>
            <p>Kisisel verilerinizi ucuncu taraflarla satmiyoruz. Verilerinizi yalnizca asagidaki durumlarda paylasabiliriz:</p>
            <p className="mt-1">We do not sell your personal data. We may share your data only in these cases:</p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>Yasal zorunluluklar gerektirdiginde / When required by law</li>
              <li>Hizmet saglayicilarimiz ile (sunucu, veritabani) / With our service providers (servers, database)</li>
              <li>Açık izniniz ile / With your explicit consent</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">5. Veri Guvenligi / Data Security</h2>
            <p>Verilerinizi korumak için asagidaki onlemleri aliyoruz / We take the following measures to protect your data:</p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>SSL/TLS sifreleme ile veri iletimi / Data transmission with SSL/TLS encryption</li>
              <li>Sifreler bcrypt ile hashlenir / Passwords are hashed with bcrypt</li>
              <li>JWT tabanli guvenli kimlik dogrulama / JWT-based secure authentication</li>
              <li>Rol tabanli erisim kontrolu / Role-based access control</li>
              <li>Duzeli guvenlik denetimleri / Regular security audits</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">6. Veri Saklama / Data Retention</h2>
            <p>Kisisel verilerinizi, hizmet sundugumuz sure boyunca ve yasal yukumluluklerin gerektirdigi sure boyunca saklariz. Hesabinizi sildiginizde, kisisel verileriniz makul bir sure icinde silinir.</p>
            <p className="mt-1">We retain your personal data for as long as we provide services and as required by legal obligations. When you delete your account, your personal data will be deleted within a reasonable time.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">7. Kullanici Haklari / Your Rights</h2>
            <p>KVKK ve GDPR kapsaminda asagidaki haklara sahipsiniz / Under KVKK and GDPR, you have the right to:</p>
            <ul className="list-disc pl-6 space-y-1 mt-2">
              <li>Verilerinize erisim talep etme / Request access to your data</li>
              <li>Verilerinizin duzeltilmesini isteme / Request correction of your data</li>
              <li>Verilerinizin silinmesini talep etme / Request deletion of your data</li>
              <li>Veri tasima hakki / Right to data portability</li>
              <li>Islem kisitlama hakki / Right to restrict processing</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">8. Cerezler / Cookies</h2>
            <p>Uygulamamiz, oturum yonetimi için gerekli cerezleri kullanir. Analitik veya ucuncu taraf cerezleri kullanilmaz.</p>
            <p className="mt-1">Our app uses essential cookies for session management. No analytics or third-party cookies are used.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">9. Degisiklikler / Changes</h2>
            <p>Bu gizlilik politikasini zaman zaman guncelleyebiliriz. Degisiklikler bu sayfada yayinlanacaktir.</p>
            <p className="mt-1">We may update this privacy policy from time to time. Changes will be posted on this page.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">10. İletişim / Contact</h2>
            <p>Gizlilik politikamiz hakkinda sorulariniz için bize ulasin:</p>
            <p className="mt-1">For questions about our privacy policy, contact us:</p>
            <div className="mt-3 p-4 bg-gray-50 rounded-lg">
              <p className="font-medium">Syroce Hotel Management</p>
              <p>E-posta / Email: privacy@syroce.com</p>
              <p>Web: https://syroce.com</p>
            </div>
          </section>
        </div>

        <div className="mt-12 pt-8 border-t text-center text-sm text-gray-400">
          <p>&copy; 2026 Syroce Hotel Management. Tum haklari saklidir / All rights reserved.</p>
        </div>
      </div>
    </div>
  );
}
