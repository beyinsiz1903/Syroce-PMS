import { toast } from "sonner";
import { t } from "i18next";
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { parseMoneyInput } from '@/lib/moneyInput';
const TABS = [{ id: "stock", label: "Stok kurtarma" }, {
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
  const headers = {
    "Content-Type": "application/json",
    ...(opts.headers || {})
  };
  // credentials: 'include' sends the httpOnly cookie automatically.
  let res;
  try { res = await fetch(path, {
    ...opts,
    headers,
    credentials: "include"
  }); } catch { res = { ok: false, status: 0, json: async () => ({ detail: "Sunucuya ulaşılamadı. İşlemin sonucunu kontrol ederek yeniden deneyin." }) }; }
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const message = res.ok ? "İşlem tamamlandı" : (typeof body?.detail === "string" ? body.detail : body?.detail?.message || "İşlem tamamlanamadı; yetkinizi ve alanları kontrol edin.");
  if (!res.ok) toast.error(message);
  if (opts.method && opts.method !== "GET" || !res.ok) window.dispatchEvent(new CustomEvent("pos-extension-result", { detail: { time: new Date().toLocaleTimeString("tr-TR"), status: res.ok ? "completed" : "failed", message } }));
  return {
    status: res.status,
    ok: res.ok,
    body: body || {}
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
  money = false,
  placeholder
}) {
  return <label className="block mb-2">
      <span className="block text-xs font-medium text-gray-700 mb-1">{label}</span>
      <input type={money ? "text" : type} inputMode={money ? "decimal" : undefined} autoComplete={money ? "off" : undefined} value={value ?? ""} onChange={e => onChange(e.target.value)} placeholder={placeholder || (money ? "Örn. 150,74" : undefined)} className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
    </label>;
}
function Btn({
  children,
  onClick,
  variant = "primary",
  disabled
}) {
  const [pending, setPending] = useState(false);
  const base = "px-3 py-2 rounded text-sm font-medium transition disabled:opacity-50";
  const cls = variant === "primary" ? `${base} bg-gray-900 text-white hover:bg-gray-800` : variant === "outline" ? `${base} border border-gray-300 bg-white text-gray-800 hover:bg-gray-50` : `${base} bg-red-600 text-white hover:bg-red-700`;
  return <button type="button" onClick={async () => { setPending(true); try { await onClick(); } catch { toast.error("İşlem tamamlanamadı. Yeniden deneyin."); } finally { setPending(false); } }} disabled={disabled || pending} className={cls}>{pending ? "İşleniyor…" : children}</button>;
}
const LABELS = {
  currency_code: 'Para birimi', base_currency: 'Tesis para birimi', rate_to_base: 'Kur', valid_at: 'Geçerlilik',
  code: 'Kod', name: 'Ad', active: 'Etkin', status: 'Durum', balance: 'Puan bakiyesi',
  discount_type: 'İndirim türü', discount_value: 'İndirim', used_count: 'Kullanım', max_uses: 'Kullanım limiti',
  min_amount: 'Asgari tutar', start_time: 'Başlangıç', end_time: 'Bitiş', days_of_week: 'Günler',
  guest_id: 'Misafir numarası', points: 'Puan', kind: 'İşlem', created_at: 'Oluşturulma', updated_at: 'Güncellenme',
  earn_points_per_unit: 'Birim tutar başına puan', redeem_value_per_point: 'Puan karşılığı',
  min_redeem_points: 'Asgari kullanım', lifetime_earned: 'Toplam kazanılan', lifetime_redeemed: 'Toplam kullanılan',
  barcode: 'Barkod', menu_item_id: 'Ürün numarası', item_id: 'Ürün numarası', item_name: 'Ürün', quantity: 'Adet',
  order_id: 'Adisyon numarası', order_number: 'Adisyon', station: 'İstasyon', printer_id: 'Yazıcı',
  attempts: 'Deneme', last_error: 'Son hata', error: 'Hata', message: 'Sonuç', valid: 'Geçerli',
  success: 'Başarılı', reason: 'Açıklama', amount: 'Tutar', discount_amount: 'İndirim tutarı',
  final_amount: 'Son tutar', amount_base: 'Tesis para biriminde tutar', amount_foreign: 'Döviz tutarı',
  opening_float: 'Açılış nakdi', closing_cash: 'Kapanış nakdi', expected_cash: 'Beklenen nakit',
  difference: 'Fark', outlet_id: 'Satış noktası', opened_at: 'Açılış', closed_at: 'Kapanış',
  payment_method: 'Ödeme yöntemi', job_type: 'İş türü', type: 'Tür', note: 'Not',
  driver: 'Cihaz sürücüsü', fiscal_no: 'Mali belge numarası', z_no: 'Z numarası',
  opening_cash: 'Açılış nakdi', counted_cash_total: 'Sayılan nakit', expected_cash_total: 'Beklenen nakit',
  cash_sales: 'Nakit hareket toplamı', variance: 'Kasa farkı', tx_count: 'İşlem sayısı',
  stock_consumption_status: 'Stok tüketimi', stock_restore_status: 'İade stoğu',
  stock_consumption_status_error: 'Tüketim hatası', stock_restore_status_error: 'İade hatası',
};
const STATES = { pending: 'Bekliyor', queued: 'Kuyrukta', completed: 'Tamamlandı', failed: 'Başarısız',
  sent: 'Gönderildi', printed: 'Yazdırıldı', running: 'Çalışıyor', open: 'Açık', closed: 'Kapalı',
  percent: 'Yüzde', amount: 'Tutar', cash: 'Nakit', card: 'Kart', simulated: 'Simülasyon' };
function Cell({ value }) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return <span className="rounded bg-gray-100 px-2">{value ? 'Evet' : 'Hayır'}</span>;
  if (Array.isArray(value)) return value.every(v => typeof v !== 'object') ? value.join(', ') : <ResultTable data={value} />;
  if (typeof value === 'object') return <ResultTable data={value} />;
  return <span className={STATES[value] ? 'rounded bg-gray-100 px-2 py-1' : ''}>{STATES[value] || String(value)}</span>;
}
export function ResultTable({ data }) {
  if (!data || Array.isArray(data) && !data.length) return <p className="text-sm text-gray-500">Kayıt bulunamadı.</p>;
  if (!Array.isArray(data)) {
    if (typeof data !== 'object') return <Cell value={data} />;
    const fields = Object.entries(data).filter(([key]) => LABELS[key]);
    const nested = Object.entries(data).filter(([key, value]) => !LABELS[key] && value && typeof value === 'object');
    return <div><dl className="grid grid-cols-2 gap-2 text-sm">{fields.map(([key, value]) => <div key={key}><dt className="text-gray-500">{LABELS[key]}</dt><dd><Cell value={value} /></dd></div>)}</dl>{nested.map(([key, value]) => <ResultTable key={key} data={value} />)}{!fields.length && !nested.length && <p>İşlem sonucu kaydedildi.</p>}</div>;
  }
  const keys = Object.keys(LABELS).filter(key => data.some(row => row && Object.hasOwn(row, key)));
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{keys.map(key => <th className="p-2 border-b" key={key}>{LABELS[key]}</th>)}</tr></thead><tbody>{data.map((row, index) => <tr key={row.id || index}>{keys.map(key => <td className="p-2 border-b" key={key}><Cell value={row[key]} /></td>)}</tr>)}</tbody></table></div>;
}

function StockTab() {
  const [jobs, setJobs] = useState([]);
  const load = useCallback(async () => {
    const result = await apiFetch('/api/pos/v2/stock/recovery');
    if (result.ok) setJobs(result.body.jobs || []);
  }, []);
  useEffect(() => { load(); }, [load]);
  return <Section title="Stok kurtarma kuyruğu">
    <p className="text-sm mb-3">Tahsilat tekrar yapılmaz. Eksik stok girişini veya bağlantıyı düzelttikten sonra yeniden çalıştırın. İlk 200 bekleyen işlem gösterilir.</p>
    <Btn onClick={load}>Yenile</Btn>
    {!jobs.length && <p>Bekleyen stok işlemi yok.</p>}
    {jobs.map(job => <div key={job.id} className="border rounded p-3 my-2"><ResultTable data={job} />
      <Btn onClick={async () => {
        const result = await apiFetch(`/api/pos/v2/stock/recovery/${encodeURIComponent(job.id)}/retry`, { method: 'POST' });
        if (result.ok) await load();
      }}>Stoğu yeniden işle</Btn></div>)}
  </Section>;
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
        <Input label={t("cm.pages_POSExtensions.try_kar\u015F\u0131l\u0131\u011F\u0131")} value={rate} onChange={setRate} money />
        <div className="flex gap-2 mt-2">
          <Btn onClick={async () => {
          const r = await apiFetch("/api/pos/ext/currency/rates", {
            method: "POST",
            body: JSON.stringify({
              currency_code: code,
              rate_to_base: parseMoneyInput(rate)
            })
          });
          setLast(r);
          await load();
        }}>{t("cm.pages_POSExtensions.kaydet")}</Btn>
          <Btn variant="outline" onClick={load}><RefreshCw className="w-4 h-4 inline" />{t("cm.pages_POSExtensions.yenile")}</Btn>
        </div>
      </Section>
      <Section title={t("cm.pages_POSExtensions.tan\u0131ml\u0131_kurlar")}>
        <ResultTable data={rates} />
      </Section>
      {last && <Section title={t("cm.pages_POSExtensions.son_i\u015Flem_yan\u0131t\u0131")}><ResultTable data={last} /></Section>}
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
      <Section title={t("cm.pages_POSExtensions.tan\u0131ml\u0131_kurallar")}><ResultTable data={rules} /></Section>
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
        <Input label={t("cm.pages_POSExtensions.tutar_tl")} value={validateAmount} onChange={setValidateAmount} money />
        <Btn variant="outline" onClick={async () => {
        const r = await apiFetch("/api/pos/ext/coupons/validate", {
          method: "POST",
          body: JSON.stringify({
            code,
            amount: parseMoneyInput(validateAmount)
          })
        });
        setLast(r.body);
      }}>{t("cm.pages_POSExtensions.kontrol_et")}</Btn>
        {last && <ResultTable data={last} />}
      </Section>
      <Section title={t("cm.pages_POSExtensions.tan\u0131ml\u0131_kuponlar")}><ResultTable data={coupons} /></Section>
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
      <Section title={t("cm.pages_POSExtensions.program_ayarlar\u0131")}><ResultTable data={settings} /></Section>
      <Section title={t("cm.pages_POSExtensions.misafir_bakiyesi")}>
        <Input label={t("cm.pages_POSExtensions.misafir_id")} value={guestId} onChange={setGuestId} />
        <Btn variant="outline" onClick={async () => {
        const r = await apiFetch(`/api/pos/ext/loyalty/balance?guest_id=${encodeURIComponent(guestId)}`);
        setBalance(r.body);
      }}>{t("cm.pages_POSExtensions.bakiye_sorgula")}</Btn>
        {balance && <ResultTable data={balance} />}
      </Section>
    </>;
}
function ShiftsTab() {
  const [outlet, setOutlet] = useState("");
  const [opening, setOpening] = useState("500");
  const [counted, setCounted] = useState("");
  const [shifts, setShifts] = useState([]);
  const [outlets, setOutlets] = useState([]);
  const [message, setMessage] = useState("");
  const load = async () => {
    const [shiftResponse, outletResponse] = await Promise.all([
      apiFetch("/api/pos/ext/shifts?limit=20"), apiFetch("/api/pos/outlets"),
    ]);
    if (shiftResponse.ok) setShifts(shiftResponse.body.shifts || []);
    if (outletResponse.ok) {
      const rows = Array.isArray(outletResponse.body) ? outletResponse.body : outletResponse.body?.outlets || [];
      setOutlets(rows);
      setOutlet(current => current || rows[0]?.id || "");
    }
  };
  useEffect(() => {
    load();
  }, []);
  return <>
      <Section title={t("cm.pages_POSExtensions.vardiya_a\xE7")}>
        <label className="block mb-2"><span className="block text-xs font-medium text-gray-700 mb-1">Satış noktası</span>
          <select className="w-full border border-gray-300 rounded px-3 py-2 text-sm" value={outlet} onChange={event => setOutlet(event.target.value)}>
            <option value="">Satış noktası seçin</option>{outlets.map(row => <option key={row.id} value={row.id}>{row.outlet_name || row.name}</option>)}
          </select>
        </label>
        <Input label={t("cm.pages_POSExtensions.a\xE7\u0131l\u0131\u015F_nakit")} value={opening} onChange={setOpening} money />
        <Btn disabled={!outlet} onClick={async () => {
        const response = await apiFetch("/api/pos/ext/shifts/open", {
          method: "POST",
          body: JSON.stringify({
            outlet_id: outlet,
            opening_cash: parseMoneyInput(opening)
          })
        });
        setMessage(response.ok ? "Vardiya açıldı." : response.body?.detail || "Vardiya açılamadı.");
        await load();
      }}>{t("cm.pages_POSExtensions.a\xE7")}</Btn>
        {message && <p className="mt-2 text-sm text-gray-700" role="status">{message}</p>}
      </Section>
      <Section title={t("cm.pages_POSExtensions.vardiyalar")}>
        {shifts.length === 0 ? <p className="text-sm text-gray-500">Henüz vardiya kaydı yok.</p> : <div className="space-y-3">
          {shifts.map(shift => <div key={shift.id} className="rounded-lg border p-3">
            <div className="flex items-start justify-between gap-3"><div><strong>{outlets.find(row => row.id === shift.outlet_id)?.outlet_name || outlets.find(row => row.id === shift.outlet_id)?.name || 'Satış noktası'}</strong><p className="text-xs text-gray-500">{shift.status === 'open' ? 'Açık vardiya' : 'Kapanmış vardiya'} · Açılış nakdi {Number(shift.opening_cash || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL</p></div><span className={`rounded-full px-2 py-1 text-xs font-semibold ${shift.status === 'open' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-700'}`}>{shift.status === 'open' ? 'Açık' : 'Kapalı'}</span></div>
            {shift.status === 'open' ? <div className="mt-3 flex items-end gap-2"><div className="flex-1"><Input label="Sayılan kasa toplamı" value={counted} onChange={setCounted} money /></div><Btn disabled={!Number.isFinite(parseMoneyInput(counted))} onClick={async () => { const response = await apiFetch(`/api/pos/ext/shifts/${shift.id}/close`, { method: 'POST', body: JSON.stringify({ counted_cash_total: parseMoneyInput(counted) }) }); setMessage(response.ok ? `Vardiya kapandı. Kasa farkı: ${Number(response.body?.shift?.variance || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL` : response.body?.detail || 'Vardiya kapatılamadı.'); if (response.ok) setCounted(''); await load(); }}>Sayımı Onayla ve Kapat</Btn></div> : <div className="mt-2 grid grid-cols-3 gap-2 text-sm"><div><span className="text-gray-500">Beklenen</span><strong className="block">{Number(shift.expected_cash_total || 0).toLocaleString('tr-TR')} TL</strong></div><div><span className="text-gray-500">Sayılan</span><strong className="block">{Number(shift.counted_cash_total || 0).toLocaleString('tr-TR')} TL</strong></div><div><span className="text-gray-500">Fark</span><strong className={`block ${Number(shift.variance || 0) === 0 ? 'text-emerald-700' : 'text-red-700'}`}>{Number(shift.variance || 0).toLocaleString('tr-TR')} TL</strong></div></div>}
          </div>)}
        </div>}
      </Section>
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
        <Input label={t("cm.pages_POSExtensions.birim_fiyat")} value={price} onChange={setPrice} money />
        <div className="flex gap-2 mt-2">
          <Btn onClick={async () => {
          await apiFetch("/api/pos/ext/barcode/map", {
            method: "POST",
            body: JSON.stringify({
              barcode,
              name,
              unit_price: parseMoneyInput(price)
            })
          });
          await load();
        }}>{t("cm.pages_POSExtensions.kaydet")}</Btn>
          <Btn variant="outline" onClick={async () => {
          const r = await apiFetch(`/api/pos/ext/barcode/lookup/${encodeURIComponent(barcode)}`);
          setLookupResult(r.body);
        }}>{t("cm.pages_POSExtensions.sorgula")}</Btn>
        </div>
        {lookupResult && <ResultTable data={lookupResult} />}
      </Section>
      <Section title={t("cm.pages_POSExtensions.e\u015Flemeler")}><ResultTable data={maps} /></Section>
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
        {last && <ResultTable data={last} />}
      </Section>
      <Section title={t("cm.pages_POSExtensions.kuyruk")}><ResultTable data={jobs} /></Section>
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
        <p className="text-sm text-gray-700">Mali cihaz işlemleri onaylı cihaz entegrasyonu gerektirir. Simülasyon çıktısı mali belge değildir. Üretimde uygun sürücü yoksa işlem engellenir; hata aşağıdaki işlem geçmişinde gösterilir.</p>
        <div className="mt-2">
          <Btn variant="outline" onClick={async () => {
          await apiFetch("/api/pos/ext/fiscal/eod", {
            method: "POST"
          });
          await load();
        }}>Gün Sonu Z Raporu Oluştur</Btn>
        </div>
      </Section>
      <Section title={t("cm.pages_POSExtensions.bekleyen_fiscal_i_\u015F_kuyru\u011Fu")}><ResultTable data={jobs} /></Section>
    </>;
}
const TAB_COMPONENTS = {
  stock: StockTab,
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
  const [history, setHistory] = useState([]);
  useEffect(() => {
    const receive = event => setHistory(rows => [event.detail, ...rows].slice(0, 30));
    window.addEventListener("pos-extension-result", receive);
    return () => window.removeEventListener("pos-extension-result", receive);
  }, []);
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
      {history.length > 0 && <Section title="Bu oturumdaki işlem geçmişi"><ol aria-live="polite">{history.map((row, index) => <li key={index} className={row.status === "failed" ? "text-red-700" : "text-green-700"}>{row.time} · {row.message}</li>)}</ol></Section>}
    </div>;
}
