import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import {
  Activity, AlertTriangle, ArrowRight, CheckCircle2, Clock,
  Database, Eye, Gauge, Inbox, Loader2, PlugZap, RefreshCw,
  Server, Shield, ShieldAlert, Timer, Wifi, WifiOff, XCircle,
  Zap, TrendingUp, BarChart3, GitCompare, Radio, Play,
} from "lucide-react";

const TENANT_ID = "syroce_default";
const PROPERTY_ID = "default";

// Health status indicator component
function StatusDot({ status }) {
  const colors = {
    healthy: "bg-emerald-500 shadow-emerald-400/50",
    degraded: "bg-amber-500 shadow-amber-400/50",
    error: "bg-red-500 shadow-red-400/50",
    unknown: "bg-slate-400 shadow-slate-300/50",
  };
  return (
    <span
      data-testid={`status-dot-${status}`}
      className={`inline-block w-2.5 h-2.5 rounded-full shadow-md ${colors[status] || colors.unknown}`}
    />
  );
}

function StatusBadge({ status, label }) {
  const variants = {
    healthy: "bg-emerald-50 text-emerald-700 border-emerald-200",
    degraded: "bg-amber-50 text-amber-700 border-amber-200",
    error: "bg-red-50 text-red-700 border-red-200",
    unknown: "bg-slate-50 text-slate-600 border-slate-200",
    enabled: "bg-emerald-50 text-emerald-700 border-emerald-200",
    disabled: "bg-slate-50 text-slate-500 border-slate-200",
    on: "bg-[#C09D63]/10 text-[#C09D63] border-[#C09D63]/30",
    off: "bg-slate-50 text-slate-500 border-slate-200",
  };
  const dotStatusMap = {
    on: "healthy", enabled: "healthy", off: "unknown", disabled: "unknown",
    healthy: "healthy", degraded: "degraded", error: "error", unknown: "unknown",
  };
  return (
    <span
      data-testid={`status-badge-${label?.toLowerCase().replace(/\s/g, "-")}`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${variants[status] || variants.unknown}`}
    >
      <StatusDot status={dotStatusMap[status] || "unknown"} />
      {label}
    </span>
  );
}

function MetricCard({ icon: Icon, label, value, subtext, color = "text-slate-700" }) {
  return (
    <div data-testid={`metric-${label?.toLowerCase().replace(/\s/g, "-")}`} className="flex items-start gap-3 p-4 rounded-xl bg-slate-50/80 border border-slate-100">
      <div className="p-2 rounded-lg bg-white border border-slate-100 shadow-sm">
        <Icon className="w-4 h-4 text-slate-500" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-slate-500 font-medium tracking-wide uppercase">{label}</p>
        <p className={`text-lg font-semibold mt-0.5 ${color}`}>{value ?? "—"}</p>
        {subtext && <p className="text-xs text-slate-400 mt-0.5 truncate">{subtext}</p>}
      </div>
    </div>
  );
}

function EventRow({ event, index }) {
  const isSuccess = event.success;
  return (
    <div
      data-testid={`event-row-${index}`}
      className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-slate-50 transition-colors group"
    >
      <div className={`p-1 rounded-md ${isSuccess ? "bg-emerald-50" : "bg-red-50"}`}>
        {isSuccess ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> : <XCircle className="w-3.5 h-3.5 text-red-500" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700 truncate">{event.operation}</p>
        <p className="text-xs text-slate-400">{event.correlation_id}</p>
      </div>
      <div className="text-right shrink-0">
        <p className="text-xs text-slate-500">{event.duration_ms}ms</p>
        <p className="text-xs text-slate-400">{formatTime(event.recorded_at)}</p>
      </div>
    </div>
  );
}

function formatTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function formatDateTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export default function HRv2OpsDashboard({ tenant }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [triggeringRecon, setTriggeringRecon] = useState(false);

  const tenantId = tenant?.tenant_id || TENANT_ID;

  const fetchDashboard = useCallback(async (showToast = false) => {
    try {
      const res = await axios.get(`/channel/hotelrunner-v2/ops-dashboard`, {
        params: { tenant_id: tenantId, property_id: PROPERTY_ID },
      });
      setData(res.data);
      if (showToast) toast.success("Dashboard yenilendi");
    } catch (err) {
      console.error("Ops dashboard fetch error:", err);
      toast.error("Dashboard verisi alinamadi");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tenantId]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchDashboard(true);
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/test-connection`, null, {
        params: { tenant_id: tenantId, property_id: PROPERTY_ID },
      });
      if (res.data?.success) {
        toast.success("Baglanti testi basarili", { description: `Latency: ${res.data.total_latency_ms}ms` });
      } else {
        toast.error("Baglanti testi basarisiz");
      }
      // Refresh dashboard after test
      fetchDashboard();
    } catch (err) {
      toast.error("Baglanti testi hatasi", { description: err.message });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleReconcile = async () => {
    setTriggeringRecon(true);
    try {
      const res = await axios.post(`/channel/hotelrunner-v2/reconcile`, null, {
        params: { tenant_id: tenantId, property_id: PROPERTY_ID, since_hours: 24 },
      });
      if (res.data?.success) {
        toast.success("Reconciliation tamamlandi", {
          description: `${res.data.mismatch_count} drift tespit edildi`,
        });
      } else {
        toast.error("Reconciliation hatasi");
      }
      fetchDashboard();
    } catch (err) {
      toast.error("Reconciliation hatasi", { description: err.message });
    } finally {
      setTriggeringRecon(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]" data-testid="ops-dashboard-loading">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-[#C09D63]" />
          <p className="text-sm text-slate-500 font-medium">Ops Dashboard yukleniyor...</p>
        </div>
      </div>
    );
  }

  const ph = data?.provider_health || {};
  const sync = data?.sync_overview || {};
  const m24 = data?.metrics_24h || {};
  const dlq = data?.dlq || {};
  const flags = data?.feature_flags || {};
  const events = data?.recent_events || [];
  const drifts = data?.recent_drifts || [];
  const errTax = data?.error_taxonomy || {};

  return (
    <TooltipProvider>
      <div data-testid="ops-dashboard" className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
        {/* Header */}
        <div className="sticky top-0 z-20 bg-white/80 backdrop-blur-xl border-b border-slate-100">
          <div className="max-w-[1440px] mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-slate-900 text-white">
                <Radio className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900" style={{ fontFamily: "Manrope, sans-serif" }}>
                  HotelRunner v2 Ops Dashboard
                </h1>
                <p className="text-xs text-slate-500 mt-0.5">
                  Canli connector izleme &bull; Son guncelleme: {formatDateTime(data?.generated_at)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                data-testid="shadow-mode-badge"
                variant="outline"
                className={`text-xs font-semibold px-3 py-1 ${
                  ph.shadow_mode
                    ? "bg-[#C09D63]/10 text-[#C09D63] border-[#C09D63]/30"
                    : "bg-emerald-50 text-emerald-700 border-emerald-200"
                }`}
              >
                <Eye className="w-3 h-3 mr-1" />
                {ph.shadow_mode ? "Shadow Mode" : "Live Mode"}
              </Badge>
              <Button
                data-testid="refresh-dashboard-btn"
                variant="outline"
                size="sm"
                onClick={handleRefresh}
                disabled={refreshing}
                className="text-xs"
              >
                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${refreshing ? "animate-spin" : ""}`} />
                Yenile
              </Button>
            </div>
          </div>
        </div>

        <div className="max-w-[1440px] mx-auto px-6 py-6">
          {/* === BENTO GRID === */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-5">

            {/* ── Provider Health Panel ── */}
            <Card data-testid="provider-health-panel" className="md:col-span-8 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-slate-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Provider Sagligi
                    </CardTitle>
                  </div>
                  <Badge variant="outline" className="text-xs bg-slate-50">{ph.connector_version || "v2"}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Status Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Auth</p>
                    <StatusBadge status={ph.auth_status || "unknown"} label={ph.auth_status === "healthy" ? "Healthy" : ph.auth_status === "degraded" ? "Degraded" : ph.auth_status === "error" ? "Failed" : "Bilinmiyor"} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Reservations API</p>
                    <StatusBadge status={ph.reservations_api || "unknown"} label={ph.reservations_api === "healthy" ? "Healthy" : ph.reservations_api === "error" ? "Error" : "Bilinmiyor"} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Shadow Mode</p>
                    <StatusBadge status={ph.shadow_mode ? "on" : "off"} label={ph.shadow_mode ? "Aktif" : "Kapali"} />
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-xs text-slate-500 font-medium">Write Path</p>
                    <StatusBadge status={ph.write_path === "enabled" ? "enabled" : "disabled"} label={ph.write_path === "enabled" ? "Enabled" : "Disabled"} />
                  </div>
                </div>
                <Separator />
                {/* Key Metrics Row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <MetricCard icon={Clock} label="Son Pull" value={formatTime(sync.last_pull_timestamp)} subtext={formatDateTime(sync.last_pull_timestamp)} />
                  <MetricCard icon={Gauge} label="Ort. Latency" value={data?.avg_latency_ms ? `${data.avg_latency_ms}ms` : "—"} subtext="Son 24 saat" />
                  <MetricCard icon={Inbox} label="DLQ" value={dlq.count ?? 0} color={dlq.count > 0 ? "text-red-600" : "text-emerald-600"} subtext={dlq.count > 0 ? "Dikkat gerekiyor" : "Temiz"} />
                  <MetricCard icon={AlertTriangle} label="Retry Sayisi" value={data?.total_retry_count ?? 0} color={data?.total_retry_count > 0 ? "text-amber-600" : "text-emerald-600"} subtext="Son 24 saat" />
                </div>
              </CardContent>
            </Card>

            {/* ── Operational Actions ── */}
            <Card data-testid="operational-actions-panel" className="md:col-span-4 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-[#C09D63]" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Operasyonel Islemler
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  data-testid="test-connection-btn"
                  onClick={handleTestConnection}
                  disabled={testingConnection}
                  className="w-full justify-start bg-slate-900 hover:bg-slate-800 text-white text-sm h-10"
                >
                  {testingConnection ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlugZap className="w-4 h-4 mr-2" />}
                  Baglanti Testi
                </Button>
                <Button
                  data-testid="trigger-reconciliation-btn"
                  onClick={handleReconcile}
                  disabled={triggeringRecon}
                  variant="outline"
                  className="w-full justify-start text-sm h-10 border-slate-200 hover:bg-slate-50"
                >
                  {triggeringRecon ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <GitCompare className="w-4 h-4 mr-2" />}
                  Reconciliation Baslat
                </Button>
                <Button
                  data-testid="refresh-status-btn"
                  onClick={handleRefresh}
                  disabled={refreshing}
                  variant="outline"
                  className="w-full justify-start text-sm h-10 border-slate-200 hover:bg-slate-50"
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
                  Provider Durumu Yenile
                </Button>
                <Separator />
                {/* Feature Flags Summary */}
                <div className="space-y-2 pt-1">
                  <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Feature Flags</p>
                  <div className="space-y-1.5">
                    {Object.entries(flags).filter(([k]) => !["tenant_id", "updated_at", "provider"].includes(k)).map(([key, val]) => (
                      <div key={key} className="flex items-center justify-between text-xs">
                        <span className="text-slate-600">{key.replace(/_/g, " ")}</span>
                        <span className={`font-medium ${val ? "text-emerald-600" : "text-slate-400"}`}>
                          {val ? "ON" : "OFF"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── Sync Overview ── */}
            <Card data-testid="sync-overview-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-slate-500" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Senkronizasyon Durumu
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard
                    icon={Database}
                    label="Drift Sayisi"
                    value={sync.drift_count ?? 0}
                    color={sync.drift_count > 0 ? "text-amber-600" : "text-emerald-600"}
                    subtext="Toplam drift"
                  />
                  <MetricCard
                    icon={TrendingUp}
                    label="Islem Basari"
                    value={m24.overall_success_rate ? `%${m24.overall_success_rate}` : "—"}
                    color={m24.overall_success_rate >= 90 ? "text-emerald-600" : "text-amber-600"}
                    subtext={`${m24.total_operations ?? 0} islem (24s)`}
                  />
                  <MetricCard
                    icon={Timer}
                    label="Son Reconciliation"
                    value={formatTime(sync.last_reconciliation?.timestamp)}
                    subtext={sync.last_reconciliation?.mismatch_count != null ? `${sync.last_reconciliation.mismatch_count} mismatch` : "Henuz calismadi"}
                  />
                  <MetricCard
                    icon={BarChart3}
                    label="Toplam Islem"
                    value={m24.total_operations ?? 0}
                    subtext="Son 24 saat"
                  />
                </div>
              </CardContent>
            </Card>

            {/* ── Failure Visibility ── */}
            <Card data-testid="failure-visibility-panel" className="md:col-span-6 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-500" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Hata Gorunurlugu
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(errTax).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <Shield className="w-8 h-8 text-emerald-400 mb-2" />
                    <p className="text-sm font-medium text-emerald-700">Hata yok</p>
                    <p className="text-xs text-slate-400 mt-1">Son 24 saatte hata kaydedilmedi</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Hata Taksonomisi (24s)</p>
                    <div className="space-y-2">
                      {Object.entries(errTax).map(([category, count]) => (
                        <div key={category} className="flex items-center justify-between p-2.5 rounded-lg bg-red-50/50 border border-red-100">
                          <div className="flex items-center gap-2">
                            <XCircle className="w-3.5 h-3.5 text-red-500" />
                            <span className="text-sm text-red-700 font-medium">{category || "unknown"}</span>
                          </div>
                          <Badge variant="outline" className="text-xs text-red-600 border-red-200 bg-red-50">{count}</Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* DLQ Section */}
                {dlq.count > 0 && (
                  <div className="mt-4 space-y-2">
                    <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Dead Letter Queue ({dlq.count})</p>
                    {dlq.recent_entries?.slice(0, 3).map((entry, i) => (
                      <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-amber-50/50 border border-amber-100 text-xs">
                        <Inbox className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                        <span className="text-amber-700 truncate">{entry.operation}: {entry.correlation_id}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Recent Events ── */}
            <Card data-testid="recent-events-panel" className="md:col-span-7 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Play className="w-4 h-4 text-slate-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Son Olaylar
                    </CardTitle>
                  </div>
                  <Badge variant="outline" className="text-xs bg-slate-50">{events.length} kayit</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {events.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <Activity className="w-8 h-8 text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Henuz olay kaydedilmedi</p>
                  </div>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {events.map((ev, i) => (
                      <EventRow key={i} event={ev} index={i} />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Recent Drifts ── */}
            <Card data-testid="recent-drifts-panel" className="md:col-span-5 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GitCompare className="w-4 h-4 text-amber-500" />
                    <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                      Son Driftler
                    </CardTitle>
                  </div>
                  <Badge variant="outline" className="text-xs bg-slate-50">{data?.sync_overview?.drift_count ?? 0} toplam</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {drifts.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <CheckCircle2 className="w-8 h-8 text-emerald-400 mb-2" />
                    <p className="text-sm font-medium text-emerald-700">Drift yok</p>
                    <p className="text-xs text-slate-400 mt-1">PMS ve HotelRunner senkronize</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {drifts.slice(0, 8).map((d, i) => (
                      <div key={i} className="p-2.5 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-slate-700">{d.case_type}</span>
                          <Badge
                            variant="outline"
                            className={`text-[10px] ${
                              d.severity === "high" ? "text-red-600 border-red-200 bg-red-50" :
                              d.severity === "medium" ? "text-amber-600 border-amber-200 bg-amber-50" :
                              "text-slate-500 border-slate-200 bg-slate-50"
                            }`}
                          >
                            {d.severity}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-500 mt-1 truncate">{d.description}</p>
                        <p className="text-[10px] text-slate-400 mt-0.5">{d.external_reservation_id}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ── Operations Breakdown ── */}
            <Card data-testid="operations-breakdown-panel" className="md:col-span-12 border-slate-100 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-slate-500" />
                  <CardTitle className="text-base font-semibold text-slate-800" style={{ fontFamily: "Manrope, sans-serif" }}>
                    Islem Detaylari (24 Saat)
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(m24.operations || {}).length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <BarChart3 className="w-8 h-8 text-slate-300 mb-2" />
                    <p className="text-sm text-slate-500">Henuz islem verisi yok</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="operations-table">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-left py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Islem</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Toplam</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Basarili</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Basarisiz</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Basari %</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Ort. Latency</th>
                          <th className="text-right py-2.5 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Max Latency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(m24.operations || {}).map(([opName, opData]) => (
                          <tr key={opName} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                            <td className="py-2.5 px-3 font-medium text-slate-700">{opName}</td>
                            <td className="py-2.5 px-3 text-right text-slate-600">{opData.total}</td>
                            <td className="py-2.5 px-3 text-right text-emerald-600">{opData.success}</td>
                            <td className="py-2.5 px-3 text-right text-red-600">{opData.failed}</td>
                            <td className="py-2.5 px-3 text-right">
                              <span className={`font-medium ${opData.success_rate >= 90 ? "text-emerald-600" : opData.success_rate >= 50 ? "text-amber-600" : "text-red-600"}`}>
                                %{opData.success_rate}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-right text-slate-600">{opData.avg_latency_ms}ms</td>
                            <td className="py-2.5 px-3 text-right text-slate-500">{opData.max_latency_ms}ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
