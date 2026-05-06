import React, { useState, useEffect, useCallback } from "react";
import { useTranslation } from 'react-i18next';
import axios from "axios";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle,
  RefreshCw, Calendar, FileText, ChevronDown, ChevronUp,
  DollarSign, Users, Building2, BarChart3, Eye, Loader2,
  Shield, Info, Timer, Settings2, Zap, RotateCcw,
  TrendingUp, CreditCard, ShieldCheck, Scale, Receipt,
  PieChart, ArrowUpDown, Banknote, AlertOctagon, Search
} from "lucide-react";
import { toast } from "sonner";

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
  const { t } = useTranslation();
  const [businessDate, setBusinessDate] = useState(null);
  const [previousDate, setPreviousDate] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [expandedRun, setExpandedRun] = useState(null);
  const [exceptions, setExceptions] = useState({});
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
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
      setBusinessDate(res.data.business_date);
      setPreviousDate(res.data.previous_business_date);
    } catch (err) {
      console.error("Business date fetch failed:", err);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await axios.get("/night-audit/history", { params: { limit: 20, skip: 0 } });
      setHistory(res.data.runs || []);
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

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchBusinessDate(), fetchHistory(), fetchSchedule(), fetchScheduleStatus()]);
    setLoading(false);
  }, [fetchBusinessDate, fetchHistory, fetchSchedule, fetchScheduleStatus]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (businessDate) {
      fetchFinancialSummary(businessDate);
      fetchReconciliation(businessDate);
      fetchIntegrityCheck(businessDate);
    }
  }, [businessDate, fetchFinancialSummary, fetchReconciliation, fetchIntegrityCheck]);

  const handleRunAudit = async () => {
    setRunning(true);
    try {
      const payload = {
        business_date: businessDate,
        force_rerun: runOptions.force_rerun,
        skip_validations: runOptions.skip_validations,
        dry_run: runOptions.dry_run,
        reason: runOptions.reason || null,
      };
      const res = await axios.post("/night-audit/run", payload);
      const result = res.data;
      toast.success(
        runOptions.dry_run
          ? `Simülasyon tamamlandı: ${result.rooms_processed} oda işlendi`
          : `Gece denetimi tamamlandı: ${result.charges_posted} masraf kaydedildi`
      );
      setShowRunDialog(false);
      setRunOptions({ force_rerun: false, skip_validations: false, dry_run: false, reason: "" });
      await loadAll();
      setPrepRefreshKey((k) => k + 1);
    } catch (err) {
      const detail = err.response?.data?.detail;
      // BLOCKED: backend yapılandırılmış nesne döner ({success:false, code:"BLOCKED", error, run:{errors,warnings}})
      if (typeof detail === "object" && detail) {
        if (detail.code === "BLOCKED") {
          const errs = detail.run?.errors || [];
          const warns = detail.run?.warnings || [];
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

  const handlePreviewLoaded = useCallback((data) => {
    setPreviewData(data);
    if (data?.business_date && data.business_date !== businessDate) {
      setBusinessDate(data.business_date);
    }
  }, [businessDate]);

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

  const ctx = {
    t,
    StatusBadge, SeverityBadge, StatCard, IntegrityBadge,
    statusConfig, severityConfig, categoryLabels, paymentMethodLabels,
    businessDate, previousDate, history, historyTotal, loading, running,
    expandedRun, exceptions, schedule, scheduleStatus, scheduleLoading,
    showRunDialog, setShowRunDialog, showScheduleDialog, setShowScheduleDialog,
    activeTab, setActiveTab, runOptions, setRunOptions,
    financialSummary, reconciliation, integrityCheck, financialReport, finLoading,
    reportDates, setReportDates,
    fetchBusinessDate, fetchHistory, fetchExceptions, fetchSchedule, fetchScheduleStatus,
    fetchFinancialSummary, fetchReconciliation, fetchIntegrityCheck, fetchFinancialReport,
    handleRunAudit, handleSaveSchedule, handleQuickToggleSchedule,
    toggleExpand: () => {},
    user, tenant, onLogout,
    lastRun,
    detail: null,
  };

  return (
    <>
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h1 data-testid="night-audit-title" className="text-xl md:text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Moon className="w-6 h-6 text-indigo-600" />
              Gece Denetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Gün sonu işlemleri: oda masrafı kaydı, no-show işleme, folio bakiye kontrolü, finansal raporlama
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              data-testid="refresh-btn"
              variant="outline"
              size="sm"
              onClick={loadAll}
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
              Yenile
            </Button>
            <Button
              data-testid="run-audit-btn"
              size="sm"
              onClick={() => setShowRunDialog(true)}
              disabled={running}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              <Play className="w-4 h-4 mr-1" />
              Denetim Başlat
            </Button>
          </div>
        </div>

        {/* Business Date & Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            icon={Calendar}
            label="İş Günü (Business Date)"
            value={businessDate || "-"}
            subValue={previousDate ? `Önceki: ${previousDate}` : undefined}
            color="text-indigo-600"
          />
          <StatCard
            icon={BarChart3}
            label="Toplam Denetim"
            value={historyTotal}
            subValue={todayCompleted ? "Bugün tamamlandı" : "Bugün bekliyor"}
            color="text-emerald-600"
          />
          <StatCard
            icon={DollarSign}
            label="Son Oda Geliri"
            value={lastRun ? `${lastRun.total_room_revenue?.toFixed(2) || "0.00"} TL` : "-"}
            subValue={lastRun ? `Vergi: ${lastRun.total_tax_amount?.toFixed(2) || "0.00"} TL` : undefined}
            color="text-blue-600"
          />
          <StatCard
            icon={Users}
            label="Son No-Show"
            value={lastRun?.no_shows_processed ?? "-"}
            subValue={lastRun ? `${lastRun.rooms_processed || 0} oda işlendi` : undefined}
            color="text-amber-600"
          />
        </div>

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

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowRunDialog(false)} disabled={running}>
                  İptal
                </Button>
                <Button
                  data-testid="confirm-run-btn"
                  onClick={handleRunAudit}
                  disabled={running}
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
