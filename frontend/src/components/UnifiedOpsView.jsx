import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { BarChart, Bar, LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Activity, Shield, AlertTriangle, CheckCircle, XCircle, TrendingUp, TrendingDown, Minus, RefreshCw, Zap, Target, Timer, Gauge, ArrowUpRight, ArrowDownRight, ChevronRight, Layers, GitBranch, Bell, BellRing, AlertOctagon, ShieldAlert, ExternalLink, Cpu, BarChart3 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { SandboxDashboard } from "./SandboxDashboard";
import { SecurityOpsDashboard } from "./SecurityOpsDashboard";
import { CICDPipelineDashboard } from "./CICDPipelineDashboard";
import { useTranslation } from 'react-i18next';

// ─── Style Maps ─────────────────────────────────────────────────
const RATING_STYLES = {
  elite: {
    label: "ELITE",
    cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30"
  },
  high: {
    label: "YÜKSEK",
    cls: "bg-blue-500/15 text-blue-600 border-blue-500/30"
  },
  medium: {
    label: "ORTA",
    cls: "bg-yellow-500/15 text-amber-600 border-yellow-500/30"
  },
  low: {
    label: "DÜŞÜK",
    cls: "bg-red-500/15 text-red-600 border-red-500/30"
  },
  no_data: {
    label: "VERI YOK",
    cls: "bg-gray-200/15 text-gray-600 border-gray-300/30"
  }
};
const ALIGNMENT_STYLES = {
  aligned: {
    label: "HIZALI",
    icon: CheckCircle,
    cls: "text-emerald-600 bg-emerald-500/10 border-emerald-500/30"
  },
  drift_detected: {
    label: "DRIFT",
    icon: AlertTriangle,
    cls: "text-red-600 bg-red-500/10 border-red-500/30"
  },
  stale: {
    label: "BAYAT",
    icon: Timer,
    cls: "text-amber-600 bg-yellow-500/10 border-yellow-500/30"
  },
  no_data: {
    label: "VERI YOK",
    icon: Minus,
    cls: "text-gray-600 bg-gray-200/10 border-gray-300/30"
  }
};
const DRIFT_SEVERITY_STYLES = {
  severe: {
    label: "SEVERE",
    icon: AlertOctagon,
    cls: "bg-red-600/20 text-red-700 border-red-500/50",
    pulse: true
  },
  critical: {
    label: "CRITICAL",
    icon: ShieldAlert,
    cls: "bg-amber-500/20 text-amber-700 border-amber-500/50",
    pulse: true
  },
  warning: {
    label: "WARNING",
    icon: AlertTriangle,
    cls: "bg-yellow-500/15 text-amber-700 border-yellow-500/40",
    pulse: false
  },
  none: {
    label: "TEMIZ",
    icon: CheckCircle,
    cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
    pulse: false
  }
};
const CORRELATION_INFERENCE = {
  positive_correlation: {
    label: "Pozitif Korelasyon",
    icon: TrendingUp,
    cls: "text-emerald-600"
  },
  inverse_correlation: {
    label: "Ters Korelasyon",
    icon: TrendingDown,
    cls: "text-amber-600"
  },
  co_declining: {
    label: "Birlikte Düşüşte",
    icon: TrendingDown,
    cls: "text-red-600"
  },
  insufficient_data: {
    label: "Yetersiz Veri",
    icon: Minus,
    cls: "text-gray-500"
  },
  no_correlation: {
    label: "Korelasyon Yok",
    icon: Minus,
    cls: "text-gray-500"
  },
  improving: {
    label: "İyileşiyor",
    icon: TrendingUp,
    cls: "text-emerald-600"
  },
  stable: {
    label: "Stabil",
    icon: Minus,
    cls: "text-blue-600"
  },
  degrading: {
    label: "Kotulesiyor",
    icon: TrendingDown,
    cls: "text-red-600"
  }
};
function ChartTooltip({
  active,
  payload,
  label
}) {
  const {
    t
  } = useTranslation();
  if (!active || !payload?.length) return null;
  return <div className="bg-white border border-gray-300 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-gray-500 mb-1">{label}</p>
      {payload.map((p, i) => <div key={p.id || i} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{
        backgroundColor: p.color
      }} />
          <span className="text-gray-600">{p.name}:</span>
          <span className="text-gray-900 font-mono font-medium">{p.value}</span>
        </div>)}
    </div>;
}

// ═══════════════════════════════════════════════════════════════════
// TOP ROW: Channel Health + Deploy Health
// ═══════════════════════════════════════════════════════════════════

function ChannelHealthBlock({
  data,
  onDrillDown
}) {
  if (!data) return <Skeleton className="h-40 bg-gray-100" />;
  const style = ALIGNMENT_STYLES[data.alignment_status] || ALIGNMENT_STYLES.no_data;
  const Icon = style.icon;
  const providers = data.provider_breakdown || [];
  return <Card className="bg-white border-gray-200" data-testid="channel-health-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
            <Layers className="h-3.5 w-3.5" /> Channel Health
          </CardTitle>
          <button onClick={() => onDrillDown?.("channel-health")} className="text-gray-500 hover:text-gray-700 transition-colors" data-testid="channel-health-drilldown">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md border ${style.cls}`}>
            <Icon className="h-4 w-4" />
            <span className="text-sm font-bold tracking-wide">{style.label}</span>
          </div>
          <div className="text-xs text-gray-500">
            <span className="text-gray-700 font-mono">{data.connectors_checked}</span> connector
          </div>
          <div className={`px-2 py-0.5 rounded text-[10px] font-mono border ${data.freshness === "fresh" ? "text-emerald-600 border-emerald-500/30 bg-emerald-500/10" : data.freshness === "recent" ? "text-blue-600 border-blue-500/30 bg-blue-500/10" : data.freshness === "stale" ? "text-amber-600 border-yellow-500/30 bg-yellow-500/10" : "text-gray-600 border-gray-300/30 bg-gray-200/10"}`}>
            {(data.freshness || "unknown").toUpperCase()}
          </div>
        </div>

        {data.drift_count > 0 && <div className="bg-red-500/5 border border-red-500/20 rounded-md p-2">
            <div className="flex items-center gap-2 text-xs text-red-600">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span className="font-mono font-bold">{data.drift_count}</span> drift,
              <span className="font-mono font-bold">{data.drift_nights}</span> gece
            </div>
          </div>}

        {providers.length > 0 && <div className="space-y-1">
            {providers.map((p, i) => <div key={p.id || i} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${p.drift_count > 0 ? "bg-red-500" : "bg-emerald-500"}`} />
                  <span className="text-gray-700 font-mono">{p.provider}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">{p.snapshots_checked} kontrol</span>
                  {p.drift_count > 0 ? <Badge variant="outline" className="text-red-600 border-red-500/30 text-[10px] px-1.5 py-0">{p.drift_count} drift</Badge> : <Badge variant="outline" className="text-emerald-600 border-emerald-500/30 text-[10px] px-1.5 py-0">OK</Badge>}
                </div>
              </div>)}
          </div>}
        <div className="text-[10px] text-gray-500">
          {data.inventory_room_type_nights} oda-tip-gece · {data.date_range?.start} — {data.date_range?.end}
        </div>
      </CardContent>
    </Card>;
}
function DeployHealthBlock({
  data,
  onDrillDown
}) {
  if (!data) return <Skeleton className="h-40 bg-gray-100" />;
  const stats = data.environments || {};
  const envList = Object.entries(stats);
  return <Card className="bg-white border-gray-200" data-testid="deploy-health-block">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5" /> Deploy Sagligi
          </CardTitle>
          <button onClick={() => onDrillDown?.("deploys")} className="text-gray-500 hover:text-gray-700 transition-colors" data-testid="deploy-health-drilldown">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {envList.length === 0 ? <div className="text-xs text-gray-500 text-center py-2">Deploy verisi yok</div> : <div className="space-y-2">
            {envList.map(([env, s]) => {
          const rate = s.total > 0 ? Math.round(s.success / s.total * 100) : 0;
          return <div key={env} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-gray-600 border-gray-300 text-[10px] font-mono px-1.5">{env}</Badge>
                    <span className="text-xs text-gray-500">{s.total} deploy</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${rate >= 90 ? "bg-emerald-500" : rate >= 70 ? "bg-yellow-500" : "bg-red-500"}`} style={{
                  width: `${rate}%`
                }} />
                    </div>
                    <span className={`text-xs font-mono font-bold ${rate >= 90 ? "text-emerald-600" : rate >= 70 ? "text-amber-600" : "text-red-600"}`}>{rate}%</span>
                  </div>
                </div>;
        })}
          </div>}
      </CardContent>
    </Card>;
}

// ═══════════════════════════════════════════════════════════════════
// MIDDLE: Live Drift Alerts
// ═══════════════════════════════════════════════════════════════════

function DriftAlertPanel({
  summary,
  alerts,
  onEvaluate,
  onAcknowledge,
  evaluating
}) {
  const {
    t
  } = useTranslation();
  const highest = summary?.highest_severity || "none";
  const style = DRIFT_SEVERITY_STYLES[highest] || DRIFT_SEVERITY_STYLES.none;
  const Icon = style.icon;
  const activeCount = summary?.active_count || 0;
  const bySeverity = summary?.by_severity || {};
  return <Card className={`border ${highest === "severe" ? "border-red-500/50 bg-red-50" : highest === "critical" ? "border-amber-500/40 bg-amber-50" : "bg-white border-gray-200"}`} data-testid="drift-alert-panel">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
            {activeCount > 0 ? <BellRing className={`h-3.5 w-3.5 ${style.pulse ? "animate-pulse" : ""} ${highest === "severe" ? "text-red-600" : highest === "critical" ? "text-amber-600" : "text-amber-600"}`} /> : <Bell className="h-3.5 w-3.5" />}
            Drift Alert Durumu
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="h-6 text-[10px] text-gray-500 hover:text-gray-700" onClick={onEvaluate} disabled={evaluating} data-testid="drift-evaluate-btn">
              {evaluating ? <RefreshCw className="h-3 w-3 mr-1 animate-spin" /> : <Zap className="h-3 w-3 mr-1" />}
              {t('cm.components_UnifiedOpsView.degerlendir')}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md border ${style.cls}`}>
            <Icon className={`h-4 w-4 ${style.pulse ? "animate-pulse" : ""}`} />
            <span className="text-sm font-bold tracking-wide">{style.label}</span>
          </div>
          {activeCount > 0 ? <div className="flex items-center gap-3 text-xs">
              {bySeverity.severe > 0 && <span className="text-red-600 font-mono font-bold">{bySeverity.severe} severe</span>}
              {bySeverity.critical > 0 && <span className="text-amber-600 font-mono font-bold">{bySeverity.critical} critical</span>}
              {bySeverity.warning > 0 && <span className="text-amber-600 font-mono font-bold">{bySeverity.warning} warning</span>}
            </div> : <span className="text-xs text-gray-500">{t('cm.components_UnifiedOpsView.aktif_drift_alarmi_yok')}</span>}
        </div>

        {alerts && alerts.length > 0 && <div className="space-y-2">
            {alerts.slice(0, 5).map((alert, i) => {
          const alertStyle = DRIFT_SEVERITY_STYLES[alert.severity] || DRIFT_SEVERITY_STYLES.warning;
          const AlertIcon = alertStyle.icon;
          const payload = alert.payload || {};
          return <div key={alert.alert_id || i} className={`border rounded-lg p-3 space-y-2 ${alert.severity === "severe" ? "border-red-500/30 bg-red-50" : alert.severity === "critical" ? "border-amber-500/25 bg-amber-50" : "border-yellow-500/20 bg-amber-50"}`} data-testid={`drift-alert-${alert.alert_id}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertIcon className={`h-3.5 w-3.5 ${alert.severity === "severe" ? "text-red-600" : alert.severity === "critical" ? "text-amber-600" : "text-amber-600"}`} />
                      <Badge variant="outline" className={`${alertStyle.cls} text-[9px] px-1.5 py-0 border`}>{alertStyle.label}</Badge>
                      <span className="text-[10px] text-gray-500 font-mono">{alert.fired_at ? new Date(alert.fired_at).toLocaleTimeString("tr-TR") : ""}</span>
                      {alert.auto_action_triggered && <Badge variant="outline" className="text-blue-600 border-blue-500/30 text-[9px] px-1.5 py-0">AUTO-HEAL</Badge>}
                    </div>
                    {!alert.acknowledged && <button onClick={() => onAcknowledge?.(alert.alert_id)} className="text-[10px] text-gray-500 hover:text-gray-700 border border-gray-300 rounded px-2 py-0.5 transition-colors" data-testid={`ack-alert-${alert.alert_id}`}>
                        {t('cm.components_UnifiedOpsView.onayla')}
                      </button>}
                  </div>
                  <p className="text-xs text-gray-700">{alert.reason}</p>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-gray-500 font-mono">
                    {payload.providers?.length > 0 && <span>provider: <span className="text-gray-700">{payload.providers.join(", ")}</span></span>}
                    {payload.drift_count > 0 && <span>drift: <span className="text-red-600">{payload.drift_count}</span></span>}
                    {payload.drift_nights > 0 && <span>gece: <span className="text-red-600">{payload.drift_nights}</span></span>}
                    <span>durum: <span className={payload.drift_or_stale === "stale" ? "text-amber-600" : payload.drift_or_stale === "drift" ? "text-red-600" : "text-gray-600"}>{payload.drift_or_stale}</span></span>
                    {payload.last_reconciliation_result && <span>recon: <span className="text-gray-600">{payload.last_reconciliation_result.status}</span></span>}
                  </div>
                  {payload.runbook_link && <a href={payload.runbook_link} className="inline-flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-700 transition-colors" data-testid={`runbook-link-${alert.alert_id}`}>
                      <ExternalLink className="h-2.5 w-2.5" /> Runbook
                    </a>}
                </div>;
        })}
          </div>}
      </CardContent>
    </Card>;
}

// ═══════════════════════════════════════════════════════════════════
// BOTTOM: KPI Dashboard
// ═══════════════════════════════════════════════════════════════════

function KpiValue({
  label,
  value,
  unit,
  trend,
  trendLabel,
  good,
  testId
}) {
  const isGood = good === undefined ? true : good;
  return <div className="bg-gray-50 border border-gray-200 rounded-lg p-3" data-testid={testId}>
      <div className="text-[10px] text-gray-500 mb-1">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold font-mono text-gray-900">{value}</span>
        {unit && <span className="text-[10px] text-gray-500">{unit}</span>}
      </div>
      {trend !== undefined && <div className={`flex items-center gap-1 mt-1 text-[10px] ${isGood ? "text-emerald-600" : "text-red-600"}`}>
          {isGood ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
          <span className="font-mono">{trendLabel || `${trend > 0 ? "+" : ""}${trend}`}</span>
        </div>}
    </div>;
}
function KpiDashboard({
  kpiData,
  dora,
  correlation,
  onDrillDown
}) {
  const {
    t
  } = useTranslation();
  if (!kpiData && !dora) return <Skeleton className="h-48 bg-gray-100" />;
  const kpis = kpiData?.field_kpis || {};
  const autoActions = kpiData?.auto_actions || {};
  const driftAlerts = kpiData?.drift_alerts || {};
  const driftTrend = kpiData?.drift_trend || [];
  const doraMetrics = dora?.metrics || {};

  // Parse KPI values
  const syncSuccess = kpis.sync_success?.current ?? 100;
  const syncPrev = kpis.sync_success?.previous;
  const mttr = kpis.mttr_hours?.current ?? 0;
  const mttrPrev = kpis.mttr_hours?.previous;
  const driftReduction = kpis.drift_reduction?.current ?? 0;
  const pushSla = kpis.push_sla_compliance?.current ?? 100;
  const correlations = correlation?.correlations || [];
  return <Card className="bg-white border-gray-200" data-testid="kpi-dashboard">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
            <BarChart3 className="h-3.5 w-3.5" /> Operasyonel KPI
          </CardTitle>
          <button onClick={() => onDrillDown?.("channel-health")} className="text-gray-500 hover:text-gray-700 transition-colors" data-testid="kpi-drilldown">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-4">
        {/* KPI Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiValue label="Sync Success" value={typeof syncSuccess === "number" ? syncSuccess.toFixed(1) : syncSuccess} unit="%" trend={syncPrev !== undefined ? parseFloat((syncSuccess - syncPrev).toFixed(1)) : undefined} good={syncPrev === undefined || syncSuccess >= syncPrev} testId="kpi-sync-success" />
          <KpiValue label="MTTR" value={typeof mttr === "number" ? mttr.toFixed(1) : mttr} unit="saat" trend={mttrPrev !== undefined ? parseFloat((mttrPrev - mttr).toFixed(1)) : undefined} trendLabel={mttrPrev !== undefined ? `${mttr < mttrPrev ? "-" : "+"}${Math.abs(mttr - mttrPrev).toFixed(1)}h` : undefined} good={mttrPrev === undefined || mttr <= mttrPrev} testId="kpi-mttr" />
          <KpiValue label="Push SLA" value={typeof pushSla === "number" ? pushSla.toFixed(1) : pushSla} unit="%" good={pushSla >= 95} testId="kpi-push-sla" />
          <KpiValue label="Auto-Heal" value={autoActions.total || 0} unit={autoActions.total > 0 ? `(${autoActions.success_rate}%)` : ""} good={autoActions.failed === 0} testId="kpi-auto-heal" />
        </div>

        {/* DORA mini metrics */}
        {doraMetrics.deployment_frequency && <div className="grid grid-cols-4 gap-2">
            {[{
          key: "deployment_frequency",
          label: "Deploy Frekans",
          unit: doraMetrics.deployment_frequency?.unit || ""
        }, {
          key: "change_failure_rate",
          label: "Hata %",
          unit: "%"
        }, {
          key: "mttr",
          label: "MTTR",
          unit: "dk"
        }, {
          key: "lead_time",
          label: "Lead Time",
          unit: "dk"
        }].map(({
          key,
          label,
          unit
        }) => {
          const m = doraMetrics[key] || {};
          const r = RATING_STYLES[m.rating] || RATING_STYLES.no_data;
          return <div key={key} className="bg-gray-50 border border-gray-200 rounded-lg p-2" data-testid={`dora-${key}`}>
                  <div className="text-[9px] text-gray-500">{label}</div>
                  <div className="text-sm font-bold font-mono text-gray-900">{m.value ?? 0}<span className="text-[9px] text-gray-500 ml-0.5">{unit}</span></div>
                  <Badge variant="outline" className={`${r.cls} text-[8px] px-1 py-0 mt-0.5 border`}>{r.label}</Badge>
                </div>;
        })}
          </div>}

        {/* Drift Trend Chart */}
        {driftTrend.length > 0 && <div>
            <div className="text-[10px] text-gray-500 mb-1">Drift Trend</div>
            <div className="h-16">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={driftTrend.slice(-20)}>
                  <defs>
                    <linearGradient id="driftGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="drift_records" stroke="#ef4444" fill="url(#driftGrad)" strokeWidth={1.5} />
                  <Tooltip content={<ChartTooltip />} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>}

        {/* Correlation insights */}
        {correlations.length > 0 && <div className="space-y-1.5">
            <div className="text-[10px] text-gray-500">DORA x Kanal Korelasyonu</div>
            {correlations.slice(0, 3).map((c, i) => {
          const inf = CORRELATION_INFERENCE[c.inference] || CORRELATION_INFERENCE.insufficient_data;
          const InfIcon = inf.icon;
          return <div key={c.id || i} className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg px-3 py-2" data-testid={`correlation-${c.name}`}>
                  <span className="text-[10px] text-gray-600 truncate mr-2">{c.question}</span>
                  <div className={`flex items-center gap-1 text-[10px] ${inf.cls} whitespace-nowrap`}>
                    <InfIcon className="h-3 w-3" />
                    <span className="font-medium">{inf.label}</span>
                  </div>
                </div>;
        })}
          </div>}

        {/* Active alerts summary */}
        <div className="flex items-center justify-between text-[10px] text-gray-500">
          <span>{t('cm.components_UnifiedOpsView.aktif_alarm')} <span className="text-gray-600 font-mono">{driftAlerts.active_count || 0}</span></span>
          <span>{t('cm.components_UnifiedOpsView.en_yuksek')} <span className={`font-mono ${driftAlerts.highest_severity === "severe" ? "text-red-600" : driftAlerts.highest_severity === "critical" ? "text-amber-600" : driftAlerts.highest_severity === "warning" ? "text-amber-600" : "text-emerald-600"}`}>{driftAlerts.highest_severity || "none"}</span></span>
          <span>Auto-heal basari: <span className="text-gray-600 font-mono">{autoActions.success_rate ?? 100}%</span></span>
        </div>
      </CardContent>
    </Card>;
}

// ═══════════════════════════════════════════════════════════════════
// MAIN: Unified Ops View
// ═══════════════════════════════════════════════════════════════════

export function UnifiedOpsView() {
  const {
    t
  } = useTranslation();
  const [alignment, setAlignment] = useState(null);
  const [dora, setDora] = useState(null);
  const [correlation, setCorrelation] = useState(null);
  const [deployStats, setDeployStats] = useState(null);
  const [driftSummary, setDriftSummary] = useState(null);
  const [driftAlerts, setDriftAlerts] = useState([]);
  const [kpiData, setKpiData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [alignRes, doraRes, corrRes, statsRes, driftSumRes, driftAlertsRes, kpiRes] = await Promise.allSettled([axios.get("/ops/dashboard/inventory-alignment"), axios.get("/ops/dashboard/dora-metrics"), axios.get("/ops/dashboard/dora-correlation"), axios.get("/ops/dashboard/deploy-stats"), axios.get("/ops/dashboard/drift-alerts/summary"), axios.get("/ops/dashboard/drift-alerts?acknowledged=false&limit=10"), axios.get("/ops/dashboard/ops-kpis")]);
      if (alignRes.status === "fulfilled") setAlignment(alignRes.value.data);
      if (doraRes.status === "fulfilled") setDora(doraRes.value.data);
      if (corrRes.status === "fulfilled") setCorrelation(corrRes.value.data);
      if (statsRes.status === "fulfilled") setDeployStats(statsRes.value.data);
      if (driftSumRes.status === "fulfilled") setDriftSummary(driftSumRes.value.data);
      if (driftAlertsRes.status === "fulfilled") setDriftAlerts(driftAlertsRes.value.data?.alerts || []);
      if (kpiRes.status === "fulfilled") setKpiData(kpiRes.value.data);
    } catch (err) {
      toast.error("Ops verisi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);
  const handleEvaluate = useCallback(async () => {
    setEvaluating(true);
    try {
      const res = await axios.post("/ops/dashboard/drift-alerts/evaluate");
      const data = res.data;
      if (data.alerts_fired?.length > 0) {
        const hasAutoAction = data.alerts_fired.some(a => a.auto_action_triggered);
        toast.warning(`${data.alerts_fired.length} drift alarmi tetiklendi!${hasAutoAction ? " Auto-heal basladi." : ""}`);
      } else {
        toast.success("Drift degerlendirmesi tamamlandi — yeni alarm yok");
      }
      const [sumRes, alertsRes, kpiRes] = await Promise.allSettled([axios.get("/ops/dashboard/drift-alerts/summary"), axios.get("/ops/dashboard/drift-alerts?acknowledged=false&limit=10"), axios.get("/ops/dashboard/ops-kpis")]);
      if (sumRes.status === "fulfilled") setDriftSummary(sumRes.value.data);
      if (alertsRes.status === "fulfilled") setDriftAlerts(alertsRes.value.data?.alerts || []);
      if (kpiRes.status === "fulfilled") setKpiData(kpiRes.value.data);
    } catch (err) {
      toast.error("Drift degerlendirmesi başarısız");
    } finally {
      setEvaluating(false);
    }
  }, []);
  const handleAcknowledge = useCallback(async alertId => {
    try {
      await axios.post(`/ops/dashboard/drift-alerts/${alertId}/acknowledge`);
      toast.success("Alarm onaylandi");
      setDriftAlerts(prev => prev.filter(a => a.alert_id !== alertId));
      setDriftSummary(prev => prev ? {
        ...prev,
        active_count: Math.max(0, (prev.active_count || 0) - 1)
      } : prev);
    } catch (err) {
      toast.error("Alarm onaylanamadi");
    }
  }, []);
  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60000);
    return () => clearInterval(interval);
  }, [fetchAll]);
  const handleDrillDown = tab => {
    const tabEl = document.querySelector(`[data-testid="tab-${tab}"]`);
    if (tabEl) tabEl.click();
  };
  return <div className="space-y-4" data-testid="unified-ops-view">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Unified Ops View</h2>
          <p className="text-[10px] text-gray-500 mt-0.5">{t('cm.components_UnifiedOpsView.tek_ekran_kanal_sagligi_deploy_drift_ale')}</p>
        </div>
        <Button variant="ghost" size="sm" className="h-7 text-xs text-gray-500" onClick={fetchAll} disabled={loading} data-testid="ops-refresh">
          <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} /> {t('cm.components_UnifiedOpsView.yenile')}
        </Button>
      </div>

      {/* TOP: Channel Health + Deploy Health */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChannelHealthBlock data={alignment} onDrillDown={handleDrillDown} />
        <DeployHealthBlock data={deployStats} onDrillDown={handleDrillDown} />
      </div>

      {/* MIDDLE: Live Drift Alerts */}
      <DriftAlertPanel summary={driftSummary} alerts={driftAlerts} onEvaluate={handleEvaluate} onAcknowledge={handleAcknowledge} evaluating={evaluating} />

      {/* BOTTOM: KPI Dashboard */}
      <KpiDashboard kpiData={kpiData} dora={dora} correlation={correlation} onDrillDown={handleDrillDown} />

      {/* CI/CD: 3-Tier Pipeline Validation */}
      <CICDPipelineDashboard />

      {/* SANDBOX: Resilience Dashboard */}
      <SandboxDashboard />

      {/* SECURITY: SEC-001 + SEC-002 Operations */}
      <SecurityOpsDashboard />
    </div>;
}