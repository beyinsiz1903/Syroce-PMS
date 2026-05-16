import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Truck, Mail, Lock, ArrowRight, ShieldCheck, Handshake, Send } from 'lucide-react';

const SupplierAuthPage = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState('login');
  const [submitted, setSubmitted] = useState(false);
  const [form, setForm] = useState({ email: '', password: '', company: '', taxNo: '', phone: '' });

  const onChange = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const onSubmit = (e) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#05070f] text-slate-100 antialiased">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(99,102,241,0.18),_transparent_60%),radial-gradient(ellipse_at_bottom,_rgba(34,211,238,0.12),_transparent_60%)]" />
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)',
            backgroundSize: '64px 64px',
            maskImage: 'radial-gradient(ellipse at center, black 40%, transparent 75%)',
          }}
        />
      </div>

      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6 lg:px-10">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-[#05070f] shadow-[0_0_24px_rgba(34,211,238,0.45)]">
            <span className="text-sm font-bold">S</span>
          </span>
          <span className="text-lg font-semibold tracking-tight text-white">Syroce</span>
        </Link>
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-4 py-2 text-sm text-white transition hover:bg-white/[0.08]"
        >
          <ArrowLeft className="h-4 w-4" />
          Ana Sayfa
        </Link>
      </header>

      <main className="relative z-10 mx-auto grid max-w-6xl gap-10 px-4 py-10 sm:px-6 lg:grid-cols-2 lg:gap-16 lg:px-10 lg:py-16">
        {/* Sol — pazarlama paneli */}
        <section className="hidden lg:block">
          <span className="inline-flex items-center gap-2 rounded-full border border-indigo-400/30 bg-indigo-400/10 px-3 py-1 text-xs font-medium tracking-wider text-indigo-200">
            <Truck className="h-3.5 w-3.5" />
            TEDARİKÇİ AĞI
          </span>
          <h1 className="mt-6 text-4xl font-semibold leading-tight tracking-tight text-white sm:text-5xl">
            Otellerle <span className="bg-gradient-to-r from-cyan-300 via-sky-300 to-indigo-300 bg-clip-text text-transparent">doğrudan</span> iş yapın.
          </h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-slate-300/90">
            Syroce tedarikçi ağına katılın; teklif, sipariş ve ödeme süreçlerini tek panelden yönetin.
            Yeni müşteriler kazanın, görünürlüğünüzü artırın.
          </p>

          <div className="mt-8 grid gap-3">
            {[
              { icon: Handshake,    title: 'Otellerle hızlı buluşma', desc: 'Talep gönderen otellere anında ulaşın.' },
              { icon: ShieldCheck,  title: 'Güvenli süreçler',         desc: 'Sözleşme, fatura ve ödeme tek yerde.' },
              { icon: Send,         title: 'Daha çok iş fırsatı',      desc: 'Profilinizle binlerce işletme önünde olun.' },
            ].map((it) => (
              <div key={it.title} className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-400/15 text-indigo-300 ring-1 ring-indigo-400/25">
                  <it.icon className="h-5 w-5" />
                </span>
                <div>
                  <div className="text-sm font-semibold text-white">{it.title}</div>
                  <div className="text-sm text-slate-400">{it.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Sağ — form */}
        <section>
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 backdrop-blur-xl sm:p-8">
            <div className="flex items-center gap-3">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-[#05070f] shadow-[0_0_24px_rgba(34,211,238,0.45)]">
                <Truck className="h-6 w-6" />
              </span>
              <div>
                <div className="text-lg font-semibold text-white">Tedarikçi Girişi</div>
                <div className="text-sm text-slate-400">
                  {mode === 'login' ? 'Hesabınıza giriş yapın' : 'Tedarikçi ağına başvuru yapın'}
                </div>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-2 rounded-xl bg-white/[0.04] p-1">
              {[
                { k: 'login',    label: 'Giriş Yap' },
                { k: 'register', label: 'Başvuru' },
              ].map((t) => (
                <button
                  key={t.k}
                  onClick={() => { setMode(t.k); setSubmitted(false); }}
                  className={
                    'rounded-lg px-3 py-2 text-sm font-medium transition ' +
                    (mode === t.k
                      ? 'bg-cyan-400 text-[#05070f] shadow-[0_8px_24px_-8px_rgba(34,211,238,0.7)]'
                      : 'text-slate-300 hover:text-white')
                  }
                >
                  {t.label}
                </button>
              ))}
            </div>

            {submitted ? (
              <div className="mt-6 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-5 text-sm text-emerald-100">
                <div className="font-semibold text-emerald-200">
                  {mode === 'login' ? 'Demo modu' : 'Başvurunuz alındı'}
                </div>
                <p className="mt-1.5 text-emerald-100/90">
                  {mode === 'login'
                    ? 'Tedarikçi portalı yakında devreye alınıyor. Erken erişim için başvuru sekmesinden talep oluşturabilirsiniz.'
                    : 'Ekibimiz başvurunuzu en kısa sürede inceleyecek ve sizinle iletişime geçecek.'}
                </p>
                <button
                  onClick={() => setSubmitted(false)}
                  className="mt-4 inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-xs font-medium text-white hover:bg-white/15"
                >
                  Forma dön
                </button>
              </div>
            ) : (
              <form onSubmit={onSubmit} className="mt-6 grid gap-4">
                {mode === 'register' && (
                  <>
                    <Field label="Firma Adı" placeholder="Örn. Akdeniz Gıda Ltd. Şti." value={form.company} onChange={onChange('company')} />
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Vergi No" placeholder="1234567890" value={form.taxNo} onChange={onChange('taxNo')} />
                      <Field label="Telefon" placeholder="+90 5xx xxx xx xx" value={form.phone} onChange={onChange('phone')} />
                    </div>
                  </>
                )}
                <Field label="E-posta" type="email" icon={Mail} placeholder="ornek@firma.com" value={form.email} onChange={onChange('email')} required />
                {mode === 'login' && (
                  <Field label="Parola" type="password" icon={Lock} placeholder="••••••••" value={form.password} onChange={onChange('password')} required />
                )}

                <button
                  type="submit"
                  className="group mt-2 inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-6 py-3 text-sm font-semibold text-[#05070f] shadow-[0_12px_40px_-10px_rgba(34,211,238,0.7)] transition hover:translate-y-[-1px]"
                >
                  {mode === 'login' ? 'Giriş Yap' : 'Başvuruyu Gönder'}
                  <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </button>

                <p className="text-center text-xs text-slate-500">
                  Otel yöneticisi misiniz?{' '}
                  <Link to="/auth" className="font-medium text-cyan-300 hover:text-cyan-200">
                    Otel Girişi'ne geçin
                  </Link>
                </p>
              </form>
            )}
          </div>
        </section>
      </main>
    </div>
  );
};

const Field = ({ label, icon: Icon, ...rest }) => (
  <label className="block">
    <span className="mb-1.5 block text-xs font-medium text-slate-300">{label}</span>
    <div className="relative">
      {Icon && (
        <span className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center text-slate-500">
          <Icon className="h-4 w-4" />
        </span>
      )}
      <input
        {...rest}
        className={
          'w-full rounded-xl border border-white/10 bg-white/[0.04] py-2.5 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-400/40 focus:bg-white/[0.06] ' +
          (Icon ? 'pl-9 pr-3' : 'px-3')
        }
      />
    </div>
  </label>
);

export default SupplierAuthPage;
