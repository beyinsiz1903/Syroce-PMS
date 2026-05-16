import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  motion,
  useScroll,
  useTransform,
  useSpring,
  useMotionValue,
  useReducedMotion,
} from 'framer-motion';
import {
  ArrowRight, Check, TrendingUp, Smile, Clock, ShieldCheck,
  Calendar, Users, BarChart3, Sparkles, Star, Phone, Mail,
  Hotel, CreditCard, KeyRound,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

const LandingPage = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const benefits = [
    { icon: TrendingUp, title: 'Daha çok gelir',  desc: 'Doğru fiyatı doğru zamanda öner. Boş kalan odayı dolu odaya çevir.' },
    { icon: Clock,      title: 'Daha az iş yükü', desc: 'Rezervasyondan faturaya kadar her adım otomatik. Ekibin asıl işine odaklansın.' },
    { icon: Smile,      title: 'Mutlu misafirler',desc: 'Hızlı check-in, kişisel hatırlatmalar ve sorunsuz ödeme. Yorumlar konuşsun.' },
    { icon: ShieldCheck,title: 'Gönül rahatlığı', desc: 'Verileriniz güvende, kanallar her zaman senkron. Geceleri rahat uyuyun.' },
  ];

  const features = [
    { icon: Calendar,  title: 'Akıllı Rezervasyon Takvimi', desc: 'Tüm odalar tek ekranda. Sürükle-bırak ile düzenle.' },
    { icon: BarChart3, title: 'Anlık Raporlar',             desc: 'Doluluk, gelir, kanal performansı — saniyeler içinde.' },
    { icon: Users,     title: 'Misafir Profili',            desc: 'Tekrar gelen misafirinizi tanıyın, tercihlerini hatırlayın.' },
    { icon: Sparkles,  title: 'Otomatik Fiyatlama',         desc: 'Sezona ve talebe göre fiyatınız kendiliğinden ayarlanır.' },
    { icon: ShieldCheck,title: 'Kanal Yönetimi',            desc: 'Booking, Expedia, kendi siteniz — tek tuşla güncellensin.' },
    { icon: Phone,     title: '7/24 Destek',                desc: 'Türkçe konuşan ekibimiz her zaman yanınızda.' },
  ];

  const stats = [
    { value: '%38',     label: 'Ortalama gelir artışı' },
    { value: '12 saat', label: 'Haftada kazanılan zaman' },
    { value: '500+',    label: 'Mutlu otel' },
    { value: '4.9/5',   label: 'Müşteri memnuniyeti' },
  ];

  const testimonials = [
    { name: 'Ayşe Yılmaz',  role: 'Genel Müdür, Bodrum',       text: 'İlk ay içinde doluluk %22 arttı. Resepsiyon ekibi artık misafirlerle ilgilenmek için zaman buluyor.' },
    { name: 'Mehmet Demir', role: 'Sahip, Kapadokya',          text: 'Eskiden Booking ve Expedia\'yı manuel güncelliyorduk. Şimdi her şey kendiliğinden oluyor. Hayat kurtaran bir sistem.' },
    { name: 'Selin Kaya',   role: 'Operasyon Müdürü, Antalya', text: 'Raporlar çok net. Sabah kahvemi içerken bütün otelin durumunu tek bakışta görüyorum.' },
  ];

  const plans = [
    { name: 'Başlangıç',  price: '₺1.490', period: '/ay',  desc: 'Küçük butik oteller için.',          features: ['50 odaya kadar', 'Rezervasyon ve takvim', 'Temel raporlar', 'E-posta destek'], highlight: false },
    { name: 'Profesyonel',price: '₺3.490', period: '/ay',  desc: 'Büyüyen oteller için en popüler.',   features: ['Sınırsız oda', 'Kanal yönetimi (Booking, Expedia...)', 'Otomatik fiyatlama', 'Detaylı analiz', 'Telefon + WhatsApp destek'], highlight: true },
    { name: 'Kurumsal',   price: 'Özel',   period: 'fiyat',desc: 'Zincir ve büyük oteller için.',      features: ['Çoklu otel yönetimi', 'Özel entegrasyonlar', 'Atanmış başarı yöneticisi', '7/24 öncelikli destek'], highlight: false },
  ];

  // Puzzle bölümünün 4 parçası — her biri PMS'in bir hizmetini anlatır.
  // Scroll ilerledikçe parçalar uzaydan gelip 3D döner, perspektif içinde
  // ortada birleşip "tam tablo"yu oluşturur.
  const puzzlePieces = [
    {
      icon: Hotel,
      title: 'Rezervasyon & Oda',
      desc: 'Tüm odalar, tüm kanallar, tek takvim. Çakışma yok, kayıp rezervasyon yok.',
      from: { x: -380, y: -260, rx: -40, ry: 55, rz: -15 },
      gradient: 'from-cyan-300/40 via-sky-400/30 to-indigo-500/40',
      glow: 'shadow-[0_0_80px_rgba(56,189,248,0.35)]',
    },
    {
      icon: CreditCard,
      title: 'Folio & Ödeme',
      desc: 'Misafir hesabı, fatura, ödeme akışı — hepsi tek dokunuşla, güvenli.',
      from: { x: 380, y: -260, rx: -40, ry: -55, rz: 15 },
      gradient: 'from-fuchsia-300/40 via-violet-400/30 to-purple-500/40',
      glow: 'shadow-[0_0_80px_rgba(168,85,247,0.35)]',
    },
    {
      icon: KeyRound,
      title: 'Kat Hizmeti & Operasyon',
      desc: 'Temizlik, bakım, kat ekibi — gerçek zamanlı görev akışı.',
      from: { x: -380, y: 260, rx: 40, ry: 55, rz: 15 },
      gradient: 'from-emerald-300/40 via-teal-400/30 to-cyan-500/40',
      glow: 'shadow-[0_0_80px_rgba(45,212,191,0.35)]',
    },
    {
      icon: BarChart3,
      title: 'Analitik & Karar',
      desc: 'Doluluk, ADR, RevPAR, kanal performansı — anlık panelde.',
      from: { x: 380, y: 260, rx: 40, ry: -55, rz: -15 },
      gradient: 'from-amber-300/40 via-orange-400/30 to-rose-500/40',
      glow: 'shadow-[0_0_80px_rgba(251,146,60,0.35)]',
    },
  ];

  return (
    <div className="min-h-screen bg-[#05060f] text-white overflow-x-hidden selection:bg-cyan-400/30">
      {/* Arka plan: derin uzayda yumuşak ışık küreleri — bütün sayfaya derinlik */}
      <BackgroundField />

      {/* Navigation */}
      <nav className={`fixed w-full z-50 transition-all duration-500 ${
        scrolled
          ? 'bg-white/5 backdrop-blur-2xl border-b border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.4)]'
          : 'bg-transparent'
      }`}>
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CrystalMark size={36} />
            <span className="font-semibold tracking-wide text-white/90">Syroce</span>
          </div>
          <div className="hidden md:flex items-center gap-7">
            <a href="#avantajlar" className="text-sm font-medium text-white/70 hover:text-white transition">Avantajlar</a>
            <a href="#ozellikler" className="text-sm font-medium text-white/70 hover:text-white transition">Özellikler</a>
            <a href="#fiyatlar"   className="text-sm font-medium text-white/70 hover:text-white transition">Fiyatlar</a>
            <a href="#iletisim"   className="text-sm font-medium text-white/70 hover:text-white transition">İletişim</a>
            <button onClick={() => navigate('/vendor')} className="text-sm font-medium text-white/70 hover:text-white transition">Tedarikçi Girişi</button>
            <Button
              onClick={() => navigate('/auth')}
              className="bg-white text-black hover:bg-white/90 shadow-[0_8px_32px_rgba(255,255,255,0.25)] font-semibold"
            >
              Otel Girişi
            </Button>
          </div>
          <Button
            onClick={() => navigate('/auth')}
            className="md:hidden bg-white text-black hover:bg-white/90 font-semibold px-4 h-9 text-sm"
          >
            Giriş
          </Button>
        </div>
      </nav>

      {/* HERO — büyük kristal, mouse-parallax + scroll fade */}
      <Hero onCta={() => navigate('/auth')} />

      {/* PUZZLE ASSEMBLY — scroll ile uzaydan gelip ortada birleşen 4 cam parça */}
      <PuzzleAssembly pieces={puzzlePieces} />

      {/* AVANTAJLAR */}
      <section id="avantajlar" className="relative py-32 px-6">
        <div className="max-w-7xl mx-auto">
          <SectionHeading
            eyebrow="Neden Syroce"
            title="Otelinize değer katan dört temel"
            sub="Cam gibi şeffaf, kristal gibi sağlam."
          />
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mt-16">
            {benefits.map((b, i) => (
              <GlassTiltCard key={b.title} delay={i * 0.08}>
                <div className="flex flex-col gap-4">
                  <div className="w-12 h-12 rounded-xl bg-white/10 backdrop-blur-xl border border-white/20 flex items-center justify-center shadow-inner">
                    <b.icon className="w-6 h-6 text-cyan-300" />
                  </div>
                  <h3 className="text-lg font-semibold text-white">{b.title}</h3>
                  <p className="text-sm text-white/60 leading-relaxed">{b.desc}</p>
                </div>
              </GlassTiltCard>
            ))}
          </div>
        </div>
      </section>

      {/* İSTATİSTİKLER — cam plakalarda parlayan sayılar */}
      <StatsBand stats={stats} />

      {/* ÖZELLİKLER — yüzen cam küpler */}
      <section id="ozellikler" className="relative py-32 px-6">
        <div className="max-w-7xl mx-auto">
          <SectionHeading
            eyebrow="Özellikler"
            title="Bir günlük işin saniyelere indiği yer"
            sub="Her özellik, gerçek bir otel günlük rutininden doğdu."
          />
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mt-16">
            {features.map((f, i) => (
              <FloatingGlassCube key={f.title} delay={i * 0.1}>
                <div className="flex items-start gap-4">
                  <div className="w-11 h-11 rounded-lg bg-gradient-to-br from-white/15 to-white/5 border border-white/20 flex items-center justify-center shrink-0 backdrop-blur-xl">
                    <f.icon className="w-5 h-5 text-cyan-200" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-white mb-1.5">{f.title}</h3>
                    <p className="text-sm text-white/55 leading-relaxed">{f.desc}</p>
                  </div>
                </div>
              </FloatingGlassCube>
            ))}
          </div>
        </div>
      </section>

      {/* MİSAFİR REFERANSLARI — 3D döner cam plakalar */}
      <section className="relative py-32 px-6">
        <div className="max-w-7xl mx-auto">
          <SectionHeading
            eyebrow="Onlar konuşuyor"
            title="500+ otel zaten Syroce ile büyüyor"
          />
          <div className="grid md:grid-cols-3 gap-6 mt-16">
            {testimonials.map((t, i) => (
              <GlassTiltCard key={t.name} delay={i * 0.1} tone="warm">
                <div className="flex flex-col gap-4">
                  <div className="flex gap-0.5">
                    {[0,1,2,3,4].map(s => (
                      <Star key={s} className="w-4 h-4 fill-amber-300 text-amber-300" />
                    ))}
                  </div>
                  <p className="text-white/80 leading-relaxed text-sm italic">"{t.text}"</p>
                  <div className="pt-3 border-t border-white/10">
                    <p className="text-sm font-semibold text-white">{t.name}</p>
                    <p className="text-xs text-white/50">{t.role}</p>
                  </div>
                </div>
              </GlassTiltCard>
            ))}
          </div>
        </div>
      </section>

      {/* FİYATLAR */}
      <section id="fiyatlar" className="relative py-32 px-6">
        <div className="max-w-7xl mx-auto">
          <SectionHeading
            eyebrow="Fiyatlandırma"
            title="Şeffaf. Sürprizsiz."
            sub="Otelinizin büyüklüğüne göre seçin. İlk 14 gün ücretsiz."
          />
          <div className="grid md:grid-cols-3 gap-6 mt-16">
            {plans.map((p, i) => (
              <PricingPanel key={p.name} plan={p} delay={i * 0.1} onCta={() => navigate('/auth')} />
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section id="iletisim" className="relative py-32 px-6">
        <div className="max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 40, rotateX: -10 }}
            whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            style={{ transformPerspective: 1200 }}
            className="relative rounded-3xl p-12 md:p-16 text-center overflow-hidden
                       bg-gradient-to-br from-white/[0.08] via-white/[0.04] to-white/[0.02]
                       border border-white/15 backdrop-blur-2xl
                       shadow-[0_30px_120px_rgba(56,189,248,0.15)]"
          >
            {/* iç parlama */}
            <div className="absolute inset-0 -z-10">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-cyan-500/20 rounded-full blur-3xl" />
              <div className="absolute bottom-0 right-0 w-[400px] h-[400px] bg-fuchsia-500/15 rounded-full blur-3xl" />
            </div>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">
              Otelinizi bugün <span className="bg-gradient-to-r from-cyan-300 to-fuchsia-300 bg-clip-text text-transparent">kristal kadar net</span> yönetin.
            </h2>
            <p className="text-white/70 text-lg mb-10 max-w-2xl mx-auto">
              14 gün ücretsiz deneyin. Kredi kartı yok, taahhüt yok. Ekibinize 15 dakikada öğretiyoruz.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                onClick={() => navigate('/auth')}
                className="bg-white text-black hover:bg-white/90 h-12 px-8 text-base font-semibold shadow-[0_12px_40px_rgba(255,255,255,0.3)]"
              >
                Ücretsiz Başla <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
              <Button
                variant="outline"
                onClick={() => window.open('mailto:info@syroce.com')}
                className="border-white/25 bg-white/5 text-white hover:bg-white/10 h-12 px-8 text-base"
              >
                <Mail className="w-4 h-4 mr-2" /> Bizimle Konuş
              </Button>
            </div>
          </motion.div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="relative border-t border-white/10 py-10 px-6 mt-10">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-white/50">
          <div className="flex items-center gap-2">
            <CrystalMark size={24} />
            <span>© {new Date().getFullYear()} Syroce PMS</span>
          </div>
          <div className="flex gap-6">
            <a href="/privacy-policy" className="hover:text-white transition">Gizlilik</a>
            <a href="#" className="hover:text-white transition">Şartlar</a>
            <a href="mailto:info@syroce.com" className="hover:text-white transition">info@syroce.com</a>
          </div>
        </div>
      </footer>
    </div>
  );
};

/* ════════════════════════════════════════════════════════════════════════════
   ALT BİLEŞENLER — landing-only, harici dosyaya ayrılmadı çünkü hiçbir
   yerden re-use edilmiyor; tek dosyada okumak/yönetmek daha kolay.
   ════════════════════════════════════════════════════════════════════════ */

// Arka plan ışık alanı: 3 büyük yumuşak küre + grid + grain hissi.
// sticky değil — sayfa boyunca akar.
function BackgroundField() {
  const reduce = useReducedMotion();
  const orb = (anim) => reduce ? {} : { animate: anim, transition: { duration: 20, repeat: Infinity, ease: 'easeInOut' } };
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#0b1230_0%,#05060f_55%,#000_100%)]" />
      <motion.div
        className="absolute top-[10%] -left-[10%] w-[600px] h-[600px] rounded-full blur-[120px] bg-cyan-500/20"
        {...orb({ x: [0, 60, 0], y: [0, 40, 0] })}
      />
      <motion.div
        className="absolute top-[40%] -right-[10%] w-[700px] h-[700px] rounded-full blur-[140px] bg-fuchsia-500/15"
        {...orb({ x: [0, -50, 0], y: [0, 60, 0] })}
      />
      <motion.div
        className="absolute bottom-[5%] left-[20%] w-[500px] h-[500px] rounded-full blur-[120px] bg-indigo-500/15"
        {...orb({ x: [0, 80, 0], y: [0, -40, 0] })}
      />
      <div className="absolute inset-0 opacity-[0.04] bg-[linear-gradient(rgba(255,255,255,0.5)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.5)_1px,transparent_1px)] bg-[size:60px_60px]" />
    </div>
  );
}

// Kristal logo işareti — küçük döner cam elmas
function CrystalMark({ size = 40 }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      style={{ width: size, height: size, transformPerspective: 600 }}
      animate={reduce ? undefined : { rotateY: [0, 360] }}
      transition={reduce ? undefined : { duration: 14, repeat: Infinity, ease: 'linear' }}
      className="relative"
    >
      <div
        className="absolute inset-0 rounded-lg rotate-45
                   bg-gradient-to-br from-cyan-200/60 via-white/30 to-fuchsia-300/50
                   border border-white/40 backdrop-blur-xl
                   shadow-[0_0_30px_rgba(103,232,249,0.5)]"
      />
      <div className="absolute inset-1 rounded-md rotate-45 border border-white/20" />
    </motion.div>
  );
}

// HERO — mouse-parallax ile dönen büyük kristal + başlık + CTA
function Hero({ onCta }) {
  const heroRef = useRef(null);
  const reduceMotion = useReducedMotion();
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const rx = useSpring(useTransform(my, [-1, 1], [12, -12]), { stiffness: 80, damping: 18 });
  const ry = useSpring(useTransform(mx, [-1, 1], [-18, 18]), { stiffness: 80, damping: 18 });

  // sayfa scroll'una göre kristal kayar/küçülür → puzzle bölümüne yumuşak geçiş
  const { scrollY } = useScroll();
  const heroOpacity = useTransform(scrollY, [0, 600], [1, 0]);
  const heroY = useTransform(scrollY, [0, 600], [0, -120]);

  function onMove(e) {
    const rect = heroRef.current?.getBoundingClientRect();
    if (!rect) return;
    const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const ny = ((e.clientY - rect.top) / rect.height) * 2 - 1;
    mx.set(nx);
    my.set(ny);
  }

  return (
    <section
      ref={heroRef}
      onMouseMove={onMove}
      className="relative min-h-screen flex items-center px-6 pt-24"
    >
      <motion.div
        style={{ opacity: heroOpacity, y: heroY }}
        className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center w-full"
      >
        {/* sol: metin */}
        <div>
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full
                       bg-white/5 border border-white/15 backdrop-blur-xl text-xs text-white/70 mb-6"
          >
            <Sparkles className="w-3.5 h-3.5 text-cyan-300" />
            Yeni nesil otel yönetim sistemi
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.05 }}
            className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.05] mb-6"
          >
            Otelinizin <br />
            <span className="bg-gradient-to-r from-cyan-300 via-white to-fuchsia-300 bg-clip-text text-transparent">
              kristal beyni.
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.15 }}
            className="text-lg md:text-xl text-white/65 max-w-xl mb-10 leading-relaxed"
          >
            Rezervasyon, kanal yönetimi, folio, kat hizmeti — hepsi tek camın ardında.
            Aşağı kaydırın, parçaların nasıl birleştiğini görün.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.25 }}
            className="flex flex-col sm:flex-row gap-3"
          >
            <Button
              onClick={onCta}
              className="bg-white text-black hover:bg-white/90 h-13 px-7 text-base font-semibold shadow-[0_14px_50px_rgba(255,255,255,0.25)]"
            >
              Ücretsiz Başla <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
            <Button
              variant="outline"
              onClick={() => document.getElementById('avantajlar')?.scrollIntoView({ behavior: 'smooth' })}
              className="border-white/25 bg-white/5 text-white hover:bg-white/10 h-13 px-7 text-base"
            >
              Nasıl Çalışır
            </Button>
          </motion.div>
        </div>

        {/* sağ: büyük kristal — mouse'a tepki verir */}
        <motion.div
          style={{ rotateX: rx, rotateY: ry, transformPerspective: 1400, transformStyle: 'preserve-3d' }}
          className="relative flex items-center justify-center min-h-[480px]"
        >
          {/* arka halo */}
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/20 via-transparent to-fuchsia-500/20 rounded-full blur-3xl" />

          {/* ana büyük elmas */}
          <motion.div
            animate={reduceMotion ? undefined : { rotateZ: [0, 360] }}
            transition={reduceMotion ? undefined : { duration: 40, repeat: Infinity, ease: 'linear' }}
            className="relative w-[280px] h-[280px] sm:w-[340px] sm:h-[340px] md:w-[420px] md:h-[420px]"
            style={{ transformStyle: 'preserve-3d' }}
          >
            <CrystalShard className="absolute inset-0 rounded-[40%] rotate-12" gradient="from-cyan-300/30 via-white/10 to-fuchsia-300/30" />
            <CrystalShard className="absolute inset-6 rounded-[35%] -rotate-12" gradient="from-fuchsia-300/25 via-white/15 to-cyan-200/30" />
            <CrystalShard className="absolute inset-14 rounded-[30%] rotate-45" gradient="from-white/40 via-cyan-100/30 to-white/10" />
          </motion.div>

          {/* yörüngedeki küçük parçalar — reduced-motion'da gizlenir */}
          {!reduceMotion && [0,1,2,3,4].map(i => (
            <motion.div
              key={i}
              className="absolute w-12 h-12 md:w-16 md:h-16 rounded-lg bg-white/10 border border-white/20 backdrop-blur-xl shadow-[0_0_30px_rgba(255,255,255,0.15)]"
              style={{
                left: '50%',
                top: '50%',
                marginLeft: -24,
                marginTop: -24,
                transformStyle: 'preserve-3d',
              }}
              animate={{
                rotateZ: [0, 360],
                x: [Math.cos(i * 1.25) * 220, Math.cos(i * 1.25 + Math.PI * 2) * 220],
                y: [Math.sin(i * 1.25) * 220, Math.sin(i * 1.25 + Math.PI * 2) * 220],
              }}
              transition={{ duration: 18 + i * 2, repeat: Infinity, ease: 'linear' }}
            />
          ))}
        </motion.div>
      </motion.div>

      {/* scroll ipucu */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1, y: [0, 10, 0] }}
        transition={{ delay: 1, duration: 2, repeat: Infinity }}
        className="absolute bottom-8 left-1/2 -translate-x-1/2 text-xs text-white/40 tracking-widest"
      >
        AŞAĞI KAYDIR — PARÇALAR BİRLEŞSİN
      </motion.div>
    </section>
  );
}

function CrystalShard({ className, gradient }) {
  return (
    <div
      className={`${className} bg-gradient-to-br ${gradient}
                  border border-white/30 backdrop-blur-2xl
                  shadow-[inset_0_2px_30px_rgba(255,255,255,0.25),0_30px_100px_rgba(56,189,248,0.25)]`}
    >
      {/* iç ışık çizgisi (refleksiyon) */}
      <div className="absolute top-[10%] left-[10%] w-[40%] h-[10%] rounded-full bg-white/40 blur-md" />
    </div>
  );
}

// PUZZLE — sticky stage; scroll progress 0→1 boyunca 4 parça uzaydan
// merkeze gelir, döner ve oturur. En sonda etiketler belirir.
function PuzzleAssembly({ pieces }) {
  const stageRef = useRef(null);
  const { scrollYProgress } = useScroll({
    target: stageRef,
    offset: ['start start', 'end end'],
  });
  // pürüzsüz spring
  const progress = useSpring(scrollYProgress, { stiffness: 80, damping: 24, mass: 0.6 });

  return (
    <section ref={stageRef} className="relative" style={{ height: '320vh' }}>
      <div className="sticky top-0 h-screen flex items-center justify-center overflow-hidden">
        {/* başlık */}
        <motion.div
          style={{ opacity: useTransform(progress, [0, 0.1, 0.85, 1], [0, 1, 1, 0.7]) }}
          className="absolute top-[12%] left-0 right-0 px-6 text-center z-10"
        >
          <p className="text-xs tracking-[0.3em] text-cyan-300/80 uppercase mb-3">Hikâye</p>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight max-w-3xl mx-auto">
            Otel yönetimi, <span className="bg-gradient-to-r from-cyan-300 to-fuchsia-300 bg-clip-text text-transparent">tek camda</span> birleşir.
          </h2>
          <p className="text-white/55 mt-3 max-w-xl mx-auto text-sm md:text-base">
            Dört temel parça — dört kritik iş akışı. Hepsi bir araya geldiğinde tablo tamamlanır.
          </p>
        </motion.div>

        {/* sahne — perspektifli 3D alan */}
        <div
          className="relative w-full max-w-5xl h-[560px] mx-auto px-6"
          style={{ perspective: '1600px', perspectiveOrigin: 'center 40%' }}
        >
          {pieces.map((piece, i) => (
            <PuzzlePiece key={piece.title} piece={piece} index={i} progress={progress} />
          ))}

          {/* ortadaki birleşim halosu — son aşamada parlar */}
          <motion.div
            style={{
              opacity: useTransform(progress, [0.55, 0.85], [0, 1]),
              scale: useTransform(progress, [0.55, 0.95], [0.6, 1]),
            }}
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
          >
            <div className="w-[420px] h-[420px] rounded-full bg-gradient-to-br from-cyan-400/15 via-white/5 to-fuchsia-400/15 blur-3xl" />
          </motion.div>
        </div>

        {/* alt etiket — son aşamada belirir */}
        <motion.div
          style={{ opacity: useTransform(progress, [0.85, 1], [0, 1]), y: useTransform(progress, [0.85, 1], [20, 0]) }}
          className="absolute bottom-[10%] left-0 right-0 text-center px-6"
        >
          <p className="text-base md:text-lg text-white/80 font-medium">
            İşte sizin <span className="text-cyan-300">tam tabloyu görebildiğiniz</span> nokta.
          </p>
        </motion.div>
      </div>
    </section>
  );
}

function PuzzlePiece({ piece, index, progress }) {
  // Her parça farklı zaman aralığında "uçar". Sıralı animasyon → birleşim hissi.
  const start = 0.05 + index * 0.05;
  const end = 0.65;

  // Mobilde uçuş mesafesi daha kısa (taşma engellenir).
  const isCoarse = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 640px)').matches;
  const distScale = isCoarse ? 0.55 : 1;

  const x = useTransform(progress, [start, end], [piece.from.x * distScale, 0]);
  const y = useTransform(progress, [start, end], [piece.from.y * distScale, 0]);
  const rx = useTransform(progress, [start, end], [piece.from.rx, 0]);
  const ry = useTransform(progress, [start, end], [piece.from.ry, 0]);
  const rz = useTransform(progress, [start, end], [piece.from.rz, 0]);
  const opacity = useTransform(progress, [start - 0.05, start + 0.05, end, 1], [0, 1, 1, 1]);
  const scale = useTransform(progress, [start, end], [0.7, 1]);

  // 2x2 puzzle ızgarası. Mobilde parçalar küçülür ve ofset daralır.
  const col = index % 2;
  const row = Math.floor(index / 2);
  // CSS clamp: min 100px (telefon), tercih 22vw, max 160px (geniş ekran).
  const offset = 'clamp(105px, 22vw, 160px)';
  const baseLeft = `calc(50% + ${col === 0 ? `-1 * ${offset}` : '0px'})`;
  const baseTop = `calc(50% + ${row === 0 ? `-1 * ${offset}` : '0px'})`;

  // Parça boyutu da responsive (offset × 2 ile uyumlu)
  const w = 'clamp(210px, 44vw, 320px)';
  const h = 'clamp(130px, 28vw, 200px)';

  const Icon = piece.icon;

  return (
    <motion.div
      style={{
        position: 'absolute',
        left: baseLeft,
        top: baseTop,
        width: w,
        height: h,
        marginLeft: `calc(${w} / -2)`,
        marginTop: `calc(${h} / -2)`,
        x, y, rotateX: rx, rotateY: ry, rotateZ: rz, opacity, scale,
        transformStyle: 'preserve-3d',
      }}
    >
      <div
        className={`relative w-full h-full rounded-2xl overflow-hidden
                    bg-gradient-to-br ${piece.gradient}
                    border border-white/25 backdrop-blur-2xl ${piece.glow}`}
      >
        {/* refleksiyon çizgisi */}
        <div className="absolute -top-1/2 -left-1/4 w-3/4 h-full bg-white/15 rotate-[20deg] blur-2xl" />

        {/* puzzle çıkıntı/girinti süsleri (alt-üst yarım daire) — birleşme hissi */}
        {/* sağ kenardan çıkıntı (sadece sol-üst ve sol-alt parçalarda) */}
        {col === 0 && (
          <div className={`absolute top-1/2 -right-5 w-10 h-10 rounded-full
                          bg-gradient-to-br ${piece.gradient}
                          border border-white/25 -translate-y-1/2 backdrop-blur-xl`} />
        )}
        {/* sol kenarda girinti (sağ parçalar) — basit gölge ile */}
        {col === 1 && (
          <div className="absolute top-1/2 -left-1 w-3 h-10 -translate-y-1/2 rounded-r-full bg-black/30" />
        )}
        {/* alt kenardan çıkıntı (üst parçalarda) */}
        {row === 0 && (
          <div className={`absolute -bottom-5 left-1/2 w-10 h-10 rounded-full
                          bg-gradient-to-br ${piece.gradient}
                          border border-white/25 -translate-x-1/2 backdrop-blur-xl`} />
        )}
        {row === 1 && (
          <div className="absolute -top-1 left-1/2 w-10 h-3 -translate-x-1/2 rounded-b-full bg-black/30" />
        )}

        {/* içerik */}
        <div className="relative h-full p-6 flex flex-col justify-between">
          <div className="w-11 h-11 rounded-xl bg-white/15 border border-white/30 flex items-center justify-center backdrop-blur-xl">
            <Icon className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white mb-1.5 drop-shadow-md">{piece.title}</h3>
            <p className="text-xs text-white/85 leading-relaxed drop-shadow">{piece.desc}</p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// Bölüm başlığı
function SectionHeading({ eyebrow, title, sub }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.7 }}
      className="text-center"
    >
      <p className="text-xs tracking-[0.3em] text-cyan-300/80 uppercase mb-3">{eyebrow}</p>
      <h2 className="text-3xl md:text-5xl font-bold tracking-tight max-w-3xl mx-auto leading-tight">
        {title}
      </h2>
      {sub && <p className="text-white/55 mt-4 max-w-xl mx-auto">{sub}</p>}
    </motion.div>
  );
}

// 3D tilt cam kartı (mouse takip)
function GlassTiltCard({ children, delay = 0, tone = 'cool' }) {
  const cardRef = useRef(null);
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const rx = useSpring(useTransform(my, [-1, 1], [10, -10]), { stiffness: 150, damping: 18 });
  const ry = useSpring(useTransform(mx, [-1, 1], [-12, 12]), { stiffness: 150, damping: 18 });

  function onMove(e) {
    const r = cardRef.current?.getBoundingClientRect();
    if (!r) return;
    mx.set(((e.clientX - r.left) / r.width) * 2 - 1);
    my.set(((e.clientY - r.top) / r.height) * 2 - 1);
  }
  function onLeave() { mx.set(0); my.set(0); }

  const glow = tone === 'warm'
    ? 'shadow-[0_30px_80px_rgba(251,191,36,0.12)]'
    : 'shadow-[0_30px_80px_rgba(56,189,248,0.12)]';

  return (
    <motion.div
      ref={cardRef}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      initial={{ opacity: 0, y: 40, rotateX: -8 }}
      whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
      style={{ rotateX: rx, rotateY: ry, transformPerspective: 900, transformStyle: 'preserve-3d' }}
      className={`relative p-6 rounded-2xl
                  bg-gradient-to-br from-white/[0.08] via-white/[0.04] to-white/[0.02]
                  border border-white/15 backdrop-blur-2xl
                  hover:border-white/30 transition-colors ${glow}`}
    >
      {/* üst refleksiyon */}
      <div className="absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent" />
      <div style={{ transform: 'translateZ(20px)' }}>{children}</div>
    </motion.div>
  );
}

// Yüzen cam küp (özellik kartı)
function FloatingGlassCube({ children, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 50, rotateY: 25 }}
      whileInView={{ opacity: 1, y: 0, rotateY: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -6, rotateX: 6, rotateY: -6 }}
      style={{ transformPerspective: 1100, transformStyle: 'preserve-3d' }}
      className="relative p-6 rounded-2xl
                 bg-gradient-to-br from-white/[0.07] via-white/[0.03] to-transparent
                 border border-white/15 backdrop-blur-2xl
                 shadow-[0_20px_60px_rgba(0,0,0,0.4)]"
    >
      <div className="absolute inset-x-3 top-0 h-px bg-gradient-to-r from-transparent via-white/50 to-transparent" />
      {children}
    </motion.div>
  );
}

// İstatistik bandı
function StatsBand({ stats }) {
  return (
    <section className="relative py-20 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {stats.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 30, rotateX: -15 }}
              whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.7, delay: i * 0.08 }}
              style={{ transformPerspective: 800 }}
              className="relative p-6 rounded-2xl text-center
                         bg-gradient-to-br from-white/[0.06] to-white/[0.02]
                         border border-white/15 backdrop-blur-xl
                         shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]"
            >
              <div className="text-3xl md:text-4xl font-bold bg-gradient-to-br from-white via-cyan-100 to-fuchsia-200 bg-clip-text text-transparent mb-1">
                {s.value}
              </div>
              <div className="text-xs md:text-sm text-white/60">{s.label}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

// Fiyat paneli
function PricingPanel({ plan, delay, onCta }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 40, rotateX: -10 }}
      whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -8, rotateX: 4 }}
      style={{ transformPerspective: 1200, transformStyle: 'preserve-3d' }}
      className={`relative p-8 rounded-3xl backdrop-blur-2xl border
                  ${plan.highlight
                    ? 'bg-gradient-to-br from-cyan-400/15 via-white/[0.08] to-fuchsia-400/15 border-white/30 shadow-[0_30px_100px_rgba(56,189,248,0.25)]'
                    : 'bg-gradient-to-br from-white/[0.06] to-white/[0.02] border-white/15'}`}
    >
      {plan.highlight && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full text-[10px] tracking-widest uppercase bg-white text-black font-semibold shadow-lg">
          En Popüler
        </div>
      )}
      <h3 className="text-xl font-bold text-white">{plan.name}</h3>
      <p className="text-sm text-white/55 mt-1 mb-6">{plan.desc}</p>
      <div className="flex items-baseline gap-1 mb-6">
        <span className="text-4xl font-bold text-white">{plan.price}</span>
        <span className="text-sm text-white/50">{plan.period}</span>
      </div>
      <ul className="space-y-3 mb-8">
        {plan.features.map(f => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-white/75">
            <Check className="w-4 h-4 text-cyan-300 mt-0.5 shrink-0" />
            <span>{f}</span>
          </li>
        ))}
      </ul>
      <Button
        onClick={onCta}
        className={`w-full h-11 font-semibold ${
          plan.highlight
            ? 'bg-white text-black hover:bg-white/90'
            : 'bg-white/10 text-white hover:bg-white/20 border border-white/20'
        }`}
      >
        Başla <ArrowRight className="w-4 h-4 ml-2" />
      </Button>
    </motion.div>
  );
}

export default LandingPage;
