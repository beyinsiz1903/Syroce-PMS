import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  Rocket,
  RefreshCw,
  CheckCircle,
  XCircle,
  RotateCcw,
  Clock,
  GitBranch,
  ChevronDown,
  ChevronRight,
  Server,
  Activity,
  TrendingUp,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

function StatCard({ label, value, sub, icon: Icon, color, testId }) {
  const colorMap = {
    emerald: "border-emerald-500/30 text-emerald-400",
    red: "border-red-500/30 text-red-400",
    blue: "border-blue-500/30 text-blue-400",
    amber: "border-amber-500/30 text-amber-400",
    zinc: "border-zinc-700 text-zinc-400",
  };

  return (
    <div
      className={`bg-zinc-900 border rounded-lg p-4 ${colorMap[color] || colorMap.zinc}`}
      data-testid={testId}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-zinc-500 uppercase tracking-wider">{label}</span>
        {Icon && <Icon className="h-4 w-4 opacity-50" />}
      </div>
      <div className="text-2xl font-bold font-mono">{value}</div>
      {sub && <div className="text-[10px] text-zinc-600 mt-1">{sub}</div>}
    </div>
  );
}

function DeployTrendChart({ trend }) {
  if (!trend || trend.length === 0) return null;

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    return (
      <div className="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-xs font-mono shadow-lg">
        <div className="text-zinc-300 mb-1">{label}</div>
        <div className="text-emerald-400">Basarili: {d?.success || 0}</div>
        <div className="text-red-400">Basarisiz: {d?.failure || 0}</div>
        {d?.rollbacks > 0 && <div className="text-amber-400">Rollback: {d.rollbacks}</div>}
      </div>
    );
  };

  return (
    <div
      className="bg-zinc-900 border border-zinc-800 rounded-lg p-4"
      data-testid="deploy-trend-chart"
    >
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp className="h-3.5 w-3.5 text-zinc-500" />
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
          Deploy Trendi
        </span>
        <span className="text-[10px] text-zinc-600">
          (son {trend.length} gun)
        </span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={trend} barGap={2}>
          <XAxis
            dataKey="date"
            tick={{ fill: "#71717a", fontSize: 10 }}
            tickFormatter={(v) => v?.slice(5) || ""}
            axisLine={{ stroke: "#27272a" }}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: "#52525b", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={24}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <Bar dataKey="success" stackId="deploys" radius={[0, 0, 0, 0]} maxBarSize={20}>
            {trend.map((entry, i) => (
              <Cell key={i} fill="#34d399" fillOpacity={0.7} />
            ))}
          </Bar>
          <Bar dataKey="failure" stackId="deploys" radius={[2, 2, 0, 0]} maxBarSize={20}>
            {trend.map((entry, i) => (
              <Cell key={i} fill="#f87171" fillOpacity={0.7} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 justify-center">
        <div className="flex items-center gap-1.5 text-[10px] text-zinc-500">
          <div className="w-2.5 h-2.5 rounded-sm bg-emerald-400/70" />
          Basarili
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-zinc-500">
          <div className="w-2.5 h-2.5 rounded-sm bg-red-400/70" />
          Basarisiz
        </div>
      </div>
    </div>
  );
}

function DeployRow({ deploy, isExpanded, onToggle }) {
  const statusConfig = {
    success: {
      icon: CheckCircle,
      color: "text-emerald-400",
      bg: "bg-emerald-500/10 border-emerald-500/30",
      label: "BASARILI",
    },
    failure: {
      icon: XCircle,
      color: "text-red-400",
      bg: "bg-red-500/10 border-red-500/30",
      label: "BASARISIZ",
    },
  };

  const cfg = statusConfig[deploy.status] || {
    icon: Clock,
    color: "text-zinc-400",
    bg: "bg-zinc-500/10 border-zinc-500/30",
    label: deploy.status?.toUpperCase() || "BILINMIYOR",
  };
  const StatusIcon = cfg.icon;

  const smokeEndpoints = deploy.smoke_test?.endpoints || [];

  const formatTime = (iso) => {
    if (!iso) return "--";
    try {
      const d = new Date(iso);
      return d.toLocaleString("tr-TR", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  const smokePassCount = smokeEndpoints.filter((e) => e.result === "OK").length;
  const smokeTotal = smokeEndpoints.length;

  return (
    <div
      className={`border-b border-zinc-800/50 ${deploy.rollback ? "bg-red-500/5" : ""}`}
      data-testid={`deploy-row-${deploy.short_sha}`}
    >
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-800/30 transition-colors"
        onClick={onToggle}
      >
        <StatusIcon className={`h-4 w-4 shrink-0 ${cfg.color}`} />
        <span className={`text-xs font-bold tracking-wide px-2 py-0.5 rounded border ${cfg.bg}`}>
          {cfg.label}
        </span>
        <code className="text-sm text-zinc-200 font-mono">{deploy.short_sha || "--"}</code>
        <Badge
          variant="outline"
          className={`text-[10px] ${
            deploy.environment === "production"
              ? "border-amber-500/40 text-amber-400"
              : "border-blue-500/40 text-blue-400"
          }`}
        >
          {deploy.environment}
        </Badge>
        {deploy.rollback && (
          <Badge variant="outline" className="text-[10px] border-red-500/40 text-red-400">
            <RotateCcw className="h-2.5 w-2.5 mr-1" />
            ROLLBACK
          </Badge>
        )}
        {smokeTotal > 0 && (
          <Badge
            variant="outline"
            className={`text-[10px] ${
              smokePassCount === smokeTotal
                ? "border-emerald-500/30 text-emerald-400"
                : "border-red-500/30 text-red-400"
            }`}
          >
            <Activity className="h-2.5 w-2.5 mr-1" />
            {smokePassCount}/{smokeTotal}
          </Badge>
        )}
        <div className="flex-1" />
        <span className="text-xs text-zinc-500 font-mono">{deploy.actor}</span>
        <span className="text-xs text-zinc-600 font-mono">{formatTime(deploy.recorded_at)}</span>
        {isExpanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-zinc-600" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-zinc-600" />
        )}
      </button>

      {isExpanded && (
        <div className="px-4 pb-3 bg-zinc-950/50">
          <div className="pl-7 space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
              <div>
                <span className="text-zinc-500">branch: </span>
                <span className="text-zinc-300">{deploy.branch || "--"}</span>
              </div>
              <div>
                <span className="text-zinc-500">sha: </span>
                <span className="text-zinc-300">{deploy.sha || "--"}</span>
              </div>
              <div>
                <span className="text-zinc-500">sure: </span>
                <span className="text-zinc-300">
                  {deploy.duration_seconds ? `${deploy.duration_seconds}s` : "--"}
                </span>
              </div>
              <div>
                <span className="text-zinc-500">zaman: </span>
                <span className="text-zinc-300">{formatTime(deploy.recorded_at)}</span>
              </div>
            </div>

            {deploy.rollback_reason && (
              <div className="text-xs bg-red-500/10 border border-red-500/20 rounded p-2 text-red-300 font-mono">
                Rollback: {deploy.rollback_reason}
              </div>
            )}

            {smokeEndpoints.length > 0 && (
              <div className="bg-zinc-900 border border-zinc-800 rounded overflow-hidden">
                <div className="px-3 py-1.5 border-b border-zinc-800 text-[10px] text-zinc-500 uppercase tracking-wider font-medium flex items-center gap-1.5">
                  <Activity className="h-3 w-3" />
                  Smoke Test Sonuçlari
                </div>
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="text-zinc-600 border-b border-zinc-800/50">
                      <th className="text-left px-3 py-1.5">Endpoint</th>
                      <th className="text-left px-3 py-1.5">Status</th>
                      <th className="text-left px-3 py-1.5">Latency</th>
                      <th className="text-left px-3 py-1.5">Sonuç</th>
                    </tr>
                  </thead>
                  <tbody>
                    {smokeEndpoints.map((ep, i) => (
                      <tr
                        key={i}
                        className="border-b border-zinc-800/30"
                        data-testid={`smoke-endpoint-${i}`}
                      >
                        <td className="px-3 py-1.5 text-zinc-300">{ep.path || ep.name}</td>
                        <td className="px-3 py-1.5">
                          <span
                            className={
                              ep.status === 200 ? "text-emerald-400" : "text-red-400"
                            }
                          >
                            {ep.status}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-zinc-400">{ep.latency_ms}ms</td>
                        <td className="px-3 py-1.5">
                          {ep.result === "OK" ? (
                            <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                          ) : (
                            <XCircle className="h-3.5 w-3.5 text-red-500" />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function DeployDashboard() {
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState(null);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedSha, setExpandedSha] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [histRes, statsRes, trendRes] = await Promise.all([
        axios.get("/ops/dashboard/deploys"),
        axios.get("/ops/dashboard/deploy-stats"),
        axios.get("/ops/dashboard/deploy-trend?days=14"),
      ]);
      setHistory(histRes.data.deploys || []);
      setStats(statsRes.data);
      setTrend(trendRes.data.trend || []);
    } catch (err) {
      toast.error("Deploy verileri yüklenemedi", {
        description: err.response?.data?.detail || err.message,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-3" data-testid="deploy-dashboard-loading">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 bg-zinc-800" />
          ))}
        </div>
        <Skeleton className="h-40 bg-zinc-800" />
        <Skeleton className="h-64 bg-zinc-800" />
      </div>
    );
  }

  const overall = stats?.overall || {};
  const envStats = stats?.by_environment || [];

  return (
    <div className="space-y-4" data-testid="deploy-dashboard">
      {/* Stats Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Toplam Deploy"
          value={overall.total_deploys || 0}
          sub={envStats.map((e) => `${e.environment}: ${e.total}`).join(" | ") || "Henüz veri yok"}
          icon={Rocket}
          color="blue"
          testId="stat-total-deploys"
        />
        <StatCard
          label="Basari Orani"
          value={`${overall.overall_success_rate || 0}%`}
          sub={`${overall.total_success || 0} basarili / ${overall.total_failure || 0} başarısız`}
          icon={CheckCircle}
          color={
            (overall.overall_success_rate || 0) >= 95
              ? "emerald"
              : (overall.overall_success_rate || 0) >= 80
                ? "amber"
                : "red"
          }
          testId="stat-success-rate"
        />
        <StatCard
          label="Rollback"
          value={overall.total_rollbacks || 0}
          sub="Otomatik geri alma"
          icon={RotateCcw}
          color={overall.total_rollbacks > 0 ? "amber" : "emerald"}
          testId="stat-rollbacks"
        />
        <StatCard
          label="Son Deploy"
          value={
            history[0]
              ? new Date(history[0].recorded_at).toLocaleString("tr-TR", {
                  day: "2-digit",
                  month: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "--"
          }
          sub={history[0] ? `${history[0].short_sha} → ${history[0].environment}` : "Henüz deploy yok"}
          icon={Clock}
          color="zinc"
          testId="stat-last-deploy"
        />
      </div>

      {/* Deploy Trend Chart */}
      <DeployTrendChart trend={trend} />

      {/* Environment Breakdown */}
      {envStats.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {envStats.map((env) => (
            <Card
              key={env.environment}
              className="bg-zinc-900 border-zinc-800"
              data-testid={`env-card-${env.environment}`}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Server className="h-4 w-4 text-zinc-500" />
                  <span className="text-sm font-medium text-zinc-200 uppercase tracking-wider">
                    {env.environment}
                  </span>
                  <Badge
                    variant="outline"
                    className={`ml-auto text-[10px] ${
                      env.success_rate >= 95
                        ? "border-emerald-500/40 text-emerald-400"
                        : env.success_rate >= 80
                          ? "border-amber-500/40 text-amber-400"
                          : "border-red-500/40 text-red-400"
                    }`}
                  >
                    {env.success_rate}%
                  </Badge>
                </div>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div>
                    <div className="text-lg font-bold font-mono text-zinc-200">{env.total}</div>
                    <div className="text-[10px] text-zinc-600">toplam</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold font-mono text-emerald-400">{env.success}</div>
                    <div className="text-[10px] text-zinc-600">basarili</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold font-mono text-red-400">{env.failure}</div>
                    <div className="text-[10px] text-zinc-600">başarısız</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold font-mono text-amber-400">
                      {env.rollback_count}
                    </div>
                    <div className="text-[10px] text-zinc-600">rollback</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Deploy History */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5 text-zinc-500" />
            <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
              Deploy Geçmişi
            </span>
            <span className="text-[10px] text-zinc-600">
              (son {history.length})
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-zinc-500"
            onClick={fetchData}
            data-testid="refresh-deploys-button"
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>

        {history.length === 0 ? (
          <div className="text-center py-12 text-zinc-500" data-testid="deploy-empty-state">
            <Rocket className="h-10 w-10 mx-auto mb-3 opacity-20" />
            <p className="text-sm">Henüz deploy kaydi yok</p>
            <p className="text-xs mt-1 text-zinc-600">
              CI/CD pipeline deploy sonuclarini buraya raporlar
            </p>
          </div>
        ) : (
          <div>
            {history.map((deploy) => (
              <DeployRow
                key={`${deploy.sha}-${deploy.recorded_at}`}
                deploy={deploy}
                isExpanded={expandedSha === `${deploy.sha}-${deploy.recorded_at}`}
                onToggle={() =>
                  setExpandedSha(
                    expandedSha === `${deploy.sha}-${deploy.recorded_at}`
                      ? null
                      : `${deploy.sha}-${deploy.recorded_at}`
                  )
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
