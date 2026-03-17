import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
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
  ChevronRight
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Severity badge colors ───────────────────────────────────
const SEVERITY_STYLE = {
  info: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  warning: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
  blocker: 'bg-rose-600/20 text-rose-400 border-rose-500/40 animate-pulse',
};

// ─── Metric Pill ─────────────────────────────────────────────
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

// ─── Status Indicator ────────────────────────────────────────
const StatusLight = ({ active, label, testId }) => (
  <div data-testid={testId} className="flex items-center gap-2">
    <span className={`w-2.5 h-2.5 rounded-full ${
      active ? 'bg-emerald-500 shadow-emerald-500/50 shadow-lg' : 'bg-zinc-600'
    }`} />
    <span className="text-xs text-zinc-400">{label}</span>
  </div>
);

// ─── Section Card ────────────────────────────────────────────
const Section = ({ title, icon: Icon, iconColor, children, testId }) => (
  <Card data-testid={testId} className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
    <CardHeader className="pb-3 pt-4 px-4">
      <CardTitle className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
        <Icon className={`w-4 h-4 ${iconColor}`} />
        {title}
      </CardTitle>
    </CardHeader>
    <CardContent className="px-4 pb-4 space-y-1.5">
      {children}
    </CardContent>
  </Card>
);

// ─── Quarantine Age Bucket ───────────────────────────────────
const AgeBucket = ({ label, count, color }) => (
  <div className="flex items-center justify-between">
    <span className="text-xs text-zinc-500">{label}</span>
    <Badge className={`${color} border text-[10px] px-1.5 font-mono`}>
      {count}
    </Badge>
  </div>
);

// ─── Event Row ───────────────────────────────────────────────
const EventRow = ({ event }) => {
  const style = SEVERITY_STYLE[event.severity] || SEVERITY_STYLE.info;
  const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '';
  return (
    <div data-testid={`event-row-${event.id}`} className="flex items-center gap-2 py-1.5 border-b border-zinc-800/40 last:border-0">
      <Badge className={`${style} border text-[9px] px-1.5 uppercase`}>
        {event.severity}
      </Badge>
      <span className="text-xs text-zinc-300 flex-1 truncate">
        {event.description}
      </span>
      <span className="text-[10px] text-zinc-600 font-mono">{time}</span>
    </div>
  );
};

export default function RuntimeCockpitPage({ user, tenant, onLogout }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cockpit, setCockpit] = useState(null);
  const [events, setEvents] = useState([]);
  const [eventSummary, setEventSummary] = useState(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    try {
      const [cRes, eRes, sRes] = await Promise.allSettled([
        axios.get(`${API}/api/lockdown/runtime/cockpit`, { headers }),
        axios.get(`${API}/api/lockdown/notifications/events?limit=10`, { headers }),
        axios.get(`${API}/api/lockdown/notifications/summary`, { headers }),
      ]);
      if (cRes.status === 'fulfilled') setCockpit(cRes.value.data);
      if (eRes.status === 'fulfilled') setEvents(eRes.value.data.events || []);
      if (sRes.status === 'fulfilled') setEventSummary(sRes.value.data);
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
    } catch {
      toast.error('Evaluation failed');
    }
  };

  const handlePushLoopAction = async (action) => {
    try {
      await axios.post(`${API}/api/lockdown/runtime/push-loop/${action}`, {}, { headers });
      toast.success(`Push loop: ${action}`);
      setTimeout(fetchAll, 500);
    } catch {
      toast.error(`Push loop ${action} failed`);
    }
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
            <Button
              data-testid="cockpit-evaluate-btn"
              variant="outline"
              size="sm"
              onClick={handleEvaluate}
              className="border-zinc-700 text-zinc-400 hover:text-zinc-100"
            >
              <Bell className="w-3.5 h-3.5 mr-1" />
              Evaluate
            </Button>
            <Button
              data-testid="cockpit-refresh-btn"
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="border-zinc-700 text-zinc-400 hover:text-zinc-100"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </div>

        {/* ═══ A) HEALTH SUMMARY (TOP BAR) ═══ */}
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
              <p data-testid="health-incidents" className={`text-lg font-bold mt-0.5 ${h.active_incidents > 0 ? 'text-amber-400' : 'text-zinc-300'}`}>
                {h.active_incidents || 0}
              </p>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
            <CardContent className="p-3 text-center">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Quarantine</p>
              <p data-testid="health-quarantine" className={`text-lg font-bold mt-0.5 ${h.quarantine_count > 0 ? 'text-red-400' : 'text-zinc-300'}`}>
                {h.quarantine_count || 0}
              </p>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
            <CardContent className="p-3 text-center">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Verify %</p>
              <p data-testid="health-verify-pct" className={`text-lg font-bold mt-0.5 ${h.verify_success_pct >= 95 ? 'text-emerald-400' : h.verify_success_pct > 0 ? 'text-amber-400' : 'text-zinc-300'}`}>
                {h.verify_success_pct || 0}%
              </p>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
            <CardContent className="p-3 text-center">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Push Loop</p>
              <p data-testid="health-push-loop" className={`text-lg font-bold mt-0.5 ${
                h.push_loop_status === 'running' ? 'text-emerald-400' :
                h.push_loop_status === 'paused' ? 'text-amber-400' : 'text-zinc-300'
              }`}>
                {(h.push_loop_status || 'stopped').toUpperCase()}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* ═══ MAIN GRID: B+C left, D+E right ═══ */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* ── LEFT COLUMN: Flow + Reliability ──── */}
          <div className="lg:col-span-2 space-y-4">

            {/* B) FLOW METRICS */}
            <Section title="Flow Metrics" icon={ArrowUpDown} iconColor="text-blue-400" testId="cockpit-flow-section">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <MetricPill label="Queued" value={flow.queued || 0} testId="flow-queued" />
                <MetricPill label="Coalesced" value={flow.coalesced || 0} testId="flow-coalesced" />
                <MetricPill label="Emitted" value={flow.emitted || 0} good={flow.emitted > 0} testId="flow-emitted" />
                <MetricPill label="Dropped" value={flow.dropped || 0} testId="flow-dropped" />
                <MetricPill label="Hard Fail Blocked" value={flow.hard_fail_blocked || 0} alert={flow.hard_fail_blocked > 0} testId="flow-hard-fail" />
                <MetricPill label="Cycles" value={flow.cycle_count || 0} testId="flow-cycles" />
              </div>
              {/* Push Loop Controls */}
              <div className="flex items-center gap-2 mt-3 pt-3 border-t border-zinc-800/50">
                <span className="text-xs text-zinc-500 mr-2">Push Loop:</span>
                <Button
                  data-testid="push-loop-start-btn"
                  variant="outline" size="sm"
                  onClick={() => handlePushLoopAction('start')}
                  className="border-zinc-700 text-emerald-400 hover:bg-emerald-500/10 h-7 px-2 text-xs"
                >
                  <Play className="w-3 h-3 mr-1" /> Start
                </Button>
                <Button
                  data-testid="push-loop-pause-btn"
                  variant="outline" size="sm"
                  onClick={() => handlePushLoopAction('pause')}
                  className="border-zinc-700 text-amber-400 hover:bg-amber-500/10 h-7 px-2 text-xs"
                >
                  <Pause className="w-3 h-3 mr-1" /> Pause
                </Button>
                <Button
                  data-testid="push-loop-stop-btn"
                  variant="outline" size="sm"
                  onClick={() => handlePushLoopAction('stop')}
                  className="border-zinc-700 text-red-400 hover:bg-red-500/10 h-7 px-2 text-xs"
                >
                  <Square className="w-3 h-3 mr-1" /> Stop
                </Button>
              </div>
            </Section>

            {/* C) RELIABILITY */}
            <Section title="Reliability" icon={HeartPulse} iconColor="text-emerald-400" testId="cockpit-reliability-section">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <MetricPill
                  label="Verify Success Ratio"
                  value={`${(rel.verify_success_ratio * 100).toFixed(1)}%`}
                  good={rel.verify_success_ratio >= 0.95}
                  alert={rel.verify_success_ratio < 0.8 && rel.verify_success_count + rel.verify_fail_count > 0}
                  testId="rel-verify-ratio"
                />
                <MetricPill label="Verify OK" value={rel.verify_success_count || 0} good testId="rel-verify-ok" />
                <MetricPill label="Verify FAIL" value={rel.verify_fail_count || 0} alert={rel.verify_fail_count > 0} testId="rel-verify-fail" />
                <MetricPill label="Dead Letters" value={rel.dead_letters || 0} alert={rel.dead_letters > 0} testId="rel-dead-letters" />
                <MetricPill label="Cycle Duration" value={`${rel.last_cycle_duration_ms || 0}ms`} testId="rel-cycle-ms" />
                <MetricPill
                  label="Ack Latency"
                  value={Object.keys(rel.provider_ack_latency_avg_ms || {}).length > 0
                    ? Object.entries(rel.provider_ack_latency_avg_ms).map(([p, v]) => `${p}: ${v}ms`).join(', ')
                    : 'N/A'
                  }
                  testId="rel-ack-latency"
                />
              </div>
            </Section>

            {/* D) DRIFT & HEAL */}
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

          {/* ── RIGHT COLUMN: Quarantine + Events ── */}
          <div className="space-y-4">

            {/* E) QUARANTINE VISIBILITY */}
            <Section title="Quarantine" icon={Lock} iconColor="text-red-400" testId="cockpit-quarantine-section">
              <div className="text-center py-2">
                <p data-testid="quarantine-total" className={`text-3xl font-bold ${q.total_quarantined > 0 ? 'text-red-400' : 'text-zinc-500'}`}>
                  {q.total_quarantined || 0}
                </p>
                <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Quarantined Items</p>
              </div>

              {q.total_quarantined > 0 && (
                <>
                  {/* Classification */}
                  <div className="pt-2 border-t border-zinc-800/50">
                    <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5">Classification</p>
                    {Object.entries(q.by_classification || {}).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between py-0.5">
                        <span className="text-xs text-zinc-400">{type.replace(/_/g, ' ')}</span>
                        <span className="text-xs font-mono text-zinc-300">{count}</span>
                      </div>
                    ))}
                  </div>

                  {/* Age Buckets */}
                  <div className="pt-2 border-t border-zinc-800/50">
                    <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5">Age Distribution</p>
                    <AgeBucket label="< 5 min" count={ageBuckets.lt_5min || 0} color="bg-emerald-500/15 text-emerald-400 border-emerald-500/30" />
                    <AgeBucket label="5-30 min" count={ageBuckets['5_30min'] || 0} color="bg-amber-500/15 text-amber-400 border-amber-500/30" />
                    <AgeBucket label="30-120 min" count={ageBuckets['30_120min'] || 0} color="bg-orange-500/15 text-orange-400 border-orange-500/30" />
                    <AgeBucket label="> 2 hours" count={ageBuckets.gt_2h || 0} color="bg-red-500/15 text-red-400 border-red-500/30" />
                  </div>

                  {/* Provider breakdown */}
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
                  <CheckCircle className="w-4 h-4" />
                  <span className="text-xs">No quarantined items</span>
                </div>
              )}
            </Section>

            {/* F) NOTIFICATION EVENTS */}
            <Section title="Recent Events" icon={Bell} iconColor="text-amber-400" testId="cockpit-events-section">
              {eventSummary && (
                <div className="grid grid-cols-4 gap-1 mb-2">
                  {['info', 'warning', 'critical', 'blocker'].map((sev) => (
                    <div key={sev} className="text-center">
                      <p className="text-[10px] text-zinc-600 uppercase">{sev}</p>
                      <p className={`text-sm font-bold ${
                        sev === 'blocker' ? 'text-rose-400' :
                        sev === 'critical' ? 'text-red-400' :
                        sev === 'warning' ? 'text-amber-400' : 'text-blue-400'
                      }`}>
                        {eventSummary.by_severity?.[sev] || 0}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              <div className="space-y-0.5 max-h-[300px] overflow-y-auto">
                {events.length === 0 ? (
                  <p className="text-xs text-zinc-600 text-center py-3">No events yet</p>
                ) : (
                  events.map((evt) => <EventRow key={evt.id} event={evt} />)
                )}
              </div>
            </Section>

            {/* G) HARD FAIL SUMMARY */}
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
      </div>
    </Layout>
  );
}
