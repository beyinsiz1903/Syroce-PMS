import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Activity, RefreshCw, AlertCircle, Clock, Gauge, BarChart3 } from "lucide-react";

const API = "";

function HealthDot({ status }) {
  const color = status === "healthy" ? "bg-emerald-500" : status === "degraded" ? "bg-amber-500" : "bg-red-500";
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
}

export default function ObservabilityDashboard() {
  const { t } = useTranslation();
  const [dashMetrics, setDashMetrics] = useState(null);
  const [traces, setTraces] = useState(null);
  const [errorSummary, setErrorSummary] = useState(null);
  const [health, setHealth] = useState(null);
  const [recentTraces, setRecentTraces] = useState([]);
  const [loading, setLoading] = useState(true);

  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    try {
      const [metricsRes, traceRes, errorRes, healthRes, recentRes] = await Promise.all([
        axios.get(`/observability/metrics`, { headers }),
        axios.get(`/observability/traces/summary?hours=1`, { headers }),
        axios.get(`/observability/errors/summary?hours=24`, { headers }),
        axios.get(`/observability/health`, { headers }),
        axios.get(`/observability/traces?limit=20&slow_only=false`, { headers }),
      ]);
      setDashMetrics(metricsRes.data);
      setTraces(traceRes.data);
      setErrorSummary(errorRes.data);
      setHealth(healthRes.data);
      setRecentTraces(Array.isArray(recentRes.data) ? recentRes.data : []);
    } catch (err) {
      console.error("Observability data fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); const iv = setInterval(fetchData, 20000); return () => clearInterval(iv); }, [fetchData]);

  const flushMetrics = async () => {
    try {
      await axios.post(`/observability/metrics/flush`, {}, { headers });
      toast.success("Metrikler flush edildi");
    } catch { toast.error("Flush başarısız"); }
  };

  const flushTraces = async () => {
    try {
      await axios.post(`/observability/traces/flush`, {}, { headers });
      toast.success("Trace'ler flush edildi");
      fetchData();
    } catch { toast.error("Flush başarısız"); }
  };

  if (loading) return <div className="flex justify-center p-12" data-testid="obs-loading"><RefreshCw className="w-8 h-8 animate-spin text-zinc-400" /></div>;

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto" data-testid="observability-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">{t("techDashboards.observability")}</h1>
          <p className="text-sm text-zinc-400 mt-1">Request tracing, metrics, errors & service health</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
          <Button variant="outline" size="sm" onClick={flushTraces} data-testid="flush-traces-btn">Trace Flush</Button>
          <Button variant="outline" size="sm" onClick={flushMetrics} data-testid="flush-metrics-btn">Metric Flush</Button>
        </div>
      </div>

      {/* Service Health */}
      {health && (
        <Card className={`border ${health.overall_status === "healthy" ? "bg-emerald-950/20 border-emerald-900/30" : health.overall_status === "degraded" ? "bg-amber-950/20 border-amber-900/30" : "bg-red-950/20 border-red-900/30"}`} data-testid="service-health">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-zinc-200">
              <Activity className="w-4 h-4" /> Servis Sagligi
              <Badge variant={health.overall_status === "healthy" ? "default" : "destructive"}>{health.overall_status}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
              {health.services && Object.entries(health.services).map(([name, info]) => (
                <div key={name} className="p-3 bg-zinc-800/60 rounded-lg">
                  <div className="flex items-center gap-1.5 mb-1">
                    <HealthDot status={info.status} />
                    <span className="text-xs font-medium text-zinc-300 capitalize">{name.replace(/_/g, " ")}</span>
                  </div>
                  {info.latency_ms != null && <span className="text-xs text-zinc-500">{info.latency_ms}ms</span>}
                  {info.mode && <span className="text-xs text-zinc-500 block">{info.mode}</span>}
                  {info.failures_1h != null && <span className="text-xs text-zinc-500 block">fail: {info.failures_1h}</span>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Metrics Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="metrics-overview">
        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase flex items-center gap-1"><Gauge className="w-3 h-3" /> İstek (1h)</div>
            <div className="text-2xl font-bold text-zinc-100 mt-1">{traces?.total_requests || 0}</div>
            <div className="text-xs text-zinc-500">Aktif trace: {traces?.active_traces || 0}</div>
          </CardContent>
        </Card>
        <Card className={`border ${(traces?.error_rate || 0) > 0.05 ? "bg-red-950/30 border-red-900/40" : "bg-zinc-900/60 border-zinc-800"}`}>
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase flex items-center gap-1"><AlertCircle className="w-3 h-3" /> Hata Orani</div>
            <div className="text-2xl font-bold text-zinc-100 mt-1">{((traces?.error_rate || 0) * 100).toFixed(2)}%</div>
            <div className="text-xs text-zinc-500">Toplam hata: {traces?.total_errors || 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase flex items-center gap-1"><BarChart3 className="w-3 h-3" /> Event Throughput</div>
            <div className="text-2xl font-bold text-zinc-100 mt-1">{dashMetrics?.event_throughput || 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase flex items-center gap-1"><Clock className="w-3 h-3" /> Messaging DR</div>
            <div className="text-2xl font-bold text-zinc-100 mt-1">{((dashMetrics?.messaging_delivery?.delivery_rate || 0) * 100).toFixed(1)}%</div>
            <div className="text-xs text-zinc-500">
              S: {dashMetrics?.messaging_delivery?.success_count || 0} / F: {dashMetrics?.messaging_delivery?.failure_count || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Endpoint Performance (from real traces) */}
        <Card className="bg-zinc-900/60 border-zinc-800" data-testid="endpoint-performance">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
              <Clock className="w-4 h-4" /> Endpoint Performansi (1h)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 max-h-80 overflow-y-auto">
            {traces?.endpoints?.length > 0 ? (
              traces.endpoints.map((ep, i) => (
                <div key={i} className="flex items-center justify-between py-1.5 border-b border-zinc-800 last:border-0">
                  <span className="text-xs font-mono text-zinc-300 truncate flex-1">{ep.path}</span>
                  <div className="flex gap-3 ml-2 shrink-0">
                    <span className="text-xs text-zinc-400">{ep.count}x</span>
                    <span className={`text-xs ${ep.avg_ms > 1000 ? "text-red-400" : "text-zinc-400"}`}>{ep.avg_ms}ms</span>
                    {ep.slow > 0 && <Badge variant="destructive" className="text-xs">{ep.slow} slow</Badge>}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-zinc-500">Henüz trace verisi yok. Flush yaparak veri toplayin.</p>
            )}
          </CardContent>
        </Card>

        {/* Error Summary */}
        <Card className="bg-zinc-900/60 border-zinc-800" data-testid="error-summary">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" /> Hata Ozeti (24h)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="p-2 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Toplam</div>
                <div className="text-lg font-bold text-zinc-100">{errorSummary?.total_errors || 0}</div>
              </div>
              <div className="p-2 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Ciddiyet</div>
                <div className="flex gap-1 mt-1 flex-wrap">
                  {errorSummary?.by_severity && Object.entries(errorSummary.by_severity).map(([sev, cnt]) => (
                    <Badge key={sev} variant={sev === "critical" ? "destructive" : "secondary"} className="text-xs">
                      {sev}: {cnt}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
            {errorSummary?.top_errors?.length > 0 && (
              <div className="space-y-1">
                {errorSummary.top_errors.slice(0, 8).map((e, i) => (
                  <div key={i} className="flex justify-between py-1 border-b border-zinc-800 last:border-0">
                    <span className="text-xs text-zinc-300">{e.error_type}</span>
                    <div className="flex gap-2">
                      <Badge variant={e.severity === "critical" ? "destructive" : "outline"} className="text-xs">{e.severity}</Badge>
                      <span className="text-xs text-zinc-400">{e.count}x</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Traces */}
      <Card className="bg-zinc-900/60 border-zinc-800" data-testid="recent-traces">
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-zinc-200">Son Trace'ler</CardTitle>
        </CardHeader>
        <CardContent>
          {recentTraces.length > 0 ? (
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {recentTraces.map((t, i) => (
                <div key={i} className={`flex items-center justify-between py-1.5 border-b border-zinc-800 last:border-0 ${t.is_slow ? "bg-amber-950/10" : ""}`}>
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Badge variant="outline" className="text-xs shrink-0">{t.method}</Badge>
                    <span className="text-xs font-mono text-zinc-300 truncate">{t.request_path}</span>
                  </div>
                  <div className="flex gap-2 ml-2 shrink-0 items-center">
                    <Badge variant={t.status_code >= 400 ? "destructive" : "secondary"} className="text-xs">{t.status_code}</Badge>
                    <span className={`text-xs ${t.duration_ms > 1000 ? "text-red-400 font-bold" : "text-zinc-400"}`}>{t.duration_ms}ms</span>
                    {t.is_slow && <Badge variant="destructive" className="text-xs">SLOW</Badge>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-zinc-500">Henüz trace verisi yok. Trace flush yaparak veritabanina kaydedin.</p>
          )}
        </CardContent>
      </Card>

      {/* Application Metrics */}
      {dashMetrics && (
        <Card className="bg-zinc-900/60 border-zinc-800" data-testid="app-metrics">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200">Uygulama Metrikleri</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">WS Latency (avg)</div>
                <div className="text-lg font-bold text-zinc-100">{dashMetrics.websocket_latency?.avg || 0}ms</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">ML Exec (avg)</div>
                <div className="text-lg font-bold text-zinc-100">{dashMetrics.ml_execution_time?.avg || 0}s</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Autopricing SR</div>
                <div className="text-lg font-bold text-zinc-100">{((dashMetrics.autopricing?.success_rate || 0) * 100).toFixed(1)}%</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Sync Lag (avg)</div>
                <div className="text-lg font-bold text-zinc-100">{dashMetrics.reservation_sync_lag?.avg || 0}ms</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
