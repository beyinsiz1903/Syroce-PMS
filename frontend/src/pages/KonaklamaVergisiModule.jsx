import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

import { confirmDialog, promptDialog } from '@/lib/dialogs';
import { PageHeader } from '@/components/ui/page-header';
import { StatusBadge } from '@/components/ui/status-badge';
import { KpiCard } from '@/components/ui/kpi-card';
import { Button } from '@/components/ui/button';
import {
  Building2,
  Calculator,
  CheckCircle2,
  ClipboardList,
  Download,
  FileCode,
  FileDown,
  FileText,
  History,
  Info,
  Loader2,
  Lock,
  Mail,
  Percent,
  Plus,
  Printer,
  Receipt,
  RefreshCw,
  Save,
  Send,
  Settings,
  ShieldOff,
  Wallet,
} from "lucide-react";
import { useTranslation } from 'react-i18next';

const TABS = [
  { key: "config", label: "Yapılandırma", icon: Settings },
  { key: "report", label: "Aylık Rapor", icon: ClipboardList },
  { key: "declaration", label: "Beyanname", icon: FileText },
  { key: "history", label: "Geçmiş", icon: History },
  { key: "calculator", label: "Hesaplayıcı", icon: Calculator },
];

const STATUS_INTENT = {
  draft:     { intent: 'neutral', label: 'Taslak' },
  finalized: { intent: 'warning', label: 'Onaylı' },
  submitted: { intent: 'info',    label: 'Gönderildi' },
  paid:      { intent: 'success', label: 'Ödendi' },
};

function DeclStatusBadge({ status }) {
  const { t } = useTranslation();
  const s = STATUS_INTENT[status] || { intent: 'default', label: status || '-' };
  return <StatusBadge intent={s.intent}>{s.label}</StatusBadge>;
}

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
  const { t } = useTranslation();
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
      const mime = fmt === "xml" ? "application/xml"
        : fmt === "pdf" ? "application/pdf"
        : "application/json";
      const blob = new Blob([res.data], { type: mime });
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

  // PDF beyannameyi e-posta ile gönder. Boş bırakılırsa config'teki
  // alıcılara gider; doluysa virgülle ayrılmış geçici alıcı listesini
  // tek seferlik olarak kullanır (config kalıcı değişmez).
  const emailDecl = async (decl) => {
    const defaults = (config?.email_recipients || []).join(", ");
    const input = await promptDialog({
      title: `Beyannameyi E-posta Gönder — ${decl.period}`,
      message: "Alıcı e-posta adres(ler)i (virgülle ayırın). Boş bırakırsanız "
        + "Yapılandırma'daki kayıtlı alıcılar kullanılır.",
      defaultValue: defaults,
      placeholder: "ornek@firma.com, muhasebe@firma.com",
    });
    if (input === null || input === undefined) return;
    const recipients = String(input).split(",").map((s) => s.trim())
      .filter((s) => s && s.includes("@"));
    if (input && recipients.length === 0) {
      toast.error("Geçerli e-posta adresi girilmedi");
      return;
    }
    setWorking(true);
    try {
      const { data } = await axios.post(
        `/finance/konaklama-vergisi/declarations/${decl.id}/email`,
        { recipients: recipients.length ? recipients : null });
      const ok = data?.sent || 0;
      const total = data?.total || 0;
      if (ok === total && ok > 0) {
        toast.success(`E-posta gönderildi (${ok}/${total})`);
      } else if (ok > 0) {
        toast.warning(`Kısmi gönderim: ${ok}/${total}`);
      } else {
        toast.error("E-posta gönderilemedi");
      }
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "E-posta gönderimi başarısız");
    } finally { setWorking(false); }
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

  // Mount: config + history paralel; tek setLoading toggle.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [cfgRes, histRes] = await Promise.allSettled([
          axios.get("/finance/konaklama-vergisi/config"),
          axios.get("/finance/konaklama-vergisi/declarations"),
        ]);
        if (cancelled) return;
        if (cfgRes.status === "fulfilled") setConfig(cfgRes.value.data);
        else toast.error("Yapılandırma yüklenemedi");
        if (histRes.status === "fulfilled") setHistory(histRes.value.data.items || []);
        else toast.error("Beyanname geçmişi yüklenemedi");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const saveConfig = async () => {
    setSaving(true);
    try {
      const recipients = Array.isArray(config.email_recipients)
        ? config.email_recipients
        : String(config.email_recipients || "").split(",").map((s) => s.trim());
      const payload = {
        rate_percent: Number(config.rate_percent || 2),
        active: !!config.active,
        auto_post: !!config.auto_post,
        effective_from: config.effective_from || null,
        notes: config.notes || null,
        exempt_segments: config.exempt_segments || [],
        auto_finalize: !!config.auto_finalize,
        auto_finalize_day: Math.max(1, Math.min(10,
          Number(config.auto_finalize_day || 1))),
        auto_email: !!config.auto_email,
        email_recipients: recipients.filter((s) => s && s.includes("@")),
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
      ["Folio ID", "Booking ID", "Geceleme", "Matrah (KDV hariç, TRY)"],
      ...report.rows.map((r) => [r._id, r.booking_id, r.nights, r.base_amount?.toFixed(2)]),
      [],
      ["TOPLAM", "", report.total_nights, report.total_base?.toFixed(2)],
      ["VERGİ (%" + report.rate_percent + ")", "", "", report.total_tax?.toFixed(2)],
    ];
    if (report.exempt_count) {
      rows.push([], ["MUAF FOLIO", "", "", report.exempt_count]);
      if (report.exempt_base) rows.push(["MUAF MATRAH", "", "", report.exempt_base?.toFixed(2)]);
    }
    downloadCSV(rows, `konaklama-vergisi-${year}-${String(month).padStart(2, "0")}.csv`);
  };

  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1);
  const yearOptions = Array.from({ length: 5 }, (_, i) => today.getFullYear() - i);

  const refreshAll = () => {
    loadConfig();
    loadHistory();
    if (tab === "report") loadReport();
    if (tab === "declaration") loadDeclaration();
  };

  return (
    <>
      <div className="p-4 lg:p-6 space-y-4">

      <PageHeader
        icon={Receipt}
        title="Konaklama Vergisi"
        subtitle={t('cm.pages_KonaklamaVergisiModule.7194_sayili_kanun_aylik_matrah_beyanname')}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={refreshAll}
            disabled={loading}
          >
            <RefreshCw className="w-4 h-4 mr-1.5" />
            {t('cm.pages_KonaklamaVergisiModule.yenile')}
          </Button>
        }
      />

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
                  active
                    ? "border-slate-900 text-slate-900 font-semibold"
                    : "border-transparent text-gray-500 hover:text-gray-800"
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
            <div className="flex items-center gap-2 text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> {t('cm.pages_KonaklamaVergisiModule.yukleniyor')}</div>
          ) : (
            <>
              <div className="flex items-start gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-3">
                <Info className="h-4 w-4 mt-0.5 shrink-0" />
                <div>
                  <b>{t('cm.pages_KonaklamaVergisiModule.matrah_oda_satiri_kdv_haric')}</b> {t('cm.pages_KonaklamaVergisiModule.konaklama_vergisi_7194_sk_uyarinca_kdv_m')}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-gray-600">{t('cm.pages_KonaklamaVergisiModule.vergi_orani')}</label>
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
                  <label className="text-xs font-medium text-gray-600">{t('cm.pages_KonaklamaVergisiModule.yururluk_tarihi')}</label>
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
                  {t('cm.pages_KonaklamaVergisiModule.aktif')}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={!!config.auto_post}
                    onChange={(e) => setConfig({ ...config, auto_post: e.target.checked })}
                  />
                  {t('cm.pages_KonaklamaVergisiModule.folio_ya_otomatik_vergi_satiri_ekle_chec')}
                </label>
              </div>

              <div>
                <label className="text-xs font-medium text-gray-600">{t('cm.pages_KonaklamaVergisiModule.notlar_muafiyet_aciklamasi')}</label>
                <textarea
                  className="border rounded px-3 py-2 w-full mt-1"
                  rows={3}
                  placeholder={t('cm.pages_KonaklamaVergisiModule.diplomatik_muafiyet_ogrenci_yurdu_vb')}
                  value={config.notes || ""}
                  onChange={(e) => setConfig({ ...config, notes: e.target.value })}
                />
              </div>

              {/* v95.9 — Otomatik Beyanname & E-posta Bölümü */}
              <div className="border-t pt-4 space-y-3">
                <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                  <Mail className="h-4 w-4" /> Otomatik Beyanname & E-posta
                </h4>
                <div className="flex items-start gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-3">
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    {t('cm.pages_KonaklamaVergisiModule.etkinlestirildiginde_her_ayin_belirtilen')} <b>{t('cm.pages_KonaklamaVergisiModule.onayli')}</b>
                    {" "}{t('cm.pages_KonaklamaVergisiModule.duruma_alinir')} <b>{t('cm.pages_KonaklamaVergisiModule.e_posta_gonderimi')}</b> {t('cm.pages_KonaklamaVergisiModule.aktifse_pdf_eki_ile_asagidaki_alicilara_')}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={!!config.auto_finalize}
                      onChange={(e) => setConfig({ ...config, auto_finalize: e.target.checked })}
                    />
                    {t('cm.pages_KonaklamaVergisiModule.otomatik_onaylama_onceki_ay')}
                  </label>
                  <div>
                    <label className="text-xs font-medium text-gray-600">{t('cm.pages_KonaklamaVergisiModule.onaylama_gunu_1_10')}</label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      className="border rounded px-3 py-2 w-full mt-1"
                      disabled={!config.auto_finalize}
                      value={config.auto_finalize_day ?? 1}
                      onChange={(e) => setConfig({ ...config, auto_finalize_day: parseInt(e.target.value) || 1 })}
                    />
                  </div>
                </div>

                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    disabled={!config.auto_finalize}
                    checked={!!config.auto_email}
                    onChange={(e) => setConfig({ ...config, auto_email: e.target.checked })}
                  />
                  {t('cm.pages_KonaklamaVergisiModule.onay_sonrasi_pdf_beyannameyi_e_posta_gon')}
                </label>

                <div>
                  <label className="text-xs font-medium text-gray-600">
                    {t('cm.pages_KonaklamaVergisiModule.e_posta_alicilari_virgulle_ayirin')}
                  </label>
                  <input
                    type="text"
                    className="border rounded px-3 py-2 w-full mt-1 font-mono text-xs"
                    placeholder="muhasebe@firma.com, mali-musavir@firma.com"
                    disabled={!config.auto_email}
                    value={Array.isArray(config.email_recipients)
                      ? config.email_recipients.join(", ")
                      : (config.email_recipients || "")}
                    onChange={(e) => setConfig({
                      ...config,
                      email_recipients: e.target.value.split(",").map((s) => s.trim()),
                    })}
                  />
                  <div className="text-xs text-slate-500 mt-1">
                    {t('cm.pages_KonaklamaVergisiModule.bu_liste_manuel_e_posta_gonder_isleminde')}
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button onClick={saveConfig} disabled={saving}>
                  {saving ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Save className="h-4 w-4 mr-1.5" />}
                  {t('cm.pages_KonaklamaVergisiModule.kaydet')}
                </Button>
              </div>
            </>
          )}
        </div>
      )}

      {(tab === "report" || tab === "declaration") && (
        <div className="bg-white rounded-lg border p-4 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 block">{t('cm.pages_KonaklamaVergisiModule.yil')}</label>
              <select className="border rounded px-3 py-2" value={year} onChange={(e) => setYear(Number(e.target.value))}>
                {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block">{t('cm.pages_KonaklamaVergisiModule.ay')}</label>
              <select className="border rounded px-3 py-2" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                {monthOptions.map((m) => <option key={m} value={m}>{String(m).padStart(2, "0")}</option>)}
              </select>
            </div>
            <Button
              onClick={tab === "report" ? loadReport : loadDeclaration}
              disabled={loading}
            >
              {loading ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1.5" />}
              {tab === "report" ? "Raporu Hesapla" : "Beyannameyi Oluştur"}
            </Button>
            {tab === "report" && report && (
              <Button variant="outline" onClick={exportReportCSV}>
                <Download className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.csv_indir')}
              </Button>
            )}
            {tab === "declaration" && declaration && (
              <Button variant="outline" onClick={() => window.print()}>
                <Printer className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.yazdir')}
              </Button>
            )}
          </div>

          {tab === "report" && report && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KpiCard icon={FileText} label={t('cm.pages_KonaklamaVergisiModule.folio_sayisi')} value={report.folio_count} />
                <KpiCard icon={ClipboardList} label={t('cm.pages_KonaklamaVergisiModule.toplam_geceleme')} value={report.total_nights} />
                <KpiCard icon={Calculator} label={t('cm.pages_KonaklamaVergisiModule.matrah_kdv_haric')} value={fmtTRY(report.total_base)} />
                <KpiCard icon={Receipt} label={`Vergi (%${report.rate_percent})`} value={fmtTRY(report.total_tax)} intent="warning" highlight />
              </div>
              {!!report.exempt_count && (
                <div className="flex items-start gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-3">
                  <ShieldOff className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    {t('cm.pages_KonaklamaVergisiModule.bu_donemde')} <b>{report.exempt_count}</b> folio muaf segment
                    nedeniyle matraha dâhil edilmedi
                    {report.exempt_base ? ` (toplam ${fmtTRY(report.exempt_base)} matrah dışı).` : "."}
                    {' '}{t('cm.pages_KonaklamaVergisiModule.muafiyet_kaynagi')} <b>{t('cm.pages_KonaklamaVergisiModule.yapilandirma_exempt_segments')}</b>.
                  </div>
                </div>
              )}
              <div className="overflow-auto border rounded">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-3 py-2">Folio ID</th>
                      <th className="text-left px-3 py-2">Booking</th>
                      <th className="text-right px-3 py-2">Geceleme</th>
                      <th className="text-right px-3 py-2">{t('cm.pages_KonaklamaVergisiModule.matrah_kdv_haric_270bc')}</th>
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
                      <tr><td colSpan={4} className="text-center text-gray-400 py-6">{t('cm.pages_KonaklamaVergisiModule.bu_donemde_oda_satiri_bulunamadi')}</td></tr>
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
                  <span className="font-medium">{t('cm.pages_KonaklamaVergisiModule.bu_donem_kilitli')}</span>
                  <DeclStatusBadge status={finalized.status} />
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
                      {t('cm.pages_KonaklamaVergisiModule.odeme')} <b>{finalized.payment_ref}</b>
                    </span>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {!finalized && (
                  <Button onClick={finalizeDeclaration} disabled={working}>
                    <Lock className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.beyannameyi_onayla_kilitle')}
                  </Button>
                )}
                {finalized && finalized.status === "finalized" && (
                  <Button variant="outline" onClick={() => submitDeclaration(finalized)} disabled={working}>
                    <Send className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.gib_tahakkuk_numarasi_kaydet')}
                  </Button>
                )}
                {finalized && (finalized.status === "submitted" || finalized.status === "finalized") && (
                  <Button variant="outline" onClick={() => payDeclaration(finalized)} disabled={working}>
                    <Wallet className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.odeme_kaydet')}
                  </Button>
                )}
                {finalized && (
                  <>
                    <Button variant="outline" onClick={() => exportDecl(finalized, "pdf")}>
                      <FileDown className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.pdf_indir')}
                    </Button>
                    <Button variant="outline" onClick={() => exportDecl(finalized, "xml")}>
                      <FileCode className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.xml_indir_gib')}
                    </Button>
                    <Button variant="outline" onClick={() => exportDecl(finalized, "json")}>
                      <Download className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.json_arsiv')}
                    </Button>
                    <Button variant="outline" onClick={() => emailDecl(finalized)} disabled={working}>
                      <Mail className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.e_posta_gonder')}
                    </Button>
                  </>
                )}
              </div>

              <div className="border rounded-lg p-6 print:p-0 print:border-0 max-w-3xl">
                <div className="text-center mb-4">
                  <h2 className="text-xl font-bold">{t('cm.pages_KonaklamaVergisiModule.konaklama_vergisi_beyannamesi')}</h2>
                  <p className="text-sm text-gray-500">{declaration.law_reference}</p>
                </div>
                <DeclRow label={t('cm.pages_KonaklamaVergisiModule.isletme')}>{declaration.tenant?.hotel_name || "-"}</DeclRow>
                <DeclRow label="Vergi No / Otel ID">{declaration.tenant?.tax_no || declaration.tenant?.hotel_id || "-"}</DeclRow>
                <DeclRow label={t('cm.pages_KonaklamaVergisiModule.donem')}>{declaration.period}</DeclRow>
                <DeclRow label={t('cm.pages_KonaklamaVergisiModule.son_beyan_odeme_tarihi')}>{declaration.due_date}</DeclRow>
                <DeclRow label={t('cm.pages_KonaklamaVergisiModule.vergi_orani_e8441')}>{`%${declaration.rate_percent}`}</DeclRow>
                <DeclRow label={t('cm.pages_KonaklamaVergisiModule.folio_sayisi_c53f2')}>{declaration.folio_count}</DeclRow>
                <DeclRow label={t('cm.pages_KonaklamaVergisiModule.toplam_geceleme_d27a1')}>{declaration.total_nights}</DeclRow>
                <DeclRow label={t('cm.pages_KonaklamaVergisiModule.matrah_kdv_haric_270bc')}>{fmtTRY(declaration.total_base)}</DeclRow>
                <DeclRow label="Tahakkuk Eden Vergi" highlight>{fmtTRY(declaration.total_tax)}</DeclRow>
                <p className="text-xs text-gray-400 mt-6">
                  {t('cm.pages_KonaklamaVergisiModule.bu_ozet_dahili_kontrol_amaclidir_resmi_b')}
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
              <History className="h-4 w-4" /> {t('cm.pages_KonaklamaVergisiModule.beyanname_gecmisi')}
            </h3>
            <Button variant="outline" size="sm" onClick={loadHistory}>
              <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.yenile_aedf3')}
            </Button>
          </div>
          <div className="overflow-auto border rounded">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-3 py-2">{t('cm.pages_KonaklamaVergisiModule.donem_625f5')}</th>
                  <th className="text-left px-3 py-2">{t('cm.pages_KonaklamaVergisiModule.durum')}</th>
                  <th className="text-right px-3 py-2">Matrah</th>
                  <th className="text-right px-3 py-2">Vergi</th>
                  <th className="text-left px-3 py-2">{t('cm.pages_KonaklamaVergisiModule.son_tarih')}</th>
                  <th className="text-left px-3 py-2">Tahakkuk</th>
                  <th className="text-left px-3 py-2">{t('cm.pages_KonaklamaVergisiModule.odeme_97fa2')}</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {history.map((d) => (
                  <tr key={d.id} className="border-t">
                    <td className="px-3 py-2 font-mono">{d.period}</td>
                    <td className="px-3 py-2"><DeclStatusBadge status={d.status} /></td>
                    <td className="px-3 py-2 text-right">{fmtTRY(d.total_base)}</td>
                    <td className="px-3 py-2 text-right font-semibold">{fmtTRY(d.total_tax)}</td>
                    <td className="px-3 py-2">{d.due_date}</td>
                    <td className="px-3 py-2 text-xs">{d.submission_ref || "-"}</td>
                    <td className="px-3 py-2 text-xs">{d.payment_ref || "-"}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => exportDecl(d, "pdf")}
                          title="PDF indir"
                        >
                          <FileDown className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => exportDecl(d, "xml")}
                          title={t('cm.pages_KonaklamaVergisiModule.xml_indir_gib_eb160')}
                        >
                          <FileCode className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => emailDecl(d)}
                          disabled={working}
                          title={t('cm.pages_KonaklamaVergisiModule.e_posta_gonder_6618f')}
                        >
                          <Mail className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {history.length === 0 && (
                  <tr>
                    <td colSpan={8} className="text-center text-gray-500 py-10">
                      <div className="flex flex-col items-center gap-3">
                        <FileText className="h-8 w-8 text-gray-300" />
                        <div>{t('cm.pages_KonaklamaVergisiModule.henuz_onaylanmis_beyanname_yok')}</div>
                        <Button onClick={() => setTab("declaration")}>
                          <Plus className="h-4 w-4 mr-1.5" /> {t('cm.pages_KonaklamaVergisiModule.ilk_beyannameyi_olustur')}
                        </Button>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "calculator" && (
        <div className="bg-white rounded-lg border p-4 max-w-xl space-y-4">
          <div className="flex items-start gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-3">
            <Info className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              {t('cm.pages_KonaklamaVergisiModule.girdiginiz')} <b>{t('cm.pages_KonaklamaVergisiModule.tutar')}</b> KDV <b>{t('cm.pages_KonaklamaVergisiModule.haric')}</b> {t('cm.pages_KonaklamaVergisiModule.oda_satiri_tutari_olmalidir_konaklama_ve')}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600">{t('cm.pages_KonaklamaVergisiModule.tutar_try_kdv_haric')}</label>
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
          <Button onClick={runCalc}>
            <Calculator className="h-4 w-4 mr-1.5" /> Hesapla
          </Button>
          {calcResult && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
              <KpiCard label={t('cm.pages_KonaklamaVergisiModule.matrah_kdv_haric_270bc')} value={fmtTRY(calcResult.base_amount)} />
              <KpiCard label={`Vergi %${calcResult.rate_percent}`} value={fmtTRY(calcResult.tax_amount)} intent="warning" highlight />
              <KpiCard label={t('cm.pages_KonaklamaVergisiModule.toplam_vergi_dahil')} value={fmtTRY(calcResult.total_with_tax)} />
              <KpiCard label="Geceleme" value={calcResult.nights} />
            </div>
          )}
        </div>
      )}
      </div>
    </>
  );
}

function DeclRow({ label, children, highlight }) {
  return (
    <div className={`flex justify-between border-b py-2 ${highlight ? "bg-slate-100 px-2 rounded font-bold text-slate-900" : ""}`}>
      <span className="text-gray-600">{label}</span>
      <span>{children}</span>
    </div>
  );
}
