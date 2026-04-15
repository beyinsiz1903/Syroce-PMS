import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { Search, Activity, Radio, ArrowLeft, RefreshCw, AlertTriangle, CheckCircle, XCircle, Clock, ChevronRight, ChevronDown, Copy, ExternalLink, Gauge, Flame, Award, Rocket, LayoutDashboard } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { ScrollArea } from "../components/ui/scroll-area";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import Layout from "../components/Layout";
import { ChannelHealth } from "../components/ChannelHealthDashboard";
import { TechDebtDashboard } from "../components/TechDebtDashboard";
import { WeeklyProof } from "../components/WeeklyProofDashboard";
import { DeployDashboard } from "../components/DeployDashboard";
import { UnifiedOpsView } from "../components/UnifiedOpsView";

// ─── Reservation Lookup ──────────────────────────────────────────
function ReservationLookup() {
  const [query, setQuery] = useState("");
  const [traceResult, setTraceResult] = useState(null);
  const [rawPayload, setRawPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setTraceResult(null);
    setRawPayload(null);
    setShowRaw(false);

    try {
      // Try external_id first
      const res = await axios.get(`/ops/timeline/external/${encodeURIComponent(q)}`);
      if (res.data && res.data.total_events > 0) {
        setTraceResult(res.data);
        return;
      }
      // Try correlation_id
      const res2 = await axios.get(`/ops/timeline/correlation/${encodeURIComponent(q)}`);
      if (res2.data && res2.data.total_events > 0) {
        setTraceResult({
          external_id: res2.data.entity_map?.external_id || q,
          entity_type: "reservation",
          entity_id: res2.data.entity_map?.reservation || "",
          timeline: res2.data.events || [],
          total_events: res2.data.total_events,
          total_duration_ms: res2.data.total_duration_ms,
          current_stage: res2.data.events?.[res2.data.events.length - 1]?.stage,
          gap_warnings: [],
        });
        return;
      }
      toast.error("Sonuç bulunamadı", { description: `"${q}" için timeline kaydı yok.` });
    } catch (err) {
      toast.error("Arama hatası", { description: err.response?.data?.detail || err.message });
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleSearch();
  };

  const loadRawPayload = async (correlationId) => {
    try {
      const res = await axios.get(`/ops/timeline/raw-payload/${correlationId}`);
      if (res.data && !res.data.error) {
        setRawPayload(res.data);
        setShowRaw(true);
      } else {
        toast.info("Raw payload bulunamadı");
      }
    } catch {
      toast.error("Raw payload yüklenemedi");
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Kopyalandı");
  };

  return (
    <div className="space-y-4" data-testid="reservation-lookup">
      {/* Search bar */}
      <div className="flex gap-2" data-testid="lookup-search-bar">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
          <Input
            ref={inputRef}
            data-testid="lookup-search-input"
            placeholder="external_id veya correlation_id girin..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-10 bg-zinc-900 border-zinc-700 text-zinc-100 font-mono placeholder:text-zinc-600 h-11"
          />
        </div>
        <Button
          data-testid="lookup-search-button"
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="bg-emerald-600 hover:bg-emerald-700 text-white h-11 px-6"
        >
          {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : "Trace"}
        </Button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-16 bg-zinc-800" />
          <Skeleton className="h-32 bg-zinc-800" />
        </div>
      )}

      {/* Result */}
      {traceResult && !loading && (
        <div className="space-y-4" data-testid="trace-result">
          <TraceHeader trace={traceResult} onCopy={copyToClipboard} />
          <TraceTimeline
            events={traceResult.timeline || []}
            onLoadRaw={loadRawPayload}
          />
          {traceResult.gap_warnings?.length > 0 && (
            <GapWarnings warnings={traceResult.gap_warnings} />
          )}
          {showRaw && rawPayload && (
            <RawPayloadViewer payload={rawPayload} onCopy={copyToClipboard} onClose={() => setShowRaw(false)} />
          )}
        </div>
      )}

      {/* Empty state */}
      {!traceResult && !loading && (
        <div className="text-center py-16 text-zinc-500" data-testid="lookup-empty-state">
          <Search className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm">OTA Reservation ID veya Correlation ID girerek trace başlatın</p>
          <p className="text-xs mt-1 text-zinc-600">Örnek: HR-12345, EX-67890, veya UUID</p>
        </div>
      )}
    </div>
  );
}

// ─── Trace Header ────────────────────────────────────────────────
function TraceHeader({ trace, onCopy }) {
  const lastEvent = trace.timeline?.[trace.timeline.length - 1];
  const hasFail = trace.timeline?.some(e => e.status === "failure");
  const isDuplicate = trace.timeline?.some(e =>
    e.stage === "deduplicated" && e.metadata?.is_duplicate === true
  );

  let statusLabel = "PROCESSING";
  let statusColor = "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
  if (hasFail) {
    statusLabel = "FAILED";
    statusColor = "bg-red-500/20 text-red-400 border-red-500/30";
  } else if (isDuplicate) {
    statusLabel = "DUPLICATE";
    statusColor = "bg-orange-500/20 text-orange-400 border-orange-500/30";
  } else if (lastEvent?.stage === "confirmed") {
    statusLabel = "CONFIRMED";
    statusColor = "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
  } else if (lastEvent?.stage === "stored" || lastEvent?.stage === "queued") {
    statusLabel = "STORED";
    statusColor = "bg-blue-500/20 text-blue-400 border-blue-500/30";
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4" data-testid="trace-header">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 rounded text-xs font-bold tracking-wide border ${statusColor}`} data-testid="trace-status-badge">
            {statusLabel}
          </span>
          <span className="text-zinc-400 text-xs font-mono">
            {trace.total_events} event · {trace.total_duration_ms != null ? `${trace.total_duration_ms}ms` : "—"}
          </span>
        </div>
        {trace.timeline?.[0]?.provider && (
          <Badge variant="outline" className="text-zinc-400 border-zinc-700 text-xs">
            {trace.timeline[0].provider}
          </Badge>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs font-mono">
        <div>
          <span className="text-zinc-500">external_id: </span>
          <button onClick={() => onCopy(trace.external_id || "")} className="text-zinc-200 hover:text-white" data-testid="trace-external-id">
            {trace.external_id || "—"}
          </button>
        </div>
        <div>
          <span className="text-zinc-500">entity_id: </span>
          <span className="text-zinc-300">{trace.entity_id || "—"}</span>
        </div>
        <div>
          <span className="text-zinc-500">current_stage: </span>
          <span className="text-zinc-300">{trace.current_stage || "—"}</span>
        </div>
      </div>
    </div>
  );
}

// ─── Trace Timeline ──────────────────────────────────────────────
function TraceTimeline({ events, onLoadRaw }) {
  const [expandedIdx, setExpandedIdx] = useState(null);

  const stageIcon = (status) => {
    if (status === "success") return <CheckCircle className="h-4 w-4 text-emerald-500" />;
    if (status === "failure") return <XCircle className="h-4 w-4 text-red-500" />;
    return <Clock className="h-4 w-4 text-yellow-500" />;
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden" data-testid="trace-timeline">
      <div className="px-4 py-2 border-b border-zinc-800 flex items-center gap-2">
        <Activity className="h-3.5 w-3.5 text-zinc-500" />
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Timeline</span>
      </div>
      <div className="divide-y divide-zinc-800/50">
        {events.map((evt, idx) => {
          const isExpanded = expandedIdx === idx;
          const hasCorrelation = !!evt.correlation_id;

          return (
            <div key={idx} className="group" data-testid={`timeline-event-${idx}`}>
              <button
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-zinc-800/50 transition-colors"
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              >
                {/* Stage icon */}
                {stageIcon(evt.status)}

                {/* Stage name */}
                <span className="text-sm font-mono text-zinc-200 min-w-[140px]">
                  {evt.stage}
                </span>

                {/* Timestamp */}
                <span className="text-xs text-zinc-500 font-mono">
                  {formatTime(evt.timestamp)}
                </span>

                {/* Key metadata inline */}
                <div className="flex-1 flex items-center gap-2 overflow-hidden">
                  {evt.metadata?.is_duplicate === true && (
                    <Badge variant="outline" className="text-orange-400 border-orange-500/30 text-[10px] px-1.5 py-0">
                      DUPLICATE
                    </Badge>
                  )}
                  {evt.metadata?.is_new === true && (
                    <Badge variant="outline" className="text-emerald-400 border-emerald-500/30 text-[10px] px-1.5 py-0">
                      NEW
                    </Badge>
                  )}
                  {evt.metadata?.room_mapped === true && (
                    <Badge variant="outline" className="text-blue-400 border-blue-500/30 text-[10px] px-1.5 py-0">
                      ROOM OK
                    </Badge>
                  )}
                  {evt.metadata?.room_mapped === false && (
                    <Badge variant="outline" className="text-red-400 border-red-500/30 text-[10px] px-1.5 py-0">
                      ROOM FAIL
                    </Badge>
                  )}
                </div>

                {/* Expand arrow */}
                {isExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5 text-zinc-600" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-zinc-600" />
                )}
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="px-4 pb-3 bg-zinc-950/50" data-testid={`timeline-detail-${idx}`}>
                  <div className="pl-7 space-y-2">
                    {/* Metadata */}
                    {evt.metadata && Object.keys(evt.metadata).length > 0 && (
                      <pre className="text-xs text-zinc-400 font-mono bg-zinc-900 rounded p-2 overflow-x-auto">
                        {JSON.stringify(evt.metadata, null, 2)}
                      </pre>
                    )}
                    <div className="flex gap-2 text-[10px] font-mono text-zinc-600">
                      <span>source: {evt.source}</span>
                      <span>·</span>
                      <span>seq: {evt.sequence}</span>
                      {evt.duration_ms && <><span>·</span><span>{evt.duration_ms}ms</span></>}
                    </div>
                    {/* Raw payload button */}
                    {hasCorrelation && evt.stage === "webhook_received" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-zinc-500 hover:text-zinc-300 h-7 px-2"
                        onClick={(e) => { e.stopPropagation(); onLoadRaw(evt.correlation_id); }}
                        data-testid={`load-raw-payload-${idx}`}
                      >
                        <ExternalLink className="h-3 w-3 mr-1" /> Raw Payload Gor
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Gap Warnings ────────────────────────────────────────────────
function GapWarnings({ warnings }) {
  return (
    <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-3" data-testid="gap-warnings">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="h-4 w-4 text-yellow-500" />
        <span className="text-xs font-medium text-yellow-400">Gap Uyarıları</span>
      </div>
      <ul className="space-y-1">
        {warnings.map((w, i) => (
          <li key={i} className="text-xs text-yellow-300/70 font-mono pl-6">{w}</li>
        ))}
      </ul>
    </div>
  );
}

// ─── Raw Payload Viewer ──────────────────────────────────────────
function RawPayloadViewer({ payload, onCopy, onClose }) {
  const raw = typeof payload.raw_payload === "string"
    ? payload.raw_payload
    : JSON.stringify(payload.raw_payload, null, 2);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden" data-testid="raw-payload-viewer">
      <div className="px-4 py-2 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Raw Payload</span>
          <Badge variant="outline" className="text-zinc-500 border-zinc-700 text-[10px]">
            {payload.content_type || "unknown"}
          </Badge>
          <Badge variant="outline" className="text-zinc-500 border-zinc-700 text-[10px]">
            {payload.provider}
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" className="h-6 px-2 text-zinc-500" onClick={() => onCopy(raw)}>
            <Copy className="h-3 w-3" />
          </Button>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-zinc-500" onClick={onClose}>
            <XCircle className="h-3 w-3" />
          </Button>
        </div>
      </div>
      <ScrollArea className="max-h-64">
        <pre className="text-xs text-zinc-400 font-mono p-4 whitespace-pre-wrap break-all">
          {raw}
        </pre>
      </ScrollArea>
    </div>
  );
}

// ─── System Health ───────────────────────────────────────────────
function SystemHealth() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await axios.get("/ops/dashboard");
      setDashboard(res.data);
    } catch (err) {
      toast.error("Dashboard yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    const interval = setInterval(fetchDashboard, 30000);
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  if (loading) return <div className="space-y-3"><Skeleton className="h-24 bg-zinc-800" /><Skeleton className="h-24 bg-zinc-800" /><Skeleton className="h-24 bg-zinc-800" /></div>;
  if (!dashboard) return <div className="text-zinc-500 text-center py-16">Dashboard verisi yok</div>;

  const m = dashboard.metrics || {};
  const score = dashboard.health_score;
  const grade = dashboard.health_grade;

  const gradeColor = {
    A: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
    B: "text-blue-400 border-blue-500/40 bg-blue-500/10",
    C: "text-yellow-400 border-yellow-500/40 bg-yellow-500/10",
    D: "text-orange-400 border-orange-500/40 bg-orange-500/10",
    F: "text-red-400 border-red-500/40 bg-red-500/10",
  }[grade] || "text-zinc-400";

  return (
    <div className="space-y-4" data-testid="system-health">
      {/* Health Score */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex items-center gap-6" data-testid="health-score-card">
        <div className={`text-5xl font-bold font-mono px-4 py-2 rounded-lg border ${gradeColor}`}>
          {grade}
        </div>
        <div>
          <div className="text-3xl font-bold text-zinc-100 font-mono">{score}</div>
          <div className="text-xs text-zinc-500 mt-1">Health Score · Son güncelleme: {formatTime(dashboard.timestamp)}</div>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Import Başarı"
          value={`${m.import_success_rate_24h ?? 100}%`}
          sub="24 saat"
          ok={m.import_success_rate_24h >= 95}
          testId="metric-import-success"
        />
        <MetricCard
          label="Sync Başarı"
          value={`${m.sync_success_rate_24h ?? 100}%`}
          sub="24 saat"
          ok={m.sync_success_rate_24h >= 95}
          testId="metric-sync-success"
        />
        <MetricCard
          label="Outbox Bekleyen"
          value={m.outbox_pending ?? 0}
          sub={`stuck: ${m.outbox_stuck ?? 0}`}
          ok={(m.outbox_stuck ?? 0) === 0}
          testId="metric-outbox-pending"
        />
        <MetricCard
          label="Hatalar (24s)"
          value={m.failure_count_24h ?? 0}
          sub={`aktif: ${m.open_failures ?? 0}`}
          ok={(m.failure_count_24h ?? 0) === 0}
          testId="metric-failures"
        />
      </div>

      {/* Pipeline depth */}
      {dashboard.pipeline?.stages && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4" data-testid="pipeline-depth">
          <div className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">Pipeline Derinligi</div>
          <div className="flex items-center gap-4">
            {dashboard.pipeline.stages.map((s, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="text-xs text-zinc-500 font-mono">{s.name.replace(/_/g, " ")}</span>
                <span className={`text-sm font-bold font-mono ${s.count > 0 ? "text-yellow-400" : "text-zinc-600"}`}>
                  {s.count}
                </span>
                {i < dashboard.pipeline.stages.length - 1 && <ChevronRight className="h-3 w-3 text-zinc-700" />}
              </div>
            ))}
            <span className="text-xs text-zinc-500 ml-auto">toplam: <span className="text-zinc-300 font-mono">{dashboard.pipeline.total_in_flight}</span></span>
          </div>
        </div>
      )}

      {/* Recent failures */}
      {dashboard.recent_failures?.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4" data-testid="recent-failures">
          <div className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">Son Hatalar</div>
          <div className="space-y-2">
            {dashboard.recent_failures.map((f, i) => (
              <div key={i} className="flex items-start gap-2 text-xs font-mono">
                <XCircle className="h-3.5 w-3.5 text-red-500 mt-0.5 shrink-0" />
                <div>
                  <span className="text-zinc-300">{f.operation || f.failure_type || "unknown"}</span>
                  {f.error_message && <span className="text-zinc-600 ml-2">— {f.error_message.slice(0, 80)}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, sub, ok, testId }) {
  return (
    <div className={`bg-zinc-900 border rounded-lg p-4 ${ok ? "border-zinc-800" : "border-red-500/30"}`} data-testid={testId}>
      <div className="text-xs text-zinc-500 mb-1">{label}</div>
      <div className={`text-xl font-bold font-mono ${ok ? "text-zinc-100" : "text-red-400"}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-600 mt-1">{sub}</div>}
    </div>
  );
}

// ─── Live Feed ───────────────────────────────────────────────────
function LiveFeed() {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await axios.get("/ops/timeline/search", { params: { limit: 50 } });
      setEvents(res.data.events || []);
      setTotal(res.data.total || 0);
    } catch {
      toast.error("Event feed yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    if (!autoRefresh) return;
    const interval = setInterval(fetchEvents, 10000);
    return () => clearInterval(interval);
  }, [fetchEvents, autoRefresh]);

  if (loading) return <div className="space-y-2">{Array.from({length: 8}).map((_, i) => <Skeleton key={i} className="h-10 bg-zinc-800" />)}</div>;

  return (
    <div className="space-y-3" data-testid="live-feed">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${autoRefresh ? "bg-emerald-500 animate-pulse" : "bg-zinc-600"}`} />
          <span className="text-xs text-zinc-400">
            {total} toplam event · son 50 gosteriliyor
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-zinc-500"
            onClick={() => setAutoRefresh(!autoRefresh)}
            data-testid="toggle-auto-refresh"
          >
            <Radio className={`h-3 w-3 mr-1 ${autoRefresh ? "text-emerald-500" : ""}`} />
            {autoRefresh ? "Canli" : "Durduruldu"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-zinc-500"
            onClick={fetchEvents}
            data-testid="refresh-feed-button"
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Event list */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="grid grid-cols-[100px_110px_1fr_80px_60px] gap-2 px-4 py-2 border-b border-zinc-800 text-[10px] text-zinc-600 uppercase tracking-wider font-medium">
          <span>Zaman</span>
          <span>Stage</span>
          <span>External ID</span>
          <span>Provider</span>
          <span>Durum</span>
        </div>
        <ScrollArea className="max-h-[500px]">
          {events.map((evt, idx) => {
            const isFail = evt.status === "failure";
            return (
              <div
                key={idx}
                className={`grid grid-cols-[100px_110px_1fr_80px_60px] gap-2 px-4 py-2 text-xs font-mono border-b border-zinc-800/30 hover:bg-zinc-800/30 transition-colors ${isFail ? "bg-red-500/5" : ""}`}
                data-testid={`feed-event-${idx}`}
              >
                <span className="text-zinc-500">{formatTime(evt.timestamp)}</span>
                <span className="text-zinc-300">{evt.stage}</span>
                <span className="text-zinc-400 truncate">{evt.external_id || "—"}</span>
                <span className="text-zinc-500">{evt.provider || "—"}</span>
                <span>
                  {isFail ? (
                    <XCircle className="h-3.5 w-3.5 text-red-500" />
                  ) : evt.status === "success" ? (
                    <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <Clock className="h-3.5 w-3.5 text-yellow-500" />
                  )}
                </span>
              </div>
            );
          })}
        </ScrollArea>
      </div>
    </div>
  );
}

// ─── Helper ──────────────────────────────────────────────────────
function formatTime(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return isoStr;
  }
}

// ─── Main Page ───────────────────────────────────────────────────
export default function ControlPlane({ user, tenant, onLogout }) {
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentPage="control_plane">
      <div className="min-h-screen bg-zinc-950 text-zinc-100" data-testid="control-plane-page">
        <div className="max-w-6xl mx-auto px-4 py-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-lg font-semibold text-zinc-100 tracking-tight">Control Plane</h1>
              <p className="text-xs text-zinc-500 mt-0.5">Ops merkezi · Kanal sağlığı · Deploy · DORA · Envanter hizalama</p>
            </div>
          </div>

          {/* Tabs */}
          <Tabs defaultValue="ops" className="space-y-4">
            <TabsList className="bg-zinc-900 border border-zinc-800 p-1">
              <TabsTrigger
                value="ops"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-ops"
              >
                <LayoutDashboard className="h-3.5 w-3.5 mr-2" />
                Ops Merkezi
              </TabsTrigger>
              <TabsTrigger
                value="lookup"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-lookup"
              >
                <Search className="h-3.5 w-3.5 mr-2" />
                Trace
              </TabsTrigger>
              <TabsTrigger
                value="health"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-health"
              >
                <Activity className="h-3.5 w-3.5 mr-2" />
                Saglik
              </TabsTrigger>
              <TabsTrigger
                value="channel-health"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-channel-health"
              >
                <Gauge className="h-3.5 w-3.5 mr-2" />
                Kanal Sagligi
              </TabsTrigger>
              <TabsTrigger
                value="feed"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-feed"
              >
                <Radio className="h-3.5 w-3.5 mr-2" />
                Canli
              </TabsTrigger>
              <TabsTrigger
                value="weekly-proof"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-weekly-proof"
              >
                <Award className="h-3.5 w-3.5 mr-2" />
                Deger Kaniti
              </TabsTrigger>
              <TabsTrigger
                value="deploys"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-deploys"
              >
                <Rocket className="h-3.5 w-3.5 mr-2" />
                Deploy
              </TabsTrigger>
              <TabsTrigger
                value="tech-debt"
                className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100 text-zinc-500 text-sm px-4"
                data-testid="tab-tech-debt"
              >
                <Flame className="h-3.5 w-3.5 mr-2" />
                Teknik Borc
              </TabsTrigger>
            </TabsList>

            <TabsContent value="ops">
              <UnifiedOpsView />
            </TabsContent>
            <TabsContent value="lookup">
              <ReservationLookup />
            </TabsContent>
            <TabsContent value="health">
              <SystemHealth />
            </TabsContent>
            <TabsContent value="channel-health">
              <ChannelHealth />
            </TabsContent>
            <TabsContent value="feed">
              <LiveFeed />
            </TabsContent>
            <TabsContent value="weekly-proof">
              <WeeklyProof />
            </TabsContent>
            <TabsContent value="deploys">
              <DeployDashboard />
            </TabsContent>
            <TabsContent value="tech-debt">
              <TechDebtDashboard />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </Layout>
  );
}
