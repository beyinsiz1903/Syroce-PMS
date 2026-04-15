import { useState, useEffect } from 'react';
import { BookOpen, Key, Search, Hotel, Calendar, DollarSign, FileText, Bell, ChevronRight, Globe, Copy, Check, ArrowLeft, Code, Shield, Zap, Users, Sparkles, ClipboardList, CreditCard, Fingerprint, Package, Phone, Coffee, Building, Receipt } from 'lucide-react';

const API_BASE = window.location.origin + '/api/b2b';

const sections = [
  { id: 'overview', icon: BookOpen },
  { id: 'auth', icon: Key },
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
    overview: 'Overview', auth: 'Authentication', content: 'Content', availability: 'Availability',
    rates: 'Rates', reservations: 'Reservations', guests: 'Guests', loyalty: 'Loyalty Program',
    housekeeping: 'Housekeeping', kbs: 'KBS / Police', identity: 'Passport / ID',
    lostfound: 'Lost & Found', wakeup: 'Wake-up Calls', journey: 'Guest Journey',
    concierge: 'Concierge', spa: 'Spa & Wellness', groups: 'MICE & Groups',
    folio: 'Folio & Billing', webhooks: 'Webhooks',
  },
  tr: {
    overview: 'Genel Bakis', auth: 'Kimlik Dogrulama', content: 'Icerik', availability: 'Musaitlik',
    rates: 'Fiyatlar', reservations: 'Rezervasyonlar', guests: 'Misafirler', loyalty: 'Sadakat Programi',
    housekeeping: 'Kat Hizmetleri', kbs: 'KBS / Emniyet', identity: 'Pasaport / Kimlik',
    lostfound: 'Kayip Esya', wakeup: 'Uyandirma', journey: 'Misafir Yolculugu',
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
                : 'Syroce Open API, tum otel PMS modullerine tam erisim saglar — rezervasyon, misafir yonetimi, sadakat programlari, kat hizmetleri, KBS emniyet bildirimleri, pasaport/kimlik okuma, kayip esya, uyandirma servisi, misafir yolculugu, concierge, spa, MICE/grup, folio/fatura ve gercek zamanli webhook\'lar. Tek bir API key ile tum islemler.'
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

            {/* ── AUTH ── */}
            <section id="auth">
              <SectionHeader icon={Key} title={isEn ? 'Authentication' : 'Kimlik Dogrulama'} id="auth-h" />
              <Desc>{isEn ? 'All API endpoints require an API key. Include your key in the X-API-Key header:' : 'Tum API endpoint\'leri bir API key gerektirir. Key\'inizi X-API-Key basligina ekleyin:'}</Desc>
              <div className="mt-4"><CodeBlock lang="http" code="X-API-Key: syroce_b2b_your_api_key_here" /></div>
              <div className="mt-4">
                <CodeBlock lang="bash" code={`curl -X GET "${API_BASE}/availability?check_in=2026-06-01&check_out=2026-06-03" \\\n  -H "X-API-Key: syroce_b2b_your_api_key_here"`} />
              </div>
              <div className="mt-4">
                <CodeBlock lang="python" code={`import requests\n\nAPI_KEY = "syroce_b2b_your_api_key_here"\nBASE = "${API_BASE}"\nheaders = {"X-API-Key": API_KEY}\n\n# Check availability\nresp = requests.get(f"{BASE}/availability",\n    headers=headers,\n    params={"check_in": "2026-06-01", "check_out": "2026-06-03"})\nprint(resp.json())`} />
              </div>
              <div className="mt-4">
                <CodeBlock lang="javascript" code={`const API_KEY = "syroce_b2b_your_api_key_here";\nconst BASE = "${API_BASE}";\n\nconst res = await fetch(\`\${BASE}/availability?check_in=2026-06-01&check_out=2026-06-03\`, {\n  headers: { "X-API-Key": API_KEY }\n});\nconst data = await res.json();\nconsole.log(data);`} />
              </div>
              <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-5">
                <h4 className="font-semibold text-blue-900 flex items-center gap-2 text-sm"><Shield size={15} /> {isEn ? 'Security Notes' : 'Guvenlik Notlari'}</h4>
                <ul className="text-sm text-blue-800 mt-2 space-y-1 list-disc pl-5">
                  <li>{isEn ? 'Keys are SHA-256 hashed — never stored in plaintext' : 'Key\'ler SHA-256 ile hashlenir — asla duz metin saklanmaz'}</li>
                  <li>{isEn ? 'Each key is scoped to a single agency and hotel tenant' : 'Her key tek bir acenteye ve otel tenant\'ina baglidir'}</li>
                  <li>{isEn ? 'Keys can be revoked or rotated by the hotel at any time' : 'Key\'ler otel tarafindan her zaman iptal edilebilir'}</li>
                  <li>{isEn ? 'Usage is tracked (request count, last used timestamp)' : 'Kullanim takip edilir (istek sayisi, son kullanim zamani)'}</li>
                </ul>
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
              <Desc>{isEn ? 'Check real-time room availability for specified dates.' : 'Belirtilen tarihler icin gercek zamanli oda musaitligini kontrol edin.'}</Desc>
              <div className="mt-6">
                <EndpointBlock method="GET" path="/api/b2b/availability">
                  <ParamTable lang={lang} params={[
                    { name: 'check_in', type: 'string', required: true, desc: isEn ? 'Check-in date (YYYY-MM-DD)' : 'Giris tarihi (YYYY-MM-DD)' },
                    { name: 'check_out', type: 'string', required: true, desc: isEn ? 'Check-out date (YYYY-MM-DD)' : 'Cikis tarihi (YYYY-MM-DD)' },
                    { name: 'room_type', type: 'string', required: false, desc: isEn ? 'Filter by room type' : 'Oda tipine gore filtre' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "check_in": "2026-06-01",\n  "check_out": "2026-06-03",\n  "room_types": [\n    { "room_type": "Deluxe Double", "capacity": 3, "base_price": 250.00,\n      "total_rooms": 10, "available_rooms": 6 }\n  ]\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── RATES ── */}
            <section id="rates">
              <SectionHeader icon={DollarSign} title={isEn ? 'Rates API' : 'Fiyat API'} id="rates-h" />
              <Desc>{isEn ? 'Fetch agency-specific or base hotel rates for a date range.' : 'Acenteye ozel veya temel otel fiyatlarini cekin.'}</Desc>
              <div className="mt-6">
                <EndpointBlock method="GET" path="/api/b2b/rates">
                  <ParamTable lang={lang} params={[
                    { name: 'start_date', type: 'string', required: true, desc: isEn ? 'Start date (YYYY-MM-DD)' : 'Baslangic tarihi (YYYY-MM-DD)' },
                    { name: 'end_date', type: 'string', required: true, desc: isEn ? 'End date (YYYY-MM-DD)' : 'Bitis tarihi (YYYY-MM-DD)' },
                    { name: 'room_type', type: 'string', required: false, desc: isEn ? 'Filter by room type' : 'Oda tipine gore filtre' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "source": "agency_rates",\n  "rates": [\n    { "date": "2026-06-01", "room_type_code": "DLX",\n      "single": 200, "double": 250, "triple": 300 }\n  ]\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── RESERVATIONS ── */}
            <section id="reservations">
              <SectionHeader icon={FileText} title={isEn ? 'Reservations API' : 'Rezervasyon API'} id="res-h" />
              <Desc>{isEn ? 'Create, list, view, and cancel reservations. All bookings automatically sync with PMS.' : 'Rezervasyon olusturun, listeleyin, goruntuleyin ve iptal edin. Otomatik PMS senkronizasyonu.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/reservations" desc={isEn ? 'Create a reservation with auto room assignment' : 'Otomatik oda atamali rezervasyon olustur'}>
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
              <SectionHeader icon={Users} title={isEn ? 'Guest Management' : 'Misafir Yonetimi'} id="guests-h" />
              <Desc>{isEn ? 'Search guests, view profiles, and access stay history.' : 'Misafir arayin, profilleri goruntuleyin ve konaklama gecmisine erisin.'}</Desc>
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
              <Desc>{isEn ? 'Manage guest loyalty points, tiers, and VIP status. Tiers: Bronze (0+), Silver (2000+), Gold (5000+), Platinum (10000+).' : 'Misafir sadakat puanlarini, seviyeleri ve VIP durumunu yonetin. Seviyeler: Bronze (0+), Silver (2000+), Gold (5000+), Platinum (10000+).'}</Desc>
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
              <Desc>{isEn ? 'Query and update room cleaning status. Integrate with housekeeping management systems.' : 'Oda temizlik durumlarini sorgulama ve guncelleme. Kat hizmeti sistemleriyle entegrasyon.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/housekeeping/rooms" desc={isEn ? 'List rooms with cleaning status' : 'Odalar ve temizlik durumlarini listele'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: false, desc: 'clean, dirty, inspected, maintenance, out_of_order' },
                    { name: 'floor', type: 'string', required: false, desc: isEn ? 'Filter by floor' : 'Kata gore filtre' },
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
              <Desc>{isEn ? 'Access guest registration data for KBS (police notification system). List checked-in guests with identity information and submit reports.' : 'KBS (emniyet bildirim sistemi) icin misafir kayit verilerine erisin. Check-in yapan misafirleri kimlik bilgileriyle listeleyin ve rapor gonderin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/kbs/guests" desc={isEn ? 'Get guests for KBS reporting with identity data' : 'KBS bildirimi icin misafir listesi ve kimlik bilgileri'}>
                  <ParamTable lang={lang} params={[
                    { name: 'date', type: 'string', required: false, desc: isEn ? 'Date (YYYY-MM-DD, default: today)' : 'Tarih (YYYY-MM-DD, varsayilan: bugun)' },
                    { name: 'status', type: 'string', required: false, desc: 'pending, submitted, confirmed, error' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "date": "2026-06-01",\n  "guests": [\n    { "id": "b1...", "guest_name": "Ali Yilmaz", "room_number": "302",\n      "check_in": "2026-06-01T14:00:00", "nationality": "TR",\n      "id_number": "12345678901", "passport_number": "",\n      "birth_date": "1985-03-15", "gender": "M" }\n  ],\n  "guest_count": 1,\n  "reports": [],\n  "report_count": 0\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/kbs/report" desc={isEn ? 'Submit a KBS report' : 'KBS bildirimi olustur'}>
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
              <Desc>{isEn ? 'Submit passport/ID OCR scan results and query guest identity data. Supports passport, ID card, and driving license. Auto-updates guest profile with scanned data.' : 'Pasaport/kimlik OCR tarama sonuclarini gonderin ve misafir kimlik verilerini sorgulayIn. Pasaport, kimlik karti ve ehliyet destegi. Taranan veriler otomatik misafir profiline yansir.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/identity/scan" desc={isEn ? 'Submit OCR scan data — auto-updates guest profile' : 'OCR tarama verisini gonderin — misafir profili otomatik guncellenir'}>
                  <ParamTable lang={lang} params={[
                    { name: 'guest_id', type: 'string', required: true, desc: isEn ? 'Guest ID' : 'Misafir ID' },
                    { name: 'scan_type', type: 'string', required: true, desc: 'passport, id_card, driving_license' },
                    { name: 'document_number', type: 'string', required: true, desc: isEn ? 'Document number' : 'Belge numarasi' },
                    { name: 'first_name', type: 'string', required: true, desc: isEn ? 'First name from document' : 'Belgedeki ad' },
                    { name: 'last_name', type: 'string', required: true, desc: isEn ? 'Last name from document' : 'Belgedeki soyad' },
                    { name: 'nationality', type: 'string', required: false, desc: isEn ? 'Nationality code (TR, DE, US...)' : 'Ulke kodu (TR, DE, US...)' },
                    { name: 'birth_date', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'gender', type: 'string', required: false, desc: 'M, F' },
                    { name: 'expiry_date', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'issuing_country', type: 'string', required: false, desc: isEn ? 'Issuing country' : 'Veren ulke' },
                    { name: 'mrz_line1', type: 'string', required: false, desc: 'MRZ Line 1' },
                    { name: 'mrz_line2', type: 'string', required: false, desc: 'MRZ Line 2' },
                    { name: 'scan_quality', type: 'number', required: false, desc: isEn ? 'Quality score 0-100 (auto-verify if >= 80)' : 'Kalite skoru 0-100 (>=80 otomatik dogrulama)' },
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
              <Desc>{isEn ? 'Manage lost and found items — register, update status, link to guests.' : 'Kayip ve bulunan esyalari yonetin — kaydedIn, durum guncelleyin, misafirlere baglayin.'}</Desc>
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
                    { name: 'description', type: 'string', required: false, desc: isEn ? 'Description' : 'Aciklama' },
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
              <SectionHeader icon={Phone} title={isEn ? 'Wake-up Calls' : 'Uyandirma Servisi'} id="wu-h" />
              <Desc>{isEn ? 'Create and manage wake-up call requests for guests.' : 'Misafirler icin uyandirma talepleri olusturun ve yonetin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/wake-up-calls" desc={isEn ? 'List wake-up calls' : 'Uyandirma listesi'}>
                  <ParamTable lang={lang} params={[
                    { name: 'date', type: 'string', required: false, desc: 'YYYY-MM-DD' },
                    { name: 'status', type: 'string', required: false, desc: 'pending, completed, cancelled, missed' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/wake-up-calls" desc={isEn ? 'Create wake-up call' : 'Uyandirma olustur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'room_number', type: 'string', required: true, desc: isEn ? 'Room number' : 'Oda numarasi' },
                    { name: 'guest_name', type: 'string', required: true, desc: isEn ? 'Guest name' : 'Misafir adi' },
                    { name: 'wake_date', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'wake_time', type: 'string', required: true, desc: 'HH:MM' },
                    { name: 'recurring', type: 'boolean', required: false, desc: isEn ? 'Repeat daily' : 'Her gun tekrarla' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="PUT" path="/api/b2b/wake-up-calls/{call_id}" desc={isEn ? 'Update wake-up call' : 'Uyandirma guncelle'} />
                <EndpointBlock method="DELETE" path="/api/b2b/wake-up-calls/{call_id}" desc={isEn ? 'Cancel wake-up call' : 'Uyandirma iptal'} />
              </div>
            </section>

            {/* ── GUEST JOURNEY ── */}
            <section id="journey">
              <SectionHeader icon={Globe} title={isEn ? 'Guest Journey' : 'Misafir Yolculugu'} id="gj-h" />
              <Desc>{isEn ? 'Online check-in, pre-arrival management, and guest service requests.' : 'Online check-in, pre-arrival yonetimi ve misafir servis talepleri.'}</Desc>
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
                <EndpointBlock method="POST" path="/api/b2b/guest-journey/request" desc={isEn ? 'Create a service request' : 'Servis talebi olustur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: true, desc: isEn ? 'Booking ID' : 'Rezervasyon ID' },
                    { name: 'request_type', type: 'string', required: true, desc: 'concierge, spa, room_service, maintenance, transport, other' },
                    { name: 'description', type: 'string', required: true, desc: isEn ? 'Request description' : 'Talep aciklamasi' },
                    { name: 'priority', type: 'string', required: false, desc: 'low, normal, high, urgent' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/guest-journey/requests" desc={isEn ? 'List service requests with filters' : 'Servis taleplerini filtreli listele'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: false, desc: isEn ? 'Filter by booking' : 'Rezervasyona gore filtre' },
                    { name: 'status', type: 'string', required: false, desc: 'pending, in_progress, completed, cancelled' },
                    { name: 'request_type', type: 'string', required: false, desc: isEn ? 'Filter by type' : 'Tipe gore filtre' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── CONCIERGE ── */}
            <section id="concierge">
              <SectionHeader icon={Coffee} title={isEn ? 'Concierge Services' : 'Concierge Hizmetleri'} id="con-h" />
              <Desc>{isEn ? 'Browse available concierge services and create service requests.' : 'Mevcut concierge hizmetlerini goruntuleyin ve talep olusturun.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/concierge/services" desc={isEn ? 'List available concierge services' : 'Mevcut concierge hizmetlerini listele'}>
                  <CodeBlock lang="json" code={`{\n  "services": [\n    { "id": "transfer", "name": "Airport Transfer",\n      "name_tr": "Havaalani Transferi", "category": "transport",\n      "price_range": "50-150" },\n    { "id": "restaurant", "name": "Restaurant Reservation",\n      "name_tr": "Restoran Rezervasyonu", "category": "dining" }\n  ]\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/concierge/request" desc={isEn ? 'Create a concierge request' : 'Concierge talebi olustur'}>
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
              <Desc>{isEn ? 'Browse spa services and create spa bookings for guests.' : 'Spa hizmetlerini goruntuleyin ve misafirler icin spa randevusu olusturun.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/spa/services" desc={isEn ? 'List spa services with prices' : 'Spa hizmetleri ve fiyat listesi'}>
                  <CodeBlock lang="json" code={`{\n  "services": [\n    { "id": "massage_60", "name": "Swedish Massage 60min",\n      "name_tr": "Isvec Masaji 60dk", "category": "massage",\n      "duration": 60, "price": 120 },\n    { "id": "hammam", "name": "Turkish Hammam",\n      "name_tr": "Turk Hamami", "category": "bath",\n      "duration": 75, "price": 100 }\n  ]\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/spa/booking" desc={isEn ? 'Create spa booking' : 'Spa randevusu olustur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'booking_id', type: 'string', required: true, desc: isEn ? 'Hotel booking ID' : 'Otel rezervasyon ID' },
                    { name: 'service_id', type: 'string', required: true, desc: isEn ? 'Service ID from /spa/services' : '/spa/services\'ten gelen hizmet ID' },
                    { name: 'preferred_date', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'preferred_time', type: 'string', required: true, desc: 'HH:MM' },
                    { name: 'guest_count', type: 'int', required: false, desc: isEn ? 'Number of guests (default: 1)' : 'Misafir sayisi (varsayilan: 1)' },
                    { name: 'notes', type: 'string', required: false, desc: isEn ? 'Special requests' : 'Ozel istekler' },
                  ]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── MICE & GROUPS ── */}
            <section id="groups">
              <SectionHeader icon={Building} title={isEn ? 'MICE & Groups' : 'MICE & Grup Yonetimi'} id="grp-h" />
              <Desc>{isEn ? 'Manage group blocks, rooming lists, and MICE events (conferences, weddings, corporate events).' : 'Grup bloklari, rooming listleri ve MICE etkinliklerini (konferans, dugun, kurumsal) yonetin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/groups" desc={isEn ? 'List group blocks' : 'Grup bloklari listele'}>
                  <ParamTable lang={lang} params={[
                    { name: 'status', type: 'string', required: false, desc: 'tentative, confirmed, cancelled' },
                  ]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/groups/block" desc={isEn ? 'Create a group block' : 'Grup blok olustur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'group_name', type: 'string', required: true, desc: isEn ? 'Group/event name' : 'Grup/etkinlik adi' },
                    { name: 'contact_name', type: 'string', required: true, desc: isEn ? 'Contact person' : 'Irtibat kisisi' },
                    { name: 'check_in', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'check_out', type: 'string', required: true, desc: 'YYYY-MM-DD' },
                    { name: 'rooms_requested', type: 'int', required: true, desc: isEn ? 'Number of rooms needed' : 'Gereken oda sayisi' },
                    { name: 'event_type', type: 'string', required: false, desc: 'conference, wedding, corporate, tour_group, other' },
                    { name: 'room_type', type: 'string', required: false, desc: isEn ? 'Preferred room type' : 'Tercih edilen oda tipi' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "block": {\n    "id": "blk1...",\n    "group_name": "Tech Conference 2026",\n    "rooms_requested": 50,\n    "rooms_picked_up": 0,\n    "status": "tentative"\n  }\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/groups/{block_id}" desc={isEn ? 'Get block details with rooming list' : 'Blok detayi ve rooming list'} />
                <EndpointBlock method="POST" path="/api/b2b/groups/{block_id}/rooming-list" desc={isEn ? 'Upload bulk guest list — creates reservations automatically' : 'Toplu misafir listesi yukle — otomatik rezervasyon olusturur'}>
                  <ParamTable lang={lang} params={[
                    { name: 'guests', type: 'array', required: true, desc: isEn ? 'Array of guest entries' : 'Misafir kayitlari dizisi' },
                    { name: 'guests[].guest_name', type: 'string', required: true, desc: isEn ? 'Guest full name' : 'Misafir tam adi' },
                    { name: 'guests[].room_type', type: 'string', required: false, desc: isEn ? 'Override room type' : 'Oda tipi (override)' },
                    { name: 'guests[].check_in', type: 'string', required: false, desc: isEn ? 'Override check-in (default: block dates)' : 'Giris tarihi (varsayilan: blok tarihi)' },
                    { name: 'guests[].check_out', type: 'string', required: false, desc: isEn ? 'Override check-out' : 'Cikis tarihi' },
                  ]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "created_count": 3,\n  "reservations": [\n    { "guest_name": "Alice Johnson",\n      "booking_id": "b1...",\n      "confirmation_code": "GRP-B1A2C3D4" }\n  ]\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── FOLIO & BILLING ── */}
            <section id="folio">
              <SectionHeader icon={Receipt} title={isEn ? 'Folio & Billing' : 'Folio & Fatura'} id="fol-h" />
              <Desc>{isEn ? 'View guest folios, post charges, and generate invoices.' : 'Misafir foliolarini goruntuleyin, masraf ekleyin ve fatura olusturun.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/folio/{booking_id}" desc={isEn ? 'Get folio with all charges and payments' : 'Tum masraf ve odemelerle folio getir'}>
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
                <EndpointBlock method="GET" path="/api/b2b/folio/{booking_id}/invoice" desc={isEn ? 'Generate invoice (JSON format)' : 'Fatura olustur (JSON formatinda)'}>
                  <CodeBlock lang="json" code={`{\n  "invoice_number": "INV-A1B2C3D4",\n  "invoice_date": "2026-06-03",\n  "hotel": { "hotel_name": "Grand Palace", "tax_number": "123..." },\n  "guest_name": "John Doe",\n  "check_in": "2026-06-01", "check_out": "2026-06-03",\n  "charges": [...],\n  "subtotal": 535.00,\n  "total_paid": 500.00,\n  "balance_due": 35.00,\n  "currency": "TRY"\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── WEBHOOKS ── */}
            <section id="webhooks">
              <SectionHeader icon={Bell} title="Webhooks" id="wh-h" />
              <Desc>{isEn ? 'Receive real-time notifications when events occur. Register webhook URLs and Syroce will POST event data with retry and dead-letter queue support.' : 'Olaylar gerceklestiginde gercek zamanli bildirimler alin. Webhook URL\'si kaydedin, Syroce olay verisini retry ve dead-letter queue destegi ile POST edecektir.'}</Desc>

              <div className="mt-6">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">{isEn ? 'Supported Events' : 'Desteklenen Olaylar'}</h3>
                <div className="space-y-2">
                  {[
                    { name: 'reservation.created', desc: isEn ? 'New reservation created' : 'Yeni rezervasyon olusturuldu' },
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
                    { name: 'secret', type: 'string', required: false, desc: isEn ? 'Signing secret for HMAC verification' : 'HMAC dogrulamasi icin imzalama anahtari' },
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
                  <p className="text-sm text-amber-800 mt-2">{isEn ? 'If you provide a secret, each delivery includes X-Webhook-Signature header. Verify with HMAC-SHA256:' : 'Secret belirlerseniz her teslimat X-Webhook-Signature basligini icerir. HMAC-SHA256 ile dogrulayin:'}</p>
                  <div className="mt-3">
                    <CodeBlock lang="python" code={`import hmac, hashlib\n\ndef verify_signature(body, secret, sig_header):\n    expected = hmac.new(\n        secret.encode(), body, hashlib.sha256\n    ).hexdigest()\n    return hmac.compare_digest(f"sha256={expected}", sig_header)`} />
                  </div>
                </div>
              </div>
            </section>

            <div className="border-t border-slate-200 pt-8 pb-16 text-center">
              <p className="text-sm text-slate-400">Syroce Open API v2.0 &middot; 19 {isEn ? 'Module Groups' : 'Modul Grubu'} &middot; {new Date().getFullYear()}</p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
