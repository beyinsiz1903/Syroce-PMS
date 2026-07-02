import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Activity, Database, Radio, Mail, AlertTriangle, Shield, RefreshCw, CheckCircle, XCircle, Clock } from "lucide-react";
const API = "";
function StatusIndicator({
  status
}) {
  const map = {
    healthy: {
      color: "bg-emerald-500",
      label: "Healthy"
    },
    degraded: {
      color: "bg-amber-500",
      label: "Degraded"
    },
    unhealthy: {
      color: "bg-red-500",
      label: "Unhealthy"
    },
    disconnected: {
      color: "bg-red-500",
      label: "Disconnected"
    },
    unknown: {
      color: "bg-zinc-400",
      label: "Unknown"
    }
  };
  const s = map[status] || map.unknown;
  return <span className="inline-flex items-center gap-1.5" data-testid={`status-${status}`}>
      <span className={`w-2 h-2 rounded-full ${s.color} animate-pulse`} />
      <span className="text-xs font-medium">{s.label}</span>
    </span>;
}
function MetricCard({
  title,
  value,
  subtitle,
  icon: Icon,
  variant = "default"
}) {
  const bg = variant === "danger" ? "bg-red-950/40 border-red-900/50" : variant === "warning" ? "bg-amber-950/40 border-amber-900/50" : variant === "success" ? "bg-emerald-950/40 border-emerald-900/50" : "bg-zinc-900/60 border-zinc-800";
  return <Card className={`${bg} border`} data-testid={`metric-card-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-zinc-400 uppercase tracking-wider">{title}</span>
          {Icon && <Icon className="w-4 h-4 text-zinc-500" />}
        </div>
        <div className="text-2xl font-bold text-zinc-100">{value}</div>
        {subtitle && <div className="text-xs text-zinc-500 mt-1">{subtitle}</div>}
      </CardContent>
    </Card>;
}
export default function RuntimeInfrastructureDashboard() {
  const {
    t
  } = useTranslation();
  const [overview, setOverview] = useState(null);
  const [persistence, setPersistence] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [alertEngine, setAlertEngine] = useState(null);
  const [messaging, setMessaging] = useState(null);
  const [observability, setObservability] = useState(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = {};
  const fetchData = useCallback(async () => {
    try {
      const [overviewRes, persistRes, alertsRes, engineRes, msgRes, obsRes] = await Promise.all([axios.get(`/runtime/overview`, {
        headers
      }).catch(() => ({
        data: null
      })), axios.get(`/runtime/persistence/health`, {
        headers
      }).catch(() => ({
        data: null
      })), axios.get(`/runtime/alerts/candidates`, {
        headers
      }).catch(() => ({
        data: []
      })), axios.get(`/runtime/alerts/engine-status`, {
        headers
      }).catch(() => ({
        data: null
      })), axios.get(`/runtime/messaging/status`, {
        headers
      }).catch(() => ({
        data: null
      })), axios.get(`/runtime/observability/summary`, {
        headers
      }).catch(() => ({
        data: null
      }))]);
      setOverview(overviewRes.data);
      setPersistence(persistRes.data);
      setAlerts(Array.isArray(alertsRes.data) ? alertsRes.data : []);
      setAlertEngine(engineRes.data);
      setMessaging(msgRes.data);
      setObservability(obsRes.data);
    } catch (err) {
      console.error("Runtime data fetch failed:", err);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);
  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 30000);
    return () => clearInterval(iv);
  }, [fetchData]);
  const evaluateAlerts = async () => {
    setEvaluating(true);
    try {
      const res = await axios.get(`/runtime/alerts/evaluate`, {
        headers
      });
      toast.success(`Alert taramasi tamamlandi: ${res.data.count} alert`);
      fetchData();
    } catch {
      toast.error("Alert taraması başarısız");
    } finally {
      setEvaluating(false);
    }
  };
  const acknowledgeAlert = async alertId => {
    try {
      await axios.post(`/runtime/alerts/${alertId}/acknowledge`, {}, {
        headers
      });
      toast.success("Alert onaylandi");
      fetchData();
    } catch {
      toast.error("Alert onaylama başarısız");
    }
  };
  if (loading) {
    return <div className="flex items-center justify-center h-64" data-testid="runtime-loading">
        <RefreshCw className="w-8 h-8 animate-spin text-zinc-400" />
      </div>;
  }
  const eb = overview?.event_bus || {};
  const db_status = overview?.database?.status || "unknown";
  const eventMetrics = overview?.event_metrics || {};
  return <div className="space-y-6 p-6 max-w-7xl mx-auto" data-testid="runtime-infrastructure-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">{t("techDashboards.runtimeInfra")}</h1>
          <p className="text-sm text-zinc-400 mt-1">Production runtime monitoring & alerts</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
          <Button size="sm" onClick={evaluateAlerts} disabled={evaluating} data-testid="evaluate-alerts-btn">
            <AlertTriangle className="w-4 h-4 mr-1" /> {evaluating ? "Taraniyor..." : "Alert Tara"}
          </Button>
        </div>
      </div>

      {/* Status Overview Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="status-overview">
        <MetricCard title="Event Bus" value={eb.mode === "redis" ? "Redis" : "In-Memory"} subtitle={<StatusIndicator status={eb.status || "healthy"} />} icon={Radio} variant={eb.status === "healthy" ? "success" : "warning"} />
        <MetricCard title="Database" value={db_status === "healthy" ? "Connected" : "Disconnected"} subtitle={<StatusIndicator status={db_status} />} icon={Database} variant={db_status === "healthy" ? "success" : "danger"} />
        <MetricCard title="Events (1h)" value={eventMetrics.events_last_hour || 0} subtitle={`${eventMetrics.published || 0} toplam, ${eventMetrics.dropped || 0} kayip`} icon={Activity} />
        <MetricCard title="Aktif Alertler" value={alerts.length} subtitle={alerts.length > 0 ? "Onay bekliyor" : "Temiz"} icon={AlertTriangle} variant={alerts.length > 0 ? "danger" : "success"} />
      </div>

      {/* Alert Candidates */}
      {alerts.length > 0 && <Card className="bg-red-950/20 border-red-900/40" data-testid="active-alerts">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-red-300">
              <AlertTriangle className="w-4 h-4" /> Aktif Alertler
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {alerts.map(alert => <div key={alert.id} className="flex items-center justify-between p-3 bg-zinc-900/60 rounded-lg border border-zinc-800">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant={alert.severity === "critical" ? "destructive" : "secondary"} className="text-xs">
                      {alert.severity}
                    </Badge>
                    <span className="text-sm font-medium text-zinc-200">{alert.title}</span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1">{alert.message}</p>
                  {alert.runbook_hint && <p className="text-xs text-blue-400 mt-1">Runbook: {alert.runbook_hint}</p>}
                </div>
                <Button size="sm" variant="ghost" onClick={() => acknowledgeAlert(alert.id)} data-testid={`ack-alert-${alert.id}`}>
                  <CheckCircle className="w-4 h-4" />
                </Button>
              </div>)}
          </CardContent>
        </Card>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Event Bus Details */}
        <Card className="bg-zinc-900/60 border-zinc-800" data-testid="event-bus-details">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-zinc-200">
              <Radio className="w-4 h-4" /> Event Bus Detay
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Mod</div>
                <div className="text-sm font-bold text-zinc-100">{eb.mode || "in_memory"}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Redis Konfigurasyonu</div>
                <div className="text-sm font-bold text-zinc-100">{eb.redis_configured ? "Aktif" : "Pasif"}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Yayinlanan</div>
                <div className="text-sm font-bold text-zinc-100">{eventMetrics.published || 0}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Iletilen</div>
                <div className="text-sm font-bold text-zinc-100">{eventMetrics.delivered || 0}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Messaging Provider Status */}
        <Card className="bg-zinc-900/60 border-zinc-800" data-testid="messaging-status">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-zinc-200">
              <Mail className="w-4 h-4" /> Messaging Providers
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {messaging?.providers?.length > 0 ? messaging.providers.slice(0, 5).map((p, i) => <div key={p.id || i} className="flex items-center justify-between p-2 bg-zinc-800/60 rounded-lg">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-zinc-300">{p.provider_type}</span>
                    <Badge variant="outline" className="text-xs">{p.mode || "live"}</Badge>
                  </div>
                  <StatusIndicator status={p.status || "unknown"} />
                </div>) : <p className="text-xs text-zinc-500">Provider konfigürasyonu bulunamadı</p>}
            {messaging?.retry_queue_size > 0 && <div className="mt-2 p-2 bg-amber-950/30 rounded-lg border border-amber-900/30">
                <div className="text-xs text-amber-400">Retry kuyrugunda: {messaging.retry_queue_size} mesaj</div>
              </div>}
          </CardContent>
        </Card>
      </div>

      {/* Persistence Health */}
      <Card className="bg-zinc-900/60 border-zinc-800" data-testid="persistence-health">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2 text-zinc-200">
            <Database className="w-4 h-4" /> Persistence Health
            <StatusIndicator status={persistence?.overall || "unknown"} />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
            {persistence?.collections && Object.entries(persistence.collections).map(([name, info]) => <div key={name} className="p-2 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400 truncate">{name.replace(/_/g, " ")}</div>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-xs font-bold text-zinc-200">{info.document_count?.toLocaleString()}</span>
                  {info.status === "healthy" ? <CheckCircle className="w-3 h-3 text-emerald-500" /> : <XCircle className="w-3 h-3 text-red-500" />}
                </div>
              </div>)}
          </div>
        </CardContent>
      </Card>

      {/* Observability Summary */}
      {observability && <Card className="bg-zinc-900/60 border-zinc-800" data-testid="observability-summary">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-zinc-200">
              <Activity className="w-4 h-4" /> Observability Ozeti
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">İstek (1h)</div>
                <div className="text-lg font-bold text-zinc-100">{observability.traces?.total_requests || 0}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Hata (1h)</div>
                <div className="text-lg font-bold text-red-400">{observability.errors?.total_errors || 0}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Event Throughput</div>
                <div className="text-lg font-bold text-zinc-100">{observability.metrics?.event_throughput || 0}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Genel Saglik</div>
                <StatusIndicator status={observability.health?.overall_status || "unknown"} />
              </div>
            </div>

            {/* Slow Endpoints */}
            {observability.traces?.endpoints?.filter(e => e.slow > 0).length > 0 && <div className="mt-4">
                <h4 className="text-xs text-zinc-400 uppercase tracking-wider mb-2">Yavas Endpoint'ler</h4>
                <div className="space-y-1">
                  {observability.traces.endpoints.filter(e => e.slow > 0).slice(0, 5).map((ep, i) => <div key={ep.id || i} className="flex items-center justify-between p-2 bg-amber-950/20 rounded border border-amber-900/20">
                      <span className="text-xs font-mono text-zinc-300">{ep.path}</span>
                      <div className="flex gap-3">
                        <span className="text-xs text-zinc-400">avg: {ep.avg_ms}ms</span>
                        <span className="text-xs text-amber-400">slow: {ep.slow}</span>
                      </div>
                    </div>)}
                </div>
              </div>}
          </CardContent>
        </Card>}

      {/* Alert Engine Status */}
      {alertEngine && <Card className="bg-zinc-900/60 border-zinc-800" data-testid="alert-engine-status">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-zinc-200">
              <Shield className="w-4 h-4" /> Alert Engine
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Cooldown (dk)</div>
                <div className="text-lg font-bold text-zinc-100">{alertEngine.cooldown_minutes}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Bastirilmis</div>
                <div className="text-lg font-bold text-zinc-100">{alertEngine.suppressed_by_cooldown}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Aktif Alert</div>
                <div className="text-lg font-bold text-zinc-100">{alertEngine.active_alerts}</div>
              </div>
            </div>
          </CardContent>
        </Card>}
    </div>;
}