import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import {
  ArrowRight, Check, Calendar, Users, Handshake, BarChart3, LayoutGrid,
  Headphones, ShieldCheck, Plane, Sparkles, ChevronDown, Phone, Mail, MapPin,
  Hotel, Building2, Coffee, Truck, Compass, Send, LogIn, Boxes, Layers,
  Zap, Globe, Lock, RefreshCw, Star, Quote, ArrowUpRight,
} from 'lucide-react';

const HERO_IMG = '/landing/hero-hotel.png';

const navLinks = [
  { label: 'Ana Sayfa',        href: '#top' },
  { label: 'Çözümler',         href: '#cozumler' },
  { label: 'Modüller',         href: '#moduller' },
  { label: 'Misafir Deneyimi', href: '#deneyim' },
  { label: 'Tedarikçi Ağı',    href: '#tedarikci' },
  { label: 'Hakkımızda',       href: '#hakkimizda' },
  { label: 'İletişim',         href: '#iletisim' },
];

const heroBadges = [
  { icon: Check,       label: 'Kolay Kullanım' },
  { icon: Headphones,  label: '7/24 Destek' },
  { icon: ShieldCheck, label: 'Güvenli Altyapı' },
  { icon: Plane,       label: 'Sürekli Gelişim' },
];

const kpis = [
  { icon: Calendar,    value: '1.250+',   label: 'Aktif Otel' },
  { icon: Handshake,   value: '3.500+',   label: 'Tedarikçi' },
  { icon: BarChart3,   value: '%25',      label: 'Ortalama Gelir Artışı' },
  { icon: Users,       value: '250.000+', label: 'Mutlu Misafir' },
  { icon: Headphones,  value: '7/24',     label: 'Canlı Destek' },
];

const modules = [
  { n: '01', icon: Calendar,   title: 'Rezervasyonları Kolayca Yönetin',     desc: 'Tüm satış kanallarınızı tek yerden yönetin, doluluğu anlık takip edin.' },
  { n: '02', icon: Users,      title: 'Misafir Memnuniyetini Artırın',       desc: 'Kişiselleştirilmiş hizmetlerle misafir sadakatini ve tekrar konaklamaları artırın.' },
  { n: '03', icon: Handshake,  title: 'Tedarik Süreçlerini Tek Yerden Yönetin', desc: 'Teklif, sipariş ve ödemeyi tek panelde toplayın, tedarik süreçlerinizi kolayca yönetin.' },
  { n: '04', icon: BarChart3,  title: 'Gelirinizi ve Performansınızı Görün', desc: 'Anlık raporlar ve analizlerle daha doğru kararlar alın, gelirinizi artırın.' },
  { n: '05', icon: Headphones, title: 'Canlı Destek ve Hızlı İşlemler',      desc: '7/24 destek ekibimizle her zaman yanınızdayız.' },
];

const solutions = [
  { icon: Hotel,       title: 'Otel Yönetimi',          desc: 'Rezervasyon, oda, ön büro, check-in ve check-out — tek ekrandan kontrol.' },
  { icon: Sparkles,    title: 'Misafir Deneyimi',       desc: 'Talepler, mesajlaşma, QR çözümleri ve memnuniyet ölçümü bir arada.' },
  { icon: Boxes,       title: 'Tedarik ve Satın Alma',  desc: 'Otelleri ve tedarikçileri aynı ekosistemde buluşturan akıllı yapı.' },
  { icon: BarChart3,   title: 'Raporlama ve Kontrol',   desc: 'İşletmenizi anlık görün, daha hızlı ve daha sağlam kararlar verin.' },
  { icon: Zap,         title: 'Satış ve Operasyon',     desc: 'İş akışını sadeleştirin, ekibinizin zamanını asıl işine ayırın.' },
  { icon: Layers,      title: 'Çoklu İşletme Yönetimi', desc: 'Birden fazla tesisi tek panelden, sade ve düzenli şekilde yönetin.' },
];

const steps = [
  { n: '01', title: 'Kayıt olun veya giriş yapın', desc: 'Birkaç dakika içinde hesabınızı açın, hemen başlayın.' },
  { n: '02', title: 'İşletmenizi sisteme ekleyin', desc: 'Odalarınızı, ekibinizi ve tedarikçilerinizi kolayca tanımlayın.' },
  { n: '03', title: 'Operasyonu yönetmeye başlayın', desc: 'Rezervasyon, misafir, oda ve tedarik akışlarınızı tek panelde takip edin.' },
  { n: '04', title: 'Daha hızlı çalışın, daha iyi hizmet verin', desc: 'Anlık raporlarla kararlarınızı güçlendirin, büyümenizi hızlandırın.' },
];

const reasons = [
  { icon: LayoutGrid, title: 'Kolay arayüz',        desc: 'İlk gün herkes kullanabilir.' },
  { icon: Globe,      title: 'Tek merkez kontrol',  desc: 'Tüm modüller tek panelde.' },
  { icon: Zap,        title: 'Zaman tasarrufu',     desc: 'Manuel işleri otomatiğe alın.' },
  { icon: RefreshCw,  title: 'Düzenli operasyon',   desc: 'Standart akış, sıfır karmaşa.' },
  { icon: Sparkles,   title: 'Mutlu misafir',       desc: 'Daha hızlı, daha kişisel.' },
  { icon: BarChart3,  title: 'Güçlü takip',         desc: 'Her veri elinizin altında.' },
  { icon: Compass,    title: 'Büyümeye hazır',      desc: 'Tek tesisten zincire ölçek.' },
  { icon: Handshake,  title: 'Bütünleşik ekosistem',desc: 'Otel ve tedarikçi tek çatıda.' },
];

const sectors = [
  { icon: Hotel,    title: 'Oteller' },
  { icon: Building2,title: 'Apart / Residence' },
  { icon: Sparkles, title: 'Butik Oteller' },
  { icon: Coffee,   title: 'Restoran ve Kafe' },
  { icon: Plane,    title: 'Tatil Tesisleri' },
  { icon: Truck,    title: 'Tedarikçiler' },
  { icon: Compass,  title: 'Turizm Firmaları' },
  { icon: Layers,   title: 'Zincir İşletmeler' },
];

const supplierBenefits = [
  'Yeni işletmelere kolayca ulaşın',
  'Tek panelden sipariş takibi yapın',
  'Teklif sürecini hızla yönetin',
  'Hızlı iletişim ve net süreçler',
  'Daha görünür, daha tercih edilir olun',
];

const testimonials = [
  { name: 'Operasyon Müdürü', role: 'Sahil Otel, Antalya',    text: 'Sabah panele bakıyorum, otelin tamamını tek ekranda görüyorum. Toplantılar daha kısa, kararlar daha net.' },
  { name: 'Genel Müdür',      role: 'Butik Otel, Bodrum',     text: 'Misafir talepleri artık hiçbir yerde kaybolmuyor. Memnuniyet skorumuz ilk ay belirgin şekilde yükseldi.' },
  { name: 'Satın Alma Şefi',  role: 'Tatil Tesisi, Muğla',    text: 'Tedarikçilerle yazışma, teklif ve sipariş süreci tek yerde. Hata payımız neredeyse sıfırlandı.' },
];

const faqs = [
  { q: 'Bu sistem kimler için uygun?',          a: 'Oteller, apart tesisler, butik oteller, restoranlar, turizm firmaları ve tedarikçiler — operasyonunu dijitalleştirmek isteyen her ölçekte işletme için uygundur.' },
  { q: 'Kurulum süreci zor mu?',                a: 'Hayır. Hesabınızı açtıktan sonra rehberli adımlarla işletmenizi tanıtırsınız ve aynı gün kullanmaya başlayabilirsiniz. Ekibimiz kurulumda yanınızdadır.' },
  { q: 'Birden fazla işletme yönetebilir miyim?', a: 'Evet. Birden fazla tesisi veya markayı tek panelden yönetebilir, her biri için ayrı yetki ve raporlama tanımlayabilirsiniz.' },
  { q: 'Tedarikçi olarak nasıl katılabilirim?', a: 'Üst menüden Tedarikçi Girişi alanına geçebilir, kayıt formunu doldurarak başvurunuzu birkaç dakikada tamamlayabilirsiniz.' },
  { q: 'Mobil cihazda kullanılabiliyor mu?',    a: 'Evet. Tüm panel mobil ve tablet cihazlarda sorunsuz çalışır. Ekibiniz sahada da aynı verilere erişir.' },
  { q: 'Teknik bilgi gerekir mi?',              a: 'Hayır. Arayüz sade Türkçe ile tasarlandı; günlük operasyonu yapan herkes ilk günden rahatça kullanabilir.' },
  { q: 'Demo talep edebilir miyim?',            a: 'Elbette. İletişim formundan ulaştığınızda ekibimiz sizinle iletişime geçer ve işletmenize özel bir tanıtım planlar.' },
  { q: 'Destek süreci nasıl işliyor?',          a: '7/24 erişebileceğiniz canlı destek hattı, e-posta ve telefon kanallarımız mevcuttur. Kritik durumlarda hızlı geri dönüş garantilidir.' },
];

const dashboardTabs = [
  { key: 'rez', label: 'Rezervasyon', desc: 'Tüm odaları ve kanalları tek takvimde görün.' },
  { key: 'occ', label: 'Doluluk',     desc: 'Anlık doluluk, geliş-gidiş ve müsaitlik haritası.' },
  { key: 'req', label: 'Talepler',    desc: 'Misafir talepleri ve operasyonel görevler.' },
  { key: 'rev', label: 'Gelir',       desc: 'Gelir, ortalama oda fiyatı ve performans raporu.' },
  { key: 'sup', label: 'Tedarik',     desc: 'Sipariş, teklif ve tedarikçi ekranı.' },
];

/* ---------- Reusable atoms ---------- */
const GlassCard = ({ className = '', children, ...rest }) => (
  <div
    className={
      'rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-xl ' +
      'shadow-[0_10px_40px_-15px_rgba(8,18,46,0.6)] ' + className
    }
    {...rest}
  >
    {children}
  </div>
);

const NeonBlob = ({ className = '' }) => (
  <div
    aria-hidden
    className={
      'pointer-events-none absolute rounded-full blur-3xl opacity-60 ' + className
    }
  />
);

const SectionTitle = ({ eyebrow, title, sub, center = true }) => (
  <div className={center ? 'mx-auto max-w-3xl text-center' : 'max-w-3xl'}>
    {eyebrow && (
      <div className={(center ? 'mx-auto ' : '') + 'mb-4 inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-medium tracking-wide text-cyan-300'}>
        <span className="h-1.5 w-1.5 rounded-full bg-cyan-300 shadow-[0_0_10px_2px_rgba(34,211,238,0.7)]" />
        {eyebrow}
      </div>
    )}
    <h2 className="text-3xl font-semibold leading-tight text-white sm:text-4xl md:text-5xl">
      {title}
    </h2>
    {sub && <p className="mt-4 text-base leading-relaxed text-slate-300/90 sm:text-lg">{sub}</p>}
  </div>
);

/* ---------- Page ---------- */
const LandingPage = () => {
  const navigate = useNavigate();
  const reduce = useReducedMotion();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState(0);
  const [activeTab, setActiveTab] = useState('rez');
  const heroRef = useRef(null);

  const { scrollY } = useScroll();
  const heroParallax = useTransform(scrollY, [0, 600], [0, reduce ? 0 : -60]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const goLogin = () => navigate('/auth');
  const goSupplier = () => navigate('/tedarikci/giris');

  return (
    <div id="top" className="relative min-h-screen overflow-x-hidden bg-[#05070f] text-slate-100 antialiased">
      {/* Global ambient background */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(34,211,238,0.10),_transparent_60%),radial-gradient(ellipse_at_bottom,_rgba(99,102,241,0.10),_transparent_60%)]" />
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)',
            backgroundSize: '64px 64px',
            maskImage: 'radial-gradient(ellipse at center, black 40%, transparent 75%)',
            WebkitMaskImage: 'radial-gradient(ellipse at center, black 40%, transparent 75%)',
          }}
        />
      </div>

      {/* ---------- NAV ---------- */}
      <header
        className={
          'fixed inset-x-0 top-0 z-50 transition-all duration-300 ' +
          (scrolled
            ? 'border-b border-white/10 bg-[#05070f]/80 backdrop-blur-xl'
            : 'bg-transparent')
        }
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-10">
          <a href="#top" className="flex items-center gap-2.5">
            <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-[#05070f] shadow-[0_0_24px_rgba(34,211,238,0.45)]">
              <span className="text-sm font-bold tracking-tight">S</span>
            </span>
            <span className="text-lg font-semibold tracking-tight text-white">Syroce</span>
          </a>

          <nav className="hidden items-center gap-7 lg:flex">
            {navLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="text-sm text-slate-300 transition hover:text-white"
              >
                {l.label}
              </a>
            ))}
          </nav>

          <div className="hidden items-center gap-3 md:flex">
            <button
              onClick={goLogin}
              className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white transition hover:bg-white/[0.08]"
            >
              <LogIn className="h-4 w-4" />
              Giriş Yap
            </button>
            <button
              onClick={goSupplier}
              className="group inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-4 py-2 text-sm font-semibold text-[#05070f] shadow-[0_8px_30px_-8px_rgba(34,211,238,0.7)] transition hover:shadow-[0_10px_40px_-6px_rgba(34,211,238,0.9)]"
            >
              <Users className="h-4 w-4" />
              Tedarikçi Girişi
            </button>
          </div>

          <button
            className="lg:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Menü"
          >
            <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2">
              <LayoutGrid className="h-5 w-5 text-white" />
            </div>
          </button>
        </div>

        {mobileOpen && (
          <div className="border-t border-white/10 bg-[#05070f]/95 backdrop-blur-xl lg:hidden">
            <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-4 sm:px-6">
              {navLinks.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  className="rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-white/[0.06]"
                  onClick={() => setMobileOpen(false)}
                >
                  {l.label}
                </a>
              ))}
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <button onClick={goLogin} className="flex-1 rounded-full border border-white/15 px-4 py-2 text-sm text-white">Giriş Yap</button>
                <button onClick={goSupplier} className="flex-1 rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-[#05070f]">Tedarikçi Girişi</button>
              </div>
            </div>
          </div>
        )}
      </header>

      {/* ---------- HERO ---------- */}
      <section
        ref={heroRef}
        className="relative flex flex-col justify-center pt-28 sm:pt-32 lg:min-h-[90vh] lg:pt-36"
      >
        <NeonBlob className="left-[-10%] top-[5%] h-[420px] w-[420px] bg-cyan-500/30" />
        <NeonBlob className="right-[-8%] top-[20%] h-[520px] w-[520px] bg-indigo-500/35" />
        <NeonBlob className="right-[15%] bottom-[5%] h-[380px] w-[380px] bg-teal-400/25" />

        <div className="mx-auto grid w-full max-w-7xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:gap-10 lg:px-10">
          {/* Left copy */}
          <motion.div
            initial={{ opacity: 0, y: reduce ? 0 : 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className=""
          >
            <span className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-medium tracking-wider text-cyan-300">
              <Sparkles className="h-3.5 w-3.5" />
              TÜM OTEL YÖNETİMİ TEK BİR PLATFORMDA
            </span>

            <h1 className="mt-6 text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl lg:text-[2.75rem] xl:text-[3rem]">
              Otelinizi Daha Kolay{' '}
              <span className="bg-gradient-to-r from-cyan-300 via-sky-300 to-indigo-300 bg-clip-text text-transparent">
                Yönetin, İşinizi Büyütün
              </span>
            </h1>

            <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-300/90 sm:text-lg">
              Rezervasyonlardan misafir deneyimine, tedarik süreçlerinden gelire kadar
              her şeyi tek ekrandan yönetin. Zamandan tasarruf edin, memnuniyeti ve
              kârlılığı artırın.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <button
                onClick={goLogin}
                className="group inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-6 py-3 text-sm font-semibold text-[#05070f] shadow-[0_12px_40px_-10px_rgba(34,211,238,0.7)] transition hover:translate-y-[-1px] hover:shadow-[0_16px_50px_-8px_rgba(34,211,238,0.9)]"
              >
                Giriş Yap
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </button>
              <button
                onClick={goSupplier}
                className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-6 py-3 text-sm font-semibold text-white transition hover:bg-white/[0.08]"
              >
                <Users className="h-4 w-4" />
                Tedarikçi Girişi
              </button>
              <a
                href="#iletisim"
                className="inline-flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-6 py-3 text-sm font-semibold text-cyan-200 transition hover:bg-cyan-400/15"
              >
                <Sparkles className="h-4 w-4" />
                Demo Talep Et
              </a>
            </div>

            <div className="mt-7 grid grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:gap-5">
              {heroBadges.map((b) => (
                <div key={b.label} className="inline-flex items-center gap-2 text-sm text-slate-300">
                  <span className="grid h-6 w-6 place-items-center rounded-full bg-cyan-400/15 text-cyan-300">
                    <b.icon className="h-3.5 w-3.5" />
                  </span>
                  {b.label}
                </div>
              ))}
            </div>
          </motion.div>

          {/* Right hero visual */}
          <motion.div
            style={{ y: heroParallax }}
            initial={{ opacity: 0, scale: reduce ? 1 : 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.9, ease: 'easeOut' }}
            className="relative"
          >
            <div className="relative mx-auto w-full max-w-[720px]" style={{ minHeight: 600 }}>
              {/* Ambient glow */}
              <div className="absolute -inset-10 rounded-[3rem] bg-gradient-to-br from-cyan-500/30 via-transparent to-indigo-500/35 blur-3xl" aria-hidden />

              {/* Merkez sahne: gerçek 3D render otel görseli + alt bilgi balonu */}
              <div className="absolute inset-0 overflow-hidden rounded-[2rem] border border-white/10 bg-gradient-to-b from-[#0a1828] via-[#0b1a2e] to-[#06101e] shadow-[inset_0_0_120px_rgba(34,211,238,0.22),0_40px_120px_-30px_rgba(34,211,238,0.4)]">
                {/* Gökyüzü tonu (görsel arkası yumuşaklığı için) */}
                <div className="absolute inset-x-0 top-0 h-2/3 bg-[radial-gradient(ellipse_at_center_top,_rgba(34,211,238,0.22),_transparent_60%)]" />
                {/* Rendered hotel image — dominant focal element */}
                <img
                  src={HERO_IMG}
                  alt="Syroce Hotel 3D görünüm"
                  className="absolute inset-0 h-full w-full object-cover object-center"
                  loading="eager"
                  decoding="async"
                />
                {/* Soft bottom vignette so the info bubble reads */}
                <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-[#040810]/80 via-[#040810]/30 to-transparent" />
                {/* Alt-orta bilgi balonu */}
                <div className="absolute bottom-5 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-full border border-cyan-400/40 bg-[#0a1424]/95 px-4 py-2 text-xs text-cyan-100 shadow-[0_12px_40px_-6px_rgba(34,211,238,0.6)] backdrop-blur-xl">
                  <Sparkles className="mr-1.5 inline h-3.5 w-3.5 text-cyan-300" />
                  Oteliniz için akıllı, güvenli ve etkili bir yönetim platformu.
                </div>
              </div>

              {/* ===== Sol sütun: 3 floating card (görselin sol kenarına bindirilmiş) ===== */}
              {[
                { top: '4%',  icon: Calendar,  title: 'Rezervasyonlar',   desc: 'Tüm kanalları tek yerden yönetin',                  pct: '18%' },
                { top: '40%', icon: Users,     title: 'Misafir Deneyimi', desc: 'Daha mutlu misafirler, daha güçlü sadakat',          pct: '24%' },
                { top: '76%', icon: Handshake, title: 'Tedarikçi Ağı',    desc: 'Güvenilir tedarikçilerle kolay ve hızlı iş birliği', pct: '22%' },
              ].map((c, i) => (
                <motion.div
                  key={'L'+i}
                  animate={reduce ? {} : { y: [0, i % 2 ? 8 : -8, 0] }}
                  transition={{ duration: 5 + i, repeat: Infinity, ease: 'easeInOut' }}
                  style={{ top: c.top }}
                  className="absolute left-0 z-10 hidden w-[200px] md:block lg:-left-10 xl:-left-20"
                >
                  <GlassCard className="flex items-start gap-2.5 p-2.5">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-cyan-400/15 text-cyan-300 ring-1 ring-cyan-400/25">
                      <c.icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1.5">
                        <div className="truncate text-[13px] font-semibold text-white">{c.title}</div>
                        <span className="shrink-0 rounded-md bg-emerald-400/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">↑ {c.pct}</span>
                      </div>
                      <p className="mt-0.5 text-[11px] leading-snug text-slate-400">{c.desc}</p>
                    </div>
                  </GlassCard>
                </motion.div>
              ))}

              {/* ===== Sağ sütun: 3 floating card (görselin sağ kenarına bindirilmiş) ===== */}
              {[
                { top: '4%',  icon: BarChart3,  title: 'Gelir ve Raporlama', desc: 'Gelirinizi ve performansınızı görün', pct: '23%' },
                { top: '40%', icon: Boxes,      title: 'Tek Platform',       desc: 'Tüm modüller tek ekranda',            pct: '15%' },
                { top: '76%', icon: Headphones, title: 'Canlı Destek',       desc: '7/24 yanınızdayız',                   online: true },
              ].map((c, i) => (
                <motion.div
                  key={'R'+i}
                  animate={reduce ? {} : { y: [0, i % 2 ? -8 : 8, 0] }}
                  transition={{ duration: 5 + i, repeat: Infinity, ease: 'easeInOut' }}
                  style={{ top: c.top }}
                  className="absolute right-0 z-10 hidden w-[200px] md:block lg:-right-10 xl:-right-20"
                >
                  <GlassCard className="flex items-start gap-2.5 p-2.5">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-cyan-400/15 text-cyan-300 ring-1 ring-cyan-400/25">
                      <c.icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1.5">
                        <div className="truncate text-[13px] font-semibold text-white">{c.title}</div>
                        {c.pct && <span className="shrink-0 rounded-md bg-emerald-400/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">↑ {c.pct}</span>}
                      </div>
                      <p className="mt-0.5 text-[11px] leading-snug text-slate-400">{c.desc}</p>
                      {c.online && (
                        <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-emerald-300">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                          Çevrimiçi
                        </div>
                      )}
                    </div>
                  </GlassCard>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* KPI strip */}
        <div className="mx-auto mt-14 max-w-7xl px-4 sm:px-6 lg:mt-20 lg:px-10">
          <GlassCard className="grid grid-cols-2 gap-4 p-5 sm:grid-cols-3 sm:p-6 lg:grid-cols-5">
            {kpis.map((k) => (
              <div key={k.label} className="flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/[0.05] text-cyan-300 ring-1 ring-white/10">
                  <k.icon className="h-5 w-5" />
                </span>
                <div>
                  <div className="text-xl font-semibold text-white sm:text-2xl">{k.value}</div>
                  <div className="text-xs text-slate-400 sm:text-sm">{k.label}</div>
                </div>
              </div>
            ))}
          </GlassCard>
        </div>
      </section>

      {/* ---------- MODÜLLER + SİZ HANGİSİSİNİZ ---------- */}
      <section id="moduller" className="relative py-24 sm:py-28">
        <NeonBlob className="left-[10%] top-[20%] h-[300px] w-[300px] bg-cyan-500/20" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <div className="grid gap-10 lg:grid-cols-12">
            {/* Modules grid */}
            <div className="lg:col-span-8">
              <div className="mb-8 flex items-end justify-between gap-4">
                <h2 className="text-2xl font-semibold text-white sm:text-3xl">
                  Tüm İhtiyaçlarınız İçin Akıllı Modüller
                </h2>
                <a href="#cozumler" className="hidden items-center gap-1 text-sm text-cyan-300 hover:text-cyan-200 sm:inline-flex">
                  Tüm Modülleri Gör <ArrowRight className="h-4 w-4" />
                </a>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {modules.map((m, i) => (
                  <motion.div
                    key={m.n}
                    initial={{ opacity: 0, y: reduce ? 0 : 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.3 }}
                    transition={{ duration: 0.45, delay: i * 0.05 }}
                  >
                    <GlassCard className="group relative h-full p-5 transition hover:bg-white/[0.06] hover:border-cyan-400/30">
                      <div className="mb-4 flex items-center justify-between">
                        <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/20">
                          <m.icon className="h-5 w-5" />
                        </span>
                        <span className="text-2xl font-semibold text-white/30 transition group-hover:text-cyan-300/70">{m.n}</span>
                      </div>
                      <h3 className="text-base font-semibold leading-tight text-white">{m.title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-slate-400">{m.desc}</p>
                      <a href="#cozumler" className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-cyan-300 hover:text-cyan-200">
                        Detaylar <ArrowRight className="h-3.5 w-3.5" />
                      </a>
                    </GlassCard>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* "Siz hangisisiniz?" */}
            <div className="lg:col-span-4">
              <h2 className="text-2xl font-semibold text-white sm:text-3xl">Siz Hangisisiniz?</h2>
              <p className="mt-2 text-sm text-slate-400">Size özel deneyime hemen başlayın.</p>

              <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1">
                <button
                  onClick={goLogin}
                  className="group relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-cyan-500/15 via-sky-500/10 to-indigo-500/15 p-5 text-left transition hover:border-cyan-400/40"
                >
                  <div className="flex items-start gap-4">
                    <span className="grid h-12 w-12 place-items-center rounded-xl bg-cyan-400/15 text-cyan-300 ring-1 ring-cyan-400/30">
                      <Hotel className="h-6 w-6" />
                    </span>
                    <div className="flex-1">
                      <div className="text-base font-semibold text-white">Otel Girişi</div>
                      <p className="mt-1 text-sm text-slate-400">Otel yönetim platformumuza erişin ve işinizi kolaylaştırın.</p>
                      <span className="mt-3 inline-flex h-8 w-8 items-center justify-center rounded-full bg-cyan-400 text-[#05070f] transition group-hover:translate-x-1">
                        <ArrowRight className="h-4 w-4" />
                      </span>
                    </div>
                  </div>
                </button>

                <button
                  onClick={goSupplier}
                  className="group relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-indigo-500/15 via-indigo-400/10 to-cyan-500/15 p-5 text-left transition hover:border-indigo-400/40"
                >
                  <div className="flex items-start gap-4">
                    <span className="grid h-12 w-12 place-items-center rounded-xl bg-indigo-400/15 text-indigo-300 ring-1 ring-indigo-400/30">
                      <Truck className="h-6 w-6" />
                    </span>
                    <div className="flex-1">
                      <div className="text-base font-semibold text-white">Tedarikçi Girişi</div>
                      <p className="mt-1 text-sm text-slate-400">Tedarikçi ağımıza katılın, iş fırsatlarını kaçırmayın.</p>
                      <span className="mt-3 inline-flex h-8 w-8 items-center justify-center rounded-full bg-indigo-400 text-[#05070f] transition group-hover:translate-x-1">
                        <ArrowRight className="h-4 w-4" />
                      </span>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- ÇÖZÜMLER ---------- */}
      <section id="cozumler" className="relative py-24 sm:py-28">
        <NeonBlob className="right-[5%] top-[10%] h-[360px] w-[360px] bg-indigo-500/20" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <SectionTitle
            eyebrow="ÇÖZÜMLER"
            title="Operasyonun her adımı için akıllı çözümler"
            sub="İşletmenize değer katan, kullanımı kolay ve büyümenize hazır modüllerle tanışın."
          />

          <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {solutions.map((s, i) => (
              <motion.div
                key={s.title}
                initial={{ opacity: 0, y: reduce ? 0 : 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.45, delay: i * 0.05 }}
              >
                <GlassCard className="group h-full p-6 transition hover:-translate-y-1 hover:border-cyan-400/30 hover:bg-white/[0.06]">
                  <span className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-to-br from-cyan-400/20 to-indigo-500/20 text-cyan-300 ring-1 ring-white/10">
                    <s.icon className="h-6 w-6" />
                  </span>
                  <h3 className="mt-5 text-lg font-semibold text-white">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.desc}</p>
                  <a href="#iletisim" className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-cyan-300 hover:text-cyan-200">
                    Detayları Gör <ArrowUpRight className="h-4 w-4" />
                  </a>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- NASIL ÇALIŞIR ---------- */}
      <section id="nasil" className="relative py-24 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <SectionTitle
            eyebrow="NASIL ÇALIŞIR"
            title="Birkaç adımda Syroce ile başlayın"
            sub="Kurulum dakikalar sürer; ekibiniz aynı gün kullanmaya başlar."
          />
          <div className="relative mt-14">
            <div aria-hidden className="absolute left-0 right-0 top-9 hidden h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent lg:block" />
            <div className="grid gap-5 lg:grid-cols-4">
              {steps.map((s, i) => (
                <motion.div
                  key={s.n}
                  initial={{ opacity: 0, y: reduce ? 0 : 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.3 }}
                  transition={{ duration: 0.45, delay: i * 0.07 }}
                  className="relative"
                >
                  <div className="mb-5 grid h-[72px] w-[72px] place-items-center">
                    <div className="absolute inset-x-0 top-0 grid h-[72px] w-[72px] place-items-center rounded-2xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-lg font-bold text-[#05070f] shadow-[0_10px_30px_-10px_rgba(34,211,238,0.7)]">
                      {s.n}
                    </div>
                  </div>
                  <GlassCard className="p-5 pt-12 -mt-12">
                    <h3 className="text-base font-semibold text-white">{s.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.desc}</p>
                  </GlassCard>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- NEDEN SYROCE ---------- */}
      <section id="neden" className="relative py-24 sm:py-28">
        <NeonBlob className="left-[20%] top-[10%] h-[340px] w-[340px] bg-cyan-500/20" />
        <NeonBlob className="right-[5%] bottom-[10%] h-[340px] w-[340px] bg-indigo-500/20" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <SectionTitle
            eyebrow="NEDEN SYROCE"
            title="Çünkü karmaşık işleri basitleştiriyoruz"
            sub="Premium görünüm değil, premium hissiyat. Operasyonun her parçası ekibinizi güçlendirsin."
          />

          <div className="mt-14 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {reasons.map((r, i) => (
              <motion.div
                key={r.title}
                initial={{ opacity: 0, y: reduce ? 0 : 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.4, delay: i * 0.04 }}
              >
                <GlassCard className="h-full p-5 transition hover:border-cyan-400/30 hover:bg-white/[0.06]">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/20">
                    <r.icon className="h-5 w-5" />
                  </span>
                  <h3 className="mt-4 text-sm font-semibold text-white">{r.title}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{r.desc}</p>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- KİMLER İÇİN ---------- */}
      <section id="kimler" className="relative py-24 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <SectionTitle
            eyebrow="KİMLER İÇİN"
            title="Konaklama, hizmet ve tedarikte her ölçek için"
            sub="Bir butik otelden zincire, küçük bir restorandan büyük tedarikçiye kadar Syroce ile büyüyün."
          />
          <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {sectors.map((s) => (
              <GlassCard
                key={s.title}
                className="flex flex-col items-center gap-3 p-6 text-center transition hover:border-cyan-400/30 hover:bg-white/[0.06]"
              >
                <span className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-to-br from-cyan-400/20 to-indigo-500/20 text-cyan-300 ring-1 ring-white/10">
                  <s.icon className="h-6 w-6" />
                </span>
                <div className="text-sm font-medium text-white">{s.title}</div>
              </GlassCard>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- DASHBOARD ÖNİZLEME ---------- */}
      <section id="deneyim" className="relative py-24 sm:py-28">
        <NeonBlob className="left-[5%] top-[20%] h-[360px] w-[360px] bg-indigo-500/25" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <SectionTitle
            eyebrow="MİSAFİR DENEYİMİ & PANEL"
            title="Tüm operasyon, tek bir akıllı ekranda"
            sub="Aşağıdaki sekmelerle panelin farklı bölümlerine göz atın."
          />

          <div className="mt-12 flex flex-wrap items-center justify-center gap-2">
            {dashboardTabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={
                  'rounded-full px-4 py-2 text-sm transition ' +
                  (activeTab === t.key
                    ? 'bg-gradient-to-r from-cyan-400 to-teal-300 text-[#05070f] shadow-[0_8px_30px_-10px_rgba(34,211,238,0.7)]'
                    : 'border border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.08]')
                }
              >
                {t.label}
              </button>
            ))}
          </div>

          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: reduce ? 0 : 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mt-8"
          >
            <GlassCard className="overflow-hidden p-2 sm:p-3">
              <div className="relative">
                <img
                  src={HERO_IMG}
                  alt="Panel önizleme"
                  className="block h-auto w-full rounded-[1.4rem]"
                  loading="lazy"
                />
                <div className="pointer-events-none absolute inset-0 rounded-[1.4rem] ring-1 ring-inset ring-white/10" />
              </div>
              <div className="mt-3 flex items-center justify-between gap-3 px-3 pb-3">
                <p className="text-sm text-slate-300">
                  {dashboardTabs.find((t) => t.key === activeTab)?.desc}
                </p>
                <button onClick={goLogin} className="hidden items-center gap-1 text-sm font-medium text-cyan-300 hover:text-cyan-200 sm:inline-flex">
                  Paneli Aç <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </GlassCard>
          </motion.div>
        </div>
      </section>

      {/* ---------- TEDARİKÇİ ---------- */}
      <section id="tedarikci" className="relative py-24 sm:py-28">
        <NeonBlob className="right-[10%] top-[10%] h-[360px] w-[360px] bg-indigo-500/15" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <div className="grid items-center gap-12 lg:grid-cols-12">
            <div className="lg:col-span-6">
              <SectionTitle
                eyebrow="TEDARİKÇİ AĞI"
                title="Tedarikçiler için yeni nesil iş bağlantısı"
                sub="İşletmelere ürün ve hizmet sunan tedarikçiler, kendi panellerinden siparişleri, teklifleri ve talepleri tek yerden yönetir."
                center={false}
              />

              <ul className="mt-8 space-y-3">
                {supplierBenefits.map((b) => (
                  <li key={b} className="flex items-start gap-3 text-slate-200">
                    <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-cyan-400/15 text-cyan-300">
                      <Check className="h-3.5 w-3.5" />
                    </span>
                    {b}
                  </li>
                ))}
              </ul>

              <div className="mt-8 flex flex-wrap gap-3">
                <button
                  onClick={goSupplier}
                  className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-indigo-400 to-cyan-400 px-5 py-3 text-sm font-semibold text-[#05070f] shadow-[0_10px_30px_-10px_rgba(99,102,241,0.7)] transition hover:translate-y-[-1px]"
                >
                  Tedarikçi Girişi
                  <ArrowRight className="h-4 w-4" />
                </button>
                <a
                  href="#iletisim"
                  className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/[0.08]"
                >
                  Tedarikçi Olarak Başvur
                </a>
              </div>
            </div>

            <div className="lg:col-span-6">
              <div className="relative">
                <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-br from-indigo-500/30 via-fuchsia-500/15 to-cyan-500/20 blur-2xl" aria-hidden />
                <GlassCard className="relative grid grid-cols-2 gap-3 p-5">
                  {[
                    { icon: Send,       label: 'Yeni Siparişler', value: '128' },
                    { icon: Handshake,  label: 'Açık Teklifler',  value: '42' },
                    { icon: Hotel,      label: 'Bağlı Otel',      value: '76' },
                    { icon: BarChart3,  label: 'Aylık Hacim',     value: '₺ 1.2M' },
                  ].map((c) => (
                    <div key={c.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                      <span className="grid h-9 w-9 place-items-center rounded-lg bg-indigo-400/15 text-indigo-300 ring-1 ring-indigo-400/20">
                        <c.icon className="h-4 w-4" />
                      </span>
                      <div className="mt-3 text-xs text-slate-400">{c.label}</div>
                      <div className="text-xl font-semibold text-white">{c.value}</div>
                    </div>
                  ))}
                  <div className="col-span-2 rounded-xl border border-white/10 bg-gradient-to-br from-cyan-500/10 to-indigo-500/10 p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-xs text-slate-400">Bu hafta</div>
                        <div className="text-base font-semibold text-white">Sipariş hacmi %18 arttı</div>
                      </div>
                      <span className="grid h-10 w-10 place-items-center rounded-lg bg-emerald-400/15 text-emerald-300">
                        <BarChart3 className="h-5 w-5" />
                      </span>
                    </div>
                  </div>
                </GlassCard>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- SOSYAL KANIT ---------- */}
      <section id="hakkimizda" className="relative py-24 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <SectionTitle
            eyebrow="GÜVEN VE DENEYİM"
            title="İşletmeler için tasarlandı, ekipler tarafından sevildi"
            sub="Kullanıcılarımızın deneyimi, yolumuzu çizen en güçlü rehber."
          />
          <div className="mt-12 grid gap-5 lg:grid-cols-3">
            {testimonials.map((t, i) => (
              <motion.div
                key={t.name}
                initial={{ opacity: 0, y: reduce ? 0 : 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.5, delay: i * 0.06 }}
              >
                <GlassCard className="h-full p-6">
                  <Quote className="h-7 w-7 text-cyan-300/80" />
                  <p className="mt-4 text-sm leading-relaxed text-slate-200">{t.text}</p>
                  <div className="mt-6 flex items-center gap-3">
                    <span className="grid h-10 w-10 place-items-center rounded-full bg-gradient-to-br from-cyan-400 to-indigo-500 text-sm font-bold text-[#05070f]">
                      {t.name.split(' ').map((p) => p[0]).join('').slice(0, 2)}
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-white">{t.name}</div>
                      <div className="text-xs text-slate-400">{t.role}</div>
                    </div>
                    <div className="ml-auto flex items-center gap-0.5 text-amber-300">
                      {Array.from({ length: 5 }).map((_, k) => (
                        <Star key={k} className="h-3.5 w-3.5 fill-current" />
                      ))}
                    </div>
                  </div>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- SSS ---------- */}
      <section id="sss" className="relative py-24 sm:py-28">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-10">
          <SectionTitle
            eyebrow="SIK SORULAN SORULAR"
            title="Aklınızdaki ilk sorulara hızlı cevaplar"
          />
          <div className="mt-10 space-y-3">
            {faqs.map((f, i) => {
              const open = openFaq === i;
              return (
                <GlassCard key={f.q} className="overflow-hidden">
                  <button
                    onClick={() => setOpenFaq(open ? -1 : i)}
                    className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
                  >
                    <span className="text-sm font-medium text-white sm:text-base">{f.q}</span>
                    <span
                      className={
                        'grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white/[0.04] text-cyan-300 ring-1 ring-white/10 transition ' +
                        (open ? 'rotate-180' : '')
                      }
                    >
                      <ChevronDown className="h-4 w-4" />
                    </span>
                  </button>
                  <motion.div
                    initial={false}
                    animate={{ height: open ? 'auto' : 0, opacity: open ? 1 : 0 }}
                    transition={{ duration: 0.3 }}
                    className="overflow-hidden"
                  >
                    <div className="px-5 pb-5 text-sm leading-relaxed text-slate-300">{f.a}</div>
                  </motion.div>
                </GlassCard>
              );
            })}
          </div>
        </div>
      </section>

      {/* ---------- İLETİŞİM ---------- */}
      <section id="iletisim" className="relative py-24 sm:py-28">
        <NeonBlob className="left-[10%] top-[10%] h-[360px] w-[360px] bg-cyan-500/20" />
        <NeonBlob className="right-[10%] bottom-[10%] h-[360px] w-[360px] bg-indigo-500/20" />

        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <div className="grid gap-10 lg:grid-cols-12">
            <div className="lg:col-span-5">
              <SectionTitle
                eyebrow="İLETİŞİM"
                title="İşletmenizi daha kolay yönetmeye hazır mısınız?"
                sub="Dakikalar içinde başlayın, operasyonunuzu sadeleştirin. Ekibimiz size özel bir tanıtım planlasın."
                center={false}
              />
              <div className="mt-8 space-y-3">
                <div className="flex items-center gap-3 text-slate-300">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/20">
                    <Phone className="h-4 w-4" />
                  </span>
                  +90 (212) 000 00 00
                </div>
                <div className="flex items-center gap-3 text-slate-300">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/20">
                    <Mail className="h-4 w-4" />
                  </span>
                  iletisim@syroce.com
                </div>
                <div className="flex items-center gap-3 text-slate-300">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/20">
                    <MapPin className="h-4 w-4" />
                  </span>
                  İstanbul, Türkiye
                </div>
              </div>
              <div className="mt-8 flex flex-wrap gap-3">
                <button onClick={goLogin} className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-5 py-3 text-sm font-semibold text-[#05070f]">
                  <LogIn className="h-4 w-4" /> Müşteri Girişi
                </button>
                <button onClick={goSupplier} className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-5 py-3 text-sm font-semibold text-white">
                  <Users className="h-4 w-4" /> Tedarikçi Girişi
                </button>
              </div>
            </div>

            <div className="lg:col-span-7">
              <GlassCard className="p-6 sm:p-8">
                <form
                  className="grid grid-cols-1 gap-4 sm:grid-cols-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    alert('Mesajınız iletildi. Ekibimiz en kısa sürede dönüş yapacak.');
                    e.currentTarget.reset();
                  }}
                >
                  {[
                    { name: 'fullName',     label: 'Ad Soyad',      type: 'text',  required: true,  half: true },
                    { name: 'company',      label: 'İşletme Adı',   type: 'text',  required: true,  half: true },
                    { name: 'phone',        label: 'Telefon',       type: 'tel',   required: true,  half: true },
                    { name: 'email',        label: 'E-posta',       type: 'email', required: true,  half: true },
                    { name: 'businessType', label: 'İşletme Türü',  type: 'text',  required: false, half: false },
                  ].map((f) => (
                    <label key={f.name} className={'block ' + (f.half ? '' : 'sm:col-span-2')}>
                      <span className="mb-1.5 block text-xs font-medium text-slate-400">{f.label}{f.required && <span className="text-cyan-300"> *</span>}</span>
                      <input
                        name={f.name}
                        type={f.type}
                        required={f.required}
                        className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-cyan-400/40 focus:bg-white/[0.06] focus:ring-2 focus:ring-cyan-400/20"
                        placeholder={f.label}
                      />
                    </label>
                  ))}
                  <label className="block sm:col-span-2">
                    <span className="mb-1.5 block text-xs font-medium text-slate-400">Mesajınız</span>
                    <textarea
                      name="message"
                      rows={4}
                      className="w-full resize-none rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-cyan-400/40 focus:bg-white/[0.06] focus:ring-2 focus:ring-cyan-400/20"
                      placeholder="Bize kısaca beklentinizi yazın"
                    />
                  </label>

                  <div className="sm:col-span-2 flex items-center justify-between gap-4">
                    <p className="text-xs text-slate-500">Bilgileriniz yalnızca size dönüş yapmak için kullanılır.</p>
                    <button
                      type="submit"
                      className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-6 py-3 text-sm font-semibold text-[#05070f] shadow-[0_10px_30px_-10px_rgba(34,211,238,0.7)] transition hover:translate-y-[-1px]"
                    >
                      Mesaj Gönder
                      <Send className="h-4 w-4" />
                    </button>
                  </div>
                </form>
              </GlassCard>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- FOOTER ---------- */}
      <footer className="relative border-t border-white/10 bg-[#04060c]/80 pt-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
          <div className="grid gap-10 lg:grid-cols-12">
            <div className="lg:col-span-4">
              <a href="#top" className="flex items-center gap-2.5">
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-[#05070f]">
                  <span className="text-sm font-bold">S</span>
                </span>
                <span className="text-lg font-semibold text-white">Syroce</span>
              </a>
              <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-400">
                Otelinizi, operasyonlarınızı ve misafir deneyiminizi tek merkezden yönetin.
                Sadece bir yazılım değil — işinizi büyüten dijital bir işletim sistemi.
              </p>
              <div className="mt-6 flex items-center gap-2 text-xs text-slate-500">
                <Lock className="h-3.5 w-3.5" /> KVKK & güvenli altyapı
              </div>
            </div>

            <FooterCol title="Kurumsal" items={[
              { label: 'Hakkımızda',           href: '#hakkimizda' },
              { label: 'Kullanım Alanları',    href: '#kimler' },
              { label: 'Referanslar',          href: '#hakkimizda' },
              { label: 'Gizlilik Politikası',  href: '/privacy-policy' },
              { label: 'Kullanım Şartları',    href: '/privacy-policy' },
            ]} />
            <FooterCol title="Çözümler" items={[
              { label: 'Otel Yönetimi',        href: '#cozumler' },
              { label: 'Misafir Deneyimi',     href: '#deneyim' },
              { label: 'Tedarik ve Satın Alma',href: '#tedarikci' },
              { label: 'Raporlama',            href: '#cozumler' },
              { label: 'Çoklu İşletme',        href: '#cozumler' },
            ]} />
            <FooterCol title="Destek" items={[
              { label: 'İletişim',             href: '#iletisim' },
              { label: 'SSS',                  href: '#sss' },
              { label: 'Demo Talep',           href: '#iletisim' },
              { label: 'Müşteri Girişi',       href: '/auth' },
              { label: 'Tedarikçi Girişi',     href: '/tedarikci/giris' },
            ]} />
          </div>

          <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-white/10 py-6 text-xs text-slate-500 sm:flex-row">
            <div>© {new Date().getFullYear()} Syroce. Tüm hakları saklıdır.</div>
            <div className="flex items-center gap-4">
              <a href="/privacy-policy" className="hover:text-slate-300">Gizlilik</a>
              <a href="/privacy-policy" className="hover:text-slate-300">Şartlar</a>
              <a href="#iletisim" className="hover:text-slate-300">İletişim</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

const FooterCol = ({ title, items }) => (
  <div className="lg:col-span-2">
    <div className="text-sm font-semibold text-white">{title}</div>
    <ul className="mt-4 space-y-2.5">
      {items.map((it) => (
        <li key={it.label}>
          <a href={it.href} className="text-sm text-slate-400 transition hover:text-cyan-300">
            {it.label}
          </a>
        </li>
      ))}
    </ul>
  </div>
);

export default LandingPage;
