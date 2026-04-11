import { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import {
  Activity, Zap, AlertTriangle, RefreshCw, CheckCircle, XCircle,
  TrendingUp, TrendingDown, Minus, Shield, Clock, BarChart3, Gauge,
  ArrowUpRight, ArrowDownRight, Target, Wrench, Timer, Eye,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";

const PERIOD_OPTIONS = [
  { label: "24s", value: 24 },
  { label: "3g", value: 72 },
  { label: "7g", value: 168 },
  { label: "30g", value: 720 },
];

const SLA_LABELS = {
  compliant: { text: "UYUMLU", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
  warning: { text: "UYARI", cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30" },
  breached: { text: "IHLAL", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
};

const FAILURE_COLORS = {
  timeout: "#f59e0b", validation_error: "#ef4444", provider_rejected: "#f97316",
  auth_error: "#dc2626", rate_limited: "#a855f7", provider_unavailable: "#6366f1", unknown: "#6b7280",
};

const FAILURE_LABELS = {
  timeout: "Timeout", validation_error: "Validasyon", provider_rejected: "Provider Red",
  auth_error: "Auth Hatasi", rate_limited: "Rate Limit", provider_unavailable: "Provider Down", unknown: "Bilinmiyor",
};

const CHART_COLORS = { p50: "#10b981", p95: "#f59e0b", p99: "#ef4444", sync: "#3b82f6", drift: "#f97316", retry: "#a855f7", failures: "#ef4444" };

function formatBucketTime(ts) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleString("tr-TR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return ts; }
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-zinc-500 mb-1">{formatBucketTime(label)}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-zinc-400">{p.name}:</span>
          <span className="text-zinc-100 font-mono font-medium">{typeof p.value === "number" ? p.value.toLocaleString("tr-TR") : p.value}{p.unit === "ms" ? "ms" : p.unit === "%" ? "%" : ""}</span>
        </div>
      ))}
    </div>
  );
}

function FieldKPICard({ icon, label, kpi, invertTrend, testId }) {
  const val = kpi?.current ?? 0;
  const prev = kpi?.previous ?? 0;
  const delta = kpi?.delta ?? 0;
  const unit = kpi?.unit ?? "";
  const trend = kpi?.trend ?? "flat";

  const isPositive = invertTrend ? trend === "down" : trend === "up";
  const isNegative = invertTrend ? trend === "up" : trend === "down";

  const trendIcon = trend === "up" ? <ArrowUpRight className="h-3 w-3" /> : trend === "down" ? <ArrowDownRight className="h-3 w-3" /> : <Minus className="h-3 w-3" />;
  const trendColor = isPositive ? "text-emerald-400" : isNegative ? "text-red-400" : "text-zinc-500";
  const borderColor = isPositive ? "border-emerald-500/20" : isNegative ? "border-red-500/20" : "border-zinc-800";

  return (
    <div className={`bg-zinc-900/80 border ${borderColor} rounded-xl p-5 transition-all hover:border-zinc-600`} data-testid={testId}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">{icon}</span>
          <span className="text-xs text-zinc-500 font-medium">{label}</span>
        </div>
        <div className={`flex items-center gap-1 text-xs font-mono ${trendColor}`}>
          {trendIcon}
          <span>{delta > 0 ? "+" : ""}{delta}{unit === "%" || unit === "saat" ? unit : ""}</span>
        </div>
      </div>
      <div className="text-2xl font-bold font-mono text-zinc-100">{val}{unit === "%" ? "%" : ""}<span className="text-sm text-zinc-600 ml-1">{unit !== "%" ? unit : ""}</span></div>
      <div className="text-[10px] text-zinc-600 mt-1.5 font-mono">onceki donem: {prev}{unit === "%" ? "%" : ` ${unit}`}</div>
    </div>
  );
}

function LatencyTrendChart({ data }) {
  if (!data?.length) return <EmptyChart label="Push latency trend verisi yok" />;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="timestamp" tickFormatter={formatBucketTime} tick={{ fontSize: 10, fill: "#71717a" }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10, fill: "#71717a" }} tickFormatter={(v) => `${v}ms`} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        <Line type="monotone" dataKey="push_latency.p50" name="p50" stroke={CHART_COLORS.p50} strokeWidth={2} dot={false} unit="ms" />
        <Line type="monotone" dataKey="push_latency.p95" name="p95" stroke={CHART_COLORS.p95} strokeWidth={2} dot={false} unit="ms" />
        <Line type="monotone" dataKey="push_latency.p99" name="p99" stroke={CHART_COLORS.p99} strokeWidth={2} dot={false} unit="ms" />
      </LineChart>
    </ResponsiveContainer>
  );
}

function SyncDriftChart({ data }) {
  if (!data?.length) return <EmptyChart label="Sync/drift trend verisi yok" />;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="timestamp" tickFormatter={formatBucketTime} tick={{ fontSize: 10, fill: "#71717a" }} interval="preserveStartEnd" />
        <YAxis yAxisId="left" tick={{ fontSize: 10, fill: "#71717a" }} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: "#71717a" }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        <Area yAxisId="left" type="monotone" dataKey="sync.success_rate" name="Sync Basari %" stroke={CHART_COLORS.sync} fill={CHART_COLORS.sync} fillOpacity={0.1} strokeWidth={2} dot={false} unit="%" />
        <Area yAxisId="right" type="monotone" dataKey="drift_created" name="Yeni Drift" stroke={CHART_COLORS.drift} fill={CHART_COLORS.drift} fillOpacity={0.1} strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function RetryFailureChart({ data }) {
  if (!data?.length) return <EmptyChart label="Retry/failure trend verisi yok" />;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="timestamp" tickFormatter={formatBucketTime} tick={{ fontSize: 10, fill: "#71717a" }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10, fill: "#71717a" }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        <Bar dataKey="failures" name="Hatalar" fill={CHART_COLORS.failures} radius={[2, 2, 0, 0]} />
        <Bar dataKey="retry.total" name="Retry" fill={CHART_COLORS.retry} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function EmptyChart({ label }) {
  return (
    <div className="flex items-center justify-center h-48 text-xs text-zinc-600">
      <BarChart3 className="h-5 w-5 mr-2 opacity-30" />{label}
    </div>
  );
}

function FailureBreakdownBar({ data }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  if (total === 0) return <div className="text-center py-4 text-zinc-600 text-xs" data-testid="failure-breakdown-empty">Hata kaydi yok</div>;
  const sorted = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <div className="space-y-2" data-testid="failure-breakdown-chart">
      <div className="h-6 bg-zinc-800 rounded-lg overflow-hidden flex">
        {sorted.map(([key, count]) => (
          <div key={key} className="h-full transition-all duration-700 first:rounded-l-lg last:rounded-r-lg"
            style={{ width: `${(count / total) * 100}%`, backgroundColor: FAILURE_COLORS[key] || "#6b7280" }}
            title={`${FAILURE_LABELS[key] || key}: ${count} (${((count / total) * 100).toFixed(1)}%)`} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {sorted.map(([key, count]) => (
          <div key={key} className="flex items-center gap-1.5 text-[10px]">
            <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: FAILURE_COLORS[key] || "#6b7280" }} />
            <span className="text-zinc-400">{FAILURE_LABELS[key] || key}</span>
            <span className="text-zinc-600 font-mono">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProviderSLACard({ provider, sla }) {
  const status = SLA_LABELS[sla.overall] || SLA_LABELS.warning;
  const checks = [
    { label: "Push Latency p95", value: `${sla.push_latency_p95_ms}ms`, target: `<${sla.push_latency_target_ms}ms`, ok: sla.push_latency_ok },
    { label: "Sync Basari", value: `${sla.sync_success_rate}%`, target: `>${sla.sync_target}%`, ok: sla.sync_ok },
    { label: "Retry Basari", value: `${sla.retry_success_rate}%`, target: `>${sla.retry_target}%`, ok: sla.retry_ok },
  ];
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4" data-testid={`sla-card-${provider}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-zinc-500" />
          <span className="text-sm font-medium text-zinc-200 capitalize">{provider}</span>
        </div>
        <Badge variant="outline" className={`text-xs border ${status.cls}`}>{status.text}</Badge>
      </div>
      <div className="space-y-2">
        {checks.map(({ label, value, target, ok }) => (
          <div key={label} className="flex items-center justify-between text-xs">
            <span className="text-zinc-500">{label}</span>
            <div className="flex items-center gap-2">
              <span className="text-zinc-400 font-mono text-[10px]">{target}</span>
              <span className={`font-mono font-medium ${ok ? "text-emerald-400" : "text-red-400"}`}>{value}</span>
              {ok ? <CheckCircle className="h-3 w-3 text-emerald-500" /> : <XCircle className="h-3 w-3 text-red-500" />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function KPISummaryCard({ icon, label, value, sub, ok, testId }) {
  return (
    <div className={`bg-zinc-900 border rounded-lg p-4 transition-colors ${ok ? "border-zinc-800" : "border-red-500/30 bg-red-500/5"}`} data-testid={testId}>
      <div className="flex items-center gap-2 mb-2">
        <span className={ok ? "text-zinc-500" : "text-red-400"}>{icon}</span>
        <span className="text-xs text-zinc-500">{label}</span>
      </div>
      <div className={`text-xl font-bold font-mono ${ok ? "text-zinc-100" : "text-red-400"}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-600 mt-1 font-mono">{sub}</div>}
    </div>
  );
}

function DriftCard({ provider, drift }) {
  const byType = drift.by_type || {};
  const total = drift.total || 0;
  const severity = total >= 50 ? "critical" : total >= 10 ? "warning" : "ok";
  const borderCls = severity === "critical" ? "border-red-500/30" : severity === "warning" ? "border-yellow-500/30" : "border-zinc-800";
  return (
    <div className={`bg-zinc-900 border ${borderCls} rounded-lg p-4`} data-testid={`drift-card-${provider}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-zinc-200 capitalize">{provider}</span>
        <span className={`text-xl font-bold font-mono ${severity === "critical" ? "text-red-400" : severity === "warning" ? "text-yellow-400" : "text-emerald-400"}`}>{total}</span>
      </div>
      {Object.keys(byType).length > 0 ? (
        <div className="grid grid-cols-2 gap-1">
          {Object.entries(byType).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([type, count]) => (
            <div key={type} className="flex items-center justify-between text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800/50">
              <span className="text-zinc-500 truncate">{type.replace(/_/g, " ")}</span>
              <span className="text-zinc-300 ml-1">{count}</span>
            </div>
          ))}
        </div>
      ) : <div className="text-xs text-zinc-600">Drift yok</div>}
    </div>
  );
}

export function ChannelHealth() {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [trends, setTrends] = useState(null);
  const [fieldKpis, setFieldKpis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(async (showToast = false) => {
    try {
      const [healthRes, trendsRes, kpisRes] = await Promise.all([
        axios.get(`/ops/dashboard/channel-health?hours=${hours}`),
        axios.get(`/ops/dashboard/channel-health/trends?hours=${Math.min(hours * 7, 720)}`),
        axios.get(`/ops/dashboard/channel-health/field-kpis?period_hours=${hours}`),
      ]);
      setData(healthRes.data);
      setTrends(trendsRes.data);
      setFieldKpis(kpisRes.data);
      if (showToast) toast.success("Kanal sagligi guncellendi");
    } catch (err) {
      toast.error("Kanal sagligi yuklenemedi", { description: err.response?.data?.detail || err.message });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [hours]);

  useEffect(() => {
    setLoading(true);
    fetchAll();
    const interval = setInterval(() => fetchAll(), 60000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleRefresh = () => { setRefreshing(true); fetchAll(true); };

  if (loading) {
    return (
      <div className="space-y-4" data-testid="channel-health-loading">
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-28 bg-zinc-800" />)}</div>
        <Skeleton className="h-64 bg-zinc-800" />
        <Skeleton className="h-48 bg-zinc-800" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-16 text-zinc-500" data-testid="channel-health-empty">
        <Activity className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Kanal sagligi verisi bulunamadi</p>
      </div>
    );
  }

  const latency = data.push_latency || {};
  const syncM = data.sync_metrics || {};
  const failures = data.failure_breakdown || {};
  const drift = data.reconciliation_drift || {};
  const retries = data.retry_metrics || {};
  const providerSla = data.provider_sla || {};
  const overallLatency = latency.overall || {};
  const overallSync = syncM.overall || {};
  const overallRetry = retries.overall || {};
  const allProviders = [...new Set([
    ...Object.keys(latency.by_provider || {}),
    ...Object.keys(syncM.by_provider || {}),
    ...Object.keys(drift.by_provider || {}),
    ...Object.keys(data.provider_summary || {}),
  ])].filter(p => p !== "unknown");

  const trendBuckets = trends?.buckets || [];
  const fk = fieldKpis || {};

  return (
    <div className="space-y-6" data-testid="channel-health-dashboard">
      {/* ── Header + Controls ─────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-zinc-400 font-mono">
            Son {data.period_hours} saat · {new Date(data.calculated_at).toLocaleTimeString("tr-TR")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-zinc-900 border border-zinc-800 rounded-lg p-0.5" data-testid="period-selector">
            {PERIOD_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => setHours(opt.value)}
                className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${hours === opt.value ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}
                data-testid={`period-${opt.value}`}>{opt.label}</button>
            ))}
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs text-zinc-500" onClick={handleRefresh} disabled={refreshing} data-testid="channel-health-refresh">
            <RefreshCw className={`h-3 w-3 mr-1 ${refreshing ? "animate-spin" : ""}`} />Yenile
          </Button>
        </div>
      </div>

      {/* ── Field KPIs — Saha Performansi ────────────────── */}
      <div>
        <h2 className="text-xs text-zinc-500 uppercase tracking-widest font-medium mb-3 flex items-center gap-2">
          <Target className="h-3.5 w-3.5" /> Saha Performans KPI
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="field-kpis-grid">
          <FieldKPICard icon={<TrendingUp className="h-4 w-4" />} label="Sync Basari Orani" kpi={fk.sync_success} testId="fkpi-sync-success" />
          <FieldKPICard icon={<AlertTriangle className="h-4 w-4" />} label="Drift Sayisi" kpi={fk.drift_reduction} invertTrend testId="fkpi-drift" />
          <FieldKPICard icon={<Timer className="h-4 w-4" />} label="MTTR" kpi={fk.mttr_hours} invertTrend testId="fkpi-mttr" />
          <FieldKPICard icon={<Wrench className="h-4 w-4" />} label="Operator Mudahale" kpi={fk.operator_interventions} invertTrend testId="fkpi-operator" />
          <FieldKPICard icon={<Shield className="h-4 w-4" />} label="Push SLA Uyum" kpi={fk.push_sla_compliance} testId="fkpi-push-sla" />
        </div>
      </div>

      {/* ── KPI Summary Strip ────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPISummaryCard icon={<Gauge className="h-4 w-4" />} label="Push Latency p95" value={`${overallLatency.p95 || 0}ms`} sub={`p50: ${overallLatency.p50 || 0}ms · p99: ${overallLatency.p99 || 0}ms`} ok={(overallLatency.p95 || 0) <= 5000} testId="kpi-push-latency" />
        <KPISummaryCard icon={<TrendingUp className="h-4 w-4" />} label="Sync Basari" value={`${overallSync.success_rate ?? 100}%`} sub={`${overallSync.completed || 0}/${overallSync.total || 0} basarili`} ok={(overallSync.success_rate ?? 100) >= 95} testId="kpi-sync-success" />
        <KPISummaryCard icon={<AlertTriangle className="h-4 w-4" />} label="Drift Sayisi" value={drift.total_open || 0} sub={`${allProviders.length} provider`} ok={(drift.total_open || 0) < 10} testId="kpi-drift-count" />
        <KPISummaryCard icon={<Zap className="h-4 w-4" />} label="Retry Basari" value={`${overallRetry.retry_success_rate ?? 0}%`} sub={`${overallRetry.retried_success || 0}/${overallRetry.total_retried || 0}`} ok={(overallRetry.retry_success_rate ?? 100) >= 80} testId="kpi-retry-success" />
      </div>

      {/* ── Historical Trends ────────────────────────────── */}
      <div>
        <h2 className="text-xs text-zinc-500 uppercase tracking-widest font-medium mb-3 flex items-center gap-2">
          <Eye className="h-3.5 w-3.5" /> Tarihsel Trendler
          {trendBuckets.length > 0 && <Badge variant="outline" className="text-zinc-600 border-zinc-700 text-[10px]">{trendBuckets.length} bucket</Badge>}
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                <Clock className="h-4 w-4 text-zinc-500" /> Push Latency Trendi
              </CardTitle>
            </CardHeader>
            <CardContent data-testid="chart-latency-trend">
              <LatencyTrendChart data={trendBuckets} />
            </CardContent>
          </Card>
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                <Activity className="h-4 w-4 text-zinc-500" /> Sync Basari & Drift Trendi
              </CardTitle>
            </CardHeader>
            <CardContent data-testid="chart-sync-drift-trend">
              <SyncDriftChart data={trendBuckets} />
            </CardContent>
          </Card>
        </div>
        <div className="mt-4">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-zinc-500" /> Hata & Retry Hacmi
              </CardTitle>
            </CardHeader>
            <CardContent data-testid="chart-retry-failure-trend">
              <RetryFailureChart data={trendBuckets} />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ── Current Period Detail ─────────────────────────── */}
      <div>
        <h2 className="text-xs text-zinc-500 uppercase tracking-widest font-medium mb-3 flex items-center gap-2">
          <Gauge className="h-3.5 w-3.5" /> Mevcut Donem Detay
        </h2>

        {/* Failure Breakdown */}
        <Card className="bg-zinc-900 border-zinc-800 mb-4">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-zinc-500" /> Hata Dagilimi
              {(failures.total_failures || 0) > 0 && (
                <Badge variant="outline" className="text-red-400 border-red-500/30 text-[10px] ml-2">{failures.total_failures} hata</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <FailureBreakdownBar data={failures.overall || {}} />
            {Object.entries(failures.by_provider || {}).filter(([k]) => k !== "unknown").map(([provider, pData]) => (
              <div key={provider} className="mt-3 pt-3 border-t border-zinc-800">
                <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-2 capitalize">{provider}</div>
                <FailureBreakdownBar data={pData} />
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Drift + SLA row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                <TrendingDown className="h-4 w-4 text-zinc-500" /> Reconciliation Drift
                <Badge variant="outline" className={`text-[10px] ml-auto border ${(drift.total_open || 0) >= 50 ? "text-red-400 border-red-500/30" : (drift.total_open || 0) >= 10 ? "text-yellow-400 border-yellow-500/30" : "text-emerald-400 border-emerald-500/30"}`}>{drift.total_open || 0} acik</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(drift.by_provider || {}).filter(([k]) => k !== "unknown").map(([provider, pDrift]) => (
                <DriftCard key={provider} provider={provider} drift={pDrift} />
              ))}
              {Object.keys(drift.by_provider || {}).filter(k => k !== "unknown").length === 0 && (
                <div className="text-xs text-zinc-600 text-center py-4">Drift verisi yok</div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                <Shield className="h-4 w-4 text-zinc-500" /> Provider SLA
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(providerSla).filter(([k]) => k !== "unknown").map(([provider, sla]) => (
                <ProviderSLACard key={provider} provider={provider} sla={sla} />
              ))}
              {Object.keys(providerSla).filter(k => k !== "unknown").length === 0 && (
                <div className="text-xs text-zinc-600 text-center py-4">SLA verisi yok</div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ── Provider Sync Detail ─────────────────────────── */}
      {Object.entries(syncM.by_provider || {}).filter(([k]) => k !== "unknown").length > 0 && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <Activity className="h-4 w-4 text-zinc-500" /> Provider Sync Detay
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {Object.entries(syncM.by_provider || {}).filter(([k]) => k !== "unknown").map(([provider, pSync]) => (
                <div key={provider} className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/30" data-testid={`sync-detail-${provider}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-zinc-300 capitalize">{provider}</span>
                    <span className={`text-sm font-bold font-mono ${pSync.success_rate >= 95 ? "text-emerald-400" : pSync.success_rate >= 80 ? "text-yellow-400" : "text-red-400"}`}>{pSync.success_rate}%</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
                    <div><div className="text-zinc-600">Toplam</div><div className="text-zinc-300">{pSync.total}</div></div>
                    <div><div className="text-zinc-600">Basarili</div><div className="text-emerald-400">{pSync.completed}</div></div>
                    <div><div className="text-zinc-600">Basarisiz</div><div className="text-red-400">{pSync.failed}</div></div>
                  </div>
                  <div className="text-[10px] text-zinc-600 mt-1 font-mono">avg duration: {pSync.avg_duration_ms}ms</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
