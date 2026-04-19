import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Activity, Wifi, WifiOff, Send, Mail, MessageSquare,
  DollarSign, TrendingUp, TrendingDown, AlertTriangle, CheckCircle,
  XCircle, RotateCcw, Shield, Clock, Users, BedDouble, Zap,
  ArrowUpDown, Globe, RefreshCw, ChevronRight
} from "lucide-react";

const API = "";

function useAuthHeaders() {
  const token = localStorage.getItem("token");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

async function apiFetch(path, opts = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...opts.headers },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ── Small Components ──

function StatCard({ title, value, icon: Icon, color = "text-blue-400", sub }) {
  return (
    <Card className="bg-slate-800/60 border-slate-700">
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-slate-700/50 ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-xs text-slate-400">{title}</p>
          <p className="text-lg font-bold text-white">{value}</p>
          {sub && <p className="text-xs text-slate-500">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function PriorityBadge({ level }) {
  const colors = {
    critical: "bg-red-500/20 text-red-400 border-red-500/30",
    high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    urgent: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    low: "bg-slate-500/20 text-slate-400 border-slate-500/30",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${colors[level] || colors.low}`}>
      {level}
    </span>
  );
}

function StatusBadge({ status }) {
  const colors = {
    pending: "bg-yellow-500/20 text-yellow-400",
    applied: "bg-green-500/20 text-green-400",
    approved: "bg-green-500/20 text-green-400",
    rejected: "bg-red-500/20 text-red-400",
    rolled_back: "bg-purple-500/20 text-purple-400",
    delivered: "bg-green-500/20 text-green-400",
    failed: "bg-red-500/20 text-red-400",
    mock: "bg-blue-500/20 text-blue-400",
    active: "bg-green-500/20 text-green-400",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${colors[status] || "bg-slate-500/20 text-slate-400"}`}>
      {status}
    </span>
  );
}

// ── WebSocket Live Panel ──

function LiveOperationsPanel({ data, wsConnected, onRefresh }) {
  if (!data) return <p className="text-slate-400 text-sm p-4">Veri yükleniyor...</p>;
  const { front_desk_queue, housekeeping_board, vip_arrivals, audit_exceptions, occupancy, overbooking_risk } = data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {wsConnected ? (
            <Badge className="bg-green-500/20 text-green-400 border-green-500/30 text-xs gap-1">
              <Wifi className="h-3 w-3" /> CANLI
            </Badge>
          ) : (
            <Badge className="bg-red-500/20 text-red-400 border-red-500/30 text-xs gap-1">
              <WifiOff className="h-3 w-3" /> BAGLANTI YOK
            </Badge>
          )}
          {overbooking_risk && (
            <Badge data-testid="overbooking-alert" className="bg-red-500/20 text-red-400 border-red-500/30 text-xs gap-1 animate-pulse">
              <AlertTriangle className="h-3 w-3" /> OVERBOOKING RISKI
            </Badge>
          )}
        </div>
        <Button size="sm" variant="ghost" onClick={onRefresh} className="text-slate-400 hover:text-white">
          <RefreshCw className="h-4 w-4 mr-1" /> Yenile
        </Button>
      </div>

      {/* Occupancy Bar */}
      <Card className="bg-slate-800/60 border-slate-700">
        <CardContent className="p-4">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-slate-400">Doluluk</span>
            <span className="text-white font-bold">%{occupancy?.pct || 0}</span>
          </div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                (occupancy?.pct || 0) > 90 ? "bg-red-500" : (occupancy?.pct || 0) > 70 ? "bg-yellow-500" : "bg-emerald-500"
              }`}
              style={{ width: `${Math.min(occupancy?.pct || 0, 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-500 mt-1">
            <span>{occupancy?.booked || 0} dolu</span>
            <span>{occupancy?.available || 0} bos</span>
            <span>{occupancy?.total_rooms || 0} toplam</span>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Front Desk Queue */}
        <Card className="bg-slate-800/60 border-slate-700" data-testid="frontdesk-queue">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-400" /> Front Desk Kuyrugu ({front_desk_queue?.count || 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 max-h-48 overflow-y-auto space-y-1">
            {(front_desk_queue?.items || []).slice(0, 8).map((item, i) => (
              <div key={i} className="flex justify-between items-center text-xs p-2 rounded bg-slate-700/40">
                <span className="text-white">{item.guest_name || "Misafir"}</span>
                <span className="text-slate-400">{item.room_type || ""}</span>
              </div>
            ))}
            {(front_desk_queue?.count || 0) === 0 && <p className="text-xs text-slate-500">Kuyruk bos</p>}
          </CardContent>
        </Card>

        {/* Housekeeping Board */}
        <Card className="bg-slate-800/60 border-slate-700" data-testid="hk-board">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
              <BedDouble className="h-4 w-4 text-emerald-400" /> HK Gorev Panosu ({housekeeping_board?.count || 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 max-h-48 overflow-y-auto space-y-1">
            {(housekeeping_board?.items || []).slice(0, 8).map((task, i) => (
              <div key={i} className="flex justify-between items-center text-xs p-2 rounded bg-slate-700/40">
                <span className="text-white">{task.room_id || "Oda"}</span>
                <div className="flex gap-1">
                  <PriorityBadge level={task.priority || "low"} />
                  <StatusBadge status={task.status || "pending"} />
                </div>
              </div>
            ))}
            {(housekeeping_board?.count || 0) === 0 && <p className="text-xs text-slate-500">Gorev yok</p>}
          </CardContent>
        </Card>

        {/* VIP Arrivals */}
        <Card className="bg-slate-800/60 border-slate-700" data-testid="vip-arrivals">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
              <Shield className="h-4 w-4 text-amber-400" /> VIP Varislar ({vip_arrivals?.count || 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 max-h-48 overflow-y-auto space-y-1">
            {(vip_arrivals?.items || []).slice(0, 5).map((vip, i) => (
              <div key={i} className="flex justify-between items-center text-xs p-2 rounded bg-amber-900/20 border border-amber-500/20">
                <span className="text-amber-300">{vip.guest_name || "VIP"}</span>
                <span className="text-slate-400">{vip.room_type || ""}</span>
              </div>
            ))}
            {(vip_arrivals?.count || 0) === 0 && <p className="text-xs text-slate-500">VIP varis yok</p>}
          </CardContent>
        </Card>

        {/* Audit Exceptions */}
        <Card className="bg-slate-800/60 border-slate-700" data-testid="audit-exceptions">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-400" /> Audit Istisnalar ({audit_exceptions?.count || 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 max-h-48 overflow-y-auto space-y-1">
            {(audit_exceptions?.items || []).slice(0, 5).map((exc, i) => (
              <div key={i} className="text-xs p-2 rounded bg-red-900/20 border border-red-500/20">
                <span className="text-red-300">{exc.payload?.description || exc.event_type || "Exception"}</span>
              </div>
            ))}
            {(audit_exceptions?.count || 0) === 0 && <p className="text-xs text-slate-500">Istisna yok</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Messaging Panel removed — use full MessagingDashboard instead ──

// ── Auto-Pricing Panel ──

function AutoPricingPanel() {
  const [dashboard, setDashboard] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [dash, hist] = await Promise.all([
        apiFetch("/api/enterprise/autopricing/dashboard"),
        apiFetch("/api/enterprise/autopricing/history?limit=20"),
      ]);
      setDashboard(dash);
      setHistory(hist.recommendations || []);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleApprove = async (recId) => {
    setLoading(true);
    try {
      await apiFetch("/api/enterprise/autopricing/approve", {
        method: "POST", body: JSON.stringify({ recommendation_id: recId }),
      });
      await loadData();
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handleReject = async (recId) => {
    setLoading(true);
    try {
      await apiFetch("/api/enterprise/autopricing/reject", {
        method: "POST", body: JSON.stringify({ recommendation_id: recId, reason: "Admin rejected" }),
      });
      await loadData();
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handleRollback = async (recId) => {
    setLoading(true);
    try {
      await apiFetch("/api/enterprise/autopricing/rollback", {
        method: "POST", body: JSON.stringify({ recommendation_id: recId, reason: "Admin rollback" }),
      });
      await loadData();
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  if (!dashboard) return <p className="text-slate-400 text-sm p-4">Yükleniyor...</p>;

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard title="Bekleyen" value={dashboard.stats?.pending || 0} icon={Clock} color="text-yellow-400" />
        <StatCard title="Uygulanan" value={dashboard.stats?.applied || 0} icon={CheckCircle} color="text-green-400" />
        <StatCard title="Reddedilen" value={dashboard.stats?.rejected || 0} icon={XCircle} color="text-red-400" />
        <StatCard title="Geri Alinan" value={dashboard.stats?.rolled_back || 0} icon={RotateCcw} color="text-purple-400" />
        <StatCard title="Mod" value={dashboard.policy?.mode || "manual"} icon={Zap} color="text-blue-400"
          sub={`Max %${dashboard.policy?.max_auto_change_pct || 0}`} />
      </div>

      {/* Pending Recommendations */}
      <Card className="bg-slate-800/60 border-slate-700" data-testid="pending-recommendations">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-yellow-400" /> Bekleyen Fiyat Onerileri ({dashboard.pending_count})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 space-y-2">
          {(dashboard.pending_recommendations || []).map((rec) => (
            <div key={rec.id} className="p-3 rounded bg-slate-700/40 border border-slate-600/50">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <span className="text-white text-sm font-medium">{rec.room_type}</span>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-slate-400 text-xs">{rec.current_rate}TL</span>
                    <ChevronRight className="h-3 w-3 text-slate-500" />
                    <span className={`text-xs font-bold ${rec.suggested_rate > rec.current_rate ? "text-green-400" : "text-red-400"}`}>
                      {rec.suggested_rate}TL
                    </span>
                    <span className="text-xs text-slate-500">(%{rec.change_pct})</span>
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => handleApprove(rec.id)} disabled={loading}
                    data-testid="approve-btn" className="h-7 text-xs text-green-400 hover:text-green-300 hover:bg-green-900/20">
                    <CheckCircle className="h-3 w-3 mr-1" /> Onayla
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => handleReject(rec.id)} disabled={loading}
                    data-testid="reject-btn" className="h-7 text-xs text-red-400 hover:text-red-300 hover:bg-red-900/20">
                    <XCircle className="h-3 w-3 mr-1" /> Reddet
                  </Button>
                </div>
              </div>
              <p className="text-xs text-slate-500">{rec.reason} | Kaynak: {rec.source} | Guven: %{(rec.confidence * 100).toFixed(0)}</p>
            </div>
          ))}
          {(dashboard.pending_count || 0) === 0 && <p className="text-xs text-slate-500">Bekleyen oneri yok</p>}
        </CardContent>
      </Card>

      {/* History */}
      <Card className="bg-slate-800/60 border-slate-700">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-300">Oneri Geçmişi</CardTitle>
        </CardHeader>
        <CardContent className="p-3 space-y-1 max-h-64 overflow-y-auto">
          {history.map((rec, i) => (
            <div key={i} className="flex justify-between items-center text-xs p-2 rounded bg-slate-700/40">
              <div className="flex items-center gap-2">
                <span className="text-white">{rec.room_type}</span>
                <span className="text-slate-500">{rec.current_rate} &rarr; {rec.suggested_rate}TL</span>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={rec.status} />
                {rec.status === "applied" && (
                  <button onClick={() => handleRollback(rec.id)} disabled={loading}
                    data-testid="rollback-btn" className="text-purple-400 hover:text-purple-300 transition">
                    <RotateCcw className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Cross-Module Integration Panel ──

function CrossModulePanel() {
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [badges, setBadges] = useState([]);

  const runAll = async () => {
    setRunning(true);
    try {
      const data = await apiFetch("/api/enterprise/integration/run-all", { method: "POST" });
      setResults(data);
      const b = await apiFetch("/api/enterprise/integration/frontdesk-warnings");
      setBadges(b.badges || []);
    } catch (e) { console.error(e); }
    setRunning(false);
  };

  useEffect(() => {
    apiFetch("/api/enterprise/integration/frontdesk-warnings").then(d => setBadges(d.badges || [])).catch(console.error);
  }, []);

  const integrationLabels = {
    cancellation_to_overbooking: { label: "İptal Tahmini -> Overbooking", icon: AlertTriangle },
    booking_prob_to_revenue: { label: "Rezervasyon Olasiligi -> Gelir Guveni", icon: TrendingUp },
    compset_to_adr: { label: "Rakip Fark -> ADR Onerisi", icon: DollarSign },
    guest_requests_to_hk: { label: "Misafir Talep -> HK Oncelik", icon: Users },
    vip_to_room_readiness: { label: "VIP Varis -> Oda Hazirlik", icon: Shield },
    audit_to_escalation: { label: "Audit Istisna -> Eskalasyon", icon: AlertTriangle },
    messaging_to_fallback: { label: "Mesaj Hatasi -> Fallback", icon: MessageSquare },
    sync_to_ops_alert: { label: "Sync Hatasi -> Ops Uyari", icon: Globe },
    autopricing_to_metrics: { label: "Auto-Fiyat -> Metrikler", icon: DollarSign },
    risk_to_frontdesk: { label: "Risk Sinyali -> FD Badge", icon: AlertTriangle },
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm text-slate-300 font-medium">Modueller Arasi Entegrasyonlar</h3>
        <Button size="sm" onClick={runAll} disabled={running} data-testid="run-integrations-btn"
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs">
          <Zap className="h-3 w-3 mr-1" /> {running ? "Calisiyor..." : "Tum Entegrasyonlari Calistir"}
        </Button>
      </div>

      {results && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {Object.entries(results.results || {}).map(([key, val]) => {
            const meta = integrationLabels[key] || { label: key, icon: Activity };
            const Icon = meta.icon;
            const isOk = val?.status === "ok";
            return (
              <Card key={key} className={`bg-slate-800/60 border-slate-700 ${!isOk ? "border-red-500/30" : ""}`}>
                <CardContent className="p-3 flex items-center gap-2">
                  <Icon className={`h-4 w-4 ${isOk ? "text-green-400" : "text-red-400"}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-white truncate">{meta.label}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {isOk ? Object.entries(val).filter(([k]) => k !== "status").map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v).slice(0, 30) : v}`).join(" | ") : val?.error || "Hata"}
                    </p>
                  </div>
                  <StatusBadge status={isOk ? "active" : "failed"} />
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Front Desk Warning Badges */}
      {badges.length > 0 && (
        <Card className="bg-slate-800/60 border-slate-700" data-testid="frontdesk-warnings">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-400" /> Front Desk Uyari Rozetleri ({badges.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 space-y-1">
            {badges.slice(0, 10).map((badge, i) => (
              <div key={i} className="flex justify-between items-center text-xs p-2 rounded bg-orange-900/20 border border-orange-500/20">
                <span className="text-orange-300">{badge.guest_name || badge.booking_id}</span>
                <div className="flex gap-1">
                  {(badge.warnings || []).map((w, j) => (
                    <span key={j} className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 text-xs">{w}</span>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Main Dashboard ──

export default function EnterpriseLiveDashboard({ user }) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState("live");
  const [liveData, setLiveData] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsStats, setWsStats] = useState(null);
  const wsRef = useRef(null);

  const loadLiveData = useCallback(async () => {
    try {
      const data = await apiFetch("/api/enterprise/ws/live-data");
      setLiveData(data);
    } catch (e) { console.error(e); }
  }, []);

  // WebSocket connection
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;
    const wsUrl = API.replace("https://", "wss://").replace("http://", "ws://");
    let ws;
    try {
      ws = new WebSocket(`${wsUrl}/api/enterprise/ws/live?token=${token}`);
      ws.onopen = () => { setWsConnected(true); wsRef.current = ws; };
      ws.onclose = () => { setWsConnected(false); wsRef.current = null; };
      ws.onerror = () => { setWsConnected(false); };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "connection_established") {
            // Connection established, start heartbeat
            const interval = setInterval(() => {
              if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "heartbeat" }));
              }
            }, 30000);
            ws._heartbeatInterval = interval;
          }
          // Refresh live data on any broadcast event
          if (msg.type !== "heartbeat_ack" && msg.type !== "connection_established") {
            loadLiveData();
          }
        } catch (e) { /* WebSocket parse error */ }
      };
    } catch (e) { console.error("WS connection failed:", e); }

    return () => {
      if (ws) {
        clearInterval(ws._heartbeatInterval);
        ws.close();
      }
    };
  }, [loadLiveData]);

  // Poll live data
  useEffect(() => {
    loadLiveData();
    const interval = setInterval(loadLiveData, 15000);
    return () => clearInterval(interval);
  }, [loadLiveData]);

  // WS stats
  useEffect(() => {
    apiFetch("/api/enterprise/ws/stats").then(setWsStats).catch(console.error);
  }, []);

  return (
    <div className="min-h-screen bg-slate-900 text-white" data-testid="enterprise-live-dashboard">
      {/* Header */}
      <div className="border-b border-slate-700/50 bg-slate-900/95 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-600/20">
              <Activity className="h-5 w-5 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">{t("techDashboards.enterpriseLive")}</h1>
              <p className="text-xs text-slate-400">Gercek zamanli operasyonel zeka merkezi</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {wsConnected ? (
              <Badge className="bg-green-500/20 text-green-400 border-green-500/30 text-xs gap-1">
                <Wifi className="h-3 w-3" /> WebSocket Aktif
              </Badge>
            ) : (
              <Badge className="bg-slate-500/20 text-slate-400 border-slate-500/30 text-xs gap-1">
                <WifiOff className="h-3 w-3" /> Polling Modu
              </Badge>
            )}
            <span className="text-xs text-slate-500">
              {wsStats?.total_connections || 0} baglanti
            </span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 py-4">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="bg-slate-800/60 border border-slate-700">
            <TabsTrigger value="live" data-testid="tab-live" className="data-[state=active]:bg-indigo-600 data-[state=active]:text-white text-slate-400 text-xs">
              <Activity className="h-3 w-3 mr-1" /> Canli Operasyon
            </TabsTrigger>
            <TabsTrigger value="autopricing" data-testid="tab-autopricing" className="data-[state=active]:bg-indigo-600 data-[state=active]:text-white text-slate-400 text-xs">
              <DollarSign className="h-3 w-3 mr-1" /> Oto-Fiyatlama
            </TabsTrigger>
            <TabsTrigger value="integration" data-testid="tab-integration" className="data-[state=active]:bg-indigo-600 data-[state=active]:text-white text-slate-400 text-xs">
              <ArrowUpDown className="h-3 w-3 mr-1" /> Entegrasyonlar
            </TabsTrigger>
          </TabsList>

          <TabsContent value="live">
            <LiveOperationsPanel data={liveData} wsConnected={wsConnected} onRefresh={loadLiveData} />
          </TabsContent>
          <TabsContent value="autopricing">
            <AutoPricingPanel />
          </TabsContent>
          <TabsContent value="integration">
            <CrossModulePanel />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
