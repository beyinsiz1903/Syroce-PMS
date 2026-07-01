import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from "react";

const API = "";

// Status badge component
const StatusBadge = ({ status }) => {
  const colors = {
    healthy: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    connected: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    running: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    active: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    disconnected: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    degraded: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    unhealthy: "bg-red-500/15 text-red-400 border-red-500/30",
    disabled: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
    development: "bg-sky-500/15 text-sky-400 border-sky-500/30",
    single: "bg-sky-500/15 text-sky-400 border-sky-500/30",
    simulated: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  };
  const c = colors[status] || colors.disabled;
  return (
    <span data-testid={`status-badge-${status}`} className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${c}`}>
      {status}
    </span>
  );
};

// Metric card
const MetricCard = ({ label, value, sub, testId }) => (
  <div data-testid={testId} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4">
    <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">{label}</div>
    <div className="text-2xl font-bold text-zinc-100">{value ?? "—"}</div>
    {sub && <div className="text-xs text-zinc-500 mt-1">{sub}</div>}
  </div>
);

// Section wrapper
const Section = ({ title, status, children, testId }) => (
  <div data-testid={testId} className="bg-zinc-900/80 border border-zinc-700/40 rounded-xl p-5 space-y-4">
    <div className="flex items-center justify-between">
      <h3 className="text-base font-semibold text-zinc-200">{title}</h3>
      {status && <StatusBadge status={status} />}
    </div>
    {children}
  </div>
);

// Queue row
const QueueRow = ({ name, data }) => (
  <div data-testid={`queue-${name}`} className="flex items-center justify-between py-2 border-b border-zinc-800 last:border-0">
    <div>
      <span className="text-sm font-medium text-zinc-300">{name}</span>
      <span className="text-xs text-zinc-500 ml-2">{data.description}</span>
    </div>
    <div className="flex gap-4 text-xs text-zinc-400">
      <span>Submitted: <span className="text-zinc-200">{data.metrics?.submitted || 0}</span></span>
      <span>Completed: <span className="text-emerald-400">{data.metrics?.completed || 0}</span></span>
      <span>Failed: <span className="text-red-400">{data.metrics?.failed || 0}</span></span>
      <span>Pending: <span className="text-amber-400">{data.pending || 0}</span></span>
    </div>
  </div>
);

export default function InfraHardeningDashboard({ user, tenant, onLogout, embedded = false }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [backupTriggered, setBackupTriggered] = useState(false);

  const token = localStorage.getItem("token");

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`/api/infra/summary`, {
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

  const triggerBackup = async () => {
    try {
      setBackupTriggered(true);
      await fetch(`/api/infra/backup/trigger`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      setTimeout(() => { setBackupTriggered(false); fetchData(); }, 3000);
    } catch {
      setBackupTriggered(false);
    }
  };

  if (loading) {
    if (embedded) return <div data-testid="infra-loading" className="flex items-center justify-center min-h-[40vh]"><div className="text-zinc-400 animate-pulse text-lg">Altyapi durumu yükleniyor...</div></div>;
    return (
      <>
        <div data-testid="infra-loading" className="flex items-center justify-center min-h-[60vh]">
          <div className="text-zinc-400 animate-pulse text-lg">Altyapi durumu yükleniyor...</div>
        </div>
      </>
    );
  }

  if (error) {
    if (embedded) return <div data-testid="infra-error" className="flex items-center justify-center min-h-[40vh]"><div className="text-red-400">Hata: {error}</div></div>;
    return (
      <>
        <div data-testid="infra-error" className="flex items-center justify-center min-h-[60vh]">
          <div className="text-red-400">Hata: {error}</div>
        </div>
      </>
    );
  }

  const redis = data?.redis_cluster || {};
  const workers = data?.worker_queues || {};
  const secrets = data?.secrets || {};
  const backup = data?.backup || {};
  const obs = data?.observability || {};
  const scaling = data?.scaling || {};
  const container = data?.container || {};
  const locks = data?.distributed_locks || {};

  const dashboardContent = (
    <div data-testid="infra-hardening-dashboard" className="space-y-6 p-4">
      {/* Header */}
      {!embedded && (
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">{t("techDashboards.infraHardening")}</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Production-grade SaaS altyapi durumu ve izleme
            </p>
          </div>
          <button
            data-testid="refresh-btn"
            onClick={fetchData}
            className="px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-300 hover:bg-zinc-700 transition"
          >
            Yenile
          </button>
        </div>
      )}
      {embedded && (
        <div className="flex items-center justify-end">
          <button data-testid="refresh-btn" onClick={fetchData} className="px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-300 hover:bg-zinc-700 transition">Yenile</button>
        </div>
      )}

        {/* Top Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <MetricCard testId="metric-redis-mode" label="Redis Mode" value={redis.mode || "—"} sub={redis.connected ? "Connected" : "Fallback"} />
          <MetricCard testId="metric-queues" label="Worker Queues" value={workers.queues?.length || 0} sub={`${workers.total_pending || 0} pending`} />
          <MetricCard testId="metric-secrets" label="Secrets Provider" value={secrets.provider || "env"} sub={secrets.status || "—"} />
          <MetricCard testId="metric-backup" label="Backup" value={backup.enabled ? "Aktif" : "Pasif"} sub={`RPO: ${backup.rpo_target || "—"}`} />
          <MetricCard testId="metric-instances" label="Instances" value={scaling.total_instances || 1} sub={`${scaling.active_instances || 1} active`} />
          <MetricCard testId="metric-container" label="Container" value={container.is_containerized ? "Docker" : "Native"} sub={container.hostname || "—"} />
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Redis Cluster */}
          <Section testId="section-redis" title="Redis Cluster" status={redis.connected ? "connected" : "disconnected"}>
            <div className="grid grid-cols-2 gap-3">
              <MetricCard testId="redis-latency" label="Latency" value={redis.health?.latency_ms ? `${redis.health.latency_ms}ms` : "—"} />
              <MetricCard testId="redis-memory" label="Memory" value={redis.health?.used_memory_human || "—"} />
              <MetricCard testId="redis-clients" label="Clients" value={redis.health?.connected_clients ?? "—"} />
              <MetricCard testId="redis-reconnects" label="Reconnects" value={redis.metrics?.reconnects || 0} />
            </div>
            <div className="mt-3 text-xs text-zinc-500">
              Mode: <span className="text-zinc-300">{redis.mode}</span> | 
              Pool: <span className="text-zinc-300">{redis.metrics?.max_connections || "—"}</span>
            </div>
          </Section>

          {/* Distributed Locks */}
          <Section testId="section-locks" title="Distributed Locks" status={locks.fallback_used > 0 ? "development" : "active"}>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard testId="locks-acquired" label="Acquired" value={locks.locks_acquired || 0} />
              <MetricCard testId="locks-active" label="Active" value={locks.active_locks || 0} />
              <MetricCard testId="locks-contention" label="Contention" value={locks.contention_events || 0} />
            </div>
            {locks.fallback_used > 0 && (
              <div className="text-xs text-amber-400 mt-2">In-process fallback kullaniliyor ({locks.fallback_used} kez)</div>
            )}
          </Section>

          {/* Worker Queues */}
          <Section testId="section-workers" title="Background Workers" status={workers.total_failed > 0 ? "degraded" : "running"}>
            <div className="grid grid-cols-4 gap-2 mb-3">
              <MetricCard testId="workers-submitted" label="Submitted" value={workers.total_submitted || 0} />
              <MetricCard testId="workers-completed" label="Completed" value={workers.total_completed || 0} />
              <MetricCard testId="workers-failed" label="Failed" value={workers.total_failed || 0} />
              <MetricCard testId="workers-stuck" label="Stuck" value={workers.stuck_candidates || 0} />
            </div>
            <div className="space-y-0 border-t border-zinc-800 pt-2">
              {workers.queue_details && Object.entries(workers.queue_details).map(([name, qd]) => (
                <QueueRow key={name} name={name} data={qd} />
              ))}
            </div>
          </Section>

          {/* Secrets Management */}
          <Section testId="section-secrets" title="Secrets Management" status={secrets.status || "disabled"}>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard testId="secrets-provider-name" label="Provider" value={secrets.provider || "env"} />
              <MetricCard testId="secrets-requests" label="Requests" value={secrets.metrics?.total_requests || 0} />
              <MetricCard testId="secrets-errors" label="Errors" value={secrets.metrics?.errors || 0} />
            </div>
            <div className="text-xs text-zinc-500 mt-2">
              {secrets.provider === "env" && "Yerel ortam degiskenleri kullaniliyor (gelistirme modu)"}
              {secrets.provider === "aws" && "AWS Secrets Manager bağlı"}
              {secrets.provider === "vault" && "HashiCorp Vault bağlı"}
            </div>
          </Section>

          {/* Backup & DR */}
          <Section testId="section-backup" title="Backup & Disaster Recovery" status={backup.enabled ? "active" : "disabled"}>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard testId="backup-total" label="Total Backups" value={backup.metrics?.total_backups || 0} />
              <MetricCard testId="backup-successful" label="Successful" value={backup.metrics?.successful_backups || 0} />
              <MetricCard testId="backup-last-duration" label="Last Duration" value={backup.metrics?.last_backup_duration_sec ? `${backup.metrics.last_backup_duration_sec}s` : "—"} />
            </div>
            <div className="flex items-center justify-between mt-3">
              <div className="text-xs text-zinc-500">
                RPO: <span className="text-zinc-300">{backup.rpo_target}</span> | 
                RTO: <span className="text-zinc-300">{backup.rto_target}</span> | 
                Retention: <span className="text-zinc-300">{backup.retention_days} gun</span>
              </div>
              <button
                data-testid="trigger-backup-btn"
                onClick={triggerBackup}
                disabled={backupTriggered}
                className="px-3 py-1.5 bg-emerald-600/20 border border-emerald-600/40 text-emerald-400 rounded text-xs hover:bg-emerald-600/30 transition disabled:opacity-50"
              >
                {backupTriggered ? "Baslatildi..." : "Backup Baslat"}
              </button>
            </div>
          </Section>

          {/* Cloud Observability */}
          <Section testId="section-observability" title="Cloud Observability" status={obs.otel?.active || obs.sentry?.active ? "active" : "disabled"}>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-zinc-400">OpenTelemetry</span>
                <StatusBadge status={obs.otel?.active ? "active" : "disabled"} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-zinc-400">Sentry</span>
                <StatusBadge status={obs.sentry?.active ? "active" : "disabled"} />
              </div>
              {obs.otel?.active && (
                <div className="text-xs text-zinc-500">
                  Spans: {obs.otel.spans_created} created, Endpoint: {obs.otel.endpoint}
                </div>
              )}
              {obs.sentry?.active && (
                <div className="text-xs text-zinc-500">
                  Events: {obs.sentry.events_sent}, Errors: {obs.sentry.errors_captured}
                </div>
              )}
              {obs.cloud_metrics?.latency && Object.keys(obs.cloud_metrics.latency).length > 0 && (
                <div className="text-xs text-zinc-500 mt-2">
                  Latency metrics: {Object.keys(obs.cloud_metrics.latency).length} endpoints tracked
                </div>
              )}
            </div>
          </Section>
        </div>

        {/* Horizontal Scaling — Full Width */}
        <Section testId="section-scaling" title="Horizontal Scaling" status={scaling.scaling_mode || "single"}>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <MetricCard testId="scaling-mode" label="Mode" value={scaling.scaling_mode || "single"} />
            <MetricCard testId="scaling-current" label="Current Instance" value={scaling.current_instance || "—"} />
            <MetricCard testId="scaling-total" label="Total Instances" value={scaling.total_instances || 1} />
            <MetricCard testId="scaling-active" label="Active" value={scaling.active_instances || 1} />
            <MetricCard testId="scaling-stale" label="Stale" value={scaling.stale_instances || 0} />
          </div>
          {scaling.stateless_check && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(scaling.stateless_check.checks || {}).map(([check, passed]) => (
                <span key={check} className={`px-2 py-0.5 rounded text-xs ${passed ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
                  {check.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}
        </Section>

        {/* Container Info — Full Width */}
        <Section testId="section-container" title="Container & Runtime" status={container.is_containerized ? "active" : "development"}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard testId="container-type" label="Runtime" value={container.is_containerized ? "Containerized" : "Native"} />
            <MetricCard testId="container-k8s" label="Kubernetes" value={container.is_kubernetes ? "Yes" : "No"} />
            <MetricCard testId="container-python" label="Python" value={container.python_version || "—"} />
            <MetricCard testId="container-host" label="Hostname" value={container.hostname || "—"} />
          </div>
          {container.environment_vars_present && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(container.environment_vars_present).map(([envVar, present]) => (
                <span key={envVar} className={`px-2 py-0.5 rounded text-xs ${
                  present === true || (typeof present === "string" && present !== "false" && present !== "env") 
                    ? "bg-emerald-500/10 text-emerald-400" 
                    : "bg-zinc-700/50 text-zinc-500"
                }`}>
                  {envVar}: {typeof present === "boolean" ? (present ? "set" : "—") : present}
                </span>
              ))}
            </div>
          )}
        </Section>
      </div>
  );

  if (embedded) return dashboardContent;

  return (
    <>
      {dashboardContent}
    </>
  );
}
