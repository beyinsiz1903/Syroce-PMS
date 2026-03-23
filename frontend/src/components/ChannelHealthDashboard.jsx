import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  Activity, Zap, AlertTriangle, RefreshCw, CheckCircle, XCircle,
  TrendingUp, TrendingDown, Shield, Clock, BarChart3, Gauge
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";

const SLA_LABELS = {
  compliant: { text: "UYUMLU", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
  warning: { text: "UYARI", cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30" },
  breached: { text: "IHLAL", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
};

const FAILURE_COLORS = {
  timeout: "#f59e0b",
  validation_error: "#ef4444",
  provider_rejected: "#f97316",
  auth_error: "#dc2626",
  rate_limited: "#a855f7",
  provider_unavailable: "#6366f1",
  unknown: "#6b7280",
};

const FAILURE_LABELS = {
  timeout: "Timeout",
  validation_error: "Validasyon",
  provider_rejected: "Provider Red",
  auth_error: "Auth Hatasi",
  rate_limited: "Rate Limit",
  provider_unavailable: "Provider Down",
  unknown: "Bilinmiyor",
};

function LatencyBar({ label, value, max, color }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-3" data-testid={`latency-bar-${label}`}>
      <span className="text-xs text-zinc-500 font-mono w-8 text-right">{label}</span>
      <div className="flex-1 h-5 bg-zinc-800 rounded overflow-hidden relative">
        <div
          className="h-full rounded transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
        <span className="absolute inset-0 flex items-center px-2 text-[10px] font-mono text-zinc-200">
          {value > 0 ? `${value}ms` : "—"}
        </span>
      </div>
    </div>
  );
}

function PercentRing({ value, size = 80, stroke = 6, label, color = "#10b981" }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const ringColor = value >= 95 ? "#10b981" : value >= 80 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-1" data-testid={`percent-ring-${label}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#27272a" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke={color || ringColor} strokeWidth={stroke}
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" className="transition-all duration-1000"
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <span className="text-base font-bold font-mono text-zinc-100">{value}%</span>
      </div>
      {label && <span className="text-[10px] text-zinc-500 mt-1">{label}</span>}
    </div>
  );
}

function FailureBreakdownBar({ data }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  if (total === 0) {
    return (
      <div className="text-center py-4 text-zinc-600 text-xs" data-testid="failure-breakdown-empty">
        Hata kaydi yok
      </div>
    );
  }

  const sorted = Object.entries(data).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-2" data-testid="failure-breakdown-chart">
      {/* Stacked bar */}
      <div className="h-6 bg-zinc-800 rounded-lg overflow-hidden flex">
        {sorted.map(([key, count]) => {
          const pct = (count / total) * 100;
          return (
            <div
              key={key}
              className="h-full transition-all duration-700 first:rounded-l-lg last:rounded-r-lg"
              style={{ width: `${pct}%`, backgroundColor: FAILURE_COLORS[key] || "#6b7280" }}
              title={`${FAILURE_LABELS[key] || key}: ${count} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>
      {/* Legend */}
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
        <Badge variant="outline" className={`text-xs border ${status.cls}`}>
          {status.text}
        </Badge>
      </div>
      <div className="space-y-2">
        {checks.map(({ label, value, target, ok }) => (
          <div key={label} className="flex items-center justify-between text-xs">
            <span className="text-zinc-500">{label}</span>
            <div className="flex items-center gap-2">
              <span className="text-zinc-400 font-mono text-[10px]">{target}</span>
              <span className={`font-mono font-medium ${ok ? "text-emerald-400" : "text-red-400"}`}>
                {value}
              </span>
              {ok ? <CheckCircle className="h-3 w-3 text-emerald-500" /> : <XCircle className="h-3 w-3 text-red-500" />}
            </div>
          </div>
        ))}
      </div>
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
        <span className={`text-xl font-bold font-mono ${severity === "critical" ? "text-red-400" : severity === "warning" ? "text-yellow-400" : "text-emerald-400"}`}>
          {total}
        </span>
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
      ) : (
        <div className="text-xs text-zinc-600">Drift yok</div>
      )}
    </div>
  );
}

export function ChannelHealth() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (showToast = false) => {
    try {
      const res = await axios.get("/ops/dashboard/channel-health?hours=24");
      setData(res.data);
      if (showToast) toast.success("Kanal sagligi guncellendi");
    } catch (err) {
      toast.error("Kanal sagligi yuklenemedi", { description: err.response?.data?.detail || err.message });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData(true);
  };

  if (loading) {
    return (
      <div className="space-y-4" data-testid="channel-health-loading">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 bg-zinc-800" />)}
        </div>
        <Skeleton className="h-48 bg-zinc-800" />
        <Skeleton className="h-36 bg-zinc-800" />
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
  const providerSummary = data.provider_summary || {};

  const overallLatency = latency.overall || {};
  const overallSync = syncM.overall || {};
  const overallRetry = retries.overall || {};
  const allProviders = [...new Set([
    ...Object.keys(latency.by_provider || {}),
    ...Object.keys(syncM.by_provider || {}),
    ...Object.keys(drift.by_provider || {}),
    ...Object.keys(providerSummary),
  ])].filter(p => p !== "unknown");

  const maxLatency = Math.max(
    overallLatency.p99 || 0,
    ...Object.values(latency.by_provider || {}).map(p => p.p99 || 0),
    1000,
  );

  return (
    <div className="space-y-5" data-testid="channel-health-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-zinc-400">
            Son {data.period_hours} saat · Guncelleme: {new Date(data.calculated_at).toLocaleTimeString("tr-TR")}
          </span>
        </div>
        <Button
          variant="ghost" size="sm"
          className="h-7 text-xs text-zinc-500"
          onClick={handleRefresh}
          disabled={refreshing}
          data-testid="channel-health-refresh"
        >
          <RefreshCw className={`h-3 w-3 mr-1 ${refreshing ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {/* KPI Summary Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPISummaryCard
          icon={<Gauge className="h-4 w-4" />}
          label="Push Latency p95"
          value={`${overallLatency.p95 || 0}ms`}
          sub={`p50: ${overallLatency.p50 || 0}ms · p99: ${overallLatency.p99 || 0}ms`}
          ok={(overallLatency.p95 || 0) <= 5000}
          testId="kpi-push-latency"
        />
        <KPISummaryCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Sync Basari"
          value={`${overallSync.success_rate ?? 100}%`}
          sub={`${overallSync.completed || 0}/${overallSync.total || 0} basarili`}
          ok={(overallSync.success_rate ?? 100) >= 95}
          testId="kpi-sync-success"
        />
        <KPISummaryCard
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Drift Sayisi"
          value={drift.total_open || 0}
          sub={`${allProviders.length} provider`}
          ok={(drift.total_open || 0) < 10}
          testId="kpi-drift-count"
        />
        <KPISummaryCard
          icon={<Zap className="h-4 w-4" />}
          label="Retry Basari"
          value={`${overallRetry.retry_success_rate ?? 0}%`}
          sub={`${overallRetry.retried_success || 0}/${overallRetry.total_retried || 0}`}
          ok={(overallRetry.retry_success_rate ?? 100) >= 80}
          testId="kpi-retry-success"
        />
      </div>

      {/* Push Latency Section */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
            <Clock className="h-4 w-4 text-zinc-500" />
            Push Latency Dagilimi
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Overall */}
          <div>
            <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-2">Genel</div>
            <div className="space-y-1.5">
              <LatencyBar label="p50" value={overallLatency.p50 || 0} max={maxLatency} color="#10b981" />
              <LatencyBar label="p95" value={overallLatency.p95 || 0} max={maxLatency} color="#f59e0b" />
              <LatencyBar label="p99" value={overallLatency.p99 || 0} max={maxLatency} color="#ef4444" />
            </div>
          </div>
          {/* Per provider */}
          {Object.entries(latency.by_provider || {}).filter(([k]) => k !== "unknown").map(([provider, pData]) => (
            <div key={provider}>
              <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-2 capitalize">{provider}</div>
              <div className="space-y-1.5">
                <LatencyBar label="p50" value={pData.p50 || 0} max={maxLatency} color="#10b981" />
                <LatencyBar label="p95" value={pData.p95 || 0} max={maxLatency} color="#f59e0b" />
                <LatencyBar label="p99" value={pData.p99 || 0} max={maxLatency} color="#ef4444" />
              </div>
              <div className="flex gap-4 mt-1 text-[10px] text-zinc-600 font-mono">
                <span>avg: {pData.avg || 0}ms</span>
                <span>min: {pData.min || 0}ms</span>
                <span>max: {pData.max || 0}ms</span>
                <span>{pData.count || 0} push</span>
              </div>
            </div>
          ))}
          {Object.keys(latency.by_provider || {}).filter(k => k !== "unknown").length === 0 && (
            <div className="text-xs text-zinc-600 text-center py-3">Push latency verisi yok</div>
          )}
        </CardContent>
      </Card>

      {/* Failure Breakdown */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-zinc-500" />
            Hata Dagilimi
            {(failures.total_failures || 0) > 0 && (
              <Badge variant="outline" className="text-red-400 border-red-500/30 text-[10px] ml-2">
                {failures.total_failures} hata
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <FailureBreakdownBar data={failures.overall || {}} />
          {/* Per provider */}
          {Object.entries(failures.by_provider || {}).filter(([k]) => k !== "unknown").map(([provider, pData]) => (
            <div key={provider} className="mt-3 pt-3 border-t border-zinc-800">
              <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-2 capitalize">{provider}</div>
              <FailureBreakdownBar data={pData} />
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Reconciliation Drift + Retry in 2-col grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Drift */}
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-zinc-500" />
              Reconciliation Drift
              <Badge variant="outline" className={`text-[10px] ml-auto border ${
                (drift.total_open || 0) >= 50 ? "text-red-400 border-red-500/30" :
                (drift.total_open || 0) >= 10 ? "text-yellow-400 border-yellow-500/30" :
                "text-emerald-400 border-emerald-500/30"
              }`}>
                {drift.total_open || 0} acik
              </Badge>
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

        {/* Provider SLA */}
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <Shield className="h-4 w-4 text-zinc-500" />
              Provider SLA
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

      {/* Sync Metrics per provider */}
      {Object.entries(syncM.by_provider || {}).filter(([k]) => k !== "unknown").length > 0 && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <Activity className="h-4 w-4 text-zinc-500" />
              Provider Sync Detay
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {Object.entries(syncM.by_provider || {}).filter(([k]) => k !== "unknown").map(([provider, pSync]) => (
                <div key={provider} className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/30" data-testid={`sync-detail-${provider}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-zinc-300 capitalize">{provider}</span>
                    <span className={`text-sm font-bold font-mono ${
                      pSync.success_rate >= 95 ? "text-emerald-400" :
                      pSync.success_rate >= 80 ? "text-yellow-400" : "text-red-400"
                    }`}>
                      {pSync.success_rate}%
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
                    <div>
                      <div className="text-zinc-600">Toplam</div>
                      <div className="text-zinc-300">{pSync.total}</div>
                    </div>
                    <div>
                      <div className="text-zinc-600">Basarili</div>
                      <div className="text-emerald-400">{pSync.completed}</div>
                    </div>
                    <div>
                      <div className="text-zinc-600">Basarisiz</div>
                      <div className="text-red-400">{pSync.failed}</div>
                    </div>
                  </div>
                  <div className="text-[10px] text-zinc-600 mt-1 font-mono">
                    avg duration: {pSync.avg_duration_ms}ms
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
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
