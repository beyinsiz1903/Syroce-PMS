import React, { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from 'react-i18next';
import axios from "axios";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import {
  Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle,
  RefreshCw, Calendar, FileText, ChevronDown, ChevronUp,
  DollarSign, Users, Building2, BarChart3, Eye, Loader2,
  Shield, Info, Timer, Settings2, Zap, RotateCcw,
  TrendingUp, CreditCard, ShieldCheck, Scale, Receipt,
  PieChart, ArrowUpDown, Banknote, AlertOctagon, Search
} from "lucide-react";
import { toast } from "sonner";
import { confirmDialog } from "@/lib/dialogs";
import { emitBusinessDateChanged } from "@/lib/businessDateEvents";
import {
  NIGHT_AUDIT_RUN_TIMEOUT_MS,
  confirmsNightAuditAdvance,
  isNightAuditTimeout,
} from "@/lib/nightAuditRunSafety";

import {
  StatusBadge, SeverityBadge, StatCard, IntegrityBadge,
  statusConfig, severityConfig, categoryLabels, paymentMethodLabels,
} from '@/components/night-audit/badges';
import OverviewTab from '@/components/night-audit/tabs/OverviewTab';
import PreparationTab from '@/components/night-audit/tabs/PreparationTab';
import FinancialTab from '@/components/night-audit/tabs/FinancialTab';
import ReconciliationTab from '@/components/night-audit/tabs/ReconciliationTab';
import IntegrityTab from '@/components/night-audit/tabs/IntegrityTab';
import ReportTab from '@/components/night-audit/tabs/ReportTab';
const NightAuditDashboard = ({ user, tenant, onLogout }) => {
  const { t, i18n } = useTranslation();
  const [businessDate, setBusinessDate] = useState(null);
  const [previousDate, setPreviousDate] = useState(null);
  const [businessDateMeta, setBusinessDateMeta] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [expandedRun, setExpandedRun] = useState(null);
  const [exceptions, setExceptions] = useState({});
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
  const [blockedRunDetail, setBlockedRunDetail] = useState(null);
  const [runActionId, setRunActionId] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [prepRefreshKey, setPrepRefreshKey] = useState(0);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("preparation");
  const [financialSummary, setFinancialSummary] = useState(null);
  const [reconciliation, setReconciliation] = useState(null);
  const [integrityCheck, setIntegrityCheck] = useState(null);
  const [financialReport, setFinancialReport] = useState(null);
  const [finLoading, setFinLoading] = useState(false);
  const [reportDates, setReportDates] = useState({ start: "", end: "" });
  const [schedule, setSchedule] = useState({
    enabled: false,
    scheduled_hour: 0,
    scheduled_minute: 0,
    timezone: "Europe/Istanbul",
    skip_validations: false,
    auto_retry: true,
    max_retries: 2,
    notify_on_complete: true,
    notify_on_failure: true,
  });
  const [scheduleStatus, setScheduleStatus] = useState(null);
  const [runOptions, setRunOptions] = useState({
    force_rerun: false,
    skip_validations: false,
    dry_run: false,
    reason: "",
  });

  const fetchBusinessDate = useCallback(async () => {
    try {
      const res = await axios.get("/night-audit/business-date");
      const nextBusinessDate = res.data.business_date;
      setBusinessDate(nextBusinessDate);
      setPreviousDate(res.data.previous_business_date);
      setBusinessDateMeta(res.data);
      emitBusinessDateChanged(nextBusinessDate, res.data);
      return nextBusinessDate;
    } catch (err) {
      console.error("Business date fetch failed:", err);
      return null;
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await axios.get("/night-audit/history", { params: { limit: 20, skip: 0 } });
      const normalizedRuns = (res.data.runs || []).map((run) => ({
        ...run,
        audit_id: run.audit_id || run.id,
        is_dry_run: Boolean(run.is_dry_run ?? run.dry_run),
        rooms_processed: run.rooms_processed ?? run.processed_count ?? 0,
        charges_posted: run.charges_posted ?? run.processed_count ?? 0,
        total_room_revenue: Number(run.total_room_revenue ?? run.total_amount ?? 0),
        total_tax_amount: Number(run.total_tax_amount ?? run.total_tax ?? 0),
        exceptions_count: run.exceptions_count ?? run.errors?.length ?? 0,
        no_shows_processed: run.no_shows_processed ?? 0,
        folios_balanced: run.folios_balanced ?? 0,
        folios_unbalanced: run.folios_unbalanced ?? 0,
      }));
      setHistory(normalizedRuns);
      setHistoryTotal(res.data.total || 0);
    } catch (err) {
      console.error("History fetch failed:", err);
    }
  }, []);

  const fetchExceptions = useCallback(async (auditId) => {
    if (exceptions[auditId]) return;
    try {
      const res = await axios.get(`/night-audit/exceptions/${auditId}`);
      setExceptions((prev) => ({ ...prev, [auditId]: res.data.exceptions || [] }));
    } catch (err) {
      console.error("Exceptions fetch failed:", err);
    }
  }, [exceptions]);

  const fetchSchedule = useCallback(async () => {
    try {
      const res = await axios.get("/night-audit/schedule");
      setSchedule(res.data);
    } catch (err) {
      console.error("Schedule fetch failed:", err);
    }
  }, []);

  const fetchScheduleStatus = useCallback(async () => {
    try {
      const res = await axios.get("/night-audit/schedule/status");
      setScheduleStatus(res.data);
    } catch (err) {
      console.error("Schedule status fetch failed:", err);
    }
  }, []);

  const fetchFinancialSummary = useCallback(async (date) => {
    try {
      const params = date ? { date } : {};
      const res = await axios.get("/night-audit/financial-summary", { params });
      setFinancialSummary(res.data);
    } catch (err) {
      console.error("Financial summary fetch failed:", err);
    }
  }, []);

  const fetchReconciliation = useCallback(async (date) => {
    try {
      const params = date ? { date } : {};
      const res = await axios.get("/night-audit/payment-reconciliation", { params });
      setReconciliation(res.data);
    } catch (err) {
      console.error("Reconciliation fetch failed:", err);
    }
  }, []);

  const fetchIntegrityCheck = useCallback(async (date) => {
    try {
      const params = date ? { date } : {};
      const res = await axios.get("/night-audit/integrity-check", { params });
      setIntegrityCheck(res.data);
    } catch (err) {
      console.error("Integrity check fetch failed:", err);
    }
  }, []);

  const fetchFinancialReport = useCallback(async (start, end) => {
    if (!start || !end) return;
    setFinLoading(true);
    try {
      const res = await axios.get("/night-audit/financial-report", {
        params: { start_date: start, end_date: end },
      });
      setFinancialReport(res.data);
    } catch (err) {
      toast.error("Finansal rapor yüklenemedi");
    } finally {
      setFinLoading(false);
    }
  }, []);

  // Mount waterfall fix: 4+3 sıralı round-trip → 7 paralel.
  // financial-summary/payment-reconciliation/integrity-check `date=null`
  // gönderildiğinde backend bugün'e default eder; businessDate gelmesini
  // beklemeye gerek yok. Sonraki businessDate değişimleri için
  // initialLoadRef ile ilk render'ı atlayıp re-fetch sadece manuel
  // değişimde tetiklenir.
  const initialLoadRef = useRef(true);
  const loadAll = useCallback(async () => {
    setLoading(true);
    initialLoadRef.current = true; // skip the businessDate effect after this
    await Promise.all([
      fetchBusinessDate(),
      fetchHistory(),
      fetchSchedule(),
      fetchScheduleStatus(),
      fetchFinancialSummary(),
      fetchReconciliation(),
      fetchIntegrityCheck(),
    ]);
    setLoading(false);
  }, [fetchBusinessDate, fetchHistory, fetchSchedule, fetchScheduleStatus, fetchFinancialSummary, fetchReconciliation, fetchIntegrityCheck]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (initialLoadRef.current) {
      // İlk yüklemede (veya loadAll sonrası) finansal endpoint'ler zaten çekildi
      initialLoadRef.current = false;
      return;
    }
    if (businessDate) {
      fetchFinancialSummary(businessDate);
      fetchReconciliation(businessDate);
      fetchIntegrityCheck(businessDate);
    }
  }, [businessDate, fetchFinancialSummary, fetchReconciliation, fetchIntegrityCheck]);

  const handleRunAudit = async () => {
    setRunning(true);
    const requestedBusinessDate = businessDate;
    try {
      const payload = {
        business_date: businessDate,
        force_rerun: runOptions.force_rerun,
        skip_validations: runOptions.skip_validations,
        dry_run: runOptions.dry_run,
        reason: runOptions.reason || null,
      };
      const res = await axios.post("/night-audit/run", payload, {
        timeout: NIGHT_AUDIT_RUN_TIMEOUT_MS,
      });
      const result = res.data;
      const postedChargeCount = result.charges_posted ?? result.run?.processed_count ?? 0;
      toast.success(
        runOptions.dry_run
          ? `Simülasyon tamamlandı: ${result.rooms_processed} oda işlendi`
          : `Gece denetimi tamamlandı: ${postedChargeCount} masraf kaydedildi`
      );
      setShowRunDialog(false);
      setRunOptions({ force_rerun: false, skip_validations: false, dry_run: false, reason: "" });
      await loadAll();
      setPrepRefreshKey((k) => k + 1);
    } catch (err) {
      if (isNightAuditTimeout(err)) {
        try {
          const verification = await axios.get("/night-audit/business-date", {
            _noCache: true,
            timeout: 30_000,
          });
          const verifiedDate = verification.data?.business_date;
          if (confirmsNightAuditAdvance(requestedBusinessDate, verifiedDate)) {
            emitBusinessDateChanged(verifiedDate, verification.data);
            toast.success("Gece denetiminin sunucuda tamamlandığı doğrulandı");
            setShowRunDialog(false);
            setRunOptions({ force_rerun: false, skip_validations: false, dry_run: false, reason: "" });
            await loadAll();
            setPrepRefreshKey((k) => k + 1);
            return;
          }
        } catch {
          // The mutation outcome remains ambiguous; do not retry it here.
        }
        setShowRunDialog(false);
        toast.error(
          "Gece denetimi sonucu henüz doğrulanamadı. Yeniden başlatmayın; durumu Yenile ile kontrol edin.",
          { duration: 8000 },
        );
        return;
      }
      const detail = err.response?.data?.detail;
      // BLOCKED: backend yapılandırılmış nesne döner ({success:false, code:"BLOCKED", error, run:{errors,warnings}})
      if (typeof detail === "object" && detail) {
        if (["BLOCKED", "VALIDATION_BLOCKED", "NEEDS_RESUME"].includes(detail.code)) {
          const errs = detail.run?.errors || detail.blockers || [detail.error].filter(Boolean);
          const warns = detail.run?.warnings || [];
          setBlockedRunDetail({
            runId: detail.run?.id || detail.run_id || detail.existing_run_id || null,
            businessDate: detail.run?.business_date || businessDate,
            errors: errs,
            warnings: warns,
            isDryRun: runOptions.dry_run || Boolean(detail.run?.dry_run),
          });
          toast.error(
            `Gece denetimi engellendi (${errs.length} hata${warns.length ? `, ${warns.length} uyarı` : ""}). Hazırlık sekmesinden detayları görüp çözebilirsiniz.`,
            { duration: 6000 }
          );
          setActiveTab("preparation");
          setPrepRefreshKey((k) => k + 1);
        } else if (detail.message) {
          toast.error(detail.message);
        } else if (detail.error) {
          toast.error(detail.error);
        } else {
          toast.error("Gece denetimi başarısız oldu");
        }
      } else if (typeof detail === "string") {
        toast.error(detail);
      } else {
        toast.error("Gece denetimi başarısız oldu");
      }
    } finally {
      setRunning(false);
    }
  };

  const handleResumeRun = async (runId) => {
    if (!runId) return;
    setRunActionId(runId);
    try {
      await axios.post(`/night-audit/runs/${runId}/resume`);
      toast.success("Bloklanan gece denetimi tamamlandı");
      setBlockedRunDetail(null);
      await loadAll();
      setPrepRefreshKey((key) => key + 1);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.code === "STILL_BLOCKED") {
        setBlockedRunDetail((prev) => ({
          runId,
          businessDate: prev?.businessDate || businessDate,
          errors: detail.blockers || [],
          warnings: prev?.warnings || [],
          isDryRun: prev?.isDryRun || false,
        }));
        toast.error("Denetim hâlâ engelli; aşağıdaki maddeleri çözün");
      } else {
        toast.error(detail?.error || detail || "Denetim devam ettirilemedi");
      }
    } finally {
      setRunActionId(null);
    }
  };

  const handleAbortRun = async (runId) => {
    if (!runId) return;
    if (!await confirmDialog({
      message: "Bu açık gece denetimi iptal edilsin mi? Kaydedilmiş masraflar geri alınmaz.",
      variant: "danger",
    })) return;
    setRunActionId(runId);
    try {
      await axios.post(`/night-audit/runs/${runId}/abort`);
      toast.success("Açık gece denetimi iptal edildi");
      setBlockedRunDetail(null);
      await loadAll();
      setPrepRefreshKey((key) => key + 1);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(detail?.error || detail || "Denetim iptal edilemedi");
    } finally {
      setRunActionId(null);
    }
  };

  const handleSaveSchedule = async () => {
    setScheduleLoading(true);
    try {
      await axios.put("/night-audit/schedule", schedule);
      toast.success(schedule.enabled ? "Otomatik zamanlama aktif edildi" : "Otomatik zamanlama devre dışı bırakıldı");
      setShowScheduleDialog(false);
      await fetchScheduleStatus();
      setPrepRefreshKey((k) => k + 1);
    } catch (err) {
      toast.error("Zamanlama kaydedilemedi");
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleQuickToggleSchedule = async () => {
    const newEnabled = !schedule.enabled;
    try {
      await axios.put("/night-audit/schedule", { ...schedule, enabled: newEnabled });
      setSchedule((prev) => ({ ...prev, enabled: newEnabled }));
      toast.success(newEnabled ? "Otomatik zamanlama aktif" : "Otomatik zamanlama devre dışı");
      await fetchScheduleStatus();
      setPrepRefreshKey((k) => k + 1);
    } catch (err) {
      toast.error("Durum değiştirilemedi");
    }
  };

  // Use functional updater + ref-free comparison so the callback identity is
  // stable across renders and does not retrigger child effects (preview loop fix).
  const handlePreviewLoaded = useCallback((data) => {
    setPreviewData(data);
    const next = data?.business_date;
    if (next) {
      setBusinessDate((prev) => (prev === next ? prev : next));
    }
  }, []);

  const toggleExpand = async (auditId) => {
    if (expandedRun === auditId) {
      setExpandedRun(null);
    } else {
      setExpandedRun(auditId);
      await fetchExceptions(auditId);
    }
  };

  const lastRun = history.length > 0 ? history[0] : null;
  const todayCompleted = lastRun?.business_date === businessDate && lastRun?.status?.startsWith("completed");

  // Engelleyici sorun varken ve "Doğrulamaları Atla" seçili değilken
  // backend hem gerçek çalıştırmayı hem de simülasyonu (doğrulama kapısı
  // simülasyondan önce çalışır) BLOCKED ile reddeder. Buton bu durumda
  // görsel olarak da kilitli olmalı.
  const runBlocked = (previewData?.blockers?.length > 0) && !runOptions.skip_validations;

  const ctx = {
    t,
    StatusBadge, SeverityBadge, StatCard, IntegrityBadge,
    statusConfig, severityConfig, categoryLabels, paymentMethodLabels,
    businessDate, previousDate, businessDateMeta, history, historyTotal, loading, running,
    expandedRun, exceptions, schedule, scheduleStatus, scheduleLoading,
    showRunDialog, setShowRunDialog, showScheduleDialog, setShowScheduleDialog,
    activeTab, setActiveTab, runOptions, setRunOptions,
    financialSummary, reconciliation, integrityCheck, financialReport, finLoading,
    reportDates, setReportDates,
    fetchBusinessDate, fetchHistory, fetchExceptions, fetchSchedule, fetchScheduleStatus,
    fetchFinancialSummary, fetchReconciliation, fetchIntegrityCheck, fetchFinancialReport,
    handleRunAudit, handleSaveSchedule, handleQuickToggleSchedule,
    handleResumeRun, handleAbortRun, runActionId,
    onOpenRun: async (runId) => {
      setActiveTab("overview");
      setExpandedRun(runId);
      await fetchExceptions(runId);
    },
    toggleExpand,
    user, tenant, onLogout,
    lastRun,
    detail: null,
  };

  return (
    <>
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
        {/* Header */}
        <PageHeader
          icon={Moon}
          title="Gece Denetimi"
          subtitle="Gün sonu işlemleri: oda masrafı kaydı, no-show işleme, folio bakiye kontrolü, finansal raporlama"
          actions={
            <>
              <Button
                data-testid="refresh-btn"
                variant="outline"
                size="sm"
                onClick={loadAll}
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
                Yenile
              </Button>
              <Button
                data-testid="run-audit-btn"
                size="sm"
                onClick={() => setShowRunDialog(true)}
                disabled={running}
              >
                <Play className="w-4 h-4 mr-1.5" />
                Denetim Başlat
              </Button>
            </>
          }
        />
        <h1 data-testid="night-audit-title" className="sr-only">Gece Denetimi</h1>

        {blockedRunDetail && (
          <Card className="border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-950" data-testid="blocked-run-details">
            <CardContent className="py-4 space-y-3">
              <div className="flex items-start gap-3">
                <AlertOctagon className="w-5 h-5 text-rose-600 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-rose-900">
                    {blockedRunDetail.businessDate} iş günü denetimi engellendi
                  </p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-xs text-rose-800">
                    {blockedRunDetail.errors.map((error, index) => <li key={`${index}-${error}`}>{error}</li>)}
                  </ul>
                  {blockedRunDetail.warnings.length > 0 && (
                    <p className="mt-2 text-xs text-amber-800">
                      Uyarılar: {blockedRunDetail.warnings.join(" · ")}
                    </p>
                  )}
                </div>
                {blockedRunDetail.runId && (
                  <div className="flex gap-2 shrink-0">
                    {!blockedRunDetail.isDryRun && (
                      <Button
                        size="sm"
                        onClick={() => handleResumeRun(blockedRunDetail.runId)}
                        disabled={runActionId === blockedRunDetail.runId}
                      >
                        <Play className="w-4 h-4 mr-1" /> Devam Ettir
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleAbortRun(blockedRunDetail.runId)}
                      disabled={runActionId === blockedRunDetail.runId}
                    >
                      <XCircle className="w-4 h-4 mr-1" /> İptal Et
                    </Button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Business Date & Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard
            icon={Calendar}
            intent="info"
            label="İş Günü"
            value={businessDate || "-"}
            sub={previousDate ? `Önceki: ${previousDate}` : undefined}
          />
          <KpiCard
            icon={BarChart3}
            intent="success"
            label="Toplam Denetim"
            value={historyTotal}
            sub={todayCompleted ? "Bugün tamamlandı" : "Bugün bekliyor"}
          />
          <KpiCard
            icon={DollarSign}
            intent="info"
            label="Son Oda Geliri"
            value={lastRun ? `${lastRun.total_room_revenue?.toFixed(2) || "0.00"} TL` : "-"}
            sub={lastRun ? `Vergi: ${lastRun.total_tax_amount?.toFixed(2) || "0.00"} TL` : undefined}
          />
          <KpiCard
            icon={Users}
            intent="warning"
            label="Son No-Show"
            value={lastRun?.no_shows_processed ?? "-"}
            sub={lastRun ? `${lastRun.rooms_processed || 0} oda işlendi` : undefined}
          />
        </div>

        {businessDateMeta?.is_initialized && (
          <Card
            className={businessDateMeta.update_source === "night_audit"
              ? "border-emerald-200 bg-emerald-50/60"
              : "border-amber-300 bg-amber-50/70"}
            data-testid="business-date-origin"
          >
            <CardContent className="py-3 flex items-start gap-3">
              {businessDateMeta.update_source === "night_audit" ? (
                <CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-700 shrink-0" />
              ) : (
                <AlertTriangle className="w-4 h-4 mt-0.5 text-amber-700 shrink-0" />
              )}
              <div className="min-w-0 text-xs text-slate-700">
                <p className="font-semibold text-slate-900">
                  {businessDateMeta.update_source === "night_audit"
                    ? "PMS iş günü tamamlanan Night Audit ile ilerletildi"
                    : businessDateMeta.update_source === "legacy_record"
                      ? "PMS iş günü eski sistem kaydından geliyor"
                      : "PMS iş günü güvenli başlangıç kaydından oluşturuldu"}
                </p>
                <p className="mt-0.5">
                  {businessDateMeta.initialization_reason === "earliest_unresolved_arrival" && "Başlangıç noktası: çözülmemiş en eski aktif rezervasyon. "}
                  {businessDateMeta.initialization_reason === "night_audit_history" && "Başlangıç noktası: son başarılı Night Audit’in ertesi günü. "}
                  {businessDateMeta.initialization_reason === "first_operational_use" && "Başlangıç noktası: ilk operasyonel kullanım günü. "}
                  {businessDateMeta.initialization_reason === "tenant_provisioning" && "Başlangıç noktası: tesis kurulum günü. "}
                  {businessDateMeta.update_source === "legacy_record" && "Eski kayıtta işlemi yapan kullanıcı veya Night Audit kimliği bulunmuyor. "}
                  {businessDateMeta.updated_at && `Son kayıt: ${new Date(businessDateMeta.updated_at).toLocaleString("tr-TR")}. `}
                  {businessDateMeta.trigger_source === "scheduler" && "Kaynak: otomatik zamanlama. "}
                  {businessDateMeta.trigger_source === "manual" && "Kaynak: manuel Night Audit. "}
                  {businessDateMeta.updated_by && `İşlemi yapan: ${businessDateMeta.updated_by}. `}
                  {businessDateMeta.audit_run_id && `Denetim: ${businessDateMeta.audit_run_id}.`}
                </p>
                {businessDateMeta.update_source !== "night_audit" && (
                  <p className="mt-1 font-medium text-amber-800">
                    Bu kayıt tek başına Night Audit yapılmış olduğu anlamına gelmez; açık iş günü bundan sonra yalnızca başarılı denetimle ilerler.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-gray-100/80 p-1">
            <TabsTrigger data-testid="tab-preparation" value="preparation" className="text-xs gap-1.5">
              <Shield className="w-3.5 h-3.5" /> Hazırlık
            </TabsTrigger>
            <TabsTrigger data-testid="tab-overview" value="overview" className="text-xs gap-1.5">
              <Moon className="w-3.5 h-3.5" /> Genel Bakış
            </TabsTrigger>
            <TabsTrigger data-testid="tab-financial" value="financial" className="text-xs gap-1.5">
              <TrendingUp className="w-3.5 h-3.5" /> Finansal Özet
            </TabsTrigger>
            <TabsTrigger data-testid="tab-reconciliation" value="reconciliation" className="text-xs gap-1.5">
              <Scale className="w-3.5 h-3.5" /> Mutabakat
            </TabsTrigger>
            <TabsTrigger data-testid="tab-integrity" value="integrity" className="text-xs gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5" /> Bütünlük
            </TabsTrigger>
            <TabsTrigger data-testid="tab-report" value="report" className="text-xs gap-1.5">
              <FileText className="w-3.5 h-3.5" /> Rapor
            </TabsTrigger>
          </TabsList>

          {/* ═══ Preparation Tab ═══ */}
          <TabsContent value="preparation" className="space-y-4 mt-4">
            <PreparationTab
              onStartRun={() => setShowRunDialog(true)}
              onPreviewLoaded={handlePreviewLoaded}
              onOpenRun={ctx.onOpenRun}
              refreshKey={prepRefreshKey}
            />
          </TabsContent>

          {/* ═══ Overview Tab ═══ */}
          <TabsContent value="overview" className="space-y-4 mt-4">
            <OverviewTab {...ctx} />
          </TabsContent>

          {/* ═══ Financial Summary Tab ═══ */}
          <TabsContent value="financial" className="space-y-4 mt-4">
            <FinancialTab {...ctx} />
          </TabsContent>

          {/* ═══ Reconciliation Tab ═══ */}
          <TabsContent value="reconciliation" className="space-y-4 mt-4">
            <ReconciliationTab {...ctx} />
          </TabsContent>

          {/* ═══ Integrity Check Tab ═══ */}
          <TabsContent value="integrity" className="space-y-4 mt-4">
            <IntegrityTab {...ctx} />
          </TabsContent>

          {/* ═══ Financial Report Tab ═══ */}
          <TabsContent value="report" className="space-y-4 mt-4">
            <ReportTab {...ctx} />
          </TabsContent>
        </Tabs>

        {/* Schedule Settings Dialog */}
        <Dialog open={showScheduleDialog} onOpenChange={setShowScheduleDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Timer className="w-5 h-5 text-indigo-600" />
                Otomatik Zamanlama Ayarları
              </DialogTitle>
              <DialogDescription>
                Gece denetiminin otomatik olarak çalıştırılacağı saat ve seçenekleri yapılandır.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              {/* Enable/Disable */}
              <div className="flex items-center justify-between p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
                <div>
                  <p className="text-sm font-medium text-indigo-800">Otomatik Çalıştırma</p>
                  <p className="text-xs text-indigo-600">Belirlenen saatte otomatik olarak çalıştırılır</p>
                </div>
                <Switch
                  data-testid="schedule-enable-switch"
                  checked={schedule.enabled}
                  onCheckedChange={(checked) => setSchedule({ ...schedule, enabled: checked })}
                />
              </div>

              {/* Time Selection */}
              <div>
                <label className="text-xs text-gray-600 mb-1.5 block font-medium">Zamanlama Saati</label>
                <div className="flex gap-2 items-center">
                  <select
                    data-testid="schedule-hour-select"
                    value={schedule.scheduled_hour}
                    onChange={(e) => setSchedule({ ...schedule, scheduled_hour: parseInt(e.target.value) })}
                    className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")}</option>
                    ))}
                  </select>
                  <span className="text-lg font-bold text-gray-400">:</span>
                  <select
                    data-testid="schedule-minute-select"
                    value={schedule.scheduled_minute}
                    onChange={(e) => setSchedule({ ...schedule, scheduled_minute: parseInt(e.target.value) })}
                    className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                  >
                    {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
                      <option key={m} value={m}>{String(m).padStart(2, "0")}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Timezone */}
              <div>
                <label className="text-xs text-gray-600 mb-1.5 block font-medium">Saat Dilimi</label>
                <select
                  data-testid="schedule-timezone-select"
                  value={schedule.timezone}
                  onChange={(e) => setSchedule({ ...schedule, timezone: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                >
                  <option value="Europe/Istanbul">Europe/Istanbul (UTC+3)</option>
                  <option value="Europe/Berlin">Europe/Berlin (UTC+1)</option>
                  <option value="Europe/London">Europe/London (UTC+0)</option>
                  <option value="Europe/Moscow">Europe/Moscow (UTC+3)</option>
                  <option value="Asia/Dubai">Asia/Dubai (UTC+4)</option>
                  <option value="UTC">UTC</option>
                </select>
              </div>

              {/* Options */}
              <div className="space-y-2">
                <label className="flex items-center justify-between p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <div className="flex items-center gap-2">
                    <RotateCcw className="w-4 h-4 text-blue-500" />
                    <div>
                      <p className="text-sm font-medium text-gray-800">Otomatik Yeniden Deneme</p>
                      <p className="text-xs text-gray-500">Başarısız olursa tekrar dener</p>
                    </div>
                  </div>
                  <Switch
                    data-testid="schedule-auto-retry-switch"
                    checked={schedule.auto_retry}
                    onCheckedChange={(checked) => setSchedule({ ...schedule, auto_retry: checked })}
                  />
                </label>

                {schedule.auto_retry && (
                  <div className="ml-8">
                    <label className="text-xs text-gray-600 mb-1 block">Maks. Deneme Sayısı</label>
                    <select
                      data-testid="schedule-max-retries-select"
                      value={schedule.max_retries}
                      onChange={(e) => setSchedule({ ...schedule, max_retries: parseInt(e.target.value) })}
                      className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                    >
                      {[1, 2, 3, 5].map((n) => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                  </div>
                )}

                <label className="flex items-center justify-between p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    <div>
                      <p className="text-sm font-medium text-gray-800">Doğrulamaları Atla</p>
                      <p className="text-xs text-gray-500">Ön kontrolleri atlayarak çalıştır</p>
                    </div>
                  </div>
                  <Switch
                    data-testid="schedule-skip-validations-switch"
                    checked={schedule.skip_validations}
                    onCheckedChange={(checked) => setSchedule({ ...schedule, skip_validations: checked })}
                  />
                </label>
              </div>

              {schedule.skip_validations && (
                <div className="p-2 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-red-700">
                    Otomatik çalıştırmada doğrulama atlama veri tutarsızlıklarına yol açabilir.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowScheduleDialog(false)} disabled={scheduleLoading}>
                  İptal
                </Button>
                <Button
                  data-testid="schedule-save-btn"
                  onClick={handleSaveSchedule}
                  disabled={scheduleLoading}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {scheduleLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                      Kaydediliyor...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4 mr-1" />
                      Kaydet
                    </>
                  )}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Run Audit Dialog */}
        <Dialog open={showRunDialog} onOpenChange={setShowRunDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Moon className="w-5 h-5 text-indigo-600" />
                Gece Denetimi Başlat
              </DialogTitle>
              <DialogDescription>
                Seçili iş günü için gece denetimi işlemini başlatır.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
                <p className="text-sm text-indigo-800">
                  <strong>İş Günü:</strong> {businessDate || "-"}
                </p>
                <p className="text-xs text-indigo-600 mt-1">
                  Bu tarih için gece denetimi çalıştırılacak
                  {previewData?.calendar_date && previewData?.business_date && (
                    previewData.calendar_date === previewData.business_date
                      ? " · Takvim ile aynı"
                      : ` · Takvim: ${previewData.calendar_date} (${previewData.date_drift_days > 0 ? `${previewData.date_drift_days} gün geride` : `${-previewData.date_drift_days} gün ileride`})`
                  )}
                </p>
              </div>

              {/* Engelleyici uyarısı */}
              {previewData && (previewData.blockers?.length > 0) && !runOptions.skip_validations && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-2" data-testid="modal-blockers-warn">
                  <AlertOctagon className="w-4 h-4 text-rose-600 mt-0.5 flex-shrink-0" />
                  <div className="text-xs text-rose-800">
                    <p className="font-medium">{previewData.blockers.length} engelleyici sorun var</p>
                    <p className="mt-0.5">
                      Hazırlık sekmesinden çözmeden başlatma engellenecek. Acil durumda &quot;Doğrulamaları Atla&quot; seçeneğini kullanabilirsiniz.
                    </p>
                    <button
                      type="button"
                      className="mt-1 text-rose-700 underline hover:text-rose-900"
                      onClick={() => { setShowRunDialog(false); setActiveTab("preparation"); }}
                    >
                      Hazırlık sekmesine git
                    </button>
                  </div>
                </div>
              )}

              {/* Options */}
              <div className="space-y-3">
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    data-testid="dry-run-checkbox"
                    type="checkbox"
                    checked={runOptions.dry_run}
                    onChange={(e) => setRunOptions({ ...runOptions, dry_run: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-indigo-600"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Simülasyon (Dry Run)</p>
                    <p className="text-xs text-gray-500">Değişiklik yapmadan test et</p>
                  </div>
                </label>

                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    data-testid="force-rerun-checkbox"
                    type="checkbox"
                    checked={runOptions.force_rerun}
                    onChange={(e) => setRunOptions({ ...runOptions, force_rerun: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-amber-600"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Tekrar Çalıştır</p>
                    <p className="text-xs text-gray-500">Daha önce tamamlanmış olsa bile tekrar çalıştır</p>
                  </div>
                </label>

                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    data-testid="skip-validations-checkbox"
                    type="checkbox"
                    checked={runOptions.skip_validations}
                    onChange={(e) => setRunOptions({ ...runOptions, skip_validations: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-red-600"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Doğrulamaları Atla</p>
                    <p className="text-xs text-gray-500">Ön kontrolleri atlayarak çalıştır (dikkatli kullanın)</p>
                  </div>
                </label>

                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Açıklama (opsiyonel)</label>
                  <input
                    data-testid="reason-input"
                    type="text"
                    placeholder="Denetim aciklamasi..."
                    value={runOptions.reason}
                    onChange={(e) => setRunOptions({ ...runOptions, reason: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
              </div>

              {runOptions.skip_validations && (
                <div className="p-2 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-red-700">
                    Doğrulama atlama sadece acil durumlarda kullanılmalıdır. Ön kontrolsüz denetim veri tutarsızlıklarına neden olabilir.
                  </p>
                </div>
              )}

              {runBlocked && (
                <p className="text-xs text-rose-700 pt-1" data-testid="run-blocked-hint">
                  Engelleyici sorunlar çözülmeden denetim başlatılamaz. Hazırlık sekmesinden çözün veya &quot;Doğrulamaları Atla&quot; seçeneğini işaretleyin.
                </p>
              )}

              <div className="flex items-center justify-between gap-3 pt-2 border-t mt-1">
                <Button variant="ghost" onClick={() => setShowRunDialog(false)} disabled={running}>
                  İptal
                </Button>
                <Button
                  data-testid="confirm-run-btn"
                  onClick={handleRunAudit}
                  disabled={running || runBlocked}
                  title={runBlocked ? 'Engelleyici sorunlar var. Önce Hazırlık sekmesinden çözün ya da "Doğrulamaları Atla" seçeneğini işaretleyin.' : undefined}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {running ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                      Calisiyor...
                    </>
                  ) : runOptions.dry_run ? (
                    <>
                      <Eye className="w-4 h-4 mr-1" />
                      Simülasyon Baslat
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 mr-1" />
                      Denetimi Başlat
                    </>
                  )}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default NightAuditDashboard;
