import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import Layout from "@/components/Layout";
import { confirmDialog, promptDialog } from '@/lib/dialogs';
import {
  Building2,
  Calculator,
  CheckCircle2,
  ClipboardList,
  Download,
  FileCode,
  FileText,
  History,
  Loader2,
  Lock,
  Percent,
  Printer,
  RefreshCw,
  Save,
  Send,
  Settings,
  Wallet,
} from "lucide-react";

const TABS = [
  { key: "config", label: "Yapılandırma", icon: Settings },
  { key: "report", label: "Aylık Rapor", icon: ClipboardList },
  { key: "declaration", label: "Beyanname", icon: FileText },
  { key: "history", label: "Geçmiş", icon: History },
  { key: "calculator", label: "Hesaplayıcı", icon: Calculator },
];

const STATUS_BADGE = {
  draft: { label: "Taslak", cls: "bg-gray-100 text-gray-700" },
  finalized: { label: "Onaylı", cls: "bg-amber-100 text-amber-800" },
  submitted: { label: "Gönderildi", cls: "bg-blue-100 text-blue-800" },
  paid: { label: "Ödendi", cls: "bg-emerald-100 text-emerald-800" },
};

function fmtTRY(v) {
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: "TRY",
    minimumFractionDigits: 2,
  }).format(Number(v || 0));
}

function downloadCSV(rows, filename) {
  const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function KonaklamaVergisiModule({ user, tenant, onLogout }) {
  const [tab, setTab] = useState("config");
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const today = useMemo(() => new Date(), []);
  const [year, setYear] = useState(today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() === 0 ? 12 : today.getMonth());

  const [report, setReport] = useState(null);
  const [declaration, setDeclaration] = useState(null);
  const [finalized, setFinalized] = useState(null);
  const [history, setHistory] = useState([]);
  const [working, setWorking] = useState(false);

  const [calc, setCalc] = useState({ amount: 1000, nights: 2, exempt: false });
  const [calcResult, setCalcResult] = useState(null);

  const loadHistory = async () => {
    try {
      const { data } = await axios.get("/finance/konaklama-vergisi/declarations");
      setHistory(data.items || []);
    } catch (e) {
      toast.error("Beyanname geçmişi yüklenemedi");
    }
  };

  const finalizeDeclaration = async () => {
    if (!declaration) return;
    if (!await confirmDialog({ message: `${declaration.period} dönemini onaylayıp kilitlemek üzeresiniz. ` +
      `Kilitledikten sonra dönem kapanır, yalnızca gönderim ve ödeme ` +
      `kayıtları eklenebilir. Devam edilsin mi?` })) return;
    setWorking(true);
    try {
      const { data } = await axios.post(
        "/finance/konaklama-vergisi/declaration/finalize",
        { year, month });
      setFinalized(data);
      toast.success(`${data.period} dönemi onaylandı (${data.id.slice(0, 8)})`);
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Onay başarısız");
    } finally { setWorking(false); }
  };

  const submitDeclaration = async (decl) => {
    const ref = await promptDialog({ message: "GİB / e-Beyanname tahakkuk fiş numarasını girin:" });
    if (!ref || ref.trim().length < 3) return;
    setWorking(true);
    try {
      const { data } = await axios.post(
        `/finance/konaklama-vergisi/declarations/${decl.id}/submit`,
        { submission_ref: ref.trim() });
      toast.success(`Beyanname gönderildi: ${data.submission_ref}`);
      setFinalized(data);
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gönderim kaydedilemedi");
    } finally { setWorking(false); }
  };

  const payDeclaration = async (decl) => {
    const ref = await promptDialog({ message: "Banka transfer / dekont referans numarası:" });
    if (!ref || ref.trim().length < 3) return;
    setWorking(true);
    try {
      const { data } = await axios.post(
        `/finance/konaklama-vergisi/declarations/${decl.id}/pay`,
        { payment_ref: ref.trim(), amount: decl.total_tax });
      toast.success(`Ödeme kaydedildi: ${data.payment_ref}`);
      setFinalized(data);
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ödeme kaydedilemedi");
    } finally { setWorking(false); }
  };

  const exportDecl = async (decl, fmt) => {
    try {
      const res = await axios.get(
        `/finance/konaklama-vergisi/declarations/${decl.id}/export`,
        { params: { format: fmt }, responseType: "blob" });
      const blob = new Blob([res.data], {
        type: fmt === "xml" ? "application/xml" : "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `kvb-${decl.period}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("İndirme başarısız");
    }
  };

  const loadConfig = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/finance/konaklama-vergisi/config");
      setConfig(data);
    } catch (e) {
      toast.error("Yapılandırma yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadConfig(); loadHistory(); }, []);

  const saveConfig = async () => {
    setSaving(true);
    try {
      const payload = {
        rate_percent: Number(config.rate_percent || 2),
        active: !!config.active,
        auto_post: !!config.auto_post,
        effective_from: config.effective_from || null,
        notes: config.notes || null,
        exempt_segments: config.exempt_segments || [],
      };
      const { data } = await axios.put("/finance/konaklama-vergisi/config", payload);
      setConfig(data);
      toast.success("Yapılandırma kaydedildi");
    } catch (e) {
      toast.error("Kaydetme başarısız");
    } finally {
      setSaving(false);
    }
  };

  const loadReport = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/finance/konaklama-vergisi/report", { params: { year, month } });
      setReport(data);
    } catch (e) {
      toast.error("Rapor yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const loadDeclaration = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(
        "/finance/konaklama-vergisi/declaration",
        { params: { year, month } });
      setDeclaration(data);
      // Check whether this period already has a persisted record.
      const list = await axios.get(
        "/finance/konaklama-vergisi/declarations");
      const existing = (list.data?.items || [])
        .find((d) => d.period === data.period);
      setFinalized(existing || null);
    } catch (e) {
      toast.error("Beyanname yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const runCalc = async () => {
    try {
      const { data } = await axios.post("/finance/konaklama-vergisi/calculate", calc);
      setCalcResult(data);
    } catch (e) {
      toast.error("Hesaplama başarısız");
    }
  };

  const exportReportCSV = () => {
    if (!report) return;
    const rows = [
      ["Folio ID", "Booking ID", "Geceleme", "Matrah (TRY)"],
      ...report.rows.map((r) => [r._id, r.booking_id, r.nights, r.base_amount?.toFixed(2)]),
      [],
      ["TOPLAM", "", report.total_nights, report.total_base?.toFixed(2)],
      ["VERGİ (%" + report.rate_percent + ")", "", "", report.total_tax?.toFixed(2)],
    ];
    downloadCSV(rows, `konaklama-vergisi-${year}-${String(month).padStart(2, "0")}.csv`);
  };

  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1);
  const yearOptions = Array.from({ length: 5 }, (_, i) => today.getFullYear() - i);

  return (
    <Layout
      user={user}
      tenant={tenant}
      onLogout={onLogout}
      currentModule="konaklama-vergisi"
      title="Konaklama Vergisi Otomasyonu"
      subtitle="7194 sayılı Kanun — Türkiye Konaklama Vergisi (varsayılan %2). Aylık beyanname takip eden ayın 26'sına kadar verilir."
    >
      <div className="p-4 lg:p-6 space-y-4">

      <div className="border-b">
        <div className="flex flex-wrap gap-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-2 px-4 py-2 border-b-2 -mb-px text-sm transition ${
                  active ? "border-amber-600 text-amber-700 font-semibold" : "border-transparent text-gray-500 hover:text-gray-800"
                }`}
              >
                <Icon className="h-4 w-4" /> {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {tab === "config" && (
        <div className="bg-white rounded-lg border p-4 max-w-2xl space-y-4">
          {loading || !config ? (
            <div className="flex items-center gap-2 text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Yükleniyor…</div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-gray-600">Vergi Oranı (%)</label>
                  <div className="flex items-center gap-2 mt-1">
                    <Percent className="h-4 w-4 text-gray-400" />
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="100"
                      className="border rounded px-3 py-2 w-full"
                      value={config.rate_percent ?? 2}
                      onChange={(e) => setConfig({ ...config, rate_percent: parseFloat(e.target.value) })}
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-600">Yürürlük Tarihi</label>
                  <input
                    type="date"
                    className="border rounded px-3 py-2 w-full mt-1"
                    value={config.effective_from || ""}
                    onChange={(e) => setConfig({ ...config, effective_from: e.target.value })}
                  />
                </div>
              </div>

              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={!!config.active}
                    onChange={(e) => setConfig({ ...config, active: e.target.checked })}
                  />
                  Aktif
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={!!config.auto_post}
                    onChange={(e) => setConfig({ ...config, auto_post: e.target.checked })}
                  />
                  Folio'ya otomatik vergi satırı ekle (checkout)
                </label>
              </div>

              <div>
                <label className="text-xs font-medium text-gray-600">Notlar / Muafiyet Açıklaması</label>
                <textarea
                  className="border rounded px-3 py-2 w-full mt-1"
                  rows={3}
                  placeholder="Diplomatik muafiyet, öğrenci yurdu vb."
                  value={config.notes || ""}
                  onChange={(e) => setConfig({ ...config, notes: e.target.value })}
                />
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={saveConfig}
                  disabled={saving}
                  className="flex items-center gap-2 bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded disabled:opacity-50"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Kaydet
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {(tab === "report" || tab === "declaration") && (
        <div className="bg-white rounded-lg border p-4 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 block">Yıl</label>
              <select className="border rounded px-3 py-2" value={year} onChange={(e) => setYear(Number(e.target.value))}>
                {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block">Ay</label>
              <select className="border rounded px-3 py-2" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                {monthOptions.map((m) => <option key={m} value={m}>{String(m).padStart(2, "0")}</option>)}
              </select>
            </div>
            <button
              onClick={tab === "report" ? loadReport : loadDeclaration}
              disabled={loading}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {tab === "report" ? "Raporu Hesapla" : "Beyannameyi Oluştur"}
            </button>
            {tab === "report" && report && (
              <button
                onClick={exportReportCSV}
                className="flex items-center gap-2 border px-4 py-2 rounded hover:bg-gray-50"
              >
                <Download className="h-4 w-4" /> CSV İndir
              </button>
            )}
            {tab === "declaration" && declaration && (
              <button
                onClick={() => window.print()}
                className="flex items-center gap-2 border px-4 py-2 rounded hover:bg-gray-50"
              >
                <Printer className="h-4 w-4" /> Yazdır
              </button>
            )}
          </div>

          {tab === "report" && report && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI title="Folio Sayısı" value={report.folio_count} />
                <KPI title="Toplam Geceleme" value={report.total_nights} />
                <KPI title="Matrah" value={fmtTRY(report.total_base)} />
                <KPI title={`Vergi (%${report.rate_percent})`} value={fmtTRY(report.total_tax)} highlight />
              </div>
              <div className="overflow-auto border rounded">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-3 py-2">Folio ID</th>
                      <th className="text-left px-3 py-2">Booking</th>
                      <th className="text-right px-3 py-2">Geceleme</th>
                      <th className="text-right px-3 py-2">Matrah</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.rows.map((r) => (
                      <tr key={r._id} className="border-t">
                        <td className="px-3 py-2 font-mono text-xs">{r._id}</td>
                        <td className="px-3 py-2 font-mono text-xs">{r.booking_id}</td>
                        <td className="px-3 py-2 text-right">{r.nights}</td>
                        <td className="px-3 py-2 text-right">{fmtTRY(r.base_amount)}</td>
                      </tr>
                    ))}
                    {report.rows.length === 0 && (
                      <tr><td colSpan={4} className="text-center text-gray-400 py-6">Bu dönemde oda satırı bulunamadı.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {tab === "declaration" && declaration && (
            <div className="space-y-3">
              {finalized && (
                <div className="flex flex-wrap items-center gap-2 text-sm bg-amber-50 border border-amber-200 rounded p-3">
                  <Lock className="h-4 w-4 text-amber-700" />
                  <span className="font-medium">Bu dönem kilitli:</span>
                  <StatusBadge status={finalized.status} />
                  <span className="text-gray-600">
                    Onay: {(finalized.finalized_at || "").slice(0, 16).replace("T", " ")}
                  </span>
                  {finalized.submission_ref && (
                    <span className="text-gray-600">
                      Tahakkuk: <b>{finalized.submission_ref}</b>
                    </span>
                  )}
                  {finalized.payment_ref && (
                    <span className="text-gray-600">
                      Ödeme: <b>{finalized.payment_ref}</b>
                    </span>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {!finalized && (
                  <button
                    onClick={finalizeDeclaration}
                    disabled={working}
                    className="flex items-center gap-2 bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded disabled:opacity-50">
                    <Lock className="h-4 w-4" /> Beyannameyi Onayla & Kilitle
                  </button>
                )}
                {finalized && finalized.status === "finalized" && (
                  <button
                    onClick={() => submitDeclaration(finalized)}
                    disabled={working}
                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded disabled:opacity-50">
                    <Send className="h-4 w-4" /> GİB Tahakkuk Numarası Kaydet
                  </button>
                )}
                {finalized && (finalized.status === "submitted" || finalized.status === "finalized") && (
                  <button
                    onClick={() => payDeclaration(finalized)}
                    disabled={working}
                    className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded disabled:opacity-50">
                    <Wallet className="h-4 w-4" /> Ödeme Kaydet
                  </button>
                )}
                {finalized && (
                  <>
                    <button
                      onClick={() => exportDecl(finalized, "xml")}
                      className="flex items-center gap-2 border px-4 py-2 rounded hover:bg-gray-50">
                      <FileCode className="h-4 w-4" /> XML İndir (GİB)
                    </button>
                    <button
                      onClick={() => exportDecl(finalized, "json")}
                      className="flex items-center gap-2 border px-4 py-2 rounded hover:bg-gray-50">
                      <Download className="h-4 w-4" /> JSON Arşiv
                    </button>
                  </>
                )}
              </div>

              <div className="border rounded-lg p-6 print:p-0 print:border-0 max-w-3xl">
                <div className="text-center mb-4">
                  <h2 className="text-xl font-bold">KONAKLAMA VERGİSİ BEYANNAMESİ</h2>
                  <p className="text-sm text-gray-500">{declaration.law_reference}</p>
                </div>
                <DeclRow label="İşletme">{declaration.tenant?.hotel_name || "-"}</DeclRow>
                <DeclRow label="Vergi No / Otel ID">{declaration.tenant?.tax_no || declaration.tenant?.hotel_id || "-"}</DeclRow>
                <DeclRow label="Dönem">{declaration.period}</DeclRow>
                <DeclRow label="Son Beyan/Ödeme Tarihi">{declaration.due_date}</DeclRow>
                <DeclRow label="Vergi Oranı">{`%${declaration.rate_percent}`}</DeclRow>
                <DeclRow label="Folio Sayısı">{declaration.folio_count}</DeclRow>
                <DeclRow label="Toplam Geceleme">{declaration.total_nights}</DeclRow>
                <DeclRow label="Matrah">{fmtTRY(declaration.total_base)}</DeclRow>
                <DeclRow label="Tahakkuk Eden Vergi" highlight>{fmtTRY(declaration.total_tax)}</DeclRow>
                <p className="text-xs text-gray-400 mt-6">
                  Bu özet, dahili kontrol amaçlıdır. Resmi beyanname için Gelir
                  İdaresi Başkanlığı (GİB) e-Beyanname sistemini kullanınız.
                  Onayladıktan sonra XML çıktısı GİB form alanlarıyla 1-1
                  eşleşir; muhasebe yazılımına aktarmak için kullanabilirsiniz.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "history" && (
        <div className="bg-white rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2">
              <History className="h-4 w-4" /> Beyanname Geçmişi
            </h3>
            <button
              onClick={loadHistory}
              className="text-sm flex items-center gap-1 text-blue-600 hover:underline">
              <RefreshCw className="h-3 w-3" /> Yenile
            </button>
          </div>
          <div className="overflow-auto border rounded">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-3 py-2">Dönem</th>
                  <th className="text-left px-3 py-2">Durum</th>
                  <th className="text-right px-3 py-2">Matrah</th>
                  <th className="text-right px-3 py-2">Vergi</th>
                  <th className="text-left px-3 py-2">Son Tarih</th>
                  <th className="text-left px-3 py-2">Tahakkuk</th>
                  <th className="text-left px-3 py-2">Ödeme</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {history.map((d) => (
                  <tr key={d.id} className="border-t">
                    <td className="px-3 py-2 font-mono">{d.period}</td>
                    <td className="px-3 py-2"><StatusBadge status={d.status} /></td>
                    <td className="px-3 py-2 text-right">{fmtTRY(d.total_base)}</td>
                    <td className="px-3 py-2 text-right font-semibold">{fmtTRY(d.total_tax)}</td>
                    <td className="px-3 py-2">{d.due_date}</td>
                    <td className="px-3 py-2 text-xs">{d.submission_ref || "-"}</td>
                    <td className="px-3 py-2 text-xs">{d.payment_ref || "-"}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => exportDecl(d, "xml")}
                        title="XML indir"
                        className="text-blue-600 hover:underline">
                        <FileCode className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {history.length === 0 && (
                  <tr><td colSpan={8} className="text-center text-gray-400 py-6">
                    Henüz onaylanmış beyanname yok.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "calculator" && (
        <div className="bg-white rounded-lg border p-4 max-w-xl space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600">Tutar (TRY)</label>
              <input type="number" className="border rounded px-3 py-2 w-full mt-1" value={calc.amount}
                onChange={(e) => setCalc({ ...calc, amount: parseFloat(e.target.value) || 0 })} />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600">Geceleme</label>
              <input type="number" min="1" className="border rounded px-3 py-2 w-full mt-1" value={calc.nights}
                onChange={(e) => setCalc({ ...calc, nights: parseInt(e.target.value) || 1 })} />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={calc.exempt} onChange={(e) => setCalc({ ...calc, exempt: e.target.checked })} />
                Muaf
              </label>
            </div>
          </div>
          <button onClick={runCalc} className="bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded flex items-center gap-2">
            <Calculator className="h-4 w-4" /> Hesapla
          </button>
          {calcResult && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
              <KPI title="Matrah" value={fmtTRY(calcResult.base_amount)} />
              <KPI title={`Vergi %${calcResult.rate_percent}`} value={fmtTRY(calcResult.tax_amount)} highlight />
              <KPI title="Toplam" value={fmtTRY(calcResult.total_with_tax)} />
              <KPI title="Geceleme" value={calcResult.nights} />
            </div>
          )}
        </div>
      )}
      </div>
    </Layout>
  );
}

function KPI({ title, value, highlight }) {
  return (
    <div className={`border rounded-lg p-3 ${highlight ? "bg-amber-50 border-amber-300" : ""}`}>
      <div className="text-xs text-gray-500">{title}</div>
      <div className={`text-lg font-semibold ${highlight ? "text-amber-700" : ""}`}>{value}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const meta = STATUS_BADGE[status] || STATUS_BADGE.draft;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

function DeclRow({ label, children, highlight }) {
  return (
    <div className={`flex justify-between border-b py-2 ${highlight ? "bg-amber-50 px-2 rounded font-bold" : ""}`}>
      <span className="text-gray-600">{label}</span>
      <span className={highlight ? "text-amber-700" : ""}>{children}</span>
    </div>
  );
}
