/**
 * Landing-page content defaults + merge helper.
 *
 * The public landing page (LandingPage.jsx) renders these built-in values
 * unless a super_admin has saved overrides via the site-content editor
 * (GET /api/site-content). Only the operator-editable surfaces live here:
 * brand name, hero copy, contact details, solution cards and FAQ entries.
 * Everything else on the landing page stays hard-coded in LandingPage.jsx.
 *
 * The shape matches the backend SiteContent pydantic model exactly so the
 * same object round-trips through GET/PUT without transformation. Icons are
 * NOT stored (they stay positional, owned by LandingPage). The merge is
 * "never-blank": an empty/missing override field falls back to the default,
 * so the landing page is never rendered with blank text.
 */

export const landingDefaults = {
  brandName: 'Syroce',
  hero: {
    badge: 'MODERN HOSPITALITY OPERATING SYSTEM',
    titlePre: 'Konaklama',
    titleAccent: 'Operasyonunun',
    titlePost: 'Yeni Merkezi',
    description:
      'Rezervasyondan gelire kadar tüm otel operasyonlarını tek akıllı platformda birleştirin. PMS, misafir deneyimi, tedarik ağı ve raporlama —',
    descriptionAccent: ' tek işletim sistemi.',
  },
  contact: {
    phone: '0540 452 93 26',
    email: 'info@syroce.com',
    address: 'Kocaeli / Kartepe',
  },
  solutions: [
    { title: 'Otel Yönetimi',          desc: 'Rezervasyon, oda, ön büro, check-in ve check-out — tek ekrandan kontrol.' },
    { title: 'Misafir Deneyimi',       desc: 'Talepler, mesajlaşma, QR çözümleri ve memnuniyet ölçümü bir arada.' },
    { title: 'Tedarik ve Satın Alma',  desc: 'Otelleri ve tedarikçileri aynı ekosistemde buluşturan akıllı yapı.' },
    { title: 'Raporlama ve Kontrol',   desc: 'İşletmenizi anlık görün, daha hızlı ve daha sağlam kararlar verin.' },
    { title: 'Satış ve Operasyon',     desc: 'İş akışını sadeleştirin, ekibinizin zamanını asıl işine ayırın.' },
    { title: 'Çoklu İşletme Yönetimi', desc: 'Birden fazla tesisi tek panelden, sade ve düzenli şekilde yönetin.' },
  ],
  faqs: [
    { q: 'Bu sistem kimler için uygun?',          a: 'Oteller, apart tesisler, butik oteller, restoranlar, turizm firmaları ve tedarikçiler — operasyonunu dijitalleştirmek isteyen her ölçekte işletme için uygundur.' },
    { q: 'Kurulum süreci zor mu?',                a: 'Hayır. Hesabınızı açtıktan sonra rehberli adımlarla işletmenizi tanıtırsınız ve aynı gün kullanmaya başlayabilirsiniz. Ekibimiz kurulumda yanınızdadır.' },
    { q: 'Birden fazla işletme yönetebilir miyim?', a: 'Evet. Birden fazla tesisi veya markayı tek panelden yönetebilir, her biri için ayrı yetki ve raporlama tanımlayabilirsiniz.' },
    { q: 'Tedarikçi olarak nasıl katılabilirim?', a: 'Üst menüden Tedarikçi Girişi alanına geçebilir, kayıt formunu doldurarak başvurunuzu birkaç dakikada tamamlayabilirsiniz.' },
    { q: 'Mobil cihazda kullanılabiliyor mu?',    a: 'Evet. Tüm panel mobil ve tablet cihazlarda sorunsuz çalışır. Ekibiniz sahada da aynı verilere erişir.' },
    { q: 'Teknik bilgi gerekir mi?',              a: 'Hayır. Arayüz sade Türkçe ile tasarlandı; günlük operasyonu yapan herkes ilk günden rahatça kullanabilir.' },
    { q: 'Demo talep edebilir miyim?',            a: 'Elbette. İletişim formundan ulaştığınızda ekibimiz sizinle iletişime geçer ve işletmenize özel bir tanıtım planlar.' },
    { q: 'Destek süreci nasıl işliyor?',          a: '7/24 erişebileceğiniz canlı destek hattı, e-posta ve telefon kanallarımız mevcuttur. Kritik durumlarda hızlı geri dönüş garantilidir.' },
  ],
};

const isFilled = (v) => typeof v === 'string' && v.trim().length > 0;

function mergeFields(def, ov) {
  const out = { ...def };
  if (ov && typeof ov === 'object') {
    for (const key of Object.keys(def)) {
      out[key] = isFilled(ov[key]) ? ov[key] : def[key];
    }
  }
  return out;
}

/**
 * Overlay stored overrides on top of the defaults with never-blank semantics:
 *  - scalar/object string fields: a blank or missing override falls back to default;
 *  - arrays (solutions/faqs): when the override array is non-empty it replaces the
 *    default wholesale, and each row's blank fields fall back to the positional
 *    default when one exists. An empty array falls back to the full default list.
 */
export function mergeLandingContent(override) {
  const ov = override && typeof override === 'object' ? override : {};

  const solutions =
    Array.isArray(ov.solutions) && ov.solutions.length
      ? ov.solutions.map((s, i) =>
          mergeFields(landingDefaults.solutions[i] || { title: '', desc: '' }, s),
        )
      : landingDefaults.solutions;

  const faqs =
    Array.isArray(ov.faqs) && ov.faqs.length
      ? ov.faqs
          .map((f) => ({
            q: isFilled(f?.q) ? f.q : '',
            a: isFilled(f?.a) ? f.a : '',
          }))
          .filter((f) => f.q || f.a)
      : landingDefaults.faqs;

  return {
    brandName: isFilled(ov.brandName) ? ov.brandName : landingDefaults.brandName,
    hero: mergeFields(landingDefaults.hero, ov.hero),
    contact: mergeFields(landingDefaults.contact, ov.contact),
    solutions: solutions.length ? solutions : landingDefaults.solutions,
    faqs: faqs.length ? faqs : landingDefaults.faqs,
  };
}
