import { t } from "i18next";
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";
const TABS = [{
  id: "currency",
  label: "Çoklu Döviz"
}, {
  id: "happyhour",
  label: "Happy Hour"
}, {
  id: "coupons",
  label: "Kuponlar"
}, {
  id: "loyalty",
  label: "Sadakat Puanı"
}, {
  id: "shifts",
  label: "Vardiya"
}, {
  id: "barcode",
  label: "Barkod"
}, {
  id: "print",
  label: "Fiş Yazıcı"
}, {
  id: "fiscal",
  label: "Mali Yazıcı"
}];
async function apiFetch(path, opts = {}) {
  const token = localStorage.getItem("access_token");
  const headers = {
    "Content-Type": "application/json",
    ...(opts.headers || {})
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, {
    ...opts,
    headers
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  return {
    status: res.status,
    ok: res.ok,
    body
  };
}
function Section({
  title,
  children
}) {
  return <div className="bg-white rounded-lg shadow p-5 mb-4">
      <h3 className="text-base font-semibold text-gray-900 mb-3">{title}</h3>
      {children}
    </div>;
}
function Input({
  label,
  value,
  onChange,
  type = "text",
  placeholder
}) {
  return <label className="block mb-2">
      <span className="block text-xs font-medium text-gray-700 mb-1">{label}</span>
      <input type={type} value={value ?? ""} onChange={e => onChange(e.target.value)} placeholder={placeholder} className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
    </label>;
}
function Btn({
  children,
  onClick,
  variant = "primary",
  disabled
}) {
  const base = "px-3 py-2 rounded text-sm font-medium transition disabled:opacity-50";
  const cls = variant === "primary" ? `${base} bg-gray-900 text-white hover:bg-gray-800` : variant === "outline" ? `${base} border border-gray-300 bg-white text-gray-800 hover:bg-gray-50` : `${base} bg-red-600 text-white hover:bg-red-700`;
  return <button type="button" onClick={onClick} disabled={disabled} className={cls}>{children}</button>;
}
function Json({
  data
}) {
  if (!data) return null;
  return <pre className="bg-gray-50 border rounded p-2 text-xs overflow-x-auto max-h-64">{JSON.stringify(data, null, 2)}</pre>;
}

// ── Tabs ────────────────────────────────────────────────────────────
function CurrencyTab() {
  const [code, setCode] = useState("USD");
  const [rate, setRate] = useState("32.5");
  const [rates, setRates] = useState([]);
  const [last, setLast] = useState(null);
  const load = useCallback(async () => {
    const r = await apiFetch("/api/pos/ext/currency/rates?limit=20");
    if (r.ok) setRates(r.body.rates || []);
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  return <>
      <Section title={t("cm.pages_POSExtensions.kur_tan\u0131mla")}>
        <Input label={t("cm.pages_POSExtensions.d\xF6viz_kodu")} value={code} onChange={setCode} placeholder={t("cm.pages_POSExtensions.usd_eur_gbp")} />
        <Input label={t("cm.pages_POSExtensions.try_kar\u015F\u0131l\u0131\u011F\u0131")} value={rate} onChange={setRate} type="number" />
        <div className="flex gap-2 mt-2">
          <Btn onClick={async () => {
          const r = await apiFetch("/api/pos/ext/currency/rates", {
            method: "POST",
            body: JSON.stringify({
              currency_code: code,
              rate_to_base: Number(rate)
            })
          });
          setLast(r);
          await load();
        }}>{t("cm.pages_POSExtensions.kaydet")}</Btn>
          <Btn variant="outline" onClick={load}><RefreshCw className="w-4 h-4 inline" />{t("cm.pages_POSExtensions.yenile")}</Btn>
        </div>
      </Section>
      <Section title={t("cm.pages_POSExtensions.tan\u0131ml\u0131_kurlar")}>
        <Json data={rates} />
      </Section>
      {last && <Section title={t("cm.pages_POSExtensions.son_i\u015Flem_yan\u0131t\u0131")}><Json data={last} /></Section>}
    </>;
}
function HappyHourTab() {
  const [name, setName] = useState("İndirimli Çay Saati");
  const [start, setStart] = useState("14:00");
  const [end, setEnd] = useState("17:00");
  const [pct, setPct] = useState("20");
  const [rules, setRules] = useState([]);
  const load = async () => {
    const r = await apiFetch("/api/pos/ext/happy-hour/rules");
    if (r.ok) setRules(r.body.rules || []);
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.kural_olu\u015Ftur")}>
        <Input label={t("cm.pages_POSExtensions.kural_ad\u0131")} value={name} onChange={setName} />
        <Input label={t("cm.pages_POSExtensions.ba\u015Flang\u0131\xE7_hh_mm")} value={start} onChange={setStart} />
        <Input label={t("cm.pages_POSExtensions.biti\u015F_hh_mm")} value={end} onChange={setEnd} />
        <Input label={t("cm.pages_POSExtensions.i_ndirim")} value={pct} onChange={setPct} type="number" />
        <Btn onClick={async () => {
        await apiFetch("/api/pos/ext/happy-hour/rules", {
          method: "POST",
          body: JSON.stringify({
            name,
            start_time: start,
            end_time: end,
            discount_type: "percent",
            discount_value: Number(pct),
            days_of_week: [0, 1, 2, 3, 4, 5, 6]
          })
        });
        await load();
      }}>{t("cm.pages_POSExtensions.kaydet")}</Btn>
      </Section>
      <Section title={t("cm.pages_POSExtensions.tan\u0131ml\u0131_kurallar")}><Json data={rules} /></Section>
    </>;
}
function CouponsTab() {
  const [code, setCode] = useState("WELCOME10");
  const [pct, setPct] = useState("10");
  const [coupons, setCoupons] = useState([]);
  const [validateAmount, setValidateAmount] = useState("100");
  const [last, setLast] = useState(null);
  const load = async () => {
    const r = await apiFetch("/api/pos/ext/coupons");
    if (r.ok) setCoupons(r.body.coupons || []);
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.kupon_olu\u015Ftur")}>
        <Input label={t("cm.pages_POSExtensions.kod")} value={code} onChange={setCode} />
        <Input label={t("cm.pages_POSExtensions.i_ndirim")} value={pct} onChange={setPct} type="number" />
        <Btn onClick={async () => {
        await apiFetch("/api/pos/ext/coupons", {
          method: "POST",
          body: JSON.stringify({
            code,
            discount_type: "percent",
            discount_value: Number(pct),
            max_uses: 100
          })
        });
        await load();
      }}>{t("cm.pages_POSExtensions.kaydet")}</Btn>
      </Section>
      <Section title={t("cm.pages_POSExtensions.do\u011Frula")}>
        <Input label={t("cm.pages_POSExtensions.tutar_tl")} value={validateAmount} onChange={setValidateAmount} type="number" />
        <Btn variant="outline" onClick={async () => {
        const r = await apiFetch("/api/pos/ext/coupons/validate", {
          method: "POST",
          body: JSON.stringify({
            code,
            amount: Number(validateAmount)
          })
        });
        setLast(r.body);
      }}>{t("cm.pages_POSExtensions.kontrol_et")}</Btn>
        {last && <Json data={last} />}
      </Section>
      <Section title={t("cm.pages_POSExtensions.tan\u0131ml\u0131_kuponlar")}><Json data={coupons} /></Section>
    </>;
}
function LoyaltyTab() {
  const [guestId, setGuestId] = useState("");
  const [balance, setBalance] = useState(null);
  const [settings, setSettings] = useState(null);
  const load = async () => {
    const s = await apiFetch("/api/pos/ext/loyalty/settings");
    if (s.ok) setSettings(s.body);
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.program_ayarlar\u0131")}><Json data={settings} /></Section>
      <Section title={t("cm.pages_POSExtensions.misafir_bakiyesi")}>
        <Input label={t("cm.pages_POSExtensions.misafir_id")} value={guestId} onChange={setGuestId} />
        <Btn variant="outline" onClick={async () => {
        const r = await apiFetch(`/api/pos/ext/loyalty/balance?guest_id=${encodeURIComponent(guestId)}`);
        setBalance(r.body);
      }}>{t("cm.pages_POSExtensions.bakiye_sorgula")}</Btn>
        {balance && <Json data={balance} />}
      </Section>
    </>;
}
function ShiftsTab() {
  const [outlet, setOutlet] = useState("MAIN");
  const [opening, setOpening] = useState("500");
  const [shifts, setShifts] = useState([]);
  const load = async () => {
    const r = await apiFetch("/api/pos/ext/shifts?limit=20");
    if (r.ok) setShifts(r.body.shifts || []);
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.vardiya_a\xE7")}>
        <Input label={t("cm.pages_POSExtensions.outlet_id")} value={outlet} onChange={setOutlet} />
        <Input label={t("cm.pages_POSExtensions.a\xE7\u0131l\u0131\u015F_nakit")} value={opening} onChange={setOpening} type="number" />
        <Btn onClick={async () => {
        await apiFetch("/api/pos/ext/shifts/open", {
          method: "POST",
          body: JSON.stringify({
            outlet_id: outlet,
            opening_cash: Number(opening)
          })
        });
        await load();
      }}>{t("cm.pages_POSExtensions.a\xE7")}</Btn>
      </Section>
      <Section title={t("cm.pages_POSExtensions.vardiyalar")}><Json data={shifts} /></Section>
    </>;
}
function BarcodeTab() {
  const [barcode, setBarcode] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [lookupResult, setLookupResult] = useState(null);
  const [maps, setMaps] = useState([]);
  const load = async () => {
    const r = await apiFetch("/api/pos/ext/barcode/map?limit=50");
    if (r.ok) setMaps(r.body.mappings || []);
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.barkod_e\u015Fle")}>
        <Input label={t("cm.pages_POSExtensions.barkod")} value={barcode} onChange={setBarcode} placeholder="8690000000000" />
        <Input label={t("cm.pages_POSExtensions.\xFCr\xFCn_ad\u0131")} value={name} onChange={setName} />
        <Input label={t("cm.pages_POSExtensions.birim_fiyat")} value={price} onChange={setPrice} type="number" />
        <div className="flex gap-2 mt-2">
          <Btn onClick={async () => {
          await apiFetch("/api/pos/ext/barcode/map", {
            method: "POST",
            body: JSON.stringify({
              barcode,
              name,
              unit_price: Number(price)
            })
          });
          await load();
        }}>{t("cm.pages_POSExtensions.kaydet")}</Btn>
          <Btn variant="outline" onClick={async () => {
          const r = await apiFetch(`/api/pos/ext/barcode/lookup/${encodeURIComponent(barcode)}`);
          setLookupResult(r.body);
        }}>{t("cm.pages_POSExtensions.sorgula")}</Btn>
        </div>
        {lookupResult && <Json data={lookupResult} />}
      </Section>
      <Section title={t("cm.pages_POSExtensions.e\u015Flemeler")}><Json data={maps} /></Section>
    </>;
}
function PrintTab() {
  const [jobs, setJobs] = useState([]);
  const [last, setLast] = useState(null);
  const load = async () => {
    const r = await apiFetch("/api/pos/ext/print/jobs?limit=20");
    if (r.ok) setJobs(r.body.jobs || []);
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.test_fi\u015Fi_bas")}>
        <Btn onClick={async () => {
        const r = await apiFetch("/api/pos/ext/print/jobs", {
          method: "POST",
          body: JSON.stringify({
            kind: "test",
            printer_id: "default",
            copies: 1,
            payload: {
              note: "manual test"
            }
          })
        });
        setLast(r.body);
        if (r.body?.job?.id) {
          await apiFetch(`/api/pos/ext/print/jobs/${r.body.job.id}/dispatch`, {
            method: "POST"
          });
        }
        await load();
      }}>{t("cm.pages_POSExtensions.test_bas")}</Btn>
        {last && <Json data={last} />}
      </Section>
      <Section title={t("cm.pages_POSExtensions.kuyruk")}><Json data={jobs} /></Section>
    </>;
}
function FiscalTab() {
  const [jobs, setJobs] = useState([]);
  const load = async () => {
    const r = await apiFetch("/api/pos/ext/fiscal/jobs?limit=20");
    if (r.ok) setJobs(r.body.jobs || []);
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.mali_yaz\u0131c\u0131_\xF6kc_durumu")}>
        <p className="text-sm text-gray-700">{t("cm.pages_POSExtensions.s\xFCr\xFCc\xFC")}<code className="bg-gray-100 px-1 rounded">{t("cm.pages_POSExtensions.pos_fiscal_driver")}</code>{t("cm.pages_POSExtensions.env_de\u011Fi\u015Fkeniyle_se\xE7ilir_\xFCreti")}</p>
        <div className="mt-2">
          <Btn variant="outline" onClick={async () => {
          await apiFetch("/api/pos/ext/fiscal/eod", {
            method: "POST"
          });
          await load();
        }}>{t("cm.pages_POSExtensions.g\xFCn_sonu_z_simulator")}</Btn>
        </div>
      </Section>
      <Section title={t("cm.pages_POSExtensions.bekleyen_fiscal_i_\u015F_kuyru\u011Fu")}><Json data={jobs} /></Section>
    </>;
}
const TAB_COMPONENTS = {
  currency: CurrencyTab,
  happyhour: HappyHourTab,
  coupons: CouponsTab,
  loyalty: LoyaltyTab,
  shifts: ShiftsTab,
  barcode: BarcodeTab,
  print: PrintTab,
  fiscal: FiscalTab
};
export default function POSExtensions() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("currency");
  const Comp = TAB_COMPONENTS[tab];
  return <div className="p-4 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <button type="button" onClick={() => navigate("/pos")} className="text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" />{t("cm.pages_POSExtensions.pos_dashboard")}</button>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">{t("cm.pages_POSExtensions.pos_eklentileri")}</h1>
          <p className="text-sm text-gray-600">{t("cm.pages_POSExtensions.\xE7oklu_d\xF6viz_happy_hour_kupon_s")}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mb-4 border-b border-gray-200">
        {TABS.map(t => <button key={t.id} type="button" onClick={() => setTab(t.id)} className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t.id ? "border-gray-900 text-gray-900" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
            {t.label}
          </button>)}
      </div>
      <Comp />
    </div>;
}