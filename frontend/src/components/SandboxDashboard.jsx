import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  Shield, CheckCircle, XCircle, AlertTriangle, RefreshCw,
  Play, ChevronDown, ChevronUp, ExternalLink, Clock,
  TrendingUp, TrendingDown, Activity,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";

const SCENARIO_LABELS = {
  duplicate_delivery: "Duplicate Delivery",
  delayed_ack: "Delayed ACK",
  retry_storm: "Retry Storm",
  stale_provider_state: "Stale Provider State",
  modify_cancel_race: "Modify/Cancel Race",
};

function SandboxTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-zinc-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-zinc-400">{p.name}:</span>
          <span className="text-zinc-100 font-mono font-medium">{p.value}%</span>
        </div>
      ))}
    </div>
  );
}

function ProviderCard({ card }) {
  const [expanded, setExpanded] = useState(false);
  const allPassed = card.failed === 0;

  return (
    <Card
      className={`border ${allPassed ? "bg-zinc-900 border-emerald-500/20" : "bg-zinc-900 border-red-500/30"}`}
      data-testid={`sandbox-provider-card-${card.provider}`}
    >
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className={`h-4 w-4 ${allPassed ? "text-emerald-400" : "text-red-400"}`} />
            <span className="text-sm font-semibold text-zinc-200">{card.display_name}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={`text-[10px] font-mono px-2 py-0 ${
                allPassed
                  ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                  : "text-red-400 border-red-500/30 bg-red-500/10"
              }`}
              data-testid={`sandbox-pass-rate-${card.provider}`}
            >
              {card.pass_rate}
            </Badge>
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
              data-testid={`sandbox-expand-${card.provider}`}
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1">
            <CheckCircle className="h-3 w-3 text-emerald-400" />
            <span className="text-zinc-400">{card.passed}</span>
          </div>
          <div className="flex items-center gap-1">
            <XCircle className="h-3 w-3 text-red-400" />
            <span className="text-zinc-400">{card.failed}</span>
          </div>
          <div className="text-zinc-600">/ {card.total} senaryo</div>
        </div>

        {/* Progress bar */}
        <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${allPassed ? "bg-emerald-500" : "bg-red-500"}`}
            style={{ width: `${(card.passed / card.total) * 100}%` }}
          />
        </div>

        {expanded && (
          <div className="space-y-1.5 pt-1" data-testid={`sandbox-scenarios-${card.provider}`}>
            {card.scenarios.map((s, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  {s.passed ? (
                    <CheckCircle className="h-3 w-3 text-emerald-400" />
                  ) : (
                    <XCircle className="h-3 w-3 text-red-400" />
                  )}
                  <span className="text-zinc-300 font-mono text-[11px]">
                    {SCENARIO_LABELS[s.name] || s.name}
                  </span>
                </div>
                <Badge
                  variant="outline"
                  className={`text-[9px] px-1.5 py-0 ${
                    s.passed
                      ? "text-emerald-400 border-emerald-500/30"
                      : "text-red-400 border-red-500/30"
                  }`}
                >
                  {s.passed ? "PASS" : "FAIL"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RegressionAlert({ regressions }) {
  if (!regressions || regressions.length === 0) return null;

  return (
    <div
      className="bg-red-950/40 border border-red-500/40 rounded-lg p-3 space-y-2"
      data-testid="sandbox-regression-alert"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-red-400 animate-pulse" />
        <span className="text-xs font-bold text-red-300 uppercase tracking-wider">
          Sandbox Regression Algılandi
        </span>
      </div>
      {regressions.map((r, i) => (
        <div key={i} className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="text-zinc-400 font-mono">{r.provider}</span>
            <span className="text-zinc-600">→</span>
            <span className="text-red-300">{SCENARIO_LABELS[r.scenario] || r.scenario}</span>
          </div>
          <Badge
            variant="outline"
            className={`text-[9px] px-1.5 py-0 ${
              r.severity === "critical"
                ? "text-red-400 border-red-500/30"
                : "text-yellow-400 border-yellow-500/30"
            }`}
          >
            {r.severity}
          </Badge>
        </div>
      ))}
    </div>
  );
}

function TrendChart({ data }) {
  if (!data || data.length < 2) {
    return (
      <div className="text-xs text-zinc-600 text-center py-4">
        Trend icin en az 2 calistirma gerekli
      </div>
    );
  }

  const chartData = data.map((d) => ({
    name: d.date ? new Date(d.date).toLocaleDateString("tr-TR", { day: "2-digit", month: "short" }) : "",
    rate: d.pass_rate,
  }));

  return (
    <div data-testid="sandbox-trend-chart">
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#71717a" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#71717a" }} />
          <Tooltip content={<SandboxTooltip />} />
          <Line
            type="monotone"
            dataKey="rate"
            name="Basari"
            stroke="#10b981"
            strokeWidth={2}
            dot={{ r: 3, fill: "#10b981" }}
            activeDot={{ r: 5, fill: "#10b981" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SandboxDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [trends, setTrends] = useState(null);
  const [regressions, setRegressions] = useState(null);
  const [correlation, setCorrelation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, trendRes, regRes, corrRes] = await Promise.allSettled([
        axios.get("/ops/sandbox/dashboard"),
        axios.get("/ops/sandbox/trends?limit=30"),
        axios.get("/ops/sandbox/regressions"),
        axios.get("/ops/sandbox/correlation?limit=10"),
      ]);
      if (dashRes.status === "fulfilled") setDashboard(dashRes.value.data);
      if (trendRes.status === "fulfilled") setTrends(trendRes.value.data);
      if (regRes.status === "fulfilled") setRegressions(regRes.value.data);
      if (corrRes.status === "fulfilled") setCorrelation(corrRes.value.data);
    } catch {
      toast.error("Sandbox verisi yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  const runSimulation = useCallback(async () => {
    setRunning(true);
    try {
      const res = await axios.post("/channel-manager/v2/sandbox/simulate");
      const data = res.data;
      if (data.summary?.all_passed) {
        toast.success(`Sandbox simulasyonu tamamlandi: ${data.summary.pass_rate} basari`);
      } else {
        toast.warning(`Sandbox simulasyonu: ${data.summary?.passed}/${data.summary?.total_scenarios} basarili`);
      }
      await fetchAll();
    } catch {
      toast.error("Sandbox simulasyonu basarisiz");
    } finally {
      setRunning(false);
    }
  }, [fetchAll]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  if (loading) {
    return (
      <div className="space-y-4" data-testid="sandbox-dashboard-loading">
        <Skeleton className="h-8 w-48 bg-zinc-800" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-40 bg-zinc-800" />
          <Skeleton className="h-40 bg-zinc-800" />
        </div>
        <Skeleton className="h-32 bg-zinc-800" />
      </div>
    );
  }

  const hasData = dashboard?.has_data;
  const lastRun = dashboard?.last_run;
  const providerCards = dashboard?.provider_cards || [];
  const overallTrend = trends?.overall_trend || [];
  const regList = regressions?.regressions || [];
  const corrInsight = correlation?.insight || "";
  const mostFailing = trends?.most_failing_scenarios || [];

  return (
    <div className="space-y-4" data-testid="sandbox-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
            <Activity className="h-4 w-4 text-cyan-400" />
            Sandbox Resilience Dashboard
          </h3>
          <p className="text-[10px] text-zinc-600 mt-0.5">
            Provider dayaniklilik testi sonuclari — sandbox_pass / sandbox_regression / prod_health
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-zinc-500"
            onClick={fetchAll}
            disabled={loading}
            data-testid="sandbox-refresh-btn"
          >
            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
            Yenile
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs text-cyan-400 border-cyan-500/30 bg-cyan-500/5 hover:bg-cyan-500/10"
            onClick={runSimulation}
            disabled={running}
            data-testid="sandbox-run-btn"
          >
            {running ? (
              <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
            ) : (
              <Play className="h-3 w-3 mr-1" />
            )}
            Simulasyon Calistir
          </Button>
        </div>
      </div>

      {!hasData ? (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-8 text-center">
            <Shield className="h-8 w-8 text-zinc-600 mx-auto mb-3" />
            <p className="text-sm text-zinc-400">Henuz sandbox simulasyonu calistirilmadi</p>
            <p className="text-xs text-zinc-600 mt-1">
              Yukaridaki butonu kullanarak ilk simulasyonu baslatabilirsiniz
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Regression Alert */}
          <RegressionAlert regressions={regList} />

          {/* Last Run Info */}
          {lastRun && (
            <div className="flex items-center gap-4 text-xs text-zinc-500">
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                <span>Son calistirma: </span>
                <span className="text-zinc-300 font-mono">
                  {new Date(lastRun.started_at).toLocaleString("tr-TR")}
                </span>
              </div>
              <Badge
                variant="outline"
                className={`text-[10px] px-2 py-0 font-mono ${
                  lastRun.summary?.all_passed
                    ? "text-emerald-400 border-emerald-500/30"
                    : "text-red-400 border-red-500/30"
                }`}
              >
                {lastRun.summary?.pass_rate}
              </Badge>
              <span className="text-zinc-600 font-mono text-[10px]">{lastRun.run_id}</span>
            </div>
          )}

          {/* Provider Cards */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {providerCards.map((card) => (
              <ProviderCard key={card.provider} card={card} />
            ))}
          </div>

          {/* Trend Chart */}
          <Card className="bg-zinc-900 border-zinc-800" data-testid="sandbox-trend-card">
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                <TrendingUp className="h-3.5 w-3.5" /> Basari Orani Trendi
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <TrendChart data={overallTrend} />
            </CardContent>
          </Card>

          {/* Bottom: Insights Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Most Failing Scenarios */}
            <Card className="bg-zinc-900 border-zinc-800" data-testid="sandbox-most-failing">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                  <TrendingDown className="h-3.5 w-3.5" /> En Cok Kırılan Senaryolar
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {mostFailing.length === 0 ? (
                  <div className="text-xs text-emerald-400 flex items-center gap-2 py-2">
                    <CheckCircle className="h-3.5 w-3.5" />
                    Hic kirilma tespit edilmedi
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {mostFailing.map((f, i) => {
                      const [prov, scenario] = (f.key || "").split(":");
                      return (
                        <div key={i} className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-2">
                            <XCircle className="h-3 w-3 text-red-400" />
                            <span className="text-zinc-400 font-mono">{prov}</span>
                            <span className="text-zinc-600">→</span>
                            <span className="text-zinc-300">{SCENARIO_LABELS[scenario] || scenario}</span>
                          </div>
                          <span className="text-red-400 font-mono text-[10px]">{f.failure_count}x</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Correlation Insight */}
            <Card className="bg-zinc-900 border-zinc-800" data-testid="sandbox-correlation">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                  <ExternalLink className="h-3.5 w-3.5" /> Deploy / Drift Korelasyonu
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-2">
                <p className="text-xs text-zinc-300">{corrInsight || "Veri bekleniyor..."}</p>
                {correlation?.drift_alerts_active > 0 && (
                  <div className="flex items-center gap-2 text-xs text-yellow-400">
                    <AlertTriangle className="h-3 w-3" />
                    <span>{correlation.drift_alerts_active} aktif drift alarmi</span>
                  </div>
                )}
                {correlation?.correlations?.length > 0 && (
                  <div className="text-[10px] text-zinc-600 font-mono">
                    {correlation.correlations.length} run analiz edildi
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
