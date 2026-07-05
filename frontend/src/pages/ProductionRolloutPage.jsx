import { t } from "i18next";
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { ArrowLeft, Shield, Zap, Activity, Play, RefreshCw, Loader2, CheckCircle2, XCircle, AlertTriangle, Target, TrendingUp, Clock, Server, Rocket, Globe, Radio, Eye, ChevronRight, Layers, Lock, Database, MonitorCheck, BarChart3 } from "lucide-react";
const API = "";

/* ── Helper Components ────────────────────────────────────────────── */

function ScoreRing({
  score,
  size = 100
}) {
  const color = score >= 90 ? "#34d399" : score >= 75 ? "#a3e635" : score >= 60 ? "#fbbf24" : "#f87171";
  const circumference = 2 * Math.PI * 38;
  const offset = circumference - score / 100 * circumference;
  return <div className="relative flex items-center justify-center" style={{
    width: size,
    height: size
  }}>
      <svg width={size} height={size} viewBox="0 0 100 100" className="-rotate-90">
        <circle cx="50" cy="50" r="38" fill="none" stroke="#27272a" strokeWidth="5" />
        <circle cx="50" cy="50" r="38" fill="none" stroke={color} strokeWidth="5" strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" style={{
        transition: "stroke-dashoffset 0.6s ease"
      }} />
      </svg>
      <span className="absolute text-xl font-bold" style={{
      color
    }}>{score}%</span>
    </div>;
}
function StatusBadge({
  status
}) {
  const map = {
    pass: {
      color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
      label: "Pass"
    },
    passed: {
      color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
      label: "Passed"
    },
    completed: {
      color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
      label: "Completed"
    },
    fail: {
      color: "bg-red-500/20 text-red-400 border-red-500/30",
      label: "Fail"
    },
    failed: {
      color: "bg-red-500/20 text-red-400 border-red-500/30",
      label: "Failed"
    },
    warn: {
      color: "bg-amber-500/20 text-amber-400 border-amber-500/30",
      label: "Warning"
    },
    pending: {
      color: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
      label: "Pending"
    },
    active: {
      color: "bg-blue-500/20 text-blue-400 border-blue-500/30",
      label: "Active"
    },
    manual_required: {
      color: "bg-violet-500/20 text-violet-400 border-violet-500/30",
      label: "Manual"
    }
  };
  const s = map[status] || map.pending;
  return <Badge data-testid={`status-badge-${status}`} className={`text-[10px] border ${s.color}`}>{s.label}</Badge>;
}
function SectionHeader({
  icon: Icon,
  title,
  count
}) {
  return <div className="flex items-center gap-2 mb-3">
      <Icon className="w-4 h-4 text-zinc-400" />
      <h3 className="text-sm font-semibold text-zinc-200">{title}</h3>
      {count !== undefined && <Badge className="text-[10px] bg-zinc-800 text-zinc-400 border-zinc-700">{count}</Badge>}
    </div>;
}

/* ── Main Component ───────────────────────────────────────────────── */

export default function ProductionRolloutDashboard() {
  const navigate = useNavigate();
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  // Data states
  const [envValidation, setEnvValidation] = useState(null);
  const [canaryPlan, setCanaryPlan] = useState(null);
  const [canaryStatus, setCanaryStatus] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [monitoring, setMonitoring] = useState(null);
  const [loadScenarios, setLoadScenarios] = useState(null);
  const [isolationResult, setIsolationResult] = useState(null);
  const [postLaunch, setPostLaunch] = useState(null);
  const [maturityScore, setMaturityScore] = useState(null);
  const [successCriteria, setSuccessCriteria] = useState(null);
  const [runningAction, setRunningAction] = useState(null);
  useEffect(() => {
    const t = localStorage.getItem("token");
    if (t) setToken(t);
  }, []);
  const headers = useCallback(() => ({}), []);
  const loadData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [envRes, planRes, statusRes, onbRes, monRes, loadRes, isoRes, plRes, matRes, scRes] = await Promise.allSettled([axios.get(`/production/env/validate`, {
        headers: headers()
      }), axios.get(`/production/canary/plan`, {
        headers: headers()
      }), axios.get(`/production/canary/status`, {
        headers: headers()
      }), axios.get(`/production/pilot/onboarding`, {
        headers: headers()
      }), axios.get(`/production/monitoring/dashboard`, {
        headers: headers()
      }), axios.get(`/production/load/scenarios`, {
        headers: headers()
      }), axios.get(`/production/isolation/validate`, {
        headers: headers()
      }), axios.get(`/production/post-launch/status`, {
        headers: headers()
      }), axios.get(`/production/maturity/score`, {
        headers: headers()
      }), axios.get(`/production/pilot/success-criteria`, {
        headers: headers()
      })]);
      if (envRes.status === "fulfilled") setEnvValidation(envRes.value.data?.data);
      if (planRes.status === "fulfilled") setCanaryPlan(planRes.value.data?.data);
      if (statusRes.status === "fulfilled") setCanaryStatus(statusRes.value.data?.data);
      if (onbRes.status === "fulfilled") setOnboarding(onbRes.value.data?.data);
      if (monRes.status === "fulfilled") setMonitoring(monRes.value.data?.data);
      if (loadRes.status === "fulfilled") setLoadScenarios(loadRes.value.data?.data);
      if (isoRes.status === "fulfilled") setIsolationResult(isoRes.value.data?.data);
      if (plRes.status === "fulfilled") setPostLaunch(plRes.value.data?.data);
      if (matRes.status === "fulfilled") setMaturityScore(matRes.value.data?.data);
      if (scRes.status === "fulfilled") setSuccessCriteria(scRes.value.data?.data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [headers, token]);
  useEffect(() => {
    loadData();
  }, [loadData]);
  const runAction = async (url, method = "post", body = null) => {
    setRunningAction(url);
    try {
      const res = method === "post" ? await axios.post(`${API}${url}`, body, {
        headers: headers()
      }) : await axios.get(`${API}${url}`, {
        headers: headers()
      });
      await loadData();
      return res.data;
    } catch (e) {
      console.error(e);
    } finally {
      setRunningAction(null);
    }
  };
  const TABS = [{
    id: "overview",
    label: "Overview",
    icon: Target
  }, {
    id: "environment",
    label: "Environment",
    icon: Server
  }, {
    id: "canary",
    label: "Canary Deploy",
    icon: Rocket
  }, {
    id: "onboarding",
    label: "Pilot Onboarding",
    icon: Globe
  }, {
    id: "monitoring",
    label: "Monitoring",
    icon: Radio
  }, {
    id: "load",
    label: "Load Validation",
    icon: Zap
  }, {
    id: "isolation",
    label: "Tenant Isolation",
    icon: Lock
  }, {
    id: "post-launch",
    label: "Post-Launch",
    icon: Eye
  }];
  if (loading && !envValidation) {
    return <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
      </div>;
  }
  return <div data-testid="production-rollout-dashboard" className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-[1400px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate("/app/dashboard")} data-testid="back-btn">
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <h1 className="text-lg font-bold tracking-tight">{t("cm.pages_ProductionRolloutPage.production_rollout")}</h1>
              <p className="text-xs text-zinc-500">{t("cm.pages_ProductionRolloutPage.phase_7_pilot_readiness_deploy")}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {maturityScore && <Badge data-testid="maturity-badge" className={`text-xs border ${maturityScore.go_live_ready ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-amber-500/20 text-amber-400 border-amber-500/30"}`}>
                {maturityScore.maturity_name} ({maturityScore.overall_score})
              </Badge>}
            <Button variant="ghost" size="sm" onClick={loadData} data-testid="refresh-btn">
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-zinc-800 bg-zinc-950/50">
        <div className="max-w-[1400px] mx-auto px-4 flex gap-0 overflow-x-auto">
          {TABS.map(tab => <button key={tab.id} data-testid={`tab-${tab.id}`} onClick={() => setActiveTab(tab.id)} className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === tab.id ? "border-emerald-400 text-emerald-400" : "border-transparent text-zinc-500 hover:text-zinc-300"}`}>
              <tab.icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>)}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-[1400px] mx-auto px-4 py-4">
        {activeTab === "overview" && <OverviewTab env={envValidation} maturity={maturityScore} canary={canaryStatus} onboarding={onboarding} isolation={isolationResult} successCriteria={successCriteria} />}
        {activeTab === "environment" && <EnvironmentTab data={envValidation} onRefresh={() => runAction("/api/production/env/validate", "get")} loading={!!runningAction} />}
        {activeTab === "canary" && <CanaryTab plan={canaryPlan} status={canaryStatus} onAdvance={stageId => runAction("/api/production/canary/advance", "post", {
        target_stage_id: stageId
      })} onRollback={reason => runAction("/api/production/canary/rollback", "post", {
        reason
      })} running={!!runningAction} />}
        {activeTab === "onboarding" && <OnboardingTab data={onboarding} onCompleteStep={stepId => runAction("/api/production/pilot/onboarding/complete-step", "post", {
        step_id: stepId
      })} onRunAuto={() => runAction("/api/production/pilot/onboarding/run-auto")} running={!!runningAction} />}
        {activeTab === "monitoring" && <MonitoringTab data={monitoring} onGenerateReport={() => runAction("/api/production/monitoring/daily-report")} running={!!runningAction} />}
        {activeTab === "load" && <LoadTab scenarios={loadScenarios} onRun={id => runAction("/api/production/load/run", "post", {
        scenario_id: id
      })} running={!!runningAction} />}
        {activeTab === "isolation" && <IsolationTab data={isolationResult} onValidate={() => runAction("/api/production/isolation/validate", "get")} running={!!runningAction} />}
        {activeTab === "post-launch" && <PostLaunchTab data={postLaunch} />}
      </div>
    </div>;
}

/* ── Overview Tab ─────────────────────────────────────────────────── */

function OverviewTab({
  env,
  maturity,
  canary,
  onboarding,
  isolation,
  successCriteria
}) {
  const cards = [{
    title: "Environment",
    icon: Server,
    score: env?.overall_score || 0,
    status: env?.ready ? "Ready" : "Not Ready",
    color: env?.ready ? "text-emerald-400" : "text-amber-400"
  }, {
    title: "Canary Deploy",
    icon: Rocket,
    score: canary?.current_stage ? 50 : 0,
    status: canary?.current_stage_name || "Not Started",
    color: canary?.status === "active" ? "text-blue-400" : "text-zinc-400"
  }, {
    title: "Pilot Onboarding",
    icon: Globe,
    score: onboarding?.progress || 0,
    status: `${onboarding?.completed_count || 0}/${onboarding?.total_steps || 0} steps`,
    color: (onboarding?.progress || 0) >= 80 ? "text-emerald-400" : "text-amber-400"
  }, {
    title: "Tenant Isolation",
    icon: Lock,
    score: isolation?.score || 0,
    status: isolation?.no_data_leakage ? "No Leakage" : "Check Needed",
    color: isolation?.critical_all_pass ? "text-emerald-400" : "text-red-400"
  }];
  return <div className="space-y-4">
      {/* Maturity Score Banner */}
      {maturity && <Card data-testid="maturity-banner" className="bg-gradient-to-r from-zinc-900 to-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="flex items-center gap-6">
              <ScoreRing score={maturity.overall_score} size={90} />
              <div className="flex-1">
                <h2 className="text-lg font-bold">{maturity.maturity_name}</h2>
                <p className="text-xs text-zinc-500 mt-0.5">{t("cm.pages_ProductionRolloutPage.platform_maturity_level")}{maturity.maturity_level}</p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge className={`text-[10px] border ${maturity.go_live_ready ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-red-500/20 text-red-400 border-red-500/30"}`}>
                    {maturity.go_live_ready ? "GO-LIVE READY" : "NOT READY"}
                  </Badge>
                  {maturity.blockers?.length > 0 && <span className="text-[10px] text-red-400">{maturity.blockers.length}{t("cm.pages_ProductionRolloutPage.blocker_s")}</span>}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {maturity.categories && Object.entries(maturity.categories).slice(0, 6).map(([key, val]) => <div key={key} className="text-center">
                    <div className="text-sm font-bold text-zinc-200">{val.score}%</div>
                    <div className="text-[9px] text-zinc-600">{key.replace(/_/g, " ")}</div>
                  </div>)}
              </div>
            </div>
          </CardContent>
        </Card>}

      {/* Quick Status Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {cards.map(card => <Card key={card.title} className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="flex items-center justify-between mb-2">
                <card.icon className="w-4 h-4 text-zinc-500" />
                <span className="text-lg font-bold text-zinc-100">{card.score}%</span>
              </div>
              <p className="text-xs font-medium text-zinc-300">{card.title}</p>
              <p className={`text-[10px] ${card.color}`}>{card.status}</p>
            </CardContent>
          </Card>)}
      </div>

      {/* Pilot Success Criteria */}
      {successCriteria && <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-sm flex items-center gap-2">
              <Target className="w-4 h-4 text-zinc-400" />{t("cm.pages_ProductionRolloutPage.pilot_success_criteria")}<Badge className={`text-[10px] border ${successCriteria.pilot_success ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-amber-500/20 text-amber-400 border-amber-500/30"}`}>
                {successCriteria.met_count}/{successCriteria.total}{t("cm.pages_ProductionRolloutPage.met")}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
              {successCriteria.criteria?.map(c => <div key={c.id} data-testid={`criterion-${c.id}`} className="flex items-center gap-2 bg-zinc-800/50 rounded px-2 py-1.5">
                  {c.met ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> : <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />}
                  <div className="min-w-0">
                    <p className="text-[11px] text-zinc-300 truncate">{c.name}</p>
                    <p className="text-[9px] text-zinc-600">{t("cm.pages_ProductionRolloutPage.target")}{c.target}</p>
                  </div>
                </div>)}
            </div>
          </CardContent>
        </Card>}
    </div>;
}

/* ── Environment Tab ──────────────────────────────────────────────── */

function EnvironmentTab({
  data,
  onRefresh,
  loading
}) {
  if (!data) return <p className="text-zinc-500 text-sm">{t("cm.pages_ProductionRolloutPage.loading_environment_validation")}</p>;
  const categories = data.categories || {};
  return <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionHeader icon={Server} title={t("cm.pages_ProductionRolloutPage.production_environment_validat")} count={data.total_checks} />
        <Button size="sm" variant="outline" onClick={onRefresh} disabled={loading} data-testid="revalidate-env-btn">
          {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}{t("cm.pages_ProductionRolloutPage.revalidate")}</Button>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <ScoreRing score={data.overall_score} size={70} />
        <div>
          <Badge className={`text-xs border ${data.ready ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-red-500/20 text-red-400 border-red-500/30"}`}>
            {data.ready ? "PRODUCTION READY" : "NOT READY"}
          </Badge>
          <p className="text-[10px] text-zinc-600 mt-1">{data.passed_checks}/{data.total_checks}{t("cm.pages_ProductionRolloutPage.checks_passed")}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Object.entries(categories).map(([catName, catData]) => <Card key={catName} className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-xs font-medium flex items-center justify-between">
                <span className="capitalize">{catName.replace(/_/g, " ")}</span>
                <span className="text-zinc-400">{catData.passed}/{catData.total}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 space-y-1.5">
              {catData.checks?.map(check => <div key={check.name} className="flex items-center gap-2" data-testid={`env-check-${check.name}`}>
                  {check.status === "pass" ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : check.status === "warn" ? <AlertTriangle className="w-3 h-3 text-amber-400" /> : <XCircle className="w-3 h-3 text-red-400" />}
                  <span className="text-[11px] text-zinc-300">{check.name.replace(/_/g, " ")}</span>
                </div>)}
              {catData.issues?.length > 0 && catData.issues.map((issue, i) => <p key={issue.id || i} className="text-[10px] text-amber-400/80 flex items-center gap-1 mt-1">
                  <AlertTriangle className="w-2.5 h-2.5 shrink-0" /> {issue}
                </p>)}
            </CardContent>
          </Card>)}
      </div>
    </div>;
}

/* ── Canary Tab ───────────────────────────────────────────────────── */

function CanaryTab({
  plan,
  status,
  onAdvance,
  onRollback,
  running
}) {
  const stages = plan?.stages || [];
  const currentStageId = status?.current_stage_id;
  const [rollbackReason, setRollbackReason] = useState("");
  const currentIdx = stages.findIndex(s => s.id === currentStageId);
  const nextStage = currentIdx < stages.length - 1 ? stages[currentIdx + 1] : null;
  return <div className="space-y-4">
      <SectionHeader icon={Rocket} title={t("cm.pages_ProductionRolloutPage.canary_deployment_strategy")} />

      {/* Stage Pipeline */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {stages.map((stage, idx) => {
        const isActive = stage.id === currentStageId;
        const isPast = idx < currentIdx;
        return <div key={stage.id} className="flex items-center gap-2" data-testid={`canary-stage-${stage.id}`}>
              <div className={`rounded-lg border px-3 py-2 min-w-[140px] transition-all ${isActive ? "bg-blue-500/10 border-blue-500/40" : isPast ? "bg-emerald-500/10 border-emerald-500/30" : "bg-zinc-900/50 border-zinc-800"}`}>
                <p className={`text-[10px] font-medium ${isActive ? "text-blue-400" : isPast ? "text-emerald-400" : "text-zinc-500"}`}>{t("cm.pages_ProductionRolloutPage.stage")}{idx + 1}</p>
                <p className="text-xs text-zinc-300">{stage.name}</p>
                <p className="text-[9px] text-zinc-600 mt-0.5">{stage.traffic_percent}{t("cm.pages_ProductionRolloutPage._traffic")}</p>
              </div>
              {idx < stages.length - 1 && <ChevronRight className="w-3 h-3 text-zinc-700 shrink-0" />}
            </div>;
      })}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {nextStage && <Button size="sm" onClick={() => onAdvance(nextStage.id)} disabled={running} data-testid="advance-stage-btn">
            {running ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Play className="w-3 h-3 mr-1" />}{t("cm.pages_ProductionRolloutPage.advance_to")}{nextStage.name}
          </Button>}
        {currentStageId && status?.status !== "rolled_back" && <div className="flex items-center gap-1">
            <input type="text" value={rollbackReason} onChange={e => setRollbackReason(e.target.value)} placeholder={t("cm.pages_ProductionRolloutPage.rollback_reason")} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 w-48" />
            <Button size="sm" variant="destructive" onClick={() => {
          if (rollbackReason) onRollback(rollbackReason);
        }} disabled={running || !rollbackReason} data-testid="rollback-btn">{t("cm.pages_ProductionRolloutPage.rollback")}</Button>
          </div>}
      </div>

      {/* Rollback Triggers */}
      {plan?.rollback_triggers && <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-xs">{t("cm.pages_ProductionRolloutPage.rollback_triggers")}</CardTitle></CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
              {plan.rollback_triggers.map(t => <div key={t.id} className="bg-zinc-800/50 rounded px-2 py-1.5" data-testid={`trigger-${t.id}`}>
                  <p className="text-[11px] text-zinc-300">{t.name}</p>
                  <p className="text-[9px] text-zinc-600">{t.metric} &gt; {t.threshold}</p>
                  <Badge className="text-[8px] mt-0.5 bg-zinc-700/50 text-zinc-400 border-zinc-600">{t.action}</Badge>
                </div>)}
            </div>
          </CardContent>
        </Card>}

      {/* Canary Metrics */}
      {plan?.canary_metrics && <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-xs">{t("cm.pages_ProductionRolloutPage.canary_monitoring_metrics")}</CardTitle></CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="grid grid-cols-3 lg:grid-cols-6 gap-2">
              {plan.canary_metrics.map(m => <div key={m.id} className="text-center bg-zinc-800/30 rounded p-2">
                  <p className="text-[10px] text-zinc-400">{m.name}</p>
                  <p className="text-xs font-medium text-zinc-200 mt-0.5">{m.target}</p>
                </div>)}
            </div>
          </CardContent>
        </Card>}
    </div>;
}

/* ── Onboarding Tab ───────────────────────────────────────────────── */

function OnboardingTab({
  data,
  onCompleteStep,
  onRunAuto,
  running
}) {
  if (!data) return <p className="text-zinc-500 text-sm">{t("cm.pages_ProductionRolloutPage.no_onboarding_data")}</p>;
  const steps = data.steps_definition || [];
  const stepsStatus = data.steps || {};
  const categories = [...new Set(steps.map(s => s.category))];
  return <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionHeader icon={Globe} title={t("cm.pages_ProductionRolloutPage.pilot_hotel_onboarding")} count={data.total_steps} />
        <div className="flex items-center gap-2">
          {data.progress !== undefined && <span className="text-xs text-zinc-400">{data.progress}{t("cm.pages_ProductionRolloutPage._complete")}</span>}
          <Button size="sm" onClick={onRunAuto} disabled={running} data-testid="run-auto-validation-btn">
            {running ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Play className="w-3 h-3 mr-1" />}{t("cm.pages_ProductionRolloutPage.run_auto_validations")}</Button>
        </div>
      </div>

      {data.progress !== undefined && <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
          <div className="h-full bg-emerald-400 rounded-full transition-all" style={{
        width: `${data.progress}%`
      }} />
        </div>}

      {categories.map(cat => <Card key={cat} className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs capitalize">{cat.replace(/_/g, " ")}</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-1.5">
            {steps.filter(s => s.category === cat).map(step => {
          const ss = stepsStatus[step.id] || {
            status: "pending"
          };
          return <div key={step.id} className="flex items-center justify-between py-1" data-testid={`step-${step.id}`}>
                  <div className="flex items-center gap-2">
                    {ss.status === "completed" ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : ss.status === "failed" ? <XCircle className="w-3.5 h-3.5 text-red-400" /> : <div className="w-3.5 h-3.5 rounded-full border border-zinc-600" />}
                    <span className="text-xs text-zinc-300">{step.name}</span>
                    {step.auto && <Badge className="text-[8px] bg-blue-500/10 text-blue-400 border-blue-500/20">{t("cm.pages_ProductionRolloutPage.auto")}</Badge>}
                  </div>
                  <div className="flex items-center gap-1">
                    <StatusBadge status={ss.status} />
                    {ss.status === "pending" && !step.auto && <Button size="sm" variant="ghost" className="h-5 text-[10px] px-1.5" onClick={() => onCompleteStep(step.id)} disabled={running}>{t("cm.pages_ProductionRolloutPage.complete")}</Button>}
                  </div>
                </div>;
        })}
          </CardContent>
        </Card>)}
    </div>;
}

/* ── Monitoring Tab ───────────────────────────────────────────────── */

function MonitoringTab({
  data,
  onGenerateReport,
  running
}) {
  if (!data) return <p className="text-zinc-500 text-sm">{t("cm.pages_ProductionRolloutPage.loading_monitoring")}</p>;
  return <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionHeader icon={Radio} title={t("cm.pages_ProductionRolloutPage.pilot_monitoring_dashboard")} />
        <Button size="sm" onClick={onGenerateReport} disabled={running} data-testid="generate-report-btn">
          {running ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <BarChart3 className="w-3 h-3 mr-1" />}{t("cm.pages_ProductionRolloutPage.generate_daily_report")}</Button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard title={t("cm.pages_ProductionRolloutPage.reservations")} value={data.reservation_metrics?.total || 0} sub={`${data.reservation_metrics?.last_24h || 0} last 24h`} />
        <MetricCard title={t("cm.pages_ProductionRolloutPage.sync_success")} value={`${data.sync_metrics?.success_rate || 0}%`} sub={`${data.sync_metrics?.total_syncs_24h || 0} syncs`} />
        <MetricCard title={t("cm.pages_ProductionRolloutPage.queue_pending")} value={data.queue_health?.pending_tasks || 0} sub={data.queue_health?.healthy ? "Healthy" : "Attention needed"} alert={!data.queue_health?.healthy} />
        <MetricCard title={t("cm.pages_ProductionRolloutPage.active_incidents")} value={data.incident_summary?.active || 0} sub={`${data.incident_summary?.total_24h || 0} in 24h`} alert={(data.incident_summary?.active || 0) > 0} />
      </div>

      {/* Night Audit Status */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MonitorCheck className="w-4 h-4 text-zinc-400" />
              <span className="text-xs text-zinc-300">{t("cm.pages_ProductionRolloutPage.night_audit")}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-400">{data.night_audit_status?.business_date || "N/A"}</span>
              <StatusBadge status={data.night_audit_status?.status || "pending"} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Active Alerts */}
      {data.alerts && data.alerts.length > 0 && <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-xs">{t("cm.pages_ProductionRolloutPage.active_alerts")}</CardTitle></CardHeader>
          <CardContent className="px-4 pb-3 space-y-1">
            {(data.alerts || []).map((alert, i) => <div key={alert.id || i} className="flex items-center gap-2 text-xs bg-zinc-800/50 rounded px-2 py-1">
                <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />
                <span className="text-zinc-300">{alert.rule_name || alert.alert_type || "Alert"}</span>
                <Badge className="text-[8px] bg-red-500/10 text-red-400 border-red-500/20 ml-auto">{alert.severity}</Badge>
              </div>)}
          </CardContent>
        </Card>}
    </div>;
}
function MetricCard({
  title,
  value,
  sub,
  alert
}) {
  return <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="p-3">
        <p className="text-[10px] text-zinc-500">{title}</p>
        <p className={`text-lg font-bold ${alert ? "text-amber-400" : "text-zinc-100"}`}>{value}</p>
        <p className={`text-[10px] ${alert ? "text-amber-400/70" : "text-zinc-600"}`}>{sub}</p>
      </CardContent>
    </Card>;
}

/* ── Load Tab ─────────────────────────────────────────────────────── */

function LoadTab({
  scenarios,
  onRun,
  running
}) {
  const items = scenarios?.scenarios || [];
  return <div className="space-y-4">
      <SectionHeader icon={Zap} title={t("cm.pages_ProductionRolloutPage.production_load_validation")} count={items.length} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map(s => <Card key={s.id} className="bg-zinc-900/50 border-zinc-800" data-testid={`load-scenario-${s.id}`}>
            <CardContent className="p-3">
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-medium text-zinc-200">{s.name}</p>
                <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2" onClick={() => onRun(s.id)} disabled={running} data-testid={`run-load-${s.id}`}>
                  {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3 mr-0.5" />}{t("cm.pages_ProductionRolloutPage.run")}</Button>
              </div>
              <p className="text-[10px] text-zinc-500 mb-2">{s.description}</p>
              <div className="flex flex-wrap gap-1">
                {Object.entries(s.thresholds || {}).map(([k, v]) => <Badge key={k} className="text-[8px] bg-zinc-800 text-zinc-400 border-zinc-700">{k}: {v}</Badge>)}
              </div>
            </CardContent>
          </Card>)}
      </div>
    </div>;
}

/* ── Isolation Tab ────────────────────────────────────────────────── */

function IsolationTab({
  data,
  onValidate,
  running
}) {
  if (!data) return <div>
      <SectionHeader icon={Lock} title={t("cm.pages_ProductionRolloutPage.tenant_isolation_confirmation")} />
      <Button size="sm" onClick={onValidate} disabled={running} data-testid="run-isolation-btn">
        {running ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Shield className="w-3 h-3 mr-1" />}{t("cm.pages_ProductionRolloutPage.run_isolation_validation")}</Button>
    </div>;
  return <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionHeader icon={Lock} title={t("cm.pages_ProductionRolloutPage.tenant_isolation_confirmation")} count={data.total} />
        <Button size="sm" variant="outline" onClick={onValidate} disabled={running} data-testid="rerun-isolation-btn">
          <RefreshCw className="w-3 h-3 mr-1" />{t("cm.pages_ProductionRolloutPage.revalidate")}</Button>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <ScoreRing score={data.score} size={70} />
        <div>
          <Badge className={`text-xs border ${data.critical_all_pass ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-red-500/20 text-red-400 border-red-500/30"}`}>
            {data.critical_all_pass ? "ALL CRITICAL PASS" : "CRITICAL FAILURES"}
          </Badge>
          <p className="text-[10px] text-zinc-600 mt-1">{data.passed}/{data.total}{t("cm.pages_ProductionRolloutPage.tests_passed")}</p>
        </div>
      </div>

      <div className="space-y-1.5">
        {data.tests?.map(test => <div key={test.test_id} className="flex items-center justify-between bg-zinc-900/50 border border-zinc-800 rounded-lg px-3 py-2" data-testid={`isolation-test-${test.test_id}`}>
            <div className="flex items-center gap-2">
              {test.passed ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <XCircle className="w-3.5 h-3.5 text-red-400" />}
              <div>
                <p className="text-xs text-zinc-300">{test.name}</p>
                <p className="text-[9px] text-zinc-600">{test.details}</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {test.critical && <Badge className="text-[8px] bg-red-500/10 text-red-400 border-red-500/20">{t("cm.pages_ProductionRolloutPage.critical")}</Badge>}
              <StatusBadge status={test.passed ? "passed" : "failed"} />
            </div>
          </div>)}
      </div>
    </div>;
}

/* ── Post-Launch Tab ──────────────────────────────────────────────── */

function PostLaunchTab({
  data
}) {
  if (!data) return <p className="text-zinc-500 text-sm">{t("cm.pages_ProductionRolloutPage.loading_post_launch_status")}</p>;
  return <div className="space-y-4">
      <SectionHeader icon={Eye} title={t("cm.pages_ProductionRolloutPage.post_launch_monitoring")} />

      {/* Continuous Monitors */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-xs">{t("cm.pages_ProductionRolloutPage.continuous_monitors")}</CardTitle></CardHeader>
        <CardContent className="px-4 pb-3">
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
            {data.monitors?.map(m => <div key={m.id} className="flex items-center gap-2 bg-zinc-800/30 rounded px-2 py-1.5" data-testid={`monitor-${m.id}`}>
                <div className={`w-1.5 h-1.5 rounded-full ${m.active ? "bg-emerald-400" : "bg-zinc-600"}`} />
                <div>
                  <p className="text-[11px] text-zinc-300">{m.name}</p>
                  <p className="text-[9px] text-zinc-600">{t("cm.pages_ProductionRolloutPage.every")}{m.interval_sec}s</p>
                </div>
              </div>)}
          </div>
        </CardContent>
      </Card>

      {/* Scheduled Drills */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-xs">{t("cm.pages_ProductionRolloutPage.scheduled_drills")}</CardTitle></CardHeader>
        <CardContent className="px-4 pb-3 space-y-2">
          {data.scheduled_drills?.map(drill => <div key={drill.schedule_id} className="flex items-center justify-between bg-zinc-800/30 rounded px-3 py-2" data-testid={`drill-${drill.schedule_id}`}>
              <div>
                <p className="text-xs text-zinc-300">{drill.name}</p>
                <p className="text-[9px] text-zinc-600">{t("cm.pages_ProductionRolloutPage.frequency")}{drill.frequency}</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-zinc-400">{t("cm.pages_ProductionRolloutPage.last")}{drill.last_run ? new Date(drill.last_run).toLocaleDateString() : "Never"}</p>
                <Badge className={`text-[8px] ${drill.overdue ? "bg-amber-500/20 text-amber-400 border-amber-500/30" : "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"}`}>
                  {drill.overdue ? "Overdue" : "On Track"}
                </Badge>
              </div>
            </div>)}
        </CardContent>
      </Card>

      {/* 30-Day Stats */}
      <div className="grid grid-cols-2 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] text-zinc-500">{t("cm.pages_ProductionRolloutPage.incidents_30d")}</p>
            <p className="text-2xl font-bold text-zinc-100">{data.incidents_30d || 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] text-zinc-500">{t("cm.pages_ProductionRolloutPage.monitoring")}</p>
            <p className="text-2xl font-bold text-emerald-400">{data.monitoring_active ? "Active" : "Inactive"}</p>
          </CardContent>
        </Card>
      </div>
    </div>;
}