import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

function StatusDot({ status }) {
  const color = status === "healthy" ? "bg-emerald-500" : status === "disconnected" ? "bg-red-500" : "bg-amber-500";
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} />;
}

export default function EventBusDashboard() {
  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [channels, setChannels] = useState([]);
  const [replaySummary, setReplaySummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, metricsRes, channelsRes, replayRes] = await Promise.all([
        axios.get(`${API}/api/event-bus/status`, { headers }),
        axios.get(`${API}/api/event-bus/metrics`, { headers }),
        axios.get(`${API}/api/event-bus/channels`, { headers }),
        axios.get(`${API}/api/event-bus/replay/summary`, { headers }),
      ]);
      setStatus(statusRes.data);
      setMetrics(metricsRes.data);
      setChannels(channelsRes.data);
      setReplaySummary(replayRes.data);
    } catch (err) {
      console.error("Event bus data fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const publishTest = async () => {
    try {
      await axios.post(`${API}/api/event-bus/publish?event_type=test_event&priority=normal`, {}, { headers });
      toast.success("Test event yayinlandi");
      fetchData();
    } catch { toast.error("Event yayin hatasi"); }
  };

  if (loading) return <div className="flex items-center justify-center h-96"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-500" /></div>;

  const backendDetails = status?.backend_details || {};
  const mode = status?.mode || "unknown";

  return (
    <div data-testid="event-bus-dashboard" className="space-y-6 p-6 bg-slate-950 min-h-screen">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Event Bus</h1>
          <p className="text-sm text-slate-400 mt-1">Production-grade event broadcasting</p>
        </div>
        <Button data-testid="publish-test-event" onClick={publishTest} size="sm" className="bg-violet-600 hover:bg-violet-700 text-white">
          Test Event Yayinla
        </Button>
      </div>

      {/* Mode & Health */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card data-testid="metric-mode" className="bg-slate-900/60 border-slate-700/50">
          <CardContent className="p-4">
            <p className="text-xs text-slate-400 uppercase tracking-wider">Aktif Mod</p>
            <div className="flex items-center gap-2 mt-2">
              <StatusDot status={backendDetails.status || "unknown"} />
              <p className="text-lg font-bold text-white capitalize">{mode.replace("_", " ")}</p>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="metric-published" className="bg-slate-900/60 border-slate-700/50">
          <CardContent className="p-4">
            <p className="text-xs text-slate-400 uppercase tracking-wider">Yayinlanan</p>
            <p className="text-2xl font-bold text-white mt-1">{metrics?.total_published || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="metric-delivered" className="bg-slate-900/60 border-slate-700/50">
          <CardContent className="p-4">
            <p className="text-xs text-slate-400 uppercase tracking-wider">Iletilen</p>
            <p className="text-2xl font-bold text-white mt-1">{metrics?.total_delivered || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="metric-errors" className="bg-slate-900/60 border-slate-700/50">
          <CardContent className="p-4">
            <p className="text-xs text-slate-400 uppercase tracking-wider">Hatalar</p>
            <p className="text-2xl font-bold text-red-400 mt-1">{metrics?.total_errors || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="metric-sessions" className="bg-slate-900/60 border-slate-700/50">
          <CardContent className="p-4">
            <p className="text-xs text-slate-400 uppercase tracking-wider">Aktif Sessions</p>
            <p className="text-2xl font-bold text-white mt-1">{metrics?.active_sessions || 0}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Backend Details */}
        <Card className="bg-slate-900/60 border-slate-700/50">
          <CardHeader><CardTitle className="text-white text-base">Backend Durumu</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(backendDetails).map(([key, val]) => (
                <div key={key} className="flex items-center justify-between py-1.5 border-b border-slate-800/50">
                  <span className="text-sm text-slate-400">{key.replace(/_/g, " ")}</span>
                  <span className="text-sm text-white font-medium">{String(val)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Top Event Types */}
        <Card className="bg-slate-900/60 border-slate-700/50">
          <CardHeader><CardTitle className="text-white text-base">Event Tipleri (Son 1 Saat)</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-slate-400 mb-3">Son saatte {metrics?.events_last_hour || 0} event</p>
            {Object.keys(metrics?.top_event_types || {}).length === 0 ? (
              <p className="text-slate-500 text-sm">Henuz event yok</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(metrics.top_event_types).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between">
                    <span className="text-sm text-slate-300">{type}</span>
                    <Badge variant="outline" className="text-violet-400 border-violet-500/30">{count}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Channels */}
        <Card className="bg-slate-900/60 border-slate-700/50">
          <CardHeader><CardTitle className="text-white text-base">Tenant Kanallari</CardTitle></CardHeader>
          <CardContent>
            {channels.length === 0 ? (
              <p className="text-slate-500 text-sm">Aktif kanal yok</p>
            ) : (
              <div className="space-y-2">
                {channels.map((ch, i) => (
                  <div key={i} data-testid={`channel-${i}`} className="p-2.5 rounded-lg bg-slate-800/50 border border-slate-700/40">
                    <p className="text-sm text-white font-medium">{ch.channel}</p>
                    <p className="text-xs text-slate-400">{ch.active_sessions} session | {ch.events_published} event</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Replay Summary */}
        <Card className="bg-slate-900/60 border-slate-700/50">
          <CardHeader><CardTitle className="text-white text-base">Replay Kuyrugu</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-slate-400 mb-3">24 saatte {replaySummary?.replayable_events_24h || 0} tekrar oynatilabilir event</p>
            {(replaySummary?.by_type || []).length === 0 ? (
              <p className="text-slate-500 text-sm">Replay verisi yok</p>
            ) : (
              <div className="space-y-2">
                {replaySummary.by_type.map((t, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-sm text-slate-300">{t.event_type}</span>
                    <span className="text-sm text-white">{t.count} (seq: {t.last_sequence})</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
