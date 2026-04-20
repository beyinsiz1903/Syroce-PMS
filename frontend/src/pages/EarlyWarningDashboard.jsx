import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Play,
  Square,
  RefreshCw,
  Zap,
  Gauge,
  TrendingUp,
  Clock,
} from "lucide-react";

const BASE = "/ops-events/early-warnings";

const healthStyles = {
  healthy: { color: "text-green-600", bg: "bg-green-50", label: "Sağlıklı", icon: CheckCircle2 },
  attention: { color: "text-yellow-600", bg: "bg-yellow-50", label: "Dikkat", icon: AlertTriangle },
  degraded: { color: "text-orange-600", bg: "bg-orange-50", label: "Bozulma", icon: AlertTriangle },
  critical: { color: "text-red-600", bg: "bg-red-50", label: "Kritik", icon: AlertTriangle },
};

const severityBadge = (s) => {
  const map = {
    critical: "bg-red-100 text-red-700 border-red-300",
    warning: "bg-orange-100 text-orange-700 border-orange-300",
    info: "bg-blue-100 text-blue-700 border-blue-300",
  };
  return map[s] || "bg-gray-100 text-gray-700 border-gray-300";
};

const confidenceColor = (c) => {
  if (c >= 80) return "bg-red-500 text-white";
  if (c >= 60) return "bg-orange-500 text-white";
  if (c >= 40) return "bg-yellow-500 text-white";
  return "bg-gray-400 text-white";
};

function Sparkline({ data = [], color = "#3b82f6", height = 40 }) {
  if (!data || data.length < 2) {
    return <div className="text-xs text-gray-400 italic">Veri yok</div>;
  }
  const values = data.map((d) => Number(d.value) || 0);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg width="100%" height={height} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="overflow-visible">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function KPICard({ icon: Icon, label, value, sub, tone = "blue" }) {
  const toneMap = {
    blue: "text-blue-600 bg-blue-50",
    red: "text-red-600 bg-red-50",
    orange: "text-orange-600 bg-orange-50",
    green: "text-green-600 bg-green-50",
    gray: "text-gray-600 bg-gray-50",
  };
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`p-3 rounded-lg ${toneMap[tone] || toneMap.blue}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
          <div className="text-2xl font-semibold">{value ?? "—"}</div>
          {sub && <div className="text-xs text-gray-500 truncate">{sub}</div>}
        </div>
      </CardContent>
    </Card>
  );
}

export default function EarlyWarningDashboard() {
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState(null);
  const [engineStatus, setEngineStatus] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [minConfidence, setMinConfidence] = useState(0);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, t, es, w, ev] = await Promise.all([
        axios.get(`${BASE}/summary`).catch(() => ({ data: null })),
        axios.get(`${BASE}/trends`).catch(() => ({ data: null })),
        axios.get(`${BASE}/engine/status`).catch(() => ({ data: null })),
        axios.get(`${BASE}?min_confidence=${minConfidence}`).catch(() => ({ data: { warnings: [] } })),
        axios.get(`${BASE}/recent-events`).catch(() => ({ data: null })),
      ]);
      setSummary(s.data);
      setTrends(t.data);
      setEngineStatus(es.data);
      setWarnings(w.data?.warnings || []);
      setEvents(ev.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Yükleme hatası");
    } finally {
      setLoading(false);
    }
  }, [minConfidence]);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 60000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const controlEngine = async (action) => {
    setBusy(true);
    try {
      await axios.post(`${BASE}/engine/${action}`);
      await fetchAll();
    } catch (e) {
      setError(e?.response?.data?.detail || `Motor ${action} başarısız`);
    } finally {
      setBusy(false);
    }
  };

  const forceCheck = async () => {
    setBusy(true);
    try {
      await axios.post(`${BASE}/force-check`);
      await fetchAll();
    } catch (e) {
      setError(e?.response?.data?.detail || "Kontrol başarısız");
    } finally {
      setBusy(false);
    }
  };

  const health = healthStyles[summary?.system_health_indicator] || healthStyles.healthy;
  const HealthIcon = health.icon;
  const running = !!engineStatus?.running;

  return (
    <Layout title="Erken Uyarı Motoru" subtitle="Tahminsel operasyonel sinyaller ve trend analizi">
      <div className="space-y-6 p-4">
        {error && (
          <div className="p-3 rounded bg-red-50 text-red-700 border border-red-200 text-sm">{error}</div>
        )}

        {/* Header: engine control */}
        <Card>
          <CardContent className="p-4 flex flex-wrap items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${health.bg}`}>
              <HealthIcon className={`w-4 h-4 ${health.color}`} />
              <span className={`text-sm font-medium ${health.color}`}>Sistem: {health.label}</span>
            </div>
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${running ? "bg-green-50" : "bg-gray-100"}`}>
              <div className={`w-2 h-2 rounded-full ${running ? "bg-green-500 animate-pulse" : "bg-gray-400"}`} />
              <span className="text-sm">
                Motor: <strong>{running ? "Çalışıyor" : "Durduruldu"}</strong>
              </span>
              {engineStatus?.check_interval_seconds && (
                <span className="text-xs text-gray-500">({engineStatus.check_interval_seconds}s)</span>
              )}
            </div>
            <div className="flex-1" />
            <Button size="sm" variant="outline" onClick={fetchAll} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Yenile
            </Button>
            {running ? (
              <Button size="sm" variant="outline" onClick={() => controlEngine("stop")} disabled={busy}>
                <Square className="w-4 h-4 mr-1" /> Durdur
              </Button>
            ) : (
              <Button size="sm" onClick={() => controlEngine("start")} disabled={busy}>
                <Play className="w-4 h-4 mr-1" /> Başlat
              </Button>
            )}
            <Button size="sm" variant="secondary" onClick={forceCheck} disabled={busy}>
              <Zap className="w-4 h-4 mr-1" /> Şimdi Tara
            </Button>
          </CardContent>
        </Card>

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            icon={AlertTriangle}
            label="Toplam Uyarı"
            value={summary?.warning_count ?? 0}
            tone="blue"
          />
          <KPICard
            icon={AlertTriangle}
            label="Kritik"
            value={summary?.critical_count ?? 0}
            tone="red"
          />
          <KPICard
            icon={Gauge}
            label="Uyarı (warning)"
            value={summary?.warning_count_warning ?? 0}
            tone="orange"
          />
          <KPICard
            icon={Activity}
            label="Risk Altında Konektör"
            value={summary?.connectors_at_risk_count ?? 0}
            sub={(summary?.connectors_at_risk || []).slice(0, 3).join(", ") || "—"}
            tone="gray"
          />
        </div>

        {/* Trends */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp className="w-4 h-4" /> Hata Oranı (son 6 saat)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Sparkline data={trends?.failure_rate_series || []} color="#ef4444" />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>{trends?.failure_rate_series?.[0]?.label || ""}</span>
                <span>{trends?.failure_rate_series?.slice(-1)?.[0]?.label || ""}</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp className="w-4 h-4" /> DLQ Büyümesi
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Sparkline data={trends?.dlq_series || []} color="#f97316" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp className="w-4 h-4" /> Backlog
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Sparkline data={trends?.backlog_series || []} color="#3b82f6" />
            </CardContent>
          </Card>
        </div>

        {/* Active warnings */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base">Aktif Uyarılar</CardTitle>
            <div className="flex items-center gap-2 text-xs">
              <span>Min güven:</span>
              <select
                className="border rounded px-2 py-1 text-xs"
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value))}
              >
                <option value={0}>Tümü</option>
                <option value={40}>≥ 40</option>
                <option value={60}>≥ 60</option>
                <option value={80}>≥ 80</option>
              </select>
            </div>
          </CardHeader>
          <CardContent>
            {warnings.length === 0 ? (
              <div className="text-sm text-gray-500 italic py-6 text-center">
                Bu eşikte aktif uyarı yok.
              </div>
            ) : (
              <div className="space-y-3">
                {warnings.map((w, i) => (
                  <div
                    key={`${w.warning_type}-${w.connector_id || i}`}
                    className="border rounded-lg p-3 flex items-start gap-3 hover:bg-gray-50"
                  >
                    <Badge className={`${confidenceColor(w.confidence)} font-mono`}>{w.confidence}</Badge>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <Badge variant="outline" className={severityBadge(w.severity)}>
                          {w.severity}
                        </Badge>
                        <span className="text-sm font-medium">
                          {w.warning_type?.replace("predictive.warning.", "")}
                        </span>
                        {w.provider && (
                          <Badge variant="outline" className="text-xs">
                            {w.provider}
                          </Badge>
                        )}
                        {w.connector_id && (
                          <span className="text-xs text-gray-500 font-mono">{w.connector_id}</span>
                        )}
                      </div>
                      <div className="text-sm text-gray-700">{w.reason}</div>
                      {w.recommended_action && (
                        <div className="text-xs text-gray-600 mt-1">
                          <strong>Öneri:</strong> {w.recommended_action}
                        </div>
                      )}
                      {w.impacted_scope && (
                        <div className="text-xs text-gray-500 mt-1">Etki: {w.impacted_scope}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent events */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="w-4 h-4" /> Son 24 Saat Olaylar ({events?.total ?? 0})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {events?.by_type && Object.keys(events.by_type).length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {Object.entries(events.by_type).map(([type, count]) => (
                  <Badge key={type} variant="outline" className="text-xs">
                    {type.replace("predictive.warning.", "")}: <strong className="ml-1">{count}</strong>
                  </Badge>
                ))}
              </div>
            )}
            {!events?.events?.length ? (
              <div className="text-sm text-gray-500 italic py-4 text-center">
                Son 24 saatte olay yok.
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {(events.events || []).map((ev, i) => (
                  <div key={ev._id || i} className="text-xs border-b pb-2 last:border-b-0">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">
                        {ev.event_type?.replace("predictive.warning.", "") || "event"}
                      </Badge>
                      <span className="text-gray-500">
                        {ev.created_at ? new Date(ev.created_at).toLocaleString("tr-TR") : ""}
                      </span>
                    </div>
                    {ev.message && <div className="text-gray-700 mt-1">{ev.message}</div>}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
