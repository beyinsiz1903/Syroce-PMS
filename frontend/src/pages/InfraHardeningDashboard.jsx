import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { confirmDialog } from "@/lib/dialogs";
const API = "";

const STATUS_LABELS = {
  healthy: "Sağlıklı",
  connected: "Bağlı",
  running: "Çalışıyor",
  active: "Aktif",
  disconnected: "Bağlantı yok",
  degraded: "Performans düşük",
  unhealthy: "Sağlıksız",
  disabled: "Devre dışı",
  development: "Geliştirme",
  single: "Tek sunucu",
  simulated: "Simülasyon"
};

const QUEUE_LABELS = {
  default: "Genel görevler",
  ml: "Model eğitimi ve tahmin",
  analytics: "Analiz ve rapor üretimi",
  messaging: "Mesaj teslimi ve yeniden deneme",
  pipeline: "Veri işleme akışları",
  backup: "Yedekleme ve bakım"
};

// Status badge component
const StatusBadge = ({
  status
}) => {
  const colors = {
    healthy: "bg-emerald-50 text-emerald-700 border-emerald-200",
    connected: "bg-emerald-50 text-emerald-700 border-emerald-200",
    running: "bg-emerald-50 text-emerald-700 border-emerald-200",
    active: "bg-emerald-50 text-emerald-700 border-emerald-200",
    disconnected: "bg-amber-50 text-amber-700 border-amber-200",
    degraded: "bg-amber-50 text-amber-700 border-amber-200",
    unhealthy: "bg-rose-50 text-rose-700 border-rose-200",
    disabled: "bg-slate-50 text-slate-700 border-slate-200",
    development: "bg-sky-50 text-sky-700 border-sky-200",
    single: "bg-sky-50 text-sky-700 border-sky-200",
    simulated: "bg-violet-50 text-violet-700 border-violet-200"
  };
  const c = colors[status] || colors.disabled;
  return <span data-testid={`status-badge-${status}`} className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${c}`}>
      {STATUS_LABELS[status] || status}
    </span>;
};

// Metric card
const MetricCard = ({
  label,
  value,
  sub,
  testId
}) => <div data-testid={testId} className="bg-slate-50 border border-slate-200 rounded-lg p-4">
    <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">{label}</div>
    <div className="text-2xl font-bold text-slate-900">{value ?? "—"}</div>
    {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
  </div>;

// Section wrapper
const Section = ({
  title,
  status,
  children,
  testId
}) => <div data-testid={testId} className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
    <div className="flex items-center justify-between">
      <h3 className="text-base font-semibold text-slate-800">{title}</h3>
      {status && <StatusBadge status={status} />}
    </div>
    {children}
  </div>;

// Queue row
const QueueRow = ({
  name,
  data
}) => <div data-testid={`queue-${name}`} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
    <div>
      <span className="text-sm font-medium text-slate-700">{QUEUE_LABELS[name] || name}</span>
    </div>
    <div className="flex gap-4 text-xs text-slate-500">
      <span>Gönderilen: <span className="text-slate-800">{data.metrics?.submitted || 0}</span></span>
      <span>Tamamlanan: <span className="text-emerald-600">{data.metrics?.completed || 0}</span></span>
      <span>Hatalı: <span className="text-rose-600">{data.metrics?.failed || 0}</span></span>
      <span>Bekleyen: <span className="text-amber-600">{data.pending || 0}</span></span>
    </div>
  </div>;
export default function InfraHardeningDashboard({
  user,
  tenant,
  onLogout,
  embedded = false
}) {
  const {
    t
  } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [backupTriggered, setBackupTriggered] = useState(false);
  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`/api/infra/summary`, {
        credentials: "include",
        headers: {}
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
  }, []);
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);
  const triggerBackup = async () => {
    if (!await confirmDialog({
      message: "Yeni bir sistem yedeği başlatmak istediğinize emin misiniz?",
      confirmText: "Yedeklemeyi Başlat"
    })) return;
    try {
      setBackupTriggered(true);
      const response = await fetch(`/api/infra/backup/trigger`, {
        credentials: "include",
        method: "POST",
        headers: {}
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      toast.success("Yedekleme arka planda başlatıldı");
      setTimeout(() => {
        setBackupTriggered(false);
        fetchData();
      }, 3000);
    } catch {
      setBackupTriggered(false);
      toast.error("Yedekleme başlatılamadı");
    }
  };
  if (loading) {
    if (embedded) return <div data-testid="infra-loading" className="flex items-center justify-center min-h-[40vh]"><div className="text-slate-500 animate-pulse text-lg">Altyapı durumu yükleniyor...</div></div>;
    return <>
        <div data-testid="infra-loading" className="flex items-center justify-center min-h-[60vh]">
          <div className="text-slate-500 animate-pulse text-lg">Altyapı durumu yükleniyor...</div>
        </div>
      </>;
  }
  if (error) {
    if (embedded) return <div data-testid="infra-error" className="flex items-center justify-center min-h-[40vh]"><div className="text-rose-600">Hata: {error}</div></div>;
    return <>
        <div data-testid="infra-error" className="flex items-center justify-center min-h-[60vh]">
          <div className="text-rose-600">Hata: {error}</div>
        </div>
      </>;
  }
  const redis = data?.redis_cluster || {};
  const workers = data?.worker_queues || {};
  const secrets = data?.secrets || {};
  const backup = data?.backup || {};
  const obs = data?.observability || {};
  const scaling = data?.scaling || {};
  const container = data?.container || {};
  const locks = data?.distributed_locks || {};
  const dashboardContent = <div data-testid="infra-hardening-dashboard" className="space-y-6 p-4">
      {/* Header */}
      {!embedded && <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{t("techDashboards.infraHardening")}</h1>
            <p className="text-sm text-slate-500 mt-1">
              Üretim ortamı altyapı durumu ve izleme
            </p>
          </div>
          <button data-testid="refresh-btn" onClick={fetchData} className="px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition">
            Yenile
          </button>
        </div>}
      {embedded && <div className="flex items-center justify-end">
          <button data-testid="refresh-btn" onClick={fetchData} className="px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition">Yenile</button>
        </div>}

        {/* Top Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <MetricCard testId="metric-redis-mode" label="Redis Çalışma Biçimi" value={redis.mode || "—"} sub={redis.connected ? "Bağlı" : "Yedek yöntem"} />
          <MetricCard testId="metric-queues" label="Görev Kuyrukları" value={workers.queues?.length || 0} sub={`${workers.total_pending || 0} bekleyen`} />
          <MetricCard testId="metric-secrets" label="Gizli Bilgi Sağlayıcısı" value={secrets.provider || "env"} sub={STATUS_LABELS[secrets.status] || secrets.status || "—"} />
          <MetricCard testId="metric-backup" label="Yedekleme" value={backup.enabled ? "Aktif" : "Pasif"} sub={`Kurtarma noktası: ${backup.rpo_target || "—"}`} />
          <MetricCard testId="metric-instances" label="Sunucular" value={scaling.total_instances || 1} sub={`${scaling.active_instances || 1} aktif`} />
          <MetricCard testId="metric-container" label="Çalışma Ortamı" value={container.is_containerized ? "Docker" : "Yerel"} sub={container.hostname || "—"} />
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Redis Cluster */}
          <Section testId="section-redis" title="Redis Kümesi" status={redis.connected ? "connected" : "disconnected"}>
            <div className="grid grid-cols-2 gap-3">
              <MetricCard testId="redis-latency" label="Gecikme" value={redis.health?.latency_ms ? `${redis.health.latency_ms}ms` : "—"} />
              <MetricCard testId="redis-memory" label="Bellek" value={redis.health?.used_memory_human || "—"} />
              <MetricCard testId="redis-clients" label="Bağlantılar" value={redis.health?.connected_clients ?? "—"} />
              <MetricCard testId="redis-reconnects" label="Yeniden Bağlantı" value={redis.metrics?.reconnects || 0} />
            </div>
            <div className="mt-3 text-xs text-slate-500">
              Çalışma biçimi: <span className="text-slate-700">{redis.mode}</span> |
              Bağlantı havuzu: <span className="text-slate-700">{redis.metrics?.max_connections || "—"}</span>
            </div>
          </Section>

          {/* Distributed Locks */}
          <Section testId="section-locks" title="Dağıtık Kilitler" status={locks.fallback_used > 0 ? "development" : "active"}>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard testId="locks-acquired" label="Alınan" value={locks.locks_acquired || 0} />
              <MetricCard testId="locks-active" label="Aktif" value={locks.active_locks || 0} />
              <MetricCard testId="locks-contention" label="Çakışma" value={locks.contention_events || 0} />
            </div>
            {locks.fallback_used > 0 && <div className="text-xs text-amber-600 mt-2">Süreç içi yedek yöntem kullanılıyor ({locks.fallback_used} kez)</div>}
          </Section>

          {/* Worker Queues */}
          <Section testId="section-workers" title="Arka Plan İşleyicileri" status={workers.total_failed > 0 ? "degraded" : "running"}>
            <div className="grid grid-cols-4 gap-2 mb-3">
              <MetricCard testId="workers-submitted" label="Gönderilen" value={workers.total_submitted || 0} />
              <MetricCard testId="workers-completed" label="Tamamlanan" value={workers.total_completed || 0} />
              <MetricCard testId="workers-failed" label="Hatalı" value={workers.total_failed || 0} />
              <MetricCard testId="workers-stuck" label="Takılan" value={workers.stuck_candidates || 0} />
            </div>
            <div className="space-y-0 border-t border-slate-100 pt-2">
              {workers.queue_details && Object.entries(workers.queue_details).map(([name, qd]) => <QueueRow key={name} name={name} data={qd} />)}
            </div>
          </Section>

          {/* Secrets Management */}
          <Section testId="section-secrets" title="Gizli Bilgi Yönetimi" status={secrets.status || "disabled"}>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard testId="secrets-provider-name" label="Sağlayıcı" value={secrets.provider || "env"} />
              <MetricCard testId="secrets-requests" label="İstekler" value={secrets.metrics?.total_requests || 0} />
              <MetricCard testId="secrets-errors" label="Hatalar" value={secrets.metrics?.errors || 0} />
            </div>
            <div className="text-xs text-slate-500 mt-2">
              {secrets.provider === "env" && "Ortam değişkenleri kullanılıyor"}
              {secrets.provider === "aws" && "AWS Secrets Manager bağlı"}
              {secrets.provider === "vault" && "HashiCorp Vault bağlı"}
            </div>
          </Section>

          {/* Backup & DR */}
          <Section testId="section-backup" title="Yedekleme ve Felaket Kurtarma" status={backup.enabled ? "active" : "disabled"}>
            <div className="grid grid-cols-3 gap-3">
              <MetricCard testId="backup-total" label="Toplam Yedek" value={backup.metrics?.total_backups || 0} />
              <MetricCard testId="backup-successful" label="Başarılı" value={backup.metrics?.successful_backups || 0} />
              <MetricCard testId="backup-last-duration" label="Son Süre" value={backup.metrics?.last_backup_duration_sec ? `${backup.metrics.last_backup_duration_sec}s` : "—"} />
            </div>
            <div className="flex items-center justify-between mt-3">
              <div className="text-xs text-slate-500">
                RPO: <span className="text-slate-700">{backup.rpo_target}</span> | 
                RTO: <span className="text-slate-700">{backup.rto_target}</span> | 
                Saklama: <span className="text-slate-700">{backup.retention_days} gün</span>
              </div>
              <button data-testid="trigger-backup-btn" onClick={triggerBackup} disabled={backupTriggered} className="px-3 py-1.5 bg-emerald-600/20 border border-emerald-600/40 text-emerald-600 rounded text-xs hover:bg-emerald-600/30 transition disabled:opacity-50">
                {backupTriggered ? "Başlatıldı..." : "Yedekleme Başlat"}
              </button>
            </div>
          </Section>

          {/* Cloud Observability */}
          <Section testId="section-observability" title="Bulut Gözlemlenebilirliği" status={obs.otel?.active || obs.sentry?.active ? "active" : "disabled"}>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500">OpenTelemetry</span>
                <StatusBadge status={obs.otel?.active ? "active" : "disabled"} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500">Sentry</span>
                <StatusBadge status={obs.sentry?.active ? "active" : "disabled"} />
              </div>
              {obs.otel?.active && <div className="text-xs text-slate-500">
                  Oluşturulan iz: {obs.otel.spans_created}, hedef servis: {obs.otel.endpoint}
                </div>}
              {obs.sentry?.active && <div className="text-xs text-slate-500">
                  Olaylar: {obs.sentry.events_sent}, hatalar: {obs.sentry.errors_captured}
                </div>}
              {obs.cloud_metrics?.latency && Object.keys(obs.cloud_metrics.latency).length > 0 && <div className="text-xs text-slate-500 mt-2">
                  Gecikmesi izlenen servis yolu: {Object.keys(obs.cloud_metrics.latency).length}
                </div>}
            </div>
          </Section>
        </div>

        {/* Horizontal Scaling — Full Width */}
        <Section testId="section-scaling" title="Yatay Ölçekleme" status={scaling.scaling_mode || "single"}>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <MetricCard testId="scaling-mode" label="Çalışma Biçimi" value={scaling.scaling_mode || "single"} />
            <MetricCard testId="scaling-current" label="Mevcut Sunucu" value={scaling.current_instance || "—"} />
            <MetricCard testId="scaling-total" label="Toplam Sunucu" value={scaling.total_instances || 1} />
            <MetricCard testId="scaling-active" label="Aktif" value={scaling.active_instances || 1} />
            <MetricCard testId="scaling-stale" label="Yanıt Vermeyen" value={scaling.stale_instances || 0} />
          </div>
          {scaling.stateless_check && <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(scaling.stateless_check.checks || {}).map(([check, passed]) => <span key={check} className={`px-2 py-0.5 rounded text-xs ${passed ? "bg-emerald-500/10 text-emerald-600" : "bg-red-500/10 text-rose-600"}`}>
                  {check.replace(/_/g, " ")}
                </span>)}
            </div>}
        </Section>

        {/* Container Info — Full Width */}
        <Section testId="section-container" title="Konteyner ve Çalışma Ortamı" status={container.is_containerized ? "active" : "development"}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard testId="container-type" label="Çalışma Ortamı" value={container.is_containerized ? "Konteyner" : "Yerel"} />
            <MetricCard testId="container-k8s" label="Kubernetes" value={container.is_kubernetes ? "Evet" : "Hayır"} />
            <MetricCard testId="container-python" label="Python" value={container.python_version || "—"} />
            <MetricCard testId="container-host" label="Sunucu Adı" value={container.hostname || "—"} />
          </div>
          {container.environment_vars_present && <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(container.environment_vars_present).map(([envVar, present]) => <span key={envVar} className={`px-2 py-0.5 rounded text-xs ${present === true || typeof present === "string" && present !== "false" && present !== "env" ? "bg-emerald-500/10 text-emerald-600" : "bg-slate-100 text-slate-500"}`}>
                  {envVar}: {typeof present === "boolean" ? present ? "Tanımlı" : "—" : present}
                </span>)}
            </div>}
        </Section>
      </div>;
  if (embedded) return dashboardContent;
  return <>
      {dashboardContent}
    </>;
}
