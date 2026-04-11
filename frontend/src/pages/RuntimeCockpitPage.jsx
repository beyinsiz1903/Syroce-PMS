import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { io } from 'socket.io-client';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Shield, ShieldCheck, ShieldAlert,
  Activity, AlertTriangle, CheckCircle, XCircle,
  RefreshCw, Loader2, Gauge, Lock,
  Timer, Zap, ArrowUpDown, Archive,
  HeartPulse, TrendingUp, Clock, Eye,
  Play, Square, Pause, RotateCcw, Bell,
  ChevronRight, Target, Rocket,
  TriangleAlert, Info, Ban, Wrench,
  VolumeX, RotateCw, ClipboardCheck,
  ArrowRight, CircleDot, Radio
} from 'lucide-react';

const API = import.meta.env.VITE_BACKEND_URL;

const SEVERITY_STYLE = {
  info: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  warning: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
  blocker: 'bg-rose-600/20 text-rose-400 border-rose-500/40 animate-pulse',
};

const SEVERITY_ICON = {
  blocker: Ban,
  critical: TriangleAlert,
  warning: AlertTriangle,
  info: Info,
};

const MetricPill = ({ label, value, good, alert, testId }) => (
  <div data-testid={testId} className="flex items-center justify-between py-2 px-3 rounded-lg bg-zinc-800/40">
    <span className="text-xs text-zinc-500 font-medium">{label}</span>
    <span className={`text-sm font-mono font-bold ${
      alert ? 'text-red-400' : good ? 'text-emerald-400' : 'text-zinc-200'
    }`}>
      {value}
    </span>
  </div>
);

const StatusLight = ({ active, label, testId }) => (
  <div data-testid={testId} className="flex items-center gap-2">
    <span className={`w-2.5 h-2.5 rounded-full ${
      active ? 'bg-emerald-500 shadow-emerald-500/50 shadow-lg' : 'bg-zinc-600'
    }`} />
    <span className="text-xs text-zinc-400">{label}</span>
  </div>
);

const Section = ({ title, icon: Icon, iconColor, children, testId, actions }) => (
  <Card data-testid={testId} className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
    <CardHeader className="pb-3 pt-4 px-4">
      <div className="flex items-center justify-between">
        <CardTitle className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
          <Icon className={`w-4 h-4 ${iconColor}`} />
          {title}
        </CardTitle>
        {actions && <div className="flex gap-1">{actions}</div>}
      </div>
    </CardHeader>
    <CardContent className="px-4 pb-4 space-y-1.5">
      {children}
    </CardContent>
  </Card>
);

const AgeBucket = ({ label, count, color }) => (
  <div className="flex items-center justify-between">
    <span className="text-xs text-zinc-500">{label}</span>
    <Badge className={`${color} border text-[10px] px-1.5 font-mono`}>{count}</Badge>
  </div>
);

const EventRow = ({ event }) => {
  const style = SEVERITY_STYLE[event.severity] || SEVERITY_STYLE.info;
  const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '';
  return (
    <div data-testid={`event-row-${event.id}`} className="flex items-center gap-2 py-1.5 border-b border-zinc-800/40 last:border-0">
      <Badge className={`${style} border text-[9px] px-1.5 uppercase`}>{event.severity}</Badge>
      <span className="text-xs text-zinc-300 flex-1 truncate">{event.description}</span>
      <span className="text-[10px] text-zinc-600 font-mono">{time}</span>
    </div>
  );
};

/* ═══ Phase Progress Bar ═══ */
const PhaseProgress = ({ phases, testId }) => (
  <div data-testid={testId} className="flex items-center gap-1">
    {phases.map((p, i) => (
      <div key={p.phase} className="flex items-center gap-1">
        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider ${
          p.status === 'completed' ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' :
          p.status === 'active' ? 'bg-blue-500/15 text-blue-400 border border-blue-500/40 ring-1 ring-blue-500/20' :
          'bg-zinc-800/40 text-zinc-600 border border-zinc-700/30'
        }`}>
          {p.status === 'completed' && <CheckCircle className="w-3 h-3" />}
          {p.status === 'active' && <CircleDot className="w-3 h-3" />}
          {p.label}
        </div>
        {i < phases.length - 1 && <ArrowRight className="w-3 h-3 text-zinc-700" />}
      </div>
    ))}
  </div>
);

/* ═══ Readiness Score Ring ═══ */
const ScoreRing = ({ score, testId }) => {
  const color = score >= 90 ? 'text-emerald-400' : score >= 60 ? 'text-amber-400' : 'text-red-400';
  const ringColor = score >= 90 ? 'stroke-emerald-400' : score >= 60 ? 'stroke-amber-400' : 'stroke-red-400';
  const circumference = 2 * Math.PI * 36;
  const offset = circumference - (score / 100) * circumference;
  return (
    <div data-testid={testId} className="relative w-24 h-24">
      <svg className="w-24 h-24 -rotate-90" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="6" className="text-zinc-800" />
        <circle cx="40" cy="40" r="36" fill="none" strokeWidth="6" strokeLinecap="round"
          className={ringColor} strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-xl font-bold font-mono ${color}`}>{score}</span>
        <span className="text-[9px] text-zinc-500 uppercase">/100</span>
      </div>
    </div>
  );
};

/* ═══ Gate Check Row ═══ */
const GateCheck = ({ check }) => (
  <div data-testid={`gate-${check.name}`} className="flex items-center gap-2 py-1.5 border-b border-zinc-800/30 last:border-0">
    {check.passed
      ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
      : <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
    }
    <span className="text-xs text-zinc-300 flex-1">{check.label}</span>
    <span className={`text-[10px] font-mono ${check.passed ? 'text-emerald-400' : 'text-red-400'}`}>
      {check.value}
    </span>
  </div>
);

export default function RuntimeCockpitPage({ user, tenant, onLogout }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cockpit, setCockpit] = useState(null);
  const [events, setEvents] = useState([]);
  const [eventSummary, setEventSummary] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [rollout, setRollout] = useState(null);
  const [actionLoading, setActionLoading] = useState({});
  const [tab, setTab] = useState('cockpit');
  const [wsConnected, setWsConnected] = useState(false);
  const [liveSnapshot, setLiveSnapshot] = useState(null);
  const socketRef = useRef(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  // WebSocket connection for real-time cockpit streaming
  useEffect(() => {
    const wsUrl = API.replace(/^http/, 'ws').replace(/\/$/, '') + '/ws';
    const httpUrl = API.replace(/\/$/, '') + '/ws';
    try {
      const socket = io(httpUrl, {
        path: '/socket.io',
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: 2000,
      });

      socket.on('connect', () => {
        setWsConnected(true);
        socket.emit('join_room', { room: 'cockpit' });
      });

      socket.on('disconnect', () => setWsConnected(false));

      socket.on('cockpit_snapshot', (data) => {
        if (data?.snapshot) {
          setLiveSnapshot(data.snapshot);
        }
      });

      socketRef.current = socket;

      return () => {
        socket.emit('leave_room', { room: 'cockpit' });
        socket.disconnect();
        socketRef.current = null;
      };
    } catch {
      // WebSocket not available, graceful fallback
    }
  }, []);

  const fetchAll = useCallback(async () => {
    try {
      const [cRes, eRes, sRes, rRes, roRes] = await Promise.allSettled([
        axios.get(`${API}/api/lockdown/runtime/cockpit`, { headers }),
        axios.get(`${API}/api/lockdown/notifications/events?limit=10`, { headers }),
        axios.get(`${API}/api/lockdown/notifications/summary`, { headers }),
        axios.get(`${API}/api/lockdown/runtime/readiness-score`, { headers }),
        axios.get(`${API}/api/lockdown/runtime/rollout/dashboard`, { headers }),
      ]);
      if (cRes.status === 'fulfilled') setCockpit(cRes.value.data);
      if (eRes.status === 'fulfilled') setEvents(eRes.value.data.events || []);
      if (sRes.status === 'fulfilled') setEventSummary(sRes.value.data);
      if (rRes.status === 'fulfilled') setReadiness(rRes.value.data);
      if (roRes.status === 'fulfilled') setRollout(roRes.value.data);
    } catch {
      toast.error('Runtime verileri yuklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleRefresh = () => { setRefreshing(true); fetchAll(); };

  const handleEvaluate = async () => {
    try {
      const res = await axios.post(`${API}/api/lockdown/notifications/evaluate`, {}, { headers });
      toast.success(`${res.data.events_emitted} event emitted`);
      fetchAll();
    } catch { toast.error('Evaluation failed'); }
  };

  const handlePushLoopAction = async (action) => {
    try {
      await axios.post(`${API}/api/lockdown/runtime/push-loop/${action}`, {}, { headers });
      toast.success(`Push loop: ${action}`);
      setTimeout(fetchAll, 500);
    } catch { toast.error(`Push loop ${action} failed`); }
  };

  const handleSafeAction = async (actionType, body = {}) => {
    setActionLoading(prev => ({ ...prev, [actionType]: true }));
    try {
      const res = await axios.post(`${API}/api/lockdown/runtime/actions/${actionType}`, body, { headers });
      const d = res.data;
      if (d.status === 'blocked') {
        toast.error(d.message);
      } else {
        toast.success(d.message);
      }
      fetchAll();
    } catch { toast.error(`Action failed: ${actionType}`); }
    finally { setActionLoading(prev => ({ ...prev, [actionType]: false })); }
  };

  const handleRolloutInit = async () => {
    try {
      await axios.post(`${API}/api/lockdown/runtime/rollout/initialize`, {}, { headers });
      toast.success('Rollout baslatildi');
      fetchAll();
    } catch { toast.error('Rollout baslatilamadi'); }
  };

  const handleRolloutAdvance = async () => {
    try {
      const res = await axios.post(`${API}/api/lockdown/runtime/rollout/advance`, {}, { headers });
      if (res.data.transitioned) {
        toast.success(res.data.message);
      } else {
        toast.error(res.data.message);
      }
      fetchAll();
    } catch { toast.error('Faz gecisi basarisiz'); }
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="lockdown">
        <div className="flex items-center justify-center h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
        </div>
      </Layout>
    );
  }

  const h = cockpit?.health || {};
  const flow = cockpit?.flow || {};
  const rel = cockpit?.reliability || {};
  const dh = cockpit?.drift_heal || {};
  const hf = cockpit?.hard_fail || {};
  const q = cockpit?.quarantine || {};
  const ageBuckets = q.by_age_bucket || {};

  const rs = readiness || {};
  const rsIssues = rs.issues || [];
  const fixOrder = rs.fix_order || [];

  const ro = rollout || {};
  const gateChecks = ro.gate_evaluation?.checks || [];
  const phaseProgress = ro.phase_progress || [];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="lockdown">
      <div className="space-y-5 p-4 lg:p-6 max-w-[1400px] mx-auto">

        {/* ─── Header ──────────────────────────────────────── */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl ${h.is_production_ready ? 'bg-emerald-500/15' : 'bg-red-500/15'}`}>
              {h.is_production_ready
                ? <ShieldCheck data-testid="cockpit-ready-icon" className="w-6 h-6 text-emerald-400" />
                : <ShieldAlert data-testid="cockpit-not-ready-icon" className="w-6 h-6 text-red-400" />
              }
            </div>
            <div>
              <h1 data-testid="cockpit-title" className="text-xl font-bold text-zinc-100">
                Runtime Cockpit
              </h1>
              <p className="text-xs text-zinc-500">Operasyonel Ucus Paneli</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              data-testid="cockpit-ready-badge"
              className={`text-xs font-bold px-3 py-1 ${
                h.is_production_ready
                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40'
                  : 'bg-red-500/15 text-red-400 border-red-500/40'
              } border`}
            >
              {h.is_production_ready ? 'PRODUCTION READY' : 'NOT READY'}
            </Badge>
            <Button data-testid="cockpit-evaluate-btn" variant="outline" size="sm"
              onClick={handleEvaluate} className="border-zinc-700 text-zinc-400 hover:text-zinc-100">
              <Bell className="w-3.5 h-3.5 mr-1" /> Evaluate
            </Button>
            {wsConnected && (
              <Badge data-testid="cockpit-live-badge" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 border text-[10px] gap-1">
                <Radio className="w-3 h-3 animate-pulse" /> LIVE
              </Badge>
            )}
            <Button data-testid="cockpit-refresh-btn" variant="outline" size="sm"
              onClick={handleRefresh} disabled={refreshing} className="border-zinc-700 text-zinc-400 hover:text-zinc-100">
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${refreshing ? 'animate-spin' : ''}`} /> Yenile
            </Button>
          </div>
        </div>

        {/* ─── Tab Navigation ──────────────────────────────── */}
        <div className="flex gap-1 border-b border-zinc-800 pb-0">
          {[
            { key: 'cockpit', label: 'Cockpit', icon: Gauge },
            { key: 'readiness', label: 'Why NOT READY?', icon: Target },
            { key: 'actions', label: '1-Click Actions', icon: Zap },
            { key: 'rollout', label: 'Narrow Rollout', icon: Rocket },
          ].map(t => (
            <button key={t.key} data-testid={`tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-all ${
                tab === t.key
                  ? 'bg-zinc-800/60 text-zinc-100 border-b-2 border-blue-500'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30'
              }`}
            >
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          ))}
        </div>

        {/* ═══ TAB: COCKPIT ═══ */}
        {tab === 'cockpit' && (
          <>
            {/* Live Metrics Strip (WebSocket) */}
            {liveSnapshot && wsConnected && (
              <div data-testid="live-metrics-strip" className="flex items-center gap-3 px-3 py-2 bg-zinc-900/80 border border-zinc-800/50 rounded-lg">
                <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse shrink-0" />
                <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider">LIVE</span>
                <div className="flex gap-4 overflow-x-auto">
                  <span className="text-[10px] text-zinc-400">Verify: <b className={liveSnapshot.verify_ratio >= 0.95 ? 'text-emerald-400' : 'text-red-400'}>{(liveSnapshot.verify_ratio * 100).toFixed(1)}%</b></span>
                  <span className="text-[10px] text-zinc-400">Queue: <b className="text-zinc-200">{liveSnapshot.queue_size}</b></span>
                  <span className="text-[10px] text-zinc-400">Emitted: <b className="text-zinc-200">{liveSnapshot.emitted}</b></span>
                  <span className="text-[10px] text-zinc-400">HF Block: <b className={liveSnapshot.hard_fail_blocked > 0 ? 'text-red-400' : 'text-zinc-200'}>{liveSnapshot.hard_fail_blocked}</b></span>
                  <span className="text-[10px] text-zinc-400">Quarantine: <b className={liveSnapshot.quarantine_count > 0 ? 'text-red-400' : 'text-zinc-200'}>{liveSnapshot.quarantine_count}</b></span>
                  <span className="text-[10px] text-zinc-400">Drift: <b className={liveSnapshot.drift_count > 0 ? 'text-amber-400' : 'text-zinc-200'}>{liveSnapshot.drift_count}</b></span>
                  <span className="text-[10px] text-zinc-400">Ready: <b className={liveSnapshot.is_production_ready ? 'text-emerald-400' : 'text-red-400'}>{liveSnapshot.is_production_ready ? 'YES' : 'NO'}</b></span>
                </div>
              </div>
            )}
            {/* Health Summary */}
            <div data-testid="cockpit-health-summary" className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Card className={`bg-zinc-900/60 border-zinc-800 backdrop-blur ${!h.is_production_ready ? 'border-red-500/30 ring-1 ring-red-500/10' : 'border-emerald-500/30'}`}>
                <CardContent className="p-3 text-center">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Status</p>
                  <p data-testid="health-status" className={`text-lg font-bold mt-0.5 ${h.is_production_ready ? 'text-emerald-400' : 'text-red-400'}`}>
                    {h.is_production_ready ? 'READY' : 'NOT READY'}
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
                <CardContent className="p-3 text-center">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Incidents</p>
                  <p data-testid="health-incidents" className={`text-lg font-bold mt-0.5 ${h.active_incidents > 0 ? 'text-amber-400' : 'text-zinc-300'}`}>{h.active_incidents || 0}</p>
                </CardContent>
              </Card>
              <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
                <CardContent className="p-3 text-center">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Quarantine</p>
                  <p data-testid="health-quarantine" className={`text-lg font-bold mt-0.5 ${h.quarantine_count > 0 ? 'text-red-400' : 'text-zinc-300'}`}>{h.quarantine_count || 0}</p>
                </CardContent>
              </Card>
              <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
                <CardContent className="p-3 text-center">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Verify %</p>
                  <p data-testid="health-verify-pct" className={`text-lg font-bold mt-0.5 ${h.verify_success_pct >= 95 ? 'text-emerald-400' : h.verify_success_pct > 0 ? 'text-amber-400' : 'text-zinc-300'}`}>{h.verify_success_pct || 0}%</p>
                </CardContent>
              </Card>
              <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
                <CardContent className="p-3 text-center">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Push Loop</p>
                  <p data-testid="health-push-loop" className={`text-lg font-bold mt-0.5 ${
                    h.push_loop_status === 'running' ? 'text-emerald-400' :
                    h.push_loop_status === 'paused' ? 'text-amber-400' : 'text-zinc-300'
                  }`}>{(h.push_loop_status || 'stopped').toUpperCase()}</p>
                </CardContent>
              </Card>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                {/* Flow Metrics */}
                <Section title="Flow Metrics" icon={ArrowUpDown} iconColor="text-blue-400" testId="cockpit-flow-section">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    <MetricPill label="Queued" value={flow.queued || 0} testId="flow-queued" />
                    <MetricPill label="Coalesced" value={flow.coalesced || 0} testId="flow-coalesced" />
                    <MetricPill label="Emitted" value={flow.emitted || 0} good={flow.emitted > 0} testId="flow-emitted" />
                    <MetricPill label="Dropped" value={flow.dropped || 0} testId="flow-dropped" />
                    <MetricPill label="Hard Fail Blocked" value={flow.hard_fail_blocked || 0} alert={flow.hard_fail_blocked > 0} testId="flow-hard-fail" />
                    <MetricPill label="Cycles" value={flow.cycle_count || 0} testId="flow-cycles" />
                  </div>
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-zinc-800/50">
                    <span className="text-xs text-zinc-500 mr-2">Push Loop:</span>
                    <Button data-testid="push-loop-start-btn" variant="outline" size="sm" onClick={() => handlePushLoopAction('start')}
                      className="border-zinc-700 text-emerald-400 hover:bg-emerald-500/10 h-7 px-2 text-xs"><Play className="w-3 h-3 mr-1" /> Start</Button>
                    <Button data-testid="push-loop-pause-btn" variant="outline" size="sm" onClick={() => handlePushLoopAction('pause')}
                      className="border-zinc-700 text-amber-400 hover:bg-amber-500/10 h-7 px-2 text-xs"><Pause className="w-3 h-3 mr-1" /> Pause</Button>
                    <Button data-testid="push-loop-stop-btn" variant="outline" size="sm" onClick={() => handlePushLoopAction('stop')}
                      className="border-zinc-700 text-red-400 hover:bg-red-500/10 h-7 px-2 text-xs"><Square className="w-3 h-3 mr-1" /> Stop</Button>
                  </div>
                </Section>

                {/* Reliability */}
                <Section title="Reliability" icon={HeartPulse} iconColor="text-emerald-400" testId="cockpit-reliability-section">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    <MetricPill label="Verify Success Ratio" value={`${(rel.verify_success_ratio * 100).toFixed(1)}%`}
                      good={rel.verify_success_ratio >= 0.95} alert={rel.verify_success_ratio < 0.8 && rel.verify_success_count + rel.verify_fail_count > 0} testId="rel-verify-ratio" />
                    <MetricPill label="Verify OK" value={rel.verify_success_count || 0} good testId="rel-verify-ok" />
                    <MetricPill label="Verify FAIL" value={rel.verify_fail_count || 0} alert={rel.verify_fail_count > 0} testId="rel-verify-fail" />
                    <MetricPill label="Dead Letters" value={rel.dead_letters || 0} alert={rel.dead_letters > 0} testId="rel-dead-letters" />
                    <MetricPill label="Cycle Duration" value={`${rel.last_cycle_duration_ms || 0}ms`} testId="rel-cycle-ms" />
                    <MetricPill label="Ack Latency"
                      value={Object.keys(rel.provider_ack_latency_avg_ms || {}).length > 0
                        ? Object.entries(rel.provider_ack_latency_avg_ms).map(([p, v]) => `${p}: ${v}ms`).join(', ') : 'N/A'}
                      testId="rel-ack-latency" />
                  </div>
                </Section>

                {/* Drift & Heal */}
                <Section title="Drift & Auto-Heal" icon={RotateCcw} iconColor="text-violet-400" testId="cockpit-drift-section">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    <MetricPill label="Active Drifts" value={dh.drift_count || 0} alert={dh.drift_count > 0} testId="drift-count" />
                    <MetricPill label="Auto-Healed (Total)" value={dh.auto_heal_total_healed || 0} good={dh.auto_heal_total_healed > 0} testId="drift-healed" />
                    <MetricPill label="Auto-Heal Failed" value={dh.auto_heal_total_failed || 0} alert={dh.auto_heal_total_failed > 0} testId="drift-heal-failed" />
                    <MetricPill label="Eligible for Heal" value={dh.auto_heal_eligible || 0} testId="drift-eligible" />
                    <MetricPill label="Healed (24h)" value={dh.auto_heal_last_24h || 0} testId="drift-healed-24h" />
                    <MetricPill label="Manual Required" value={dh.manual_required || 0} alert={dh.manual_required > 0} testId="drift-manual" />
                  </div>
                </Section>
              </div>

              <div className="space-y-4">
                {/* Quarantine */}
                <Section title="Quarantine" icon={Lock} iconColor="text-red-400" testId="cockpit-quarantine-section">
                  <div className="text-center py-2">
                    <p data-testid="quarantine-total" className={`text-3xl font-bold ${q.total_quarantined > 0 ? 'text-red-400' : 'text-zinc-500'}`}>{q.total_quarantined || 0}</p>
                    <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Quarantined Items</p>
                  </div>
                  {q.total_quarantined > 0 && (
                    <>
                      <div className="pt-2 border-t border-zinc-800/50">
                        <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5">Classification</p>
                        {Object.entries(q.by_classification || {}).map(([type, count]) => (
                          <div key={type} className="flex items-center justify-between py-0.5">
                            <span className="text-xs text-zinc-400">{type.replace(/_/g, ' ')}</span>
                            <span className="text-xs font-mono text-zinc-300">{count}</span>
                          </div>
                        ))}
                      </div>
                      <div className="pt-2 border-t border-zinc-800/50">
                        <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5">Age Distribution</p>
                        <AgeBucket label="< 5 min" count={ageBuckets.lt_5min || 0} color="bg-emerald-500/15 text-emerald-400 border-emerald-500/30" />
                        <AgeBucket label="5-30 min" count={ageBuckets['5_30min'] || 0} color="bg-amber-500/15 text-amber-400 border-amber-500/30" />
                        <AgeBucket label="30-120 min" count={ageBuckets['30_120min'] || 0} color="bg-orange-500/15 text-orange-400 border-orange-500/30" />
                        <AgeBucket label="> 2 hours" count={ageBuckets.gt_2h || 0} color="bg-red-500/15 text-red-400 border-red-500/30" />
                      </div>
                      {Object.keys(q.by_provider || {}).length > 0 && (
                        <div className="pt-2 border-t border-zinc-800/50">
                          <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5">By Provider</p>
                          {Object.entries(q.by_provider).map(([prov, count]) => (
                            <div key={prov} className="flex items-center justify-between py-0.5">
                              <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/20 border text-[10px]">{prov}</Badge>
                              <span className="text-xs font-mono text-zinc-300">{count}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                  {q.total_quarantined === 0 && (
                    <div className="flex items-center justify-center gap-2 py-3 text-emerald-500/60">
                      <CheckCircle className="w-4 h-4" /><span className="text-xs">No quarantined items</span>
                    </div>
                  )}
                </Section>

                {/* Events */}
                <Section title="Recent Events" icon={Bell} iconColor="text-amber-400" testId="cockpit-events-section">
                  {eventSummary && (
                    <div className="grid grid-cols-4 gap-1 mb-2">
                      {['info', 'warning', 'critical', 'blocker'].map((sev) => (
                        <div key={sev} className="text-center">
                          <p className="text-[10px] text-zinc-600 uppercase">{sev}</p>
                          <p className={`text-sm font-bold ${
                            sev === 'blocker' ? 'text-rose-400' : sev === 'critical' ? 'text-red-400' :
                            sev === 'warning' ? 'text-amber-400' : 'text-blue-400'
                          }`}>{eventSummary.by_severity?.[sev] || 0}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="space-y-0.5 max-h-[300px] overflow-y-auto">
                    {events.length === 0
                      ? <p className="text-xs text-zinc-600 text-center py-3">No events yet</p>
                      : events.map((evt) => <EventRow key={evt.id} event={evt} />)
                    }
                  </div>
                </Section>

                {/* Hard Fail */}
                <Section title="Hard Fail Gate" icon={Shield} iconColor="text-orange-400" testId="cockpit-hardfail-section">
                  <MetricPill label="Active Blocks" value={hf.hard_fail_change_sets || 0} alert={hf.hard_fail_change_sets > 0} testId="hf-active" />
                  <MetricPill label="Open Incidents" value={hf.open_hard_fail_incidents || 0} alert={hf.open_hard_fail_incidents > 0} testId="hf-incidents" />
                  <MetricPill label="Blocks (24h)" value={hf.hard_fails_last_24h || 0} testId="hf-24h" />
                  {Object.keys(hf.by_failure_type || {}).length > 0 && (
                    <div className="pt-2 border-t border-zinc-800/50">
                      <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1">By Type</p>
                      {Object.entries(hf.by_failure_type).map(([type, count]) => (
                        <div key={type} className="flex items-center justify-between py-0.5">
                          <span className="text-xs text-zinc-400">{type.replace(/_/g, ' ')}</span>
                          <span className="text-xs font-mono text-zinc-300">{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </Section>
              </div>
            </div>
          </>
        )}

        {/* ═══ TAB: WHY NOT READY? ═══ */}
        {tab === 'readiness' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 space-y-4">
              {/* Issues List */}
              <Section title="Sorun Listesi (Oncelik Sirasina Gore)" icon={AlertTriangle} iconColor="text-amber-400" testId="readiness-issues-section">
                {rsIssues.length === 0 ? (
                  <div className="flex items-center justify-center gap-2 py-6 text-emerald-500/60">
                    <CheckCircle className="w-5 h-5" />
                    <span className="text-sm">Tum kontroller gecti — sistem hazir!</span>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {rsIssues.map((issue, i) => {
                      const Ic = SEVERITY_ICON[issue.severity] || Info;
                      const style = SEVERITY_STYLE[issue.severity] || SEVERITY_STYLE.info;
                      return (
                        <div key={i} data-testid={`readiness-issue-${i}`}
                          className="p-3 rounded-lg bg-zinc-800/30 border border-zinc-800/50">
                          <div className="flex items-start gap-2">
                            <Ic className={`w-4 h-4 mt-0.5 shrink-0 ${
                              issue.severity === 'blocker' ? 'text-rose-400' :
                              issue.severity === 'critical' ? 'text-red-400' :
                              issue.severity === 'warning' ? 'text-amber-400' : 'text-blue-400'
                            }`} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge className={`${style} border text-[9px] px-1.5 uppercase`}>{issue.severity}</Badge>
                                <span className="text-xs font-semibold text-zinc-200">{issue.title}</span>
                              </div>
                              <p className="text-xs text-zinc-400">{issue.detail}</p>
                              <div className="flex items-center gap-3 mt-2">
                                <span className="text-[10px] text-zinc-500">
                                  <Wrench className="w-3 h-3 inline mr-1" />{issue.fix_action}
                                </span>
                                {issue.fix_impact > 0 && (
                                  <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 border text-[10px]">
                                    +{issue.fix_impact} puan
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Section>

              {/* Fix Order */}
              {fixOrder.length > 0 && (
                <Section title="Onerilen Duzeltme Sirasi" icon={ClipboardCheck} iconColor="text-blue-400" testId="readiness-fix-order">
                  <div className="space-y-1.5">
                    {fixOrder.map((fix, i) => (
                      <div key={i} data-testid={`fix-order-${i}`}
                        className="flex items-center gap-3 py-2 px-3 rounded-lg bg-zinc-800/30">
                        <span className="text-xs font-bold text-zinc-500 w-5 text-center">{fix.step}</span>
                        <span className="text-xs text-zinc-300 flex-1">{fix.action}</span>
                        <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 border text-[10px]">{fix.impact}</Badge>
                      </div>
                    ))}
                  </div>
                </Section>
              )}
            </div>

            {/* Score Ring + Breakdown */}
            <div className="space-y-4">
              <Section title="Hazirlik Skoru" icon={Target} iconColor="text-blue-400" testId="readiness-score-section">
                <div className="flex flex-col items-center py-3 gap-3">
                  <ScoreRing score={rs.score || 0} testId="readiness-score-ring" />
                  <Badge className={`text-xs font-bold px-3 py-1 ${
                    rs.is_ready ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40' : 'bg-red-500/15 text-red-400 border-red-500/40'
                  } border`}>
                    {rs.is_ready ? 'PRODUCTION READY' : 'NOT READY'}
                  </Badge>
                </div>
                <div className="space-y-1.5 pt-2 border-t border-zinc-800/50">
                  {Object.entries(rs.scores || {}).map(([key, val]) => (
                    <div key={key} className="flex items-center justify-between py-1">
                      <span className="text-xs text-zinc-400 capitalize">{key.replace(/_/g, ' ')}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${val.score >= val.max ? 'bg-emerald-400' : val.score > 0 ? 'bg-amber-400' : 'bg-red-400'}`}
                            style={{ width: `${val.max > 0 ? (val.score / val.max) * 100 : 0}%` }} />
                        </div>
                        <span className="text-[10px] font-mono text-zinc-500">{val.score}/{val.max}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            </div>
          </div>
        )}

        {/* ═══ TAB: 1-CLICK ACTIONS ═══ */}
        {tab === 'actions' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Retry Safe */}
            <Section title="Retry Safe" icon={RotateCw} iconColor="text-blue-400" testId="action-retry-section">
              <p className="text-xs text-zinc-400 mb-3">
                Basarisiz (retryable) push change set'lerini yeniden deneme icin kuyruga al.
                Idempotent: tekrar calistirmak zarar vermez.
              </p>
              <Button data-testid="action-retry-btn" onClick={() => handleSafeAction('retry-safe')}
                disabled={actionLoading['retry-safe']}
                className="w-full bg-blue-500/15 text-blue-400 border border-blue-500/30 hover:bg-blue-500/25">
                {actionLoading['retry-safe'] ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <RotateCw className="w-4 h-4 mr-2" />}
                Retry Safe
              </Button>
            </Section>

            {/* Revalidate Mapping */}
            <Section title="Mapping Dogrulama" icon={ClipboardCheck} iconColor="text-emerald-400" testId="action-revalidate-section">
              <p className="text-xs text-zinc-400 mb-3">
                Tum provider mapping'lerini bastan dogrula. Hatalilari ve nedenlerini detayli goster.
                Salt okunur islem — hicbir seyi degistirmez.
              </p>
              <Button data-testid="action-revalidate-btn" onClick={() => handleSafeAction('revalidate-mapping', {})}
                disabled={actionLoading['revalidate-mapping']}
                className="w-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25">
                {actionLoading['revalidate-mapping'] ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <ClipboardCheck className="w-4 h-4 mr-2" />}
                Mapping'leri Dogrula
              </Button>
            </Section>

            {/* Suppress Noise */}
            <Section title="Bildirim Susturma" icon={VolumeX} iconColor="text-amber-400" testId="action-suppress-section">
              <p className="text-xs text-zinc-400 mb-3">
                Operasyonel bildirim akisini gecici olarak sustur. Max 120 dakika.
                Idempotent: tekrar calistirmak sureyi uzatir.
              </p>
              <Button data-testid="action-suppress-btn" onClick={() => handleSafeAction('suppress-noise', { duration_minutes: 30 })}
                disabled={actionLoading['suppress-noise']}
                className="w-full bg-amber-500/15 text-amber-400 border border-amber-500/30 hover:bg-amber-500/25">
                {actionLoading['suppress-noise'] ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <VolumeX className="w-4 h-4 mr-2" />}
                30 Dakika Sustur
              </Button>
            </Section>

            {/* Auto-Heal */}
            <Section title="Auto-Heal Calistir" icon={HeartPulse} iconColor="text-violet-400" testId="action-heal-section">
              <p className="text-xs text-zinc-400 mb-3">
                Guvenli auto-heal dongusu calistir. Sadece whitelist'teki drift tipleri heal edilir.
                Her heal evidence kaydi uretir.
              </p>
              <Button data-testid="action-heal-btn" onClick={async () => {
                setActionLoading(prev => ({ ...prev, heal: true }));
                try {
                  const res = await axios.post(`${API}/api/lockdown/runtime/auto-heal/run`, {}, { headers });
                  toast.success(`Auto-heal: ${res.data.healed} healed, ${res.data.failed} failed`);
                  fetchAll();
                } catch { toast.error('Auto-heal calistirilamadi'); }
                finally { setActionLoading(prev => ({ ...prev, heal: false })); }
              }}
                disabled={actionLoading.heal}
                className="w-full bg-violet-500/15 text-violet-400 border border-violet-500/30 hover:bg-violet-500/25">
                {actionLoading.heal ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <HeartPulse className="w-4 h-4 mr-2" />}
                Auto-Heal Calistir
              </Button>
            </Section>
          </div>
        )}

        {/* ═══ TAB: NARROW ROLLOUT ═══ */}
        {tab === 'rollout' && (
          <div className="space-y-4">
            {/* Phase Progress */}
            {phaseProgress.length > 0 && (
              <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
                      <Rocket className="w-4 h-4 text-blue-400" /> Rollout Faz Ilerleme
                    </h3>
                    {!ro.is_active && (
                      <Button data-testid="rollout-init-btn" size="sm" onClick={handleRolloutInit}
                        className="bg-blue-500/15 text-blue-400 border border-blue-500/30 hover:bg-blue-500/25">
                        <Play className="w-3 h-3 mr-1" /> Rollout Baslat
                      </Button>
                    )}
                  </div>
                  <PhaseProgress phases={phaseProgress} testId="rollout-phase-progress" />
                </CardContent>
              </Card>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                {/* Gate Checks */}
                <Section title="Gate Kontrolleri" icon={Shield} iconColor="text-orange-400" testId="rollout-gate-section">
                  {ro.gate_evaluation?.next_phase ? (
                    <>
                      <div className="flex items-center gap-2 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/20 border text-[10px]">{ro.current_phase}</Badge>
                        <ArrowRight className="w-3 h-3 text-zinc-600" />
                        <Badge className="bg-zinc-800 text-zinc-400 border-zinc-700 border text-[10px]">{ro.gate_evaluation.next_phase}</Badge>
                        {ro.gate_evaluation.gate_passed && <CheckCircle className="w-4 h-4 text-emerald-400" />}
                      </div>
                      <div className="space-y-0.5">
                        {gateChecks.map((check, i) => <GateCheck key={i} check={check} />)}
                      </div>
                      {ro.is_active && ro.gate_evaluation.gate_passed && (
                        <Button data-testid="rollout-advance-btn" className="w-full mt-3 bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25"
                          onClick={handleRolloutAdvance}>
                          <Rocket className="w-4 h-4 mr-2" /> Sonraki Faza Gec
                        </Button>
                      )}
                      {ro.is_active && !ro.gate_evaluation.gate_passed && (
                        <div className="mt-3 p-2 rounded bg-red-500/5 border border-red-500/20">
                          <p className="text-[10px] text-red-400">
                            Gate kontrolleri gecmedi — gecis engellidir. Manuel override mevcut degil.
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="flex items-center justify-center gap-2 py-4 text-emerald-500/60">
                      <CheckCircle className="w-4 h-4" /><span className="text-xs">Production fazinda</span>
                    </div>
                  )}
                </Section>

                {/* Phase History */}
                {ro.phase_history?.length > 0 && (
                  <Section title="Faz Gecmisi" icon={Clock} iconColor="text-zinc-400" testId="rollout-history-section">
                    <div className="space-y-1.5">
                      {ro.phase_history.map((ph, i) => (
                        <div key={i} className="flex items-center gap-2 py-1.5 border-b border-zinc-800/30 last:border-0">
                          <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/20 border text-[10px]">{ph.phase}</Badge>
                          <span className="text-[10px] text-zinc-500 font-mono">
                            {ph.started_at ? new Date(ph.started_at).toLocaleDateString('tr-TR') : ''}
                          </span>
                          {ph.gate_results?.length > 0 && (
                            <span className="text-[10px] text-zinc-600">{ph.gate_results.length} gate kontrolu</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </Section>
                )}
              </div>

              {/* Rollout Status Summary */}
              <div className="space-y-4">
                <Section title="Rollout Durumu" icon={Activity} iconColor="text-blue-400" testId="rollout-status-section">
                  <div className="space-y-2">
                    <MetricPill label="Aktif Faz" value={ro.phase_label || 'Baslatilmadi'} testId="rollout-current-phase" />
                    <MetricPill label="Faz Suresi" value={`${ro.phase_duration_hours || 0}h`} testId="rollout-phase-duration" />
                    <MetricPill label="Min Gerekli" value={`${ro.min_duration_hours || 0}h`} testId="rollout-min-duration" />
                    <MetricPill label="Toplam Rollout" value={`${ro.total_rollout_hours || 0}h`} testId="rollout-total-hours" />
                    <MetricPill label="Durum" value={ro.is_active ? 'AKTIF' : 'BASLATILMADI'}
                      good={ro.is_active} testId="rollout-active-status" />
                  </div>
                </Section>

                <Section title="Basari Kriterleri" icon={CheckCircle} iconColor="text-emerald-400" testId="rollout-criteria-section">
                  <div className="space-y-1.5 text-xs text-zinc-400">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                      0 veri kaybi
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                      0 sessiz hata
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                      Tum drift aciklanabilir
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                      Tum incident'lar actionable
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      7 gun kesintisiz basari
                    </div>
                  </div>
                </Section>
              </div>
            </div>
          </div>
        )}

      </div>
    </Layout>
  );
}
