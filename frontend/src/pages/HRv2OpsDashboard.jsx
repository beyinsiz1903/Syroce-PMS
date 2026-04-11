import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import {
  Activity, AlertTriangle, ArrowRight, CheckCircle2, Clock,
  Database, Eye, Gauge, Inbox, Loader2, PlugZap, RefreshCw,
  Server, Shield, ShieldAlert, Timer, Wifi, WifiOff, XCircle,
  Zap, TrendingUp, BarChart3, GitCompare, Radio, Play,
  Target, ArrowUpRight, ArrowDownRight, Minus, Calendar,
  FileText, ChevronRight, Layers, FlaskConical, Link2, Ban,
  CircleSlash, ShieldCheck,
} from "lucide-react";

const TENANT_ID = "syroce_default";
const PROPERTY_ID = "default";

// Health status indicator component
function StatusDot({ status }) {
  const colors = {
    healthy: "bg-emerald-500 shadow-emerald-400/50",
    degraded: "bg-amber-500 shadow-amber-400/50",
    error: "bg-red-500 shadow-red-400/50",
    unknown: "bg-slate-400 shadow-slate-300/50",
  };
  return (
    <span
      data-testid={`status-dot-${status}`}
      className={`inline-block w-2.5 h-2.5 rounded-full shadow-md ${colors[status] || colors.unknown}`}
    />
  );
}

function StatusBadge({ status, label }) {
  const variants = {
    healthy: "bg-emerald-50 text-emerald-700 border-emerald-200",
    degraded: "bg-amber-50 text-amber-700 border-amber-200",
    error: "bg-red-50 text-red-700 border-red-200",
    unknown: "bg-slate-50 text-slate-600 border-slate-200",
    enabled: "bg-emerald-50 text-emerald-700 border-emerald-200",
    disabled: "bg-slate-50 text-slate-500 border-slate-200",
    on: "bg-[#C09D63]/10 text-[#C09D63] border-[#C09D63]/30",
    off: "bg-slate-50 text-slate-500 border-slate-200",
  };
  const dotStatusMap = {
    on: "healthy", enabled: "healthy", off: "unknown", disabled: "unknown",
    healthy: "healthy", degraded: "degraded", error: "error", unknown: "unknown",
  };
  return (
    <span
      data-testid={`status-badge-${label?.toLowerCase().replace(/\s/g, "-")}`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${variants[status] || variants.unknown}`}
    >
      <StatusDot status={dotStatusMap[status] || "unknown"} />
      {label}
    </span>
  );
}

function MetricCard({ icon: Icon, label, value, subtext, color = "text-slate-700" }) {
  return (
    <div data-testid={`metric-${label?.toLowerCase().replace(/\s/g, "-")}`} className="flex items-start gap-3 p-4 rounded-xl bg-slate-50/80 border border-slate-100">
      <div className="p-2 rounded-lg bg-white border border-slate-100 shadow-sm">
        <Icon className="w-4 h-4 text-slate-500" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-slate-500 font-medium tracking-wide uppercase">{label}</p>
        <p className={`text-lg font-semibold mt-0.5 ${color}`}>{value ?? "—"}</p>
        {subtext && <p className="text-xs text-slate-400 mt-0.5 truncate">{subtext}</p>}
      </div>
    </div>
  );
}

function EventRow({ event, index }) {
  const isSuccess = event.success;
  return (
    <div
      data-testid={`event-row-${index}`}
      className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-slate-50 transition-colors group"
    >
      <div className={`p-1 rounded-md ${isSuccess ? "bg-emerald-50" : "bg-red-50"}`}>
        {isSuccess ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> : <XCircle className="w-3.5 h-3.5 text-red-500" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700 truncate">{event.operation}</p>
        <p className="text-xs text-slate-400">{event.correlation_id}</p>
      </div>
      <div className="text-right shrink-0">
        <p className="text-xs text-slate-500">{event.duration_ms}ms</p>
        <p className="text-xs text-slate-400">{formatTime(event.recorded_at)}</p>
      </div>
    </div>
  );
}

function formatTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function formatDateTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

// ── Write Readiness Score Gauge ──────────────────────────────────
function ReadinessGauge({ score, verdict, verdictLabel, components }) {
  const getScoreColor = (s) => {
    if (s >= 90) return { ring: "text-emerald-500", bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" };
    if (s >= 70) return { ring: "text-amber-500", bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" };
    if (s >= 50) return { ring: "text-orange-500", bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200" };
    return { ring: "text-red-500", bg: "bg-red-50", text: "text-red-700", border: "border-red-200" };
  };

  const colors = getScoreColor(score);
  const circumference = 2 * Math.PI * 54;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  const componentLabels = {
    drift: "Drift",
    error_rate: "Hata Orani",
    retry: "Retry",
    dlq: "DLQ",
    latency: "Latency",
  };

  return (
    <div data-testid="readiness-gauge" className="flex flex-col items-center">
      {/* Circular gauge */}
      <div className="relative w-36 h-36 mb-4">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="54" fill="none" strokeWidth="8" className="stroke-slate-100" />
          <circle
            cx="60" cy="60" r="54" fill="none" strokeWidth="8"
            className={colors.ring}
            strokeLinecap="round"
            style={{
              strokeDasharray: circumference,
              strokeDashoffset,
              transition: "stroke-dashoffset 1s ease-in-out",
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-bold ${colors.text}`} style={{ fontFamily: "Manrope, sans-serif" }}>
            {score}
          </span>
          <span className="text-[10px] text-slate-400 uppercase tracking-wider font-medium">/ 100</span>
        </div>
      </div>

      {/* Verdict */}
      <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${colors.bg} ${colors.text} ${colors.border}`}>
        <Target className="w-3 h-3" />
        {verdictLabel}
      </div>

      {/* Component breakdown */}
      {components && (
        <div className="w-full mt-4 space-y-2">
          {Object.entries(components).map(([key, comp]) => {
            const barColor = comp.score >= 80 ? "bg-emerald-500" : comp.score >= 50 ? "bg-amber-500" : "bg-red-500";
            return (
              <div key={key} data-testid={`readiness-component-${key}`} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-600 font-medium">{componentLabels[key] || key}</span>
                  <span className="text-slate-500">{comp.score}<span className="text-slate-400">/100</span></span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${barColor}`}
                    style={{ width: `${comp.score}%`, transition: "width 0.8s ease-in-out" }}
                  />
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-400">
                  <span>{comp.raw_value} {comp.unit}</span>
                  <span>agirlik: %{Math.round(comp.weight * 100)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Transition Phase Indicator ──────────────────────────────────
function TransitionPhaseBar({ currentPhase, phaseDef }) {
  const phases = [
    { key: "shadow", label: "Shadow", icon: Eye },
    { key: "dry_run", label: "Dry-Run", icon: FileText },
    { key: "limited_live", label: "Limited", icon: Layers },
    { key: "full_live", label: "Full Live", icon: Zap },
  ];
  const currentIdx = phases.findIndex(p => p.key === currentPhase);

  return (
    <div data-testid="transition-phase-bar" className="w-full">
      <div className="flex items-center justify-between gap-1">
        {phases.map((p, i) => {
          const isActive = i === currentIdx;
          const isPast = i < currentIdx;
          const Icon = p.icon;
          return (
            <div key={p.key} className="flex items-center gap-1 flex-1">
              <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all flex-1 justify-center ${
                isActive
                  ? "bg-slate-900 text-white shadow-md"
                  : isPast
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                  : "bg-slate-50 text-slate-400 border border-slate-100"
              }`}>
                <Icon className="w-3 h-3" />
                <span className="hidden sm:inline">{p.label}</span>
              </div>
              {i < phases.length - 1 && (
                <ChevronRight className={`w-3.5 h-3.5 shrink-0 ${isPast ? "text-emerald-400" : "text-slate-200"}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Alert Badge ──────────────────────────────────
function AlertItem({ name, alert }) {
  const labels = {
    drift_count_24h: "Drift (24s)",
    retry_count_24h: "Retry (24s)",
    dlq_count: "DLQ",
    error_rate_pct: "Hata Orani",
    avg_latency_ms: "Ort. Latency",
    auth_failure_count: "Auth Hatasi",
    duplicate_ingest_count: "Tekrar Ingest",
    stale_reservation_count: "Stale Rez.",
  };
  const statusColors = {
    ok: "bg-emerald-50 text-emerald-700 border-emerald-200",
    warn: "bg-amber-50 text-amber-700 border-amber-200",
    critical: "bg-red-50 text-red-700 border-red-200",
  };
  const statusIcons = {
    ok: <CheckCircle2 className="w-3 h-3 text-emerald-500" />,
    warn: <AlertTriangle className="w-3 h-3 text-amber-500" />,
    critical: <XCircle className="w-3 h-3 text-red-500" />,
  };

  return (
    <div data-testid={`alert-${name}`} className={`flex items-center justify-between p-2 rounded-lg border text-xs ${statusColors[alert.status] || statusColors.ok}`}>
      <div className="flex items-center gap-1.5">
        {statusIcons[alert.status]}
        <span className="font-medium">{labels[name] || name}</span>
      </div>
      <span className="font-semibold">{alert.value}</span>
    </div>
  );
}

export default function HRv2OpsDashboard({ tenant }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [triggeringRecon, setTriggeringRecon] = useState(false);
  const [collectingSnapshot, setCollectingSnapshot] = useState(false);
  const [observationData, setObservationData] = useState(null);
  const [runningDryRun, setRunningDryRun] = useState(false);
  const [runningChain, setRunningChain] = useState(false);
  const [runningFailSim, setRunningFailSim] = useState(null);
  const [triggeringAutoSnapshot, setTriggeringAutoSnapshot] = useState(false);

  const tenantId = tenant?.tenant_id || TENANT_ID;

  const fetchDashboard = useCallback(async (showToast = false) => {
    try {
      const [dashRes, obsRes] = await Promise.all([
        axios.get(`/channel/hotelrunner-v2/ops-dashboard`, {
          params: { tenant_id: tenantId, property_id: PROPERTY_ID },
        }),
        axios.get(`/channel/hotelrunner-v2/observation/report`, {
          params: { tenant_id: tenantId },
        }).catch(() => ({ data: null })),
      ]);
      setData(dashRes.data);
      setObservationData(obsRes.data);
      if (showToast) toast.success("Dashboard yenilendi");
    } catch (err) {
      console.error("Ops dashboard fetch error:", err);
      toast.error("Dashboard verisi alinamadi");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tenantId]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchDashboard(true);
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/test-connection`, null, {
        params: { tenant_id: tenantId, property_id: PROPERTY_ID },
      });
      if (res.data?.success) {
        toast.success("Baglanti testi basarili", { description: `Latency: ${res.data.total_latency_ms}ms` });
      } else {
        toast.error("Baglanti testi basarisiz");
      }
      // Refresh dashboard after test
      fetchDashboard();
    } catch (err) {
      toast.error("Baglanti testi hatasi", { description: err.message });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleReconcile = async () => {
    setTriggeringRecon(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/reconcile`, null, {
        params: { tenant_id: tenantId, property_id: PROPERTY_ID, since_hours: 24 },
      });
      if (res.data?.success) {
        toast.success("Reconciliation tamamlandi", {
          description: `${res.data.mismatch_count} drift tespit edildi`,
        });
      } else {
        toast.error("Reconciliation hatasi");
      }
      fetchDashboard();
    } catch (err) {
      toast.error("Reconciliation hatasi", { description: err.message });
    } finally {
      setTriggeringRecon(false);
    }
  };

  const handleCollectSnapshot = async () => {
    setCollectingSnapshot(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/observation/snapshot`, null, {
        params: { tenant_id: tenantId },
      });
      const alerts = res.data?.alert_summary;
      toast.success("Gunluk snapshot toplandi", {
        description: alerts ? `${alerts.critical_count} critical, ${alerts.warn_count} warn` : "",
      });
      fetchDashboard();
    } catch (err) {
      toast.error("Snapshot toplama hatasi", { description: err.message });
    } finally {
      setCollectingSnapshot(false);
    }
  };

  const handleDryRunAriPush = async () => {
    setRunningDryRun(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/dry-run/ari-push`, {
        inv_code: "HR:DR-TEST-101",
        start_date: "2026-04-01",
        end_date: "2026-04-05",
        availability: 10,
        price: 200.0,
        verify: true,
      }, { params: { tenant_id: tenantId, property_id: PROPERTY_ID } });
      if (res.data?.success) {
        toast.success("Dry-run ARI push basarili", {
          description: `Correlation: ${res.data.correlation_id} | ${res.data.duration_ms}ms`,
        });
      } else {
        toast.error("Dry-run ARI push basarisiz", {
          description: res.data?.noop_response?.error || "",
        });
      }
      fetchDashboard();
    } catch (err) {
      toast.error("Dry-run hatasi", { description: err.message });
    } finally {
      setRunningDryRun(false);
    }
  };

  const handleDryRunChain = async () => {
    setRunningChain(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/dry-run/chain`, {}, {
        params: { tenant_id: tenantId, property_id: PROPERTY_ID },
      });
      if (res.data?.success) {
        toast.success("Dry-run zincir tamamlandi", {
          description: `${res.data.success_count}/${res.data.step_count} basarili | ${res.data.correlation_id}`,
        });
      } else {
        toast.error("Dry-run zincir basarisiz", {
          description: `${res.data?.failure_count || 0} adim basarisiz`,
        });
      }
      fetchDashboard();
    } catch (err) {
      toast.error("Dry-run zincir hatasi", { description: err.message });
    } finally {
      setRunningChain(false);
    }
  };

  const handleSimulateFailure = async (failureType) => {
    setRunningFailSim(failureType);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/dry-run/simulate-failure`, {
        failure_type: failureType,
      }, { params: { tenant_id: tenantId, property_id: PROPERTY_ID } });
      const label = { timeout: "Timeout", validation_error: "Validation Error", rate_limit: "Rate Limit" }[failureType] || failureType;
      toast.info(`${label} simule edildi`, {
        description: `Correlation: ${res.data?.correlation_id}`,
      });
      fetchDashboard();
    } catch (err) {
      toast.error("Simulasyon hatasi", { description: err.message });
    } finally {
      setRunningFailSim(null);
    }
  };

  const handleTriggerAutoSnapshot = async () => {
    setTriggeringAutoSnapshot(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/automation/trigger`, null, {
        params: { tenant_id: tenantId },
      });
      const score = res.data?.readiness?.overall_score;
      const alerts = res.data?.alerts_generated || 0;
      const chainOk = res.data?.dry_run_chain?.success;
      toast.success("Otomasyon snapshot tamamlandi", {
        description: `Readiness: ${score} | Chain: ${chainOk ? "OK" : "FAIL"} | Alert: ${alerts}`,
      });
      fetchDashboard();
    } catch (err) {
      toast.error("Otomasyon snapshot hatasi", { description: err.message });
    } finally {
      setTriggeringAutoSnapshot(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]" data-testid="ops-dashboard-loading">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-[#C09D63]" />
          <p className="text-sm text-slate-500 font-medium">Ops Dashboard yukleniyor...</p>
        </div>
      </div>
    );
  }

  const ph = data?.provider_health || {};
  const sync = data?.sync_overview || {};
  const m24 = data?.metrics_24h || {};
  const dlq = data?.dlq || {};
  const flags = data?.feature_flags || {};
  const events = data?.recent_events || [];
  const drifts = data?.recent_drifts || [];
  const errTax = data?.error_taxonomy || {};
  const readiness = data?.readiness || {};
  const transition = data?.transition || {};
  const dryRun = data?.dry_run || {};
  const writeCriteria = data?.write_criteria || {};
  const obsReport = observationData || {};
  const obsAlerts = obsReport?.latest_snapshot?.alerts || {};
  const automation = data?.automation || {};
  const autoStatus = automation?.status || {};
  const autoTrends = automation?.trends || {};

  return (
    <TooltipProvider>
      <div data-testid="ops-dashboard" className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
        {/* Header */}
        <div className="sticky top-0 z-20 bg-white/80 backdrop-blur-xl border-b border-slate-100">
          <div className="max-w-[1440px] mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-slate-900 text-white">
                <Radio className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900" style={{ fontFamily: "Manrope, sans-serif" }}>
                  HotelRunner v2 Ops Dashboard
                </h1>
                <p className="text-xs text-slate-500 mt-0.5">
                  Canli connector izleme &bull; Son guncelleme: {formatDateTime(data?.generated_at)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                data-testid="shadow-mode-badge"
                variant="outline"
                className={`text-xs font-semibold px-3 py-1 ${
                  ph.shadow_mode
                    ? "bg-[#C09D63]/10 text-[#C09D63] border-[#C09D63]/30"
                    : "bg-emerald-50 text-emerald-700 border-emerald-200"
                }`}
              >
                <Eye className="w-3 h-3 mr-1" />
                {ph.shadow_mode ? "Shadow Mode" : "Live Mode"}
              </Badge>
              <Button
                data-testid="refresh-dashboard-btn"
                variant="outline"
                size="sm"
                onClick={handleRefresh}
                disabled={refreshing}
                className="text-xs"
              >
                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${refreshing ? "animate-spin" : ""}`} />
                Yenile
              </Button>
            </div>
          </div>
        </div>

        <div className="max-w-[1440px] mx-auto px-6 py-6">
          {/* === BENTO GRID === */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-5">

            {/* ── Transition Phase Bar ── */}
            <Card data-testid="transition-phase-panel" className="md:col-span-12 border-slate-100 shadow-sm">
              <CardContent className="py-4 px-5">
                <div className="flex items-center gap-3 mb-3">
                  <Layers className="w-4 h-4 text-slate-500" />
                  <p className="text-sm font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Write Path Gecis Durumu
                  </p>
                  <Badge variant="outline" className="text-[10px] bg-slate-50 ml-auto">
                    Gun {transition.phase_day || 0}
                  </Badge>
                </div>
                <TransitionPhaseBar currentPhase={transition.current_phase || "shadow"} />
              </CardContent>
            </Card>

            {/* ── Write Readiness Score ── */}
            <Card data-testid="readiness-score-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-[#C09D63]" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Write Readiness Score
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <ReadinessGauge
                  score={readiness.overall_score ?? 0}
                  verdict={readiness.verdict}
                  verdictLabel={readiness.verdict_label || "—"}
                  components={readiness.components}
                />
              </CardContent>
            </Card>
            {/* ── Provider Health Panel ── */}
            <Card data-testid="provider-health-panel" className="md:col-span-8 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-slate-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Provider Sagligi
                    </CardTitle>
                  </div>
                  <Badge variant="outline" className="text-xs bg-slate-50">{ph.connector_version || "v2"}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Status Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Auth</p>
                    <StatusBadge status={ph.auth_status || "unknown"} label={ph.auth_status === "healthy" ? "Healthy" : ph.auth_status === "degraded" ? "Degraded" : ph.auth_status === "error" ? "Failed" : "Bilinmiyor"} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Reservations API</p>
                    <StatusBadge status={ph.reservations_api || "unknown"} label={ph.reservations_api === "healthy" ? "Healthy" : ph.reservations_api === "error" ? "Error" : "Bilinmiyor"} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Shadow Mode</p>
                    <StatusBadge status={ph.shadow_mode ? "on" : "off"} label={ph.shadow_mode ? "Aktif" : "Kapali"} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Write Path</p>
                    <StatusBadge status={ph.write_path === "enabled" ? "enabled" : "disabled"} label={ph.write_path === "enabled" ? "Enabled" : "Disabled"} />
                  </div>
                </div>
                <Separator />
                {/* Key Metrics Row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <MetricCard icon={Clock} label="Son Pull" value={formatTime(sync.last_pull_timestamp)} subtext={formatDateTime(sync.last_pull_timestamp)} />
                  <MetricCard icon={Gauge} label="Ort. Latency" value={data?.avg_latency_ms ? `${data.avg_latency_ms}ms` : "—"} subtext="Son 24 saat" />
                  <MetricCard icon={Inbox} label="DLQ" value={dlq.count ?? 0} color={dlq.count > 0 ? "text-red-600" : "text-emerald-600"} subtext={dlq.count > 0 ? "Dikkat gerekiyor" : "Temiz"} />
                  <MetricCard icon={AlertTriangle} label="Retry Sayisi" value={data?.total_retry_count ?? 0} color={data?.total_retry_count > 0 ? "text-amber-600" : "text-emerald-600"} subtext="Son 24 saat" />
                </div>
              </CardContent>
            </Card>

            {/* ── Operational Actions ── */}
            <Card data-testid="operational-actions-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-[#C09D63]" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Operasyonel Islemler
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  data-testid="test-connection-btn"
                  onClick={handleTestConnection}
                  disabled={testingConnection}
                  className="w-full justify-start bg-slate-900 hover:bg-slate-800 text-white text-sm h-10"
                >
                  {testingConnection ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlugZap className="w-4 h-4 mr-2" />}
                  Baglanti Testi
                </Button>
                <Button
                  data-testid="trigger-reconciliation-btn"
                  onClick={handleReconcile}
                  disabled={triggeringRecon}
                  variant="outline"
                  className="w-full justify-start text-sm h-10 border-slate-200 hover:bg-slate-50"
                >
                  {triggeringRecon ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <GitCompare className="w-4 h-4 mr-2" />}
                  Reconciliation Baslat
                </Button>
                <Button
                  data-testid="refresh-status-btn"
                  onClick={handleRefresh}
                  disabled={refreshing}
                  variant="outline"
                  className="w-full justify-start text-sm h-10 border-slate-200 hover:bg-slate-50"
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
                  Provider Durumu Yenile
                </Button>
                <Button
                  data-testid="collect-snapshot-btn"
                  onClick={handleCollectSnapshot}
                  disabled={collectingSnapshot}
                  variant="outline"
                  className="w-full justify-start text-sm h-10 border-[#C09D63]/30 text-[#C09D63] hover:bg-[#C09D63]/5"
                >
                  {collectingSnapshot ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Calendar className="w-4 h-4 mr-2" />}
                  Gunluk Snapshot Topla
                </Button>
                <Separator />
                {/* Feature Flags Summary */}
                <div className="space-y-2 pt-1">
                  <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Feature Flags</p>
                  <div className="space-y-1.5">
                    {Object.entries(flags).filter(([k]) => !["tenant_id", "updated_at", "provider"].includes(k)).map(([key, val]) => (
                      <div key={key} className="flex items-center justify-between text-xs">
                        <span className="text-slate-600">{key.replace(/_/g, " ")}</span>
                        <span className={`font-medium ${val ? "text-emerald-600" : "text-slate-400"}`}>
                          {val ? "ON" : "OFF"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── Dry-Run Write Path ── */}
            <Card data-testid="dry-run-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FlaskConical className="w-4 h-4 text-indigo-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Dry-Run Kontrol
                    </CardTitle>
                  </div>
                  {dryRun.total_runs > 0 && (
                    <Badge variant="outline" className="text-[10px] bg-indigo-50 text-indigo-600 border-indigo-200">
                      {dryRun.total_runs} calisma
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  data-testid="dry-run-ari-push-btn"
                  onClick={handleDryRunAriPush}
                  disabled={runningDryRun}
                  className="w-full justify-start bg-indigo-600 hover:bg-indigo-700 text-white text-sm h-10"
                >
                  {runningDryRun ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                  Dry-Run ARI Push
                </Button>
                <Button
                  data-testid="dry-run-chain-btn"
                  onClick={handleDryRunChain}
                  disabled={runningChain}
                  variant="outline"
                  className="w-full justify-start text-sm h-10 border-indigo-200 text-indigo-700 hover:bg-indigo-50"
                >
                  {runningChain ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />}
                  Zincir Testi (Create/Modify/Cancel)
                </Button>
                <Separator />
                <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Hata Simulasyonu</p>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { key: "timeout", label: "Timeout", icon: Clock },
                    { key: "validation_error", label: "Validation", icon: Ban },
                    { key: "rate_limit", label: "Rate Limit", icon: CircleSlash },
                  ].map(({ key, label, icon: FIcon }) => (
                    <Button
                      key={key}
                      data-testid={`simulate-${key}-btn`}
                      onClick={() => handleSimulateFailure(key)}
                      disabled={runningFailSim === key}
                      variant="outline"
                      size="sm"
                      className="text-[11px] h-8 border-red-200 text-red-600 hover:bg-red-50"
                    >
                      {runningFailSim === key ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <FIcon className="w-3 h-3 mr-1" />}
                      {label}
                    </Button>
                  ))}
                </div>
                <Separator />
                {/* Dry-run stats summary */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-600">Basari Orani</span>
                    <span className={`font-semibold ${dryRun.success_rate >= 95 ? "text-emerald-600" : dryRun.success_rate >= 70 ? "text-amber-600" : "text-red-600"}`}>
                      {dryRun.total_runs > 0 ? `%${dryRun.success_rate}` : "—"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-600">Basarili / Basarisiz</span>
                    <span className="text-slate-700 font-medium">
                      <span className="text-emerald-600">{dryRun.total_success || 0}</span>
                      <span className="text-slate-400 mx-1">/</span>
                      <span className="text-red-600">{dryRun.total_failed || 0}</span>
                    </span>
                  </div>
                  {dryRun.last_chain && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-600">Son Zincir</span>
                      <span className={`font-medium ${dryRun.last_chain.success ? "text-emerald-600" : "text-red-600"}`}>
                        {dryRun.last_chain.success ? "Basarili" : "Basarisiz"} ({dryRun.last_chain.success_count}/{dryRun.last_chain.step_count})
                      </span>
                    </div>
                  )}
                  {dryRun.last_result && (
                    <div className="mt-2 p-2 rounded-lg bg-slate-50 border border-slate-100">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-slate-500">Son islem</span>
                        <span className={`font-medium ${dryRun.last_result.success ? "text-emerald-600" : "text-red-600"}`}>
                          {dryRun.last_result.operation} — {dryRun.last_result.success ? "OK" : "FAIL"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400 mt-0.5">
                        <span>{dryRun.last_result.correlation_id}</span>
                        <span>{dryRun.last_result.duration_ms}ms</span>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* ── Dry-Run Failure Breakdown ── */}
            <Card data-testid="dry-run-failure-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-500" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Dry-Run Hata Dagilimi
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(dryRun.failure_breakdown || {}).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <Shield className="w-8 h-8 text-emerald-400 mb-2" />
                    <p className="text-sm font-medium text-emerald-700">Hata yok</p>
                    <p className="text-xs text-slate-400 mt-1">Dry-run'da hata kaydedilmedi</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(dryRun.failure_breakdown).map(([cat, count]) => (
                      <div key={cat} className="flex items-center justify-between p-2.5 rounded-lg bg-red-50/50 border border-red-100">
                        <div className="flex items-center gap-2">
                          <XCircle className="w-3.5 h-3.5 text-red-500" />
                          <span className="text-sm text-red-700 font-medium">{cat || "unknown"}</span>
                        </div>
                        <Badge variant="outline" className="text-xs text-red-600 border-red-200 bg-red-50">{count}</Badge>
                      </div>
                    ))}
                    {/* Dry-run per-operation breakdown */}
                    {Object.keys(dryRun.operations || {}).length > 0 && (
                      <>
                        <Separator />
                        <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Islem Bazli</p>
                        {Object.entries(dryRun.operations).map(([op, opData]) => (
                          <div key={op} className="flex items-center justify-between text-xs py-1">
                            <span className="text-slate-600 font-medium">{op}</span>
                            <span>
                              <span className="text-emerald-600">{opData.success}</span>
                              <span className="text-slate-400 mx-0.5">/</span>
                              <span className="text-red-600">{opData.failed}</span>
                              <span className="text-slate-400 ml-1">(%{opData.success_rate})</span>
                            </span>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Write Enable Criteria ── */}
            <Card data-testid="write-criteria-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-slate-700" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Write Acma Kriterleri
                    </CardTitle>
                  </div>
                  <Badge
                    variant="outline"
                    className={`text-[10px] ${
                      writeCriteria.all_met
                        ? "text-emerald-600 border-emerald-200 bg-emerald-50"
                        : "text-amber-600 border-amber-200 bg-amber-50"
                    }`}
                  >
                    {writeCriteria.met_count ?? 0}/{writeCriteria.total_criteria ?? 0}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {(writeCriteria.criteria || []).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <Target className="w-8 h-8 text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Kriter verisi yok</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {(writeCriteria.criteria || []).map((c) => (
                      <div key={c.name} data-testid={`criteria-${c.name}`} className={`flex items-center justify-between p-2 rounded-lg border text-xs ${
                        c.met
                          ? "bg-emerald-50/50 border-emerald-100 text-emerald-700"
                          : "bg-red-50/50 border-red-100 text-red-700"
                      }`}>
                        <div className="flex items-center gap-1.5">
                          {c.met ? <CheckCircle2 className="w-3 h-3 text-emerald-500" /> : <XCircle className="w-3 h-3 text-red-500" />}
                          <span className="font-medium">{c.label}</span>
                        </div>
                        <span className="font-semibold">{typeof c.current_value === 'number' ? c.current_value : c.current_value}</span>
                      </div>
                    ))}
                    {writeCriteria.all_met && (
                      <div className="mt-2 p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-center">
                        <p className="text-xs font-medium text-emerald-700">
                          <CheckCircle2 className="w-3.5 h-3.5 inline mr-1" />
                          Tum kriterler karsilandi — Write acilabilir
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Sync Overview ── */}
            <Card data-testid="sync-overview-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-slate-500" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Senkronizasyon Durumu
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard
                    icon={Database}
                    label="Drift Sayisi"
                    value={sync.drift_count ?? 0}
                    color={sync.drift_count > 0 ? "text-amber-600" : "text-emerald-600"}
                    subtext="Toplam drift"
                  />
                  <MetricCard
                    icon={TrendingUp}
                    label="Islem Basari"
                    value={m24.overall_success_rate ? `%${m24.overall_success_rate}` : "—"}
                    color={m24.overall_success_rate >= 90 ? "text-emerald-600" : "text-amber-600"}
                    subtext={`${m24.total_operations ?? 0} islem (24s)`}
                  />
                  <MetricCard
                    icon={Timer}
                    label="Son Reconciliation"
                    value={formatTime(sync.last_reconciliation?.timestamp)}
                    subtext={sync.last_reconciliation?.mismatch_count != null ? `${sync.last_reconciliation.mismatch_count} mismatch` : "Henuz calismadi"}
                  />
                  <MetricCard
                    icon={BarChart3}
                    label="Toplam Islem"
                    value={m24.total_operations ?? 0}
                    subtext="Son 24 saat"
                  />
                </div>
              </CardContent>
            </Card>

            {/* ── Failure Visibility ── */}
            <Card data-testid="failure-visibility-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-500" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Hata Gorunurlugu
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(errTax).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <Shield className="w-8 h-8 text-emerald-400 mb-2" />
                    <p className="text-sm font-medium text-emerald-700">Hata yok</p>
                    <p className="text-xs text-slate-400 mt-1">Son 24 saatte hata kaydedilmedi</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Hata Taksonomisi (24s)</p>
                    <div className="space-y-2">
                      {Object.entries(errTax).map(([category, count]) => (
                        <div key={category} className="flex items-center justify-between p-2.5 rounded-lg bg-red-50/50 border border-red-100">
                          <div className="flex items-center gap-2">
                            <XCircle className="w-3.5 h-3.5 text-red-500" />
                            <span className="text-sm text-red-700 font-medium">{category || "unknown"}</span>
                          </div>
                          <Badge variant="outline" className="text-xs text-red-600 border-red-200 bg-red-50">{count}</Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* DLQ Section */}
                {dlq.count > 0 && (
                  <div className="mt-4 space-y-2">
                    <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Dead Letter Queue ({dlq.count})</p>
                    {dlq.recent_entries?.slice(0, 3).map((entry, i) => (
                      <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-amber-50/50 border border-amber-100 text-xs">
                        <Inbox className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                        <span className="text-amber-700 truncate">{entry.operation}: {entry.correlation_id}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Recent Events ── */}
            <Card data-testid="recent-events-panel" className="md:col-span-7 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Play className="w-4 h-4 text-slate-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Son Olaylar
                    </CardTitle>
                  </div>
                  <Badge variant="outline" className="text-xs bg-slate-50">{events.length} kayit</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {events.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <Activity className="w-8 h-8 text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Henuz olay kaydedilmedi</p>
                  </div>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {events.map((ev, i) => (
                      <EventRow key={i} event={ev} index={i} />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Recent Drifts ── */}
            <Card data-testid="recent-drifts-panel" className="md:col-span-5 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GitCompare className="w-4 h-4 text-amber-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Son Driftler
                    </CardTitle>
                  </div>
                  <Badge variant="outline" className="text-xs bg-slate-50">{data?.sync_overview?.drift_count ?? 0} toplam</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {drifts.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <CheckCircle2 className="w-8 h-8 text-emerald-400 mb-2" />
                    <p className="text-sm font-medium text-emerald-700">Drift yok</p>
                    <p className="text-xs text-slate-400 mt-1">PMS ve HotelRunner senkronize</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {drifts.slice(0, 8).map((d, i) => (
                      <div key={i} className="p-2.5 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-slate-700">{d.case_type}</span>
                          <Badge
                            variant="outline"
                            className={`text-[10px] ${
                              d.severity === "high" ? "text-red-600 border-red-200 bg-red-50" :
                              d.severity === "medium" ? "text-amber-600 border-amber-200 bg-amber-50" :
                              "text-slate-500 border-slate-200 bg-slate-50"
                            }`}
                          >
                            {d.severity}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-500 mt-1 truncate">{d.description}</p>
                        <p className="text-[10px] text-slate-400 mt-0.5">{d.external_reservation_id}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Operations Breakdown ── */}
            <Card data-testid="operations-breakdown-panel" className="md:col-span-12 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-slate-500" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Islem Detaylari (24 Saat)
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(m24.operations || {}).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <BarChart3 className="w-8 h-8 text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Henuz islem verisi yok</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="operations-table">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-left py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Islem</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Toplam</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Basarili</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Basarisiz</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Basari %</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Ort. Latency</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Max Latency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(m24.operations || {}).map(([opName, opData]) => (
                          <tr key={opName} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                            <td className="py-2.5 px-3 font-medium text-slate-700">{opName}</td>
                            <td className="py-2.5 px-3 text-right text-slate-600">{opData.total}</td>
                            <td className="py-2.5 px-3 text-right text-emerald-600">{opData.success}</td>
                            <td className="py-2.5 px-3 text-right text-red-600">{opData.failed}</td>
                            <td className="py-2.5 px-3 text-right">
                              <span className={`font-medium ${opData.success_rate >= 90 ? "text-emerald-600" : opData.success_rate >= 50 ? "text-amber-600" : "text-red-600"}`}>
                                %{opData.success_rate}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-right text-slate-600">{opData.avg_latency_ms}ms</td>
                            <td className="py-2.5 px-3 text-right text-slate-500">{opData.max_latency_ms}ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Shadow Observation Alerts ── */}
            <Card data-testid="observation-alerts-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Alert Durumu
                    </CardTitle>
                  </div>
                  {obsReport?.latest_snapshot?.alert_summary && (
                    <div className="flex items-center gap-1.5">
                      {obsReport.latest_snapshot.alert_summary.critical_count > 0 && (
                        <Badge variant="outline" className="text-[10px] text-red-600 border-red-200 bg-red-50">
                          {obsReport.latest_snapshot.alert_summary.critical_count} critical
                        </Badge>
                      )}
                      {obsReport.latest_snapshot.alert_summary.warn_count > 0 && (
                        <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-200 bg-amber-50">
                          {obsReport.latest_snapshot.alert_summary.warn_count} warn
                        </Badge>
                      )}
                      {obsReport.latest_snapshot.alert_summary.critical_count === 0 && obsReport.latest_snapshot.alert_summary.warn_count === 0 && (
                        <Badge variant="outline" className="text-[10px] text-emerald-600 border-emerald-200 bg-emerald-50">
                          Temiz
                        </Badge>
                      )}
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(obsAlerts).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <Calendar className="w-8 h-8 text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Henuz snapshot verisi yok</p>
                    <p className="text-xs text-slate-400 mt-1">Ilk snapshot'i toplamak icin "Gunluk Snapshot Topla" butonunu kullanin</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(obsAlerts).map(([name, alert]) => (
                      <AlertItem key={name} name={name} alert={alert} />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Observation History (7 Days) ── */}
            <Card data-testid="observation-history-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-slate-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Gozlem Gecmisi
                    </CardTitle>
                  </div>
                  {obsReport?.observation_day > 0 && (
                    <Badge variant="outline" className="text-[10px] bg-slate-50">
                      Gun {obsReport.observation_day} / {obsReport.observation_target || 7}
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {(!obsReport?.history_summary || obsReport.history_summary.length === 0) ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <BarChart3 className="w-8 h-8 text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Henuz gozlem verisi yok</p>
                    <p className="text-xs text-slate-400 mt-1">7 gunluk gozlem sureci baslatilmadi</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs" data-testid="observation-history-table">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-left py-2 px-2 font-medium text-slate-500">Gun</th>
                          <th className="text-right py-2 px-2 font-medium text-slate-500">Islem</th>
                          <th className="text-right py-2 px-2 font-medium text-slate-500">Hata %</th>
                          <th className="text-right py-2 px-2 font-medium text-slate-500">Drift</th>
                          <th className="text-right py-2 px-2 font-medium text-slate-500">Latency</th>
                          <th className="text-right py-2 px-2 font-medium text-slate-500">Alert</th>
                        </tr>
                      </thead>
                      <tbody>
                        {obsReport.history_summary.map((row, i) => (
                          <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                            <td className="py-2 px-2 font-medium text-slate-700">{row.day}</td>
                            <td className="py-2 px-2 text-right text-slate-600">{row.total_ops}</td>
                            <td className="py-2 px-2 text-right">
                              <span className={row.error_rate > 5 ? "text-red-600" : "text-emerald-600"}>
                                %{row.error_rate}
                              </span>
                            </td>
                            <td className="py-2 px-2 text-right">
                              <span className={row.drift_count > 0 ? "text-amber-600" : "text-emerald-600"}>
                                {row.drift_count}
                              </span>
                            </td>
                            <td className="py-2 px-2 text-right text-slate-600">{row.avg_latency}ms</td>
                            <td className="py-2 px-2 text-right">
                              {row.alerts_critical > 0 ? (
                                <span className="text-red-600 font-medium">{row.alerts_critical}C</span>
                              ) : row.alerts_warn > 0 ? (
                                <span className="text-amber-600">{row.alerts_warn}W</span>
                              ) : (
                                <span className="text-emerald-600">OK</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {obsReport.observation_complete && (
                      <div className="mt-3 p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-center">
                        <p className="text-xs font-medium text-emerald-700">
                          <CheckCircle2 className="w-3.5 h-3.5 inline mr-1" />
                          7 gunluk gozlem tamamlandi
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Shadow Automation Status ── */}
            <Card data-testid="automation-status-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Radio className="w-4 h-4 text-teal-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Shadow Otomasyon
                    </CardTitle>
                  </div>
                  <Badge variant="outline" className="text-[10px] text-teal-600 border-teal-200 bg-teal-50">
                    Aktif
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  data-testid="trigger-auto-snapshot-btn"
                  onClick={handleTriggerAutoSnapshot}
                  disabled={triggeringAutoSnapshot}
                  className="w-full justify-start bg-teal-600 hover:bg-teal-700 text-white text-sm h-10"
                >
                  {triggeringAutoSnapshot ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Zap className="w-4 h-4 mr-2" />}
                  Manuel Snapshot Tetikle
                </Button>
                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Snapshot Periyodu</span>
                    <span className="text-slate-700 font-medium">6 saat</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Gunluk Ozet</span>
                    <span className="text-slate-700 font-medium">00:00 UTC</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Son 24s Snapshot</span>
                    <span className="text-slate-700 font-semibold">{autoStatus.snapshots_24h ?? 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Aktif Alert</span>
                    <span className={`font-semibold ${(autoStatus.active_alerts || 0) > 0 ? "text-red-600" : "text-emerald-600"}`}>
                      {autoStatus.active_alerts ?? 0}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Alert (24s)</span>
                    <span className={`font-semibold ${(autoStatus.alerts_24h || 0) > 0 ? "text-amber-600" : "text-emerald-600"}`}>
                      {autoStatus.alerts_24h ?? 0}
                    </span>
                  </div>
                </div>
                <Separator />
                {autoStatus.last_snapshot ? (
                  <div className="p-2.5 rounded-lg bg-teal-50/50 border border-teal-100">
                    <p className="text-[11px] text-teal-700 font-medium">Son Snapshot</p>
                    <div className="flex items-center justify-between text-[10px] text-teal-600 mt-1">
                      <span>Readiness: {autoStatus.last_snapshot.readiness_score ?? "—"}</span>
                      <span>Chain: {autoStatus.last_snapshot.chain_success === true ? "OK" : autoStatus.last_snapshot.chain_success === false ? "FAIL" : "—"}</span>
                    </div>
                    <p className="text-[10px] text-teal-500 mt-0.5">{formatDateTime(autoStatus.last_snapshot.created_at)}</p>
                  </div>
                ) : (
                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-center">
                    <p className="text-xs text-slate-400">Henuz snapshot yok</p>
                  </div>
                )}
                {autoStatus.last_daily_summary && (
                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                    <p className="text-[11px] text-slate-600 font-medium">Son Gunluk Ozet</p>
                    <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1">
                      <span>Tarih: {autoStatus.last_daily_summary.date}</span>
                      <span>
                        Score: {autoStatus.last_daily_summary.readiness_score ?? "—"}
                        {autoStatus.last_daily_summary.score_change != null && (
                          <span className={autoStatus.last_daily_summary.score_change > 0 ? "text-emerald-600 ml-1" : autoStatus.last_daily_summary.score_change < 0 ? "text-red-600 ml-1" : "text-slate-400 ml-1"}>
                            ({autoStatus.last_daily_summary.score_change > 0 ? "+" : ""}{autoStatus.last_daily_summary.score_change})
                          </span>
                        )}
                      </span>
                    </div>
                  </div>
                )}
                <div className="space-y-1.5 pt-1">
                  <p className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">Retention</p>
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-500">Ham snapshot</span>
                    <span className="text-slate-600">30 gun</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-500">Gunluk ozetler</span>
                    <span className="text-slate-600">90 gun</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── Trend Panels (Readiness, Drift, Latency, Failure) ── */}
            <Card data-testid="trend-readiness-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-emerald-500" />
                  <CardTitle className="text-sm font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Readiness Trend
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {(autoTrends.readiness_trend || []).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-6 text-center">
                    <TrendingUp className="w-6 h-6 text-slate-300 mb-1" />
                    <p className="text-xs text-slate-400">Veri bekleniyor</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-end gap-1 h-24">
                      {(autoTrends.readiness_trend || []).map((p, i) => {
                        const h = Math.max(4, (p.score / 100) * 100);
                        const color = p.score >= 90 ? "bg-emerald-400" : p.score >= 70 ? "bg-amber-400" : "bg-red-400";
                        return (
                          <Tooltip key={i}>
                            <TooltipTrigger asChild>
                              <div
                                data-testid={`readiness-bar-${i}`}
                                className={`flex-1 rounded-t-sm ${color} transition-all hover:opacity-80 cursor-pointer`}
                                style={{ height: `${h}%`, minWidth: "6px" }}
                              />
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                              <p className="font-medium">{p.time}</p>
                              <p>Score: {p.score}</p>
                            </TooltipContent>
                          </Tooltip>
                        );
                      })}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400">
                      <span>{(autoTrends.readiness_trend || [])[0]?.time || ""}</span>
                      <span>{(autoTrends.readiness_trend || []).at(-1)?.time || ""}</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card data-testid="trend-drift-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <GitCompare className="w-4 h-4 text-amber-500" />
                  <CardTitle className="text-sm font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Drift Trend
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {(autoTrends.drift_trend || []).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-6 text-center">
                    <TrendingUp className="w-6 h-6 text-slate-300 mb-1" />
                    <p className="text-xs text-slate-400">Veri bekleniyor</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-end gap-1 h-24">
                      {(autoTrends.drift_trend || []).map((p, i) => {
                        const maxDrift = Math.max(1, ...autoTrends.drift_trend.map(x => x.count));
                        const h = Math.max(4, (p.count / maxDrift) * 100);
                        const color = p.count === 0 ? "bg-emerald-400" : p.count < 5 ? "bg-amber-400" : "bg-red-400";
                        return (
                          <Tooltip key={i}>
                            <TooltipTrigger asChild>
                              <div
                                data-testid={`drift-bar-${i}`}
                                className={`flex-1 rounded-t-sm ${color} transition-all hover:opacity-80 cursor-pointer`}
                                style={{ height: `${h}%`, minWidth: "6px" }}
                              />
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                              <p className="font-medium">{p.time}</p>
                              <p>Drift: {p.count}</p>
                            </TooltipContent>
                          </Tooltip>
                        );
                      })}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400">
                      <span>{(autoTrends.drift_trend || [])[0]?.time || ""}</span>
                      <span>{(autoTrends.drift_trend || []).at(-1)?.time || ""}</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Latency Trend ── */}
            <Card data-testid="trend-latency-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <Timer className="w-4 h-4 text-blue-500" />
                  <CardTitle className="text-sm font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Latency Trend
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {(autoTrends.latency_trend || []).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-6 text-center">
                    <TrendingUp className="w-6 h-6 text-slate-300 mb-1" />
                    <p className="text-xs text-slate-400">Veri bekleniyor</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-end gap-1 h-24">
                      {(autoTrends.latency_trend || []).map((p, i) => {
                        const maxLat = Math.max(1, ...autoTrends.latency_trend.map(x => x.avg_ms));
                        const h = Math.max(4, (p.avg_ms / maxLat) * 100);
                        const color = p.avg_ms <= 1000 ? "bg-blue-400" : p.avg_ms <= 3000 ? "bg-amber-400" : "bg-red-400";
                        return (
                          <Tooltip key={i}>
                            <TooltipTrigger asChild>
                              <div
                                data-testid={`latency-bar-${i}`}
                                className={`flex-1 rounded-t-sm ${color} transition-all hover:opacity-80 cursor-pointer`}
                                style={{ height: `${h}%`, minWidth: "6px" }}
                              />
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                              <p className="font-medium">{p.time}</p>
                              <p>Latency: {p.avg_ms}ms</p>
                            </TooltipContent>
                          </Tooltip>
                        );
                      })}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400">
                      <span>{(autoTrends.latency_trend || [])[0]?.time || ""}</span>
                      <span>{(autoTrends.latency_trend || []).at(-1)?.time || ""}</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Failure Trend ── */}
            <Card data-testid="trend-failure-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-500" />
                  <CardTitle className="text-sm font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Failure Trend
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {(autoTrends.failure_trend || []).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-6 text-center">
                    <TrendingUp className="w-6 h-6 text-slate-300 mb-1" />
                    <p className="text-xs text-slate-400">Veri bekleniyor</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-end gap-1 h-24">
                      {(autoTrends.failure_trend || []).map((p, i) => {
                        const maxRate = Math.max(1, ...autoTrends.failure_trend.map(x => x.error_rate));
                        const h = maxRate > 0 ? Math.max(4, (p.error_rate / maxRate) * 100) : 4;
                        const color = p.error_rate === 0 ? "bg-emerald-400" : p.error_rate < 5 ? "bg-amber-400" : "bg-red-400";
                        return (
                          <Tooltip key={i}>
                            <TooltipTrigger asChild>
                              <div
                                data-testid={`failure-bar-${i}`}
                                className={`flex-1 rounded-t-sm ${color} transition-all hover:opacity-80 cursor-pointer`}
                                style={{ height: `${h}%`, minWidth: "6px" }}
                              />
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                              <p className="font-medium">{p.time}</p>
                              <p>Hata: %{p.error_rate} ({p.fail_count} adet)</p>
                            </TooltipContent>
                          </Tooltip>
                        );
                      })}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400">
                      <span>{(autoTrends.failure_trend || [])[0]?.time || ""}</span>
                      <span>{(autoTrends.failure_trend || []).at(-1)?.time || ""}</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
