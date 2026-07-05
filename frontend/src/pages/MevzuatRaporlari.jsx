import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Award, BarChart3, CheckCircle2, ClipboardCheck, Download, ExternalLink, FileText, Loader2, RefreshCw, ScrollText, Save, Send, Settings, ShieldCheck, UserX, Wifi, WifiOff } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useTranslation } from 'react-i18next';
const TABS = [{
  key: "tuik",
  label: "TÜİK Aylık Anketi",
  icon: BarChart3
}, {
  key: "tga",
  label: "TGA Tesis Entegrasyon",
  icon: Send
}, {
  key: "inspection",
  label: "Bakanlık Denetim Hazırlık",
  icon: ShieldCheck
}, {
  key: "stars",
  label: "Yıldız Sınıflama Self-Check",
  icon: Award
}];
function fmtNum(v) {
  return new Intl.NumberFormat("tr-TR").format(Number(v || 0));
}
function downloadCSV(rows, filename) {
  const csv = rows.map(r => r.map(c => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff" + csv], {
    type: "text/csv;charset=utf-8;"
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
function RefreshButton({
  onClick,
  loading,
  label = "Yenile"
}) {
  const { t, i18n } = useTranslation();
  return <Button variant="outline" size="sm" onClick={onClick} disabled={loading}>
      {loading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
      {label}
    </Button>;
}
export default function MevzuatRaporlari({
  user,
  tenant
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [tab, setTab] = useState("tuik");
  const isSuperAdmin = user?.role === "SUPER_ADMIN" || user?.role === "super_admin";

  // ── TÜİK
  const today = useMemo(() => new Date(), []);
  // Cari ay (1-12). Ocak değilse year aynı; Ocak'ta da today.getMonth()=0 → ay 1, yıl aynı.
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [tuik, setTuik] = useState(null);
  const [loading, setLoading] = useState(false);
  const [missingOpen, setMissingOpen] = useState(false);
  const loadTuik = async () => {
    setLoading(true);
    try {
      const {
        data
      } = await axios.get("/regulatory/tuik/monthly", {
        params: {
          year,
          month
        }
      });
      setTuik(data);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 403) toast.error("Bu raporu görme yetkiniz yok (yönetici izni gerekir).");else toast.error("Rapor yüklenemedi");
    } finally {
      setLoading(false);
    }
  };
  const exportTuikCSV = () => {
    if (!tuik) return;
    const rows = [["Dönem", tuik.period], ["Toplam Oda", tuik.capacity.rooms], ["Toplam Yatak", tuik.capacity.beds], ["Kapasite Oda-Gece", tuik.capacity.room_nights_capacity], ["Satılan Oda-Gece", tuik.stays.room_nights_sold], ["Doluluk %", tuik.occupancy_pct], ["Toplam Misafir", tuik.stays.guest_count], ["Yerli Kişi-Gece", tuik.stays.person_nights_domestic], ["Yabancı Kişi-Gece", tuik.stays.person_nights_foreign], ["Uyruk Belirsiz Kişi-Gece", tuik.stays.person_nights_unspecified], ["Ortalama Kalış", tuik.average_length_of_stay], [], ["Ülke", "Kişi-Gece"], ...tuik.nationality_top20.map(n => [n.country, n.person_nights]), ["Diğer", tuik.nationality_other_total]];
    downloadCSV(rows, `tuik-konaklama-${tuik.period}.csv`);
  };

  // ── Inspection readiness
  const [readiness, setReadiness] = useState(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const loadReadiness = async (nocache = false) => {
    setReadinessLoading(true);
    try {
      const {
        data
      } = await axios.get("/regulatory/inspection-readiness", nocache ? {
        params: {
          nocache: "true"
        }
      } : undefined);
      setReadiness(data);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 403) toast.error("Bu raporu görme yetkiniz yok (yönetici izni gerekir).");else toast.error("Hazırlık raporu yüklenemedi");
    } finally {
      setReadinessLoading(false);
    }
  };
  const exportReadinessCSV = () => {
    if (!readiness) return;
    const rows = [["Bakanlık Denetim Hazırlık Raporu"], ["Tesis", readiness.tenant?.hotel_name || "—"], ["Hazırlık Skoru", `%${readiness.readiness_score}`], ["Toplam Oda", readiness.rooms_total], ["Aktif Personel", readiness.active_users], ["İşletme Belgesi (gün)", readiness.license_days_left ?? "—"], [], ["Kontrol Noktası", "Durum"], ...readiness.checks.map(c => [c.label, c.ok ? "TAMAM" : "EKSİK"]), [], ["Dönem", "Aktif Rezervasyon", "Kapasite Oda-Gece", "Doluluk %"], ...readiness.booking_trend_12m.map(m => [m.period, m.booking_count, m.capacity_room_nights, m.occupancy_pct])];
    downloadCSV(rows, `bakanlik-denetim-hazirlik-${new Date().toISOString().slice(0, 10)}.csv`);
  };
  const goToTenantSettings = () => {
    if (isSuperAdmin) {
      const tid = readiness?.tenant?.hotel_id || tenant?.id || tenant?.hotel_id;
      navigate(tid ? `/admin/tenants?edit=${encodeURIComponent(tid)}` : "/admin/tenants");
    } else {
      toast.info("Bu alanları yalnızca tesis yöneticisi düzenleyebilir. Lütfen yöneticinizle iletişime geçin.");
    }
  };
  const goToMissingNationality = () => {
    setMissingOpen(true);
  };
  const openBookingForFix = id => {
    if (!id) return;
    setMissingOpen(false);
    navigate(`/app/pms?edit=${encodeURIComponent(id)}#bookings`);
  };

  // ── Star checklist
  const [checklist, setChecklist] = useState(null);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [savingCl, setSavingCl] = useState(false);
  const loadChecklist = async (nocache = false) => {
    setChecklistLoading(true);
    try {
      const {
        data
      } = await axios.get("/regulatory/star-classification/checklist", nocache ? {
        params: {
          nocache: "true"
        }
      } : undefined);
      setChecklist(data);
    } catch {
      toast.error("Kontrol listesi yüklenemedi");
    } finally {
      setChecklistLoading(false);
    }
  };
  const saveChecklist = async () => {
    if (!checklist) return;
    setSavingCl(true);
    try {
      const entries = checklist.items.map(i => ({
        key: i.key,
        state: i.state,
        note: i.note || null
      }));
      const {
        data
      } = await axios.post("/regulatory/star-classification/checklist", {
        target_star: checklist.target_star,
        entries
      });
      setChecklist(data);
      toast.success(`Kaydedildi — uyumluluk %${data.compliance_score}`);
    } catch {
      toast.error("Kayıt başarısız");
    } finally {
      setSavingCl(false);
    }
  };

  // ── TGA Tesis Entegrasyon
  const [tgaCfg, setTgaCfg] = useState(null);
  const [tgaForm, setTgaForm] = useState({
    belge_no: "",
    vergi_no: "",
    api_key: "",
    environment: "test",
    enabled: false
  });
  const [tgaLog, setTgaLog] = useState([]);
  const [tgaPreview, setTgaPreview] = useState(null);
  const [tgaSaving, setTgaSaving] = useState(false);
  const [tgaSending, setTgaSending] = useState(false);
  const [tgaPreviewing, setTgaPreviewing] = useState(false);
  const [tgaLogLoading, setTgaLogLoading] = useState(false);
  const loadTgaCfg = async () => {
    try {
      const {
        data
      } = await axios.get("/regulatory/tga/config");
      setTgaCfg(data);
      setTgaForm({
        belge_no: data.belge_no || "",
        vergi_no: data.vergi_no || "",
        api_key: "",
        environment: data.environment || "test",
        enabled: !!data.enabled
      });
    } catch {
      toast.error("TGA ayarları yüklenemedi");
    }
  };
  const loadTgaLog = async () => {
    setTgaLogLoading(true);
    try {
      const {
        data
      } = await axios.get("/regulatory/tga/log", {
        params: {
          days: 30
        }
      });
      setTgaLog(data.items || []);
    } catch {/* sessiz */} finally {
      setTgaLogLoading(false);
    }
  };
  const saveTgaCfg = async () => {
    setTgaSaving(true);
    try {
      const body = {
        ...tgaForm
      };
      if (!body.api_key) delete body.api_key;
      const {
        data
      } = await axios.put("/regulatory/tga/config", body);
      setTgaCfg(data);
      setTgaForm(f => ({
        ...f,
        api_key: ""
      }));
      toast.success("TGA ayarları kaydedildi");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kayıt başarısız");
    } finally {
      setTgaSaving(false);
    }
  };
  const previewTga = async () => {
    setTgaPreviewing(true);
    try {
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      const {
        data
      } = await axios.get("/regulatory/tga/preview", {
        params: {
          date: yesterday,
          days: 1
        }
      });
      setTgaPreview(data.single || data);
    } catch {
      toast.error("Önizleme alınamadı");
    } finally {
      setTgaPreviewing(false);
    }
  };
  const sendTgaNow = async () => {
    setTgaSending(true);
    try {
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      const {
        data
      } = await axios.post("/regulatory/tga/send", null, {
        params: {
          end_date: yesterday,
          days: 7
        }
      });
      if (data.status === "sent") toast.success(`TGA'ya gönderildi (HTTP ${data.http_status})`);else if (data.status === "skipped") toast.error(`Atlandı: ${data.reason}`);else toast.error(`Başarısız: ${data.error || "HTTP " + data.http_status}`);
      await loadTgaLog();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gönderim başarısız");
    } finally {
      setTgaSending(false);
    }
  };

  // TGA dirty flag — form değişti, henüz kaydedilmedi.
  const tgaDirty = useMemo(() => {
    if (!tgaCfg) return false;
    return (tgaForm.belge_no || "") !== (tgaCfg.belge_no || "") || (tgaForm.vergi_no || "") !== (tgaCfg.vergi_no || "") || (tgaForm.environment || "test") !== (tgaCfg.environment || "test") || !!tgaForm.enabled !== !!tgaCfg.enabled || !!tgaForm.api_key;
  }, [tgaForm, tgaCfg]);
  const sendDisabledReason = (() => {
    if (!tgaCfg) return null;
    if (tgaDirty) return "Önce değişiklikleri kaydedin.";
    if (!tgaCfg.enabled) return "Önce ayarları aktifleştirin ve kaydedin.";
    if (!tgaCfg.api_key_set) return "Önce API anahtarı kaydedin.";
    return null;
  })();
  useEffect(() => {
    if (tab === "tuik" && !tuik && !loading) loadTuik();
    if (tab === "inspection" && !readiness) loadReadiness();
    if (tab === "stars" && !checklist) loadChecklist();
    if (tab === "tga" && !tgaCfg) {
      loadTgaCfg();
      loadTgaLog();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);
  const monthOpts = Array.from({
    length: 12
  }, (_, i) => i + 1);
  const yearOpts = Array.from({
    length: 5
  }, (_, i) => today.getFullYear() - i);

  // 12-ay sparkline maks değeri (occupancy_pct).
  const trendMax = readiness?.booking_trend_12m ? Math.max(1, ...readiness.booking_trend_12m.map(m => m.occupancy_pct || 0)) : 1;
  const refreshAction = tab === "tuik" ? <RefreshButton onClick={loadTuik} loading={loading} label="Hesapla" /> : tab === "inspection" ? <RefreshButton onClick={() => loadReadiness(true)} loading={readinessLoading} /> : tab === "stars" ? <RefreshButton onClick={() => loadChecklist(true)} loading={checklistLoading} /> : tab === "tga" ? <RefreshButton onClick={loadTgaLog} loading={tgaLogLoading} /> : null;
  return <div className="p-4 lg:p-6 space-y-4">
      <PageHeader icon={ScrollText} title="Mevzuat & Resmi Raporlar" subtitle={t('cm.pages_MevzuatRaporlari.tuik_tga_bakanlik_denetim_hazirligi_ve_y')} actions={refreshAction} />

      <div className="border-b">
        <div className="flex flex-wrap gap-1">
          {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.key;
          return <button key={t.key} onClick={() => setTab(t.key)} className={`flex items-center gap-2 px-4 py-2 border-b-2 -mb-px text-sm transition ${active ? "border-slate-900 text-slate-900 font-semibold" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
                <Icon className="h-4 w-4" /> {t.label}
              </button>;
        })}
        </div>
      </div>

      {tab === "tuik" && <div className="bg-white border rounded-lg p-4 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs text-slate-600 block">{t('cm.pages_MevzuatRaporlari.yil')}</label>
              <select className="border rounded px-3 py-2" value={year} onChange={e => setYear(Number(e.target.value))}>
                {yearOpts.map(y => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-600 block">{t('cm.pages_MevzuatRaporlari.ay')}</label>
              <select className="border rounded px-3 py-2" value={month} onChange={e => setMonth(Number(e.target.value))}>
                {monthOpts.map(m => <option key={m} value={m}>{String(m).padStart(2, "0")}</option>)}
              </select>
            </div>
            <Button onClick={loadTuik} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1.5" />}
              Raporu Hesapla
            </Button>
            {tuik && <Button variant="outline" size="sm" onClick={exportTuikCSV}>
                <Download className="h-4 w-4 mr-1.5" /> {t('cm.pages_MevzuatRaporlari.csv_indir')}
              </Button>}
            {tuik && <Button variant="outline" size="sm" onClick={() => window.print()}>
                <FileText className="h-4 w-4 mr-1.5" /> {t('cm.pages_MevzuatRaporlari.yazdir')}
              </Button>}
          </div>

          {!tuik && !loading && <div className="text-sm text-slate-500 italic">
              {t('cm.pages_MevzuatRaporlari.yil_ve_ay_secip_raporu_hesapla_butonuna_')}
            </div>}
          {loading && !tuik && <div className="text-sm text-slate-500 flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> {t('cm.pages_MevzuatRaporlari.cari_ay_raporu_hesaplaniyor')}
            </div>}

          {tuik && <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KpiCard label={t('cm.pages_MevzuatRaporlari.toplam_oda')} value={fmtNum(tuik.capacity.rooms)} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.toplam_yatak')} value={fmtNum(tuik.capacity.beds)} intent="neutral" />
                <KpiCard label="Doluluk" value={`%${tuik.occupancy_pct}`} intent="info" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.ortalama_kalis')} value={tuik.average_length_of_stay} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.satilan_oda_gece')} value={fmtNum(tuik.stays.room_nights_sold)} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.toplam_misafir')} value={fmtNum(tuik.stays.guest_count)} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.yerli_kisi_gece')} value={fmtNum(tuik.stays.person_nights_domestic)} intent="success" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.yabanci_kisi_gece')} value={fmtNum(tuik.stays.person_nights_foreign)} intent="info" />
                {tuik.stays.person_nights_unspecified > 0 && <KpiCard label={t('cm.pages_MevzuatRaporlari.uyruk_belirsiz_kisi_gece')} value={fmtNum(tuik.stays.person_nights_unspecified)} intent="warning" />}
              </div>

              {tuik.stays.person_nights_unspecified > 0 && <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-3 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-600" />
                  <div className="flex-1">
                    <div className="font-semibold mb-1">
                      {fmtNum(tuik.stays.person_nights_unspecified)} {t('cm.pages_MevzuatRaporlari.kisi_gece_icin_uyruk_girilmemis')}
                    </div>
                    <div className="text-xs text-amber-700">
                      {t('cm.pages_MevzuatRaporlari.tuik_formu_yerli_yabanci_ayrimi_zorunlud')}{" "}
                      <strong>{fmtNum(tuik.missing_nationality?.booking_count || 0)}</strong>.
                    </div>
                    {tuik.missing_nationality?.samples?.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Button variant="outline" size="sm" onClick={goToMissingNationality}>
                          {t('cm.pages_MevzuatRaporlari.eksik_uyruklu_rezervasyonlari_gor')}
                        </Button>
                        <span className="text-xs text-amber-700">
                          {t('cm.pages_MevzuatRaporlari.ilk_ornek')} {tuik.missing_nationality.samples[0].confirmation_number || tuik.missing_nationality.samples[0].id} —
                          {" "}{tuik.missing_nationality.samples[0].guest_name || "—"})
                        </span>
                      </div>}
                  </div>
                </div>}

              {tuik.data_quality?.adults_defaulted_count > 0 && <div className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-2 flex items-start gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-500" />
                  <span>
                    {fmtNum(tuik.data_quality.adults_defaulted_count)} {t('cm.pages_MevzuatRaporlari.rezervasyonda_yetiskin_sayisi_bos_kisi_g')}
                  </span>
                </div>}

              <div className="overflow-auto border rounded">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left px-3 py-2">{t('cm.pages_MevzuatRaporlari.ulke_ilk_20')}</th>
                      <th className="text-right px-3 py-2">{t('cm.pages_MevzuatRaporlari.kisi_gece')}</th>
                      <th className="text-right px-3 py-2">Pay %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tuik.nationality_top20.map(n => {
                const total = tuik.stays.person_nights_total || 1;
                return <tr key={n.country} className="border-t">
                          <td className="px-3 py-1.5">{n.country}</td>
                          <td className="px-3 py-1.5 text-right">{fmtNum(n.person_nights)}</td>
                          <td className="px-3 py-1.5 text-right">{(n.person_nights / total * 100).toFixed(1)}%</td>
                        </tr>;
              })}
                    {tuik.nationality_other_total > 0 && <tr className="border-t bg-slate-50">
                        <td className="px-3 py-1.5 italic">{t('cm.pages_MevzuatRaporlari.diger')}</td>
                        <td className="px-3 py-1.5 text-right">{fmtNum(tuik.nationality_other_total)}</td>
                        <td className="px-3 py-1.5 text-right">—</td>
                      </tr>}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-400">
                {t('cm.pages_MevzuatRaporlari.bu_cikti_tuik_e_anket_sistemine_veri_gir')}
              </p>
            </>}
        </div>}

      {tab === "tga" && <div className="space-y-4">
          <div className="bg-sky-50 border border-sky-200 rounded-lg p-3 text-xs text-sky-900 leading-relaxed">
            <strong>TGA Tesis Entegrasyon API'si:</strong> {t('cm.pages_MevzuatRaporlari.turkiye_turizm_tanitim_ve_gelistirme_aja')}
            <br />
            <strong>{t('cm.pages_MevzuatRaporlari.on_gereklilik')}</strong> {t('cm.pages_MevzuatRaporlari.tga_dan_tesisinize_ozel')} <em>X-API-Key</em> ile
            <em> Tesis Belge No</em> {t('cm.pages_MevzuatRaporlari.alinmis_olmali_dokumantasyon')} <a href="https://tesis-entegrasyon.tga.gov.tr/docs" target="_blank" rel="noreferrer" className="underline">tesis-entegrasyon.tga.gov.tr/docs</a>
          </div>

          <div className="bg-white border rounded-lg p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold flex items-center gap-2">
                <Send className="h-4 w-4" /> {t('cm.pages_MevzuatRaporlari.baglanti_ayarlari')}
              </h3>
              {tgaCfg && <StatusBadge intent={tgaCfg.enabled ? "success" : "neutral"} icon={tgaCfg.enabled ? Wifi : WifiOff}>
                  {tgaCfg.enabled ? "Aktif" : "Pasif"} · {tgaCfg.environment === "live" ? "CANLI" : "TEST"}
                </StatusBadge>}
            </div>

            {!tgaCfg ? <div className="text-sm text-slate-500 flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> {t('cm.pages_MevzuatRaporlari.yukleniyor')}
              </div> : <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-slate-600 block mb-1">Tesis Belge No</label>
                    <input type="text" placeholder={t('cm.pages_MevzuatRaporlari.orn_tr_07_12345')} className="w-full border rounded px-3 py-2 text-sm" value={tgaForm.belge_no} onChange={e => setTgaForm({
                ...tgaForm,
                belge_no: e.target.value
              })} />
                  </div>
                  <div>
                    <label className="text-xs text-slate-600 block mb-1">Vergi No</label>
                    <input type="text" placeholder="10 hane" className="w-full border rounded px-3 py-2 text-sm" value={tgaForm.vergi_no} onChange={e => setTgaForm({
                ...tgaForm,
                vergi_no: e.target.value
              })} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs text-slate-600 block mb-1">
                      X-API-Key {tgaCfg.api_key_set && <span className="text-emerald-700">{t('cm.pages_MevzuatRaporlari.kayitli_bos_birak_degismez')}</span>}
                    </label>
                    <input type="password" placeholder="pk_live_…" className="w-full border rounded px-3 py-2 text-sm font-mono" value={tgaForm.api_key} onChange={e => setTgaForm({
                ...tgaForm,
                api_key: e.target.value
              })} />
                  </div>
                  <div>
                    <label className="text-xs text-slate-600 block mb-1">Ortam</label>
                    <select className="w-full border rounded px-3 py-2 text-sm" value={tgaForm.environment} onChange={e => setTgaForm({
                ...tgaForm,
                environment: e.target.value
              })}>
                      <option value="test">Test</option>
                      <option value="live">{t('cm.pages_MevzuatRaporlari.canli')}</option>
                    </select>
                  </div>
                  <div className="flex items-end">
                    <label className="inline-flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={tgaForm.enabled} onChange={e => setTgaForm({
                  ...tgaForm,
                  enabled: e.target.checked
                })} />
                      {t('cm.pages_MevzuatRaporlari.otomatik_gonderimi_aktiflestir')}
                    </label>
                  </div>
                </div>

                {tgaDirty && <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2 flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-600" />
                    <span>{t('cm.pages_MevzuatRaporlari.kaydedilmemis_degisiklikler_var_simdi_go')}</span>
                  </div>}

                <div className="flex flex-wrap gap-2">
                  <Button onClick={saveTgaCfg} disabled={tgaSaving}>
                    {tgaSaving ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Save className="h-4 w-4 mr-1.5" />}
                    {t('cm.pages_MevzuatRaporlari.kaydet')}
                  </Button>
                  <Button variant="outline" size="sm" onClick={previewTga} disabled={tgaPreviewing}>
                    {tgaPreviewing ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <FileText className="h-4 w-4 mr-1.5" />}
                    {t('cm.pages_MevzuatRaporlari.dunun_verisini_onizle')}
                  </Button>
                  <Button onClick={sendTgaNow} disabled={tgaSending || !!sendDisabledReason} title={sendDisabledReason || "Son 7 günü TGA'ya gönder"}>
                    {tgaSending ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Send className="h-4 w-4 mr-1.5" />}
                    {t('cm.pages_MevzuatRaporlari.simdi_gonder_son_7_gun')}
                  </Button>
                  {sendDisabledReason && <span className="text-xs text-slate-500 self-center">{sendDisabledReason}</span>}
                </div>
              </>}
          </div>

          {tgaPreview && <div className="bg-white border rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-sm">{t('cm.pages_MevzuatRaporlari.payload_onizleme')} {tgaPreview.rapor_tarihi}</h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                <KpiCard label={t('cm.pages_MevzuatRaporlari.toplam_oda_3026f')} value={fmtNum(tgaPreview.toplam_oda)} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.toplam_kisi')} value={fmtNum(tgaPreview.toplam_kisi)} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.giren_oda')} value={fmtNum(tgaPreview.giren_oda)} intent="info" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.giren_kisi')} value={fmtNum(tgaPreview.giren_kisi)} intent="info" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.net_oda_geliri')} value={fmtNum(tgaPreview.net_oda_geliri)} intent="success" />
              </div>
              <details className="text-xs">
                <summary className="cursor-pointer text-slate-600 hover:text-slate-900">{t('cm.pages_MevzuatRaporlari.demografik_kanal_dokumunu_goster')}</summary>
                <pre className="mt-2 bg-slate-50 border rounded p-2 overflow-auto max-h-80 text-[11px]">
                  {JSON.stringify({
              demografik_veriler: tgaPreview.demografik_veriler,
              kanal_veriler: tgaPreview.kanal_veriler
            }, null, 2)}
                </pre>
              </details>
            </div>}

          <div className="bg-white border rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <ScrollText className="h-4 w-4" /> {t('cm.pages_MevzuatRaporlari.son_30_gun_gonderim_gecmisi')}
              </h3>
              <RefreshButton onClick={loadTgaLog} loading={tgaLogLoading} />
            </div>
            {tgaLog.length === 0 ? <div className="text-sm text-slate-500 italic">{t('cm.pages_MevzuatRaporlari.henuz_gonderim_kaydi_yok')}</div> : <div className="overflow-auto border rounded">
                <table className="min-w-full text-xs">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left px-3 py-2">Zaman</th>
                      <th className="text-left px-3 py-2">{t('cm.pages_MevzuatRaporlari.tarih_araligi')}</th>
                      <th className="text-left px-3 py-2">Ortam</th>
                      <th className="text-left px-3 py-2">Tetikleyici</th>
                      <th className="text-center px-3 py-2">{t('cm.pages_MevzuatRaporlari.durum')}</th>
                      <th className="text-right px-3 py-2">HTTP</th>
                      <th className="text-right px-3 py-2">{t('cm.pages_MevzuatRaporlari.toplam_oda_3026f')}</th>
                      <th className="text-right px-3 py-2">Net Gelir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tgaLog.map((it, i) => {
                const ok = it.status === "sent";
                const skip = it.status === "skipped";
                return <tr key={it.id || i} className="border-t">
                          <td className="px-3 py-1.5 font-mono">{(it.started_at || "").slice(0, 16).replace("T", " ")}</td>
                          <td className="px-3 py-1.5">son {it.days}g · {it.end_date}</td>
                          <td className="px-3 py-1.5">{it.environment === "live" ? "CANLI" : "TEST"}</td>
                          <td className="px-3 py-1.5">{it.triggered_by}</td>
                          <td className="px-3 py-1.5 text-center">
                            <StatusBadge intent={ok ? "success" : skip ? "neutral" : "danger"}>
                              {ok ? "Gönderildi" : skip ? "Atlandı" : "Hata"}
                            </StatusBadge>
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono">{it.http_status || "—"}</td>
                          <td className="px-3 py-1.5 text-right">{fmtNum(it.request_summary?.toplam_oda_sum)}</td>
                          <td className="px-3 py-1.5 text-right">{fmtNum(it.request_summary?.net_oda_geliri_sum)}</td>
                        </tr>;
              })}
                  </tbody>
                </table>
              </div>}
          </div>
        </div>}

      {tab === "inspection" && <div className="bg-white border rounded-lg p-4 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h3 className="font-semibold flex items-center gap-2">
              <ShieldCheck className="h-4 w-4" /> {t('cm.pages_MevzuatRaporlari.bakanlik_denetim_hazirlik')}
            </h3>
            <div className="flex gap-2">
              {readiness && <>
                  <Button variant="outline" size="sm" onClick={exportReadinessCSV}>
                    <Download className="h-4 w-4 mr-1.5" /> {t('cm.pages_MevzuatRaporlari.csv_indir_45c8e')}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => window.print()}>
                    <FileText className="h-4 w-4 mr-1.5" /> {t('cm.pages_MevzuatRaporlari.pdf_yazdir')}
                  </Button>
                </>}
              <RefreshButton onClick={() => loadReadiness(true)} loading={readinessLoading} />
            </div>
          </div>

          {!readiness ? <div className="text-slate-500 text-sm flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> {t('cm.pages_MevzuatRaporlari.yukleniyor_b597b')}
            </div> : <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KpiCard label={t('cm.pages_MevzuatRaporlari.hazirlik_skoru')} value={`%${readiness.readiness_score}`} intent={readiness.readiness_score >= 80 ? "success" : readiness.readiness_score >= 50 ? "warning" : "danger"} />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.toplam_oda_3026f')} value={fmtNum(readiness.rooms_total)} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.aktif_personel')} value={fmtNum(readiness.active_users)} intent="neutral" />
                <KpiCard label={t('cm.pages_MevzuatRaporlari.isletme_belgesi_gun')} value={readiness.license_days_left == null ? "—" : fmtNum(readiness.license_days_left)} intent={readiness.license_days_left == null ? "warning" : readiness.license_days_left < 30 ? "danger" : readiness.license_days_left < 90 ? "warning" : "success"} />
              </div>

              {readiness.tenant_missing_fields?.length > 0 && <div className="bg-amber-50 border border-amber-200 rounded p-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-600" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-amber-900">
                        {t('cm.pages_MevzuatRaporlari.tesis_kunyesinde')} {readiness.tenant_missing_fields.length} alan eksik
                      </div>
                      <div className="text-xs text-amber-800 mt-1">
                        {t('cm.pages_MevzuatRaporlari.bakanlik_denetiminde_sorulacak_temel_bil')}
                      </div>
                      <ul className="text-xs text-amber-900 mt-1.5 list-disc pl-4 space-y-0.5">
                        {readiness.tenant_missing_fields.map(f => <li key={f.field}><strong>{f.label}</strong> <span className="text-amber-700">({f.field})</span></li>)}
                      </ul>
                    </div>
                  </div>
                  <div>
                    <Button variant="outline" size="sm" onClick={goToTenantSettings}>
                      <Settings className="h-4 w-4 mr-1.5" />
                      {isSuperAdmin ? "Tesis ayarlarına git" : "Yöneticiye nasıl iletişim kuracağımı gör"}
                    </Button>
                  </div>
                </div>}

              {readiness.rooms_missing_bed_capacity > 0 && <div className="text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded p-2 flex items-start gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-500" />
                  <span>
                    <strong>{fmtNum(readiness.rooms_missing_bed_capacity)} / {fmtNum(readiness.rooms_total)}</strong>{" "}
                    odada yatak kapasitesi (<code>bed_capacity</code>{t('cm.pages_MevzuatRaporlari.tanimli_degil_tuik_yatak_toplami_bu_odal')}
                  </span>
                </div>}

              <div className="border rounded">
                <div className="bg-slate-50 px-3 py-2 font-semibold text-sm">{t('cm.pages_MevzuatRaporlari.kontrol_noktalari')}</div>
                <ul className="divide-y">
                  {readiness.checks.map(c => <li key={c.key} className="px-3 py-2 flex items-center gap-2 text-sm">
                      {c.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertTriangle className="h-4 w-4 text-amber-600" />}
                      <span className={c.ok ? "" : "text-amber-800 flex-1"}>{c.label}</span>
                      {!c.ok && c.fields?.length > 0 && <Button variant="outline" size="sm" onClick={goToTenantSettings}>
                          Doldurmaya git
                        </Button>}
                    </li>)}
                </ul>
              </div>

              <div className="border rounded">
                <div className="bg-slate-50 px-3 py-2 font-semibold text-sm">{t('cm.pages_MevzuatRaporlari.son_12_ay_rezervasyon_hacmi')}</div>
                <div className="overflow-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="text-left px-3 py-2">{t('cm.pages_MevzuatRaporlari.donem')}</th>
                        <th className="text-right px-3 py-2">{t('cm.pages_MevzuatRaporlari.aktif_rezervasyon')}</th>
                        <th className="text-right px-3 py-2">{t('cm.pages_MevzuatRaporlari.kapasite_oda_gece')}</th>
                        <th className="text-right px-3 py-2">Kaba Doluluk %</th>
                        <th className="text-left px-3 py-2 w-1/3">Trend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {readiness.booking_trend_12m.map(m => {
                  const pct = (m.occupancy_pct || 0) / trendMax * 100;
                  const barColor = m.occupancy_pct >= 70 ? "bg-emerald-500" : m.occupancy_pct >= 40 ? "bg-sky-500" : m.occupancy_pct > 0 ? "bg-amber-500" : "bg-slate-200";
                  return <tr key={m.period} className="border-t">
                            <td className="px-3 py-1 font-mono">{m.period}</td>
                            <td className="px-3 py-1 text-right">{fmtNum(m.booking_count)}</td>
                            <td className="px-3 py-1 text-right">{fmtNum(m.capacity_room_nights)}</td>
                            <td className="px-3 py-1 text-right">{m.occupancy_pct}%</td>
                            <td className="px-3 py-1">
                              <div className="w-full bg-slate-100 rounded h-2 overflow-hidden">
                                <div className={`h-full ${barColor}`} style={{
                          width: `${Math.max(2, pct)}%`
                        }} />
                              </div>
                            </td>
                          </tr>;
                })}
                    </tbody>
                  </table>
                </div>
              </div>
              <p className="text-xs text-slate-400">
                {t('cm.pages_MevzuatRaporlari.bu_rapor_bakanlik_denetim_ziyaretlerine_')}
              </p>
            </>}
        </div>}

      {tab === "stars" && <div className="bg-white border rounded-lg p-4 space-y-4">
          {!checklist ? <div className="text-slate-500 text-sm flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> {t('cm.pages_MevzuatRaporlari.yukleniyor_b597b')}
            </div> : <>
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="text-xs text-slate-600 block">{t('cm.pages_MevzuatRaporlari.hedef_yildiz')}</label>
                  <select className="border rounded px-3 py-2" value={checklist.target_star} onChange={e => setChecklist({
              ...checklist,
              target_star: Number(e.target.value)
            })}>
                    {[1, 2, 3, 4, 5].map(s => <option key={s} value={s}>{s} {t('cm.pages_MevzuatRaporlari.yildiz')}</option>)}
                  </select>
                </div>
                <div className="flex-1 min-w-[160px]">
                  <KpiCard label="Uyumluluk Skoru" value={`%${checklist.compliance_score}`} intent="info" />
                </div>
                <div>
                  <KpiCard label="Eksik Zorunlu Kriter" value={`${checklist.required_missing} / ${checklist.required_total}`} intent={checklist.required_missing > 0 ? "warning" : "success"} />
                </div>
                <Button onClick={saveChecklist} disabled={savingCl}>
                  {savingCl ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Save className="h-4 w-4 mr-1.5" />}
                  {t('cm.pages_MevzuatRaporlari.kaydet_hesapla')}
                </Button>
              </div>

              {Object.entries(checklist.items.reduce((acc, it) => {
          (acc[it.category] = acc[it.category] || []).push(it);
          return acc;
        }, {})).map(([cat, items]) => <div key={cat} className="border rounded">
                  <div className="bg-slate-50 px-3 py-2 font-semibold text-sm">{cat}</div>
                  <ul className="divide-y">
                    {items.map(it => <li key={it.key} className={`px-3 py-2 flex items-center gap-3 text-sm ${it.required && it.state !== "yes" ? "bg-amber-50" : ""}`}>
                        <div className="flex-1">
                          <span>{it.label}</span>
                          {it.required && <StatusBadge intent="danger" className="ml-2">
                              {checklist.target_star} {t('cm.pages_MevzuatRaporlari.icin_zorunlu')}
                            </StatusBadge>}
                        </div>
                        <select value={it.state} className="border rounded px-2 py-1 text-xs" onChange={e => {
                const items2 = checklist.items.map(x => x.key === it.key ? {
                  ...x,
                  state: e.target.value
                } : x);
                setChecklist({
                  ...checklist,
                  items: items2
                });
              }}>
                          <option value="yes">Var</option>
                          <option value="partial">{t('cm.pages_MevzuatRaporlari.kismen')}</option>
                          <option value="no">Yok</option>
                        </select>
                      </li>)}
                  </ul>
                </div>)}
              {checklist.saved_at && <p className="text-xs text-slate-400 flex items-center gap-1">
                  <ClipboardCheck className="h-3 w-3" />
                  {t('cm.pages_MevzuatRaporlari.son_kayit')} {checklist.saved_at.slice(0, 16).replace("T", " ")}
                </p>}
            </>}
        </div>}

      <Dialog open={missingOpen} onOpenChange={setMissingOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserX className="w-5 h-5 text-amber-600" />
              Eksik uyruklu rezervasyonlar
            </DialogTitle>
            <DialogDescription>
              {tuik?.missing_nationality?.booking_count > 0 ? `${fmtNum(tuik.missing_nationality.booking_count)} rezervasyonda misafir uyruğu girilmemiş. TÜİK formu yerli/yabancı ayrımı için uyruk zorunludur; kaydı açıp uyruğu girin.` : "Eksik uyruklu rezervasyon bulunmuyor."}
            </DialogDescription>
          </DialogHeader>

          {tuik?.missing_nationality?.samples?.length > 0 ? <div className="max-h-[60vh] overflow-y-auto -mx-1 px-1">
              <ul className="divide-y divide-slate-100">
                {tuik.missing_nationality.samples.map((s, i) => <li key={s.id || s.confirmation_number || i} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <div className="font-medium text-sm text-slate-800 truncate">
                        {s.guest_name || "—"}
                      </div>
                      <div className="text-xs text-slate-500 truncate">
                        {s.confirmation_number ? `#${s.confirmation_number}` : ""}
                        {s.check_in ? ` · ${s.check_in}` : ""}
                        {s.check_out ? ` → ${s.check_out}` : ""}
                      </div>
                    </div>
                    <Button variant="outline" size="sm" className="shrink-0" onClick={() => openBookingForFix(s.id)} disabled={!s.id}>
                      <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
                      Aç ve düzelt
                    </Button>
                  </li>)}
              </ul>
              {tuik.missing_nationality.booking_count > tuik.missing_nationality.samples.length && <p className="text-xs text-slate-400 pt-3">
                  İlk {tuik.missing_nationality.samples.length} kayıt gösteriliyor (toplam {fmtNum(tuik.missing_nationality.booking_count)}).
                </p>}
            </div> : <p className="text-sm text-slate-500 py-4">Gösterilecek kayıt yok.</p>}
        </DialogContent>
      </Dialog>
    </div>;
}