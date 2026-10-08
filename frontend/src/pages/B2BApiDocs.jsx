import { t } from "i18next";
import { useState, useEffect } from 'react';
import { BookOpen, Key, Search, Hotel, Calendar, DollarSign, FileText, Bell, ChevronRight, Globe, Copy, Check, ArrowLeft, Code, Shield, Zap, Users, Sparkles, ClipboardList, CreditCard, Fingerprint, Package, Phone, Coffee, Building, Receipt, AlertTriangle, Gauge, List, Rocket, GitBranch } from 'lucide-react';
const API_BASE = window.location.origin + '/api/b2b';
const sections = [{
  id: 'overview',
  icon: BookOpen
}, {
  id: 'quickstart',
  icon: Rocket
}, {
  id: 'auth',
  icon: Key
}, {
  id: 'errors',
  icon: AlertTriangle
}, {
  id: 'ratelimits',
  icon: Gauge
}, {
  id: 'pagination',
  icon: List
}, {
  id: 'content',
  icon: Hotel
}, {
  id: 'availability',
  icon: Calendar
}, {
  id: 'rates',
  icon: DollarSign
}, {
  id: 'reservations',
  icon: FileText
}, {
  id: 'guests',
  icon: Users
}, {
  id: 'loyalty',
  icon: Sparkles
}, {
  id: 'housekeeping',
  icon: ClipboardList
}, {
  id: 'kbs',
  icon: Shield
}, {
  id: 'identity',
  icon: Fingerprint
}, {
  id: 'lostfound',
  icon: Package
}, {
  id: 'wakeup',
  icon: Phone
}, {
  id: 'journey',
  icon: Globe
}, {
  id: 'concierge',
  icon: Coffee
}, {
  id: 'spa',
  icon: Zap
}, {
  id: 'groups',
  icon: Building
}, {
  id: 'folio',
  icon: Receipt
}, {
  id: 'webhooks',
  icon: Bell
}, {
  id: 'versioning',
  icon: GitBranch
}];
const navLabels = {
  en: {
    overview: 'Overview',
    quickstart: 'Quick Start',
    auth: 'Authentication',
    errors: 'Error Codes',
    ratelimits: 'Rate Limits',
    pagination: 'Pagination',
    content: 'Content',
    availability: 'Availability',
    rates: 'Rates',
    reservations: 'Reservations',
    guests: 'Guests',
    loyalty: 'Loyalty Program',
    housekeeping: 'Housekeeping',
    kbs: 'KBS / Police',
    identity: 'Passport / ID',
    lostfound: 'Lost & Found',
    wakeup: 'Wake-up Calls',
    journey: 'Guest Journey',
    concierge: 'Concierge',
    spa: 'Spa & Wellness',
    groups: 'MICE & Groups',
    folio: 'Folio & Billing',
    webhooks: 'Webhooks',
    versioning: 'Versioning'
  },
  tr: {
    overview: 'Genel Bakış',
    quickstart: 'Hızlı Başlangıç',
    auth: 'Kimlik Doğrulama',
    errors: 'Hata Kodları',
    ratelimits: 'İstek Limitleri',
    pagination: 'Sayfalama',
    content: 'İçerik',
    availability: 'Müsaitlik',
    rates: 'Fiyatlar',
    reservations: 'Rezervasyonlar',
    guests: 'Misafirler',
    loyalty: 'Sadakat Programı',
    housekeeping: 'Kat Hizmetleri',
    kbs: 'KBS / Emniyet',
    identity: 'Pasaport / Kimlik',
    lostfound: 'Kayıp Eşya',
    wakeup: 'Uyandırma',
    journey: 'Misafir Yolculuğu',
    concierge: 'Concierge',
    spa: 'Spa & Wellness',
    groups: 'MICE & Grup',
    folio: 'Folio & Fatura',
    webhooks: 'Webhook\'lar',
    versioning: 'Sürümleme'
  }
};
const t_labels = {
  en: {
    required: 'required',
    optional: 'optional'
  },
  tr: {
    required: 'zorunlu',
    optional: 'opsiyonel'
  }
};
const CodeBlock = ({
  code,
  lang = 'bash'
}) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return <div className="relative group rounded-lg overflow-hidden border border-slate-700 bg-[#0d1117]">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-slate-700">
        <span className="text-xs text-slate-400 font-mono">{lang}</span>
        <button onClick={handleCopy} className="text-xs text-slate-400 hover:text-white transition flex items-center gap-1">
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-sm leading-relaxed"><code className="text-slate-200 font-mono text-[13px]">{code}</code></pre>
    </div>;
};
const ParamTable = ({
  params,
  lang
}) => <div className="overflow-x-auto rounded-lg border border-slate-200">
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-slate-50 border-b border-slate-200">
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.parameter")}</th>
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.type")}</th>
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.required")}</th>
          <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.description")}</th>
        </tr>
      </thead>
      <tbody>
        {params.map((p, i) => <tr key={p.name} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
            <td className="px-4 py-2.5 font-mono text-[13px] text-emerald-700">{p.name}</td>
            <td className="px-4 py-2.5 text-slate-500 font-mono text-[13px]">{p.type}</td>
            <td className="px-4 py-2.5">
              {p.required ? <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">{t_labels[lang].required}</span> : <span className="text-xs text-slate-400">{t_labels[lang].optional}</span>}
            </td>
            <td className="px-4 py-2.5 text-slate-600">{p.desc}</td>
          </tr>)}
      </tbody>
    </table>
  </div>;
const MethodBadge = ({
  method
}) => {
  const colors = {
    GET: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    POST: 'bg-blue-100 text-blue-800 border-blue-200',
    PUT: 'bg-amber-100 text-amber-800 border-amber-200',
    DELETE: 'bg-red-100 text-red-800 border-red-200'
  };
  return <span className={`inline-block px-2.5 py-1 rounded font-mono text-xs font-bold border ${colors[method] || 'bg-slate-100 text-slate-700'}`}>{method}</span>;
};
const EndpointBlock = ({
  method,
  path,
  desc,
  children
}) => <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
    <div className="flex items-center gap-3 px-4 py-3 bg-slate-50 border-b border-slate-200">
      <MethodBadge method={method} />
      <code className="text-sm font-mono text-slate-800">{path}</code>
    </div>
    {desc && <p className="px-5 pt-3 text-sm text-slate-500">{desc}</p>}
    {children && <div className="p-5 space-y-4">{children}</div>}
  </div>;
const SectionHeader = ({
  icon: Icon,
  title,
  id
}) => <h2 id={id} className="text-2xl font-bold text-slate-900 flex items-center gap-3 pt-8 pb-2 scroll-mt-20" style={{
  fontFamily: 'Manrope, sans-serif'
}}>
    <div className="w-9 h-9 rounded-lg bg-[#C09D63]/10 flex items-center justify-center">
      <Icon size={18} className="text-[#C09D63]" />
    </div>
    {title}
  </h2>;
const SubTitle = ({
  children
}) => <h3 className="text-lg font-semibold text-slate-800 mb-2">{children}</h3>;
const Desc = ({
  children
}) => <p className="text-slate-600 leading-relaxed mt-3">{children}</p>;

const MARKETPLACE_BASE = window.location.origin + '/api/marketplace/v1';
const marketplaceEndpoints = [
  ['GET', '/hotels', 'Onaylı sözleşmesi bulunan, yayındaki otelleri listeler. Filtreler: city, country, q, limit (en fazla 200).', 'Lists published hotels covered by an approved contract. Filters: city, country, q and limit (max 200).'],
  ['GET', '/hotels/{tenant_id}', 'Aktif sözleşmeli otelin içerik ve oda tipi detayını getirir.', 'Returns content and room-type details for a hotel with an active contract.'],
  ['POST', '/search', 'Sözleşmeli otellerde canlı fiyat ve müsaitlik arar.', 'Searches live rates and availability across contracted hotels.'],
  ['GET', '/hotels/{tenant_id}/availability', 'check_in ve check_out (YYYY-MM-DD) için müsaitlik döndürür.', 'Returns availability for check_in and check_out (YYYY-MM-DD).'],
  ['GET', '/hotels/{tenant_id}/rates', 'start_date, end_date ve isteğe bağlı room_type için fiyatları döndürür.', 'Returns rates for start_date, end_date and optional room_type.'],
  ['POST', '/reservations', 'Sunucuda yeniden fiyatlayarak rezervasyon oluşturur; tekrar denemelerde idempotency_key kullanın.', 'Creates a server-repriced reservation; reuse idempotency_key when retrying.'],
  ['GET', '/reservations', 'Acentenin rezervasyonlarını status, tenant_id ve giriş tarihiyle filtreler; limit en fazla 500.', 'Lists agency reservations filtered by status, tenant_id and arrival date; limit is capped at 500.'],
  ['GET', '/reservations/{reservation_id}', 'Acenteye ait rezervasyonun özet ve PMS görünümünü getirir.', 'Returns the agency-owned reservation summary and PMS view.'],
  ['GET', '/reservations/{reservation_id}/voucher.pdf', 'Voucher belgesini PDF olarak indirir.', 'Downloads the voucher as PDF.'],
  ['POST', '/reservations/{reservation_id}/voucher-email', 'Voucher belgesini body içindeki email adresine gönderir.', 'Emails the voucher to the email supplied in the request body.'],
  ['DELETE', '/reservations/{reservation_id}', 'Doğrudan iptal etmez; otel onayı bekleyen iptal talebi açar. reason en az 5 karakter olmalıdır.', 'Creates a cancellation request for hotel approval instead of cancelling immediately; reason must be at least 5 characters.'],
  ['POST', '/reservations/{reservation_id}/modification-proposals', 'Tarih/oda değişiklik teklifini otel onayına gönderir.', 'Submits date or room changes for hotel approval.'],
  ['GET', '/negotiations', 'Acentenin bekleyen ve sonuçlanan değişiklik/iptal görüşmelerini listeler.', 'Lists pending and resolved modification or cancellation negotiations.'],
  ['POST', '/negotiations/{proposal_id}/decision', 'Otel tarafından başlatılan görüşmeye acente kararı verir.', 'Records the agency decision for a hotel-initiated negotiation.'],
  ['POST', '/contracts/propose', 'Bir otel için komisyon ve sözleşme koşulları teklifi oluşturur.', 'Proposes commission and commercial terms for one hotel.'],
  ['GET', '/contracts/mine', 'Acentenin otel bazlı sözleşmelerini listeler.', 'Lists the agency’s hotel-specific contracts.'],
  ['GET', '/contracts/{contract_id}', 'Tek sözleşmenin ayrıntısını getirir.', 'Returns one contract in detail.'],
  ['DELETE', '/contracts/{contract_id}', 'Yalnızca bekleyen teklifi geri çeker.', 'Withdraws a pending proposal only.'],
  ['GET', '/reconciliation/agency', 'period_start ve period_end ile acente mutabakatını JSON döndürür.', 'Returns agency reconciliation as JSON for period_start and period_end.'],
  ['GET', '/reconciliation/agency.csv', 'Aynı mutabakatı CSV olarak indirir.', 'Downloads the same reconciliation as CSV.'],
];

function MarketplaceDocs({ isEn }) {
  return <>
    <section id="overview">
      <SectionHeader icon={BookOpen} title={isEn ? 'Agency Marketplace API' : 'Acente Marketplace API'} id="marketplace-overview" />
      <Desc>{isEn ? 'Server-to-server API for agency hotel discovery, hotel-specific contracts, live search, reservations, negotiation, vouchers and reconciliation. Human extranet users use Bearer login and do not need this key.' : 'Acente yazılımının otel keşfi, otel bazlı sözleşme, canlı arama, rezervasyon, görüşme, voucher ve mutabakat işlemleri için sunucudan sunucuya API’dir. Extranet kullanan insan kullanıcı bu anahtara ihtiyaç duymaz.'}</Desc>
      <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
        <strong>{isEn ? 'Security:' : 'Güvenlik:'}</strong> {isEn ? <>Store the <code>syroce_mkt_…</code> key only in a backend secret or environment variable. Never place it in a browser, mobile application, Git repository or message. Send it in the <code>X-API-Key</code> header on every request.</> : <><code>syroce_mkt_…</code> anahtarını yalnızca backend secret/env alanında saklayın. Tarayıcıya, mobil uygulamaya, Git deposuna veya mesaja koymayın. Tüm çağrılarda <code>X-API-Key</code> başlığı kullanılır.</>}
      </div>
      <div className="mt-5"><CodeBlock lang="bash" code={`export SYROCE_MARKETPLACE_API_KEY="syroce_mkt_..."\n\ncurl "${MARKETPLACE_BASE}/hotels?limit=50" \\\n  -H "X-API-Key: $SYROCE_MARKETPLACE_API_KEY"`} /></div>
    </section>

    <section id="marketplace-contracts">
      <SectionHeader icon={Shield} title={isEn ? 'Commercial rules' : 'Ticari kurallar'} id="marketplace-rules" />
      <ul className="mt-4 list-disc space-y-2 pl-6 text-sm leading-6 text-slate-700">
        <li>{isEn ? 'Hotel discovery, search, rates and reservations require an approved contract that is valid for the requested dates.' : 'Otel keşfi, arama, fiyat ve rezervasyon için ilgili otelle tarih bakımından geçerli, onaylı sözleşme gerekir.'}</li>
        <li>{isEn ? 'The agency default commission is never silently applied to a reservation; the approved hotel contract takes precedence.' : 'Acente varsayılan komisyonu rezervasyona sessizce uygulanmaz; onaylı otel sözleşmesindeki oran önceliklidir.'}</li>
        <li>{isEn ? 'Only Syroce administration can set the Syroce platform service fee.' : 'Syroce platform hizmet bedeli yalnızca Syroce yönetimi tarafından belirlenir.'}</li>
        <li>{isEn ? 'Cancellation and modification calls do not directly alter the PMS record; they open a negotiation that requires the counterparty’s approval.' : 'İptal ve değişiklik çağrıları doğrudan PMS kaydını değiştirmez; karşı taraf onayı isteyen bir görüşme kaydı açar.'}</li>
      </ul>
    </section>

    <section id="marketplace-models">
      <SectionHeader icon={FileText} title={isEn ? 'Request models' : 'İstek modelleri'} id="marketplace-models-h" />
      <SubTitle>POST /search</SubTitle>
      <CodeBlock lang="json" code={`{\n  "check_in": "2026-11-10",\n  "check_out": "2026-11-12",\n  "adults": 2,\n  "children": 1,\n  "child_ages": [7],\n  "city": "Sapanca",\n  "amenities": ["pool"],\n  "meal_plans": ["bb"],\n  "min_star_rating": 4,\n  "max_price": 15000,\n  "limit": 50\n}`} />
      <div className="mt-6"><SubTitle>POST /reservations</SubTitle></div>
      <CodeBlock lang="json" code={`{\n  "tenant_id": "hotel-tenant-id",\n  "room_type": "Deluxe",\n  "check_in": "2026-11-10",\n  "check_out": "2026-11-12",\n  "guest_name": "Ayşe Yılmaz",\n  "guest_email": "ayse@example.com",\n  "guest_phone": "+905551112233",\n  "adults": 2,\n  "children": 0,\n  "child_ages": [],\n  "special_requests": "Geç giriş",\n  "external_reference": "AGENCY-PNR-42",\n  "idempotency_key": "booking-42-attempt-1"\n}`} />
      <p className="mt-3 text-sm text-slate-600">{isEn ? <>The submitted <code>total_amount</code> is not trusted; the server recalculates it from the active contract and rate records.</> : <>Gönderilen <code>total_amount</code> güven kaynağı değildir; sunucu aktif sözleşme ve fiyat kayıtlarıyla tutarı yeniden hesaplar.</>}</p>
      <div className="mt-6"><SubTitle>POST /contracts/propose</SubTitle></div>
      <CodeBlock lang="json" code={`{\n  "tenant_id": "hotel-tenant-id",\n  "commission_pct": 12,\n  "valid_from": "2026-11-01",\n  "valid_to": "2027-10-31",\n  "currency": "TRY",\n  "payment_terms": "net_15",\n  "allowed_room_types": ["Deluxe", "Suite"],\n  "cancellation_policy": {\n    "free_until_days_before": 7,\n    "penalty_pct": 50,\n    "no_show_penalty_pct": 100\n  },\n  "special_terms": "Mutabakat her ayın ilk haftasıdır.",\n  "webhook_url": "https://agency.example.com/syroce/events"\n}`} />
      <p className="mt-3 text-sm text-slate-600"><code>payment_terms</code>: prepaid, on_arrival, net_7, net_15 {isEn ? 'or' : 'veya'} net_30. {isEn ? 'The date range may not exceed two years; a supplied webhook URL must use HTTPS.' : 'Tarih aralığı en fazla iki yıl olabilir; webhook adresi verilirse HTTPS olmalıdır.'}</p>
      <div className="mt-6"><SubTitle>{isEn ? 'Negotiation and voucher bodies' : 'Görüşme ve voucher gövdeleri'}</SubTitle></div>
      <CodeBlock lang="json" code={`// POST /reservations/{id}/voucher-email\n{ "email": "operations@agency.example" }\n\n// POST /reservations/{id}/modification-proposals\n{\n  "check_in": "2026-11-11",\n  "check_out": "2026-11-13",\n  "room_type": "Suite",\n  "reason": "Misafir tarih değişikliği istedi"\n}\n\n// POST /negotiations/{proposal_id}/decision\n{ "accept": true, "response_note": "Teklif kabul edildi" }`} />
      <p className="mt-3 text-sm text-slate-600">{isEn ? <>For cancellation, <code>reason</code> is a query parameter in <code>DELETE /reservations/{'{reservation_id}'}?reason=...</code>, not a JSON body. Reconciliation calls require <code>period_start</code> and <code>period_end</code> query parameters in YYYY-MM-DD format.</> : <>İptal talebindeki <code>reason</code> JSON gövdesi değil, <code>DELETE /reservations/{'{reservation_id}'}?reason=...</code> sorgu parametresidir. Mutabakat çağrılarında <code>period_start</code> ve <code>period_end</code> zorunlu YYYY-MM-DD sorgu parametreleridir.</>}</p>
      <div className="mt-8"><SubTitle>{isEn ? 'Representative response envelopes' : 'Temel yanıt zarfları'}</SubTitle></div>
      <CodeBlock lang="json" code={`// POST /search
{ "check_in": "2026-11-10", "check_out": "2026-11-12",
  "results": [...], "total_hotels": 4, "message": null }

// POST /reservations
{ "ok": true, "idempotent_replay": false,
  "reservation": { "id": "...", "confirmation_code": "MKT-...",
    "status": "confirmed", "total_amount": 7500,
    "commission_pct": 12, "commission_amount": 900 } }

// POST /contracts/propose
{ "ok": true, "contract": { "id": "...", "tenant_id": "...",
  "status": "pending", "commission_pct": 12 } }

// GET /reconciliation/agency
{ "agency_id": "...", "period_start": "2026-11-01",
  "period_end": "2026-11-30", "totals": {...}, "by_hotel": [...] }`} />
    </section>

    <section id="marketplace-endpoints">
      <SectionHeader icon={List} title={isEn ? 'Verified endpoint catalogue' : 'Doğrulanmış endpoint kataloğu'} id="marketplace-endpoints-h" />
      <Desc>{isEn ? 'The catalogue below is limited to external agency endpoints authenticated with syroce_mkt_ keys. Admin, hotel-JWT, extranet and public widget routes are intentionally excluded.' : 'Bu katalog yalnızca syroce_mkt_ anahtarıyla çağrılan dış acente endpoint’lerini içerir. Yönetim, otel JWT, extranet ve herkese açık widget route’ları özellikle dahil edilmemiştir.'}</Desc>
      <div className="mt-5 space-y-3">{marketplaceEndpoints.map(([method, path, trDesc, enDesc]) => <EndpointBlock key={`${method}-${path}`} method={method} path={`/api/marketplace/v1${path}`} desc={isEn ? enDesc : trDesc} />)}</div>
    </section>

    <section id="marketplace-errors">
      <SectionHeader icon={AlertTriangle} title={isEn ? 'Errors and retries' : 'Hatalar ve tekrar deneme'} id="marketplace-errors-h" />
      <CodeBlock lang="json" code={`401  {"detail":"Marketplace API için syroce_mkt_ anahtarı gerekli"}\n401  {"detail":"Geçersiz veya devre dışı marketplace API key"}\n403  {"detail":"Bu otelle aktif sözleşmeniz yok"}\n404  {"detail":"Rezervasyon bulunamadı"}\n409  {"detail":"Aynı rezervasyon isteği halen işleniyor"}\n422  {"detail":[{"loc":["body", "field"], "msg":"...", "type":"..."}]}`} />
      <p className="mt-4 text-sm leading-6 text-slate-600">{isEn ? <>After a network error or timeout, retry a reservation request with the same <code>idempotency_key</code>. Do not retry 4xx responses until the data or authorization problem is corrected. This version does not guarantee a fixed request limit or <code>X-RateLimit-*</code> response headers. For 429/503 responses, honor <code>Retry-After</code> when present; otherwise use exponential backoff.</> : <>Rezervasyon çağrısını ağ hatası veya timeout sonrasında aynı <code>idempotency_key</code> ile tekrar edin. 4xx hatalarını veri/yetki düzeltilmeden tekrar etmeyin. Bu sürümde belgelenmiş sabit istek limiti veya <code>X-RateLimit-*</code> yanıt başlığı garantisi yoktur; 429/503 alınırsa <code>Retry-After</code> varsa ona uyun, yoksa üstel bekleme kullanın.</>}</p>
    </section>
  </>;
}

export default function B2BApiDocs() {
  const [lang, setLang] = useState('en');
  const [apiProduct, setApiProduct] = useState('hotel');
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
  const scrollTo = id => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    });
  };
  const isEn = lang === 'en';
  return <div className="min-h-screen bg-white" data-testid="b2b-api-docs">
      <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet" />

      <header className="fixed top-0 left-0 right-0 z-50 bg-slate-900 border-b border-slate-700/50 h-14">
        <div className="flex items-center justify-between h-full px-6 max-w-[1600px] mx-auto">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-md bg-[#C09D63] flex items-center justify-center"><Code size={14} className="text-white" /></div>
              <span className="text-white font-bold text-lg" style={{
              fontFamily: 'Manrope, sans-serif'
            }}>{apiProduct === 'hotel' ? 'Syroce Hotel Integration API' : 'Syroce Agency Marketplace API'}</span>
            </div>
            <span className="hidden md:block text-slate-400 text-sm border-l border-slate-600 pl-4 ml-2">
              {isEn ? 'Complete PMS Integration Documentation' : 'Kapsamli PMS Entegrasyon Dokumantasyonu'}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center bg-slate-800 rounded-lg p-0.5">
              <button onClick={() => setApiProduct('marketplace')} className={`px-3 py-1.5 rounded-md text-xs font-semibold ${apiProduct === 'marketplace' ? 'bg-[#C09D63] text-white' : 'text-slate-300'}`}>Marketplace</button>
              <button onClick={() => setApiProduct('hotel')} className={`px-3 py-1.5 rounded-md text-xs font-semibold ${apiProduct === 'hotel' ? 'bg-[#C09D63] text-white' : 'text-slate-300'}`}>Hotel API</button>
            </div>
            <button onClick={() => {
            navigator.clipboard.writeText(window.location.origin + '/b2b/docs');
            setUrlCopied(true);
            setTimeout(() => setUrlCopied(false), 2000);
          }} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all border border-slate-600" title={isEn ? 'Copy documentation URL' : 'Dokümantasyon linkini kopyala'}>
              {urlCopied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
              <span className="hidden sm:inline">{urlCopied ? isEn ? 'Copied!' : 'Kopyalandi!' : isEn ? 'Copy Link' : 'Link Kopyala'}</span>
            </button>
            <div className="flex items-center bg-slate-800 rounded-lg p-0.5">
              <button onClick={() => setLang('en')} className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${lang === 'en' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-white'}`}>{t("cm.pages_B2BApiDocs.en")}</button>
              <button onClick={() => setLang('tr')} className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${lang === 'tr' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-400 hover:text-white'}`}>{t("cm.pages_B2BApiDocs.tr")}</button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex pt-14">
        {apiProduct === 'hotel' && <aside className="hidden lg:block fixed left-0 top-14 bottom-0 w-60 bg-slate-50 border-r border-slate-200 overflow-y-auto">
          <nav className="py-4 px-3">
            <div className="space-y-0.5">
              {sections.map(({
              id,
              icon: Icon
            }) => <button key={id} onClick={() => scrollTo(id)} className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2.5 transition-all ${activeSection === id ? 'bg-white shadow-sm border border-slate-200 text-slate-900 font-semibold' : 'text-slate-500 hover:text-slate-800 hover:bg-white/60'}`}>
                  <Icon size={14} className={activeSection === id ? 'text-[#C09D63]' : 'text-slate-400'} />
                  <span className="truncate">{nl[id]}</span>
                </button>)}
            </div>
          </nav>
        </aside>}

        <main className={`flex-1 min-h-screen ${apiProduct === 'hotel' ? 'lg:ml-60' : ''}`}>
          <div className="max-w-4xl mx-auto px-6 md:px-10 py-10 space-y-12">

            {apiProduct === 'marketplace' ? <MarketplaceDocs isEn={isEn} /> : <>

            {/* ── OVERVIEW ── */}
            <section id="overview">
              <SectionHeader icon={BookOpen} title={isEn ? 'Getting Started' : 'Başlangıç'} id="overview-h" />
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-5"><h3 className="font-bold text-blue-950">Syroce Hotel Integration API</h3><p className="mt-2 text-sm leading-6 text-blue-900"><code>syroce_b2b_…</code> anahtarı yalnızca tek otelin izin verilen PMS alanları içindir. Her anahtar en az bir scope ile oluşturulur; kanal yöneticisine folyo, kimlik veya KBS gibi ilgisiz kapsamlar verilmemelidir.</p><div className="mt-3 flex flex-wrap gap-2">{['booking_engine','folio','groups','guest_journey','guests','housekeeping','identity','kbs','lost_found','services','wake_up','webhooks'].map(scope => <code key={scope} className="rounded bg-white px-2 py-1 text-xs text-blue-800">{scope}</code>)}</div></div>
              <Desc>{isEn ? 'The Hotel Integration API exposes only the PMS capabilities explicitly granted to an integration key. Each key is bound to one hotel and one agency; requests outside its scopes return 403.' : 'Hotel Integration API yalnızca entegrasyon anahtarına açıkça verilen PMS yeteneklerini sunar. Her anahtar tek bir otel ve tek bir acenteye bağlıdır; kapsam dışındaki istekler 403 döndürür.'}</Desc>

              <div className="mt-6 space-y-4">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">{isEn ? 'Base URL' : 'Temel URL'}</h3>
                <CodeBlock code={API_BASE} lang="url" />
              </div>

              <div className="mt-8">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">{isEn ? 'Documentation sections (12 permission scopes)' : 'Dokümantasyon bölümleri (12 yetki kapsamı)'}</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {sections.filter(s => s.id !== 'overview').map(({
                  id,
                  icon: Icon
                }) => <button key={id} onClick={() => scrollTo(id)} className="flex items-center gap-3 text-sm text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-white rounded-lg px-4 py-3 border border-slate-200 transition text-left">
                      <Icon size={16} className="text-[#C09D63] shrink-0" />
                      {nl[id]}
                      <ChevronRight size={14} className="ml-auto text-slate-300" />
                    </button>)}
                </div>
              </div>

              <div className="mt-8">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">{isEn ? 'Response Format' : 'Yanıt Formatı'}</h3>
                <CodeBlock lang="json" code={`// Başarılı yanıt endpoint'e özgüdür; örnek:\n{ "check_in": "2026-07-01", "check_out": "2026-07-03", "room_types": [] }\n\n// Hata yanıtı\n{ "detail": "Error message" }`} />
              </div>
            </section>

            {/* ── QUICK START ── */}
            <section id="quickstart">
              <SectionHeader icon={Rocket} title={isEn ? 'Quick Start Guide' : 'Hızlı Başlangıç Rehberi'} id="qs-h" />
              <Desc>{isEn ? 'Follow these steps to start integrating with the Syroce Open API in minutes. From getting your API key to making your first reservation.' : 'Syroce Open API ile dakikalar içinde entegrasyona başlayın. API anahtarı almaktan ilk rezervasyonunuzu yapmaya kadar adım adım rehber.'}</Desc>

              <div className="mt-8 space-y-6">
                <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#C09D63] flex items-center justify-center text-white font-bold text-sm shrink-0">1</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-slate-900">{isEn ? 'Get Your API Key' : 'API Key Alin'}</h4>
                      <p className="text-sm text-slate-600 mt-1">{isEn ? 'Your hotel partner creates an API key for your agency through the Syroce PMS admin panel:' : 'Otel ortağınız Syroce PMS yönetim panelinden acente API key\'inizi oluşturur:'}</p>
                      <div className="mt-3 space-y-2 text-sm text-slate-600">
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">{t("cm.pages_B2BApiDocs.a")}</span> {isEn ? 'Hotel admin navigates to Travel Agent Management (Acente Yönetimi)' : 'Otel yöneticisi Acente Yönetimi sayfasina gider'}</div>
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">{t("cm.pages_B2BApiDocs.b")}</span> {isEn ? 'Selects your agency and clicks "Generate API Key"' : 'Acentenizi secer ve "API Key Olustur" butonuna tiklar'}</div>
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">{t("cm.pages_B2BApiDocs.c")}</span> {isEn ? 'The key (starting with syroce_b2b_) is shown ONCE — copy it immediately' : 'Key (syroce_b2b_ ile baslar) sadece BIR KEZ gosterilir — hemen kopyalayin'}</div>
                        <div className="flex items-start gap-2"><span className="text-[#C09D63] font-bold">{t("cm.pages_B2BApiDocs.d")}</span> {isEn ? 'Store the key securely (environment variable, secrets manager)' : 'Key\'i guvenli saklayin (ortam degiskeni, secrets manager)'}</div>
                      </div>
                      <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
                        <p className="text-xs text-amber-800 flex items-center gap-1.5">
                          <AlertTriangle size={13} className="shrink-0" />
                          {isEn ? 'The raw API key is only shown at creation time. Key-management routes are control-plane operations for the PMS UI, not calls an external integration should make. Regeneration invalidates the old key.' : 'Ham API anahtarı yalnızca oluşturulurken gösterilir. Anahtar yönetimi route’ları PMS arayüzünün kontrol düzlemi içindir; dış entegrasyonlar bu çağrıları yapmamalıdır. Yenileme eski anahtarı geçersiz kılar.'}
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
                      <p className="text-sm text-slate-600 mt-1">{isEn ? 'Call hotel-info first; unlike content, it does not depend on the hotel publishing content to the agency.' : 'İlk olarak hotel-info çağrısını yapın; content endpointinden farklı olarak otelin acenteye içerik yayımlamasına bağlı değildir.'}</p>
                      <div className="mt-3">
                        <CodeBlock lang="bash" code={`curl -X GET "${API_BASE}/hotel-info" \\\n  -H "X-API-Key: syroce_b2b_YOUR_KEY_HERE"\n\n# Expected: 200 OK with the key's hotel and agency identity\n# If 401: Check your key is correct and active\n# If 403: The agency is inactive or booking_engine scope is missing`} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#C09D63] flex items-center justify-center text-white font-bold text-sm shrink-0">3</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-slate-900">{isEn ? 'Check Availability & Rates' : 'Müsaitlik ve Fiyat Sorgulayın'}</h4>
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
                <p className="text-sm text-slate-600 mb-3">{isEn ? 'All API keys start with the prefix syroce_b2b_ followed by a random string. Example:' : 'Tüm API anahtarları syroce_b2b_ ön eki ile başlar, ardından rastgele bir dizi gelir. Örnek:'}</p>
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
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.endpoint")}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Auth' : 'Yetki'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[{
                      action: isEn ? 'Create key' : 'Key oluştur',
                      who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi',
                      ep: 'POST /api/b2b/api-keys?agency_id=...&scopes=booking_engine',
                      auth: 'JWT'
                    }, {
                      action: isEn ? 'View key info' : 'Key bilgisi gor',
                      who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi',
                      ep: 'GET /api/b2b/api-keys/{agency_id}',
                      auth: 'JWT'
                    }, {
                      action: isEn ? 'Regenerate key' : 'Key yenile',
                      who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi',
                      ep: 'POST /api/b2b/api-keys/{agency_id}/regenerate',
                      auth: 'JWT'
                    }, {
                      action: isEn ? 'Revoke key' : 'Key iptal',
                      who: isEn ? 'Hotel Admin' : 'Otel Yöneticisi',
                      ep: 'DELETE /api/b2b/api-keys/{agency_id}',
                      auth: 'JWT'
                    }].map((r, i) => <tr key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.action}</td>
                          <td className="px-4 py-2.5 text-slate-500">{r.who}</td>
                          <td className="px-4 py-2.5 font-mono text-[12px] text-emerald-700">{r.ep}</td>
                          <td className="px-4 py-2.5"><span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-medium">{r.auth}</span></td>
                        </tr>)}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-slate-500 mt-2">{isEn ? 'Note: Key management endpoints require JWT authentication (hotel admin login), not API key auth. Only the hotel admin can create, view, regenerate, or revoke API keys.' : 'Not: Key yönetim endpoint\'leri JWT kimlik doğrulama (otel admin girisi) gerektirir, API key değil. Sadece otel yöneticisi API key oluşturabilir, görüntüleyebilir, yenileyebilir veya iptal edebilir.'}</p>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Usage Examples' : 'Kullanım Örnekleri'}</SubTitle>
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
                  <li>{isEn ? 'Usage is tracked: request count, last used time, and IP address' : 'Kullanım takip edilir: istek sayısı, son kullanım zamanı ve IP adresi'}</li>
                  <li>{isEn ? 'Use HTTPS in production — never send API keys over unencrypted connections' : 'Uretimde HTTPS kullanin — API key\'leri sifrelenmemis baglantilarda gondermeyin'}</li>
                  <li>{isEn ? 'Rotate keys periodically using the regenerate endpoint' : 'Key\'leri periyodik olarak yenileme endpoint\'i ile dondurun'}</li>
                </ul>
              </div>
            </section>

            {/* ── ERROR CODES ── */}
            <section id="errors">
              <SectionHeader icon={AlertTriangle} title={isEn ? 'Error Codes Reference' : 'Hata Kodlari Referansi'} id="err-h" />
              <Desc>{isEn ? 'The API uses standard HTTP status codes. Error responses include a detail field with a human-readable message.' : 'API standart HTTP durum kodlarini kullanir. Hata yanitlari okunabilir bir mesaj iceren detail alani icerir.'}</Desc>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Error Response Format' : 'Hata Yanıt Formatı'}</SubTitle>
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
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Example' : 'Örnek'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[{
                      code: '200',
                      status: 'OK',
                      color: 'emerald',
                      desc: isEn ? 'Request succeeded' : 'İstek başarılı',
                      example: isEn ? 'Data returned successfully' : 'Veri başarıyla döndü'
                    }, {
                      code: '400',
                      status: 'Bad Request',
                      color: 'amber',
                      desc: isEn ? 'Invalid request data' : 'Geçersiz istek verisi',
                      example: isEn ? 'Invalid date format, missing required field, invalid enum value' : 'Geçersiz tarih formatı, eksik zorunlu alan, geçersiz enum değeri'
                    }, {
                      code: '401',
                      status: 'Unauthorized',
                      color: 'red',
                      desc: isEn ? 'Invalid or missing API key' : 'Geçersiz veya eksik API key',
                      example: '"Geçersiz veya devre dışı API key"'
                    }, {
                      code: '403',
                      status: 'Forbidden',
                      color: 'red',
                      desc: isEn ? 'API key valid but access denied' : 'API key geçerli ama erişim reddedildi',
                      example: isEn ? 'Agency account inactive' : 'Acente hesabı aktif değil'
                    }, {
                      code: '404',
                      status: 'Not Found',
                      color: 'amber',
                      desc: isEn ? 'Resource not found' : 'Kaynak bulunamadı',
                      example: isEn ? 'Reservation, guest, or room not found' : 'Rezervasyon, misafir veya oda bulunamadı'
                    }, {
                      code: '409',
                      status: 'Conflict',
                      color: 'amber',
                      desc: isEn ? 'Resource conflict' : 'Kaynak çatışması',
                      example: isEn ? 'No available rooms for the selected dates' : 'Seçilen tarihler için müsait oda yok'
                    }, {
                      code: '422',
                      status: 'Validation Error',
                      color: 'amber',
                      desc: isEn ? 'Request body validation failed' : 'İstek gövdesi doğrulama hatası',
                      example: isEn ? 'Negative amount, zero points, date in past' : 'Negatif tutar, sıfır puan, geçmiş tarih'
                    }, {
                      code: '429',
                      status: 'Too Many Requests',
                      color: 'red',
                      desc: isEn ? 'The same Idempotency-Key is still being processed' : 'Aynı Idempotency-Key hâlâ işleniyor',
                      example: isEn ? 'Retry after 2 seconds with the same key' : 'Aynı anahtarla 2 saniye sonra tekrar deneyin'
                    }, {
                      code: '500',
                      status: 'Server Error',
                      color: 'red',
                      desc: isEn ? 'Internal server error' : 'Sunucu hatası',
                      example: isEn ? 'Contact support if persistent' : 'Devam ederse destek ile iletisime gecin'
                    }].map((r, i) => <tr key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5"><span className={`font-mono font-bold text-${r.color}-700`}>{r.code}</span></td>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.status}</td>
                          <td className="px-4 py-2.5 text-slate-600">{r.desc}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs">{r.example}</td>
                        </tr>)}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Common Error Examples' : 'Yaygın Hata Örnekleri'}</SubTitle>
                <div className="space-y-3">
                  <CodeBlock lang="json" code={`// 401 — Invalid API Key\n{"detail": "Geçersiz veya devre dışı API key"}\n\n// 403 — Agency Inactive\n{"detail": "Acente hesabı aktif değil"}\n\n// 400 — Bad Request\n{"detail": "check_out, check_in'den sonra olmalı"}\n{"detail": "Geçersiz durum. Geçerli: clean, dirty, inspected, maintenance, out_of_order"}\n{"detail": "operation must be 'add' or 'subtract'"}\n\n// 404 — Not Found\n{"detail": "Rezervasyon bulunamadı"}\n{"detail": "Misafir bulunamadı"}\n{"detail": "Oda bulunamadı"}\n\n// 409 — No Availability\n{"detail": "Bu tarihler ve oda tipi için müsait oda yok"}\n\n// 422 — Validation Error (Pydantic)\n{"detail": [{"loc": ["body", "amount"], "msg": "Input should be greater than 0", "type": "greater_than"}]}`} />
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Endpoint-specific error contract' : 'Endpoint bazında hata sözleşmesi'}</SubTitle>
                <div className="space-y-2 text-sm leading-6 text-slate-600">
                  <p><code>401</code> — {isEn ? 'Every endpoint: missing, invalid or revoked X-API-Key.' : 'Tüm endpoint’ler: eksik, geçersiz veya iptal edilmiş X-API-Key.'}</p>
                  <p><code>403</code> — {isEn ? 'Every endpoint: inactive agency, wrong hotel binding or missing required scope.' : 'Tüm endpoint’ler: pasif acente, yanlış otel bağlantısı veya eksik kapsam.'}</p>
                  <p><code>400</code> — <code>availability</code>, <code>reservations/{'{id}'}/cancel</code>, <code>groups/block</code>, <code>lost-found/{'{id}'}</code>, <code>housekeeping/rooms/{'{id}'}</code>, <code>folio/{'{id}'}/charge</code>, <code>wake-up-calls/{'{id}'}</code>, <code>webhooks</code>.</p>
                  <p><code>404</code> — {isEn ? 'Detail or mutation endpoints when the requested guest, reservation, room, group, report, folio, service, identity record, wake-up call or webhook is outside the key scope or does not exist.' : 'İstenen misafir, rezervasyon, oda, grup, rapor, folyo, hizmet, kimlik kaydı, uyandırma çağrısı veya webhook anahtar kapsamı dışında olduğunda ya da bulunmadığında ayrıntı/değişiklik endpoint’leri.'}</p>
                  <p><code>409</code> — <code>POST /reservations</code> ({isEn ? 'Idempotency-Key conflict or no inventory' : 'Idempotency-Key çakışması veya stok yokluğu'}); <code>POST /groups/{'{block_id}'}/rooming-list</code> ({isEn ? 'rooming-list conflict' : 'oda listesi çakışması'}).</p>
                  <p><code>422</code> — {isEn ? 'FastAPI validation for every typed body/query/path field before the handler runs. The response is the standard detail[] validation envelope.' : 'Handler çalışmadan önce tüm tipli gövde/sorgu/yol alanlarında FastAPI doğrulaması. Yanıt standart detail[] doğrulama zarfıdır.'}</p>
                  <p><code>429</code> — <code>POST /reservations</code> {isEn ? 'only while the same Idempotency-Key is in flight; Retry-After: 2.' : 'yalnızca aynı Idempotency-Key işlenmeye devam ederken; Retry-After: 2.'}</p>
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
              <Desc>{isEn ? 'This API version does not publish a fixed per-key quota. Handle 429 and 503 with Retry-After when present and exponential backoff otherwise.' : 'Bu API sürümü sabit bir anahtar kotası yayımlamaz. 429 ve 503 yanıtlarında varsa Retry-After başlığına uyun; yoksa üstel bekleme uygulayın.'}</Desc>

              <div className="mt-6">
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Endpoint Type' : 'Endpoint Tipi'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Rate Limit' : 'İstek Limiti'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Window' : 'Pencere'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Examples' : 'Örnekler'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[{
                      type: isEn ? 'Read (GET)' : 'Okuma (GET)',
                      limit: isEn ? 'Not guaranteed' : 'Garanti edilmez',
                      window: '—',
                      ex: 'availability, rates, reservations list, guests'
                    }, {
                      type: isEn ? 'Write (POST/PUT)' : 'Yazma (POST/PUT)',
                      limit: isEn ? 'Not guaranteed' : 'Garanti edilmez',
                      window: '—',
                      ex: 'create reservation, loyalty points, folio charge'
                    }, {
                      type: isEn ? 'Delete (DELETE)' : 'Silme (DELETE)',
                      limit: isEn ? 'Not guaranteed' : 'Garanti edilmez',
                      window: '—',
                      ex: 'cancel wake-up, delete webhook'
                    }, {
                      type: isEn ? 'Bulk Operations' : 'Toplu Islemler',
                      limit: isEn ? 'Not guaranteed' : 'Garanti edilmez',
                      window: '—',
                      ex: 'rooming-list upload, KBS report'
                    }].map((r, i) => <tr key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.type}</td>
                          <td className="px-4 py-2.5"><span className="font-mono font-bold text-[#C09D63]">{r.limit}</span> {isEn ? 'requests' : 'istek'}</td>
                          <td className="px-4 py-2.5 text-slate-500">{r.window}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs font-mono">{r.ex}</td>
                        </tr>)}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Retry contract' : 'Tekrar deneme sözleşmesi'}</SubTitle>
                <p className="text-sm text-slate-600 mb-3">{isEn ? 'X-RateLimit-* headers are not part of the current API contract. Do not build quota accounting around them. Use Retry-After only when it is actually returned.' : 'X-RateLimit-* başlıkları mevcut API sözleşmesinin parçası değildir; kota hesabını bu başlıklara bağlamayın. Retry-After başlığını yalnızca gerçekten döndüğünde kullanın.'}</p>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Handling 429 Too Many Requests' : '429 Cok Fazla İstek Yönetimi'}</SubTitle>
                <CodeBlock lang="python" code={`import time\nimport requests\n\ndef api_call_with_retry(url, headers, max_retries=3):\n    for attempt in range(max_retries):\n        resp = requests.get(url, headers=headers)\n        if resp.status_code == 429:\n            retry_after = int(resp.headers.get("Retry-After", 60))\n            print(f"Rate limited. Retrying in {retry_after}s...")\n            time.sleep(retry_after)\n            continue\n        return resp\n    raise Exception("Max retries exceeded")`} />
              </div>
            </section>

            {/* ── PAGINATION ── */}
            <section id="pagination">
              <SectionHeader icon={List} title={isEn ? 'Pagination & Filtering' : 'Sayfalama & Filtreleme'} id="pag-h" />
              <Desc>{isEn ? 'Collection endpoints use endpoint-specific filters and limits. Only the endpoints listed below accept a client-supplied limit; response counters also vary by endpoint.' : 'Koleksiyon endpoint\'leri endpoint\'e özel filtreler ve limitler kullanır. Yalnızca aşağıda belirtilen endpoint\'ler istemciden limit kabul eder; yanıt sayaçlarının adı da endpoint\'e göre değişir.'}</Desc>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Pagination Parameters' : 'Sayfalama Parametreleri'}</SubTitle>
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.parameter")}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.type")}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Default' : 'Varsayilan'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Description' : 'Açıklama'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[{
                      name: 'limit',
                      type: 'integer',
                      def: isEn ? 'Endpoint-specific' : 'Endpoint\'e özel',
                      desc: isEn ? 'Supported only by the endpoints listed below; there is no offset or cursor contract' : 'Yalnızca aşağıdaki endpoint\'lerde desteklenir; offset veya cursor sözleşmesi yoktur'
                    }, {
                      name: 'status',
                      type: 'string',
                      def: isEn ? 'All statuses' : 'Tüm durumlar',
                      desc: isEn ? 'Filter by status (varies per endpoint)' : 'Duruma göre filtre (endpoint\'e göre değişir)'
                    }, {
                      name: 'date',
                      type: 'string',
                      def: isEn ? 'Today' : 'Bugün',
                      desc: isEn ? 'Filter by date (YYYY-MM-DD)' : 'Tarihe göre filtre (YYYY-MM-DD)'
                    }].map((p, i) => <tr key={p.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-mono text-[13px] text-emerald-700">{p.name}</td>
                          <td className="px-4 py-2.5 text-slate-500 font-mono text-[13px]">{p.type}</td>
                          <td className="px-4 py-2.5 text-slate-500">{p.def}</td>
                          <td className="px-4 py-2.5 text-slate-600">{p.desc}</td>
                        </tr>)}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Response Structure' : 'Yanıt Yapısı'}</SubTitle>
                <p className="text-sm text-slate-600 mb-3">{isEn ? 'Most filtered list endpoints return count, but this is not a universal envelope. For example, KBS uses guest_count/report_count and service catalogues return only services. Follow the response schema documented for each endpoint.' : 'Filtreli liste endpoint\'lerinin çoğu count döndürür; ancak bu evrensel bir yanıt zarfı değildir. Örneğin KBS guest_count/report_count kullanır, hizmet katalogları yalnızca services döndürür. Her endpoint için belgelenen yanıt şemasını esas alın.'}</p>
                <CodeBlock lang="json" code={`// GET /api/b2b/reservations?status=confirmed&limit=50\n{\n  "reservations": [\n    { "id": "abc...", "guest_name": "John Doe", ... },\n    { "id": "def...", "guest_name": "Jane Smith", ... }\n  ],\n  "count": 2\n}\n\n// GET /api/b2b/wake-up-calls?date=2026-07-01\n{\n  "wake_up_calls": [...],\n  "count": 5\n}\n\n// GET /api/b2b/lost-found?status=found&category=electronics\n{\n  "items": [...],\n  "count": 3\n}`} />
              </div>

              <div className="mt-6">
                <SubTitle>{isEn ? 'Client-supplied limits per endpoint' : 'Endpoint bazında istemci limitleri'}</SubTitle>
                <div className="overflow-x-auto rounded-lg border border-slate-200 mt-3">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{t("cm.pages_B2BApiDocs.endpoint")}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Default Limit' : 'Varsayilan Limit'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Max Limit' : 'Maks Limit'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Available Filters' : 'Mevcut Filtreler'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[{
                      ep: '/reservations',
                      def: '100',
                      max: '500',
                      filters: 'status, check_in_from, check_in_to'
                    }, {
                      ep: '/guests/search',
                      def: '20',
                      max: '100',
                      filters: 'q (search query)'
                    }, {
                      ep: '/guests/{id}/stays',
                      def: '50',
                      max: '200',
                      filters: '-'
                    }, {
                      ep: '/kbs/guests',
                      def: '100',
                      max: '500',
                      filters: 'date, status'
                    }, {
                      ep: '/lost-found',
                      def: '50',
                      max: '200',
                      filters: 'status, category'
                    }, {
                      ep: '/guest-journey/requests',
                      def: '50',
                      max: '200',
                      filters: 'booking_id, status, request_type'
                    }, {
                      ep: '/groups',
                      def: '50',
                      max: '200',
                      filters: 'status'
                    }].map((r, i) => <tr key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-mono text-[12px] text-emerald-700">{r.ep}</td>
                          <td className="px-4 py-2.5 text-slate-700">{r.def}</td>
                          <td className="px-4 py-2.5 text-slate-700">{r.max}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs font-mono">{r.filters}</td>
                        </tr>)}
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
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Example' : 'Örnek'}</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-700">{isEn ? 'Used In' : 'Kullanildigi Yer'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[{
                      type: isEn ? 'Date' : 'Tarih',
                      format: 'YYYY-MM-DD',
                      example: '2026-07-15',
                      used: 'check_in, check_out, wake_date, preferred_date'
                    }, {
                      type: isEn ? 'Time' : 'Saat',
                      format: 'HH:MM',
                      example: '07:30',
                      used: 'wake_time, preferred_time, arrival_time'
                    }, {
                      type: isEn ? 'Timestamp' : 'Zaman Damgasi',
                      format: 'ISO 8601',
                      example: '2026-07-15T14:30:00+00:00',
                      used: 'created_at, updated_at (response only)'
                    }].map((r, i) => <tr key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                          <td className="px-4 py-2.5 font-medium text-slate-700">{r.type}</td>
                          <td className="px-4 py-2.5 font-mono text-[13px] text-emerald-700">{r.format}</td>
                          <td className="px-4 py-2.5 font-mono text-[13px] text-slate-600">{r.example}</td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs">{r.used}</td>
                        </tr>)}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>

            {/* ── CONTENT ── */}
            <section id="content">
              <SectionHeader icon={Hotel} title={isEn ? 'Content API' : 'İçerik API'} id="content-h" />
              <Desc>{isEn ? 'Retrieve hotel content including room types, services, and property information.' : 'Oda tipleri, hizmetler ve tesis bilgileri dahil otel icerigini getirin.'}</Desc>
              <div className="mt-6 space-y-3">
                <EndpointBlock method="GET" path="/api/b2b/hotel-info" desc={isEn ? 'Get the integration hotel identity and basic profile.' : 'Entegrasyon anahtarının bağlı olduğu otelin kimliğini ve temel profilini getirir.'}>
                  <CodeBlock lang="json" code={`{\n  "tenant_id": "hotel-tenant-id",\n  "hotel": {\n    "name": "Grand Palace Hotel",\n    "currency": "TRY",\n    "country": "TR",\n    "city": "Istanbul",\n    "address": "...",\n    "phone": "+90212...",\n    "email": "hotel@example.com",\n    "website": "https://hotel.example.com",\n    "timezone": "Europe/Istanbul",\n    "property_type": "hotel",\n    "star_rating": 5\n  },\n  "agency": {\n    "id": "agency-id",\n    "name": "Example Travel",\n    "commission_rate": 12\n  },\n  "room_types": [\n    { "room_type": "Deluxe Double", "capacity": 3, "base_price": 250,\n      "bed_type": "double", "total_rooms": 10 }\n  ],\n  "content_published": true\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/content" desc={isEn ? 'No parameters required.' : 'Parametre gerektirmez.'}>
                  <CodeBlock lang="json" code={`{\n  "published": true,\n  "hotel_content": {\n    "hotel_name": "Grand Palace Hotel",\n    "star_rating": 5,\n    "room_types": [...],\n    "services": [...]\n  }\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── AVAILABILITY ── */}
            <section id="availability">
              <SectionHeader icon={Calendar} title={isEn ? 'Availability API' : 'Müsaitlik API'} id="avail-h" />
              <Desc>{isEn ? 'Check real-time room availability for specified dates.' : 'Belirtilen tarihler için gerçek zamanlı oda müsaitliğini kontrol edin.'}</Desc>
              <div className="mt-6">
                <EndpointBlock method="GET" path="/api/b2b/availability">
                  <ParamTable lang={lang} params={[{
                  name: 'check_in',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Check-in date (YYYY-MM-DD)' : 'Giriş tarihi (YYYY-MM-DD)'
                }, {
                  name: 'check_out',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Check-out date (YYYY-MM-DD)' : 'Çıkış tarihi (YYYY-MM-DD)'
                }, {
                  name: 'room_type',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Filter by room type' : 'Oda tipine göre filtre'
                }]} />
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
                  <ParamTable lang={lang} params={[{
                  name: 'start_date',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Start date (YYYY-MM-DD)' : 'Başlangıç tarihi (YYYY-MM-DD)'
                }, {
                  name: 'end_date',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'End date (YYYY-MM-DD)' : 'Bitis tarihi (YYYY-MM-DD)'
                }, {
                  name: 'room_type',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Filter by room type' : 'Oda tipine göre filtre'
                }]} />
                  <CodeBlock lang="json" code={`{\n  "start_date": "2026-06-01",\n  "end_date": "2026-06-03",\n  "source": "agency_rates",\n  "rates": [\n    { "date": "2026-06-01", "room_type_code": "DLX",\n      "single": 200, "double": 250, "triple": 300 }\n  ]\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── RESERVATIONS ── */}
            <section id="reservations">
              <SectionHeader icon={FileText} title={isEn ? 'Reservations API' : 'Rezervasyon API'} id="res-h" />
              <Desc>{isEn ? 'Create, list, view, and cancel reservations. All bookings automatically sync with PMS.' : 'Rezervasyon oluşturun, listeleyin, görüntüleyin ve iptal edin. Otomatik PMS senkronizasyonu.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/reservations" desc={isEn ? 'Create a reservation with auto room assignment' : 'Otomatik oda atamali rezervasyon oluştur'}>
                  <p className="text-sm text-slate-600">{isEn ? 'For safe retries, send a stable Idempotency-Key header. Reusing the key with a different body returns 409; a concurrent in-flight retry returns 429 with Retry-After: 2.' : 'Güvenli tekrar denemeleri için sabit bir Idempotency-Key başlığı gönderin. Aynı anahtarın farklı gövdeyle kullanılması 409; eşzamanlı devam eden tekrar ise Retry-After: 2 ile 429 döndürür.'}</p>
                  <CodeBlock lang="http" code="Idempotency-Key: reservation-attempt-7f95d3a2" />
                  <ParamTable lang={lang} params={[{
                  name: 'room_type',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Room type name' : 'Oda tipi adi'
                }, {
                  name: 'check_in',
                  type: 'string',
                  required: true,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'check_out',
                  type: 'string',
                  required: true,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'guest_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Full guest name' : 'Misafir tam adi'
                }, {
                  name: 'guest_email',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Guest email' : 'E-posta'
                }, {
                  name: 'guest_phone',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Guest phone' : 'Telefon'
                }, {
                  name: 'adults',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Adults (default: 2)' : 'Yetiskin (varsayilan: 2)'
                }, {
                  name: 'children',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Children (default: 0)' : 'Cocuk (varsayilan: 0)'
                }, {
                  name: 'special_requests',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Guest notes and special requests' : 'Misafir notları ve özel talepler'
                }, {
                  name: 'total_amount',
                  type: 'number',
                  required: false,
                  desc: isEn ? 'Total price (0 = auto)' : 'Toplam fiyat (0 = otomatik)'
                }]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "reservation": {\n    "id": "a1b2c3d4-...",\n    "confirmation_code": "B2B-A1B2C3D4",\n    "status": "confirmed",\n    "room_type": "Deluxe Double",\n    "room_number": "204",\n    "check_in": "2026-06-01",\n    "check_out": "2026-06-03",\n    "guest_name": "John Doe",\n    "total_amount": 750.00,\n    "commission_rate": 12,\n    "commission_amount": 90.00,\n    "created_at": "2026-05-20T12:00:00+00:00"\n  },\n  "message": "Rezervasyon olusturuldu: B2B-A1B2C3D4"\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/reservations" desc={isEn ? 'List reservations with filters' : 'Filtreyle rezervasyon listele'}>
                  <ParamTable lang={lang} params={[{
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'confirmed, cancelled, checked_in, checked_out'
                }, {
                  name: 'check_in_from',
                  type: 'string',
                  required: false,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'check_in_to',
                  type: 'string',
                  required: false,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'limit',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Max results (default 100, max 500)' : 'Maks sonuc (varsayilan 100, maks 500)'
                }]} />
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
                <EndpointBlock method="GET" path="/api/b2b/guests/search" desc={isEn ? 'Search by name, email, or phone using the q query parameter (min 2 chars).' : 'q sorgu parametresiyle isim, e-posta veya telefon arayın (en az 2 karakter).'}>
                  <ParamTable lang={lang} params={[{
                  name: 'q',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Search query (name, email, phone)' : 'Arama sorgusu (isim, e-posta, telefon)'
                }, {
                  name: 'limit',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Max results (default 20)' : 'Maks sonuc (varsayilan 20)'
                }]} />
                  <CodeBlock lang="json" code={`{\n  "guests": [\n    { "id": "g1...", "name": "John Doe", "email": "john@example.com",\n      "phone": "+90555...", "vip_status": true, "loyalty_points": 5200 }\n  ],\n  "count": 1\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/guests/{guest_id}" desc={isEn ? 'Get full guest profile' : 'Tam misafir profili'} />
                <EndpointBlock method="GET" path="/api/b2b/guests/{guest_id}/stays" desc={isEn ? 'Get guest stay history' : 'Misafir konaklama gecmisi'}>
                  <ParamTable lang={lang} params={[{
                  name: 'limit',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Max results (default 50)' : 'Maks sonuc (varsayilan 50)'
                }]} />
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
                  <ParamTable lang={lang} params={[{
                  name: 'points',
                  type: 'int',
                  required: true,
                  desc: isEn ? 'Points amount' : 'Puan miktari'
                }, {
                  name: 'reason',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Reason for the change' : 'Degisiklik nedeni'
                }, {
                  name: 'operation',
                  type: 'string',
                  required: false,
                  desc: isEn ? '"add" (default) or "subtract"' : '"add" (varsayilan) veya "subtract"'
                }]} />
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
                  <ParamTable lang={lang} params={[{
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'clean, dirty, inspected, maintenance, out_of_order'
                }, {
                  name: 'floor',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Filter by floor' : 'Kata göre filtre'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="PUT" path="/api/b2b/housekeeping/rooms/{room_id}" desc={isEn ? 'Update room cleaning status' : 'Oda temizlik durumu guncelle'}>
                  <ParamTable lang={lang} params={[{
                  name: 'status',
                  type: 'string',
                  required: true,
                  desc: 'clean, dirty, inspected, maintenance, out_of_order'
                }, {
                  name: 'notes',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Optional notes' : 'Opsiyonel notlar'
                }]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── KBS ── */}
            <section id="kbs">
              <SectionHeader icon={Shield} title={isEn ? 'KBS / Police Notification' : 'KBS / Emniyet Bildirimi'} id="kbs-h" />
              <Desc>{isEn ? 'Access guest registration data for KBS (police notification system). List checked-in guests with identity information and submit reports.' : 'KBS (emniyet bildirim sistemi) için misafir kayıt verilerine erişin. Check-in yapan misafirleri kimlik bilgileriyle listeleyin ve rapor gönderin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/kbs/guests" desc={isEn ? 'Get guests for KBS reporting with identity data' : 'KBS bildirimi için misafir listesi ve kimlik bilgileri'}>
                  <ParamTable lang={lang} params={[{
                  name: 'date',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Date (YYYY-MM-DD, default: today)' : 'Tarih (YYYY-MM-DD, varsayilan: bugün)'
                }, {
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Filters returned reports: pending, submitted, confirmed, error' : 'Dönen raporları filtreler: pending, submitted, confirmed, error'
                }, {
                  name: 'limit',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Max results (default 100, max 500)' : 'Maksimum sonuç (varsayılan 100, en fazla 500)'
                }]} />
                  <CodeBlock lang="json" code={`{\n  "date": "2026-06-01",\n  "guests": [\n    { "id": "b1...", "guest_name": "Ali Yilmaz", "room_number": "302",\n      "check_in": "2026-06-01T14:00:00", "nationality": "TR",\n      "id_number": "12345678901", "passport_number": "",\n      "birth_date": "1985-03-15", "gender": "M" }\n  ],\n  "guest_count": 1,\n  "reports": [],\n  "report_count": 0\n}`} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/kbs/report" desc={isEn ? 'Submit a KBS report' : 'KBS bildirimi oluştur'}>
                  <ParamTable lang={lang} params={[{
                  name: 'date',
                  type: 'string',
                  required: true,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'guest_ids',
                  type: 'array',
                  required: false,
                  desc: isEn ? 'List of guest/booking IDs' : 'Misafir/rezervasyon ID listesi'
                }, {
                  name: 'notes',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Report notes' : 'Rapor notlari'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/kbs/report/{report_id}" desc={isEn ? 'Get KBS report detail' : 'KBS rapor detayi'} />
              </div>
            </section>

            {/* ── IDENTITY / PASSPORT ── */}
            <section id="identity">
              <SectionHeader icon={Fingerprint} title={isEn ? 'Passport / ID Scanning' : 'Pasaport / Kimlik Okuma'} id="id-h" />
              <Desc>{isEn ? 'Store passport/ID OCR results for a guest who has a current or recent reservation owned by this agency. The scan remains agency-scoped and does not overwrite the hotel-wide guest profile.' : 'Bu acenteye ait güncel veya yakın tarihli rezervasyonu bulunan misafir için pasaport/kimlik OCR sonucunu saklar. Tarama acente kapsamında kalır ve otelin ortak misafir profilinin üzerine yazmaz.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/identity/scan" desc={isEn ? 'Submit an agency-scoped OCR scan; hotel staff must verify shared profile changes' : 'Acente kapsamlı OCR taraması gönderir; ortak profil değişikliklerini otel personeli doğrulamalıdır'}>
                  <ParamTable lang={lang} params={[{
                  name: 'guest_id',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Guest ID' : 'Misafir ID'
                }, {
                  name: 'scan_type',
                  type: 'string',
                  required: true,
                  desc: 'passport, id_card, driving_license'
                }, {
                  name: 'document_number',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Document number' : 'Belge numarasi'
                }, {
                  name: 'first_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'First name from document' : 'Belgedeki ad'
                }, {
                  name: 'last_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Last name from document' : 'Belgedeki soyad'
                }, {
                  name: 'nationality',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Nationality code (TR, DE, US...)' : 'Ülke kodu (TR, DE, US...)'
                }, {
                  name: 'birth_date',
                  type: 'string',
                  required: false,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'gender',
                  type: 'string',
                  required: false,
                  desc: 'M, F'
                }, {
                  name: 'expiry_date',
                  type: 'string',
                  required: false,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'issuing_country',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Issuing country' : 'Veren ulke'
                }, {
                  name: 'mrz_line1',
                  type: 'string',
                  required: false,
                  desc: 'MRZ Line 1'
                }, {
                  name: 'mrz_line2',
                  type: 'string',
                  required: false,
                  desc: 'MRZ Line 2'
                }, {
                  name: 'scan_quality',
                  type: 'number',
                  required: false,
                  desc: isEn ? 'Quality score 0-100 (auto-verify if >= 80)' : 'Kalite skoru 0-100 (>=80 otomatik doğrulama)'
                }, {
                  name: 'raw_ocr_data',
                  type: 'object',
                  required: false,
                  desc: isEn ? 'Raw OCR JSON data' : 'Ham OCR JSON verisi'
                }]} />
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
                  <ParamTable lang={lang} params={[{
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'found, claimed, returned, disposed'
                }, {
                  name: 'category',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Item category' : 'Esya kategorisi'
                }, {
                  name: 'limit',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Max results (default 50, max 200)' : 'Maksimum sonuç (varsayılan 50, en fazla 200)'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/lost-found" desc={isEn ? 'Register a found item' : 'Bulunan esya kaydet'}>
                  <ParamTable lang={lang} params={[{
                  name: 'item_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Item name' : 'Esya adi'
                }, {
                  name: 'description',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Description' : 'Açıklama'
                }, {
                  name: 'category',
                  type: 'string',
                  required: false,
                  desc: 'electronics, clothing, jewelry, documents, other'
                }, {
                  name: 'location_found',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Where found' : 'Bulundugu yer'
                }, {
                  name: 'found_by',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Name of the person or employee who found it' : 'Eşyayı bulan kişi veya çalışan'
                }, {
                  name: 'guest_name',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Related guest name, when known' : 'Biliniyorsa ilişkili misafir adı'
                }, {
                  name: 'room_number',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Room number' : 'Oda numarasi'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="PUT" path="/api/b2b/lost-found/{item_id}" desc={isEn ? 'Update item status' : 'Esya durumu guncelle'}>
                  <ParamTable lang={lang} params={[{
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'found, claimed, returned, disposed'
                }, {
                  name: 'guest_name',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Related guest name' : 'İlişkili misafir adı'
                }, {
                  name: 'claimed_by',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Claimed by (guest name)' : 'Teslim alan (misafir adi)'
                }, {
                  name: 'notes',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Notes' : 'Notlar'
                }]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── WAKE-UP CALLS ── */}
            <section id="wakeup">
              <SectionHeader icon={Phone} title={isEn ? 'Wake-up Calls' : 'Uyandırma Servisi'} id="wu-h" />
              <Desc>{isEn ? 'Create and manage wake-up call requests for guests.' : 'Misafirler için uyandırma talepleri oluşturun ve yönetin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/wake-up-calls" desc={isEn ? 'List wake-up calls' : 'Uyandırma listesi'}>
                  <ParamTable lang={lang} params={[{
                  name: 'date',
                  type: 'string',
                  required: false,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'pending, completed, cancelled, missed'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/wake-up-calls" desc={isEn ? 'Create wake-up call' : 'Uyandırma oluştur'}>
                  <ParamTable lang={lang} params={[{
                  name: 'room_number',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Room number' : 'Oda numarasi'
                }, {
                  name: 'guest_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Guest name' : 'Misafir adi'
                }, {
                  name: 'wake_date',
                  type: 'string',
                  required: true,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'wake_time',
                  type: 'string',
                  required: true,
                  desc: 'HH:MM'
                }, {
                  name: 'recurring',
                  type: 'boolean',
                  required: false,
                  desc: isEn ? 'Repeat daily' : 'Her gün tekrarla'
                }, {
                  name: 'recurring_until',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Last recurrence date (YYYY-MM-DD)' : 'Son tekrar tarihi (YYYY-MM-DD)'
                }, {
                  name: 'notes',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Operational notes' : 'Operasyon notları'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="PUT" path="/api/b2b/wake-up-calls/{call_id}" desc={isEn ? 'Update wake-up call' : 'Uyandırma guncelle'}>
                  <ParamTable lang={lang} params={[{
                  name: 'wake_time',
                  type: 'string',
                  required: false,
                  desc: 'HH:MM'
                }, {
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'pending, completed, cancelled, missed'
                }, {
                  name: 'notes',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Operational notes' : 'Operasyon notları'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="DELETE" path="/api/b2b/wake-up-calls/{call_id}" desc={isEn ? 'Cancel wake-up call' : 'Uyandırma iptal'} />
              </div>
            </section>

            {/* ── GUEST JOURNEY ── */}
            <section id="journey">
              <SectionHeader icon={Globe} title={isEn ? 'Guest Journey' : 'Misafir Yolculugu'} id="gj-h" />
              <Desc>{isEn ? 'Online check-in, pre-arrival management, and guest service requests.' : 'Online check-in, pre-arrival yönetimi ve misafir servis talepleri.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/guest-journey/online-checkin" desc={isEn ? 'Submit online check-in data' : 'Online check-in bilgilerini gonder'}>
                  <ParamTable lang={lang} params={[{
                  name: 'booking_id',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Booking ID' : 'Rezervasyon ID'
                }, {
                  name: 'arrival_time',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Expected arrival time' : 'Beklenen varis zamani'
                }, {
                  name: 'flight_number',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Flight number' : 'Ucus numarasi'
                }, {
                  name: 'room_preference',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Guest room preference' : 'Misafirin oda tercihi'
                }, {
                  name: 'special_requests',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Pre-arrival special requests' : 'Varış öncesi özel talepler'
                }, {
                  name: 'passport_number',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Passport number (auto-updates guest)' : 'Pasaport no (otomatik profil gunceller)'
                }, {
                  name: 'nationality',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Nationality code' : 'Uyruk kodu'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/guest-journey/pre-arrival/{booking_id}" desc={isEn ? 'Get pre-arrival status' : 'Pre-arrival durumu sorgula'} />
                <EndpointBlock method="POST" path="/api/b2b/guest-journey/request" desc={isEn ? 'Create a service request' : 'Servis talebi oluştur'}>
                  <ParamTable lang={lang} params={[{
                  name: 'booking_id',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Booking ID' : 'Rezervasyon ID'
                }, {
                  name: 'request_type',
                  type: 'string',
                  required: true,
                  desc: 'concierge, spa, room_service, maintenance, transport, other'
                }, {
                  name: 'description',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Request description' : 'Talep aciklamasi'
                }, {
                  name: 'priority',
                  type: 'string',
                  required: false,
                  desc: 'low, normal, high, urgent'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/guest-journey/requests" desc={isEn ? 'List service requests with filters' : 'Servis taleplerini filtreli listele'}>
                  <ParamTable lang={lang} params={[{
                  name: 'booking_id',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Filter by booking' : 'Rezervasyona göre filtre'
                }, {
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'pending, in_progress, completed, cancelled'
                }, {
                  name: 'request_type',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Filter by type' : 'Tipe göre filtre'
                }, {
                  name: 'limit',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Max results (default 50, max 200)' : 'Maksimum sonuç (varsayılan 50, en fazla 200)'
                }]} />
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
                  <ParamTable lang={lang} params={[{
                  name: 'booking_id',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Booking ID' : 'Rezervasyon ID'
                }, {
                  name: 'service_id',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Service ID from /concierge/services' : '/concierge/services\'ten gelen hizmet ID'
                }, {
                  name: 'description',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Additional details' : 'Ek detaylar'
                }, {
                  name: 'preferred_date',
                  type: 'string',
                  required: false,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'preferred_time',
                  type: 'string',
                  required: false,
                  desc: 'HH:MM'
                }, {
                  name: 'guest_count',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Number of guests (default 1)' : 'Misafir sayısı (varsayılan 1)'
                }]} />
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
                  <ParamTable lang={lang} params={[{
                  name: 'booking_id',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Hotel booking ID' : 'Otel rezervasyon ID'
                }, {
                  name: 'service_id',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Service ID from /spa/services' : '/spa/services\'ten gelen hizmet ID'
                }, {
                  name: 'preferred_date',
                  type: 'string',
                  required: true,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'preferred_time',
                  type: 'string',
                  required: true,
                  desc: 'HH:MM'
                }, {
                  name: 'guest_count',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Number of guests (default: 1)' : 'Misafir sayısı (varsayilan: 1)'
                }, {
                  name: 'notes',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Special requests' : 'Özel istekler'
                }]} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── MICE & GROUPS ── */}
            <section id="groups">
              <SectionHeader icon={Building} title={isEn ? 'MICE & Groups' : 'MICE & Grup Yönetimi'} id="grp-h" />
              <Desc>{isEn ? 'Manage group blocks, rooming lists, and MICE events (conferences, weddings, corporate events).' : 'Grup bloklari, rooming listleri ve MICE etkinliklerini (konferans, dugun, kurumsal) yönetin.'}</Desc>
              <div className="mt-6 space-y-6">
                <EndpointBlock method="GET" path="/api/b2b/groups" desc={isEn ? 'List group blocks' : 'Grup bloklari listele'}>
                  <ParamTable lang={lang} params={[{
                  name: 'status',
                  type: 'string',
                  required: false,
                  desc: 'tentative, confirmed, cancelled'
                }, {
                  name: 'limit',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Max results (default 50, max 200)' : 'Maksimum sonuç (varsayılan 50, en fazla 200)'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="POST" path="/api/b2b/groups/block" desc={isEn ? 'Create a group block' : 'Grup blok oluştur'}>
                  <ParamTable lang={lang} params={[{
                  name: 'group_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Group/event name' : 'Grup/etkinlik adi'
                }, {
                  name: 'contact_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Contact person' : 'Irtibat kisisi'
                }, {
                  name: 'contact_email',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Contact email' : 'İrtibat e-postası'
                }, {
                  name: 'contact_phone',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Contact phone' : 'İrtibat telefonu'
                }, {
                  name: 'check_in',
                  type: 'string',
                  required: true,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'check_out',
                  type: 'string',
                  required: true,
                  desc: 'YYYY-MM-DD'
                }, {
                  name: 'rooms_requested',
                  type: 'int',
                  required: true,
                  desc: isEn ? 'Number of rooms needed' : 'Gereken oda sayısı'
                }, {
                  name: 'event_type',
                  type: 'string',
                  required: false,
                  desc: 'conference, wedding, corporate, tour_group, other'
                }, {
                  name: 'room_type',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Preferred room type' : 'Tercih edilen oda tipi'
                }, {
                  name: 'estimated_revenue',
                  type: 'number',
                  required: false,
                  desc: isEn ? 'Estimated group revenue (default 0)' : 'Tahmini grup geliri (varsayılan 0)'
                }, {
                  name: 'notes',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Group notes' : 'Grup notları'
                }]} />
                  <CodeBlock lang="json" code={`{\n  "ok": true,\n  "block": {\n    "id": "blk1...",\n    "group_name": "Tech Conference 2026",\n    "rooms_requested": 50,\n    "rooms_picked_up": 0,\n    "status": "tentative"\n  }\n}`} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/groups/{block_id}" desc={isEn ? 'Get block details with rooming list' : 'Blok detayi ve rooming list'} />
                <EndpointBlock method="POST" path="/api/b2b/groups/{block_id}/rooming-list" desc={isEn ? 'Upload bulk guest list — creates reservations automatically' : 'Toplu misafir listesi yukle — otomatik rezervasyon oluşturur'}>
                  <ParamTable lang={lang} params={[{
                  name: 'guests',
                  type: 'array',
                  required: true,
                  desc: isEn ? 'Array of guest entries' : 'Misafir kayitlari dizisi'
                }, {
                  name: 'guests[].guest_name',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Guest full name' : 'Misafir tam adi'
                }, {
                  name: 'guests[].room_type',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Override room type' : 'Oda tipi (override)'
                }, {
                  name: 'guests[].check_in',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Override check-in (default: block dates)' : 'Giriş tarihi (varsayilan: blok tarihi)'
                }, {
                  name: 'guests[].check_out',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Override check-out' : 'Çıkış tarihi'
                }, {
                  name: 'guests[].special_requests',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Guest-specific requests' : 'Misafire özel talepler'
                }]} />
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
                  <ParamTable lang={lang} params={[{
                  name: 'charge_type',
                  type: 'string',
                  required: true,
                  desc: 'room, minibar, restaurant, spa, laundry, phone, other'
                }, {
                  name: 'description',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'Charge description' : 'Masraf aciklamasi'
                }, {
                  name: 'amount',
                  type: 'number',
                  required: true,
                  desc: isEn ? 'Unit price' : 'Birim fiyat'
                }, {
                  name: 'quantity',
                  type: 'int',
                  required: false,
                  desc: isEn ? 'Quantity (default: 1)' : 'Adet (varsayilan: 1)'
                }]} />
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/folio/{booking_id}/invoice" desc={isEn ? 'Generate invoice (JSON format)' : 'Fatura oluştur (JSON formatında)'}>
                  <CodeBlock lang="json" code={`{\n  "invoice_number": "INV-A1B2C3D4",\n  "invoice_date": "2026-06-03",\n  "hotel": { "hotel_name": "Grand Palace", "tax_number": "123..." },\n  "guest_name": "John Doe",\n  "check_in": "2026-06-01", "check_out": "2026-06-03",\n  "charges": [...],\n  "subtotal": 535.00,\n  "total_paid": 500.00,\n  "balance_due": 35.00,\n  "currency": "TRY"\n}`} />
                </EndpointBlock>
              </div>
            </section>

            {/* ── WEBHOOKS ── */}
            <section id="webhooks">
              <SectionHeader icon={Bell} title={t("cm.pages_B2BApiDocs.webhooks")} id="wh-h" />
              <Desc>{isEn ? 'Receive real-time notifications when events occur. Register webhook URLs and Syroce will POST event data with retry and dead-letter queue support.' : 'Olaylar gerceklestiginde gerçek zamanlı bildirimler alin. Webhook URL\'si kaydedin, Syroce olay verisini retry ve dead-letter queue destegi ile POST edecektir.'}</Desc>

              <div className="mt-6">
                <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">{isEn ? 'Supported Events' : 'Desteklenen Olaylar'}</h3>
                <div className="space-y-2">
                  {[{
                  name: 'reservation.created',
                  desc: isEn ? 'New reservation created' : 'Yeni rezervasyon oluşturuldu'
                }, {
                  name: 'reservation.cancelled',
                  desc: isEn ? 'Reservation cancelled' : 'Rezervasyon iptal edildi'
                }, {
                  name: 'reservation.updated',
                  desc: isEn ? 'Reservation status changed' : 'Rezervasyon durumu degisti'
                }, {
                  name: 'rates.updated',
                  desc: isEn ? 'Room rates changed' : 'Oda fiyatları güncellendi'
                }, {
                  name: 'availability.updated',
                  desc: isEn ? 'Room availability changed' : 'Oda müsaitliği güncellendi'
                }].map(ev => <div key={ev.name} className="flex items-center gap-3 bg-slate-50 rounded-lg px-4 py-3 border border-slate-200">
                      <code className="text-xs font-mono bg-white px-2 py-1 rounded border border-slate-200 text-[#C09D63] font-semibold">{ev.name}</code>
                      <span className="text-sm text-slate-600">{ev.desc}</span>
                    </div>)}
                </div>
              </div>

              <div className="mt-8 space-y-6">
                <EndpointBlock method="POST" path="/api/b2b/webhooks" desc={isEn ? 'Register webhook' : 'Webhook kaydet'}>
                  <ParamTable lang={lang} params={[{
                  name: 'url',
                  type: 'string',
                  required: true,
                  desc: isEn ? 'HTTPS endpoint URL' : 'HTTPS endpoint URL'
                }, {
                  name: 'events',
                  type: 'array',
                  required: true,
                  desc: isEn ? 'Event types to subscribe' : 'Abone olunacak olay tipleri'
                }, {
                  name: 'secret',
                  type: 'string',
                  required: false,
                  desc: isEn ? 'Signing secret for HMAC verification' : 'HMAC dogrulamasi için imzalama anahtari'
                }]} />
                  <CodeBlock lang="bash" code={`curl -X POST "${API_BASE}/webhooks" \\\n  -H "X-API-Key: syroce_b2b_your_key" \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "url": "https://your-app.com/webhook",\n    "events": ["reservation.created", "reservation.cancelled"],\n    "secret": "your_signing_secret"\n  }'`} />
                  <p className="mt-3 text-sm leading-6 text-slate-600">{isEn ? 'The URL must use public HTTPS and pass SSRF/DNS validation. An agency may have at most 5 active webhooks. If secret is omitted, Syroce generates one and returns it only in this registration response; store it immediately because list responses never expose it.' : 'URL herkese açık HTTPS kullanmalı ve SSRF/DNS doğrulamasından geçmelidir. Bir acentenin en fazla 5 aktif webhook\'u olabilir. secret gönderilmezse Syroce bir secret üretir ve yalnızca bu kayıt yanıtında bir kez döndürür; liste yanıtlarında gösterilmediği için hemen güvenli biçimde saklayın.'}</p>
                </EndpointBlock>
                <EndpointBlock method="GET" path="/api/b2b/webhooks" desc={isEn ? 'List your webhooks (signing secrets are never returned)' : 'Webhook listesi (imzalama secret değerleri döndürülmez)'} />
                <EndpointBlock method="DELETE" path="/api/b2b/webhooks/{webhook_id}" desc={isEn ? 'Delete webhook' : 'Webhook sil'} />
                <EndpointBlock method="POST" path="/api/b2b/webhooks/{webhook_id}/test" desc={isEn ? 'Send one immediate test delivery' : 'Tek seferlik anlık test olayı gönder'}>
                  <CodeBlock lang="json" code={`{
  "ok": true,
  "delivery_id": "d1e2f3a4-...",
  "status_code": 204,
  "error": null,
  "message": "Test olayi gonderildi"
}`} />
                  <p className="mt-3 text-sm leading-6 text-slate-600">{isEn ? 'The test endpoint performs one synchronous delivery and returns the receiver status. It includes X-Webhook-Event, X-Webhook-Delivery and, when configured, X-Webhook-Signature. Unlike production delivery, it does not retry, enter the dead-letter queue or send X-Idempotency-Key.' : 'Test endpoint’i tek bir eşzamanlı teslimat yapar ve alıcının durum kodunu döndürür. X-Webhook-Event, X-Webhook-Delivery ve yapılandırılmışsa X-Webhook-Signature başlıklarını gönderir. Üretim teslimatından farklı olarak tekrar denemez, başarısız teslimat kuyruğuna girmez ve X-Idempotency-Key göndermez.'}</p>
                </EndpointBlock>

                <div className="mt-6">
                  <SubTitle>{isEn ? 'Webhook Payload' : 'Webhook Payload'}</SubTitle>
                  <CodeBlock lang="json" code={`{\n  "event": "reservation.created",\n  "timestamp": "2026-06-01T14:30:00+00:00",\n  "delivery_id": "d1e2f3a4-...",\n  "idempotency_key": "abc123...",\n  "data": {\n    "reservation_id": "a1b2c3d4-...",\n    "confirmation_code": "B2B-A1B2C3D4",\n    "status": "confirmed",\n    "guest_name": "John Doe",\n    "total_amount": 750.00\n  }\n}`} />
                </div>

                <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 mt-4">
                  <h4 className="font-semibold text-amber-900 flex items-center gap-2 text-sm">
                    <Shield size={15} /> {isEn ? 'Signature Verification' : 'Imza Dogrulama'}
                  </h4>
                  <p className="text-sm text-amber-800 mt-2">{isEn ? 'Each delivery includes X-Webhook-Signature. Verify HMAC-SHA256 over the exact raw request body before JSON parsing:' : 'Her teslimat X-Webhook-Signature başlığını içerir. JSON ayrıştırmadan önce isteğin ham gövdesi üzerinden HMAC-SHA256 doğrulaması yapın:'}</p>
                  <p className="text-sm text-amber-800 mt-2">{isEn ? 'Use X-Webhook-Delivery and X-Idempotency-Key to deduplicate deliveries. Production deliveries are retried up to 5 times; return a 2xx response only after the event is durably accepted.' : 'Tekrarlanan teslimatları ayıklamak için X-Webhook-Delivery ve X-Idempotency-Key başlıklarını kullanın. Üretim teslimatları en fazla 5 kez denenir; yalnızca olayı kalıcı olarak kabul ettikten sonra 2xx döndürün.'}</p>
                  <div className="mt-3">
                    <CodeBlock lang="python" code={`import hmac, hashlib\n\ndef verify_signature(body, secret, sig_header):\n    expected = hmac.new(\n        secret.encode(), body, hashlib.sha256\n    ).hexdigest()\n    return hmac.compare_digest(f"sha256={expected}", sig_header)`} />
                    <CodeBlock lang="javascript" code={`import crypto from "node:crypto";

export function verifySyroceWebhook(rawBody, secret, signature) {
  const digest = crypto
    .createHmac("sha256", secret)
    .update(rawBody)
    .digest("hex");
  const expected = Buffer.from("sha256=" + digest);
  const received = Buffer.from(signature || "");
  return expected.length === received.length &&
    crypto.timingSafeEqual(expected, received);
}`} />
                  </div>
                </div>
              </div>
            </section>

            <section id="versioning">
              <SectionHeader icon={GitBranch} title={isEn ? 'Versioning and compatibility' : 'Sürümleme ve geriye uyumluluk'} id="versioning-h" />
              <div className="mt-4 space-y-3 text-sm leading-6 text-slate-700">
                <p>{isEn ? 'The current Hotel Integration contract uses /api/b2b. Additive fields and new optional endpoints may be released without changing this base path; clients must ignore unknown response fields.' : 'Mevcut Hotel Integration sözleşmesi /api/b2b temel yolunu kullanır. Yeni yanıt alanları ve isteğe bağlı endpoint’ler bu yol değiştirilmeden eklenebilir; istemciler tanımadıkları yanıt alanlarını yok saymalıdır.'}</p>
                <p>{isEn ? 'Removing or renaming a field, changing its type, making an optional request field required, or changing authentication semantics is a breaking change and requires a new versioned base path plus a published migration window.' : 'Bir alanı kaldırmak veya yeniden adlandırmak, türünü değiştirmek, isteğe bağlı bir istek alanını zorunlu yapmak ya da kimlik doğrulama anlamını değiştirmek geriye uyumsuz değişikliktir; yeni sürümlenmiş temel yol ve yayımlanmış geçiş süresi gerektirir.'}</p>
                <p>{isEn ? 'Deprecations are announced before removal. During the migration window both versions remain independently testable; credentials and scopes are never broadened automatically.' : 'Kullanımdan kaldırmalar silinmeden önce duyurulur. Geçiş süresince iki sürüm de bağımsız test edilebilir durumda tutulur; anahtar izinleri ve kapsamları hiçbir zaman otomatik genişletilmez.'}</p>
              </div>
            </section>

            <div className="border-t border-slate-200 pt-8 pb-16 text-center">
              <p className="text-sm text-slate-400">Syroce Hotel Integration API &middot; {isEn ? '12 permission-scoped API groups' : '12 yetki kapsamlı API grubu'} &middot; {new Date().getFullYear()}</p>
              <p className="text-xs text-slate-300 mt-1">{isEn ? 'Current contract — breaking changes require a new versioned base path' : 'Güncel sözleşme — geriye dönük uyumsuz değişiklikler yeni sürümlenmiş bir temel yol gerektirir'}</p>
            </div>
            </>}
          </div>
        </main>
      </div>
    </div>;
}
