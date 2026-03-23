import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  Activity, Shield, AlertTriangle, CheckCircle, XCircle,
  TrendingUp, TrendingDown, Minus, RefreshCw, Zap,
  Target, Timer, Gauge, ArrowUpRight, ArrowDownRight,
  ChevronRight, Layers, GitBranch,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";

const RATING_STYLES = {
  elite: { label: "ELITE", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
  high: { label: "YUKSEK", cls: "bg-blue-500/15 text-blue-400 border-blue-500/30" },
  medium: { label: "ORTA", cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30" },
  low: { label: "DUSUK", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
  no_data: { label: "VERI YOK", cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30" },
};

const ALIGNMENT_STYLES = {
  aligned: { label: "HIZALI", icon: CheckCircle, cls: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" },
  drift_detected: { label: "DRIFT", icon: AlertTriangle, cls: "text-red-400 bg-red-500/10 border-red-500/30" },
  stale: { label: "BAYAT", icon: Timer, cls: "text-yellow-400 bg-yellow-500/10 border-yellow-500/30" },
  no_data: { label: "VERI YOK", icon: Minus, cls: "text-zinc-400 bg-zinc-500/10 border-zinc-500/30" },
};

const CORRELATION_INFERENCE = {
  positive_correlation: { label: "Pozitif Korelasyon", icon: TrendingUp, cls: "text-emerald-400" },
  inverse_correlation: { label: "Ters Korelasyon", icon: TrendingDown, cls: "text-yellow-400" },
  co_declining: { label: "Birlikte Dususte", icon: TrendingDown, cls: "text-red-400" },
  insufficient_data: { label: "Yetersiz Veri", icon: Minus, cls: "text-zinc-500" },
  no_correlation: { label: "Korelasyon Yok", icon: Minus, cls: "text-zinc-500" },
  improving: { label: "Iyilesiyor", icon: TrendingUp, cls: "text-emerald-400" },
  stable: { label: "Stabil", icon: Minus, cls: "text-blue-400" },
  degrading: { label: "Kotulesiyor", icon: TrendingDown, cls: "text-red-400" },
};

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-zinc-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-zinc-400">{p.name}:</span>
          <span className="text-zinc-100 font-mono font-medium">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Inventory Alignment Block ──────────────────────────────────
function AlignmentBlock({ data, onDrillDown }) {
  if (!data) return <Skeleton className="h-40 bg-zinc-800" />;

  const style = ALIGNMENT_STYLES[data.alignment_status] || ALIGNMENT_STYLES.no_data;
  const Icon = style.icon;

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="alignment-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <Layers className="h-3.5 w-3.5" /> Inventory Alignment
          </CardTitle>
          <button
            onClick={() => onDrillDown?.("inventory-alignment")}
            className="text-zinc-600 hover:text-zinc-300 transition-colors"
            data-testid="alignment-drilldown"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md border ${style.cls}`}>
            <Icon className="h-4 w-4" />
            <span className="text-sm font-bold tracking-wide">{style.label}</span>
          </div>
          <div className="text-xs text-zinc-500">
            <span className="text-zinc-300 font-mono">{data.connectors_checked}</span> connector kontrol edildi
          </div>
        </div>

        {data.drift_count > 0 && (
          <div className="bg-red-500/5 border border-red-500/20 rounded-md p-2">
            <div className="flex items-center gap-2 text-xs text-red-400">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span className="font-mono font-bold">{data.drift_count}</span> drift,
              <span className="font-mono font-bold">{data.drift_nights}</span> gece
            </div>
          </div>
        )}

        {/* Provider breakdown */}
        {data.provider_breakdown?.length > 0 && (
          <div className="space-y-1">
            {data.provider_breakdown.map((p, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-zinc-400 font-mono">{p.provider}</span>
                <div className="flex items-center gap-2">
                  <span className="text-zinc-500">{p.snapshots_checked} kontrol</span>
                  {p.drift_count > 0 ? (
                    <Badge variant="outline" className="text-red-400 border-red-500/30 text-[10px] px-1.5 py-0">
                      {p.drift_count} drift
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-emerald-400 border-emerald-500/30 text-[10px] px-1.5 py-0">
                      OK
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 text-[10px] text-zinc-600">
          <span>freshness: <span className="text-zinc-400">{data.freshness}</span></span>
          <span>·</span>
          <span>{data.inventory_room_type_nights} oda-gece</span>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── DORA Metrics Block ────────────────────────────────────────
function DoraBlock({ data, onDrillDown }) {
  if (!data) return <Skeleton className="h-52 bg-zinc-800" />;

  const m = data.metrics || {};

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="dora-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <Zap className="h-3.5 w-3.5" /> DORA Metrikleri
          </CardTitle>
          <button
            onClick={() => onDrillDown?.("dora")}
            className="text-zinc-600 hover:text-zinc-300 transition-colors"
            data-testid="dora-drilldown"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="grid grid-cols-2 gap-3">
          <DoraMetricCard
            label="Deploy Frekans"
            value={m.deployment_frequency?.value || 0}
            unit={m.deployment_frequency?.unit || ""}
            rating={m.deployment_frequency?.rating}
            testId="dora-deploy-freq"
          />
          <DoraMetricCard
            label="Degisiklik Hata %"
            value={m.change_failure_rate?.value || 0}
            unit="%"
            rating={m.change_failure_rate?.rating}
            inverse
            testId="dora-cfr"
          />
          <DoraMetricCard
            label="MTTR"
            value={m.mttr?.value || 0}
            unit="dk"
            rating={m.mttr?.rating}
            inverse
            testId="dora-mttr"
          />
          <DoraMetricCard
            label="Lead Time"
            value={m.lead_time?.value || 0}
            unit="dk"
            rating={m.lead_time?.rating}
            inverse
            testId="dora-lead-time"
          />
        </div>

        {/* Mini trend chart */}
        {data.trend?.length > 0 && (
          <div className="mt-3 h-20">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.trend.slice(-14)} barGap={1}>
                <Bar dataKey="success" fill="#10b981" radius={[2, 2, 0, 0]} />
                <Bar dataKey="failure" fill="#ef4444" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="flex items-center justify-between mt-2 text-[10px] text-zinc-600">
          <span>{data.total_deploys} toplam deploy</span>
          <span>{data.period_days} gun · {data.environment}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function DoraMetricCard({ label, value, unit, rating, inverse, testId }) {
  const r = RATING_STYLES[rating] || RATING_STYLES.no_data;
  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3" data-testid={testId}>
      <div className="text-[10px] text-zinc-500 mb-1">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold font-mono text-zinc-100">{value}</span>
        <span className="text-[10px] text-zinc-600">{unit}</span>
      </div>
      <Badge variant="outline" className={`${r.cls} text-[9px] px-1.5 py-0 mt-1 border`}>
        {r.label}
      </Badge>
    </div>
  );
}

// ─── Deploy Health Block ────────────────────────────────────────
function DeployHealthBlock({ data, onDrillDown }) {
  if (!data) return <Skeleton className="h-24 bg-zinc-800" />;

  const stats = data.environments || {};
  const envList = Object.entries(stats);

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="deploy-health-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5" /> Deploy Sagligi
          </CardTitle>
          <button
            onClick={() => onDrillDown?.("deploys")}
            className="text-zinc-600 hover:text-zinc-300 transition-colors"
            data-testid="deploy-health-drilldown"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {envList.length === 0 ? (
          <div className="text-xs text-zinc-600 text-center py-2">Deploy verisi yok</div>
        ) : (
          <div className="space-y-2">
            {envList.map(([env, s]) => {
              const rate = s.total > 0 ? Math.round((s.success / s.total) * 100) : 0;
              return (
                <div key={env} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-zinc-400 border-zinc-700 text-[10px] font-mono px-1.5">
                      {env}
                    </Badge>
                    <span className="text-xs text-zinc-500">
                      {s.total} deploy
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${rate >= 90 ? "bg-emerald-500" : rate >= 70 ? "bg-yellow-500" : "bg-red-500"}`}
                        style={{ width: `${rate}%` }}
                      />
                    </div>
                    <span className={`text-xs font-mono font-bold ${rate >= 90 ? "text-emerald-400" : rate >= 70 ? "text-yellow-400" : "text-red-400"}`}>
                      {rate}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Provider Health Block ──────────────────────────────────────
function ProviderHealthBlock({ data, onDrillDown }) {
  if (!data) return <Skeleton className="h-24 bg-zinc-800" />;

  const providers = data.provider_breakdown || [];

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="provider-health-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <Shield className="h-3.5 w-3.5" /> Provider Durumu
          </CardTitle>
          <button
            onClick={() => onDrillDown?.("channel-health")}
            className="text-zinc-600 hover:text-zinc-300 transition-colors"
            data-testid="provider-health-drilldown"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {providers.length === 0 ? (
          <div className="text-xs text-zinc-600 text-center py-2">Provider verisi yok</div>
        ) : (
          <div className="space-y-2">
            {providers.map((p, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${p.drift_count > 0 ? "bg-red-500" : "bg-emerald-500"}`} />
                  <span className="text-zinc-300 font-mono">{p.provider}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-zinc-500">{p.snapshots_checked} snapshot</span>
                  {p.drift_count > 0 ? (
                    <span className="text-red-400 font-mono font-bold">{p.drift_count} drift</span>
                  ) : (
                    <span className="text-emerald-400 font-mono">hizali</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Correlation Block ──────────────────────────────────────────
function CorrelationBlock({ data }) {
  if (!data) return <Skeleton className="h-36 bg-zinc-800" />;

  const correlations = data.correlations || [];

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="correlation-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
          <Activity className="h-3.5 w-3.5" /> DORA x Kanal Sagligi Korelasyonu
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-2">
        {correlations.length === 0 ? (
          <div className="text-xs text-zinc-600 text-center py-2">Korelasyon verisi yok</div>
        ) : (
          correlations.map((c, i) => {
            const inf = CORRELATION_INFERENCE[c.inference] || CORRELATION_INFERENCE.insufficient_data;
            const InfIcon = inf.icon;
            return (
              <div key={i} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3" data-testid={`correlation-${c.name}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-zinc-300">{c.question}</span>
                  <div className={`flex items-center gap-1 text-xs ${inf.cls}`}>
                    <InfIcon className="h-3 w-3" />
                    <span className="font-medium">{inf.label}</span>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-[10px] text-zinc-500 font-mono">
                  {c.deploy_change !== undefined && (
                    <span>deploy: <span className={c.deploy_change > 0 ? "text-emerald-400" : c.deploy_change < 0 ? "text-red-400" : "text-zinc-400"}>
                      {c.deploy_change > 0 ? "+" : ""}{c.deploy_change}
                    </span></span>
                  )}
                  {c.drift_change !== undefined && (
                    <span>drift: <span className={c.drift_change < 0 ? "text-emerald-400" : c.drift_change > 0 ? "text-red-400" : "text-zinc-400"}>
                      {c.drift_change > 0 ? "+" : ""}{c.drift_change}
                    </span></span>
                  )}
                  {c.cfr_change !== undefined && (
                    <span>CFR: <span className={c.cfr_change < 0 ? "text-emerald-400" : c.cfr_change > 0 ? "text-red-400" : "text-zinc-400"}>
                      {c.cfr_change > 0 ? "+" : ""}{c.cfr_change}%
                    </span></span>
                  )}
                  {c.import_failure_change !== undefined && (
                    <span>import fail: <span className={c.import_failure_change < 0 ? "text-emerald-400" : c.import_failure_change > 0 ? "text-red-400" : "text-zinc-400"}>
                      {c.import_failure_change > 0 ? "+" : ""}{c.import_failure_change}
                    </span></span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

// ─── Reconciliation Queue Block ─────────────────────────────────
function ReconQueueBlock({ data }) {
  if (!data) return <Skeleton className="h-20 bg-zinc-800" />;

  const freshness = data.freshness || "unknown";
  const rtnCount = data.inventory_room_type_nights || 0;

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="recon-queue-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
          <Target className="h-3.5 w-3.5" /> Reconciliation Durumu
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`px-2 py-1 rounded text-xs font-mono border ${
              freshness === "fresh" ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" :
              freshness === "recent" ? "text-blue-400 border-blue-500/30 bg-blue-500/10" :
              freshness === "stale" ? "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" :
              "text-zinc-400 border-zinc-600/30 bg-zinc-600/10"
            }`}>
              {freshness.toUpperCase()}
            </div>
            <span className="text-xs text-zinc-500">
              <span className="text-zinc-300 font-mono">{rtnCount}</span> oda-tip-gece kaydi
            </span>
          </div>
          <span className="text-[10px] text-zinc-600">
            {data.date_range?.start} - {data.date_range?.end}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Main Unified Ops View ──────────────────────────────────────
export function UnifiedOpsView() {
  const [alignment, setAlignment] = useState(null);
  const [dora, setDora] = useState(null);
  const [correlation, setCorrelation] = useState(null);
  const [deployStats, setDeployStats] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [alignRes, doraRes, corrRes, statsRes] = await Promise.allSettled([
        axios.get("/ops/dashboard/inventory-alignment"),
        axios.get("/ops/dashboard/dora-metrics"),
        axios.get("/ops/dashboard/dora-correlation"),
        axios.get("/ops/dashboard/deploy-stats"),
      ]);
      if (alignRes.status === "fulfilled") setAlignment(alignRes.value.data);
      if (doraRes.status === "fulfilled") setDora(doraRes.value.data);
      if (corrRes.status === "fulfilled") setCorrelation(corrRes.value.data);
      if (statsRes.status === "fulfilled") setDeployStats(statsRes.value.data);
    } catch (err) {
      toast.error("Ops verisi yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleDrillDown = (tab) => {
    const tabEl = document.querySelector(`[data-testid="tab-${tab}"]`);
    if (tabEl) tabEl.click();
  };

  return (
    <div className="space-y-4" data-testid="unified-ops-view">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">Unified Ops View</h2>
          <p className="text-[10px] text-zinc-600 mt-0.5">Tek ekran: deploy + kanal + inventory + DORA</p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-zinc-500"
          onClick={fetchAll}
          disabled={loading}
          data-testid="ops-refresh"
        >
          <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {/* Top row: Alignment + Deploy Health */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AlignmentBlock data={alignment} onDrillDown={handleDrillDown} />
        <DeployHealthBlock data={deployStats} onDrillDown={handleDrillDown} />
      </div>

      {/* Middle row: DORA + Provider Health */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <DoraBlock data={dora} onDrillDown={handleDrillDown} />
        <ProviderHealthBlock data={alignment} onDrillDown={handleDrillDown} />
      </div>

      {/* Bottom: Correlation + Recon Queue */}
      <CorrelationBlock data={correlation} />
      <ReconQueueBlock data={alignment} />
    </div>
  );
}
