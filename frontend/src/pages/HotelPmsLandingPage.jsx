import React, { useEffect } from 'react';
import { ArrowRight, CalendarDays, ClipboardList, Hotel, Layers3, Receipt, ShieldCheck } from 'lucide-react';
import MarketingContactForm from '@/components/marketing/MarketingContactForm';
import MarketingConsent from '@/components/marketing/MarketingConsent';

const featureCards = [
  { icon: CalendarDays, title: 'Rezervasyon takvimi', body: 'Odaları, tarihleri ve rezervasyonları tek takvim üzerinden görün. Oda değiştirme akışını demoda deneyin.' },
  { icon: ClipboardList, title: 'Ön büro işlemleri', body: 'Giriş, çıkış ve konaklama bilgilerini günlük operasyon içinde takip edin.' },
  { icon: Receipt, title: 'Folyo ve tahsilat', body: 'Günlük fiyatları, ek ücretleri, ödemeleri ve kalan bakiyeyi aynı rezervasyon bağlamında inceleyin.' },
  { icon: Layers3, title: 'Tesisinize uygun kapsam', body: 'Kullanıcı yetkileri, raporlar ve kanal bağlantılarının kapsamını ihtiyaçlarınıza göre değerlendirin.' },
];

const demoSteps = [
  'Kullandığınız oda tiplerini ve rezervasyon akışını konuşalım.',
  'Takvim, ön büro ve folyo işlemlerini canlı üründe gösterelim.',
  'Entegrasyon ve kurulum kapsamını tesisinize göre netleştirelim.',
];

export default function HotelPmsLandingPage() {
  useEffect(() => {
    const previousTitle = document.title;
    const description = document.querySelector('meta[name="description"]');
    const previousDescription = description?.content;
    const canonical = document.querySelector('link[rel="canonical"]');
    const previousCanonical = canonical?.href;
    document.title = 'Otel Yönetim Programı ve PMS Demo | Syroce';
    if (description) description.content = 'Syroce otel yönetim programında rezervasyon takvimi, ön büro, folyo ve oda operasyonunu canlı demoda inceleyin. Tesisinize uygun kapsam için demo talep edin.';
    if (canonical) canonical.href = 'https://pms.syroce.com/otel-programi';
    if (window.location.hash === '#demo') {
      requestAnimationFrame(() => document.getElementById('demo')?.scrollIntoView());
    }
    return () => {
      document.title = previousTitle;
      if (description) description.content = previousDescription || '';
      if (canonical) canonical.href = previousCanonical || 'https://pms.syroce.com/';
    };
  }, []);

  return <div className="min-h-screen overflow-x-hidden bg-[#07111e] text-slate-100">
    <MarketingConsent />
    <header className="border-b border-white/10 bg-[#07111e]/95">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
        <a href="/" className="flex items-center gap-2 text-lg font-bold"><img src="/syroce-circle-256.webp" width="36" height="36" alt="" className="rounded-full" />Syroce</a>
        <div className="flex items-center gap-3 text-sm"><a href="/auth" className="hidden text-slate-300 hover:text-white sm:inline">Giriş Yap</a><a href="#demo" className="rounded-full bg-cyan-400 px-4 py-2 font-semibold text-[#07111e]">Demo Talep Et</a></div>
      </div>
    </header>

    <main>
      <section className="relative overflow-hidden border-b border-white/10 bg-[radial-gradient(ellipse_at_top_right,_rgba(34,211,238,0.16),_transparent_55%)]">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-2 lg:gap-16 lg:py-28">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-cyan-200"><Hotel className="h-4 w-4" /> Oteller için PMS</p>
            <h1 className="mt-6 text-4xl font-semibold leading-tight tracking-tight text-white sm:text-5xl">Otel rezervasyonlarını ve ön büro işlerini <span className="text-cyan-300">tek panelde</span> yönetin</h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">Syroce ile rezervasyon takvimini, odaları, misafir işlemlerini ve folyoları birlikte görün. Sisteminizle uyumunu canlı demoda kendi senaryonuz üzerinden değerlendirin.</p>
            <div className="mt-8 flex flex-wrap gap-3"><a href="#demo" className="inline-flex min-h-12 items-center gap-2 rounded-full bg-cyan-400 px-6 py-3 font-semibold text-[#07111e] hover:bg-cyan-300">Demo Talep Et <ArrowRight className="h-4 w-4" /></a><a href="#neler-goreceksiniz" className="inline-flex min-h-12 items-center rounded-full border border-white/20 px-6 py-3 font-medium hover:bg-white/5">Neler göreceksiniz?</a></div>
            <p className="mt-5 text-sm text-slate-400">Fiyat, kurulum süresi ve entegrasyon kapsamı tesisinize göre görüşmede netleştirilir.</p>
          </div>
          <div aria-label="Rezervasyon takvimi iş akışının temsili gösterimi" className="rounded-3xl border border-white/10 bg-[#0c2033] p-4 shadow-[0_25px_90px_-35px_rgba(34,211,238,0.45)] sm:p-6">
            <div className="flex items-center justify-between border-b border-white/10 pb-4"><div className="flex items-center gap-2 text-sm font-semibold"><CalendarDays className="h-5 w-5 text-cyan-300" /> Rezervasyon Takvimi</div><span className="rounded-full bg-white/10 px-2.5 py-1 text-xs text-slate-300">Temsili akış</span></div>
            <div className="mt-5 grid grid-cols-[5rem_repeat(3,minmax(0,1fr))] gap-2 text-center text-xs sm:grid-cols-[7rem_repeat(3,minmax(0,1fr))]">
              <span className="text-left text-slate-400">Oda</span>{['Pzt', 'Sal', 'Çar'].map(day => <span key={day} className="text-slate-400">{day}</span>)}
              {['101', '102', '103'].map((room, index) => <React.Fragment key={room}><span className="rounded-lg bg-white/5 p-3 text-left text-slate-200">{room}</span>{[0, 1, 2].map(day => <span key={day} className={`rounded-lg p-3 ${day === index || (index === 0 && day === 1) ? 'bg-cyan-400/25 text-cyan-100' : 'bg-white/5 text-slate-500'}`}>{day === index ? 'Dolu' : index === 0 && day === 1 ? 'Dolu' : 'Müsait'}</span>)}</React.Fragment>)}
            </div>
            <div className="mt-5 flex flex-wrap gap-2 text-xs text-slate-300"><span className="rounded-full border border-white/10 px-3 py-1.5">Rezervasyon</span><span className="rounded-full border border-white/10 px-3 py-1.5">Ön büro</span><span className="rounded-full border border-white/10 px-3 py-1.5">Folyo</span></div>
          </div>
        </div>
      </section>

      <section id="neler-goreceksiniz" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="max-w-2xl"><p className="text-sm font-semibold uppercase tracking-wider text-cyan-300">ÜRÜNÜ TANIYIN</p><h2 className="mt-3 text-3xl font-semibold text-white sm:text-4xl">Günlük otel operasyonunuzdaki temel akışlar</h2><p className="mt-4 text-slate-300">Özellikleri genel vaatlerle değil, canlı ürün üzerinden birlikte değerlendirin.</p></div>
        <div className="mt-9 grid gap-4 sm:grid-cols-2">{featureCards.map(card => <article key={card.title} className="rounded-2xl border border-white/10 bg-white/[0.04] p-6"><card.icon className="h-7 w-7 text-cyan-300" /><h3 className="mt-4 text-xl font-semibold">{card.title}</h3><p className="mt-2 leading-7 text-slate-300">{card.body}</p></article>)}</div>
      </section>

      <section className="border-y border-white/10 bg-white/[0.03]"><div className="mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:px-6 lg:grid-cols-2"><div><p className="text-sm font-semibold uppercase tracking-wider text-cyan-300">DEMO GÖRÜŞMESİ</p><h2 className="mt-3 text-3xl font-semibold">Kendi senaryonuzu getirin</h2><p className="mt-4 text-slate-300">Mevcut kullandığınız sistem veya kanal yöneticisi varsa söyleyin. Bağlantı kapsamını doğrulamadan çalıştığını varsaymayız.</p></div><ol className="space-y-4">{demoSteps.map((step, index) => <li key={step} className="flex gap-4"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-cyan-400/15 text-sm font-bold text-cyan-300">{index + 1}</span><span className="pt-1 text-slate-200">{step}</span></li>)}</ol></div></section>

      <section id="demo" className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[0.8fr_1.2fr]"><div><p className="text-sm font-semibold uppercase tracking-wider text-cyan-300">DEMO TALEBİ</p><h2 className="mt-3 text-3xl font-semibold">Otelinize uygun bir demo planlayalım</h2><p className="mt-4 leading-7 text-slate-300">Formu doldurun; ekibimiz sizinle iletişime geçsin. Formu göndermek ücretsizdir ve bir satın alma taahhüdü oluşturmaz.</p><div className="mt-6 flex items-center gap-2 text-sm text-slate-400"><ShieldCheck className="h-5 w-5 text-cyan-300" /> Talebiniz gizlilik politikamıza göre işlenir.</div></div><div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5 sm:p-8"><MarketingContactForm /></div></section>
    </main>
    <footer className="border-t border-white/10"><div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 text-sm text-slate-400 sm:flex-row sm:items-center sm:justify-between sm:px-6"><span>© {new Date().getFullYear()} Syroce</span><div className="flex flex-wrap gap-5"><a href="/" className="hover:text-white">Ana Sayfa</a><a href="/privacy-policy" className="hover:text-white">Gizlilik Politikası</a><button type="button" onClick={() => window.dispatchEvent(new Event('syroce:marketing-preferences'))} className="text-left hover:text-white">Analitik Tercihi</button><a href="mailto:info@syroce.com" className="hover:text-white">info@syroce.com</a></div></div></footer>
  </div>;
}
