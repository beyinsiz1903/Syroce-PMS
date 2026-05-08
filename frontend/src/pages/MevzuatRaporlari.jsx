import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

import {
  AlertTriangle, Award, BarChart3, CheckCircle2, ClipboardCheck,
  Download, FileText, Loader2, RefreshCw, ScrollText, Save, Send, ShieldCheck, Wifi, WifiOff,
} from "lucide-react";

const TABS = [
  { key: "tuik", label: "TÜİK Aylık Anketi", icon: BarChart3 },
  { key: "tga", label: "TGA Tesis Entegrasyon", icon: Send },
  { key: "inspection", label: "Bakanlık Denetim Hazırlık", icon: ShieldCheck },
  { key: "stars", label: "Yıldız Sınıflama Self-Check", icon: Award },
];

function fmtNum(v) { return new Intl.NumberFormat("tr-TR").format(Number(v || 0)); }

function downloadCSV(rows, filename) {
  const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export default function MevzuatRaporlari({ user, tenant, onLogout }) {
  const [tab, setTab] = useState("tuik");

  // ── TÜİK
  const today = useMemo(() => new Date(), []);
  const [year, setYear] = useState(today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() === 0 ? 12 : today.getMonth());
  const [tuik, setTuik] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadTuik = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/regulatory/tuik/monthly", { params: { year, month } });
      setTuik(data);
    } catch (e) { toast.error("Rapor yüklenemedi"); } finally { setLoading(false); }
  };

  const exportTuikCSV = () => {
    if (!tuik) return;
    const rows = [
      ["Dönem", tuik.period],
      ["Toplam Oda", tuik.capacity.rooms],
      ["Toplam Yatak", tuik.capacity.beds],
      ["Kapasite Oda-Gece", tuik.capacity.room_nights_capacity],
      ["Satılan Oda-Gece", tuik.stays.room_nights_sold],
      ["Doluluk %", tuik.occupancy_pct],
      ["Toplam Misafir", tuik.stays.guest_count],
      ["Yerli Kişi-Gece", tuik.stays.person_nights_domestic],
      ["Yabancı Kişi-Gece", tuik.stays.person_nights_foreign],
      ["Ortalama Kalış", tuik.average_length_of_stay],
      [],
      ["Ülke", "Kişi-Gece"],
      ...tuik.nationality_top20.map((n) => [n.country, n.person_nights]),
      ["Diğer", tuik.nationality_other_total],
    ];
    downloadCSV(rows, `tuik-konaklama-${tuik.period}.csv`);
  };

  // ── Inspection readiness
  const [readiness, setReadiness] = useState(null);
  const loadReadiness = async () => {
    try {
      const { data } = await axios.get("/regulatory/inspection-readiness");
      setReadiness(data);
    } catch { toast.error("Hazırlık raporu yüklenemedi"); }
  };

  // ── Star checklist
  const [checklist, setChecklist] = useState(null);
  const [savingCl, setSavingCl] = useState(false);
  const loadChecklist = async () => {
    try {
      const { data } = await axios.get("/regulatory/star-classification/checklist");
      setChecklist(data);
    } catch { toast.error("Kontrol listesi yüklenemedi"); }
  };
  const saveChecklist = async () => {
    if (!checklist) return;
    setSavingCl(true);
    try {
      const entries = checklist.items.map((i) => ({
        key: i.key, state: i.state, note: i.note || null,
      }));
      const { data } = await axios.post(
        "/regulatory/star-classification/checklist",
        { target_star: checklist.target_star, entries });
      setChecklist(data);
      toast.success(`Kaydedildi — uyumluluk %${data.compliance_score}`);
    } catch { toast.error("Kayıt başarısız"); }
    finally { setSavingCl(false); }
  };

  // ── TGA Tesis Entegrasyon
  const [tgaCfg, setTgaCfg] = useState(null);
  const [tgaForm, setTgaForm] = useState({
    belge_no: "", vergi_no: "", api_key: "",
    environment: "test", enabled: false,
  });
  const [tgaLog, setTgaLog] = useState([]);
  const [tgaPreview, setTgaPreview] = useState(null);
  const [tgaSaving, setTgaSaving] = useState(false);
  const [tgaSending, setTgaSending] = useState(false);
  const [tgaPreviewing, setTgaPreviewing] = useState(false);

  const loadTgaCfg = async () => {
    try {
      const { data } = await axios.get("/regulatory/tga/config");
      setTgaCfg(data);
      setTgaForm({
        belge_no: data.belge_no || "",
        vergi_no: data.vergi_no || "",
        api_key: "",
        environment: data.environment || "test",
        enabled: !!data.enabled,
      });
    } catch { toast.error("TGA ayarları yüklenemedi"); }
  };
  const loadTgaLog = async () => {
    try {
      const { data } = await axios.get("/regulatory/tga/log", { params: { days: 30 } });
      setTgaLog(data.items || []);
    } catch { /* sessiz */ }
  };
  const saveTgaCfg = async () => {
    setTgaSaving(true);
    try {
      const body = { ...tgaForm };
      if (!body.api_key) delete body.api_key;
      const { data } = await axios.put("/regulatory/tga/config", body);
      setTgaCfg(data);
      setTgaForm((f) => ({ ...f, api_key: "" }));
      toast.success("TGA ayarları kaydedildi");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kayıt başarısız");
    } finally { setTgaSaving(false); }
  };
  const previewTga = async () => {
    setTgaPreviewing(true);
    try {
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      const { data } = await axios.get("/regulatory/tga/preview", {
        params: { date: yesterday, days: 1 },
      });
      setTgaPreview(data.single || data);
    } catch { toast.error("Önizleme alınamadı"); }
    finally { setTgaPreviewing(false); }
  };
  const sendTgaNow = async () => {
    setTgaSending(true);
    try {
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      const { data } = await axios.post("/regulatory/tga/send", null, {
        params: { end_date: yesterday, days: 7 },
      });
      if (data.status === "sent") toast.success(`TGA'ya gönderildi (HTTP ${data.http_status})`);
      else if (data.status === "skipped") toast.error(`Atlandı: ${data.reason}`);
      else toast.error(`Başarısız: ${data.error || "HTTP " + data.http_status}`);
      await loadTgaLog();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gönderim başarısız");
    } finally { setTgaSending(false); }
  };

  useEffect(() => {
    if (tab === "inspection" && !readiness) loadReadiness();
    if (tab === "stars" && !checklist) loadChecklist();
    if (tab === "tga" && !tgaCfg) { loadTgaCfg(); loadTgaLog(); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [tab]);

  const monthOpts = Array.from({ length: 12 }, (_, i) => i + 1);
  const yearOpts = Array.from({ length: 5 }, (_, i) => today.getFullYear() - i);

  return (
    <>
    <div className="p-4 lg:p-6 space-y-4">

      <div className="border-b">
        <div className="flex flex-wrap gap-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`flex items-center gap-2 px-4 py-2 border-b-2 -mb-px text-sm transition ${
                  active ? "border-emerald-700 text-emerald-800 font-semibold"
                         : "border-transparent text-gray-500 hover:text-gray-800"}`}>
                <Icon className="h-4 w-4" /> {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {tab === "tuik" && (
        <div className="bg-white border rounded-lg p-4 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs text-gray-600 block">Yıl</label>
              <select className="border rounded px-3 py-2" value={year} onChange={(e) => setYear(Number(e.target.value))}>
                {yearOpts.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-600 block">Ay</label>
              <select className="border rounded px-3 py-2" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                {monthOpts.map((m) => <option key={m} value={m}>{String(m).padStart(2, "0")}</option>)}
              </select>
            </div>
            <button onClick={loadTuik} disabled={loading}
              className="flex items-center gap-2 bg-emerald-700 hover:bg-emerald-800 text-white px-4 py-2 rounded disabled:opacity-50">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Raporu Hesapla
            </button>
            {tuik && (
              <button onClick={exportTuikCSV}
                className="flex items-center gap-2 border px-4 py-2 rounded hover:bg-gray-50">
                <Download className="h-4 w-4" /> CSV İndir (TÜİK)
              </button>
            )}
            {tuik && (
              <button onClick={() => window.print()}
                className="flex items-center gap-2 border px-4 py-2 rounded hover:bg-gray-50">
                <FileText className="h-4 w-4" /> Yazdır
              </button>
            )}
          </div>

          {tuik && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI title="Toplam Oda" value={fmtNum(tuik.capacity.rooms)} />
                <KPI title="Toplam Yatak" value={fmtNum(tuik.capacity.beds)} />
                <KPI title="Doluluk" value={`%${tuik.occupancy_pct}`} highlight />
                <KPI title="Ortalama Kalış" value={tuik.average_length_of_stay} />
                <KPI title="Satılan Oda-Gece" value={fmtNum(tuik.stays.room_nights_sold)} />
                <KPI title="Toplam Misafir" value={fmtNum(tuik.stays.guest_count)} />
                <KPI title="Yerli Kişi-Gece" value={fmtNum(tuik.stays.person_nights_domestic)} />
                <KPI title="Yabancı Kişi-Gece" value={fmtNum(tuik.stays.person_nights_foreign)} highlight />
                {tuik.stays.person_nights_unspecified > 0 && (
                  <KPI title="Uyruk Belirsiz Kişi-Gece"
                       value={fmtNum(tuik.stays.person_nights_unspecified)}
                       warning />
                )}
              </div>
              {tuik.stays.person_nights_unspecified > 0 && (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 flex items-start gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>{fmtNum(tuik.stays.person_nights_unspecified)} kişi-gece için
                  uyruk girilmemiş. TÜİK gönderiminden önce ilgili rezervasyonlara
                  uyruk bilgisi eklenmesi önerilir.</span>
                </div>
              )}
              <div className="overflow-auto border rounded">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-3 py-2">Ülke (İlk 20)</th>
                      <th className="text-right px-3 py-2">Kişi-Gece</th>
                      <th className="text-right px-3 py-2">Pay %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tuik.nationality_top20.map((n) => {
                      const total = tuik.stays.person_nights_total || 1;
                      return (
                        <tr key={n.country} className="border-t">
                          <td className="px-3 py-1.5">{n.country}</td>
                          <td className="px-3 py-1.5 text-right">{fmtNum(n.person_nights)}</td>
                          <td className="px-3 py-1.5 text-right">{((n.person_nights / total) * 100).toFixed(1)}%</td>
                        </tr>
                      );
                    })}
                    {tuik.nationality_other_total > 0 && (
                      <tr className="border-t bg-gray-50">
                        <td className="px-3 py-1.5 italic">Diğer</td>
                        <td className="px-3 py-1.5 text-right">{fmtNum(tuik.nationality_other_total)}</td>
                        <td className="px-3 py-1.5 text-right">—</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-gray-400">
                Bu çıktı TÜİK e-Anket sistemine veri girişi içindir. Resmî
                gönderim TÜİK web portalı üzerinden yapılır.
              </p>
            </>
          )}
        </div>
      )}

      {tab === "tga" && (
        <div className="space-y-4">
          {/* Bilgi kutusu */}
          <div className="bg-sky-50 border border-sky-200 rounded-lg p-3 text-xs text-sky-900 leading-relaxed">
            <strong>TGA Tesis Entegrasyon API'si:</strong> Türkiye Turizm Tanıtım ve Geliştirme Ajansı,
            konaklama tesislerinden günlük operasyonel veri toplar. Sistem her 6 saatte bir
            son 7 günü otomatik gönderir; manuel tetikleme de mümkündür.
            <br />
            <strong>Ön gereklilik:</strong> TGA'dan tesisinize özel <em>X-API-Key</em> ile
            <em> Tesis Belge No</em> alınmış olmalı.
            Dokümantasyon: <a href="https://tesis-entegrasyon.tga.gov.tr/docs"
              target="_blank" rel="noreferrer" className="underline">tesis-entegrasyon.tga.gov.tr/docs</a>
          </div>

          {/* Ayarlar kartı */}
          <div className="bg-white border rounded-lg p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold flex items-center gap-2">
                <Send className="h-4 w-4" /> Bağlantı Ayarları
              </h3>
              {tgaCfg && (
                <span className={`text-xs px-2 py-0.5 rounded inline-flex items-center gap-1 ${
                  tgaCfg.enabled ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
                  {tgaCfg.enabled ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
                  {tgaCfg.enabled ? "Aktif" : "Pasif"} · {tgaCfg.environment === "live" ? "CANLI" : "TEST"}
                </span>
              )}
            </div>

            {!tgaCfg ? (
              <div className="text-sm text-gray-500 flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Yükleniyor…
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">Tesis Belge No</label>
                    <input type="text" placeholder="örn. TR-07-12345"
                      className="w-full border rounded px-3 py-2 text-sm"
                      value={tgaForm.belge_no}
                      onChange={(e) => setTgaForm({ ...tgaForm, belge_no: e.target.value })} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">Vergi No</label>
                    <input type="text" placeholder="10 hane"
                      className="w-full border rounded px-3 py-2 text-sm"
                      value={tgaForm.vergi_no}
                      onChange={(e) => setTgaForm({ ...tgaForm, vergi_no: e.target.value })} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs text-gray-600 block mb-1">
                      X-API-Key {tgaCfg.api_key_set && <span className="text-emerald-600">(kayıtlı — boş bırak: değişmez)</span>}
                    </label>
                    <input type="password" placeholder="pk_live_…"
                      className="w-full border rounded px-3 py-2 text-sm font-mono"
                      value={tgaForm.api_key}
                      onChange={(e) => setTgaForm({ ...tgaForm, api_key: e.target.value })} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">Ortam</label>
                    <select className="w-full border rounded px-3 py-2 text-sm"
                      value={tgaForm.environment}
                      onChange={(e) => setTgaForm({ ...tgaForm, environment: e.target.value })}>
                      <option value="test">Test</option>
                      <option value="live">Canlı</option>
                    </select>
                  </div>
                  <div className="flex items-end">
                    <label className="inline-flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={tgaForm.enabled}
                        onChange={(e) => setTgaForm({ ...tgaForm, enabled: e.target.checked })} />
                      Otomatik gönderimi aktifleştir
                    </label>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button onClick={saveTgaCfg} disabled={tgaSaving}
                    className="flex items-center gap-2 bg-emerald-700 hover:bg-emerald-800 text-white px-4 py-2 rounded text-sm disabled:opacity-50">
                    {tgaSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    Kaydet
                  </button>
                  <button onClick={previewTga} disabled={tgaPreviewing}
                    className="flex items-center gap-2 border px-4 py-2 rounded text-sm hover:bg-gray-50 disabled:opacity-50">
                    {tgaPreviewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                    Dünün Verisini Önizle
                  </button>
                  <button onClick={sendTgaNow} disabled={tgaSending || !tgaCfg.enabled || !tgaCfg.api_key_set}
                    className="flex items-center gap-2 bg-sky-700 hover:bg-sky-800 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
                    title={!tgaCfg.enabled ? "Önce ayarları aktifleştirin" : !tgaCfg.api_key_set ? "Önce API anahtarı kaydedin" : "Son 7 günü TGA'ya gönder"}>
                    {tgaSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    Şimdi Gönder (Son 7 Gün)
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Önizleme */}
          {tgaPreview && (
            <div className="bg-white border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-sm">Payload Önizleme — {tgaPreview.rapor_tarihi}</h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                <KPI title="Toplam Oda" value={fmtNum(tgaPreview.toplam_oda)} />
                <KPI title="Toplam Kişi" value={fmtNum(tgaPreview.toplam_kisi)} />
                <KPI title="Giren Oda" value={fmtNum(tgaPreview.giren_oda)} />
                <KPI title="Giren Kişi" value={fmtNum(tgaPreview.giren_kisi)} />
                <KPI title="Net Oda Geliri" value={fmtNum(tgaPreview.net_oda_geliri)} highlight />
              </div>
              <details className="text-xs">
                <summary className="cursor-pointer text-gray-600 hover:text-gray-900">Demografik & Kanal dökümünü göster</summary>
                <pre className="mt-2 bg-gray-50 border rounded p-2 overflow-auto max-h-80 text-[11px]">
                  {JSON.stringify({ demografik_veriler: tgaPreview.demografik_veriler, kanal_veriler: tgaPreview.kanal_veriler }, null, 2)}
                </pre>
              </details>
            </div>
          )}

          {/* Log */}
          <div className="bg-white border rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <ScrollText className="h-4 w-4" /> Son 30 Gün Gönderim Geçmişi
              </h3>
              <button onClick={loadTgaLog}
                className="text-xs flex items-center gap-1 text-blue-600 hover:underline">
                <RefreshCw className="h-3 w-3" /> Yenile
              </button>
            </div>
            {tgaLog.length === 0 ? (
              <div className="text-sm text-gray-500 italic">Henüz gönderim kaydı yok.</div>
            ) : (
              <div className="overflow-auto border rounded">
                <table className="min-w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-3 py-2">Zaman</th>
                      <th className="text-left px-3 py-2">Tarih Aralığı</th>
                      <th className="text-left px-3 py-2">Ortam</th>
                      <th className="text-left px-3 py-2">Tetikleyici</th>
                      <th className="text-center px-3 py-2">Durum</th>
                      <th className="text-right px-3 py-2">HTTP</th>
                      <th className="text-right px-3 py-2">Toplam Oda</th>
                      <th className="text-right px-3 py-2">Net Gelir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tgaLog.map((it, i) => {
                      const ok = it.status === "sent";
                      const skip = it.status === "skipped";
                      return (
                        <tr key={i} className="border-t">
                          <td className="px-3 py-1.5 font-mono">{(it.started_at || "").slice(0, 16).replace("T", " ")}</td>
                          <td className="px-3 py-1.5">son {it.days}g · {it.end_date}</td>
                          <td className="px-3 py-1.5">{it.environment === "live" ? "CANLI" : "TEST"}</td>
                          <td className="px-3 py-1.5">{it.triggered_by}</td>
                          <td className={`px-3 py-1.5 text-center font-semibold ${
                            ok ? "text-emerald-700" : skip ? "text-slate-500" : "text-rose-700"}`}>
                            {ok ? "Gönderildi" : skip ? "Atlandı" : "Hata"}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono">{it.http_status || "—"}</td>
                          <td className="px-3 py-1.5 text-right">{fmtNum(it.request_summary?.toplam_oda_sum)}</td>
                          <td className="px-3 py-1.5 text-right">{fmtNum(it.request_summary?.net_oda_geliri_sum)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "inspection" && (
        <div className="bg-white border rounded-lg p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2">
              <ShieldCheck className="h-4 w-4" /> Bakanlık Denetim Hazırlık
            </h3>
            <button onClick={loadReadiness} className="text-sm flex items-center gap-1 text-blue-600 hover:underline">
              <RefreshCw className="h-3 w-3" /> Yenile
            </button>
          </div>
          {!readiness ? (
            <div className="text-gray-500 text-sm flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Yükleniyor…
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI title="Hazırlık Skoru" value={`%${readiness.readiness_score}`} highlight />
                <KPI title="Toplam Oda" value={fmtNum(readiness.rooms_total)} />
                <KPI title="Aktif Personel" value={fmtNum(readiness.active_users)} />
                <KPI title="İşletme Belgesi (gün)"
                     value={readiness.license_days_left == null ? "—" : fmtNum(readiness.license_days_left)}
                     warning={readiness.license_days_left != null && readiness.license_days_left < 30} />
              </div>

              <div className="border rounded">
                <div className="bg-gray-50 px-3 py-2 font-semibold text-sm">Kontrol Noktaları</div>
                <ul className="divide-y">
                  {readiness.checks.map((c) => (
                    <li key={c.key} className="px-3 py-2 flex items-center gap-2 text-sm">
                      {c.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                            : <AlertTriangle className="h-4 w-4 text-amber-600" />}
                      <span className={c.ok ? "" : "text-amber-800"}>{c.label}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="border rounded">
                <div className="bg-gray-50 px-3 py-2 font-semibold text-sm">Son 12 Ay Rezervasyon Hacmi</div>
                <div className="overflow-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-3 py-2">Dönem</th>
                        <th className="text-right px-3 py-2">Aktif Rezervasyon</th>
                        <th className="text-right px-3 py-2">Kapasite Oda-Gece</th>
                        <th className="text-right px-3 py-2">Kaba Doluluk %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {readiness.booking_trend_12m.map((m) => (
                        <tr key={m.period} className="border-t">
                          <td className="px-3 py-1 font-mono">{m.period}</td>
                          <td className="px-3 py-1 text-right">{fmtNum(m.booking_count)}</td>
                          <td className="px-3 py-1 text-right">{fmtNum(m.capacity_room_nights)}</td>
                          <td className="px-3 py-1 text-right">{m.occupancy_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <p className="text-xs text-gray-400">
                Bu rapor, Bakanlık denetim ziyaretlerine hazırlık amaçlı dahili
                bir özettir; resmî denetimin yerini almaz.
              </p>
            </>
          )}
        </div>
      )}

      {tab === "stars" && (
        <div className="bg-white border rounded-lg p-4 space-y-4">
          {!checklist ? (
            <div className="text-gray-500 text-sm flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Yükleniyor…
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="text-xs text-gray-600 block">Hedef Yıldız</label>
                  <select className="border rounded px-3 py-2" value={checklist.target_star}
                          onChange={(e) => setChecklist({ ...checklist, target_star: Number(e.target.value) })}>
                    {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>{s} Yıldız</option>)}
                  </select>
                </div>
                <div className="flex-1 min-w-[160px]">
                  <KPI title="Uyumluluk Skoru" value={`%${checklist.compliance_score}`} highlight />
                </div>
                <div>
                  <KPI title="Eksik Zorunlu Kriter" value={`${checklist.required_missing} / ${checklist.required_total}`}
                       warning={checklist.required_missing > 0} />
                </div>
                <button onClick={saveChecklist} disabled={savingCl}
                  className="flex items-center gap-2 bg-emerald-700 hover:bg-emerald-800 text-white px-4 py-2 rounded disabled:opacity-50">
                  {savingCl ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Kaydet & Hesapla
                </button>
              </div>

              {Object.entries(checklist.items.reduce((acc, it) => {
                (acc[it.category] = acc[it.category] || []).push(it);
                return acc;
              }, {})).map(([cat, items]) => (
                <div key={cat} className="border rounded">
                  <div className="bg-gray-50 px-3 py-2 font-semibold text-sm">{cat}</div>
                  <ul className="divide-y">
                    {items.map((it) => (
                      <li key={it.key} className={`px-3 py-2 flex items-center gap-3 text-sm ${
                        it.required && it.state !== "yes" ? "bg-amber-50" : ""}`}>
                        <div className="flex-1">
                          <span>{it.label}</span>
                          {it.required && (
                            <span className="ml-2 text-xs px-1.5 py-0.5 bg-red-100 text-red-700 rounded">
                              {checklist.target_star} için zorunlu
                            </span>
                          )}
                        </div>
                        <select value={it.state} className="border rounded px-2 py-1 text-xs"
                          onChange={(e) => {
                            const items2 = checklist.items.map((x) =>
                              x.key === it.key ? { ...x, state: e.target.value } : x);
                            setChecklist({ ...checklist, items: items2 });
                          }}>
                          <option value="yes">Var</option>
                          <option value="partial">~ Kısmen</option>
                          <option value="no">Yok</option>
                        </select>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {checklist.saved_at && (
                <p className="text-xs text-gray-400 flex items-center gap-1">
                  <ClipboardCheck className="h-3 w-3" />
                  Son kayıt: {checklist.saved_at.slice(0, 16).replace("T", " ")}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
    </>
  );
}

function KPI({ title, value, highlight, warning }) {
  const cls = warning ? "bg-amber-50 border-amber-300"
            : highlight ? "bg-emerald-50 border-emerald-300" : "";
  const txt = warning ? "text-amber-700"
            : highlight ? "text-emerald-700" : "";
  return (
    <div className={`border rounded-lg p-3 ${cls}`}>
      <div className="text-xs text-gray-500">{title}</div>
      <div className={`text-lg font-semibold ${txt}`}>{value}</div>
    </div>
  );
}
