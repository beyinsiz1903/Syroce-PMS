import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from "react";
import Layout from "../components/Layout";
import { Shield, Activity, Server, Database, Radio, Bell, Rocket, RefreshCw, ChevronRight, AlertTriangle, CheckCircle2, XCircle, Clock, Zap, Settings, FileText, Play, Box, GitBranch, HardDrive, Lock, BarChart3, Download } from "lucide-react";

const API = "";

const READINESS_COLORS = {
  READY: { bg: "bg-emerald-500/10", border: "border-emerald-500/40", text: "text-emerald-400", ring: "ring-emerald-500/30", gradient: "from-emerald-500/20 to-emerald-500/5" },
  DEGRADED: { bg: "bg-amber-500/10", border: "border-amber-500/40", text: "text-amber-400", ring: "ring-amber-500/30", gradient: "from-amber-500/20 to-amber-500/5" },
  NOT_READY: { bg: "bg-red-500/10", border: "border-red-500/40", text: "text-red-400", ring: "ring-red-500/30", gradient: "from-red-500/20 to-red-500/5" },
};

const LAUNCH_COLORS = {
  GO_LIVE_READY: { bg: "bg-emerald-500/10", text: "text-emerald-400", icon: CheckCircle2 },
  CONDITIONALLY_READY: { bg: "bg-amber-500/10", text: "text-amber-400", icon: AlertTriangle },
  NOT_READY: { bg: "bg-red-500/10", text: "text-red-400", icon: XCircle },
};

const STATUS_CLS = (s) => {
  const m = { healthy: "text-emerald-400", connected: "text-emerald-400", active: "text-emerald-400", pass: "text-emerald-400", PASS: "text-emerald-400", READY: "text-emerald-400", success: "text-emerald-400", production: "text-emerald-400", enabled: "text-emerald-400", operational: "text-emerald-400", GO_LIVE_READY: "text-emerald-400", CLEAR: "text-emerald-400", degraded: "text-amber-400", DEGRADED: "text-amber-400", PARTIAL: "text-amber-400", warning: "text-amber-400", partial: "text-amber-400", standalone: "text-amber-400", CONDITIONALLY_READY: "text-amber-400", WARNING: "text-amber-400", BLOCKED: "text-red-400", disconnected: "text-zinc-500", disabled: "text-zinc-500", inactive: "text-zinc-500", not_configured: "text-zinc-500", NOT_READY: "text-red-400", FAIL: "text-red-400", error: "text-red-400", fail: "text-red-400", failed: "text-red-400" };
  return m[s] || "text-zinc-400";
};

const Badge = ({ status, testId }) => {
  const color = STATUS_CLS(status);
  const bgMap = { "text-emerald-400": "bg-emerald-500/15 border-emerald-500/30", "text-amber-400": "bg-amber-500/15 border-amber-500/30", "text-red-400": "bg-red-500/15 border-red-500/30", "text-zinc-500": "bg-zinc-700/40 border-zinc-600/30", "text-zinc-400": "bg-zinc-700/40 border-zinc-600/30" };
  return <span data-testid={testId} className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${bgMap[color] || "bg-zinc-700/40 border-zinc-600/30"} ${color} uppercase tracking-wider`}>{status}</span>;
};

const MetricBox = ({ label, value, sub, testId }) => (
  <div data-testid={testId} className="bg-zinc-800/60 border border-zinc-700/40 rounded-lg p-3.5">
    <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 font-medium">{label}</div>
    <div className="text-lg font-bold text-zinc-100 tabular-nums leading-tight">{value ?? "--"}</div>
    {sub && <div className="text-[11px] text-zinc-500 mt-0.5">{sub}</div>}
  </div>
);

const Panel = ({ title, status, children, testId, icon: Icon, actions }) => (
  <div data-testid={testId} className="bg-zinc-900/80 border border-zinc-700/40 rounded-xl p-5 space-y-4">
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        {Icon && <Icon size={16} className="text-zinc-500" />}
        <h3 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">{title}</h3>
      </div>
      <div className="flex items-center gap-2">
        {actions}
        {status && <Badge status={status} testId={`${testId}-badge`} />}
      </div>
    </div>
    {children}
  </div>
);

const StepRow = ({ step, idx }) => {
  const icons = { pass: CheckCircle2, fail: XCircle, warning: AlertTriangle, skipped: Clock };
  const colors = { pass: "text-emerald-400", fail: "text-red-400", warning: "text-amber-400", skipped: "text-zinc-500" };
  const Icon = icons[step.status] || Clock;
  const color = colors[step.status] || "text-zinc-400";
  return (
    <div data-testid={`step-${idx}`} className="flex items-center justify-between py-2.5 border-b border-zinc-800/50 last:border-0">
      <div className="flex items-center gap-2.5">
        <Icon size={14} className={color} />
        <div>
          <span className="text-sm font-medium text-zinc-200">{step.name.replace(/_/g, " ")}</span>
          <span className="text-[11px] text-zinc-600 ml-2">{step.category}</span>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-[11px] text-zinc-500 tabular-nums">{step.latency_ms?.toFixed(0)}ms</span>
        {step.blocker && <span className="text-[9px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded font-bold uppercase">Blocker</span>}
        <Badge status={step.status} />
      </div>
    </div>
  );
};

const ProviderTestRow = ({ name, data, onTest, testing }) => (
  <div data-testid={`provider-test-${name}`} className="flex items-center justify-between py-3 border-b border-zinc-800/50 last:border-0">
    <div className="flex items-center gap-3">
      <div className={`w-2 h-2 rounded-full ${data?.status === "success" ? "bg-emerald-400" : data?.status === "degraded" ? "bg-amber-400" : data?.status === "not_configured" ? "bg-zinc-600" : "bg-red-400"}`} />
      <div>
        <span className="text-sm font-medium text-zinc-200">{name.replace(/_/g, " ").toUpperCase()}</span>
        <span className="text-[11px] text-zinc-600 ml-2">{data?.mode || ""}</span>
      </div>
    </div>
    <div className="flex items-center gap-3">
      {data?.latency_ms > 0 && <span className="text-[11px] text-zinc-500 tabular-nums">{data.latency_ms.toFixed(0)}ms</span>}
      {data?.validated_at && <span className="text-[10px] text-zinc-600">{new Date(data.validated_at).toLocaleTimeString()}</span>}
      <Badge status={data?.status || "pending"} />
      <button
        data-testid={`test-btn-${name}`}
        onClick={() => onTest(name)}
        disabled={testing}
        className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-zinc-800 border border-zinc-700/60 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-all disabled:opacity-40"
      >
        {testing ? "..." : "Test"}
      </button>
    </div>
  </div>
);

export default function ProductionGoLiveDashboard({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [providerTests, setProviderTests] = useState({});
  const [testingProvider, setTestingProvider] = useState(null);
  const [testingAll, setTestingAll] = useState(false);
  const [prelaunchResult, setPrelaunchResult] = useState(null);
  const [runningPrelaunch, setRunningPrelaunch] = useState(false);
  const [validationHistory, setValidationHistory] = useState([]);
  const [deploymentData, setDeploymentData] = useState(null);
  const [triggeringBackup, setTriggeringBackup] = useState(false);
  const [backupResult, setBackupResult] = useState(null);
  const token = localStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`/api/production-golive/summary`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      if (json.prelaunch_latest) setPrelaunchResult(json.prelaunch_latest);
      setError(null);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 30000); return () => clearInterval(i); }, [fetchData]);

  const testProvider = async (provider) => {
    setTestingProvider(provider);
    try {
      const res = await fetch(`/api/production-golive/providers/${provider}/test`, { method: "POST", headers });
      const json = await res.json();
      setProviderTests(prev => ({ ...prev, [provider]: json }));
    } catch (e) { console.error(e); }
    setTestingProvider(null);
  };

  const testAllProviders = async () => {
    setTestingAll(true);
    try {
      const res = await fetch(`/api/production-golive/providers/test-all`, { method: "POST", headers });
      const json = await res.json();
      if (json.providers) setProviderTests(json.providers);
    } catch (e) { console.error(e); }
    setTestingAll(false);
  };

  const runPrelaunch = async () => {
    setRunningPrelaunch(true);
    try {
      const res = await fetch(`/api/production-golive/validate/run`, { method: "POST", headers });
      const json = await res.json();
      setPrelaunchResult(json);
      // Refresh history
      const hRes = await fetch(`/api/production-golive/validate/history?limit=10`, { headers });
      const hJson = await hRes.json();
      setValidationHistory(hJson.history || []);
    } catch (e) { console.error(e); }
    setRunningPrelaunch(false);
  };

  const fetchDeployment = useCallback(async () => {
    try {
      const [riskRes, stratRes, infraRes] = await Promise.all([
        fetch(`/api/production-golive/deployment/risk-assessment`, { headers }),
        fetch(`/api/production-golive/deployment/strategy`, { headers }),
        fetch(`/api/production-golive/deployment/infrastructure`, { headers }),
      ]);
      const [risk, strategy, infra] = await Promise.all([riskRes.json(), stratRes.json(), infraRes.json()]);
      setDeploymentData({ risk, strategy, infra });
    } catch (e) { console.error(e); }
  }, [token]);

  const triggerBackup = async () => {
    setTriggeringBackup(true);
    try {
      const res = await fetch(`/api/production-golive/backup/trigger`, { method: "POST", headers });
      const json = await res.json();
      setBackupResult(json);
    } catch (e) { console.error(e); }
    setTriggeringBackup(false);
  };

  useEffect(() => { if (activeTab === "deployment") fetchDeployment(); }, [activeTab, fetchDeployment]);

  if (loading) return <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="production_golive"><div data-testid="golive-loading" className="flex items-center justify-center min-h-[60vh]"><div className="text-zinc-400 animate-pulse text-lg">Production Go-Live kontrol ediliyor...</div></div></Layout>;
  if (error) return <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="production_golive"><div data-testid="golive-error" className="flex items-center justify-center min-h-[60vh]"><div className="text-red-400">Hata: {error}</div></div></Layout>;

  const readiness = data?.readiness || {};
  const config = data?.configuration || {};
  const configAct = data?.config_activation || {};
  const redis = data?.redis || {};
  const mongo = data?.mongodb || {};
  const workers = data?.workers || {};
  const providers = data?.providers || {};
  const backup = data?.backup || {};
  const observability = data?.observability || {};
  const security = data?.security || {};
  const alertsSummary = data?.alerts_summary || {};

  const rScore = readiness.readiness_score || 0;
  const rStatus = readiness.readiness || "NOT_READY";
  const rColors = READINESS_COLORS[rStatus] || READINESS_COLORS.NOT_READY;

  const tabs = [
    { key: "overview", label: "Overview", icon: Activity },
    { key: "deployment", label: "Deployment", icon: Box },
    { key: "providers", label: "Providers", icon: Radio },
    { key: "config", label: "Config", icon: Settings },
    { key: "infra", label: "Infrastructure", icon: Server },
    { key: "prelaunch", label: "Pre-Launch", icon: Rocket },
    { key: "security", label: "Security", icon: Shield },
    { key: "alerts", label: "Alerts", icon: Bell },
  ];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="production_golive">
      <div data-testid="production-golive-dashboard" className="space-y-5 pb-10">
        {/* Header */}
        <div className={`bg-gradient-to-r ${rColors.gradient} ${rColors.border} border rounded-2xl p-6 ring-1 ${rColors.ring}`}>
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <h1 data-testid="golive-title" className="text-2xl font-bold text-zinc-100 tracking-tight">{t("techDashboards.productionGoLive")}</h1>
              <p className="text-sm text-zinc-400 mt-1">Sistem hazirlik durumu ve production dogrulama</p>
            </div>
            <div className="flex items-center gap-5">
              <div className="text-right">
                <div data-testid="readiness-score" className={`text-4xl font-black tabular-nums ${rColors.text}`}>{rScore}%</div>
                <div className="text-[11px] text-zinc-500">Readiness Score</div>
              </div>
              <div data-testid="readiness-status" className={`px-4 py-2 rounded-xl text-base font-bold ${rColors.bg} ${rColors.border} border ${rColors.text}`}>{rStatus}</div>
              <button data-testid="refresh-btn" onClick={fetchData} className="p-2 rounded-lg bg-zinc-800/60 border border-zinc-700/40 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60 transition-all"><RefreshCw size={16} /></button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-zinc-900/60 p-1 rounded-xl border border-zinc-800/60 overflow-x-auto">
          {tabs.map(t => (<button key={t.key} data-testid={`tab-${t.key}`} onClick={() => setActiveTab(t.key)} className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${activeTab === t.key ? "bg-zinc-700/60 text-zinc-100 shadow-sm" : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40"}`}><t.icon size={14} />{t.label}</button>))}
        </div>

        {/* TAB: Overview */}
        {activeTab === "overview" && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricBox testId="metric-redis" label="Redis" value={redis.connected ? "Connected" : "Offline"} sub={redis.mode} />
              <MetricBox testId="metric-mongo" label="MongoDB" value={mongo.overall_status || "unknown"} sub={`Pool: ${mongo.connection_pool?.current_connections || 0}`} />
              <MetricBox testId="metric-workers" label="Workers" value={`${workers.queues?.length || 0} Queues`} sub={`Submitted: ${workers.total_submitted || 0}`} />
              <MetricBox testId="metric-backup" label="Backup" value={backup.enabled ? "Enabled" : "Disabled"} sub={`Retention: ${backup.retention_days || 30}d`} />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricBox testId="metric-config" label="Config" value={`${config.total_configured || 0}/${config.total_required || 0}`} sub={config.overall_status} />
              <MetricBox testId="metric-boot" label="Boot Status" value={configAct.boot_status || "UNKNOWN"} sub={`Blockers: ${configAct.blocker_count || 0}`} />
              <MetricBox testId="metric-security" label="Security" value={`${security.score || 0}%`} sub={security.overall_status} />
              <MetricBox testId="metric-alerts" label="Alerts" value={alertsSummary.total_alerts || 0} sub={`Webhooks: ${alertsSummary.webhook_targets_configured || 0}`} />
            </div>

            {/* Launch Recommendation */}
            {prelaunchResult && (
              <div data-testid="launch-recommendation" className={`${(LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).bg} border border-zinc-700/40 rounded-xl p-5`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {React.createElement((LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).icon, { size: 20, className: (LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).text })}
                    <div>
                      <div className={`text-lg font-bold ${(LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).text}`}>{prelaunchResult.recommendation?.replace(/_/g, " ")}</div>
                      <div className="text-[11px] text-zinc-500">Son dogrulama: {prelaunchResult.started_at ? new Date(prelaunchResult.started_at).toLocaleString() : "N/A"}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-black text-zinc-100 tabular-nums">{prelaunchResult.readiness_score || 0}%</div>
                    <div className="text-[11px] text-zinc-500">{prelaunchResult.passed_count || 0}/{prelaunchResult.total_checks || 0} passed</div>
                  </div>
                </div>
                {prelaunchResult.blockers?.length > 0 && (
                  <div className="mt-3 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                    <div className="text-[11px] font-bold text-red-400 uppercase mb-1">Launch Blockers</div>
                    {prelaunchResult.blockers.map((b, i) => <div key={i} className="text-xs text-red-300">{b.name}: {b.message}</div>)}
                  </div>
                )}
              </div>
            )}

            {/* Subsystem Checks */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {readiness.checks && Object.entries(readiness.checks).map(([key, val]) => (
                <div key={key} className="bg-zinc-900/60 border border-zinc-800/50 rounded-lg p-3.5 flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-300 capitalize">{key.replace(/_/g, " ")}</span>
                  <Badge status={val.status} testId={`check-${key}`} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB: Deployment */}
        {activeTab === "deployment" && (
          <div className="space-y-5">
            {/* Risk Assessment */}
            {deploymentData?.risk && (
              <Panel title="Deployment Risk Assessment" status={deploymentData.risk.verdict} testId="panel-risk" icon={AlertTriangle}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <MetricBox testId="safety-score" label="Safety Score" value={`${deploymentData.risk.safety_score}%`} sub={deploymentData.risk.verdict?.replace(/_/g, " ")} />
                  <MetricBox testId="risk-score" label="Risk Score" value={deploymentData.risk.risk_score} sub={`${deploymentData.risk.risk_count} risk factors`} />
                  <MetricBox testId="deploy-strategy" label="Strategy" value={deploymentData.strategy?.strategy?.replace(/_/g, " ")} sub={`Est. ${deploymentData.strategy?.estimated_duration_minutes || 0} min`} />
                  <MetricBox testId="deploy-components" label="Components" value={deploymentData.infra?.total_components || 0} sub={`${deploymentData.infra?.critical_components || 0} critical`} />
                </div>

                {/* Risk factors */}
                {deploymentData.risk.risks?.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider">Risk Factors</div>
                    {deploymentData.risk.risks.map((r, i) => (
                      <div key={i} className="flex items-center justify-between py-2 border-b border-zinc-800/50 last:border-0">
                        <div className="flex items-center gap-2.5">
                          <AlertTriangle size={12} className="text-amber-400" />
                          <span className="text-sm text-zinc-300">{r.description}</span>
                        </div>
                        <span className="text-xs text-amber-400 font-bold tabular-nums">-{r.weight}pts</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Mitigations */}
                {deploymentData.risk.mitigations?.length > 0 && (
                  <div className="mt-4 bg-zinc-800/40 rounded-lg p-3.5">
                    <div className="text-[11px] font-bold text-emerald-400 uppercase mb-2">Mitigations</div>
                    {deploymentData.risk.mitigations.map((m, i) => (
                      <div key={i} className="flex items-start gap-2 py-1">
                        <ChevronRight size={10} className="text-emerald-500 mt-1 flex-shrink-0" />
                        <span className="text-xs text-zinc-400">{m}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
            )}

            {/* Deployment Strategy */}
            {deploymentData?.strategy && (
              <Panel title="Deployment Strategy" status={deploymentData.strategy.strategy} testId="panel-strategy" icon={GitBranch}>
                <div className="mb-3 text-sm text-zinc-400">{deploymentData.strategy.description}</div>

                {/* Deployment batches */}
                <div className="space-y-1">
                  <div className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Deployment Order</div>
                  {deploymentData.strategy.deployment_batches?.map((b, i) => (
                    <div key={i} data-testid={`batch-${b.component}`} className="flex items-center justify-between py-2 border-b border-zinc-800/50 last:border-0">
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] text-zinc-600 font-mono w-5 text-right">{b.order}</span>
                        <div className={`w-2 h-2 rounded-full ${b.critical ? "bg-amber-400" : "bg-zinc-600"}`} />
                        <span className="text-sm font-medium text-zinc-200">{b.component}</span>
                        <span className="text-[10px] text-zinc-600">{b.type}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        {b.health_check && <span className="text-[10px] text-zinc-600 font-mono">{b.health_check}</span>}
                        <span className="text-[10px] text-zinc-500">x{b.replicas}</span>
                        {b.critical && <span className="text-[9px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded font-bold">CRITICAL</span>}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Pre/Post checks */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[11px] font-bold text-zinc-400 uppercase mb-2">Pre-Deployment</div>
                    {deploymentData.strategy.pre_deployment_checks?.map((c, i) => (
                      <div key={i} className="text-xs text-zinc-500 py-0.5 flex items-start gap-1.5"><CheckCircle2 size={10} className="text-zinc-600 mt-0.5" />{c}</div>
                    ))}
                  </div>
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[11px] font-bold text-zinc-400 uppercase mb-2">Post-Deployment</div>
                    {deploymentData.strategy.post_deployment_checks?.map((c, i) => (
                      <div key={i} className="text-xs text-zinc-500 py-0.5 flex items-start gap-1.5"><CheckCircle2 size={10} className="text-zinc-600 mt-0.5" />{c}</div>
                    ))}
                  </div>
                </div>

                {/* Rollback plan */}
                {deploymentData.strategy.rollback_plan && (
                  <div className="mt-3 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                    <div className="text-[11px] font-bold text-red-400 uppercase mb-1">Rollback Plan</div>
                    <div className="text-xs text-zinc-400">Auto: {deploymentData.strategy.rollback_plan.auto_rollback ? "Enabled" : "Disabled"} | Health Check: {deploymentData.strategy.rollback_plan.health_check_interval_sec}s | Threshold: {deploymentData.strategy.rollback_plan.failure_threshold} failures</div>
                  </div>
                )}
              </Panel>
            )}

            {/* Infrastructure Topology */}
            {deploymentData?.infra && (
              <Panel title="Infrastructure Topology" testId="panel-infra-topology" icon={HardDrive}>
                {/* Monitoring Stack */}
                <div className="mb-4">
                  <div className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Monitoring Stack</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {deploymentData.infra.monitoring_stack && Object.entries(deploymentData.infra.monitoring_stack).map(([k, v]) => (
                      <div key={k} className="bg-zinc-800/40 rounded-lg p-2.5">
                        <div className="text-[10px] text-zinc-600 uppercase">{k}</div>
                        <div className="text-xs text-zinc-300 font-medium">{v}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Security */}
                <div className="mb-4">
                  <div className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Security Layer</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {deploymentData.infra.security && Object.entries(deploymentData.infra.security).map(([k, v]) => (
                      <div key={k} className="bg-zinc-800/40 rounded-lg p-2.5">
                        <div className="text-[10px] text-zinc-600 uppercase">{k}</div>
                        <div className="text-xs text-zinc-300">{v}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Config files */}
                <div>
                  <div className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Config File Inventory</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
                    {deploymentData.infra.config_files && Object.entries(deploymentData.infra.config_files).map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between py-1.5">
                        <span className="text-xs text-zinc-400">{k.replace(/_/g, " ")}</span>
                        <span className="text-[10px] text-zinc-600 font-mono">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Grafana Dashboards */}
                {deploymentData.infra.grafana_dashboards && (
                  <div className="mt-4">
                    <div className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Grafana Dashboards</div>
                    <div className="flex gap-2 flex-wrap">
                      {deploymentData.infra.grafana_dashboards.map((d, i) => (
                        <span key={i} className="px-3 py-1.5 bg-zinc-800/60 border border-zinc-700/40 rounded-lg text-xs text-zinc-300 font-medium flex items-center gap-1.5">
                          <BarChart3 size={10} className="text-zinc-500" />{d.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </Panel>
            )}

            {/* Backup & DR */}
            <Panel title="Backup & Disaster Recovery" testId="panel-deploy-backup" icon={Download} actions={
              <button data-testid="trigger-backup-btn" onClick={triggerBackup} disabled={triggeringBackup} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-zinc-800 border border-zinc-700/60 text-zinc-300 hover:bg-zinc-700 transition-all disabled:opacity-40">
                <HardDrive size={12} />{triggeringBackup ? "Running..." : "Trigger Backup"}
              </button>
            }>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="deploy-backup-enabled" label="Enabled" value={data?.backup?.enabled ? "Yes" : "No"} />
                <MetricBox testId="deploy-backup-retention" label="Retention" value={`${data?.backup?.retention_days || 30}d`} />
                <MetricBox testId="deploy-backup-rpo" label="RPO" value="24h" />
                <MetricBox testId="deploy-backup-rto" label="RTO" value="4h" />
              </div>
              {backupResult && (
                <div className="mt-3 bg-zinc-800/40 rounded-lg p-3">
                  <div className="text-[11px] font-bold text-zinc-500 uppercase mb-1">Backup Result</div>
                  <div className="text-sm text-zinc-300">ID: {backupResult.backup_id} | Status: <span className={STATUS_CLS(backupResult.status)}>{backupResult.status}</span></div>
                  {backupResult.size_bytes > 0 && <div className="text-xs text-zinc-500">Size: {(backupResult.size_bytes / 1024).toFixed(1)} KB</div>}
                </div>
              )}
            </Panel>
          </div>
        )}


        {/* TAB: Providers */}
        {activeTab === "providers" && (
          <div className="space-y-5">
            <Panel title="Provider Connection Tests" status={Object.values(providerTests).some(t => t.status === "success") ? "partial" : "not_configured"} testId="panel-provider-tests" icon={Radio} actions={
              <button data-testid="test-all-providers-btn" onClick={testAllProviders} disabled={testingAll} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-zinc-800 border border-zinc-700/60 text-zinc-300 hover:bg-zinc-700 transition-all disabled:opacity-40">
                <Play size={12} />{testingAll ? "Testing..." : "Test All"}
              </button>
            }>
              {["twilio_sms", "sendgrid_email", "whatsapp", "redis", "sentry", "otel"].map(p => (
                <ProviderTestRow key={p} name={p} data={providerTests[p]} onTest={testProvider} testing={testingProvider === p} />
              ))}
            </Panel>

            <Panel title="Messaging Providers" status={providers.active_providers > 0 ? "partial" : "not_configured"} testId="panel-providers" icon={Radio}>
              {providers.providers && Object.entries(providers.providers).map(([name, pData]) => (
                <div key={name} data-testid={`provider-${name}`} className="flex items-center justify-between py-2.5 border-b border-zinc-800/50 last:border-0">
                  <div>
                    <span className="text-sm font-medium text-zinc-200">{name.replace(/_/g, " ").toUpperCase()}</span>
                    {pData?.ready_for_production && <span className="ml-2 text-[10px] text-emerald-400 font-semibold uppercase">Production Ready</span>}
                  </div>
                  <Badge status={pData?.status || "unknown"} />
                </div>
              ))}
              {providers.providers && Object.values(providers.providers).some(p => p.missing_vars?.length > 0) && (
                <div className="mt-3 bg-zinc-800/40 rounded-lg p-3 space-y-1">
                  <div className="text-[11px] font-bold text-amber-400 uppercase">Missing Configuration</div>
                  {Object.entries(providers.providers).filter(([, p]) => p.missing_vars?.length > 0).map(([name, pData]) => (
                    <div key={name} className="text-xs text-zinc-400"><span className="font-medium text-zinc-300">{name}:</span> {pData.missing_vars.join(", ")}</div>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="Fallback Chain" testId="panel-fallback" icon={ChevronRight}>
              <div className="flex items-center gap-2 flex-wrap">
                {(providers.fallback_chain || []).map((p, i) => (
                  <React.Fragment key={p}>
                    <span className="px-3 py-1.5 bg-zinc-800/60 border border-zinc-700/40 rounded-lg text-xs text-zinc-300 font-medium">{p}</span>
                    {i < (providers.fallback_chain?.length || 0) - 1 && <ChevronRight size={12} className="text-zinc-600" />}
                  </React.Fragment>
                ))}
              </div>
            </Panel>
          </div>
        )}

        {/* TAB: Config */}
        {activeTab === "config" && (
          <div className="space-y-5">
            <Panel title="Config Activation" status={configAct.boot_status} testId="panel-config-activation" icon={Settings}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <MetricBox label="Total Variables" value={configAct.total_variables} testId="cfg-total" />
                <MetricBox label="Configured" value={configAct.configured_count} testId="cfg-configured" />
                <MetricBox label="Blockers" value={configAct.blocker_count} testId="cfg-blockers" />
                <MetricBox label="Format Errors" value={configAct.format_error_count} testId="cfg-format-errors" />
              </div>
              {configAct.blockers?.length > 0 && (
                <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3 mb-3">
                  <div className="text-[11px] font-bold text-red-400 uppercase mb-1">Boot Blockers</div>
                  {configAct.blockers.map((b, i) => <div key={i} className="text-xs text-red-300 font-mono">{b.variable} — {b.description}</div>)}
                </div>
              )}
              {configAct.format_errors?.length > 0 && (
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-3 mb-3">
                  <div className="text-[11px] font-bold text-amber-400 uppercase mb-1">Format Errors</div>
                  {configAct.format_errors.map((f, i) => <div key={i} className="text-xs text-amber-300 font-mono">{f.variable}: {f.hint}</div>)}
                </div>
              )}
              {configAct.source_summary && (
                <div className="mt-3">
                  <div className="text-[11px] font-bold text-zinc-500 uppercase mb-2">Config Sources</div>
                  <div className="flex gap-3">
                    {Object.entries(configAct.source_summary).map(([src, cnt]) => (
                      <div key={src} className="px-3 py-1.5 bg-zinc-800/40 rounded-lg text-xs text-zinc-400"><span className="font-medium text-zinc-300">{src}:</span> {cnt}</div>
                    ))}
                  </div>
                </div>
              )}
            </Panel>

            <Panel title="Environment Variables" status={config.overall_status} testId="panel-config" icon={FileText}>
              {config.categories && Object.entries(config.categories).map(([cat, catData]) => (
                <div key={cat} className="space-y-1.5">
                  <div className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider pt-2">{cat} ({catData.configured}/{catData.total})</div>
                  {catData.variables?.map(v => (
                    <div key={v.variable} className="flex items-center justify-between py-1.5 border-b border-zinc-800/40 last:border-0">
                      <div>
                        <span className="text-sm text-zinc-300 font-mono">{v.variable}</span>
                        <span className="text-[11px] text-zinc-600 ml-2">{v.description}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {v.masked_value && <span className="text-[11px] text-zinc-600 font-mono">{v.masked_value}</span>}
                        <span className={`w-2 h-2 rounded-full ${v.configured ? "bg-emerald-400" : v.critical ? "bg-red-400" : "bg-zinc-600"}`} />
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </Panel>
          </div>
        )}

        {/* TAB: Infrastructure */}
        {activeTab === "infra" && (
          <div className="space-y-5">
            <Panel title="Redis Cluster" status={redis.connected ? "connected" : "disconnected"} testId="panel-redis" icon={Database}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="redis-mode" label="Mode" value={redis.mode} />
                <MetricBox testId="redis-connected" label="Connected" value={redis.connected ? "Yes" : "No"} />
                <MetricBox testId="redis-reconnects" label="Reconnects" value={redis.metrics?.reconnects || 0} />
                <MetricBox testId="redis-cmds" label="Commands" value={redis.metrics?.commands_sent || 0} />
              </div>
            </Panel>
            <Panel title="MongoDB Production" status={mongo.overall_status} testId="panel-mongo" icon={Database}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="mongo-pool" label="Connections" value={mongo.connection_pool?.current_connections || 0} sub={`Available: ${mongo.connection_pool?.available_connections || 0}`} />
                <MetricBox testId="mongo-version" label="Version" value={mongo.connection_pool?.mongo_version || "unknown"} />
                <MetricBox testId="mongo-replica" label="Replica Set" value={mongo.replica_set?.is_replica_set ? "Yes" : "No"} sub={mongo.replica_set?.status} />
                <MetricBox testId="mongo-indexes" label="Index Status" value={mongo.index_validation?.status || "unknown"} sub={`Missing: ${mongo.index_validation?.missing_index_count || 0}`} />
              </div>
            </Panel>
            <Panel title="Worker Cluster" status="active" testId="panel-workers" icon={Zap}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="worker-queues" label="Queues" value={workers.queues?.length || 0} />
                <MetricBox testId="worker-submitted" label="Submitted" value={workers.total_submitted || 0} />
                <MetricBox testId="worker-completed" label="Completed" value={workers.total_completed || 0} />
                <MetricBox testId="worker-failed" label="Failed" value={workers.total_failed || 0} />
              </div>
            </Panel>
            <Panel title="Backup & DR" status={backup.enabled ? "enabled" : "disabled"} testId="panel-backup" icon={Server}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="backup-enabled" label="Enabled" value={backup.enabled ? "Yes" : "No"} />
                <MetricBox testId="backup-retention" label="Retention" value={`${backup.retention_days || 30} days`} />
                <MetricBox testId="backup-rpo" label="RPO Target" value="24h" />
                <MetricBox testId="backup-rto" label="RTO Target" value="4h" />
              </div>
            </Panel>
            <Panel title="Observability Stack" status={observability.otel?.active || observability.sentry?.active ? "active" : "inactive"} testId="panel-observability" icon={Activity}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="otel-status" label="OpenTelemetry" value={observability.otel?.active ? "Active" : "Inactive"} />
                <MetricBox testId="sentry-status" label="Sentry" value={observability.sentry?.active ? "Active" : "Inactive"} />
                <MetricBox testId="grafana-status" label="Grafana" value="Template Ready" />
                <MetricBox testId="prometheus-status" label="Prometheus" value="Configured" />
              </div>
            </Panel>
          </div>
        )}

        {/* TAB: Pre-Launch */}
        {activeTab === "prelaunch" && (
          <div className="space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-zinc-100">Pre-Launch Validation Suite</h2>
              <button data-testid="run-prelaunch-btn" onClick={runPrelaunch} disabled={runningPrelaunch} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-zinc-800 border border-zinc-700/60 text-zinc-200 hover:bg-zinc-700 transition-all disabled:opacity-40">
                <Rocket size={14} />{runningPrelaunch ? "Running..." : "Run Validation"}
              </button>
            </div>

            {prelaunchResult && prelaunchResult.steps && (
              <>
                <div data-testid="prelaunch-result" className={`${(LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).bg} border border-zinc-700/40 rounded-xl p-5`}>
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      {React.createElement((LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).icon, { size: 24, className: (LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).text })}
                      <div>
                        <div className={`text-xl font-bold ${(LAUNCH_COLORS[prelaunchResult.recommendation] || LAUNCH_COLORS.NOT_READY).text}`}>{prelaunchResult.recommendation?.replace(/_/g, " ")}</div>
                        <div className="text-[11px] text-zinc-500">Run: {prelaunchResult.run_id} ({prelaunchResult.total_duration_ms?.toFixed(0)}ms)</div>
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-4 text-center">
                      <div><div className="text-lg font-bold text-zinc-100">{prelaunchResult.readiness_score}%</div><div className="text-[10px] text-zinc-500">Score</div></div>
                      <div><div className="text-lg font-bold text-emerald-400">{prelaunchResult.passed_count}</div><div className="text-[10px] text-zinc-500">Passed</div></div>
                      <div><div className="text-lg font-bold text-amber-400">{prelaunchResult.warning_count}</div><div className="text-[10px] text-zinc-500">Warnings</div></div>
                      <div><div className="text-lg font-bold text-red-400">{prelaunchResult.blocker_count}</div><div className="text-[10px] text-zinc-500">Blockers</div></div>
                    </div>
                  </div>

                  {/* Steps */}
                  <div className="bg-zinc-900/60 rounded-lg p-4">
                    {prelaunchResult.steps.map((step, i) => <StepRow key={i} step={step} idx={i} />)}
                  </div>
                </div>

                {/* Recommended Actions */}
                {prelaunchResult.recommended_actions?.length > 0 && (
                  <Panel title="Recommended Actions" testId="panel-actions" icon={FileText}>
                    {prelaunchResult.recommended_actions.map((a, i) => (
                      <div key={i} className="flex items-start gap-2 py-1.5">
                        <ChevronRight size={12} className="text-zinc-500 mt-0.5 flex-shrink-0" />
                        <span className="text-sm text-zinc-300">{a}</span>
                      </div>
                    ))}
                  </Panel>
                )}
              </>
            )}

            {!prelaunchResult?.steps && (
              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-xl p-10 text-center">
                <Rocket size={32} className="text-zinc-600 mx-auto mb-3" />
                <div className="text-sm text-zinc-500">Henuz dogrulama calistirilmadi. "Run Validation" ile baslatin.</div>
              </div>
            )}

            {/* Validation History */}
            {validationHistory.length > 0 && (
              <Panel title="Validation History" testId="panel-validation-history" icon={Clock}>
                {validationHistory.map((h, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-zinc-800/50 last:border-0">
                    <div className="flex items-center gap-2">
                      <Badge status={h.recommendation} />
                      <span className="text-xs text-zinc-400 font-mono">{h.run_id}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-zinc-300 tabular-nums">{h.readiness_score}%</span>
                      <span className="text-[11px] text-zinc-500">{h.started_at ? new Date(h.started_at).toLocaleString() : ""}</span>
                    </div>
                  </div>
                ))}
              </Panel>
            )}
          </div>
        )}

        {/* TAB: Security */}
        {activeTab === "security" && (
          <div className="space-y-5">
            <Panel title="Security Go-Live Checklist" status={security.overall_status} testId="panel-security" icon={Shield}>
              <div className="flex items-center gap-6 mb-4">
                <div>
                  <span className={`text-3xl font-black tabular-nums ${security.score >= 80 ? "text-emerald-400" : security.score >= 50 ? "text-amber-400" : "text-red-400"}`}>{security.score || 0}%</span>
                  <span className="text-[11px] text-zinc-500 ml-1">Score</span>
                </div>
                <div className="text-sm text-zinc-400">{security.passed || 0}/{security.total || 0} checks passed</div>
              </div>
              {security.checks?.map((check, i) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-zinc-800/50 last:border-0">
                  <span className="text-sm text-zinc-300">{check.check?.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) || `Check ${i + 1}`}</span>
                  <div className="flex items-center gap-2">
                    {(check.note || check.error) && <span className="text-[11px] text-zinc-500">{check.note || check.error}</span>}
                    <span className={`text-xs font-bold ${check.pass ? "text-emerald-400" : "text-red-400"}`}>{check.pass ? "PASS" : "FAIL"}</span>
                  </div>
                </div>
              ))}
              {security.failed_checks?.length > 0 && (
                <div className="mt-3 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                  <div className="text-[11px] font-bold text-red-400 mb-1">Failed Checks</div>
                  <div className="text-xs text-red-300">{security.failed_checks.join(", ")}</div>
                </div>
              )}
            </Panel>
          </div>
        )}

        {/* TAB: Alerts */}
        {activeTab === "alerts" && (
          <div className="space-y-5">
            <Panel title="Live Ops Alerts" status={alertsSummary.total_alerts > 0 ? "active" : "inactive"} testId="panel-alerts" icon={Bell}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <MetricBox label="Total Alerts" value={alertsSummary.total_alerts || 0} testId="alert-total" />
                <MetricBox label="Critical" value={alertsSummary.by_severity?.critical || 0} testId="alert-critical" />
                <MetricBox label="High" value={alertsSummary.by_severity?.high || 0} testId="alert-high" />
                <MetricBox label="Webhooks" value={alertsSummary.webhook_targets_configured || 0} testId="alert-webhooks" />
              </div>
              {alertsSummary.last_alert && (
                <div className="bg-zinc-800/40 rounded-lg p-3">
                  <div className="text-[11px] font-bold text-zinc-500 uppercase mb-1">Last Alert</div>
                  <div className="text-sm text-zinc-300">{alertsSummary.last_alert.description}</div>
                  <div className="text-[11px] text-zinc-500 mt-1">{alertsSummary.last_alert.fired_at}</div>
                </div>
              )}
              {(!alertsSummary.total_alerts || alertsSummary.total_alerts === 0) && (
                <div className="text-sm text-zinc-500 text-center py-6">Henuz alert olusturulmadi. Pre-launch validation calismasi sirasinda otomatik alert uretilir.</div>
              )}
            </Panel>

            <Panel title="Alert Definitions" testId="panel-alert-defs" icon={FileText}>
              {Object.entries(ALERT_DEFINITIONS_UI).map(([key, defn]) => (
                <div key={key} className="flex items-center justify-between py-2.5 border-b border-zinc-800/50 last:border-0">
                  <div>
                    <span className="text-sm font-medium text-zinc-200">{key.replace(/_/g, " ")}</span>
                    <span className="text-[11px] text-zinc-500 ml-2">{defn.desc}</span>
                  </div>
                  <Badge status={defn.severity} />
                </div>
              ))}
            </Panel>
          </div>
        )}
      </div>
    </Layout>
  );
}

const ALERT_DEFINITIONS_UI = {
  readiness_blocker: { severity: "critical", desc: "Production readiness has blockers" },
  provider_connection_failure: { severity: "high", desc: "External provider connection test failed" },
  redis_disconnected: { severity: "high", desc: "Redis connection lost" },
  tracing_export_failure: { severity: "medium", desc: "OTel trace export failing" },
  backup_readiness_failure: { severity: "high", desc: "Backup system not ready" },
  config_blocker: { severity: "critical", desc: "Critical config missing" },
  security_score_low: { severity: "high", desc: "Security score below threshold" },
  prelaunch_validation_failed: { severity: "critical", desc: "Pre-launch validation NOT_READY" },
};
