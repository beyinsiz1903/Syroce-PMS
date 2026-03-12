import React, { useState, useEffect, useCallback } from "react";
import Layout from "../components/Layout";

const API = process.env.REACT_APP_BACKEND_URL;

const READINESS_COLORS = {
  READY: { bg: "bg-emerald-500/10", border: "border-emerald-500/40", text: "text-emerald-400", ring: "ring-emerald-500/30" },
  DEGRADED: { bg: "bg-amber-500/10", border: "border-amber-500/40", text: "text-amber-400", ring: "ring-amber-500/30" },
  NOT_READY: { bg: "bg-red-500/10", border: "border-red-500/40", text: "text-red-400", ring: "ring-red-500/30" },
};

const STATUS_COLORS = {
  healthy: "text-emerald-400", connected: "text-emerald-400", active: "text-emerald-400",
  pass: "text-emerald-400", PASS: "text-emerald-400", READY: "text-emerald-400",
  production: "text-emerald-400", enabled: "text-emerald-400", operational: "text-emerald-400",
  degraded: "text-amber-400", DEGRADED: "text-amber-400", PARTIAL: "text-amber-400",
  warning: "text-amber-400", partial: "text-amber-400", standalone: "text-amber-400",
  disconnected: "text-zinc-500", disabled: "text-zinc-500", inactive: "text-zinc-500",
  not_configured: "text-zinc-500", NOT_READY: "text-red-400", FAIL: "text-red-400",
  error: "text-red-400", fail: "text-red-400",
};

const Badge = ({ status, testId }) => {
  const color = STATUS_COLORS[status] || "text-zinc-400";
  const bgMap = {
    "text-emerald-400": "bg-emerald-500/15 border-emerald-500/30",
    "text-amber-400": "bg-amber-500/15 border-amber-500/30",
    "text-red-400": "bg-red-500/15 border-red-500/30",
    "text-zinc-500": "bg-zinc-700/40 border-zinc-600/30",
    "text-zinc-400": "bg-zinc-700/40 border-zinc-600/30",
  };
  return (
    <span data-testid={testId} className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${bgMap[color] || ""} ${color}`}>
      {status}
    </span>
  );
};

const MetricBox = ({ label, value, sub, testId }) => (
  <div data-testid={testId} className="bg-zinc-800/60 border border-zinc-700/40 rounded-lg p-4">
    <div className="text-[11px] text-zinc-500 uppercase tracking-wider mb-1 font-medium">{label}</div>
    <div className="text-xl font-bold text-zinc-100 tabular-nums">{value ?? "--"}</div>
    {sub && <div className="text-xs text-zinc-500 mt-1">{sub}</div>}
  </div>
);

const Panel = ({ title, status, children, testId, icon }) => (
  <div data-testid={testId} className="bg-zinc-900/80 border border-zinc-700/40 rounded-xl p-5 space-y-4">
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        {icon && <span className="text-lg">{icon}</span>}
        <h3 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">{title}</h3>
      </div>
      {status && <Badge status={status} testId={`${testId}-badge`} />}
    </div>
    {children}
  </div>
);

const CheckRow = ({ label, pass: passed, detail }) => (
  <div className="flex items-center justify-between py-2 border-b border-zinc-800/60 last:border-0">
    <span className="text-sm text-zinc-300">{label}</span>
    <div className="flex items-center gap-2">
      {detail && <span className="text-xs text-zinc-500">{detail}</span>}
      <span className={`text-xs font-bold ${passed ? "text-emerald-400" : "text-red-400"}`}>
        {passed ? "PASS" : "FAIL"}
      </span>
    </div>
  </div>
);

const ProviderRow = ({ name, data }) => (
  <div data-testid={`provider-${name}`} className="flex items-center justify-between py-2.5 border-b border-zinc-800/60 last:border-0">
    <div>
      <span className="text-sm font-medium text-zinc-200">{name.replace(/_/g, " ").toUpperCase()}</span>
    </div>
    <div className="flex items-center gap-3">
      {data?.ready_for_production && <span className="text-[10px] text-emerald-400 font-semibold uppercase">Production Ready</span>}
      <Badge status={data?.status || "unknown"} />
    </div>
  </div>
);

export default function ProductionGoLiveDashboard({ user, tenant, onLogout }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const token = localStorage.getItem("token");

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/production-golive/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="production_golive">
        <div data-testid="golive-loading" className="flex items-center justify-center min-h-[60vh]">
          <div className="text-zinc-400 animate-pulse text-lg">Production Go-Live kontrol ediliyor...</div>
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="production_golive">
        <div data-testid="golive-error" className="flex items-center justify-center min-h-[60vh]">
          <div className="text-red-400">Hata: {error}</div>
        </div>
      </Layout>
    );
  }

  const readiness = data?.readiness || {};
  const config = data?.configuration || {};
  const redis = data?.redis || {};
  const mongo = data?.mongodb || {};
  const workers = data?.workers || {};
  const providers = data?.providers || {};
  const backup = data?.backup || {};
  const observability = data?.observability || {};
  const security = data?.security || {};

  const rScore = readiness.readiness_score || 0;
  const rStatus = readiness.readiness || "NOT_READY";
  const rColors = READINESS_COLORS[rStatus] || READINESS_COLORS.NOT_READY;

  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "config", label: "Configuration" },
    { key: "infra", label: "Infrastructure" },
    { key: "providers", label: "Providers" },
    { key: "security", label: "Security" },
  ];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="production_golive">
      <div data-testid="production-golive-dashboard" className="space-y-6 pb-10">
        {/* Header with Readiness Score */}
        <div className={`${rColors.bg} ${rColors.border} border rounded-2xl p-6 ring-1 ${rColors.ring}`}>
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <h1 data-testid="golive-title" className="text-2xl font-bold text-zinc-100 tracking-tight">Production Go-Live</h1>
              <p className="text-sm text-zinc-400 mt-1">Sistem hazirlik durumu ve production dogrulama</p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div data-testid="readiness-score" className={`text-4xl font-black tabular-nums ${rColors.text}`}>{rScore}%</div>
                <div className="text-xs text-zinc-500 mt-0.5">Readiness Score</div>
              </div>
              <div data-testid="readiness-status" className={`px-4 py-2 rounded-xl text-base font-bold ${rColors.bg} ${rColors.border} border ${rColors.text}`}>
                {rStatus}
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-zinc-900/60 p-1 rounded-xl border border-zinc-800/60">
          {tabs.map(t => (
            <button
              key={t.key}
              data-testid={`tab-${t.key}`}
              onClick={() => setActiveTab(t.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeTab === t.key
                  ? "bg-zinc-700/60 text-zinc-100 shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40"
              }`}
            >
              {t.label}
            </button>
          ))}
          <button
            data-testid="refresh-btn"
            onClick={fetchData}
            className="ml-auto px-3 py-2 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40 transition-all"
          >
            Yenile
          </button>
        </div>

        {/* TAB: Overview */}
        {activeTab === "overview" && (
          <div className="space-y-5">
            {/* Subsystem Summary Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricBox testId="metric-redis" label="Redis" value={redis.connected ? "Connected" : "Offline"} sub={redis.mode} />
              <MetricBox testId="metric-mongo" label="MongoDB" value={mongo.overall_status || "unknown"} sub={`Pool: ${mongo.connection_pool?.current_connections || 0}`} />
              <MetricBox testId="metric-workers" label="Workers" value={`${workers.queues?.length || 0} Queues`} sub={`Submitted: ${workers.total_submitted || 0}`} />
              <MetricBox testId="metric-backup" label="Backup" value={backup.enabled ? "Enabled" : "Disabled"} sub={`Retention: ${backup.retention_days || 30}d`} />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricBox testId="metric-config" label="Config" value={`${config.total_configured || 0}/${config.total_required || 0}`} sub={config.overall_status} />
              <MetricBox testId="metric-providers" label="Providers" value={`${providers.active_providers || 0}/${providers.total_providers || 3}`} sub="Active" />
              <MetricBox testId="metric-security" label="Security" value={`${security.score || 0}%`} sub={security.overall_status} />
              <MetricBox testId="metric-observability" label="Observability" value={observability.otel?.active ? "Active" : "Inactive"} sub={observability.sentry?.active ? "Sentry ON" : "Sentry OFF"} />
            </div>

            {/* Subsystem Check Details */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {readiness.checks && Object.entries(readiness.checks).map(([key, val]) => (
                <div key={key} className="bg-zinc-900/60 border border-zinc-800/50 rounded-lg p-4 flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-300 capitalize">{key}</span>
                  <Badge status={val.status} testId={`check-${key}`} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB: Configuration */}
        {activeTab === "config" && (
          <div className="space-y-5">
            <Panel title="Environment Variables" status={config.overall_status} testId="panel-config">
              {config.categories && Object.entries(config.categories).map(([cat, catData]) => (
                <div key={cat} className="space-y-2">
                  <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider pt-2">{cat} ({catData.configured}/{catData.total})</div>
                  {catData.variables?.map(v => (
                    <div key={v.variable} className="flex items-center justify-between py-1.5 border-b border-zinc-800/40 last:border-0">
                      <div>
                        <span className="text-sm text-zinc-300 font-mono">{v.variable}</span>
                        <span className="text-xs text-zinc-600 ml-2">{v.description}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {v.masked_value && <span className="text-xs text-zinc-600 font-mono">{v.masked_value}</span>}
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
            {/* Redis */}
            <Panel title="Redis Cluster" status={redis.connected ? "connected" : "disconnected"} testId="panel-redis">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="redis-mode" label="Mode" value={redis.mode} />
                <MetricBox testId="redis-connected" label="Connected" value={redis.connected ? "Yes" : "No"} />
                <MetricBox testId="redis-reconnects" label="Reconnects" value={redis.metrics?.reconnects || 0} />
                <MetricBox testId="redis-cmds" label="Commands" value={redis.metrics?.commands_sent || 0} />
              </div>
            </Panel>

            {/* MongoDB */}
            <Panel title="MongoDB Production" status={mongo.overall_status} testId="panel-mongo">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="mongo-pool" label="Connections" value={mongo.connection_pool?.current_connections || 0} sub={`Available: ${mongo.connection_pool?.available_connections || 0}`} />
                <MetricBox testId="mongo-version" label="Version" value={mongo.connection_pool?.mongo_version || "unknown"} />
                <MetricBox testId="mongo-replica" label="Replica Set" value={mongo.replica_set?.is_replica_set ? "Yes" : "No"} sub={mongo.replica_set?.status} />
                <MetricBox testId="mongo-indexes" label="Index Status" value={mongo.index_validation?.status || "unknown"} sub={`Missing: ${mongo.index_validation?.missing_index_count || 0}`} />
              </div>
              {/* Collection Health */}
              {mongo.collection_health?.health?.critical && (
                <div className="mt-3">
                  <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Critical Collections</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {Object.entries(mongo.collection_health.health.critical).map(([name, info]) => (
                      <div key={name} className="bg-zinc-800/40 rounded-lg px-3 py-2 flex items-center justify-between">
                        <span className="text-xs text-zinc-400 font-mono">{name}</span>
                        <span className="text-xs text-zinc-300 font-bold tabular-nums">{info.document_count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Panel>

            {/* Workers */}
            <Panel title="Worker Cluster" status="active" testId="panel-workers">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="worker-queues" label="Queues" value={workers.queues?.length || 0} />
                <MetricBox testId="worker-submitted" label="Submitted" value={workers.total_submitted || 0} />
                <MetricBox testId="worker-completed" label="Completed" value={workers.total_completed || 0} />
                <MetricBox testId="worker-failed" label="Failed" value={workers.total_failed || 0} />
              </div>
              {workers.queue_details && (
                <div className="mt-3 space-y-1">
                  {Object.entries(workers.queue_details).map(([qName, qData]) => (
                    <div key={qName} className="flex items-center justify-between py-2 border-b border-zinc-800/50 last:border-0">
                      <div>
                        <span className="text-sm font-medium text-zinc-300">{qName}</span>
                        <span className="text-xs text-zinc-600 ml-2">{qData.description}</span>
                      </div>
                      <div className="flex gap-3 text-xs">
                        <span className="text-zinc-400">Priority: <span className="text-zinc-200">{qData.priority}</span></span>
                        <span className="text-zinc-400">Retries: <span className="text-zinc-200">{qData.max_retries}</span></span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            {/* Backup */}
            <Panel title="Backup & DR" status={backup.enabled ? "enabled" : "disabled"} testId="panel-backup">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="backup-enabled" label="Enabled" value={backup.enabled ? "Yes" : "No"} />
                <MetricBox testId="backup-retention" label="Retention" value={`${backup.retention_days || 30} days`} />
                <MetricBox testId="backup-rpo" label="RPO Target" value="24h" />
                <MetricBox testId="backup-rto" label="RTO Target" value="4h" />
              </div>
            </Panel>

            {/* Observability */}
            <Panel title="Observability Stack" status={observability.otel?.active || observability.sentry?.active ? "active" : "inactive"} testId="panel-observability">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox testId="otel-status" label="OpenTelemetry" value={observability.otel?.active ? "Active" : "Inactive"} />
                <MetricBox testId="sentry-status" label="Sentry" value={observability.sentry?.active ? "Active" : "Inactive"} />
                <MetricBox testId="grafana-status" label="Grafana" value="Template Ready" />
                <MetricBox testId="prometheus-status" label="Prometheus" value="Configured" />
              </div>
            </Panel>
          </div>
        )}

        {/* TAB: Providers */}
        {activeTab === "providers" && (
          <div className="space-y-5">
            <Panel title="Messaging Providers" status={providers.active_providers > 0 ? "partial" : "not_configured"} testId="panel-providers">
              {providers.providers && Object.entries(providers.providers).map(([name, pData]) => (
                <ProviderRow key={name} name={name} data={pData} />
              ))}
              {providers.providers && Object.values(providers.providers).some(p => p.missing_vars?.length > 0) && (
                <div className="mt-3 bg-zinc-800/40 rounded-lg p-3 space-y-2">
                  <div className="text-xs font-semibold text-amber-400 uppercase">Missing Configuration</div>
                  {Object.entries(providers.providers).filter(([, p]) => p.missing_vars?.length > 0).map(([name, pData]) => (
                    <div key={name} className="text-xs text-zinc-400">
                      <span className="font-medium text-zinc-300">{name}:</span> {pData.missing_vars.join(", ")}
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            {/* Delivery Metrics */}
            <Panel title="Delivery Metrics" testId="panel-delivery">
              {Object.keys(providers.delivery_metrics || {}).length === 0 ? (
                <div className="text-sm text-zinc-500">Henuz delivery verisi yok.</div>
              ) : (
                Object.entries(providers.delivery_metrics).map(([name, m]) => (
                  <div key={name} className="space-y-2">
                    <div className="text-xs font-semibold text-zinc-400 uppercase">{name}</div>
                    <div className="grid grid-cols-4 gap-3">
                      <MetricBox label="Sent" value={m.total_sent} testId={`delivery-${name}-sent`} />
                      <MetricBox label="Delivered" value={m.delivered} testId={`delivery-${name}-delivered`} />
                      <MetricBox label="Success Rate" value={`${m.success_rate}%`} testId={`delivery-${name}-rate`} />
                      <MetricBox label="Avg Latency" value={`${m.avg_latency_ms}ms`} testId={`delivery-${name}-latency`} />
                    </div>
                  </div>
                ))
              )}
            </Panel>

            {/* Fallback Chain */}
            <Panel title="Fallback Chain" testId="panel-fallback">
              <div className="flex items-center gap-2">
                {(providers.fallback_chain || []).map((p, i) => (
                  <React.Fragment key={p}>
                    <span className="px-3 py-1.5 bg-zinc-800/60 border border-zinc-700/40 rounded-lg text-xs text-zinc-300 font-medium">{p}</span>
                    {i < (providers.fallback_chain?.length || 0) - 1 && <span className="text-zinc-600 text-xs">-&gt;</span>}
                  </React.Fragment>
                ))}
              </div>
            </Panel>
          </div>
        )}

        {/* TAB: Security */}
        {activeTab === "security" && (
          <div className="space-y-5">
            <Panel title="Security Go-Live Checklist" status={security.overall_status} testId="panel-security" icon={null}>
              <div className="flex items-center gap-6 mb-4">
                <div>
                  <span className={`text-3xl font-black tabular-nums ${security.score >= 80 ? "text-emerald-400" : security.score >= 50 ? "text-amber-400" : "text-red-400"}`}>
                    {security.score || 0}%
                  </span>
                  <span className="text-xs text-zinc-500 ml-1">Score</span>
                </div>
                <div className="text-sm text-zinc-400">{security.passed || 0}/{security.total || 0} checks passed</div>
              </div>
              {security.checks?.map((check, i) => (
                <CheckRow
                  key={i}
                  label={check.check?.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) || `Check ${i + 1}`}
                  pass={check.pass}
                  detail={check.note || check.error || null}
                />
              ))}
              {security.failed_checks?.length > 0 && (
                <div className="mt-3 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                  <div className="text-xs font-semibold text-red-400 mb-1">Failed Checks</div>
                  <div className="text-xs text-red-300">{security.failed_checks.join(", ")}</div>
                </div>
              )}
            </Panel>
          </div>
        )}
      </div>
    </Layout>
  );
}
