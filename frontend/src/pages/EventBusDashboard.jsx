import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Radio, RefreshCw, Zap, ArrowDownToLine, AlertTriangle, Activity } from "lucide-react";
const API = "";
function StatusDot({
  status
}) {
  const color = status === "healthy" ? "bg-emerald-500" : status === "disconnected" ? "bg-red-500" : "bg-amber-500";
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color} animate-pulse`} />;
}
export default function EventBusDashboard() {
  const {
    t
  } = useTranslation();
  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [channels, setChannels] = useState([]);
  const [replaySummary, setReplaySummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = {
    Authorization: `Bearer ${token}`
  };
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, metricsRes, channelsRes, replayRes] = await Promise.all([axios.get(`/event-bus/status`, {
        headers
      }), axios.get(`/event-bus/metrics`, {
        headers
      }), axios.get(`/event-bus/channels`, {
        headers
      }), axios.get(`/event-bus/replay/summary`, {
        headers
      })]);
      setStatus(statusRes.data);
      setMetrics(metricsRes.data);
      setChannels(channelsRes.data);
      setReplaySummary(replayRes.data);
    } catch (err) {
      console.error("Event bus data fetch failed:", err);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);
  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 15000);
    return () => clearInterval(iv);
  }, [fetchData]);
  const publishTest = async () => {
    try {
      await axios.post(`/event-bus/publish?event_type=test_event&priority=normal`, {}, {
        headers
      });
      toast.success("Test event yayinlandi");
      fetchData();
    } catch {
      toast.error("Event yayın başarısız");
    }
  };
  if (loading) return <div className="flex justify-center p-12" data-testid="event-bus-loading"><RefreshCw className="w-8 h-8 animate-spin text-zinc-400" /></div>;
  const backendStatus = status?.backend_status || "unknown";
  const mode = status?.mode || "in_memory";
  const redisConfigured = status?.redis_configured || false;
  const fallbackAvailable = status?.fallback_available || false;
  return <div className="space-y-6 p-6 max-w-7xl mx-auto" data-testid="event-bus-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">{t("techDashboards.eventBus")}</h1>
          <p className="text-sm text-zinc-400 mt-1">Real-time event routing & Pub/Sub monitoring</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
          <Button size="sm" onClick={publishTest} data-testid="publish-test-btn">
            <Zap className="w-4 h-4 mr-1" /> Test Event
          </Button>
        </div>
      </div>

      {/* Mode & Status */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="event-bus-status-cards">
        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase tracking-wider">Backend Modu</div>
            <div className="flex items-center gap-2 mt-2">
              <Badge variant={mode === "redis" ? "default" : "secondary"} className="text-sm">
                {mode === "redis" ? "Redis" : "In-Memory"}
              </Badge>
              <StatusDot status={backendStatus} />
            </div>
            <div className="text-xs text-zinc-500 mt-1">
              Redis: {redisConfigured ? "Konfigüre" : "Pasif"} | Fallback: {fallbackAvailable ? "Hazir" : "Yok"}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase tracking-wider flex items-center gap-1"><Zap className="w-3 h-3" /> Yayinlanan</div>
            <div className="text-2xl font-bold text-zinc-100 mt-1">{metrics?.total_published || 0}</div>
            <div className="text-xs text-zinc-500">Son 1h: {metrics?.events_last_hour || 0}</div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase tracking-wider flex items-center gap-1"><ArrowDownToLine className="w-3 h-3" /> Iletilen</div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{metrics?.total_delivered || 0}</div>
            <div className="text-xs text-zinc-500">Hata: {metrics?.total_errors || 0}</div>
          </CardContent>
        </Card>

        <Card className={`border ${(metrics?.total_dropped || 0) > 0 ? "bg-red-950/30 border-red-900/40" : "bg-zinc-900/60 border-zinc-800"}`}>
          <CardContent className="p-4">
            <div className="text-xs text-zinc-400 uppercase tracking-wider flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Kayip/Fallback</div>
            <div className="text-2xl font-bold text-zinc-100 mt-1">{metrics?.total_dropped || 0}</div>
            <div className="text-xs text-zinc-500">Fallback: {metrics?.total_fallback_used || 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* Redis Delivery Metrics */}
      {metrics?.redis_delivery_metrics && <Card className="bg-zinc-900/60 border-zinc-800" data-testid="redis-delivery-metrics">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
              <Radio className="w-4 h-4" /> Redis Delivery Metrikleri
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Ortalama Latency</div>
                <div className="text-lg font-bold text-zinc-100">{metrics.redis_delivery_metrics.avg_publish_latency_ms}ms</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Channel Sayısı</div>
                <div className="text-lg font-bold text-zinc-100">{metrics.redis_delivery_metrics.channel_cardinality}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Errors</div>
                <div className="text-lg font-bold text-red-400">{metrics.redis_delivery_metrics.errors}</div>
              </div>
              <div className="p-3 bg-zinc-800/60 rounded-lg">
                <div className="text-xs text-zinc-400">Dropped</div>
                <div className="text-lg font-bold text-amber-400">{metrics.redis_delivery_metrics.dropped}</div>
              </div>
            </div>
          </CardContent>
        </Card>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Backend Details */}
        <Card className="bg-zinc-900/60 border-zinc-800" data-testid="backend-details">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200">Backend Detaylari</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {status?.backend_details && Object.entries(status.backend_details).map(([key, val]) => <div key={key} className="flex justify-between py-1 border-b border-zinc-800 last:border-0">
                <span className="text-xs text-zinc-400">{key}</span>
                <span className="text-xs font-mono text-zinc-200">{typeof val === "object" ? JSON.stringify(val) : String(val)}</span>
              </div>)}
          </CardContent>
        </Card>

        {/* Top Event Types */}
        <Card className="bg-zinc-900/60 border-zinc-800" data-testid="top-event-types">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
              <Activity className="w-4 h-4" /> En Cok Event Tipleri
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {metrics?.top_event_types && Object.entries(metrics.top_event_types).length > 0 ? Object.entries(metrics.top_event_types).map(([type, count]) => <div key={type} className="flex justify-between py-1 border-b border-zinc-800 last:border-0">
                  <span className="text-xs font-mono text-zinc-300">{type}</span>
                  <Badge variant="outline" className="text-xs">{count}</Badge>
                </div>) : <p className="text-xs text-zinc-500">Henüz event yayinlanmadi</p>}
          </CardContent>
        </Card>
      </div>

      {/* Replay Summary */}
      {replaySummary && <Card className="bg-zinc-900/60 border-zinc-800" data-testid="replay-summary">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200">Replay Ozeti (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-zinc-300 mb-3">
              Toplam tekrar oynatilabilir: <span className="font-bold">{replaySummary.replayable_events_24h || 0}</span>
            </div>
            {replaySummary.by_type?.length > 0 && <div className="space-y-1">
                {replaySummary.by_type.map((t, i) => <div key={t.id || i} className="flex justify-between py-1 border-b border-zinc-800 last:border-0">
                    <span className="text-xs font-mono text-zinc-300">{t.event_type}</span>
                    <span className="text-xs text-zinc-400">{t.count} event, seq: {t.last_sequence}</span>
                  </div>)}
              </div>}
          </CardContent>
        </Card>}

      {/* Channels */}
      {channels?.length > 0 && <Card className="bg-zinc-900/60 border-zinc-800" data-testid="channels-list">
          <CardHeader className="pb-3">
            <CardTitle className="text-base text-zinc-200">Aktif Channellar</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {channels.map((ch, i) => <div key={ch.id || i} className="flex items-center justify-between p-2 bg-zinc-800/60 rounded-lg">
                <span className="text-xs font-mono text-zinc-300">{ch.channel}</span>
                <div className="flex gap-3">
                  <span className="text-xs text-zinc-400">Sessions: {ch.active_sessions}</span>
                  <span className="text-xs text-zinc-400">Events: {ch.events_published}</span>
                </div>
              </div>)}
          </CardContent>
        </Card>}
    </div>;
}