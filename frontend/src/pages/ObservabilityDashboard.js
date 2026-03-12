import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

function HealthIcon({ status }) {
  if (status === "healthy") return <span className="inline-block w-3 h-3 rounded-full bg-emerald-500" />;
  if (status === "degraded") return <span className="inline-block w-3 h-3 rounded-full bg-amber-500" />;
  return <span className="inline-block w-3 h-3 rounded-full bg-red-500" />;
}

function MetricBar({ label, value, max, unit, color }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">{label}</span>
        <span className="text-xs text-white font-medium">{typeof value === "number" ? value.toFixed(2) : value} {unit}</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color || "bg-teal-500"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function ObservabilityDashboard() {
  const [health, setHealth] = useState(null);
  const [dashMetrics, setDashMetrics] = useState(null);
  const [errors, setErrors] = useState(null);
  const [traces, setTraces] = useState(null);
  const [loading, setLoading] = useState(true);

  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    try {
      const [healthRes, metricsRes, errorsRes, tracesRes] = await Promise.all([
        axios.get(`${API}/api/observability/health`, { headers }),
        axios.get(`${API}/api/observability/metrics`, { headers }),
        axios.get(`${API}/api/observability/errors/summary?hours=24`, { headers }),
        axios.get(`${API}/api/observability/traces/summary?hours=1`, { headers }),
      ]);
      setHealth(healthRes.data);
      setDashMetrics(metricsRes.data);
      setErrors(errorsRes.data);
      setTraces(tracesRes.data);
    } catch (err) {
      console.error("Observability data fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const flushMetrics = async () => {
    try {
      await axios.post(`${API}/api/observability/metrics/flush`, {}, { headers });
      toast.success("Metrikler kaydedildi");
    } catch { toast.error("Flush hatasi"); }
  };

  if (loading) return <div className="flex items-center justify-center h-96"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-teal-500" /></div>;

  const services = health?.services || {};
  const dm = dashMetrics || {};

  return (
    <div data-testid="observability-dashboard" className="space-y-6 p-6 bg-slate-950 min-h-screen">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Observability</h1>
          <p className="text-sm text-slate-400 mt-1">Platform performans ve saglik izleme</p>
        </div>
        <div className="flex gap-2">
          <Button data-testid="flush-metrics-btn" onClick={flushMetrics} size="sm" variant="outline" className="border-teal-500/50 text-teal-400 hover:bg-teal-600/20">
            Metrikleri Kaydet
          </Button>
          <Button data-testid="refresh-btn" onClick={fetchData} size="sm" className="bg-teal-600 hover:bg-teal-700 text-white">Yenile</Button>
        </div>
      </div>

      {/* Overall Health Banner */}
      <Card data-testid="health-banner" className={`border ${health?.overall_status === "healthy" ? "bg-emerald-900/20 border-emerald-700/30" : health?.overall_status === "degraded" ? "bg-amber-900/20 border-amber-700/30" : "bg-red-900/20 border-red-700/30"}`}>
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <HealthIcon status={health?.overall_status} />
            <span className="text-lg font-semibold text-white capitalize">{health?.overall_status || "unknown"}</span>
            <span className="text-sm text-slate-400">| {health?.healthy_count || 0} saglikli / {health?.service_count || 0} servis</span>
          </div>
          <span className="text-xs text-slate-500">{health?.checked_at ? new Date(health.checked_at).toLocaleString("tr-TR") : ""}</span>
        </CardContent>
      </Card>

      {/* Service Health Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {Object.entries(services).map(([name, svc]) => (
          <Card key={name} data-testid={`service-${name}`} className="bg-slate-900/60 border-slate-700/50">
            <CardContent className="p-3">
              <div className="flex items-center gap-2 mb-1">
                <HealthIcon status={svc.status} />
                <p className="text-xs font-medium text-white truncate">{name.replace(/_/g, " ")}</p>
              </div>
              {Object.entries(svc).filter(([k]) => k !== "status").map(([k, v]) => (
                <p key={k} className="text-xs text-slate-400">{k}: <span className="text-slate-300">{String(v)}</span></p>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="metrics" className="space-y-4">
        <TabsList className="bg-slate-800/80 border-slate-700">
          <TabsTrigger value="metrics" data-testid="tab-metrics" className="data-[state=active]:bg-teal-600">Metrikler</TabsTrigger>
          <TabsTrigger value="errors" data-testid="tab-errors" className="data-[state=active]:bg-teal-600">Hatalar</TabsTrigger>
          <TabsTrigger value="traces" data-testid="tab-traces" className="data-[state=active]:bg-teal-600">Traces</TabsTrigger>
        </TabsList>

        <TabsContent value="metrics">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card className="bg-slate-900/60 border-slate-700/50">
              <CardHeader><CardTitle className="text-white text-base">Performans Metrikleri</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <MetricBar label="WebSocket Latency (avg)" value={dm.websocket_latency?.avg || 0} max={1000} unit="ms" color="bg-violet-500" />
                <MetricBar label="ML Execution Time (avg)" value={dm.ml_execution_time?.avg || 0} max={60} unit="sec" color="bg-cyan-500" />
                <MetricBar label="Reservation Sync Lag (avg)" value={dm.reservation_sync_lag?.avg || 0} max={5000} unit="ms" color="bg-amber-500" />
                <MetricBar label="Event Throughput" value={dm.event_throughput || 0} max={10000} unit="events" color="bg-emerald-500" />
              </CardContent>
            </Card>
            <Card className="bg-slate-900/60 border-slate-700/50">
              <CardHeader><CardTitle className="text-white text-base">Is Metrikleri</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40">
                  <p className="text-xs text-slate-400">AutoPricing Basari Orani</p>
                  <p className="text-xl font-bold text-white">{((dm.autopricing?.success_rate || 0) * 100).toFixed(1)}%</p>
                  <p className="text-xs text-slate-500">{dm.autopricing?.success_count || 0} basarili / {dm.autopricing?.failure_count || 0} basarisiz</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40">
                  <p className="text-xs text-slate-400">Messaging Iletim Orani</p>
                  <p className="text-xl font-bold text-white">{((dm.messaging_delivery?.delivery_rate || 0) * 100).toFixed(1)}%</p>
                  <p className="text-xs text-slate-500">{dm.messaging_delivery?.success_count || 0} basarili / {dm.messaging_delivery?.failure_count || 0} basarisiz</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="errors">
          <Card className="bg-slate-900/60 border-slate-700/50">
            <CardHeader><CardTitle className="text-white text-base">Hata Ozeti (24 Saat)</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40 text-center">
                  <p className="text-xs text-slate-400">Toplam</p>
                  <p className="text-2xl font-bold text-white">{errors?.total_errors || 0}</p>
                </div>
                <div className="p-3 rounded-lg bg-red-900/20 border border-red-700/30 text-center">
                  <p className="text-xs text-red-400">Critical/High</p>
                  <p className="text-2xl font-bold text-red-400">{(errors?.by_severity?.critical || 0) + (errors?.by_severity?.high || 0)}</p>
                </div>
                <div className="p-3 rounded-lg bg-amber-900/20 border border-amber-700/30 text-center">
                  <p className="text-xs text-amber-400">Medium/Low</p>
                  <p className="text-2xl font-bold text-amber-400">{(errors?.by_severity?.medium || 0) + (errors?.by_severity?.low || 0)}</p>
                </div>
              </div>
              {(errors?.top_errors || []).length > 0 && (
                <div className="space-y-2">
                  {errors.top_errors.slice(0, 8).map((e, i) => (
                    <div key={i} data-testid={`error-${i}`} className="flex items-center justify-between p-2 rounded bg-slate-800/50">
                      <div>
                        <span className="text-sm text-white">{e.error_type}</span>
                        <span className="text-xs text-slate-500 ml-2">{e.module}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className={e.severity === "critical" ? "text-red-400 border-red-500/30" : "text-amber-400 border-amber-500/30"}>{e.severity}</Badge>
                        <span className="text-xs text-slate-400">x{e.count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="traces">
          <Card className="bg-slate-900/60 border-slate-700/50">
            <CardHeader><CardTitle className="text-white text-base">Request Traces (Son 1 Saat)</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40 text-center">
                  <p className="text-xs text-slate-400">Requests</p>
                  <p className="text-2xl font-bold text-white">{traces?.total_requests || 0}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40 text-center">
                  <p className="text-xs text-slate-400">Errors</p>
                  <p className="text-2xl font-bold text-red-400">{traces?.total_errors || 0}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40 text-center">
                  <p className="text-xs text-slate-400">Error Rate</p>
                  <p className="text-2xl font-bold text-white">{((traces?.error_rate || 0) * 100).toFixed(2)}%</p>
                </div>
              </div>
              {(traces?.endpoints || []).length > 0 && (
                <div className="space-y-2">
                  {traces.endpoints.slice(0, 10).map((ep, i) => (
                    <div key={i} data-testid={`trace-${i}`} className="flex items-center justify-between p-2 rounded bg-slate-800/50">
                      <span className="text-sm text-slate-300 truncate max-w-[200px]">{ep.path}</span>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-slate-400">{ep.avg_ms?.toFixed(0)}ms avg</span>
                        <span className="text-xs text-slate-500">x{ep.count}</span>
                        {ep.slow > 0 && <Badge variant="outline" className="text-amber-400 border-amber-500/30">{ep.slow} slow</Badge>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
