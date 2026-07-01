import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import {
  ArrowRight, Check, Calendar, Users, Handshake, BarChart3, LayoutGrid,
  Headphones, ShieldCheck, Plane, Sparkles, ChevronDown, Phone, Mail, MapPin,
  Hotel, Building2, Coffee, Truck, Compass, Send, LogIn, Boxes, Layers,
  Zap, Globe, Lock, RefreshCw, Star, Quote, ArrowUpRight,
} from 'lucide-react';

import axios from 'axios';
import { mergeLandingContent } from '@/config/landingContentDefaults';

const HERO_IMG = '/landing/hero-hotel.png';

// Public iletisim formu -> POST /api/leads/contact (axios baseURL '/api').
// Lead, super_admin AdminLeads gelen kutusuna dusurulur (kaynak: marketing_contact).
function LandingContactForm() {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const onSubmit = async (e) => {
    e.preventDefault();
    const formEl = e.currentTarget;
    const fd = new FormData(formEl);
    const payload = {
      full_name: String(fd.get('fullName') || '').trim(),
      company: String(fd.get('company') || '').trim(),
      phone: String(fd.get('phone') || '').trim(),
      email: String(fd.get('email') || '').trim(),
      business_type: String(fd.get('businessType') || '').trim() || undefined,
      message: String(fd.get('message') || '').trim() || undefined,
    };
    setSubmitting(true);
    setResult(null);
    try {
      await axios.post('/leads/contact', payload);
      setResult({ ok: true, msg: 'Mesajınız alındı. Ekibimiz en kısa sürede sizinle iletişime geçecek.' });
      formEl.reset();
    } catch (err) {
      const status = err?.response?.status;
      setResult({
        ok: false,
        msg:
          status === 422
            ? 'Lütfen ad soyad, işletme, telefon ve geçerli bir e-posta girin.'
            : 'Mesaj gönderilemedi. Lütfen daha sonra tekrar deneyin.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="grid grid-cols-1 gap-4 sm:grid-cols-2" onSubmit={onSubmit}>
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

      {result && (
        <div
          className={
            'sm:col-span-2 rounded-xl px-4 py-3 text-sm ' +
            (result.ok
              ? 'border border-emerald-400/30 bg-emerald-400/10 text-emerald-100'
              : 'border border-rose-400/30 bg-rose-400/10 text-rose-100')
          }
        >
          {result.msg}
        </div>
      )}

      <div className="sm:col-span-2 flex items-center justify-between gap-4">
        <p className="text-xs text-slate-500">Bilgileriniz yalnızca size dönüş yapmak için kullanılır.</p>
        <button
          type="submit"
          disabled={submitting}
          className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-6 py-3 text-sm font-semibold text-[#05070f] shadow-[0_10px_30px_-10px_rgba(34,211,238,0.7)] transition hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Gönderiliyor...' : 'Mesaj Gönder'}
          <Send className="h-4 w-4" />
        </button>
      </div>
    </form>
  );
}

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

// Çözüm kartı ikonları — içerik super_admin panelinden düzenlenebildiği için
// metinler /api/site-content'ten gelir; ikonlar burada pozisyonel kalır.
const solutionIcons = [Hotel, Sparkles, Boxes, BarChart3, Zap, Layers];

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
  const [content, setContent] = useState(() => mergeLandingContent(null));
  const heroRef = useRef(null);

  const { scrollY } = useScroll();
  const heroParallax = useTransform(scrollY, [0, 600], [0, reduce ? 0 : -60]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // Public landing content overrides (super_admin tarafından düzenlenebilir).
  // Herhangi bir hatada yerleşik varsayılanlara döner, sayfa asla boş kalmaz.
  useEffect(() => {
    let active = true;
    fetch('/api/site-content', { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (active && data) setContent(mergeLandingContent(data)); })
      .catch(() => {});
    return () => { active = false; };
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
          <a href="#top" className="group flex items-center gap-2.5">
            <img
              src="/syroce-circle-256.webp"
              srcSet="/syroce-circle-256.webp 1x, /syroce-circle-512.webp 2x"
              alt="Syroce"
              width={40}
              height={40}
              loading="eager"
              decoding="async"
              className="h-10 w-10 rounded-full shadow-[0_0_32px_rgba(34,211,238,0.45)] ring-1 ring-white/15 transition group-hover:shadow-[0_0_44px_rgba(34,211,238,0.7)]"
            />
            <span className="text-lg font-bold tracking-tight text-white">{content.brandName}</span>
          </a>

          <nav className="hidden items-center gap-1 lg:flex">
            {navLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="group relative rounded-full px-3 py-1.5 text-[13px] text-slate-300 transition hover:text-white"
              >
                {l.label}
                <span
                  aria-hidden
                  className="pointer-events-none absolute inset-x-3 -bottom-0.5 h-px scale-x-0 bg-gradient-to-r from-transparent via-cyan-300/80 to-transparent transition-transform duration-300 group-hover:scale-x-100"
                />
              </a>
            ))}
          </nav>

          <div className="hidden items-center gap-2.5 md:flex">
            <button
              onClick={goLogin}
              className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-[13px] font-medium text-slate-200 transition hover:border-white/20 hover:bg-white/[0.06] hover:text-white"
            >
              <LogIn className="h-3.5 w-3.5" />
              Giriş Yap
            </button>
            <button
              onClick={goSupplier}
              className="group relative inline-flex items-center gap-2 overflow-hidden rounded-full border border-cyan-300/40 bg-gradient-to-r from-cyan-400/15 via-teal-300/10 to-indigo-400/15 px-3.5 py-1.5 text-[13px] font-semibold text-cyan-100 shadow-[0_0_22px_-6px_rgba(34,211,238,0.55),inset_0_1px_0_rgba(255,255,255,0.08)] transition hover:border-cyan-200/70 hover:text-white hover:shadow-[0_0_30px_-4px_rgba(34,211,238,0.85),inset_0_1px_0_rgba(255,255,255,0.12)]"
            >
              <span aria-hidden className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/15 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
              <Users className="relative h-3.5 w-3.5" />
              <span className="relative">Tedarikçi Girişi</span>
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
        {/* Breathing ambient blobs — sürekli scale/opacity döngüsü ile hero canlı hisset */}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute left-[-10%] top-[5%] h-[420px] w-[420px] rounded-full bg-cyan-500/30 blur-3xl"
          animate={reduce ? {} : { scale: [1, 1.08, 1], opacity: [0.7, 1, 0.7] }}
          transition={{ duration: 9, repeat: Infinity, ease: 'easeInOut' }}
        />
        <motion.div
          aria-hidden
          className="pointer-events-none absolute right-[-8%] top-[20%] h-[520px] w-[520px] rounded-full bg-indigo-500/35 blur-3xl"
          animate={reduce ? {} : { scale: [1, 1.06, 1], opacity: [0.75, 1, 0.75] }}
          transition={{ duration: 11, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
        />
        <motion.div
          aria-hidden
          className="pointer-events-none absolute right-[15%] bottom-[5%] h-[380px] w-[380px] rounded-full bg-teal-400/25 blur-3xl"
          animate={reduce ? {} : { scale: [1, 1.1, 1], opacity: [0.65, 0.95, 0.65] }}
          transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut', delay: 2 }}
        />

        <div className="mx-auto grid w-full max-w-7xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-[0.78fr_1.22fr] lg:gap-8 lg:px-10">
          {/* Left copy */}
          <motion.div
            initial={{ opacity: 0, y: reduce ? 0 : 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="min-w-0"
          >
            <span className="inline-flex max-w-full items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2.5 py-1 text-[10px] font-medium tracking-wider text-cyan-300 sm:px-3 sm:text-xs">
              <Sparkles className="h-3 w-3 shrink-0 sm:h-3.5 sm:w-3.5" />
              <span className="truncate">{content.hero.badge}</span>
            </span>

            <h1 className="mt-4 break-words text-[1.75rem] font-semibold leading-[1.1] tracking-tight text-white sm:mt-6 sm:text-5xl sm:leading-[1.08] lg:text-[2.85rem] xl:text-[3.15rem]">
              {content.hero.titlePre}{' '}
              <span className="inline-block bg-gradient-to-r from-cyan-300 via-sky-300 to-indigo-300 bg-clip-text text-transparent">
                {content.hero.titleAccent}
              </span>
              <br className="hidden sm:block" />
              {' '}{content.hero.titlePost}
            </h1>

            <p className="mt-3.5 max-w-xl text-[13.5px] leading-relaxed text-slate-300/90 sm:mt-5 sm:text-lg">
              {content.hero.description}
              {content.hero.descriptionAccent ? (
                <span className="text-cyan-200/90">{content.hero.descriptionAccent}</span>
              ) : null}
            </p>

            <div className="mt-5 grid grid-cols-2 gap-2.5 sm:mt-7 sm:flex sm:flex-wrap sm:items-center sm:gap-3">
              <button
                onClick={goLogin}
                className="group col-span-2 inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-5 py-3 text-[13px] font-semibold text-[#05070f] shadow-[0_12px_40px_-10px_rgba(34,211,238,0.7)] transition hover:translate-y-[-1px] hover:shadow-[0_16px_50px_-8px_rgba(34,211,238,0.9)] sm:col-span-1 sm:px-6 sm:text-sm"
              >
                Giriş Yap
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </button>
              <button
                onClick={goSupplier}
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-4 py-3 text-[13px] font-semibold text-white transition hover:bg-white/[0.08] sm:px-6 sm:text-sm"
              >
                <Users className="h-4 w-4" />
                Tedarikçi Girişi
              </button>
              <a
                href="#iletisim"
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-4 py-3 text-[13px] font-semibold text-cyan-200 transition hover:bg-cyan-400/15 sm:px-6 sm:text-sm"
              >
                <Sparkles className="h-4 w-4" />
                Demo Talep Et
              </a>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-2.5 sm:mt-7 sm:flex sm:flex-wrap sm:gap-5">
              {heroBadges.map((b) => (
                <div key={b.label} className="inline-flex items-center gap-2 text-[12px] text-slate-300 sm:text-sm">
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-cyan-400/15 text-cyan-300 sm:h-6 sm:w-6">
                    <b.icon className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
                  </span>
                  <span className="truncate">{b.label}</span>
                </div>
              ))}
            </div>

            {/* Mobile-only pill — moved out of hero image area to prevent clipping */}
            <div className="mt-5 inline-flex max-w-full items-center gap-2 rounded-2xl border border-cyan-400/40 bg-[#0a1424]/80 px-3.5 py-2 text-[11px] leading-snug text-cyan-100 shadow-[0_8px_30px_-8px_rgba(34,211,238,0.55)] backdrop-blur-xl lg:hidden">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
              <span>Oteliniz için akıllı, güvenli ve etkili bir yönetim platformu.</span>
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
            {/*
              HERO VISUAL (redesign 2026-05-16):
              - Hotel görseli artık çerçeve/border/inset-shadow içinde DEĞİL.
              - object-contain + drop-shadow ile hero içinde bağımsız 3D asset gibi durur.
              - Hiçbir frame "screenshot/mockup" izlenimi vermez.
              - Floating glass kartlar görselin etrafında dengeli pozisyonda.
            */}
            <div
              className="relative mx-auto flex min-h-[300px] w-full max-w-[860px] items-center justify-center sm:min-h-[420px] lg:min-h-[680px] lg:-translate-y-4 lg:translate-x-3"
            >
              {/* Arka katman 1 — geniş cyan/teal ambient halo (otelin arka aydınlatması) */}
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-8 top-4 bottom-6 rounded-[2rem] bg-[radial-gradient(ellipse_at_center,_rgba(45,232,222,0.32),_rgba(34,211,238,0.12)_38%,_transparent_70%)] blur-2xl sm:inset-x-4 sm:top-6 sm:bottom-10 sm:rounded-[3rem] sm:bg-[radial-gradient(ellipse_at_center,_rgba(45,232,222,0.42),_rgba(34,211,238,0.18)_38%,_transparent_70%)] sm:blur-3xl"
              />
              {/* Arka katman 2 — derin mavi/mor atmosfer (üst kısım) */}
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-16 top-0 h-[55%] rounded-full bg-[radial-gradient(ellipse_at_top,_rgba(99,102,241,0.22),_transparent_70%)] blur-2xl sm:inset-x-12 sm:bg-[radial-gradient(ellipse_at_top,_rgba(99,102,241,0.32),_transparent_70%)] sm:blur-3xl"
              />
              {/* Arka katman 3 — alt neon zemin parıltısı (otelin altı) */}
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-24 bottom-2 h-16 rounded-[100%] bg-[radial-gradient(ellipse_at_center,_rgba(56,242,232,0.4),_transparent_75%)] blur-xl sm:inset-x-20 sm:h-24 sm:bg-[radial-gradient(ellipse_at_center,_rgba(56,242,232,0.55),_transparent_75%)] sm:blur-2xl"
              />

              {/* 3D otel görseli — bağımsız asset (frame YOK), büyütüldü.
                  Responsive: mobil/tablet/desktop için ayrı WebP variant'ları,
                  PNG orijinal fallback olarak. */}
              <picture>
                <source
                  type="image/webp"
                  srcSet={`/landing/hero-hotel-640.webp 640w, /landing/hero-hotel-960.webp 960w, /landing/hero-hotel-1280.webp 1280w`}
                  sizes="(max-width: 639px) 100vw, (max-width: 1023px) 80vw, 860px"
                />
                <img
                  src={HERO_IMG}
                  alt="Syroce 3D Otel Görünümü"
                  className="relative z-[1] block h-auto w-full max-h-[300px] object-contain sm:max-h-[420px] lg:max-h-[680px]"
                  style={{ filter: 'drop-shadow(0 25px 50px rgba(0, 220, 220, 0.28)) drop-shadow(0 8px 18px rgba(99, 102, 241, 0.18))' }}
                  loading="eager"
                  decoding="async"
                  width="1280"
                  height="896"
                />
              </picture>

              {/* Connection lines — otel merkezinden floating kartlara doğru ince
                  neon yollar + akan data dot'ları. SVG viewBox 100×100; pos %
                  ile kartların yaklaşık merkez koordinatlarına denk gelir. */}
              <svg
                aria-hidden
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                className="pointer-events-none absolute inset-0 z-[2] hidden h-full w-full lg:block"
              >
                <defs>
                  <linearGradient id="syroceLine" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%"  stopColor="rgba(94,234,212,0.0)" />
                    <stop offset="40%" stopColor="rgba(94,234,212,0.55)" />
                    <stop offset="100%" stopColor="rgba(99,102,241,0.0)" />
                  </linearGradient>
                </defs>
                {/* Hotel merkez ~ (50, 55). Kart merkezleri yaklaşık. */}
                {[
                  { x: 18, y: 16 }, { x: 14, y: 42 }, { x: 19, y: 80 },
                  { x: 82, y: 18 }, { x: 84, y: 48 }, { x: 80, y: 78 },
                ].map((p, i) => (
                  <g key={i}>
                    <line
                      x1="50" y1="55" x2={p.x} y2={p.y}
                      stroke="url(#syroceLine)" strokeWidth="0.18" strokeLinecap="round"
                    />
                    {!reduce && (
                      <motion.circle
                        r="0.5"
                        fill="rgba(125,255,240,0.95)"
                        initial={{ cx: 50, cy: 55, opacity: 0 }}
                        animate={{ cx: [50, p.x], cy: [55, p.y], opacity: [0, 1, 0] }}
                        transition={{ duration: 3.2 + (i * 0.4), repeat: Infinity, delay: i * 0.55, ease: 'easeInOut' }}
                      />
                    )}
                  </g>
                ))}
              </svg>

              {/* Alt orta neon pill — sadece lg+ görselin altında; mobilde sol kolona taşındı */}
              <div className="absolute bottom-1 left-1/2 z-[2] hidden -translate-x-1/2 whitespace-nowrap rounded-full border border-cyan-400/45 bg-[#0a1424]/90 px-4 py-2 text-xs text-cyan-100 shadow-[0_12px_40px_-6px_rgba(34,211,238,0.65)] backdrop-blur-xl lg:block">
                <Sparkles className="mr-1.5 inline h-3.5 w-3.5 text-cyan-300" />
                Oteliniz için akıllı, güvenli ve etkili bir yönetim platformu.
              </div>

              {/*
                Floating cards — referans premium görsele göre kalibre:
                - Sol: top 8% / top 34% / bottom 18%
                - Sağ: top 10% / top 40% / bottom 16%
                - Genişlik 230px (başlıklar artık kırpılmaz: "Rezervasyonlar",
                  "Gelir ve Raporlama" tek satırda sığar).
                - Glassmorphism + cyan border + hover glow güçlendirildi.
              */}
              {[
                { pos: { top: '8%',     left: '7%'  }, icon: Calendar,  title: 'Rezervasyonlar',   desc: 'Tüm kanalları tek yerden yönetin',                  pct: '18%', side: 'L', i: 0 },
                { pos: { top: '34%',    left: '3%'  }, icon: Users,     title: 'Misafir Deneyimi', desc: 'Daha mutlu misafirler, daha güçlü sadakat',          pct: '24%', side: 'L', i: 1 },
                { pos: { bottom: '18%', left: '8%'  }, icon: Handshake, title: 'Tedarikçi Ağı',    desc: 'Güvenilir tedarikçilerle hızlı iş birliği',          pct: '22%', side: 'L', i: 2 },
                { pos: { top: '10%',    right: '4%' }, icon: BarChart3, title: 'Gelir ve Raporlama', desc: 'Performansınızı anlık görün',                      pct: '23%', side: 'R', i: 0 },
                { pos: { top: '40%',    right: '2%' }, icon: Boxes,     title: 'Tek Platform',       desc: 'Tüm modüller tek ekranda',                          pct: '15%', side: 'R', i: 1 },
                { pos: { bottom: '16%', right: '6%' }, icon: Headphones,title: 'Canlı Destek',       desc: '7/24 yanınızdayız',                                 online: true, side: 'R', i: 2 },
              ].map((c) => (
                <motion.div
                  key={`${c.side}${c.i}`}
                  animate={reduce ? {} : { y: [0, (c.i % 2 ? 6 : -6), 0] }}
                  transition={{ duration: 5 + c.i, repeat: Infinity, ease: 'easeInOut' }}
                  style={c.pos}
                  className="group/card absolute z-[3] hidden w-[230px] lg:block"
                >
                  <div className="rounded-[20px] border border-[rgba(75,235,230,0.4)] bg-[rgba(8,26,42,0.58)] p-[18px] text-white shadow-[0_24px_70px_rgba(0,220,220,0.18),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-[22px] transition duration-300 group-hover/card:border-[rgba(94,234,212,0.7)] group-hover/card:shadow-[0_30px_90px_rgba(45,232,222,0.32),inset_0_1px_0_rgba(255,255,255,0.12)]">
                    <div className="flex items-start gap-2.5">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-cyan-400/20 text-cyan-200 ring-1 ring-cyan-400/35 shadow-[inset_0_0_12px_rgba(34,211,238,0.25)]">
                        <c.icon className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-1.5">
                          <div className="text-[13px] font-semibold leading-tight text-white">{c.title}</div>
                          {c.pct && (
                            <span className="shrink-0 rounded-md bg-emerald-400/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">↑ {c.pct}</span>
                          )}
                        </div>
                        <p className="mt-1 text-[11px] leading-snug text-slate-300/85">{c.desc}</p>
                        {c.online && (
                          <div className="mt-1.5 inline-flex items-center gap-1 text-[10px] font-medium text-emerald-300">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                            Çevrimiçi
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>

            {/*
              Mobile/tablet fallback: lg altında floating kartlar görünmez,
              görsel altında düzenli 2 kolon grid olarak listelenir.
              Üst üste binme riski yok; tek liste, okunaklı.
            */}
            <div className="mt-5 grid grid-cols-2 gap-2.5 lg:hidden">
              {[
                { icon: Calendar,  title: 'Rezervasyon',      desc: 'Tüm kanallar tek yerde' },
                { icon: Users,     title: 'Misafir',          desc: 'Mutlu misafir, güçlü sadakat' },
                { icon: Handshake, title: 'Tedarikçi',        desc: 'Hızlı iş birliği' },
                { icon: BarChart3, title: 'Gelir & Rapor',    desc: 'Anlık performans' },
                { icon: Boxes,     title: 'Tek Platform',     desc: 'Modüller tek ekranda' },
                { icon: Headphones,title: 'Canlı Destek',     desc: '7/24 yanınızda' },
              ].map((c) => (
                <div
                  key={c.title}
                  className="flex h-full flex-col rounded-2xl border border-[rgba(75,235,230,0.22)] bg-[rgba(8,26,42,0.55)] p-3 backdrop-blur-lg shadow-[0_8px_24px_-12px_rgba(34,211,238,0.35)]"
                >
                  <div className="flex items-center gap-2">
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-cyan-400/15 text-cyan-300 ring-1 ring-cyan-400/25">
                      <c.icon className="h-3.5 w-3.5" />
                    </span>
                    <div className="truncate text-[12.5px] font-semibold text-white">{c.title}</div>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-slate-300/85">{c.desc}</p>
                </div>
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

          {/* Trust strip — enterprise/SaaS güven sinyalleri (uptime / multi-property /
              KVKK / API / channel integrations). Hero altı boşluğu kapatır ve
              hospitality OS hissi verir. */}
          <div className="mt-5 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 rounded-2xl border border-white/10 bg-white/[0.025] px-5 py-4 text-[12px] text-slate-300 backdrop-blur-xl sm:gap-x-8 sm:text-[13px]">
            <div className="inline-flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.85)]" />
              </span>
              <span className="font-semibold text-emerald-300">%99,9 Uptime</span>
              <span className="text-slate-400">SLA</span>
            </div>
            <div className="hidden h-4 w-px bg-white/10 sm:block" />
            <div className="inline-flex items-center gap-2">
              <Layers className="h-4 w-4 text-cyan-300" />
              <span>Çoklu Tesis Yönetimi</span>
            </div>
            <div className="hidden h-4 w-px bg-white/10 sm:block" />
            <div className="inline-flex items-center gap-2">
              <Globe className="h-4 w-4 text-cyan-300" />
              <span>Kanal & OTA Entegrasyonları</span>
            </div>
            <div className="hidden h-4 w-px bg-white/10 sm:block" />
            <div className="inline-flex items-center gap-2">
              <Zap className="h-4 w-4 text-cyan-300" />
              <span>API & Webhook</span>
            </div>
            <div className="hidden h-4 w-px bg-white/10 sm:block" />
            <div className="inline-flex items-center gap-2">
              <Lock className="h-4 w-4 text-cyan-300" />
              <span>KVKK / GDPR Ready</span>
            </div>
            <div className="hidden h-4 w-px bg-white/10 sm:block" />
            <div className="inline-flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-cyan-300" />
              <span>Audit & 2FA</span>
            </div>
          </div>
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
            {content.solutions.map((s, i) => {
              const Icon = solutionIcons[i] || Layers;
              return (
              <motion.div
                key={s.title || i}
                initial={{ opacity: 0, y: reduce ? 0 : 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.45, delay: i * 0.05 }}
              >
                <GlassCard className="group h-full p-6 transition hover:-translate-y-1 hover:border-cyan-400/30 hover:bg-white/[0.06]">
                  <span className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-to-br from-cyan-400/20 to-indigo-500/20 text-cyan-300 ring-1 ring-white/10">
                    <Icon className="h-6 w-6" />
                  </span>
                  <h3 className="mt-5 text-lg font-semibold text-white">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.desc}</p>
                  <a href="#iletisim" className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-cyan-300 hover:text-cyan-200">
                    Detayları Gör <ArrowUpRight className="h-4 w-4" />
                  </a>
                </GlassCard>
              </motion.div>
              );
            })}
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

          {/*
            Panel önizleme (redesign 2026-05-16):
            Önceden HERO_IMG buraya "Panel önizleme" olarak basılıyordu —
            sayfanın kendi 3D otel hero görselini bir mockup gibi tekrar
            göstermek istenmiyor. Bunun yerine DOM-render mock dashboard
            (sticky topbar + KPI cards + bar chart + son aktiviteler)
            kullanılıyor. Sekme değiştikçe KPI değerleri/etiketler değişir.
          */}
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: reduce ? 0 : 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mt-8"
          >
            <GlassCard className="overflow-hidden p-2 sm:p-3">
              <div className="overflow-hidden rounded-[1.4rem] border border-white/10 bg-gradient-to-b from-[#0a1828] via-[#0b1a2e] to-[#070f1c]">
                {/* Mock topbar */}
                <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.03] px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-cyan-400 to-teal-300 text-[11px] font-bold text-[#05070f]">S</span>
                    <span className="text-sm font-semibold text-white">{content.brandName} · {dashboardTabs.find((t) => t.key === activeTab)?.label}</span>
                  </div>
                  <div className="hidden items-center gap-2 sm:flex">
                    <span className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2 py-0.5 text-[10px] text-cyan-300">Canlı</span>
                    <span className="grid h-7 w-7 place-items-center rounded-full bg-white/[0.06] text-slate-300"><Users className="h-3.5 w-3.5" /></span>
                  </div>
                </div>

                {/* Mock KPI row — sekme bazlı */}
                <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-4 sm:gap-3 sm:p-4">
                  {(() => {
                    const kpiByTab = {
                      rez: [
                        { label: 'Bugün Giriş',     value: '24',   trend: '+12%', icon: Calendar },
                        { label: 'Bugün Çıkış',     value: '18',   trend: '+8%',  icon: ArrowUpRight },
                        { label: 'Açık Rezervasyon',value: '142',  trend: '+5%',  icon: Layers },
                        { label: 'Doluluk',         value: '%83',  trend: '+3%',  icon: BarChart3 },
                      ],
                      occ: [
                        { label: 'Doluluk',         value: '%83',  trend: '+3%',  icon: BarChart3 },
                        { label: 'Müsait Oda',      value: '17',   trend: '-2',   icon: LayoutGrid },
                        { label: 'Geç Çıkış',       value: '4',    trend: '0',    icon: RefreshCw },
                        { label: 'No-Show Risk',    value: '%6',   trend: '-1%',  icon: ShieldCheck },
                      ],
                      req: [
                        { label: 'Açık Talep',      value: '11',   trend: '+2',   icon: Headphones },
                        { label: 'SLA İçinde',      value: '%94',  trend: '+2%',  icon: ShieldCheck },
                        { label: 'Ortalama Süre',   value: '12 dk',trend: '-3 dk',icon: Zap },
                        { label: 'VIP',             value: '3',    trend: '+1',   icon: Star },
                      ],
                      rev: [
                        { label: 'Günlük Gelir',    value: '₺184k',trend: '+9%',  icon: BarChart3 },
                        { label: 'ADR',             value: '₺3.2k',trend: '+5%',  icon: ArrowUpRight },
                        { label: 'RevPAR',          value: '₺2.6k',trend: '+7%',  icon: Sparkles },
                        { label: 'Upsell',          value: '%18',  trend: '+4%',  icon: Layers },
                      ],
                      sup: [
                        { label: 'Açık Sipariş',    value: '37',   trend: '+5',   icon: Boxes },
                        { label: 'Bekleyen Teklif', value: '12',   trend: '+2',   icon: Handshake },
                        { label: 'Tedarikçi',       value: '128',  trend: '+3',   icon: Truck },
                        { label: 'Bu Ay Tasarruf',  value: '%11',  trend: '+2%',  icon: BarChart3 },
                      ],
                    };
                    const k = kpiByTab[activeTab] || kpiByTab.rez;
                    return k.map((kpi) => (
                      <div key={kpi.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="flex items-center justify-between">
                          <span className="grid h-7 w-7 place-items-center rounded-md bg-cyan-400/15 text-cyan-300">
                            <kpi.icon className="h-3.5 w-3.5" />
                          </span>
                          <span className="rounded-md bg-emerald-400/15 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-300">{kpi.trend}</span>
                        </div>
                        <div className="mt-2 text-lg font-semibold text-white">{kpi.value}</div>
                        <div className="text-[10px] text-slate-400">{kpi.label}</div>
                      </div>
                    ));
                  })()}
                </div>

                {/* Mock chart strip */}
                <div className="border-t border-white/10 bg-white/[0.02] px-4 py-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Son 7 Gün</span>
                    <span className="text-[11px] text-cyan-300">Detay ↗</span>
                  </div>
                  <div className="flex items-end gap-1.5 sm:gap-2">
                    {[
                      { day: 'Pzt', h: 42 },
                      { day: 'Sal', h: 58 },
                      { day: 'Çar', h: 71 },
                      { day: 'Per', h: 55 },
                      { day: 'Cum', h: 83 },
                      { day: 'Cmt', h: 68 },
                      { day: 'Paz', h: 91 },
                    ].map((b) => (
                      <div key={b.day} className="flex flex-1 flex-col items-center gap-1">
                        <div
                          className="w-full rounded-t-md bg-gradient-to-t from-cyan-500/80 to-teal-300"
                          style={{ height: `${b.h * 0.7}px` }}
                        />
                        <span className="text-[9px] text-slate-500">{b.day}</span>
                      </div>
                    ))}
                  </div>
                </div>
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
            {content.faqs.map((f, i) => {
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
                  {content.contact.phone}
                </div>
                <div className="flex items-center gap-3 text-slate-300">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/20">
                    <Mail className="h-4 w-4" />
                  </span>
                  {content.contact.email}
                </div>
                <div className="flex items-center gap-3 text-slate-300">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/20">
                    <MapPin className="h-4 w-4" />
                  </span>
                  {content.contact.address}
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
                <LandingContactForm />
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
                <img
                  src="/syroce-circle-256.webp"
                  srcSet="/syroce-circle-256.webp 1x, /syroce-circle-512.webp 2x"
                  alt="Syroce"
                  width={40}
                  height={40}
                  loading="lazy"
                  decoding="async"
                  className="h-10 w-10 rounded-full shadow-[0_0_28px_rgba(34,211,238,0.35)] ring-1 ring-white/15"
                />
                <div>
                  <div className="text-lg font-bold tracking-tight text-white">{content.brandName}</div>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-300/70">Hospitality OS</div>
                </div>
              </a>
              <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-400">
                Otelinizi, operasyonlarınızı ve misafir deneyiminizi tek merkezden yönetin.
                Sadece bir yazılım değil — konaklama operasyonu için modern bir işletim sistemi.
              </p>
              {/* Status / uptime live badge */}
              <a
                href="#iletisim"
                className="mt-5 inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-300 transition hover:border-emerald-300/50 hover:bg-emerald-400/15"
              >
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                </span>
                Tüm sistemler aktif · %99,9 uptime
              </a>
              <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1.5"><Lock className="h-3.5 w-3.5" /> KVKK / GDPR</span>
                <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> 2FA / Audit log</span>
                <span className="inline-flex items-center gap-1.5"><Globe className="h-3.5 w-3.5" /> TR · EN · DE · RU</span>
              </div>
            </div>

            <FooterCol title="Ürün" items={[
              { label: 'Modüller',             href: '#moduller' },
              { label: 'Çözümler',             href: '#cozumler' },
              { label: 'Misafir Deneyimi',     href: '#deneyim' },
              { label: 'Tedarik ve Satın Alma',href: '#tedarikci' },
              { label: 'Çoklu Tesis',          href: '#cozumler' },
              { label: 'Yol Haritası',         href: '#iletisim' },
            ]} />
            <FooterCol title="Geliştiriciler" items={[
              { label: 'API & Webhook',        href: '#iletisim' },
              { label: 'Entegrasyonlar',       href: '#cozumler' },
              { label: 'Channel Manager',      href: '#cozumler' },
              { label: 'OTA Bağlantıları',     href: '#cozumler' },
              { label: 'Dokümantasyon',        href: '#iletisim' },
            ]} />
            <FooterCol title="Güven" items={[
              { label: 'Güvenlik',             href: '/privacy-policy' },
              { label: 'KVKK / GDPR',          href: '/privacy-policy' },
              { label: 'Uptime Status',        href: '#iletisim' },
              { label: 'Gizlilik',             href: '/privacy-policy' },
              { label: 'Kullanım Şartları',    href: '/privacy-policy' },
            ]} />
            <FooterCol title="Şirket" items={[
              { label: 'Hakkımızda',           href: '#hakkimizda' },
              { label: 'İletişim',             href: '#iletisim' },
              { label: 'SSS',                  href: '#sss' },
              { label: 'Demo Talep',           href: '#iletisim' },
              { label: 'Müşteri Girişi',       href: '/auth' },
              { label: 'Tedarikçi Girişi',     href: '/tedarikci/giris' },
            ]} />
          </div>

          <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-white/10 py-6 text-xs text-slate-500 sm:flex-row">
            <div>© {new Date().getFullYear()} {content.brandName}. Tüm hakları saklıdır.</div>
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
