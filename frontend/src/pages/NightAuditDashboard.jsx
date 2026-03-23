import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
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

const statusConfig = {
  completed: { label: "Tamamlandi", color: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: CheckCircle2 },
  completed_with_exceptions: { label: "Istisnali Tamamlandi", color: "bg-amber-100 text-amber-700 border-amber-200", icon: AlertTriangle },
  running: { label: "Calisiyor", color: "bg-blue-100 text-blue-700 border-blue-200", icon: Loader2 },
  failed: { label: "Basarisiz", color: "bg-red-100 text-red-700 border-red-200", icon: XCircle },
  pending: { label: "Bekliyor", color: "bg-gray-100 text-gray-600 border-gray-200", icon: Clock },
};

const severityConfig = {
  info: { label: "Bilgi", color: "bg-blue-50 text-blue-700 border-blue-200" },
  warning: { label: "Uyari", color: "bg-amber-50 text-amber-700 border-amber-200" },
  error: { label: "Hata", color: "bg-red-50 text-red-700 border-red-200" },
  critical: { label: "Kritik", color: "bg-red-100 text-red-800 border-red-300" },
};

const StatusBadge = ({ status }) => {
  const cfg = statusConfig[status] || statusConfig.pending;
  const Icon = cfg.icon;
  return (
    <Badge data-testid={`status-badge-${status}`} className={`${cfg.color} border gap-1 font-medium`}>
      <Icon className={`w-3 h-3 ${status === "running" ? "animate-spin" : ""}`} />
      {cfg.label}
    </Badge>
  );
};

const SeverityBadge = ({ severity }) => {
  const cfg = severityConfig[severity] || severityConfig.info;
  return (
    <Badge className={`${cfg.color} border text-[11px]`}>{cfg.label}</Badge>
  );
};

const StatCard = ({ icon: Icon, label, value, subValue, color = "text-gray-600" }) => (
  <div className="bg-white border rounded-xl p-4 flex items-start gap-3">
    <div className={`rounded-lg p-2 ${color.replace("text-", "bg-").replace("-600", "-100")}`}>
      <Icon className={`w-5 h-5 ${color}`} />
    </div>
    <div className="min-w-0">
      <p className="text-2xl font-bold text-gray-900 leading-tight">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      {subValue && <p className="text-[11px] text-gray-400 mt-0.5">{subValue}</p>}
    </div>
  </div>
);

const IntegrityBadge = ({ status }) => {
  const cfg = {
    pass: { label: "Gecti", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    warning: { label: "Uyari", cls: "bg-amber-50 text-amber-700 border-amber-200" },
    error: { label: "Hata", cls: "bg-red-50 text-red-700 border-red-200" },
    fail: { label: "Basarisiz", cls: "bg-red-50 text-red-700 border-red-200" },
  }[status] || { label: status, cls: "bg-gray-50 text-gray-600 border-gray-200" };
  return <Badge className={`${cfg.cls} border text-[11px]`}>{cfg.label}</Badge>;
};

const categoryLabels = {
  room: "Oda",
  no_show_fee: "No-Show",
  room_service: "Oda Servisi",
  minibar: "Minibar",
  restaurant: "Restoran",
  spa: "Spa",
  laundry: "Camasir",
  parking: "Park",
  other: "Diger",
};

const paymentMethodLabels = {
  cash: "Nakit",
  credit_card: "Kredi Karti",
  debit_card: "Banka Karti",
  bank_transfer: "Havale/EFT",
  city_ledger: "Cari Hesap",
  agency: "Acente",
  other: "Diger",
};

const NightAuditDashboard = ({ user, tenant, onLogout }) => {
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
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
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
      toast.error("Finansal rapor yuklenemedi");
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
          ? `Simuelasyon tamamlandi: ${result.rooms_processed} oda islendi`
          : `Gece denetimi tamamlandi: ${result.charges_posted} masraf kaydedildi`
      );
      setShowRunDialog(false);
      setRunOptions({ force_rerun: false, skip_validations: false, dry_run: false, reason: "" });
      await loadAll();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === "object" && detail?.message) {
        toast.error(detail.message);
      } else if (typeof detail === "string") {
        toast.error(detail);
      } else {
        toast.error("Gece denetimi basarisiz oldu");
      }
    } finally {
      setRunning(false);
    }
  };

  const handleSaveSchedule = async () => {
    setScheduleLoading(true);
    try {
      await axios.put("/night-audit/schedule", schedule);
      toast.success(schedule.enabled ? "Otomatik zamanlama aktif edildi" : "Otomatik zamanlama devre disi birakildi");
      setShowScheduleDialog(false);
      await fetchScheduleStatus();
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
      toast.success(newEnabled ? "Otomatik zamanlama aktif" : "Otomatik zamanlama devre disi");
      await fetchScheduleStatus();
    } catch (err) {
      toast.error("Durum degistirilemedi");
    }
  };

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

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="night_audit">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h1 data-testid="night-audit-title" className="text-xl md:text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Moon className="w-6 h-6 text-indigo-600" />
              Gece Denetimi (Night Audit)
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Gun sonu islemleri: oda masrafi kaydi, no-show isleme, folio bakiye kontrolu, finansal raporlama
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
              Denetim Baslat
            </Button>
          </div>
        </div>

        {/* Business Date & Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            icon={Calendar}
            label="Is Gunu (Business Date)"
            value={businessDate || "-"}
            subValue={previousDate ? `Onceki: ${previousDate}` : undefined}
            color="text-indigo-600"
          />
          <StatCard
            icon={BarChart3}
            label="Toplam Denetim"
            value={historyTotal}
            subValue={todayCompleted ? "Bugun tamamlandi" : "Bugun bekliyor"}
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
            subValue={lastRun ? `${lastRun.rooms_processed || 0} oda islendi` : undefined}
            color="text-amber-600"
          />
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-gray-100/80 p-1">
            <TabsTrigger data-testid="tab-overview" value="overview" className="text-xs gap-1.5">
              <Moon className="w-3.5 h-3.5" /> Genel Bakis
            </TabsTrigger>
            <TabsTrigger data-testid="tab-financial" value="financial" className="text-xs gap-1.5">
              <TrendingUp className="w-3.5 h-3.5" /> Finansal Ozet
            </TabsTrigger>
            <TabsTrigger data-testid="tab-reconciliation" value="reconciliation" className="text-xs gap-1.5">
              <Scale className="w-3.5 h-3.5" /> Mutabakat
            </TabsTrigger>
            <TabsTrigger data-testid="tab-integrity" value="integrity" className="text-xs gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5" /> Butunluk
            </TabsTrigger>
            <TabsTrigger data-testid="tab-report" value="report" className="text-xs gap-1.5">
              <FileText className="w-3.5 h-3.5" /> Rapor
            </TabsTrigger>
          </TabsList>

          {/* ═══ Overview Tab ═══ */}
          <TabsContent value="overview" className="space-y-4 mt-4">
            {/* Automatic Scheduling Card */}
            <Card data-testid="schedule-card">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Timer className="w-4 h-4 text-indigo-500" />
                    Otomatik Zamanlama
                  </CardTitle>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                      <Switch
                        data-testid="schedule-toggle"
                        checked={schedule.enabled}
                        onCheckedChange={handleQuickToggleSchedule}
                      />
                      <span className={`text-xs font-medium ${schedule.enabled ? "text-emerald-600" : "text-gray-400"}`}>
                        {schedule.enabled ? "Aktif" : "Devre Disi"}
                      </span>
                    </div>
                    <Button
                      data-testid="schedule-settings-btn"
                      variant="outline"
                      size="sm"
                      onClick={() => setShowScheduleDialog(true)}
                    >
                      <Settings2 className="w-3.5 h-3.5 mr-1" />
                      Ayarlar
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                    <div className="rounded-lg p-2 bg-indigo-100">
                      <Clock className="w-4 h-4 text-indigo-600" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-900">
                        {String(schedule.scheduled_hour).padStart(2, "0")}:{String(schedule.scheduled_minute).padStart(2, "0")}
                      </p>
                      <p className="text-xs text-gray-500">{schedule.timezone || "Europe/Istanbul"}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                    <div className={`rounded-lg p-2 ${
                      scheduleStatus?.last_auto_run_status === "completed" ? "bg-emerald-100"
                        : scheduleStatus?.last_auto_run_status === "failed" ? "bg-red-100" : "bg-gray-100"
                    }`}>
                      {scheduleStatus?.last_auto_run_status === "completed" ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      ) : scheduleStatus?.last_auto_run_status === "failed" ? (
                        <XCircle className="w-4 h-4 text-red-600" />
                      ) : (
                        <Clock className="w-4 h-4 text-gray-400" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-900">
                        {scheduleStatus?.last_auto_run
                          ? new Date(scheduleStatus.last_auto_run).toLocaleString("tr-TR")
                          : "Henuz calistirilmadi"}
                      </p>
                      <p className="text-xs text-gray-500">Son otomatik calistirma</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                    <div className="rounded-lg p-2 bg-blue-100">
                      <Zap className="w-4 h-4 text-blue-600" />
                    </div>
                    <div>
                      <div className="flex flex-wrap gap-1">
                        {schedule.auto_retry && (
                          <Badge className="bg-blue-50 text-blue-700 border border-blue-200 text-[10px]">
                            Otomatik Yeniden Deneme
                          </Badge>
                        )}
                        {schedule.skip_validations && (
                          <Badge className="bg-amber-50 text-amber-700 border border-amber-200 text-[10px]">
                            Dogrulama Atla
                          </Badge>
                        )}
                        {!schedule.auto_retry && !schedule.skip_validations && (
                          <Badge className="bg-gray-50 text-gray-500 border border-gray-200 text-[10px]">
                            Standart Ayarlar
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">Ozellikler</p>
                    </div>
                  </div>
                </div>
                {scheduleStatus?.recent_logs?.length > 0 && (
                  <div className="mt-3 border-t pt-3">
                    <p className="text-xs font-semibold text-gray-600 mb-2">Son Otomatik Calistirma Loglari</p>
                    <div className="space-y-1.5 max-h-32 overflow-y-auto">
                      {scheduleStatus.recent_logs.map((log) => (
                        <div key={log.id} className="flex items-center justify-between text-xs p-1.5 bg-gray-50 rounded">
                          <div className="flex items-center gap-2">
                            {log.status === "completed" ? (
                              <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                            ) : log.status === "failed" ? (
                              <XCircle className="w-3 h-3 text-red-500" />
                            ) : (
                              <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
                            )}
                            <span className="text-gray-700">{log.business_date}</span>
                          </div>
                          <span className="text-gray-400">
                            {log.triggered_at ? new Date(log.triggered_at).toLocaleString("tr-TR") : "-"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Latest Run Summary */}
            {lastRun && (
              <Card data-testid="last-run-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <FileText className="w-4 h-4 text-gray-500" />
                    Son Denetim Ozeti
                    <StatusBadge status={lastRun.status} />
                    {lastRun.is_dry_run && (
                      <Badge className="bg-purple-100 text-purple-700 border-purple-200 border text-[11px]">
                        Simuelasyon
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 text-sm">
                    <div>
                      <span className="text-gray-500 text-xs">Is Gunu</span>
                      <p className="font-semibold">{lastRun.business_date}</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Odalar</span>
                      <p className="font-semibold">{lastRun.rooms_processed}</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Masraflar</span>
                      <p className="font-semibold">{lastRun.charges_posted}</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Oda Geliri</span>
                      <p className="font-semibold">{lastRun.total_room_revenue?.toFixed(2)} TL</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Vergi</span>
                      <p className="font-semibold">{lastRun.total_tax_amount?.toFixed(2)} TL</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Sure</span>
                      <p className="font-semibold">{lastRun.duration_ms ? `${lastRun.duration_ms}ms` : "-"}</p>
                    </div>
                  </div>
                  {(lastRun.arrivals_pending > 0 || lastRun.departures_pending > 0 || lastRun.folios_unbalanced > 0) && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {lastRun.arrivals_pending > 0 && (
                        <Badge className="bg-blue-50 text-blue-700 border border-blue-200 text-xs">
                          {lastRun.arrivals_pending} bekleyen giris
                        </Badge>
                      )}
                      {lastRun.departures_pending > 0 && (
                        <Badge className="bg-orange-50 text-orange-700 border border-orange-200 text-xs">
                          {lastRun.departures_pending} bekleyen cikis
                        </Badge>
                      )}
                      {lastRun.folios_unbalanced > 0 && (
                        <Badge className="bg-red-50 text-red-700 border border-red-200 text-xs">
                          {lastRun.folios_unbalanced} dengesiz folio
                        </Badge>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* History Table */}
            <Card data-testid="audit-history-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Clock className="w-4 h-4 text-gray-500" />
                  Denetim Gecmisi ({historyTotal})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
                    <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
                    Yukleniyor...
                  </div>
                ) : history.length === 0 ? (
                  <div data-testid="no-history" className="py-10 text-center text-gray-500 text-sm">
                    <Moon className="w-10 h-10 mx-auto text-gray-300 mb-2" />
                    Henuz gece denetimi yapilmamis
                  </div>
                ) : (
                  <div className="space-y-2">
                    {history.map((run) => {
                      const isExpanded = expandedRun === run.audit_id;
                      const runExceptions = exceptions[run.audit_id] || [];
                      const startedAt = run.started_at ? new Date(run.started_at) : null;
                      return (
                        <div
                          key={run.audit_id}
                          data-testid={`audit-run-${run.audit_id}`}
                          className="border rounded-lg overflow-hidden"
                        >
                          <div
                            className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50/50 transition"
                            onClick={() => toggleExpand(run.audit_id)}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <StatusBadge status={run.status} />
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-gray-900">
                                  {run.business_date}
                                  {run.is_dry_run && <span className="ml-1.5 text-purple-600 text-xs font-normal">(Simuelasyon)</span>}
                                  {run.is_rerun && <span className="ml-1.5 text-orange-600 text-xs font-normal">(Tekrar)</span>}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {startedAt ? startedAt.toLocaleString("tr-TR") : "-"}
                                  {run.duration_ms ? ` - ${run.duration_ms}ms` : ""}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-3">
                              <div className="hidden md:flex items-center gap-4 text-xs text-gray-500">
                                <span>{run.rooms_processed} oda</span>
                                <span>{run.charges_posted} masraf</span>
                                <span>{run.total_room_revenue?.toFixed(0)} TL</span>
                                {run.exceptions_count > 0 && (
                                  <Badge className="bg-amber-50 text-amber-700 border border-amber-200 text-[11px]">
                                    {run.exceptions_count} istisna
                                  </Badge>
                                )}
                              </div>
                              {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                            </div>
                          </div>
                          {isExpanded && (
                            <div className="border-t bg-gray-50/50 px-4 py-3 space-y-3">
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                                <div>
                                  <span className="text-gray-500 text-xs">Oda Geliri</span>
                                  <p className="font-semibold">{run.total_room_revenue?.toFixed(2)} TL</p>
                                </div>
                                <div>
                                  <span className="text-gray-500 text-xs">Vergi</span>
                                  <p className="font-semibold">{run.total_tax_amount?.toFixed(2)} TL</p>
                                </div>
                                <div>
                                  <span className="text-gray-500 text-xs">No-Show</span>
                                  <p className="font-semibold">{run.no_shows_processed}</p>
                                </div>
                                <div>
                                  <span className="text-gray-500 text-xs">Folio (Dengeli/Dengesiz)</span>
                                  <p className="font-semibold">
                                    <span className="text-emerald-600">{run.folios_balanced}</span>
                                    {" / "}
                                    <span className={run.folios_unbalanced > 0 ? "text-red-600" : "text-gray-400"}>{run.folios_unbalanced}</span>
                                  </p>
                                </div>
                              </div>
                              {runExceptions.length > 0 ? (
                                <div>
                                  <p className="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-1">
                                    <AlertTriangle className="w-3.5 h-3.5" /> Istisnalar ({runExceptions.length})
                                  </p>
                                  <div className="space-y-1.5 max-h-60 overflow-y-auto">
                                    {runExceptions.map((exc) => (
                                      <div key={exc.id} className="flex items-start gap-2 p-2 bg-white border rounded text-xs">
                                        <SeverityBadge severity={exc.severity} />
                                        <div className="min-w-0 flex-1">
                                          <p className="text-gray-800">{exc.message}</p>
                                          <p className="text-gray-400 text-[11px] mt-0.5">
                                            {exc.category} - {exc.entity_type}
                                            {exc.entity_id ? ` - ${exc.entity_id.substring(0, 8)}...` : ""}
                                          </p>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : run.exceptions_count === 0 ? (
                                <p className="text-xs text-gray-400 flex items-center gap-1">
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                                  Istisna yok - denetim temiz tamamlandi
                                </p>
                              ) : (
                                <p className="text-xs text-gray-400">Istisnalar yukleniyor...</p>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══ Financial Summary Tab ═══ */}
          <TabsContent value="financial" className="space-y-4 mt-4">
            {financialSummary ? (
              <>
                {/* Revenue & Payment Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard
                    icon={TrendingUp}
                    label="Toplam Gelir"
                    value={`${financialSummary.revenue?.total?.toFixed(2) || "0.00"} TL`}
                    subValue={`${financialSummary.revenue?.charges_count || 0} masraf`}
                    color="text-emerald-600"
                  />
                  <StatCard
                    icon={Receipt}
                    label="Vergi Toplami"
                    value={`${financialSummary.tax?.total?.toFixed(2) || "0.00"} TL`}
                    subValue={`KDV: ${financialSummary.tax?.breakdown?.vat?.toFixed(2) || "0"} TL`}
                    color="text-blue-600"
                  />
                  <StatCard
                    icon={CreditCard}
                    label="Toplam Odeme"
                    value={`${financialSummary.payments?.total?.toFixed(2) || "0.00"} TL`}
                    subValue={`${financialSummary.payments?.payments_count || 0} odeme`}
                    color="text-indigo-600"
                  />
                  <StatCard
                    icon={ArrowUpDown}
                    label="Net Pozisyon"
                    value={`${financialSummary.net_position?.toFixed(2) || "0.00"} TL`}
                    subValue={financialSummary.net_position > 0 ? "Alacak" : financialSummary.net_position < 0 ? "Fazla odeme" : "Dengeli"}
                    color={financialSummary.net_position > 0 ? "text-amber-600" : financialSummary.net_position < 0 ? "text-red-600" : "text-emerald-600"}
                  />
                </div>

                {/* Revenue Breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card data-testid="revenue-breakdown-card">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <PieChart className="w-4 h-4 text-emerald-500" />
                        Gelir Dagilimi (Kategori)
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {Object.keys(financialSummary.revenue?.by_category || {}).length === 0 ? (
                        <p className="text-xs text-gray-400 py-6 text-center">Bugun icin masraf kaydedilmemis</p>
                      ) : (
                        <div className="space-y-2">
                          {Object.entries(financialSummary.revenue.by_category).map(([cat, data]) => {
                            const pct = financialSummary.revenue.total > 0
                              ? ((data.amount / financialSummary.revenue.total) * 100).toFixed(1)
                              : 0;
                            return (
                              <div key={cat} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                                <div className="flex items-center gap-2">
                                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                                  <span className="text-sm font-medium text-gray-700">{categoryLabels[cat] || cat}</span>
                                  <span className="text-[11px] text-gray-400">({data.count})</span>
                                </div>
                                <div className="text-right">
                                  <span className="text-sm font-semibold text-gray-900">{data.amount.toFixed(2)} TL</span>
                                  <span className="text-[11px] text-gray-400 ml-2">{pct}%</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card data-testid="payment-methods-card">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Banknote className="w-4 h-4 text-indigo-500" />
                        Odeme Yontemleri
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {Object.keys(financialSummary.payments?.by_method || {}).length === 0 ? (
                        <p className="text-xs text-gray-400 py-6 text-center">Bugun icin odeme kaydedilmemis</p>
                      ) : (
                        <div className="space-y-2">
                          {Object.entries(financialSummary.payments.by_method).map(([method, data]) => (
                            <div key={method} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                              <div className="flex items-center gap-2">
                                <CreditCard className="w-3.5 h-3.5 text-indigo-400" />
                                <span className="text-sm font-medium text-gray-700">{paymentMethodLabels[method] || method}</span>
                                <span className="text-[11px] text-gray-400">({data.count})</span>
                              </div>
                              <span className="text-sm font-semibold text-gray-900">{data.amount.toFixed(2)} TL</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Open Folios */}
                <Card data-testid="open-folios-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <FileText className="w-4 h-4 text-amber-500" />
                      Acik Folyolar
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <p className="text-2xl font-bold text-gray-900">{financialSummary.open_folios?.count || 0}</p>
                        <p className="text-xs text-gray-500">Toplam Acik Folyo</p>
                      </div>
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <p className="text-2xl font-bold text-gray-900">{financialSummary.open_folios?.balance?.total?.toFixed(2) || "0.00"} TL</p>
                        <p className="text-xs text-gray-500">Toplam Bakiye</p>
                      </div>
                      <div className="p-3 bg-amber-50 rounded-lg">
                        <p className="text-2xl font-bold text-amber-700">{financialSummary.open_folios?.balance?.receivable?.toFixed(2) || "0.00"} TL</p>
                        <p className="text-xs text-amber-600">Alacak</p>
                      </div>
                      <div className="p-3 bg-blue-50 rounded-lg">
                        <p className="text-2xl font-bold text-blue-700">{financialSummary.open_folios?.balance?.overpayment?.toFixed(2) || "0.00"} TL</p>
                        <p className="text-xs text-blue-600">Fazla Odeme</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </>
            ) : (
              <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
                <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Finansal ozet yukleniyor...
              </div>
            )}
          </TabsContent>

          {/* ═══ Reconciliation Tab ═══ */}
          <TabsContent value="reconciliation" className="space-y-4 mt-4">
            {reconciliation ? (
              <>
                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard
                    icon={Receipt}
                    label="Masraf Toplami"
                    value={`${reconciliation.charges_total?.toFixed(2) || "0.00"} TL`}
                    subValue={`${reconciliation.charges_count || 0} masraf`}
                    color="text-blue-600"
                  />
                  <StatCard
                    icon={CreditCard}
                    label="Odeme Toplami"
                    value={`${reconciliation.payments_total?.toFixed(2) || "0.00"} TL`}
                    subValue={`${reconciliation.payments_count || 0} odeme`}
                    color="text-emerald-600"
                  />
                  <StatCard
                    icon={Scale}
                    label="Fark"
                    value={`${reconciliation.variance?.toFixed(2) || "0.00"} TL`}
                    subValue={reconciliation.is_balanced ? "Dengeli" : "Dengesiz"}
                    color={reconciliation.is_balanced ? "text-emerald-600" : "text-red-600"}
                  />
                  <StatCard
                    icon={AlertOctagon}
                    label="Tutarsizlik"
                    value={reconciliation.discrepancy_count || 0}
                    subValue={`${reconciliation.high_balance_count || 0} yuksek bakiye`}
                    color={reconciliation.discrepancy_count > 0 ? "text-red-600" : "text-emerald-600"}
                  />
                </div>

                {/* Discrepancies */}
                <Card data-testid="discrepancies-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-500" />
                      Tutarsizliklar ({reconciliation.discrepancy_count || 0})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {(reconciliation.discrepancies || []).length === 0 ? (
                      <div className="py-8 text-center">
                        <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400 mb-2" />
                        <p className="text-sm text-gray-500">Tutarsizlik bulunamadi - mutabakat temiz</p>
                      </div>
                    ) : (
                      <div className="space-y-2 max-h-80 overflow-y-auto">
                        {reconciliation.discrepancies.map((d, i) => (
                          <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 border rounded-lg">
                            <div className={`rounded-lg p-1.5 flex-shrink-0 ${
                              d.severity === "error" ? "bg-red-100" : "bg-amber-100"
                            }`}>
                              {d.severity === "error" ? (
                                <XCircle className="w-4 h-4 text-red-600" />
                              ) : (
                                <AlertTriangle className="w-4 h-4 text-amber-600" />
                              )}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="text-sm text-gray-800">{d.message}</p>
                              <div className="flex items-center gap-2 mt-1">
                                <Badge className={`text-[10px] ${
                                  d.type === "duplicate_charge" ? "bg-amber-50 text-amber-700 border-amber-200"
                                    : d.type === "rate_discrepancy" ? "bg-blue-50 text-blue-700 border-blue-200"
                                    : d.type === "high_balance" ? "bg-red-50 text-red-700 border-red-200"
                                    : "bg-gray-50 text-gray-600 border-gray-200"
                                } border`}>
                                  {d.type === "duplicate_charge" ? "Tekrar Masraf"
                                    : d.type === "rate_discrepancy" ? "Oran Tutarsizligi"
                                    : d.type === "high_balance" ? "Yuksek Bakiye"
                                    : d.type === "orphan_charge" ? "Sahipsiz Masraf"
                                    : d.type}
                                </Badge>
                                {d.amount && <span className="text-[11px] text-gray-400">{d.amount} TL</span>}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* High Balance Folios */}
                {(reconciliation.high_balance_folios || []).length > 0 && (
                  <Card data-testid="high-balance-folios-card">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <AlertOctagon className="w-4 h-4 text-red-500" />
                        Yuksek Bakiyeli Folyolar ({reconciliation.high_balance_count})
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-1.5">
                        {reconciliation.high_balance_folios.map((f) => (
                          <div key={f.id} className="flex items-center justify-between p-2.5 bg-gray-50 rounded-lg text-sm">
                            <div className="flex items-center gap-2">
                              <FileText className="w-4 h-4 text-gray-400" />
                              <span className="font-medium text-gray-800">{f.folio_number || f.id?.substring(0, 8)}</span>
                            </div>
                            <span className={`font-bold ${f.balance > 0 ? "text-red-600" : "text-blue-600"}`}>
                              {f.balance?.toFixed(2)} TL
                            </span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : (
              <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
                <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Mutabakat yukleniyor...
              </div>
            )}
          </TabsContent>

          {/* ═══ Integrity Check Tab ═══ */}
          <TabsContent value="integrity" className="space-y-4 mt-4">
            {integrityCheck ? (
              <>
                {/* Summary */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard
                    icon={ShieldCheck}
                    label="Toplam Kontrol"
                    value={integrityCheck.summary?.total || 0}
                    color="text-indigo-600"
                  />
                  <StatCard
                    icon={CheckCircle2}
                    label="Gecen"
                    value={integrityCheck.summary?.passed || 0}
                    color="text-emerald-600"
                  />
                  <StatCard
                    icon={AlertTriangle}
                    label="Uyari"
                    value={integrityCheck.summary?.warnings || 0}
                    color="text-amber-600"
                  />
                  <StatCard
                    icon={XCircle}
                    label="Basarisiz"
                    value={integrityCheck.summary?.failures || 0}
                    color="text-red-600"
                  />
                </div>

                {/* Overall Status */}
                <div className={`p-4 rounded-xl border-2 ${
                  integrityCheck.summary?.overall_status === "pass" ? "border-emerald-200 bg-emerald-50"
                    : integrityCheck.summary?.overall_status === "warning" ? "border-amber-200 bg-amber-50"
                    : "border-red-200 bg-red-50"
                }`}>
                  <div className="flex items-center gap-3">
                    {integrityCheck.summary?.overall_status === "pass" ? (
                      <ShieldCheck className="w-6 h-6 text-emerald-600" />
                    ) : integrityCheck.summary?.overall_status === "warning" ? (
                      <AlertTriangle className="w-6 h-6 text-amber-600" />
                    ) : (
                      <XCircle className="w-6 h-6 text-red-600" />
                    )}
                    <div>
                      <p className="text-sm font-bold text-gray-900">
                        {integrityCheck.summary?.overall_status === "pass" ? "Finansal Butunluk Kontrolu Gecti"
                          : integrityCheck.summary?.overall_status === "warning" ? "Uyarilarla Gecti"
                          : "Butunluk Sorunlari Tespit Edildi"}
                      </p>
                      <p className="text-xs text-gray-600">
                        {integrityCheck.business_date} tarihli kontrol sonuclari
                      </p>
                    </div>
                  </div>
                </div>

                {/* Individual Checks */}
                <Card data-testid="integrity-checks-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Shield className="w-4 h-4 text-indigo-500" />
                      Kontrol Detaylari
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {(integrityCheck.checks || []).map((check, i) => (
                        <div
                          key={i}
                          data-testid={`integrity-check-${check.check}`}
                          className={`flex items-center justify-between p-3 rounded-lg border ${
                            check.status === "pass" ? "bg-emerald-50/50 border-emerald-100"
                              : check.status === "warning" ? "bg-amber-50/50 border-amber-100"
                              : "bg-red-50/50 border-red-100"
                          }`}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            {check.status === "pass" ? (
                              <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
                            ) : check.status === "warning" ? (
                              <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
                            ) : (
                              <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                            )}
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-gray-800">{check.label}</p>
                              <p className="text-xs text-gray-500 mt-0.5">{check.detail}</p>
                            </div>
                          </div>
                          <IntegrityBadge status={check.status} />
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </>
            ) : (
              <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
                <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Butunluk kontrolu yukleniyor...
              </div>
            )}
          </TabsContent>

          {/* ═══ Financial Report Tab ═══ */}
          <TabsContent value="report" className="space-y-4 mt-4">
            <Card data-testid="financial-report-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Search className="w-4 h-4 text-indigo-500" />
                  Tarih Araligi Finansal Rapor
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row items-end gap-3 mb-4">
                  <div className="flex-1">
                    <label className="text-xs text-gray-600 mb-1 block">Baslangic Tarihi</label>
                    <input
                      data-testid="report-start-date"
                      type="date"
                      value={reportDates.start}
                      onChange={(e) => setReportDates((p) => ({ ...p, start: e.target.value }))}
                      className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-xs text-gray-600 mb-1 block">Bitis Tarihi</label>
                    <input
                      data-testid="report-end-date"
                      type="date"
                      value={reportDates.end}
                      onChange={(e) => setReportDates((p) => ({ ...p, end: e.target.value }))}
                      className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                  </div>
                  <Button
                    data-testid="generate-report-btn"
                    size="sm"
                    onClick={() => fetchFinancialReport(reportDates.start, reportDates.end)}
                    disabled={!reportDates.start || !reportDates.end || finLoading}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white"
                  >
                    {finLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <BarChart3 className="w-4 h-4 mr-1" />}
                    Rapor Olustur
                  </Button>
                </div>

                {financialReport ? (
                  <div className="space-y-4">
                    {/* Summary */}
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                      <div className="p-3 bg-emerald-50 rounded-lg">
                        <p className="text-lg font-bold text-emerald-700">{financialReport.summary?.total_revenue?.toFixed(2)} TL</p>
                        <p className="text-[11px] text-emerald-600">Toplam Gelir</p>
                      </div>
                      <div className="p-3 bg-blue-50 rounded-lg">
                        <p className="text-lg font-bold text-blue-700">{financialReport.summary?.total_tax?.toFixed(2)} TL</p>
                        <p className="text-[11px] text-blue-600">Toplam Vergi</p>
                      </div>
                      <div className="p-3 bg-indigo-50 rounded-lg">
                        <p className="text-lg font-bold text-indigo-700">{financialReport.summary?.total_with_tax?.toFixed(2)} TL</p>
                        <p className="text-[11px] text-indigo-600">Vergili Toplam</p>
                      </div>
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <p className="text-lg font-bold text-gray-700">{financialReport.summary?.total_payments?.toFixed(2)} TL</p>
                        <p className="text-[11px] text-gray-600">Toplam Odeme</p>
                      </div>
                      <div className="p-3 bg-amber-50 rounded-lg">
                        <p className="text-lg font-bold text-amber-700">{financialReport.summary?.net_position?.toFixed(2)} TL</p>
                        <p className="text-[11px] text-amber-600">Net Pozisyon</p>
                      </div>
                      <div className="p-3 bg-purple-50 rounded-lg">
                        <p className="text-lg font-bold text-purple-700">{financialReport.summary?.total_bookings || 0}</p>
                        <p className="text-[11px] text-purple-600">Toplam Rezervasyon</p>
                      </div>
                    </div>

                    {/* Category Breakdown */}
                    {Object.keys(financialReport.revenue_by_category || {}).length > 0 && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-sm">Kategori Bazli Gelir</CardTitle>
                          </CardHeader>
                          <CardContent>
                            <div className="space-y-2">
                              {Object.entries(financialReport.revenue_by_category).map(([cat, data]) => (
                                <div key={cat} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                                  <span className="text-sm font-medium text-gray-700">{categoryLabels[cat] || cat}</span>
                                  <div className="text-right">
                                    <span className="text-sm font-semibold">{data.amount.toFixed(2)} TL</span>
                                    <span className="text-[11px] text-gray-400 ml-2">({data.count})</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-sm">Odeme Yontem Dagilimi</CardTitle>
                          </CardHeader>
                          <CardContent>
                            {Object.keys(financialReport.payments_by_method || {}).length === 0 ? (
                              <p className="text-xs text-gray-400 py-4 text-center">Odeme kaydedilmemis</p>
                            ) : (
                              <div className="space-y-2">
                                {Object.entries(financialReport.payments_by_method).map(([method, data]) => (
                                  <div key={method} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                                    <span className="text-sm font-medium text-gray-700">{paymentMethodLabels[method] || method}</span>
                                    <div className="text-right">
                                      <span className="text-sm font-semibold">{data.amount.toFixed(2)} TL</span>
                                      <span className="text-[11px] text-gray-400 ml-2">({data.count})</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      </div>
                    )}

                    {/* Daily Revenue Trend */}
                    {(financialReport.revenue_by_date || []).length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm flex items-center gap-2">
                            <BarChart3 className="w-4 h-4 text-emerald-500" />
                            Gunluk Gelir Trendi
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-xs text-gray-500 border-b">
                                  <th className="text-left pb-2 pr-4">Tarih</th>
                                  <th className="text-right pb-2 pr-4">Gelir</th>
                                  <th className="text-right pb-2 pr-4">Vergi</th>
                                  <th className="text-right pb-2">Kategoriler</th>
                                </tr>
                              </thead>
                              <tbody>
                                {financialReport.revenue_by_date.map((day) => (
                                  <tr key={day.date} className="border-b border-gray-50 hover:bg-gray-50">
                                    <td className="py-2 pr-4 font-medium">{day.date}</td>
                                    <td className="py-2 pr-4 text-right font-semibold text-emerald-600">{day.total.toFixed(2)} TL</td>
                                    <td className="py-2 pr-4 text-right text-gray-500">{day.tax.toFixed(2)} TL</td>
                                    <td className="py-2 text-right">
                                      <div className="flex flex-wrap justify-end gap-1">
                                        {Object.entries(day.categories || {}).map(([cat, d]) => (
                                          <Badge key={cat} className="bg-gray-100 text-gray-600 border-gray-200 border text-[10px]">
                                            {categoryLabels[cat] || cat}: {d.amount.toFixed(0)}
                                          </Badge>
                                        ))}
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {/* Audit Runs in Range */}
                    {(financialReport.audit_runs || []).length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm flex items-center gap-2">
                            <Moon className="w-4 h-4 text-indigo-500" />
                            Donem Denetim Gecmisi ({financialReport.audit_runs.length})
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-xs text-gray-500 border-b">
                                  <th className="text-left pb-2 pr-4">Tarih</th>
                                  <th className="text-left pb-2 pr-4">Durum</th>
                                  <th className="text-right pb-2 pr-4">Gelir</th>
                                  <th className="text-right pb-2 pr-4">Vergi</th>
                                  <th className="text-right pb-2 pr-4">Oda</th>
                                  <th className="text-right pb-2">Sure</th>
                                </tr>
                              </thead>
                              <tbody>
                                {financialReport.audit_runs.map((run) => (
                                  <tr key={run.audit_id} className="border-b border-gray-50 hover:bg-gray-50">
                                    <td className="py-2 pr-4 font-medium">{run.business_date}</td>
                                    <td className="py-2 pr-4"><StatusBadge status={run.status} /></td>
                                    <td className="py-2 pr-4 text-right font-semibold">{run.total_room_revenue?.toFixed(2)} TL</td>
                                    <td className="py-2 pr-4 text-right text-gray-500">{run.total_tax_amount?.toFixed(2)} TL</td>
                                    <td className="py-2 pr-4 text-right">{run.rooms_processed}</td>
                                    <td className="py-2 text-right text-gray-400">{run.duration_ms ? `${run.duration_ms}ms` : "-"}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </CardContent>
                      </Card>
                    )}
                  </div>
                ) : (
                  <div className="py-12 text-center">
                    <BarChart3 className="w-10 h-10 mx-auto text-gray-300 mb-2" />
                    <p className="text-sm text-gray-500">Tarih araligi secip "Rapor Olustur" butonuna tiklayin</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Schedule Settings Dialog */}
        <Dialog open={showScheduleDialog} onOpenChange={setShowScheduleDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Timer className="w-5 h-5 text-indigo-600" />
                Otomatik Zamanlama Ayarlari
              </DialogTitle>
              <DialogDescription>
                Gece denetiminin otomatik olarak calistirilacagi saat ve secenekleri yapilandir.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              {/* Enable/Disable */}
              <div className="flex items-center justify-between p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
                <div>
                  <p className="text-sm font-medium text-indigo-800">Otomatik Calistirma</p>
                  <p className="text-xs text-indigo-600">Belirlenen saatte otomatik olarak calistirilir</p>
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
                      <p className="text-xs text-gray-500">Basarisiz olursa tekrar dener</p>
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
                    <label className="text-xs text-gray-600 mb-1 block">Maks. Deneme Sayisi</label>
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
                      <p className="text-sm font-medium text-gray-800">Dogrulamalari Atla</p>
                      <p className="text-xs text-gray-500">On kontrolleri atlayarak calistir</p>
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
                    Otomatik calistirmada dogrulama atlama veri tutarsizliklarina yol acabilir.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowScheduleDialog(false)} disabled={scheduleLoading}>
                  Iptal
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
                Gece Denetimi Baslat
              </DialogTitle>
              <DialogDescription>
                Secili is gunu icin gece denetimi islemini baslatir.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
                <p className="text-sm text-indigo-800">
                  <strong>Is Gunu:</strong> {businessDate || "-"}
                </p>
                <p className="text-xs text-indigo-600 mt-1">
                  Bu tarih icin gece denetimi calistirilacak
                </p>
              </div>

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
                    <p className="text-sm font-medium text-gray-800">Simuelasyon (Dry Run)</p>
                    <p className="text-xs text-gray-500">Degisiklik yapmadan test et</p>
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
                    <p className="text-sm font-medium text-gray-800">Tekrar Calistir</p>
                    <p className="text-xs text-gray-500">Daha once tamamlanmissa bile tekrar calistir</p>
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
                    <p className="text-sm font-medium text-gray-800">Dogrulamalari Atla</p>
                    <p className="text-xs text-gray-500">On kontrolleri atlayarak calistir (dikkatli kullanin)</p>
                  </div>
                </label>

                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Aciklama (opsiyonel)</label>
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
                    Dogrulama atlama sadece acil durumlarda kullanilmalidir. On kontrolsuz denetim veri tutarsizliklarina neden olabilir.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowRunDialog(false)} disabled={running}>
                  Iptal
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
                      Simuelasyon Baslat
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 mr-1" />
                      Denetimi Baslat
                    </>
                  )}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default NightAuditDashboard;
