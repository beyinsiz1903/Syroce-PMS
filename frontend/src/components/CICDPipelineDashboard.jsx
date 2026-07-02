import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { GitBranch, Play, CheckCircle, XCircle, AlertTriangle, RefreshCw, Shield, Clock, ChevronDown, ChevronUp, Layers, Activity, Zap, Lock, ExternalLink, BarChart3, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';
const TIER_LABELS = {
  pr_gate: {
    name: "PR Gate",
    color: "text-blue-600",
    border: "border-blue-500/30",
    bg: "bg-blue-500/10"
  },
  staging_gate: {
    name: "Staging Gate",
    color: "text-amber-600",
    border: "border-amber-500/30",
    bg: "bg-amber-500/10"
  },
  nightly: {
    name: "Nightly",
    color: "text-violet-600",
    border: "border-violet-500/30",
    bg: "bg-violet-500/10"
  }
};
const VERDICT_STYLES = {
  PASS: {
    label: "PASS",
    cls: "text-emerald-600 border-emerald-500/30 bg-emerald-500/10"
  },
  BLOCK: {
    label: "BLOCK",
    cls: "text-red-600 border-red-500/30 bg-red-500/10"
  },
  WARN: {
    label: "WARN",
    cls: "text-amber-600 border-yellow-500/30 bg-yellow-500/10"
  },
  UNKNOWN: {
    label: "N/A",
    cls: "text-gray-600 border-gray-300/30 bg-gray-200/10"
  },
  NO_DATA: {
    label: "NO DATA",
    cls: "text-gray-500 border-gray-300/30 bg-gray-200/10"
  }
};
function PipelineTooltip({
  active,
  payload,
  label
}) {
  const {
    t
  } = useTranslation();
  if (!active || !payload?.length) return null;
  return <div className="bg-white border border-gray-300 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-gray-500 mb-1">{label}</p>
      {payload.map((p, i) => <div key={p.id || i} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{
        backgroundColor: p.color
      }} />
          <span className="text-gray-600">{p.name}:</span>
          <span className="text-gray-900 font-mono font-medium">{p.value}%</span>
        </div>)}
    </div>;
}
function HealthBadge({
  badge
}) {
  const vs = VERDICT_STYLES[badge.verdict] || VERDICT_STYLES.UNKNOWN;
  return <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2" data-testid={`health-badge-${badge.tier}`}>
      <div className={`w-2.5 h-2.5 rounded-full ${badge.status === "pass" ? "bg-emerald-500" : badge.status === "fail" ? "bg-red-500" : "bg-gray-400"}`} />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] text-gray-500">{badge.display_name}</div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={`text-[9px] px-1.5 py-0 font-mono ${vs.cls}`}>
            {vs.label}
          </Badge>
          {badge.pass_rate && badge.pass_rate !== "N/A" && <span className="text-[10px] text-gray-600 font-mono">{badge.pass_rate}</span>}
        </div>
      </div>
      {badge.last_run_at && <span className="text-[9px] text-gray-500 font-mono whitespace-nowrap">
          {new Date(badge.last_run_at).toLocaleDateString("tr-TR")}
        </span>}
    </div>;
}
function AcceptanceCriteriaList({
  criteria
}) {
  if (!criteria?.length) return null;
  return <div className="space-y-1" data-testid="cicd-acceptance-criteria">
      {criteria.map(c => <div key={c.id} className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            {c.passed ? <CheckCircle className="h-3 w-3 text-emerald-600 shrink-0" /> : <XCircle className="h-3 w-3 text-red-600 shrink-0" />}
            <span className={`font-mono text-[11px] ${c.passed ? "text-gray-600" : "text-red-700"}`}>
              {c.name}
            </span>
          </div>
          <Badge variant="outline" className={`text-[9px] px-1.5 py-0 font-mono ${c.passed ? "text-emerald-600 border-emerald-500/30" : "text-red-600 border-red-500/30"}`}>
            {c.value}
          </Badge>
        </div>)}
    </div>;
}
function RunCard({
  run
}) {
  const [expanded, setExpanded] = useState(false);
  const tier = TIER_LABELS[run.tier] || TIER_LABELS.pr_gate;
  const gate = run.deploy_gate || {};
  const vs = VERDICT_STYLES[gate.verdict] || VERDICT_STYLES.UNKNOWN;
  const criteria = run.acceptance_criteria?.criteria || [];
  const failedCriteria = criteria.filter(c => !c.passed);
  return <div className={`border rounded-lg overflow-hidden ${gate.verdict === "PASS" ? "border-emerald-500/20 bg-white" : gate.verdict === "BLOCK" ? "border-red-500/30 bg-red-50" : "border-gray-200 bg-white"}`} data-testid={`cicd-run-${run.run_id}`}>
      <div className="p-3 space-y-2">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={`text-[9px] px-1.5 py-0 ${tier.color} ${tier.border} ${tier.bg}`}>
              {tier.name}
            </Badge>
            <Badge variant="outline" className={`text-[9px] px-1.5 py-0 font-mono ${vs.cls}`}>
              {vs.label}
            </Badge>
            {run.build_context?.commit_sha && run.build_context.commit_sha !== "HEAD" && <span className="text-[9px] text-gray-500 font-mono">
                {run.build_context.commit_sha.slice(0, 7)}
              </span>}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-gray-500 font-mono">
              {run.started_at ? new Date(run.started_at).toLocaleString("tr-TR") : ""}
            </span>
            <button onClick={() => setExpanded(!expanded)} className="text-gray-500 hover:text-gray-700 transition-colors">
              {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {/* Summary */}
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1">
            <CheckCircle className="h-3 w-3 text-emerald-600" />
            <span className="text-gray-600">{run.simulation_summary?.passed || 0}</span>
          </div>
          <div className="flex items-center gap-1">
            <XCircle className="h-3 w-3 text-red-600" />
            <span className="text-gray-600">{run.simulation_summary?.failed || 0}</span>
          </div>
          <div className="text-gray-500 text-[10px]">
            / {run.simulation_summary?.total_scenarios || 0} senaryo
          </div>
          <div className="flex-1" />
          <span className={`text-[10px] font-mono ${run.simulation_summary?.pass_rate === "100%" ? "text-emerald-600" : "text-red-600"}`}>
            {run.simulation_summary?.pass_rate || "N/A"}
          </span>
        </div>

        {/* Failed criteria quick view */}
        {failedCriteria.length > 0 && !expanded && <div className="flex flex-wrap gap-1">
            {failedCriteria.slice(0, 3).map(c => <Badge key={c.id} variant="outline" className="text-[8px] px-1 py-0 text-red-600 border-red-500/30">
                {c.id}
              </Badge>)}
            {failedCriteria.length > 3 && <Badge variant="outline" className="text-[8px] px-1 py-0 text-gray-500 border-gray-300">
                +{failedCriteria.length - 3}
              </Badge>}
          </div>}
      </div>

      {/* Expanded: Full acceptance criteria + failure details */}
      {expanded && <div className="border-t border-gray-200 p-3 space-y-3">
          <AcceptanceCriteriaList criteria={criteria} />

          {/* Failure details with runbooks */}
          {gate.failure_details?.length > 0 && <div className="space-y-2 pt-1">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">
                Failure Details & Runbooks
              </div>
              {gate.failure_details.map((fd, i) => <div key={fd.id || i} className="bg-red-50 border border-red-500/20 rounded-md p-2 space-y-1">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-3 w-3 text-red-600" />
                    <span className="text-[10px] text-red-700 font-mono">{fd.criteria_id}</span>
                    <Badge variant="outline" className="text-[8px] px-1 py-0 text-red-600 border-red-500/30">
                      {fd.severity}
                    </Badge>
                  </div>
                  <p className="text-[10px] text-gray-600">{fd.impact}</p>
                  <div className="flex items-center gap-3 text-[10px]">
                    <a href={fd.runbook} className="text-blue-600 hover:text-blue-700 flex items-center gap-1">
                      <ExternalLink className="h-2.5 w-2.5" /> Runbook
                    </a>
                    <span className="text-gray-500">Rollback: {fd.rollback}</span>
                  </div>
                </div>)}
            </div>}
        </div>}
    </div>;
}
function TrendChart({
  data
}) {
  const {
    t
  } = useTranslation();
  if (!data || data.length < 2) {
    return <div className="text-xs text-gray-500 text-center py-4">
        {t('cm.components_CICDPipelineDashboard.trend_icin_en_az_2_calistirma_gerekli')}
      </div>;
  }
  const chartData = data.map(d => ({
    name: d.date ? new Date(d.date).toLocaleDateString("tr-TR", {
      day: "2-digit",
      month: "short"
    }) : "",
    rate: d.pass_rate,
    verdict: d.verdict
  }));
  return <div data-testid="cicd-trend-chart">
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={chartData} margin={{
        top: 5,
        right: 5,
        left: -20,
        bottom: 0
      }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="name" tick={{
          fontSize: 9,
          fill: "#71717a"
        }} />
          <YAxis domain={[0, 100]} tick={{
          fontSize: 9,
          fill: "#71717a"
        }} />
          <Tooltip content={<PipelineTooltip />} />
          <Line type="monotone" dataKey="rate" name="Basari" stroke="#22d3ee" strokeWidth={2} dot={props => {
          const {
            cx,
            cy,
            payload
          } = props;
          const fill = payload.verdict === "PASS" ? "#10b981" : payload.verdict === "BLOCK" ? "#ef4444" : "#eab308";
          return <circle key={cx} cx={cx} cy={cy} r={3.5} fill={fill} stroke="none" />;
        }} />
        </LineChart>
      </ResponsiveContainer>
    </div>;
}
export function CICDPipelineDashboard() {
  const {
    t
  } = useTranslation();
  const [badges, setBadges] = useState(null);
  const [runs, setRuns] = useState([]);
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null); // which tier is running

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [badgeRes, runsRes, trendRes] = await Promise.allSettled([axios.get("/ops/cicd/health-badges"), axios.get("/ops/cicd/runs?limit=10"), axios.get("/ops/cicd/trends?limit=30")]);
      if (badgeRes.status === "fulfilled") setBadges(badgeRes.value.data?.badges || {});
      if (runsRes.status === "fulfilled") setRuns(runsRes.value.data?.runs || []);
      if (trendRes.status === "fulfilled") setTrends(trendRes.value.data);
    } catch {
      toast.error("CI/CD verisi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);
  const triggerRun = useCallback(async tier => {
    setRunning(tier);
    try {
      const res = await axios.post("/ops/cicd/run", {
        tier,
        triggered_by: "operator"
      });
      const gate = res.data?.deploy_gate || {};
      if (gate.verdict === "PASS") {
        toast.success(`${TIER_LABELS[tier]?.name || tier}: Tüm kriterler karsilandi — PASS`);
      } else if (gate.verdict === "BLOCK") {
        toast.error(`${TIER_LABELS[tier]?.name || tier}: Deploy ENGELLENDI — ${gate.message}`);
      } else {
        toast.warning(`${TIER_LABELS[tier]?.name || tier}: ${gate.message || "Tamamlandi"}`);
      }
      await fetchAll();
    } catch {
      toast.error(`${TIER_LABELS[tier]?.name || tier} pipeline başarısız`);
    } finally {
      setRunning(null);
    }
  }, [fetchAll]);
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);
  if (loading) {
    return <div className="space-y-4" data-testid="cicd-dashboard-loading">
        <Skeleton className="h-8 w-56 bg-gray-100" />
        <div className="grid grid-cols-3 gap-3">
          <Skeleton className="h-16 bg-gray-100" />
          <Skeleton className="h-16 bg-gray-100" />
          <Skeleton className="h-16 bg-gray-100" />
        </div>
        <Skeleton className="h-40 bg-gray-100" />
      </div>;
  }
  const badgeList = badges ? Object.values(badges) : [];
  const overallTrend = trends?.overall_trend || [];
  return <div className="space-y-4" data-testid="cicd-pipeline-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-cyan-600" />
            CI/CD Pipeline Validation
          </h3>
          <p className="text-[10px] text-gray-500 mt-0.5">
            {t('cm.components_CICDPipelineDashboard.3_katmanli_sandbox_dogrulama_pr_gate_sta')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-7 text-xs text-gray-500" onClick={fetchAll} disabled={loading} data-testid="cicd-refresh-btn">
            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} /> {t('cm.components_CICDPipelineDashboard.yenile')}
          </Button>
        </div>
      </div>

      {/* Health Badges — sandbox / staging / prod ayrı */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="cicd-health-badges">
        {badgeList.map(b => <HealthBadge key={b.tier} badge={b} />)}
        {badgeList.length === 0 && <div className="col-span-3 text-xs text-gray-500 text-center py-3">
            {t('cm.components_CICDPipelineDashboard.henuz_pipeline_calistirilmadi')}
          </div>}
      </div>

      {/* Tier Action Buttons */}
      <div className="flex items-center gap-2">
        {Object.entries(TIER_LABELS).map(([key, label]) => <Button key={key} variant="outline" size="sm" className={`h-7 text-xs ${label.color} ${label.border} ${label.bg} hover:opacity-80`} onClick={() => triggerRun(key)} disabled={running !== null} data-testid={`cicd-trigger-${key}`}>
            {running === key ? <RefreshCw className="h-3 w-3 mr-1 animate-spin" /> : <Play className="h-3 w-3 mr-1" />}
            {label.name}
          </Button>)}
      </div>

      {/* Trend Chart */}
      {overallTrend.length > 0 && <Card className="bg-white border-gray-200" data-testid="cicd-trend-card">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
              <BarChart3 className="h-3.5 w-3.5" /> Pipeline Trend
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <TrendChart data={overallTrend} />
          </CardContent>
        </Card>}

      {/* Recent Runs */}
      <div className="space-y-2" data-testid="cicd-recent-runs">
        <div className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
          <Clock className="h-3.5 w-3.5" /> Son Pipeline Calistirmalari
        </div>
        {runs.length === 0 ? <Card className="bg-white border-gray-200">
            <CardContent className="p-6 text-center">
              <GitBranch className="h-8 w-8 text-gray-500 mx-auto mb-3" />
              <p className="text-sm text-gray-600">{t('cm.components_CICDPipelineDashboard.henuz_ci_cd_pipeline_calistirilmadi')}</p>
              <p className="text-xs text-gray-500 mt-1">
                Yukaridaki butonlardan bir tier secip calistirabilirsiniz
              </p>
            </CardContent>
          </Card> : <div className="space-y-2">
            {runs.map(run => <RunCard key={run.run_id} run={run} />)}
          </div>}
      </div>
    </div>;
}