import { useState, useEffect } from 'react';
import { BookOpen, Key, Search, Hotel, Calendar, DollarSign, FileText, Bell, ChevronRight, Globe, Copy, Check, ArrowLeft, Code, Shield, Zap, Users, Sparkles, ClipboardList, CreditCard, Fingerprint, Package, Phone, Coffee, Building, Receipt, AlertTriangle, Gauge, List, Rocket } from 'lucide-react';

const API_BASE = window.location.origin + '/api/b2b';

const sections = [
  { id: 'overview', icon: BookOpen },
  { id: 'quickstart', icon: Rocket },
  { id: 'auth', icon: Key },
  { id: 'errors', icon: AlertTriangle },
  { id: 'ratelimits', icon: Gauge },
  { id: 'pagination', icon: List },
  { id: 'content', icon: Hotel },
  { id: 'availability', icon: Calendar },
  { id: 'rates', icon: DollarSign },
  { id: 'reservations', icon: FileText },
  { id: 'guests', icon: Users },
  { id: 'loyalty', icon: Sparkles },
  { id: 'housekeeping', icon: ClipboardList },
  { id: 'kbs', icon: Shield },
  { id: 'identity', icon: Fingerprint },
  { id: 'lostfound', icon: Package },
  { id: 'wakeup', icon: Phone },
  { id: 'journey', icon: Globe },
  { id: 'concierge', icon: Coffee },
  { id: 'spa', icon: Zap },
  { id: 'groups', icon: Building },
  { id: 'folio', icon: Receipt },
  { id: 'webhooks', icon: Bell },
];

const navLabels = {
  en: {
    overview: 'Overview', quickstart: 'Quick Start', auth: 'Authentication', errors: 'Error Codes',
    ratelimits: 'Rate Limits', pagination: 'Pagination', content: 'Content', availability: 'Availability',
    rates: 'Rates', reservations: 'Reservations', guests: 'Guests', loyalty: 'Loyalty Program',
    housekeeping: 'Housekeeping', kbs: 'KBS / Police', identity: 'Passport / ID',
    lostfound: 'Lost & Found', wakeup: 'Wake-up Calls', journey: 'Guest Journey',
    concierge: 'Concierge', spa: 'Spa & Wellness', groups: 'MICE & Groups',
    folio: 'Folio & Billing', webhooks: 'Webhooks',
  },
  tr: {
    overview: 'Genel Bakis', quickstart: 'Hızlı Baslangic', auth: 'Kimlik Dogrulama', errors: 'Hata Kodlari',
    ratelimits: 'İstek Limitleri', pagination: 'Sayfalama', content: 'Icerik', availability: 'Musaitlik',
    rates: 'Fiyatlar', reservations: 'Rezervasyonlar', guests: 'Misafirler', loyalty: 'Sadakat Programi',
    housekeeping: 'Kat Hizmetleri', kbs: 'KBS / Emniyet', identity: 'Pasaport / Kimlik',
    lostfound: 'Kayip Esya', wakeup: 'Uyandırma', journey: 'Misafir Yolculugu',
    concierge: 'Concierge', spa: 'Spa & Wellness', groups: 'MICE & Grup',
    folio: 'Folio & Fatura', webhooks: 'Webhook\'lar',
  },
};

const t_labels = { en: { required: 'required', optional: 'optional' }, tr: { required: 'zorunlu', optional: 'opsiyonel' } };

const CodeBlock = ({ code, lang = 'bash' }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500); };
  return (
    <div className="relative group rounded-lg overflow-hidden border border-slate-700 bg-[#0d1117]">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-slate-700">
        <span className="text-xs text-slate-400 font-mono">{lang}</span>
        <button onClick={handleCopy} className="text-xs text-slate-400 hover:text-white transition flex items-center gap-1">
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-sm leading-relaxed"><code className="text-slate-200 font-mono text-[13px]">{code}</code></pre>
    </div>
  );
};

const ParamTable = ({ params, lang }) => (
  <div className="overflow-x-auto rounded-lg border border-slate-200">
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-slate-50 border-b border-slate-200">
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Parameter</th>
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Type</th>
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Required</th>
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Description</th>
        </tr>
      </thead>
      <tbody>
        {params.map((p, i) => (
          <tr key={p.name} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
            <td className="px-4 py-2.5 font-mono text-[13px] text-emerald-700">{p.name}</td>
            <td className="px-4 py-2.5 text-slate-500 font-mono text-[13px]">{p.type}</td>
            <td className="px-4 py-2.5">
              {p.required
                ? <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">{t_labels[lang].required}</span>
                : <span className="text-xs text-slate-400">{t_labels[lang].optional}</span>
              }
            </td>
            <td className="px-4 py-2.5 text-slate-600">{p.desc}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const MethodBadge = ({ method }) => {
  const colors = {
    GET: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    POST: 'bg-blue-100 text-blue-800 border-blue-200',
    PUT: 'bg-amber-100 text-amber-800 border-amber-200',
    DELETE: 'bg-red-100 text-red-800 border-red-200',
  };
  return <span className={`inline-block px-2.5 py-1 rounded font-mono text-xs font-bold border ${colors[method] || 'bg-slate-100 text-slate-700'}`}>{method}</span>;
};

const EndpointBlock = ({ method, path, desc, children }) => (
  <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
    <div className="flex items-center gap-3 px-4 py-3 bg-slate-50 border-b border-slate-200">
      <MethodBadge method={method} />
      <code className="text-sm font-mono text-slate-800">{path}</code>
    </div>
    {desc && <p className="px-5 pt-3 text-sm text-slate-500">{desc}</p>}
    {children && <div className="p-5 space-y-4">{children}</div>}
  </div>
);

const SectionHeader = ({ icon: Icon, title, id }) => (
  <h2 id={id} className="text-2xl font-bold text-slate-900 flex items-center gap-3 pt-8 pb-2 scroll-mt-20" style={{ fontFamily: 'Manrope, sans-serif' }}>
    <div className="w-9 h-9 rounded-lg bg-[#C09D63]/10 flex items-center justify-center">
      <Icon size={18} className="text-[#C09D63]" />
    </div>
    {title}
  </h2>
);

const SubTitle = ({ children }) => <h3 className="text-lg font-semibold text-slate-800 mb-2">{children}</h3>;

const Desc = ({ children }) => <p className="text-slate-600 leading-relaxed mt-3">{children}</p>;

export default function B2BApiDocs() {
  const [lang, setLang] = useState('en');
  const [activeSection, setActiveSection] = useState('overview');
  const [urlCopied, setUrlCopied] = useState(false);
  const nl = navLabels[lang];

  useEffect(() => {
    const handleScroll = () => {
      const ids = sections.map(s => s.id);
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= 120) setActiveSection(id);
      }
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollTo = (id) => { const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  const isEn = lang === 'en';

  return (
    <div className="min-h-screen bg-white" data-testid="b2b-api-docs">
      <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet" />

      <header className="fixed top-0 left-0 right-0 z-50 bg-slate-900 border-b border-slate-700/50 h-14">
        <div className="flex items-center justify-between h-full px-6 max-w-[1600px] mx-auto">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-md bg-[#C09D63] flex items-center justify-center"><Code size={14} className="text-white" /></div>
              <span className="text-white font-bold text-lg" style={{ fontFamily: 'Manrope, sans-serif' }}>Syroce Open API</span>
            </div>
            <span className="hidden md:block text-slate-400 text-sm border-l border-slate-600 pl-4 ml-2">
              {isEn ? 'Complete PMS Integration Documentation' : 'Kapsamli PMS Entegrasyon Dokumantasyonu'}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => { navigator.clipboard.writeText(window.location.origin + '/b2b/docs'); setUrlCopied(true); setTimeout(() => setUrlCopied(false), 2000); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all border border-slate-600"
              title={isEn ? 'Copy documentation URL' : 'Dokümantasyon linkini kopyala'}
            >
              {urlCopied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
              <span className="hidden sm:inline">{urlCopied ? (isEn ? 'Copied!' : 'Kopyalandi!') : (isEn ? 'Copy Link' : 'Link Kopyala')}</span>
            </button>
            <div className="flex items-center bg-slate-800 rounded-lg p-0.5">
              <button onClick={() => setLang('en')} className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${lang === 'en' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-white'}`}>EN</button>
              <button onClick={() => setLang('tr')} className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${lang === 'tr' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-white'}`}>TR</button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex pt-14">
        <aside className="hidden lg:block fixed left-0 top-14 bottom-0 w-60 bg-slate-50 border-r border-slate-200 overflow-y-auto">
          <nav className="py-4 px-3">
            <div className="space-y-0.5">
              {sections.map(({ id, icon: Icon }) => (
                <button key={id} onClick={() => scrollTo(id)} className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2.5 transition-all ${activeSection === id ? 'bg-white shadow-sm border border-slate-200 text-slate-900 font-semibold' : 'text-slate-500 hover:text-slate-800 hover:bg-white/60'}`}>
                  <Icon size={14} className={activeSection === id ? 'text-[#C09D63]' : 'text-slate-400'} />
                  <span className="truncate">{nl[id]}</span>
                </button>
              ))}
            </div>
          </nav>
        </aside>

        <main className="flex-1 lg:ml-60 min-h-screen">
          <div className="max-w-4xl mx-auto px-6 md:px-10 py-10 space-y-12">

            {/* ── OVERVIEW ── */}
            <section id="overview">
              <SectionHeader icon={BookOpen} title={isEn ? 'Getting Started' : 'Baslangic'} id="overview-h" />
              <Desc>{isEn
                ? 'The Syroce Open API provides complete access to all hotel PMS modules — reservations, guest management, loyalty programs, housekeeping, KBS police notifications, passport/ID scanning, lost & found, wake-up calls, guest journey, concierge, spa, MICE/groups, folio/billing, and real-time webhooks. All through a single API with API key authentication.'
                : 'Syroce Open API, tüm otel PMS modullerine tam erişim saglar — rezervasyon, misafir yönetimi, sadakat programlari, kat hizmetleri, KBS emniyet bildirimleri, pasaport/kimlik okuma, kayip esya, uyandırma servisi, misafir yolculugu, concierge, spa, MICE/grup, folio/fatura ve gerçek zamanlı webhook\'lar. Tek bir API key ile tüm işlemler.'
              }</Desc>

              <div className="mt-6 space-y-4">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">{isEn ? 'Base URL' : 'Temel URL'}</h3>
                <CodeBlock code={API_BASE} lang="url" />
              </div>

              <div className="mt-8">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">{isEn ? 'Available Modules (19 API Groups)' : 'Mevcut Moduller (19 API Grubu)'}</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {sections.filter(s => s.id !== 'overview').map(({ id, icon: Icon }) => (
                    <button key={id} onClick={() => scrollTo(id)} className="flex items-center gap-3 text-sm text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-white rounded-lg px-4 py-3 border border-slate-200 transition text-left">
                      <Icon size={16} className="text-[#C09D63] shrink-0" />
                      {nl[id]}
                      <ChevronRight size={14} className="ml-auto text-slate-300" />
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-8">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">{isEn ? 'Response Format' : 'Yanit Formati'}</h3>
                <CodeBlock lang="json" code={`// Success\n{ "ok": true, "data": {...} }\n\n// Error\n{ "detail": "Error message" }`} />
              </div>
            </section>

            {/* ── QUICK START ── */}
            <section id="quickstart">
              <SectionHeader icon={Rocket} title={isEn ? 'Quick Start Guide' : 'Hızlı Baslangic Rehberi'} id="qs-h" />
              <Desc>{isEn
                ? 'Follow these steps to start integrating with the Syroce Open API in minutes. From getting your API key to making your first reservation.'
                : 'Syroce Open API ile dakikalar icinde entegrasyona baslayin. API key almaktan ilk rezervasyonunuzu yapmaya kadar adim adim rehber.'
              }</Desc>

              <div className="mt-8 space-y-6">
                <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#C09D63] flex items-center justify-center text-white font-bold text-sm shrink-0">1</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-slate-900">{isEn ? 'Get Your API Key' : 'API Key Alin'}</h4>
                      <p className="text-sm text-slate-600 mt-1">{isEn
                        ? 'Your hotel partner creates an API key for your agency through the Syroce PMS admin panel:'
                        : 'Otel ortağınız Syroce PMS yönetim panelinden acente API key\'inizi oluşturur:'
                      }</p>
                      <div className="mt-3 space-y-2 text-sm text-slate-600">
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">a.</span> {isEn ? 'Hotel admin navigates to Travel Agent Management (Acente Yönetimi)' : 'Otel yöneticisi Acente Yönetimi sayfasina gider'}</div>
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">b.</span> {isEn ? 'Selects your agency and clicks "Generate API Key"' : 'Acentenizi secer ve "API Key Olustur" butonuna tiklar'}</div>
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">c.</span> {isEn ? 'The key (starting with syroce_b2b_) is shown ONCE — copy it immediately' : 'Key (syroce_b2b_ ile baslar) sadece BIR KEZ gosterilir — hemen kopyalayin'}</div>
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">d.</span> {isEn ? 'Store the key securely (environment variable, secrets manager)' : 'Key\'i guvenli saklayin (ortam degiskeni, secrets manager)'}</div>
                      </div>
                      <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
                        <p className="text-xs text-amber-800 flex items-center gap-1.5">
                          <AlertTriangle size={13} className="shrink-0" />
                          {isEn ? 'The raw API key is only shown at creation time. If lost, the hotel admin must regenerate it (POST /api/b2b/api-keys/{agency_id}/regenerate). This invalidates the old key.' : 'Ham API key sadece olusturulurken gosterilir. Kaybederseniz otel yöneticisi yenilemek zorundadir (POST /api/b2b/api-keys/{agency_id}/regenerate). Eski key geçersiz olur.'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#C09D63] flex items-center justify-center text-white font-bold text-sm shrink-0">2</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-slate-900">{isEn ? 'Test Your Connection' : 'Baglantinizi Test Edin'}</h4>
                      <p className="text-sm text-slate-600 mt-1">{isEn ? 'Make your first API call to verify the key works:' : 'Key\'in çalıştığını doğrulamak için ilk API çağrınızı yapin:'}</p>
                      <div className="mt-3">
                        <CodeBlock lang="bash" code={`curl -X GET "${API_BASE}/content" \\\n  -H "X-API-Key: syroce_b2b_YOUR_KEY_HERE"\n\n# Expected: 200 OK with hotel content\n# If 401: Check your key is correct and active\n# If 403: Your agency account may be inactive`} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#C09D63] flex items-center justify-center text-white font-bold text-sm shrink-0">3</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-slate-900">{isEn ? 'Check Availability & Rates' : 'Musaitlik ve Fiyat Sorgulayın'}</h4>
                      <div className="mt-3">
                        <CodeBlock lang="bash" code={`# Check room availability\ncurl "${API_BASE}/availability?check_in=2026-07-01&check_out=2026-07-03" \\\n  -H "X-API-Key: syroce_b2b_YOUR_KEY_HERE"\n\n# Get rates for date range\ncurl "${API_BASE}/rates?start_date=2026-07-01&end_date=2026-07-03" \\\n  -H "X-API-Key: syroce_b2b_YOUR_KEY_HERE"`} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#C09D63] flex items-center justify-center text-white font-bold text-sm shrink-0">4</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-slate-900">{isEn ? 'Create Your First Reservation' : 'Ilk Rezervasyonunuzu Olusturun'}</h4>
                      <div className="mt-3">
                        <CodeBlock lang="bash" code={`curl -X POST "${API_BASE}/reservations" \\\n  -H "X-API-Key: syroce_b2b_YOUR_KEY_HERE" \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "room_type": "Deluxe Double",\n    "check_in": "2026-07-01",\n    "check_out": "2026-07-03",\n    "guest_name": "John Doe",\n    "guest_email": "john@example.com",\n    "guest_phone": "+905551234567",\n    "adults": 2,\n    "children": 0\n  }'\n\n# Response includes confirmation_code, room_number, total_amount`} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#C09D63] flex items-center justify-center text-white font-bold text-sm shrink-0">5</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-slate-900">{isEn ? 'Set Up Webhooks (Optional)' : 'Webhook Kurun (Opsiyonel)'}</h4>
                      <p className="text-sm text-slate-600 mt-1">{isEn ? 'Receive real-time notifications when reservations change:' : 'Rezervasyonlar degistiginde gerçek zamanlı bildirim alin:'}</p>
                      <div className="mt-3">
                        <CodeBlock lang="bash" code={`curl -X POST "${API_BASE}/webhooks" \\\n  -H "X-API-Key: syroce_b2b_YOUR_KEY_HERE" \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "url": "https://your-system.com/webhook/syroce",\n    "events": ["reservation.created", "reservation.cancelled", "reservation.updated"],\n    "secret": "your_webhook_signing_secret"\n  }'`} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-6">
                  <h4 className="font-semibold text-emerald-900 mb-3">{isEn ? 'Complete Integration Example (Python)' : 'Tam Entegrasyon Ornegi (Python)'}</h4>
                  <CodeBlock lang="python" code={`import requests\n\nAPI_KEY = "syroce_b2b_YOUR_KEY_HERE"  # Store in env variable!\nBASE_URL = "${API_BASE}"\nHEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}\n\nclass SyroceClient:\n    def __init__(self):\n        self.session = requests.Session()\n        self.session.headers.update(HEADERS)\n\n    def check_availability(self, check_in, check_out, room_type=None):\n        params = {"check_in": check_in, "check_out": check_out}\n        if room_type:\n            params["room_type"] = room_type\n        resp = self.session.get(f"{BASE_URL}/availability", params=params)\n        resp.raise_for_status()\n        return resp.json()\n\n    def create_reservation(self, room_type, check_in, check_out,\n                           guest_name, guest_email="", guest_phone=""):\n        body = {\n            "room_type": room_type,\n            "check_in": check_in,\n            "check_out": check_out,\n            "guest_name": guest_name,\n            "guest_email": guest_email,\n            "guest_phone": guest_phone,\n        }\n        resp = self.session.post(f"{BASE_URL}/reservations", json=body)\n        resp.raise_for_status()\n        return resp.json()\n\n    def get_reservations(self, status=None, limit=50):\n        params = {"limit": limit}\n        if status:\n            params["status"] = status\n        resp = self.session.get(f"{BASE_URL}/reservations", params=params)\n        resp.raise_for_status()\n        return resp.json()\n\n    def cancel_reservation(self, reservation_id):\n        resp = self.session.put(f"{BASE_URL}/reservations/{reservation_id}/cancel")\n        resp.raise_for_status()\n        return resp.json()\n\n    def search_guests(self, query):\n        resp = self.session.get(f"{BASE_URL}/guests/search", params={"q": query})\n        resp.raise_for_status()\n        return resp.json()\n\n# Usage\nclient = SyroceClient()\navail = client.check_availability("2026-07-01", "2026-07-03")\nprint(f"Available rooms: {len(avail['room_types'])}")\n\nbooking = client.create_reservation(\n    "Deluxe Double", "2026-07-01", "2026-07-03",\n    "John Doe", "john@example.com"\n)\nprint(f"Booked! Code: {booking['reservation']['confirmation_code']}")`} />
                </div>

                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-6">
                  <h4 className="font-semibold text-emerald-900 mb-3">{isEn ? 'Complete Integration Example (JavaScript/Node.js)' : 'Tam Entegrasyon Ornegi (JavaScript/Node.js)'}</h4>
                  <CodeBlock lang="javascript" code={`const API_KEY = process.env.SYROCE_API_KEY; // Store in env variable!\nconst BASE_URL = "${API_BASE}";\n\nclass SyroceClient {\n  constructor() {\n    this.headers = {\n      "X-API-Key": API_KEY,\n      "Content-Type": "application/json"\n    };\n  }\n\n  async request(method, path, options = {}) {\n    const url = new URL(BASE_URL + path);\n    if (options.params) {\n      Object.entries(options.params).forEach(([k, v]) =>\n        url.searchParams.set(k, v)\n      );\n    }\n    const res = await fetch(url, {\n      method,\n      headers: this.headers,\n      body: options.body ? JSON.stringify(options.body) : undefined\n    });\n    if (!res.ok) {\n      const err = await res.json().catch(() => ({}));\n      throw new Error(err.detail || \`HTTP \${res.status}\`);\n    }\n    return res.json();\n  }\n\n  checkAvailability(checkIn, checkOut, roomType) {\n    const params = { check_in: checkIn, check_out: checkOut };\n    if (roomType) params.room_type = roomType;\n    return this.request("GET", "/availability", { params });\n  }\n\n  createReservation(data) {\n    return this.request("POST", "/reservations", { body: data });\n  }\n\n  getReservations(status, limit = 50) {\n    const params = { limit };\n    if (status) params.status = status;\n    return this.request("GET", "/reservations", { params });\n  }\n\n  cancelReservation(id) {\n    return this.request("PUT", \`/reservations/\${id}/cancel\`);\n  }\n\n  searchGuests(query) {\n    return this.request("GET", "/guests/search", { params: { q: query } });\n  }\n}\n\n// Usage\nconst client = new SyroceClient();\nconst avail = await client.checkAvailability("2026-07-01", "2026-07-03");\nconsole.log(\`Available: \${avail.room_types.length} types\`);\n\nconst booking = await client.createReservation({\n  room_type: "Deluxe Double",\n  check_in: "2026-07-01",\n  check_out: "2026-07-03",\n  guest_name: "John Doe",\n  guest_email: "john@example.com"\n});\nconsole.log(\`Booked! Code: \${booking.reservation.confirmation_code}\`);`} />
                </div>
              </div>
            </section>

            {/* ── AUTH ── */}
            <section id="auth">
              <SectionHeader icon={Key} title={isEn ? 'Authentication' : 'Kimlik Dogrulama'} id="auth-h" />
              <Desc>{isEn ? 'All API endpoints require an API key in the X-API-Key header. Keys are issued by the hotel administrator through the PMS admin panel.' : 'Tüm API endpoint\'leri X-API-Key başlığında bir API key gerektirir. Key\'ler otel yöneticisi tarafından PMS yönetim panelinden verilir.'}</Desc>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Header Format' : 'Baslik Formati'}</SubTitle>
                <CodeBlock lang="http" code="X-API-Key: syroce_b2b_your_api_key_here" />
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'API Key Format' : 'API Key Formati'}</SubTitle>
                <p className="text-sm text-slate-600 mb-3">{isEn
                  ? 'All API keys start with the prefix syroce_b2b_ followed by a random string. Example:'
                  : 'Tüm API key\'ler syroce_b2b_ on eki ile baslar, ardindan rastgele bir dizi gelir. Ornek:'
                }</p>
                <CodeBlock lang="text" code="syroce_b2b_zMskjN7H0K4xPq2B1wR9fY3eT6uI8oL" />
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'API Key Lifecycle' : 'API Key Yasam Dongusu'}</SubTitle>
                <div className="overflow-x-auto rounded-lg border border-slate-200 mt-3">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Action' : 'İşlem'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Who' : 'Kim'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Endpoint</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Auth' : 'Yetki'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { action: isEn ? 'Create key' : 'Key oluştur', who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi', ep: 'POST /api/b2b/api-keys?agency_id=...', auth: 'JWT' },
                        { action: isEn ? 'View key info' : 'Key bilgisi gor', who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi', ep: 'GET /api/b2b/api-keys/{agency_id}', auth: 'JWT' },
                        { action: isEn ? 'Regenerate key' : 'Key yenile', who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi', ep: 'POST /api/b2b/api-keys/{agency_id}/regenerate', auth: 'JWT' },
                        { action: isEn ? 'Revoke key' : 'Key iptal', who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi', ep: 'DELETE /api/b2b/api-keys/{agency_id}', auth: 'JWT' },
                      ].map((r, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.action}</td>
                          <td className="px-4 py-2.5 text-slate-500">{r.who}</td>
                          <td className="px-4 py-2.5 font-mono text-[12px] text-emerald-700">{r.ep}</td>
                          <td className="px-4 py-2.5"><span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-medium">{r.auth}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-slate-500 mt-2">{isEn
                  ? 'Note: Key management endpoints require JWT authentication (hotel admin login), not API key auth. Only the hotel admin can create, view, regenerate, or revoke API keys.'
                  : 'Not: Key yönetim endpoint\'leri JWT kimlik doğrulama (otel admin girisi) gerektirir, API key değil. Sadece otel yöneticisi API key oluşturabilir, görüntüleyebilir, yenileyebilir veya iptal edebilir.'
                }</p>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Usage Examples' : 'Kullanim Ornekleri'}</SubTitle>
                <div className="space-y-3">
                  <CodeBlock lang="bash" code={`curl -X GET "${API_BASE}/availability?check_in=2026-06-01&check_out=2026-06-03" \\\n  -H "X-API-Key: syroce_b2b_your_api_key_here"`} />
                  <CodeBlock lang="python" code={`import requests\n\nheaders = {"X-API-Key": "syroce_b2b_your_api_key_here"}\nresp = requests.get("${API_BASE}/availability",\n    headers=headers,\n    params={"check_in": "2026-06-01", "check_out": "2026-06-03"})\nprint(resp.json())`} />
                  <CodeBlock lang="javascript" code={`const res = await fetch("${API_BASE}/availability?check_in=2026-06-01&check_out=2026-06-03", {\n  headers: { "X-API-Key": "syroce_b2b_your_api_key_here" }\n});\nconst data = await res.json();`} />
                </div>
              </div>

              <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-5">
                <h4 className="font-semibold text-blue-900 flex items-center gap-2 text-sm"><Shield size={15} /> {isEn ? 'Security Best Practices' : 'Güvenlik En İyi Uygulamaları'}</h4>
                <ul className="text-sm text-blue-800 mt-2 space-y-1.5 list-disc pl-5">
                  <li>{isEn ? 'Keys are SHA-256 hashed on the server — never stored in plaintext' : 'Key\'ler sunucuda SHA-256 ile hashlenir — asla duz metin saklanmaz'}</li>
                  <li>{isEn ? 'Each key is scoped to a single agency and hotel tenant' : 'Her key tek bir acenteye ve otel tenant\'ina baglidir'}</li>
                  <li>{isEn ? 'Store your key in environment variables — never hardcode in source code' : 'Key\'inizi ortam degiskenlerinde saklayin — kaynak koduna asla yazmayIn'}</li>
                  <li>{isEn ? 'Keys can be revoked or rotated by the hotel at any time' : 'Key\'ler otel tarafından her zaman iptal edilebilir veya dondurulebilir'}</li>
                  <li>{isEn ? 'Usage is tracked: request count, last used time, and IP address' : 'Kullanim takip edilir: istek sayısı, son kullanım zamani ve IP adresi'}</li>
                  <li>{isEn ? 'Use HTTPS in production — never send API keys over unencrypted connections' : 'Uretimde HTTPS kullanin — API key\'leri sifrelenmemis baglantilarda gondermeyin'}</li>
                  <li>{isEn ? 'Rotate keys periodically using the regenerate endpoint' : 'Key\'leri periyodik olarak yenileme endpoint\'i ile dondurun'}</li>
                </ul>
              </div>
            </section>

            {/* ── ERROR CODES ── */}
            <section id="errors">
              <SectionHeader icon={AlertTriangle} title={isEn ? 'Error Codes Reference' : 'Hata Kodlari Referansi'} id="err-h" />
              <Desc>{isEn
                ? 'The API uses standard HTTP status codes. Error responses include a detail field with a human-readable message.'
                : 'API standart HTTP durum kodlarini kullanir. Hata yanitlari okunabilir bir mesaj iceren detail alani icerir.'
              }</Desc>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Error Response Format' : 'Hata Yanit Formati'}</SubTitle>
                <CodeBlock lang="json" code={`{\n  "detail": "Geçersiz veya devre dışı API key"\n}`} />
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'HTTP Status Codes' : 'HTTP Durum Kodlari'}</SubTitle>
                <div className="overflow-x-auto rounded-lg border border-slate-200 mt-3">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700 w-24">{isEn ? 'Code' : 'Kod'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700 w-40">{isEn ? 'Status' : 'Durum'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Description' : 'Açıklama'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Example' : 'Ornek'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { code: '200', status: 'OK', color: 'emerald', desc: isEn ? 'Request succeeded' : 'İstek basarili', example: isEn ? 'Data returned successfully' : 'Veri basariyla dondu' },
                        { code: '201', status: 'Created', color: 'emerald', desc: isEn ? 'Resource created' : 'Kaynak oluşturuldu', example: isEn ? 'Reservation created' : 'Rezervasyon oluşturuldu' },
                        { code: '400', status: 'Bad Request', color: 'amber', desc: isEn ? 'Invalid request data' : 'Geçersiz istek verisi', example: isEn ? 'Invalid date format, missing required field, invalid enum value' : 'Geçersiz tarih formatı, eksik zorunlu alan, geçersiz enum değeri' },
                        { code: '401', status: 'Unauthorized', color: 'red', desc: isEn ? 'Invalid or missing API key' : 'Geçersiz veya eksik API key', example: '"Geçersiz veya devre dışı API key"' },
                        { code: '403', status: 'Forbidden', color: 'red', desc: isEn ? 'API key valid but access denied' : 'API key geçerli ama erişim reddedildi', example: isEn ? 'Agency account inactive' : 'Acente hesabı aktif değil' },
                        { code: '404', status: 'Not Found', color: 'amber', desc: isEn ? 'Resource not found' : 'Kaynak bulunamadı', example: isEn ? 'Reservation, guest, or room not found' : 'Rezervasyon, misafir veya oda bulunamadı' },
                        { code: '409', status: 'Conflict', color: 'amber', desc: isEn ? 'Resource conflict' : 'Kaynak çatışması', example: isEn ? 'No available rooms for the selected dates' : 'Seçilen tarihler için müsait oda yok' },
                        { code: '422', status: 'Validation Error', color: 'amber', desc: isEn ? 'Request body validation failed' : 'İstek govdesi doğrulama hatası', example: isEn ? 'Negative amount, zero points, date in past' : 'Negatif tutar, sifir puan, gecmis tarih' },
                        { code: '429', status: 'Too Many Requests', color: 'red', desc: isEn ? 'Rate limit exceeded' : 'İstek limiti asildi', example: isEn ? 'Retry after the specified time' : 'Belirtilen sureden sonra tekrar deneyin' },
                        { code: '500', status: 'Server Error', color: 'red', desc: isEn ? 'Internal server error' : 'Sunucu hatası', example: isEn ? 'Contact support if persistent' : 'Devam ederse destek ile iletisime gecin' },
                      ].map((r, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5"><span className={`font-mono font-bold text-${r.color}-700`}>{r.code}</span></td>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.status}</td>
                          <td className="px-4 py-2.5 text-slate-600">{r.desc}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs">{r.example}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Common Error Examples' : 'Yaygin Hata Ornekleri'}</SubTitle>
                <div className="space-y-3">
                  <CodeBlock lang="json" code={`// 401 — Invalid API Key\n{"detail": "Geçersiz veya devre dışı API key"}\n\n// 403 — Agency Inactive\n{"detail": "Acente hesabı aktif değil"}\n\n// 400 — Bad Request\n{"detail": "check_out, check_in'den sonra olmalı"}\n{"detail": "Geçersiz durum. Geçerli: clean, dirty, inspected, maintenance, out_of_order"}\n{"detail": "operation must be 'add' or 'subtract'"}\n\n// 404 — Not Found\n{"detail": "Rezervasyon bulunamadı"}\n{"detail": "Misafir bulunamadı"}\n{"detail": "Oda bulunamadı"}\n\n// 409 — No Availability\n{"detail": "Bu tarihler ve oda tipi için müsait oda yok"}\n\n// 422 — Validation Error (Pydantic)\n{"detail": [{"loc": ["body", "amount"], "msg": "Input should be greater than 0", "type": "greater_than"}]}`} />
                </div>
              </div>

              <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-5">
                <h4 className="font-semibold text-blue-900 text-sm">{isEn ? 'Error Handling Best Practice' : 'Hata Yönetimi En İyi Uygulama'}</h4>
                <CodeBlock lang="python" code={`import requests\n\ntry:\n    resp = requests.post(f"{BASE_URL}/reservations",\n        headers=headers, json=data, timeout=30)\n    resp.raise_for_status()\n    result = resp.json()\nexcept requests.exceptions.HTTPError as e:\n    error_body = e.response.json()\n    if e.response.status_code == 401:\n        print("API key invalid — check or regenerate")\n    elif e.response.status_code == 409:\n        print(f"No availability: {error_body['detail']}")\n    elif e.response.status_code == 422:\n        print(f"Validation error: {error_body['detail']}")\n    else:\n        print(f"Error {e.response.status_code}: {error_body}")\nexcept requests.exceptions.Timeout:\n    print("Request timed out — retry with backoff")\nexcept requests.exceptions.ConnectionError:\n    print("Connection failed — check network")`} />
              </div>
            </section>

            {/* ── RATE LIMITS ── */}
            <section id="ratelimits">
              <SectionHeader icon={Gauge} title={isEn ? 'Rate Limits' : 'İstek Limitleri'} id="rl-h" />
              <Desc>{isEn
                ? 'API requests are rate-limited per API key to ensure fair usage and system stability. Limits vary by endpoint type.'
                : 'API istekleri, adil kullanım ve sistem kararlılığı için API key basina sınırlandırılmıştır. Limitler endpoint tipine göre değişir.'
              }</Desc>

              <div className="mt-6">
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Endpoint Type' : 'Endpoint Tipi'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Rate Limit' : 'İstek Limiti'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Window' : 'Pencere'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Examples' : 'Ornekler'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { type: isEn ? 'Read (GET)' : 'Okuma (GET)', limit: '120', window: isEn ? 'per minute' : 'dakika basina', ex: 'availability, rates, reservations list, guests' },
                        { type: isEn ? 'Write (POST/PUT)' : 'Yazma (POST/PUT)', limit: '30', window: isEn ? 'per minute' : 'dakika basina', ex: 'create reservation, loyalty points, folio charge' },
                        { type: isEn ? 'Delete (DELETE)' : 'Silme (DELETE)', limit: '10', window: isEn ? 'per minute' : 'dakika basina', ex: 'cancel wake-up, delete webhook' },
                        { type: isEn ? 'Bulk Operations' : 'Toplu Islemler', limit: '5', window: isEn ? 'per minute' : 'dakika basina', ex: 'rooming-list upload, KBS report' },
                      ].map((r, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.type}</td>
                          <td className="px-4 py-2.5"><span className="font-mono font-bold text-[#C09D63]">{r.limit}</span> {isEn ? 'requests' : 'istek'}</td>
                          <td className="px-4 py-2.5 text-slate-500">{r.window}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs font-mono">{r.ex}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Rate Limit Headers' : 'İstek Limiti Basliklari'}</SubTitle>
                <p className="text-sm text-slate-600 mb-3">{isEn
                  ? 'Every API response includes headers showing your current rate limit status:'
                  : 'Her API yaniti mevcut istek limiti durumunuzu gosteren basliklar icerir:'
                }</p>
                <CodeBlock lang="http" code={`X-RateLimit-Limit: 120\nX-RateLimit-Remaining: 115\nX-RateLimit-Reset: 1719835260`} />
                <div className="mt-3 space-y-1.5 text-sm text-slate-600">
                  <div><code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded font-mono">X-RateLimit-Limit</code> — {isEn ? 'Maximum requests allowed in the window' : 'Penceredeki maksimum istek sayısı'}</div>
                  <div><code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded font-mono">X-RateLimit-Remaining</code> — {isEn ? 'Remaining requests in current window' : 'Mevcut pencerede kalan istek sayısı'}</div>
                  <div><code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded font-mono">X-RateLimit-Reset</code> — {isEn ? 'Unix timestamp when the window resets' : 'Pencerenin sifirlanacagi Unix zaman damgasi'}</div>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Handling 429 Too Many Requests' : '429 Cok Fazla İstek Yönetimi'}</SubTitle>
                <CodeBlock lang="python" code={`import time\nimport requests\n\ndef api_call_with_retry(url, headers, max_retries=3):\n    for attempt in range(max_retries):\n        resp = requests.get(url, headers=headers)\n        if resp.status_code == 429:\n            retry_after = int(resp.headers.get("Retry-After", 60))\n            print(f"Rate limited. Retrying in {retry_after}s...")\n            time.sleep(retry_after)\n            continue\n        return resp\n    raise Exception("Max retries exceeded")`} />
              </div>
            </section>

            {/* ── PAGINATION ── */}
            <section id="pagination">
              <SectionHeader icon={List} title={isEn ? 'Pagination & Filtering' : 'Sayfalama & Filtreleme'} id="pag-h" />
              <Desc>{isEn
                ? 'List endpoints support limit-based pagination and various filters. All list responses include a count field.'
                : 'Liste endpoint\'leri limit tabanli sayfalama ve cesitli filtreler destekler. Tüm liste yanitlari bir count alani icerir.'
              }</Desc>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Pagination Parameters' : 'Sayfalama Parametreleri'}</SubTitle>
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Parameter</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Type</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Default' : 'Varsayilan'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Description' : 'Açıklama'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { name: 'limit', type: 'integer', def: isEn ? 'Varies (20-100)' : 'Degisir (20-100)', desc: isEn ? 'Maximum number of results to return' : 'Dondurulecek maksimum sonuc sayısı' },
                        { name: 'status', type: 'string', def: isEn ? 'All statuses' : 'Tüm durumlar', desc: isEn ? 'Filter by status (varies per endpoint)' : 'Duruma göre filtre (endpoint\'e göre değişir)' },
                        { name: 'date', type: 'string', def: isEn ? 'Today' : 'Bugün', desc: isEn ? 'Filter by date (YYYY-MM-DD)' : 'Tarihe göre filtre (YYYY-MM-DD)' },
                      ].map((p, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-mono text-[13px] text-emerald-700">{p.name}</td>
                          <td className="px-4 py-2.5 text-slate-500 font-mono text-[13px]">{p.type}</td>
                          <td className="px-4 py-2.5 text-slate-500">{p.def}</td>
                          <td className="px-4 py-2.5 text-slate-600">{p.desc}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Response Structure' : 'Yanit Yapisi'}</SubTitle>
                <p className="text-sm text-slate-600 mb-3">{isEn
                  ? 'All list endpoints return data in a consistent format with a count field:'
                  : 'Tüm liste endpoint\'leri verileri count alaniyla tutarli bir formatta dondurur:'
                }</p>
                <CodeBlock lang="json" code={`// GET /api/b2b/reservations?status=confirmed&limit=50\n{\n  "reservations": [\n    { "id": "abc...", "guest_name": "John Doe", ... },\n    { "id": "def...", "guest_name": "Jane Smith", ... }\n  ],\n  "count": 2\n}\n\n// GET /api/b2b/wake-up-calls?date=2026-07-01\n{\n  "wake_up_calls": [...],\n  "count": 5\n}\n\n// GET /api/b2b/lost-found?status=found&category=electronics\n{\n  "items": [...],\n  "count": 3\n}`} />
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Limits per Endpoint' : 'Endpoint Basina Limitler'}</SubTitle>
                <div className="overflow-x-auto rounded-lg border border-slate-200 mt-3">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">Endpoint</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Default Limit' : 'Varsayilan Limit'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Max Limit' : 'Maks Limit'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Available Filters' : 'Mevcut Filtreler'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { ep: '/reservations', def: '100', max: '500', filters: 'status, check_in_from, check_in_to' },
                        { ep: '/guests/search', def: '20', max: '100', filters: 'q (search query)' },
                        { ep: '/guests/{id}/stays', def: '50', max: '200', filters: '-' },
                        { ep: '/housekeeping/rooms', def: '500', max: '500', filters: 'status, floor' },
                        { ep: '/kbs/guests', def: '100', max: '500', filters: 'date, status' },
                        { ep: '/lost-found', def: '50', max: '200', filters: 'status, category' },
                        { ep: '/wake-up-calls', def: '200', max: '200', filters: 'date, status' },
                        { ep: '/guest-journey/requests', def: '50', max: '200', filters: 'booking_id, status, request_type' },
                        { ep: '/groups', def: '50', max: '200', filters: 'status' },
                      ].map((r, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-mono text-[12px] text-emerald-700">{r.ep}</td>
                          <td className="px-4 py-2.5 text-slate-700">{r.def}</td>
                          <td className="px-4 py-2.5 text-slate-700">{r.max}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs font-mono">{r.filters}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Date & Time Formats' : 'Tarih & Saat Formatlari'}</SubTitle>
                <div className="overflow-x-auto rounded-lg border border-slate-200 mt-3">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Type' : 'Tip'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Format' : 'Format'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Example' : 'Ornek'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Used In' : 'Kullanildigi Yer'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { type: isEn ? 'Date' : 'Tarih', format: 'YYYY-MM-DD', example: '2026-07-15', used: 'check_in, check_out, wake_date, preferred_date' },
                        { type: isEn ? 'Time' : 'Saat', format: 'HH:MM', example: '07:30', used: 'wake_time, preferred_time, arrival_time' },
                        { type: isEn ? 'Timestamp' : 'Zaman Damgasi', format: 'ISO 8601', example: '2026-07-15T14:30:00+00:00', used: 'created_at, updated_at (response only)' },
                      ].map((r, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.type}</td>
                          <td className="px-4 py-2.5 font-mono text-[13px] text-emerald-700">{r.format}</td>
                          <td className="px-4 py-2.5 font-mono text-[13px] text-slate-600">{r.example}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs">{r.used}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>

            {/* ── CONTENT ── */}
            <section id="content">
              <SectionHeader icon={Hotel} title={isEn ? 'Content API' : 'Icerik API'} id="content-h" />
              <Desc>{isEn ? 'Retrieve hotel content including room types, services, and property information.' : 'Oda tipleri, hizmetler ve tesis bilgileri dahil otel icerigini getirin.'}</Desc>
              <div className="mt-6">
                <EndpointBlock method="GET" path="/api/b2b/content" desc={isEn ? 'No parameters required.' : 'Parametre gerektirmez.'}>
                  <CodeBlock lang="json" code={`{\n  "published": true,\n  "hotel_content": {\n    "hotel_name": "Grand Palace Hotel",\n    "star_rating": 5,\n    "room_types": [...],\n    "services": [...]\n  }\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── AVAILABILITY ── */}
            <section id="availability">
              <SectionHeader icon={Calendar} title={isEn ? 'Availability API' : 'Musaitlik API'} id="avail-h" />
              <Desc>{isEn ? 'Check real-time room availability for specified dates.' : 'Belirtilen tarihler için gerçek zamanlı oda müsaitliğini kontrol edin.'}</Desc>
              <div className="mt-6">
                <EndpointBlock method="GET" path="/api/b2b/availability">
                  <ParamTable lang={lang} params={[
                    { name: 'check_in', type: 'string', required: true, desc: isEn ? 'Check-in date (YYYY-MM-DD)' : 'Giriş tarihi (YYYY-MM-DD)' },
                    { name: 'check_out', type: 'string', required: true, desc: isEn ? 'Check-out date (YYYY-MM-DD)' : 'Çıkış tarihi (YYYY-MM-DD)' },
                    { name: 'room_type', type: 'string', required: false, desc: isEn ? 'Filter by room type' : 'Oda tipine göre filtre' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "check_in": "2026-06-01",\n  "check_out": "2026-06-03",\n  "room_types": [\n    { "room_type": "Deluxe Double", "capacity": 3, "base_price": 250.00,\n      "total_rooms": 10, "available_rooms": 6 }\n  ]\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── RATES ── */}
            <section id="rates">
              <SectionHeader icon={DollarSign} title={isEn ? 'Rates API' : 'Fiyat API'} id="rates-h" />
              <Desc>{isEn ? 'Fetch agency-specific or base hotel rates for a date range.' : 'Acenteye özel veya temel otel fiyatlarini cekin.'}</Desc>
              <div className="mt-6">
                <EndpointBlock method="GET" path="/api/b2b/rates">
                  <ParamTable lang={lang} params={[
                    { name: 'start_date', type: 'string', required: true, desc: isEn ? 'Start date (YYYY-MM-DD)' : 'Baslangic tarihi (YYYY-MM-DD)' },
                    { name: 'end_date', type: 'string', required: true, desc: isEn ? 'End date (YYYY-MM-DD)' : 'Bitis tarihi (YYYY-MM-DD)' },
                    { name: 'room_type', type: 'string', required: false, desc: isEn ? 'Filter by room type' : 'Oda tipine göre filtre' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "source": "agency_rates",\n  "rates": [\n    { "date": "2026-06-01", "room_type_code": "DLX",\n      "single": 200, "double": 250, "triple": 300 }\n  ]\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── RESERVATIONS ── */}
            <section id="reservations">
              <SectionHeader icon={FileText} title={isEn ? 'Reservations API' : 'Rezervasyon API'} id="res-h" />
              <Desc>{isEn ? 'Create, list, view, and cancel reservations. All bookings automatically sync with PMS.' : 'Rezervasyon oluşturun, listeleyin, görüntüleyin ve iptal edin. Otomatik PMS senkronizasyonu.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/reservations" desc={isEn ? 'Create a reservation with auto room assignment' : 'Otomatik oda atamali rezervasyon oluştur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'room_type', type: 'string', required: true, desc: isEn ? 'Room type name' : 'Oda tipi adi' },
                    { name: 'check_in', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'check_out', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'guest_name', type: 'string', required: true, desc: isEn ? 'Full guest name' : 'Misafir tam adi' },
                    { name: 'guest_email', type: 'string', required: false, desc: isEn ? 'Guest email' : 'E-posta' },
                    { name: 'guest_phone', type: 'string', required: false, desc: isEn ? 'Guest phone' : 'Telefon' },
                    { name: 'adults', type: 'int', required: false, desc: isEn ? 'Adults (default: 2)' : 'Yetiskin (varsayilan: 2)' },
                    { name: 'children', type: 'int', required: false, desc: isEn ? 'Children (default: 0)' : 'Cocuk (varsayilan: 0)' },
                    { name: 'total_amount', type: 'number', required: false, desc: isEn ? 'Total price (0 = auto)' : 'Toplam fiyat (0 = otomatik)' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "reservation": {\n    "id": "a1b2c3d4-...",\n    "confirmation_code": "B2B-A1B2C3D4",\n    "status": "confirmed",\n    "commission_rate": 12,\n    "commission_amount": 90.00\n  }\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/reservations" desc={isEn ? 'List reservations with filters' : 'Filtreyle rezervasyon listele'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: false, desc: 'confirmed, cancelled, checked_in, checked_out' },
                    { name: 'check_in_from', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'check_in_to', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'limit', type: 'int', required: false, desc: isEn ? 'Max results (default 100, max 500)' : 'Maks sonuc (varsayilan 100, maks 500)' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/reservations/{reservation_id}" desc={isEn ? 'Get reservation by ID or confirmation code' : 'ID veya onay kodu ile rezervasyon detayi'} />
                <EndpointBlock method="PUT" path="/api/b2b/reservations/{reservation_id}/cancel" desc={isEn ? 'Cancel a reservation' : 'Rezervasyon iptal et'} />
              </div>
            </section>

            {/* ── GUESTS ── */}
            <section id="guests">
              <SectionHeader icon={Users} title={isEn ? 'Guest Management' : 'Misafir Yönetimi'} id="guests-h" />
              <Desc>{isEn ? 'Search guests, view profiles, and access stay history.' : 'Misafir arayin, profilleri görüntüleyin ve konaklama gecmisine erişin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/guests/search?q={query}" desc={isEn ? 'Search by name, email, or phone (min 2 chars)' : 'Isim, e-posta veya telefon ile arama (min 2 karakter)'}>
                  <ParamTable lang={lang} params={[
                    { name: 'q', type: 'string', required: true, desc: isEn ? 'Search query (name, email, phone)' : 'Arama sorgusu (isim, e-posta, telefon)' },
                    { name: 'limit', type: 'int', required: false, desc: isEn ? 'Max results (default 20)' : 'Maks sonuc (varsayilan 20)' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "guests": [\n    { "id": "g1...", "name": "John Doe", "email": "john@example.com",\n      "phone": "+90555...", "vip_status": true, "loyalty_points": 5200 }\n  ],\n  "count": 1\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/guests/{guest_id}" desc={isEn ? 'Get full guest profile' : 'Tam misafir profili'} />
                <EndpointBlock method="GET" path="/api/b2b/guests/{guest_id}/stays" desc={isEn ? 'Get guest stay history' : 'Misafir konaklama gecmisi'}>
                  <ParamTable lang={lang} params={[
                    { name: 'limit', type: 'int', required: false, desc: isEn ? 'Max results (default 50)' : 'Maks sonuc (varsayilan 50)' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── LOYALTY ── */}
            <section id="loyalty">
              <SectionHeader icon={Sparkles} title={isEn ? 'Loyalty Program' : 'Sadakat Programi'} id="loyalty-h" />
              <Desc>{isEn ? 'Manage guest loyalty points, tiers, and VIP status. Tiers: Bronze (0+), Silver (2000+), Gold (5000+), Platinum (10000+).' : 'Misafir sadakat puanlarini, seviyeleri ve VIP durumunu yönetin. Seviyeler: Bronze (0+), Silver (2000+), Gold (5000+), Platinum (10000+).'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/guests/{guest_id}/loyalty" desc={isEn ? 'Get loyalty status and points' : 'Sadakat durumu ve puan bilgisi'}>
                  <CodeBlock lang="json" code={`{\n  "guest_id": "g1...",\n  "guest_name": "John Doe",\n  "loyalty_points": 5200,\n  "loyalty_tier": "gold",\n  "vip_status": true,\n  "total_stays": 12,\n  "total_spend": 45000.00\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/guests/{guest_id}/loyalty/points" desc={isEn ? 'Add or subtract loyalty points' : 'Sadakat puani ekle veya cikar'}>
                  <ParamTable lang={lang} params={[
                    { name: 'points', type: 'int', required: true, desc: isEn ? 'Points amount' : 'Puan miktari' },
                    { name: 'reason', type: 'string', required: true, desc: isEn ? 'Reason for the change' : 'Degisiklik nedeni' },
                    { name: 'operation', type: 'string', required: false, desc: isEn ? '"add" (default) or "subtract"' : '"add" (varsayilan) veya "subtract"' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "previous_points": 5200,\n  "new_points": 5700,\n  "new_tier": "gold"\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── HOUSEKEEPING ── */}
            <section id="housekeeping">
              <SectionHeader icon={ClipboardList} title={isEn ? 'Housekeeping' : 'Kat Hizmetleri'} id="hk-h" />
              <Desc>{isEn ? 'Query and update room cleaning status. Integrate with housekeeping management systems.' : 'Oda temizlik durumlarini sorgulama ve güncelleme. Kat hizmeti sistemleriyle entegrasyon.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/housekeeping/rooms" desc={isEn ? 'List rooms with cleaning status' : 'Odalar ve temizlik durumlarini listele'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: false, desc: 'clean, dirty, inspected, maintenance, out_of_order' },
                    { name: 'floor', type: 'string', required: false, desc: isEn ? 'Filter by floor' : 'Kata göre filtre' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="PUT" path="/api/b2b/housekeeping/rooms/{room_id}" desc={isEn ? 'Update room cleaning status' : 'Oda temizlik durumu guncelle'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: true, desc: 'clean, dirty, inspected, maintenance, out_of_order' },
                    { name: 'notes', type: 'string', required: false, desc: isEn ? 'Optional notes' : 'Opsiyonel notlar' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── KBS ── */}
            <section id="kbs">
              <SectionHeader icon={Shield} title={isEn ? 'KBS / Police Notification' : 'KBS / Emniyet Bildirimi'} id="kbs-h" />
              <Desc>{isEn ? 'Access guest registration data for KBS (police notification system). List checked-in guests with identity information and submit reports.' : 'KBS (emniyet bildirim sistemi) için misafir kayıt verilerine erişin. Check-in yapan misafirleri kimlik bilgileriyle listeleyin ve rapor gönderin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/kbs/guests" desc={isEn ? 'Get guests for KBS reporting with identity data' : 'KBS bildirimi için misafir listesi ve kimlik bilgileri'}>
                  <ParamTable lang={lang} params={[
                    { name: 'date', type: 'string', required: false, desc: isEn ? 'Date (YYYY-MM-DD, default: today)' : 'Tarih (YYYY-MM-DD, varsayilan: bugün)' },
                    { name: 'status', type: 'string', required: false, desc: 'pending, submitted, confirmed, error' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "date": "2026-06-01",\n  "guests": [\n    { "id": "b1...", "guest_name": "Ali Yilmaz", "room_number": "302",\n      "check_in": "2026-06-01T14:00:00", "nationality": "TR",\n      "id_number": "12345678901", "passport_number": "",\n      "birth_date": "1985-03-15", "gender": "M" }\n  ],\n  "guest_count": 1,\n  "reports": [],\n  "report_count": 0\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/kbs/report" desc={isEn ? 'Submit a KBS report' : 'KBS bildirimi oluştur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'date', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'guest_ids', type: 'array', required: false, desc: isEn ? 'List of guest/booking IDs' : 'Misafir/rezervasyon ID listesi' },
                    { name: 'notes', type: 'string', required: false, desc: isEn ? 'Report notes' : 'Rapor notlari' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/kbs/report/{report_id}" desc={isEn ? 'Get KBS report detail' : 'KBS rapor detayi'} />
              </div>
            </section>

            {/* ── IDENTITY / PASSPORT ── */}
            <section id="identity">
              <SectionHeader icon={Fingerprint} title={isEn ? 'Passport / ID Scanning' : 'Pasaport / Kimlik Okuma'} id="id-h" />
              <Desc>{isEn ? 'Submit passport/ID OCR scan results and query guest identity data. Supports passport, ID card, and driving license. Auto-updates guest profile with scanned data.' : 'Pasaport/kimlik OCR tarama sonuclarini gönderin ve misafir kimlik verilerini sorgulayIn. Pasaport, kimlik karti ve ehliyet destegi. Taranan veriler otomatik misafir profiline yansir.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/identity/scan" desc={isEn ? 'Submit OCR scan data — auto-updates guest profile' : 'OCR tarama verisini gönderin — misafir profili otomatik guncellenir'}>
                  <ParamTable lang={lang} params={[
                    { name: 'guest_id', type: 'string', required: true, desc: isEn ? 'Guest ID' : 'Misafir ID' },
                    { name: 'scan_type', type: 'string', required: true, desc: 'passport, id_card, driving_license' },
                    { name: 'document_number', type: 'string', required: true, desc: isEn ? 'Document number' : 'Belge numarasi' },
                    { name: 'first_name', type: 'string', required: true, desc: isEn ? 'First name from document' : 'Belgedeki ad' },
                    { name: 'last_name', type: 'string', required: true, desc: isEn ? 'Last name from document' : 'Belgedeki soyad' },
                    { name: 'nationality', type: 'string', required: false, desc: isEn ? 'Nationality code (TR, DE, US...)' : 'Ülke kodu (TR, DE, US...)' },
                    { name: 'birth_date', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'gender', type: 'string', required: false, desc: 'M, F' },
                    { name: 'expiry_date', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'issuing_country', type: 'string', required: false, desc: isEn ? 'Issuing country' : 'Veren ulke' },
                    { name: 'mrz_line1', type: 'string', required: false, desc: 'MRZ Line 1' },
                    { name: 'mrz_line2', type: 'string', required: false, desc: 'MRZ Line 2' },
                    { name: 'scan_quality', type: 'number', required: false, desc: isEn ? 'Quality score 0-100 (auto-verify if >= 80)' : 'Kalite skoru 0-100 (>=80 otomatik doğrulama)' },
                    { name: 'raw_ocr_data', type: 'object', required: false, desc: isEn ? 'Raw OCR JSON data' : 'Ham OCR JSON verisi' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "scan": {\n    "id": "s1...",\n    "scan_type": "passport",\n    "document_number": "U12345678",\n    "verified": true,\n    "scan_quality": 92.5\n  }\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/identity/guest/{guest_id}" desc={isEn ? 'Get guest identity data and scan history' : 'Misafir kimlik bilgisi ve tarama gecmisi'} />
              </div>
            </section>

            {/* ── LOST & FOUND ── */}
            <section id="lostfound">
              <SectionHeader icon={Package} title={isEn ? 'Lost & Found' : 'Kayip Esya'} id="lf-h" />
              <Desc>{isEn ? 'Manage lost and found items — register, update status, link to guests.' : 'Kayip ve bulunan esyalari yönetin — kaydedIn, durum guncelleyin, misafirlere baglayin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/lost-found" desc={isEn ? 'List items with filters' : 'Filtreli esya listesi'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: false, desc: 'found, claimed, returned, disposed' },
                    { name: 'category', type: 'string', required: false, desc: isEn ? 'Item category' : 'Esya kategorisi' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/lost-found" desc={isEn ? 'Register a found item' : 'Bulunan esya kaydet'}>
                  <ParamTable lang={lang} params={[
                    { name: 'item_name', type: 'string', required: true, desc: isEn ? 'Item name' : 'Esya adi' },
                    { name: 'description', type: 'string', required: false, desc: isEn ? 'Description' : 'Açıklama' },
                    { name: 'category', type: 'string', required: false, desc: isEn ? 'Category (electronics, clothing, jewelry, documents, other)' : 'Kategori (elektronik, giyim, muceviher, belge, diger)' },
                    { name: 'location_found', type: 'string', required: false, desc: isEn ? 'Where found' : 'Bulundugu yer' },
                    { name: 'room_number', type: 'string', required: false, desc: isEn ? 'Room number' : 'Oda numarasi' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="PUT" path="/api/b2b/lost-found/{item_id}" desc={isEn ? 'Update item status' : 'Esya durumu guncelle'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: false, desc: 'found, claimed, returned, disposed' },
                    { name: 'claimed_by', type: 'string', required: false, desc: isEn ? 'Claimed by (guest name)' : 'Teslim alan (misafir adi)' },
                    { name: 'notes', type: 'string', required: false, desc: isEn ? 'Notes' : 'Notlar' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── WAKE-UP CALLS ── */}
            <section id="wakeup">
              <SectionHeader icon={Phone} title={isEn ? 'Wake-up Calls' : 'Uyandırma Servisi'} id="wu-h" />
              <Desc>{isEn ? 'Create and manage wake-up call requests for guests.' : 'Misafirler için uyandırma talepleri oluşturun ve yönetin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/wake-up-calls" desc={isEn ? 'List wake-up calls' : 'Uyandırma listesi'}>
                  <ParamTable lang={lang} params={[
                    { name: 'date', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'status', type: 'string', required: false, desc: 'pending, completed, cancelled, missed' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/wake-up-calls" desc={isEn ? 'Create wake-up call' : 'Uyandırma oluştur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'room_number', type: 'string', required: true, desc: isEn ? 'Room number' : 'Oda numarasi' },
                    { name: 'guest_name', type: 'string', required: true, desc: isEn ? 'Guest name' : 'Misafir adi' },
                    { name: 'wake_date', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'wake_time', type: 'string', required: true, desc: 'HH:MM' },
                    { name: 'recurring', type: 'boolean', required: false, desc: isEn ? 'Repeat daily' : 'Her gün tekrarla' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="PUT" path="/api/b2b/wake-up-calls/{call_id}" desc={isEn ? 'Update wake-up call' : 'Uyandırma guncelle'} />
                <EndpointBlock method="DELETE" path="/api/b2b/wake-up-calls/{call_id}" desc={isEn ? 'Cancel wake-up call' : 'Uyandırma iptal'} />
              </div>
            </section>

            {/* ── GUEST JOURNEY ── */}
            <section id="journey">
              <SectionHeader icon={Globe} title={isEn ? 'Guest Journey' : 'Misafir Yolculugu'} id="gj-h" />
              <Desc>{isEn ? 'Online check-in, pre-arrival management, and guest service requests.' : 'Online check-in, pre-arrival yönetimi ve misafir servis talepleri.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/guest-journey/online-checkin" desc={isEn ? 'Submit online check-in data' : 'Online check-in bilgilerini gonder'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: true, desc: isEn ? 'Booking ID' : 'Rezervasyon ID' },
                    { name: 'arrival_time', type: 'string', required: false, desc: isEn ? 'Expected arrival time' : 'Beklenen varis zamani' },
                    { name: 'flight_number', type: 'string', required: false, desc: isEn ? 'Flight number' : 'Ucus numarasi' },
                    { name: 'passport_number', type: 'string', required: false, desc: isEn ? 'Passport number (auto-updates guest)' : 'Pasaport no (otomatik profil gunceller)' },
                    { name: 'nationality', type: 'string', required: false, desc: isEn ? 'Nationality code' : 'Uyruk kodu' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/guest-journey/pre-arrival/{booking_id}" desc={isEn ? 'Get pre-arrival status' : 'Pre-arrival durumu sorgula'} />
                <EndpointBlock method="POST" path="/api/b2b/guest-journey/request" desc={isEn ? 'Create a service request' : 'Servis talebi oluştur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: true, desc: isEn ? 'Booking ID' : 'Rezervasyon ID' },
                    { name: 'request_type', type: 'string', required: true, desc: 'concierge, spa, room_service, maintenance, transport, other' },
                    { name: 'description', type: 'string', required: true, desc: isEn ? 'Request description' : 'Talep aciklamasi' },
                    { name: 'priority', type: 'string', required: false, desc: 'low, normal, high, urgent' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/guest-journey/requests" desc={isEn ? 'List service requests with filters' : 'Servis taleplerini filtreli listele'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: false, desc: isEn ? 'Filter by booking' : 'Rezervasyona göre filtre' },
                    { name: 'status', type: 'string', required: false, desc: 'pending, in_progress, completed, cancelled' },
                    { name: 'request_type', type: 'string', required: false, desc: isEn ? 'Filter by type' : 'Tipe göre filtre' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── CONCIERGE ── */}
            <section id="concierge">
              <SectionHeader icon={Coffee} title={isEn ? 'Concierge Services' : 'Concierge Hizmetleri'} id="con-h" />
              <Desc>{isEn ? 'Browse available concierge services and create service requests.' : 'Mevcut concierge hizmetlerini görüntüleyin ve talep oluşturun.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/concierge/services" desc={isEn ? 'List available concierge services' : 'Mevcut concierge hizmetlerini listele'}>
                  <CodeBlock lang="json" code={`{\n  "services": [\n    { "id": "transfer", "name": "Airport Transfer",\n      "name_tr": "Havaalani Transferi", "category": "transport",\n      "price_range": "50-150" },\n    { "id": "restaurant", "name": "Restaurant Reservation",\n      "name_tr": "Restoran Rezervasyonu", "category": "dining" }\n  ]\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/concierge/request" desc={isEn ? 'Create a concierge request' : 'Concierge talebi oluştur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: true, desc: isEn ? 'Booking ID' : 'Rezervasyon ID' },
                    { name: 'service_id', type: 'string', required: true, desc: isEn ? 'Service ID from /concierge/services' : '/concierge/services\'ten gelen hizmet ID' },
                    { name: 'description', type: 'string', required: false, desc: isEn ? 'Additional details' : 'Ek detaylar' },
                    { name: 'preferred_date', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'preferred_time', type: 'string', required: false, desc: 'HH:MM' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── SPA ── */}
            <section id="spa">
              <SectionHeader icon={Zap} title={isEn ? 'Spa & Wellness' : 'Spa & Wellness'} id="spa-h" />
              <Desc>{isEn ? 'Browse spa services and create spa bookings for guests.' : 'Spa hizmetlerini görüntüleyin ve misafirler için spa randevusu oluşturun.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/spa/services" desc={isEn ? 'List spa services with prices' : 'Spa hizmetleri ve fiyat listesi'}>
                  <CodeBlock lang="json" code={`{\n  "services": [\n    { "id": "massage_60", "name": "Swedish Massage 60min",\n      "name_tr": "Isvec Masaji 60dk", "category": "massage",\n      "duration": 60, "price": 120 },\n    { "id": "hammam", "name": "Turkish Hammam",\n      "name_tr": "Turk Hamami", "category": "bath",\n      "duration": 75, "price": 100 }\n  ]\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/spa/booking" desc={isEn ? 'Create spa booking' : 'Spa randevusu oluştur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: true, desc: isEn ? 'Hotel booking ID' : 'Otel rezervasyon ID' },
                    { name: 'service_id', type: 'string', required: true, desc: isEn ? 'Service ID from /spa/services' : '/spa/services\'ten gelen hizmet ID' },
                    { name: 'preferred_date', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'preferred_time', type: 'string', required: true, desc: 'HH:MM' },
                    { name: 'guest_count', type: 'int', required: false, desc: isEn ? 'Number of guests (default: 1)' : 'Misafir sayısı (varsayilan: 1)' },
                    { name: 'notes', type: 'string', required: false, desc: isEn ? 'Special requests' : 'Özel istekler' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── MICE & GROUPS ── */}
            <section id="groups">
              <SectionHeader icon={Building} title={isEn ? 'MICE & Groups' : 'MICE & Grup Yönetimi'} id="grp-h" />
              <Desc>{isEn ? 'Manage group blocks, rooming lists, and MICE events (conferences, weddings, corporate events).' : 'Grup bloklari, rooming listleri ve MICE etkinliklerini (konferans, dugun, kurumsal) yönetin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/groups" desc={isEn ? 'List group blocks' : 'Grup bloklari listele'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: false, desc: 'tentative, confirmed, cancelled' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/groups/block" desc={isEn ? 'Create a group block' : 'Grup blok oluştur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'group_name', type: 'string', required: true, desc: isEn ? 'Group/event name' : 'Grup/etkinlik adi' },
                    { name: 'contact_name', type: 'string', required: true, desc: isEn ? 'Contact person' : 'Irtibat kisisi' },
                    { name: 'check_in', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'check_out', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'rooms_requested', type: 'int', required: true, desc: isEn ? 'Number of rooms needed' : 'Gereken oda sayısı' },
                    { name: 'event_type', type: 'string', required: false, desc: 'conference, wedding, corporate, tour_group, other' },
                    { name: 'room_type', type: 'string', required: false, desc: isEn ? 'Preferred room type' : 'Tercih edilen oda tipi' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "block": {\n    "id": "blk1...",\n    "group_name": "Tech Conference 2026",\n    "rooms_requested": 50,\n    "rooms_picked_up": 0,\n    "status": "tentative"\n  }\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/groups/{block_id}" desc={isEn ? 'Get block details with rooming list' : 'Blok detayi ve rooming list'} />
                <EndpointBlock method="POST" path="/api/b2b/groups/{block_id}/rooming-list" desc={isEn ? 'Upload bulk guest list — creates reservations automatically' : 'Toplu misafir listesi yukle — otomatik rezervasyon oluşturur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'guests', type: 'array', required: true, desc: isEn ? 'Array of guest entries' : 'Misafir kayitlari dizisi' },
                    { name: 'guests[].guest_name', type: 'string', required: true, desc: isEn ? 'Guest full name' : 'Misafir tam adi' },
                    { name: 'guests[].room_type', type: 'string', required: false, desc: isEn ? 'Override room type' : 'Oda tipi (override)' },
                    { name: 'guests[].check_in', type: 'string', required: false, desc: isEn ? 'Override check-in (default: block dates)' : 'Giriş tarihi (varsayilan: blok tarihi)' },
                    { name: 'guests[].check_out', type: 'string', required: false, desc: isEn ? 'Override check-out' : 'Çıkış tarihi' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "created_count": 3,\n  "reservations": [\n    { "guest_name": "Alice Johnson",\n      "booking_id": "b1...",\n      "confirmation_code": "GRP-B1A2C3D4" }\n  ]\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── FOLIO & BILLING ── */}
            <section id="folio">
              <SectionHeader icon={Receipt} title={isEn ? 'Folio & Billing' : 'Folio & Fatura'} id="fol-h" />
              <Desc>{isEn ? 'View guest folios, post charges, and generate invoices.' : 'Misafir foliolarini görüntüleyin, masraf ekleyin ve fatura oluşturun.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/folio/{booking_id}" desc={isEn ? 'Get folio with all charges and payments' : 'Tüm masraf ve odemelerle folio getir'}>
                  <CodeBlock lang="json" code={`{\n  "booking": { "guest_name": "John Doe", "room_number": "302" },\n  "charges": [\n    { "charge_type": "room", "description": "Room charge",\n      "amount": 250.00 },\n    { "charge_type": "minibar", "description": "Minibar",\n      "amount": 35.00 }\n  ],\n  "payments": [\n    { "amount": 250.00, "method": "credit_card" }\n  ],\n  "total_charges": 285.00,\n  "total_payments": 250.00,\n  "balance": 35.00\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/folio/{booking_id}/charge" desc={isEn ? 'Post a charge to the folio' : 'Folioya masraf ekle'}>
                  <ParamTable lang={lang} params={[
                    { name: 'charge_type', type: 'string', required: true, desc: 'room, minibar, restaurant, spa, laundry, phone, other' },
                    { name: 'description', type: 'string', required: true, desc: isEn ? 'Charge description' : 'Masraf aciklamasi' },
                    { name: 'amount', type: 'number', required: true, desc: isEn ? 'Unit price' : 'Birim fiyat' },
                    { name: 'quantity', type: 'int', required: false, desc: isEn ? 'Quantity (default: 1)' : 'Adet (varsayilan: 1)' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/folio/{booking_id}/invoice" desc={isEn ? 'Generate invoice (JSON format)' : 'Fatura oluştur (JSON formatında)'}>
                  <CodeBlock lang="json" code={`{\n  "invoice_number": "INV-A1B2C3D4",\n  "invoice_date": "2026-06-03",\n  "hotel": { "hotel_name": "Grand Palace", "tax_number": "123..." },\n  "guest_name": "John Doe",\n  "check_in": "2026-06-01", "check_out": "2026-06-03",\n  "charges": [...],\n  "subtotal": 535.00,\n  "total_paid": 500.00,\n  "balance_due": 35.00,\n  "currency": "TRY"\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── WEBHOOKS ── */}
            <section id="webhooks">
              <SectionHeader icon={Bell} title="Webhooks" id="wh-h" />
              <Desc>{isEn ? 'Receive real-time notifications when events occur. Register webhook URLs and Syroce will POST event data with retry and dead-letter queue support.' : 'Olaylar gerceklestiginde gerçek zamanlı bildirimler alin. Webhook URL\'si kaydedin, Syroce olay verisini retry ve dead-letter queue destegi ile POST edecektir.'}</Desc>

              <div className="mt-6">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">{isEn ? 'Supported Events' : 'Desteklenen Olaylar'}</h3>
                <div className="space-y-2">
                  {[
                    { name: 'reservation.created', desc: isEn ? 'New reservation created' : 'Yeni rezervasyon oluşturuldu' },
                    { name: 'reservation.cancelled', desc: isEn ? 'Reservation cancelled' : 'Rezervasyon iptal edildi' },
                    { name: 'reservation.updated', desc: isEn ? 'Reservation status changed' : 'Rezervasyon durumu degisti' },
                  ].map(ev => (
                    <div key={ev.name} className="flex items-center gap-3 bg-slate-50 rounded-lg px-4 py-3 border border-slate-200">
                      <code className="text-xs font-mono bg-white px-2 py-1 rounded border border-slate-200 text-[#C09D63] font-semibold">{ev.name}</code>
                      <span className="text-sm text-slate-600">{ev.desc}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-8 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/webhooks" desc={isEn ? 'Register webhook' : 'Webhook kaydet'}>
                  <ParamTable lang={lang} params={[
                    { name: 'url', type: 'string', required: true, desc: isEn ? 'HTTPS endpoint URL' : 'HTTPS endpoint URL' },
                    { name: 'events', type: 'array', required: true, desc: isEn ? 'Event types to subscribe' : 'Abone olunacak olay tipleri' },
                    { name: 'secret', type: 'string', required: false, desc: isEn ? 'Signing secret for HMAC verification' : 'HMAC dogrulamasi için imzalama anahtari' },
                  ]} />
                  <CodeBlock lang="bash" code={`curl -X POST "${API_BASE}/webhooks" \\\n  -H "X-API-Key: syroce_b2b_your_key" \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "url": "https://your-app.com/webhook",\n    "events": ["reservation.created", "reservation.cancelled"],\n    "secret": "your_signing_secret"\n  }'`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/webhooks" desc={isEn ? 'List your webhooks' : 'Webhook listesi'} />
                <EndpointBlock method="DELETE" path="/api/b2b/webhooks/{webhook_id}" desc={isEn ? 'Delete webhook' : 'Webhook sil'} />
                <EndpointBlock method="POST" path="/api/b2b/webhooks/{webhook_id}/test" desc={isEn ? 'Send test event' : 'Test olayi gonder'} />

                <div className="mt-6">
                  <SubTitle>{isEn ? 'Webhook Payload' : 'Webhook Payload'}</SubTitle>
                  <CodeBlock lang="json" code={`{\n  "event": "reservation.created",\n  "timestamp": "2026-06-01T14:30:00+00:00",\n  "delivery_id": "d1e2f3a4-...",\n  "idempotency_key": "abc123...",\n  "data": {\n    "reservation_id": "a1b2c3d4-...",\n    "confirmation_code": "B2B-A1B2C3D4",\n    "status": "confirmed",\n    "guest_name": "John Doe",\n    "total_amount": 750.00\n  }\n}`} />
                </div>

                <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 mt-4">
                  <h4 className="font-semibold text-amber-900 flex items-center gap-2 text-sm">
                    <Shield size={15} /> {isEn ? 'Signature Verification' : 'Imza Dogrulama'}
                  </h4>
                  <p className="text-sm text-amber-800 mt-2">{isEn ? 'If you provide a secret, each delivery includes X-Webhook-Signature header. Verify with HMAC-SHA256:' : 'Secret belirlerseniz her teslimat X-Webhook-Signature basligini icerir. HMAC-SHA256 ile doğrulayın:'}</p>
                  <div className="mt-3">
                    <CodeBlock lang="python" code={`import hmac, hashlib\n\ndef verify_signature(body, secret, sig_header):\n    expected = hmac.new(\n        secret.encode(), body, hashlib.sha256\n    ).hexdigest()\n    return hmac.compare_digest(f"sha256={expected}", sig_header)`} />
                  </div>
                </div>
              </div>
            </section>

            <div className="border-t border-slate-200 pt-8 pb-16 text-center">
              <p className="text-sm text-slate-400">Syroce Open API v2.0 &middot; 22 {isEn ? 'Documentation Sections' : 'Dokumantasyon Bolumu'} &middot; 19 {isEn ? 'API Groups' : 'API Grubu'} &middot; {new Date().getFullYear()}</p>
              <p className="text-xs text-slate-300 mt-1">{isEn ? 'API Version: v1 (stable) — No breaking changes without version bump' : 'API Versiyon: v1 (stabil) — Versiyon degisikligi olmadan kirilma degisikligi yapilmaz'}</p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
