import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowRight, Check, TrendingUp, Smile, Clock, ShieldCheck,
  Calendar, Users, BarChart3, Sparkles, Star, Phone, Mail
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
    {
      icon: TrendingUp,
      title: 'Daha çok gelir',
      desc: 'Doğru fiyatı doğru zamanda öner. Boş kalan odayı dolu odaya çevir.',
      color: 'from-emerald-400 to-teal-500',
    },
    {
      icon: Clock,
      title: 'Daha az iş yükü',
      desc: 'Rezervasyondan faturaya kadar her adım otomatik. Ekibin asıl işine odaklansın.',
      color: 'from-blue-400 to-indigo-500',
    },
    {
      icon: Smile,
      title: 'Mutlu misafirler',
      desc: 'Hızlı check-in, kişisel hatırlatmalar ve sorunsuz ödeme. Yorumlar konuşsun.',
      color: 'from-pink-400 to-rose-500',
    },
    {
      icon: ShieldCheck,
      title: 'Gönül rahatlığı',
      desc: 'Verileriniz güvende, kanallar her zaman senkron. Geceleri rahat uyuyun.',
      color: 'from-amber-400 to-orange-500',
    },
  ];

  const features = [
    { icon: Calendar,  title: 'Akıllı Rezervasyon Takvimi', desc: 'Tüm odalar tek ekranda. Sürükle-bırak ile düzenle.' },
    { icon: BarChart3, title: 'Anlık Raporlar',             desc: 'Doluluk, gelir, kanal performansı — saniyeler içinde.' },
    { icon: Users,     title: 'Misafir Profili',            desc: 'Tekrar gelen misafirinizi tanıyın, tercihlerini hatırlayın.' },
    { icon: Sparkles,  title: 'Otomatik Fiyatlama',         desc: 'Sezona ve talebe göre fiyatınız kendiliğinden ayarlanır.' },
    { icon: ShieldCheck, title: 'Kanal Yönetimi',           desc: 'Booking, Expedia, kendi siteniz — tek tuşla güncellensin.' },
    { icon: Phone,     title: '7/24 Destek',                desc: 'Türkçe konuşan ekibimiz her zaman yanınızda.' },
  ];

  const stats = [
    { value: '%38',   label: 'Ortalama gelir artışı' },
    { value: '12 saat', label: 'Haftada kazanılan zaman' },
    { value: '500+',  label: 'Mutlu otel' },
    { value: '4.9/5', label: 'Müşteri memnuniyeti' },
  ];

  const testimonials = [
    {
      name: 'Ayşe Yılmaz',
      role: 'Genel Müdür, Bodrum',
      text: 'İlk ay içinde doluluk %22 arttı. Resepsiyon ekibi artık misafirlerle ilgilenmek için zaman buluyor.',
    },
    {
      name: 'Mehmet Demir',
      role: 'Sahip, Kapadokya',
      text: 'Eskiden Booking ve Expedia\'yı manuel güncelliyorduk. Şimdi her şey kendiliğinden oluyor. Hayat kurtaran bir sistem.',
    },
    {
      name: 'Selin Kaya',
      role: 'Operasyon Müdürü, Antalya',
      text: 'Raporlar çok net. Sabah kahvemi içerken bütün otelin durumunu tek bakışta görüyorum.',
    },
  ];

  const plans = [
    {
      name: 'Başlangıç',
      price: '₺1.490',
      period: '/ay',
      desc: 'Küçük butik oteller için.',
      features: ['50 odaya kadar', 'Rezervasyon ve takvim', 'Temel raporlar', 'E-posta destek'],
      highlight: false,
    },
    {
      name: 'Profesyonel',
      price: '₺3.490',
      period: '/ay',
      desc: 'Büyüyen oteller için en popüler.',
      features: ['Sınırsız oda', 'Kanal yönetimi (Booking, Expedia...)', 'Otomatik fiyatlama', 'Detaylı analiz', 'Telefon + WhatsApp destek'],
      highlight: true,
    },
    {
      name: 'Kurumsal',
      price: 'Özel',
      period: 'fiyat',
      desc: 'Zincir ve büyük oteller için.',
      features: ['Çoklu otel yönetimi', 'Özel entegrasyonlar', 'Atanmış başarı yöneticisi', '7/24 öncelikli destek'],
      highlight: false,
    },
  ];

  return (
    <div className="min-h-screen bg-white text-gray-900">
      {/* Navigation */}
      <nav className={`fixed w-full z-50 transition-all duration-300 ${
        scrolled ? 'bg-white/90 backdrop-blur-md shadow-sm border-b border-gray-100' : 'bg-transparent'
      }`}>
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <img src="/syroce-logo.svg" alt="Syroce" className="h-10 w-auto" />
          <div className="hidden md:flex items-center gap-7">
            <a href="#avantajlar" className={`text-sm font-medium transition ${scrolled ? 'text-gray-700 hover:text-blue-600' : 'text-white/90 hover:text-white'}`}>Avantajlar</a>
            <a href="#ozellikler" className={`text-sm font-medium transition ${scrolled ? 'text-gray-700 hover:text-blue-600' : 'text-white/90 hover:text-white'}`}>Özellikler</a>
            <a href="#fiyatlar" className={`text-sm font-medium transition ${scrolled ? 'text-gray-700 hover:text-blue-600' : 'text-white/90 hover:text-white'}`}>Fiyatlar</a>
            <a href="#iletisim" className={`text-sm font-medium transition ${scrolled ? 'text-gray-700 hover:text-blue-600' : 'text-white/90 hover:text-white'}`}>İletişim</a>
            <button
              onClick={() => navigate('/vendor')}
              className={`text-sm font-medium transition ${scrolled ? 'text-gray-700 hover:text-blue-600' : 'text-white/90 hover:text-white'}`}
            >
              Tedarikçi Girişi
            </button>
            <Button onClick={() => navigate('/auth')} className="bg-blue-600 hover:bg-blue-700 text-white shadow-md">
              Otel Girişi
            </Button>
          </div>
          {/* Mobil: kompakt giriş butonu — md altı ekranlarda nav menüsü gizli olduğundan
              kullanıcının hemen göz seviyesinde "Giriş" butonuna ulaşabilmesi gerekiyor. */}
          <Button
            onClick={() => navigate('/auth')}
            className="md:hidden bg-white text-blue-700 hover:bg-blue-50 shadow-md font-semibold px-4 h-9 text-sm"
          >
            Giriş
          </Button>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-32 pb-24 overflow-hidden bg-gradient-to-br from-indigo-900 via-blue-900 to-slate-900">
        <div className="absolute inset-0 opacity-30 pointer-events-none">
          <div className="absolute top-20 left-10 w-72 h-72 bg-blue-400 rounded-full mix-blend-screen filter blur-3xl animate-pulse" />
          <div className="absolute top-40 right-10 w-96 h-96 bg-purple-500 rounded-full mix-blend-screen filter blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
          <div className="absolute bottom-10 left-1/3 w-80 h-80 bg-pink-500 rounded-full mix-blend-screen filter blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
        </div>

        <div className="relative max-w-5xl mx-auto px-6 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-white/10 backdrop-blur-sm rounded-full border border-white/20 mb-8">
            <Sparkles className="w-4 h-4 text-yellow-300" />
            <span className="text-white text-xs font-semibold tracking-wide">Türkiye'nin En Akıllı Otel Yönetim Sistemi</span>
          </div>

          <h1 className="text-5xl md:text-7xl font-extrabold text-white leading-[1.05] mb-6">
            Otelinizi yönetmenin
            <span className="block bg-gradient-to-r from-amber-300 via-pink-300 to-purple-300 bg-clip-text text-transparent">
              en kolay yolu.
            </span>
          </h1>

          <p className="text-lg md:text-xl text-blue-100/90 max-w-2xl mx-auto mb-10 leading-relaxed">
            Rezervasyondan ödemeye, fiyat takibinden misafir mutluluğuna kadar
            her şey tek ekranda. Sade, hızlı, dert etmeden.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button
              size="lg"
              onClick={() => navigate('/auth')}
              className="bg-white text-blue-900 hover:bg-blue-50 font-semibold px-8 py-6 text-base shadow-2xl"
            >
              Ücretsiz Başla <ArrowRight className="ml-2 w-4 h-4" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={() => document.getElementById('avantajlar')?.scrollIntoView({ behavior: 'smooth' })}
              className="bg-white/5 backdrop-blur-sm border-white/30 text-white hover:bg-white/10 px-8 py-6 text-base"
            >
              Nasıl Çalışıyor?
            </Button>
          </div>

          <p className="text-blue-200/70 text-xs mt-6">
            Kredi kartı gerekmez · 14 gün ücretsiz dene · İstediğin zaman vazgeç
          </p>
        </div>
      </section>

      {/* Stats */}
      <section className="bg-white border-b border-gray-100 py-10">
        <div className="max-w-6xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-6">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <div className="text-3xl md:text-4xl font-extrabold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                {s.value}
              </div>
              <div className="text-xs md:text-sm text-gray-600 mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Benefits */}
      <section id="avantajlar" className="py-24 bg-gradient-to-b from-white to-gray-50">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-16">
            <p className="text-blue-600 font-semibold text-sm uppercase tracking-wider mb-3">Neden Syroce?</p>
            <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              Otelciler için, otelciler tarafından.
            </h2>
            <p className="text-gray-600 text-lg max-w-2xl mx-auto">
              Karışık menüler, eski yazılımlar, sürekli hata mesajları... Bunların hepsini geride bırakın.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {benefits.map((b) => {
              const Icon = b.icon;
              return (
                <div key={b.title} className="group relative bg-white rounded-2xl p-7 shadow-sm hover:shadow-xl border border-gray-100 transition-all duration-300 hover:-translate-y-1">
                  <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${b.color} flex items-center justify-center mb-5 shadow-lg`}>
                    <Icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">{b.title}</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">{b.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="ozellikler" className="py-24 bg-white">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-16">
            <p className="text-blue-600 font-semibold text-sm uppercase tracking-wider mb-3">Her Şey Dahil</p>
            <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              İhtiyacın olan her şey, tek pakette.
            </h2>
            <p className="text-gray-600 text-lg max-w-2xl mx-auto">
              Ekstra modül, gizli ücret veya karmaşık kurulum yok. Aboneliğin başladığı an her şey hazır.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="flex items-start gap-4 p-5 rounded-xl hover:bg-gray-50 transition-colors">
                  <div className="shrink-0 w-11 h-11 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                    <Icon className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900 mb-1">{f.title}</h3>
                    <p className="text-sm text-gray-600">{f.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-24 bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-900 text-white">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-16">
            <p className="text-blue-300 font-semibold text-sm uppercase tracking-wider mb-3">Otelciler Ne Diyor?</p>
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              Sadece sözümüz değil, sonuçlar.
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {testimonials.map((tst) => (
              <div key={tst.name} className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-7 hover:bg-white/10 transition-colors">
                <div className="flex gap-1 mb-4">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="w-4 h-4 fill-amber-300 text-amber-300" />
                  ))}
                </div>
                <p className="text-blue-50 leading-relaxed mb-6 text-sm">"{tst.text}"</p>
                <div>
                  <p className="font-semibold text-white">{tst.name}</p>
                  <p className="text-xs text-blue-300">{tst.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="fiyatlar" className="py-24 bg-gray-50">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-16">
            <p className="text-blue-600 font-semibold text-sm uppercase tracking-wider mb-3">Şeffaf Fiyatlar</p>
            <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              Otelinize uygun bir plan var.
            </h2>
            <p className="text-gray-600 text-lg max-w-2xl mx-auto">
              Gizli ücret yok. İstediğin zaman planını değiştir veya iptal et.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {plans.map((p) => (
              <div
                key={p.name}
                className={`relative rounded-2xl p-8 transition-all ${
                  p.highlight
                    ? 'bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-2xl scale-105 border-2 border-blue-400'
                    : 'bg-white text-gray-900 shadow-sm border border-gray-200 hover:shadow-lg'
                }`}
              >
                {p.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-amber-400 text-amber-900 text-xs font-bold px-3 py-1 rounded-full shadow">
                    EN POPÜLER
                  </div>
                )}
                <h3 className={`text-xl font-bold mb-1 ${p.highlight ? 'text-white' : 'text-gray-900'}`}>{p.name}</h3>
                <p className={`text-sm mb-6 ${p.highlight ? 'text-blue-100' : 'text-gray-600'}`}>{p.desc}</p>
                <div className="mb-6">
                  <span className="text-4xl font-extrabold">{p.price}</span>
                  <span className={`text-sm ml-1 ${p.highlight ? 'text-blue-200' : 'text-gray-500'}`}>{p.period}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <Check className={`w-4 h-4 mt-0.5 shrink-0 ${p.highlight ? 'text-amber-300' : 'text-emerald-500'}`} />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  onClick={() => navigate('/auth')}
                  className={`w-full ${
                    p.highlight
                      ? 'bg-white text-blue-700 hover:bg-blue-50'
                      : 'bg-gray-900 text-white hover:bg-gray-800'
                  }`}
                >
                  {p.price === 'Özel' ? 'İletişime Geç' : 'Hemen Başla'}
                </Button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-24 bg-white">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <div className="bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-700 rounded-3xl p-12 md:p-16 shadow-2xl relative overflow-hidden">
            <div className="absolute -top-20 -right-20 w-60 h-60 bg-white/10 rounded-full blur-3xl" />
            <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-white/10 rounded-full blur-3xl" />
            <div className="relative">
              <h2 className="text-3xl md:text-5xl font-extrabold text-white mb-4">
                Otelinizi bugün ileri taşıyın.
              </h2>
              <p className="text-blue-100 text-lg mb-8 max-w-xl mx-auto">
                14 gün ücretsiz deneyin. Hiçbir şey ödemeden Syroce'nin farkını yaşayın.
              </p>
              <Button
                size="lg"
                onClick={() => navigate('/auth')}
                className="bg-white text-blue-700 hover:bg-blue-50 font-bold px-10 py-6 text-base shadow-xl"
              >
                Ücretsiz Hesap Oluştur <ArrowRight className="ml-2 w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer id="iletisim" className="bg-gray-900 text-gray-300 py-14">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-10 mb-10">
            <div>
              <img src="/syroce-logo.svg" alt="Syroce" className="h-9 w-auto mb-4 brightness-0 invert" />
              <p className="text-sm text-gray-400 leading-relaxed">
                {t('landing.footer.tagline')}
              </p>
            </div>
            <div>
              <h4 className="font-semibold text-white mb-3 text-sm">{t('landing.footer.productHeading')}</h4>
              <ul className="space-y-2 text-sm text-gray-400">
                <li><a href="#avantajlar" className="hover:text-white">{t('landing.footer.benefits')}</a></li>
                <li><a href="#ozellikler" className="hover:text-white">{t('landing.footer.features')}</a></li>
                <li><a href="#fiyatlar" className="hover:text-white">{t('landing.footer.pricing')}</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-white mb-3 text-sm">{t('landing.footer.companyHeading')}</h4>
              <ul className="space-y-2 text-sm text-gray-400">
                <li>
                  <a
                    href="mailto:destek@syroce.com?subject=Hakk%C4%B1m%C4%B1zda%20bilgi%20talebi"
                    className="hover:text-white"
                  >
                    {t('landing.footer.about')}
                  </a>
                </li>
                <li>
                  <a
                    href="mailto:kariyer@syroce.com?subject=Kariyer%20ba%C5%9Fvurusu"
                    className="hover:text-white"
                  >
                    {t('landing.footer.careers')}
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-white mb-3 text-sm">{t('landing.footer.contactHeading')}</h4>
              <ul className="space-y-2 text-sm text-gray-400">
                <li className="flex items-center gap-2"><Mail className="w-4 h-4" /> destek@syroce.com</li>
                <li className="flex items-center gap-2"><Phone className="w-4 h-4" /> 0 (850) 000 00 00</li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-800 pt-6 flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-gray-500">
            <p>{t('landing.footer.copyright', { year: new Date().getFullYear() })}</p>
            <div className="flex gap-5">
              <a href="/privacy-policy" className="hover:text-white">{t('landing.footer.privacy')}</a>
              <a href="/privacy-policy" className="hover:text-white">{t('landing.footer.terms')}</a>
              <a href="/privacy-policy#kvkk" className="hover:text-white">{t('landing.footer.kvkk')}</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
