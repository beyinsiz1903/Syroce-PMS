import React, { useEffect, useState, useCallback, useRef } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
  Radar,
} from "lucide-react";

const BASE = "/ops-events/early-warnings";

// system_health_indicator → Sprint A intent
const HEALTH_INTENT = {
  healthy: "success",
  attention: "info",
  degraded: "warning",
  critical: "danger",
  unknown: "neutral",
};
const HEALTH_LABEL = {
  healthy: "Sağlıklı",
  attention: "Dikkat",
  degraded: "Bozulma",
  critical: "Kritik",
  unknown: "Bilinmiyor",
};

// severity → Sprint A intent
const SEVERITY_INTENT = {
  critical: "danger",
  warning: "warning",
  info: "info",
};

// confidence (0-100) → palette tone
const confidenceClass = (c) => {
  if (c >= 80) return "bg-rose-600 text-white";
  if (c >= 60) return "bg-amber-500 text-white";
  if (c >= 40) return "bg-amber-400 text-white";
  return "bg-slate-400 text-white";
};

function Sparkline({ data = [], color = "#6366f1", height = 40 }) {
  if (!data || data.length < 2) {
    return <div className="text-xs text-slate-400 italic">Veri yok</div>;
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
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      className="overflow-visible"
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export default function EarlyWarningDashboard({ user, tenant, onLogout }) {
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState(null);
  const [engineStatus, setEngineStatus] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [minConfidence, setMinConfidence] = useState("0");

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const conf = Number(minConfidence) || 0;
      const [s, t, es, w, ev] = await Promise.all([
        axios.get(`${BASE}/summary`).catch(() => ({ data: null })),
        axios.get(`${BASE}/trends`).catch(() => ({ data: null })),
        axios.get(`${BASE}/engine/status`).catch(() => ({ data: null })),
        axios.get(`${BASE}`, { params: { min_confidence: conf } }).catch(() => ({ data: { warnings: [] } })),
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

  // Polling: yalnızca sekme görünürken (90s); arka planda CPU yakmasın
  const intervalRef = useRef(null);
  useEffect(() => {
    fetchAll();
    const setup = () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        intervalRef.current = setInterval(fetchAll, 90000);
      }
    };
    setup();
    const onVis = () => {
      setup();
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        fetchAll();
      }
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVis);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVis);
      }
    };
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

  const healthKey = summary?.system_health_indicator || "healthy";
  const healthIntent = HEALTH_INTENT[healthKey] || "neutral";
  const healthLabel = HEALTH_LABEL[healthKey] || healthKey;
  const running = !!engineStatus?.running;

  return (
    <div className="space-y-4 p-4 md:p-6 max-w-7xl mx-auto">
      <PageHeader
        icon={Radar}
        title="Erken Uyarı Motoru"
        subtitle="Tahmini uyarılar, trend analizi ve motor kontrolü"
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={fetchAll} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
              Yenile
            </Button>
            {running ? (
              <Button size="sm" variant="outline" onClick={() => controlEngine("stop")} disabled={busy}>
                <Square className="w-4 h-4 mr-1.5" aria-hidden="true" /> Durdur
              </Button>
            ) : (
              <Button size="sm" onClick={() => controlEngine("start")} disabled={busy}>
                <Play className="w-4 h-4 mr-1.5" aria-hidden="true" /> Başlat
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={forceCheck} disabled={busy}>
              <Zap className="w-4 h-4 mr-1.5" aria-hidden="true" /> Şimdi Tara
            </Button>
          </div>
        }
      />

      {error && (
        <div className="p-3 rounded bg-rose-50 text-rose-700 border border-rose-200 text-sm">
          {error}
        </div>
      )}

      {/* Sağlık şeridi */}
      <Card>
        <CardContent className="p-3 flex flex-wrap gap-3 items-center text-sm">
          <div className="flex items-center gap-2">
            <span className="font-medium">Sistem:</span>
            <StatusBadge intent={healthIntent} icon={healthIntent === "success" ? CheckCircle2 : AlertTriangle}>
              {healthLabel}
            </StatusBadge>
          </div>
          <div className="h-4 w-px bg-slate-200" aria-hidden="true" />
          <div className="flex items-center gap-2">
            <span className="font-medium">Motor:</span>
            <StatusBadge intent={running ? "success" : "neutral"}>
              {running ? "Çalışıyor" : "Durduruldu"}
            </StatusBadge>
            {engineStatus?.check_interval_seconds && (
              <span className="text-xs text-slate-500">
                ({engineStatus.check_interval_seconds}s aralık)
              </span>
            )}
          </div>
          <div className="h-4 w-px bg-slate-200" aria-hidden="true" />
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Clock className="w-3.5 h-3.5" aria-hidden="true" />
            Otomatik yenileme: 90sn (sekme aktifken)
          </div>
        </CardContent>
      </Card>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          icon={AlertTriangle}
          label="Toplam Uyarı"
          value={summary?.warning_count ?? 0}
          intent="info"
        />
        <KpiCard
          icon={AlertTriangle}
          label="Kritik"
          value={summary?.critical_count ?? 0}
          intent="danger"
          highlight={(summary?.critical_count ?? 0) > 0}
        />
        <KpiCard
          icon={Gauge}
          label="Uyarı (warning)"
          value={summary?.warning_count_warning ?? 0}
          intent="warning"
        />
        <KpiCard
          icon={Activity}
          label="Risk Altında Konektör"
          value={summary?.connectors_at_risk_count ?? 0}
          sub={(summary?.connectors_at_risk || []).slice(0, 3).join(", ") || "—"}
          intent="neutral"
        />
      </div>

      {/* Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-rose-600" aria-hidden="true" /> Hata Oranı (son 6 saat)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Sparkline data={trends?.failure_rate_series || []} color="#e11d48" />
            <div className="flex justify-between text-xs text-slate-500 mt-1">
              <span>{trends?.failure_rate_series?.[0]?.label || ""}</span>
              <span>{trends?.failure_rate_series?.slice(-1)?.[0]?.label || ""}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-amber-600" aria-hidden="true" /> DLQ Bekleyen
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trends?.dlq_current != null ? (
              <div className="space-y-1">
                <div className="text-2xl font-bold text-slate-800">{trends.dlq_current}</div>
                <div className="text-xs text-slate-500">
                  Son 30dk yeni: <strong>{trends.dlq_recent_additions ?? 0}</strong>
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-400 italic">Veri yok</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-indigo-600" aria-hidden="true" /> Backlog
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trends?.backlog_current != null ? (
              <div className="space-y-1">
                <div className="text-2xl font-bold text-slate-800">{trends.backlog_current}</div>
                <div className="text-xs text-slate-500">retry kuyruğunda</div>
              </div>
            ) : (
              <div className="text-xs text-slate-400 italic">Veri yok</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Active warnings */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
          <CardTitle className="text-base">Aktif Uyarılar</CardTitle>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-600">Min güven:</span>
            <Select value={minConfidence} onValueChange={setMinConfidence}>
              <SelectTrigger className="h-8 w-28 text-xs" aria-label="Min güven filtresi">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">Tümü</SelectItem>
                <SelectItem value="40">≥ 40</SelectItem>
                <SelectItem value="60">≥ 60</SelectItem>
                <SelectItem value="80">≥ 80</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {warnings.length === 0 ? (
            <div className="text-sm text-slate-500 italic py-6 text-center">
              <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500" aria-hidden="true" />
              Bu eşikte aktif uyarı yok.
            </div>
          ) : (
            <div className="space-y-3">
              {warnings.map((w, i) => (
                <div
                  key={`${w.warning_type}-${w.connector_id || i}`}
                  className="border rounded-lg p-3 flex items-start gap-3 hover:bg-slate-50"
                >
                  <Badge className={`${confidenceClass(w.confidence)} font-mono`}>{w.confidence}</Badge>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <StatusBadge intent={SEVERITY_INTENT[w.severity] || "neutral"}>
                        {w.severity}
                      </StatusBadge>
                      <span className="text-sm font-medium">
                        {w.warning_type?.replace("predictive.warning.", "")}
                      </span>
                      {w.provider && (
                        <Badge variant="outline" className="text-xs">
                          {w.provider}
                        </Badge>
                      )}
                      {w.connector_id && (
                        <span className="text-xs text-slate-500 font-mono">{w.connector_id}</span>
                      )}
                    </div>
                    <div className="text-sm text-slate-700">{w.reason}</div>
                    {w.recommended_action && (
                      <div className="text-xs text-slate-600 mt-1">
                        <strong>Öneri:</strong> {w.recommended_action}
                      </div>
                    )}
                    {w.impacted_scope && (
                      <div className="text-xs text-slate-500 mt-1">Etki: {w.impacted_scope}</div>
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
            <Clock className="w-4 h-4 text-slate-600" aria-hidden="true" /> Son 24 Saat Olaylar ({events?.total ?? 0})
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
            <div className="text-sm text-slate-500 italic py-4 text-center">
              Son 24 saatte olay yok.
            </div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {(events.events || []).map((ev, i) => (
                <div key={ev._id || ev.id || i} className="text-xs border-b pb-2 last:border-b-0">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {ev.event_type?.replace("predictive.warning.", "") || "event"}
                    </Badge>
                    <span className="text-slate-500">
                      {ev.created_at ? new Date(ev.created_at).toLocaleString("tr-TR") : ""}
                    </span>
                  </div>
                  {ev.message && <div className="text-slate-700 mt-1">{ev.message}</div>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
