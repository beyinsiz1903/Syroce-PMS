import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { io } from "socket.io-client";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";

import {
  Activity, Shield, Server, AlertTriangle, RefreshCw, CheckCircle2,
  XCircle, Clock, Wifi, WifiOff, Lock, Eye, ArrowLeft, Loader2,
  Database, Radio, Zap, TrendingUp, TrendingDown, Minus, Users, Building2, Layers, Network
} from "lucide-react";

const API = "";

/* ── Tiny Reusable Components ─────────────────────────── */

function StatusBadge({ status }) {
  const map = {
    healthy: { label: "Healthy", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
    degraded: { label: "Degraded", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
    critical: { label: "Critical", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
    warning: { label: "Warning", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
    active: { label: "Active", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
    ok: { label: "OK", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
    unknown: { label: "Unknown", cls: "bg-gray-100 text-gray-600 border-gray-200" },
  };
  const m = map[status] || { label: status || "Unknown", cls: "bg-gray-100 text-gray-600 border-gray-200" };
  return <Badge data-testid={`status-badge-${status}`} variant="outline" className={`${m.cls} text-xs font-mono`}>{m.label}</Badge>;
}

function SeverityChip({ severity }) {
  const map = {
    critical: "bg-red-500/20 text-red-300 border-red-500/40",
    high: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    warning: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    info: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  };
  return (
    <span data-testid={`severity-chip-${severity}`} className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${map[severity] || map.info}`}>
      {severity}
    </span>
  );
}

function MetricCard({ icon: Icon, title, value, sub, testId }) {
  return (
    <div data-testid={testId} className="bg-white border border-gray-200 rounded-lg p-4 flex items-start gap-3">
      <div className="p-2 rounded-md bg-gray-50"><Icon className="w-4 h-4 text-gray-600" /></div>
      <div>
        <p className="text-xs text-gray-600 mb-0.5">{title}</p>
        <p className="text-lg font-semibold text-gray-900 leading-none">{value}</p>
        {sub && <p className="text-[11px] text-gray-600 mt-1">{sub}</p>}
      </div>
    </div>
  );
}

function PanelCard({ title, icon: Icon, children, status, onAction, actionLabel, actionLoading, testId, permissionGated }) {
  return (
    <Card data-testid={testId} className="bg-white border-gray-200 shadow-lg">
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-gray-600" />
          <CardTitle className="text-sm font-semibold text-gray-900">{title}</CardTitle>
        </div>
        <div className="flex items-center gap-2">
          {status && <StatusBadge status={status} />}
          {onAction && !permissionGated && (
            <Button data-testid={testId ? `${testId}-action` : `action-${title.toLowerCase().replace(/\s+/g, "-")}`}
              size="sm" variant="outline"
              className="h-7 text-xs border-gray-200 bg-white hover:bg-gray-50 text-gray-700"
              onClick={onAction} disabled={actionLoading}>
              {actionLoading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
              {actionLabel || "Scan"}
            </Button>
          )}
          {permissionGated && (
            <span className="text-[10px] text-gray-600 flex items-center gap-1"><Lock className="w-3 h-3" /> View Only</span>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  );
}

function EmptyState({ icon: Icon, message }) {
  return (
    <div data-testid="empty-state" className="flex flex-col items-center justify-center py-6 text-gray-600">
      <Icon className="w-6 h-6 mb-2 opacity-50" />
      <span className="text-xs">{message}</span>
    </div>
  );
}

function ScopeBanner({ role, scope }) {
  const roleConfig = {
    superadmin: { icon: Layers, color: "text-violet-400", bg: "bg-violet-500/8 border-violet-500/20", label: "Superadmin - Global" },
    admin: { icon: Building2, color: "text-sky-400", bg: "bg-sky-500/8 border-sky-500/20", label: "Admin - Tenant Scope" },
    gm: { icon: Users, color: "text-amber-400", bg: "bg-amber-500/8 border-amber-500/20", label: "GM - Property Scope" },
  };
  const cfg = roleConfig[role] || roleConfig.admin;
  const RIcon = cfg.icon;
  return (
    <div data-testid="scope-banner" className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium border ${cfg.bg}`}>
      <RIcon className={`w-3 h-3 ${cfg.color}`} />
      <span className={cfg.color}>{cfg.label}</span>
      {scope && <span className="text-gray-600 ml-1">({scope})</span>}
    </div>
  );
}

/* ── Row Helper ─────────────────────────────────────────── */
function DataRow({ label, value, valueClass }) {
  return (
    <div className="flex justify-between text-gray-600">
      <span>{label}</span>
      <span className={valueClass || "text-gray-900"}>{value}</span>
    </div>
  );
}

/* ── WS Bridge — Mini sparkline for the rolling 1h error trend ─ */
function ErrorSparkline({ points, testId }) {
  // Renders ``publish_errors_delta`` (errors per snapshot interval)
  // as a tiny SVG polyline. We use a simple linear scale so a single
  // tall spike is still clearly visible. When all values are zero the
  // line collapses onto the baseline, which is exactly what we want
  // (operators read "flat at zero" as healthy).
  const series = Array.isArray(points) ? points : [];
  if (series.length < 2) {
    return (
      <div
        data-testid={`${testId}-empty`}
        className="text-[11px] text-gray-400 italic"
      >
        Trend için yeterli veri yok (≥2 örnek gerekli)
      </div>
    );
  }
  const W = 220;
  const H = 36;
  const PAD = 2;
  const values = series.map((p) => Math.max(0, Number(p.publish_errors_delta) || 0));
  const max = Math.max(1, ...values); // avoid /0; floor at 1 so empty series sits flat at the bottom
  const stepX = (W - PAD * 2) / Math.max(1, values.length - 1);
  const coords = values.map((v, i) => {
    const x = PAD + i * stepX;
    const y = H - PAD - (v / max) * (H - PAD * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const linePath = coords.join(" ");
  // Translucent fill under the line for readability
  const areaPath = `${PAD},${H - PAD} ${linePath} ${(W - PAD).toFixed(1)},${H - PAD}`;
  const peakValue = max;
  return (
    <svg
      data-testid={testId}
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      role="img"
      aria-label={`Son ${series.length} örnekte zirve hata sayısı ${peakValue}`}
      className="block"
    >
      <polyline points={areaPath} fill="rgba(239,68,68,0.12)" stroke="none" />
      <polyline
        points={linePath}
        fill="none"
        stroke="rgb(220,38,38)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ── WS Bridge (Multi-Instance Live Chat) Panel ─────────── */
function WSBridgePanel({ wsBridge, testIdPrefix = "ws-bridge" }) {
  if (!wsBridge) return null;
  const detail = wsBridge.detail || {};
  const status = wsBridge.status || "unknown";
  const errors = detail.publish_errors ?? 0;
  const threshold = detail.publish_error_threshold ?? 10;
  const errorsClass = errors >= threshold ? "text-red-400" : (errors > 0 ? "text-amber-400" : "text-gray-900");
  const lastErrAt = detail.last_publish_error_at
    ? new Date(detail.last_publish_error_at).toLocaleString()
    : null;
  const mode = detail.single_instance_mode
    ? "Single instance (Redis disabled)"
    : (detail.active ? "Active (Redis pub/sub)" : "Inactive");

  // Task #47 — rolling history for the sparkline + trend chip.
  const history = detail.metrics_history || {};
  const points = Array.isArray(history.points) ? history.points : [];
  const trend = history.error_trend || "flat";
  const errorsInWindow = history.errors_in_window ?? 0;
  const intervalMin = Math.max(
    1,
    Math.round((history.interval_seconds ?? 60) / 60),
  );
  const windowMin = points.length * intervalMin;
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;
  const trendClass =
    trend === "up"
      ? "text-red-600"
      : trend === "down"
        ? "text-emerald-600"
        : "text-gray-500";
  const trendLabel =
    trend === "up"
      ? "Hata oranı yükseliyor"
      : trend === "down"
        ? "Hata oranı düşüyor"
        : "Hata oranı sabit";

  return (
    <PanelCard
      testId={`${testIdPrefix}-panel`}
      title="Multi-Instance Chat Bridge"
      icon={Network}
      status={status}
    >
      <div className="space-y-2 text-xs">
        <DataRow label="Mode" value={mode} />
        {detail.instance_id && <DataRow label="Instance" value={detail.instance_id} />}
        <DataRow label="Active Channels" value={detail.channels_active ?? 0} />
        <DataRow label="Messages Published" value={detail.messages_published ?? 0} />
        <DataRow label="Messages Received" value={detail.messages_received ?? 0} />
        <DataRow label="Messages Forwarded" value={detail.messages_forwarded ?? 0} />
        <DataRow
          label={`Publish Errors (≥${threshold} alerts)`}
          value={errors}
          valueClass={errorsClass}
        />

        {/* Sparkline / trend block */}
        <div
          data-testid={`${testIdPrefix}-trend`}
          className="mt-2 p-2 rounded border border-gray-200 bg-gray-50/60"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-semibold text-gray-700">
              Son {windowMin || 0} dk hata trendi
            </span>
            <span
              data-testid={`${testIdPrefix}-trend-chip`}
              className={`inline-flex items-center gap-1 text-[11px] font-medium ${trendClass}`}
              title={trendLabel}
              aria-label={trendLabel}
            >
              <TrendIcon className="w-3.5 h-3.5" />
              {trend === "up" ? "Artıyor" : trend === "down" ? "Azalıyor" : "Sabit"}
            </span>
          </div>
          <ErrorSparkline points={points} testId={`${testIdPrefix}-sparkline`} />
          <div className="mt-1 flex items-center justify-between text-[10px] text-gray-500">
            <span>{points.length} örnek</span>
            <span>Pencerede {errorsInWindow} hata</span>
          </div>
        </div>

        {detail.last_publish_error && (
          <div data-testid={`${testIdPrefix}-last-error`} className="mt-2 p-2 rounded bg-red-50 border border-red-200">
            <p className="text-[11px] font-semibold text-red-700">Last publish error</p>
            <p className="text-[11px] text-red-600 break-all">{detail.last_publish_error}</p>
            {lastErrAt && <p className="text-[10px] text-red-500/80 mt-0.5">{lastErrAt}</p>}
          </div>
        )}
        {wsBridge.degraded_reason && (
          <p data-testid={`${testIdPrefix}-degraded`} className="text-[11px] text-amber-500/90">
            {wsBridge.degraded_reason}
          </p>
        )}
        {wsBridge.suggested_action && (
          <p className="text-[11px] text-sky-500/80">{wsBridge.suggested_action}</p>
        )}
      </div>
    </PanelCard>
  );
}

/* ── Room Service Live Connections Panel (Task #92) ─────── */
function RoomServiceLivePanel({ roomService, testIdPrefix = "room-service" }) {
  if (!roomService) return null;
  const detail = roomService.detail || {};
  const status = roomService.status || "healthy";
  const bookings = detail.active_bookings_local ?? 0;
  const guestSockets = detail.guest_sockets_local ?? 0;
  const staffTenants = detail.staff_tenants_local ?? 0;
  const staffSockets = detail.staff_sockets_local ?? 0;
  const eventsLastHour = detail.events_last_hour ?? 0;
  const windowSec = detail.event_window_seconds ?? 3600;
  const windowMin = Math.max(1, Math.round(windowSec / 60));
  const bridgeActive = !!detail.bridge_active;
  const bridgeChannels = detail.bridge_room_service_channels ?? 0;

  return (
    <PanelCard
      testId={`${testIdPrefix}-panel`}
      title="Oda servisi canlı bağlantıları"
      icon={Radio}
      status={status}
    >
      <div className="space-y-2 text-xs">
        <DataRow
          label="Aktif rezervasyonlar (bu pod)"
          value={bookings}
        />
        <DataRow
          label="Misafir soketleri"
          value={guestSockets}
        />
        <DataRow
          label="Personel panelleri (kiracı)"
          value={`${staffTenants} kiracı / ${staffSockets} soket`}
        />
        <DataRow
          label={`Son ${windowMin} dk teslim edilen güncelleme`}
          value={eventsLastHour}
          valueClass={eventsLastHour > 0 ? "text-emerald-600" : "text-gray-900"}
        />
        <p className="text-[10px] text-gray-500 -mt-1">
          (her misafir/personel ekranına teslim her güncelleme bir kez sayılır)
        </p>
        <div className="flex justify-between text-gray-600">
          <span>Çoklu sunucu köprüsü</span>
          <StatusBadge status={bridgeActive ? "active" : "unknown"} />
        </div>
        <DataRow
          label="Köprüde room_service kanalı"
          value={bridgeChannels}
        />
        {roomService.evidence_summary && (
          <p className="text-[11px] text-gray-500 mt-1">{roomService.evidence_summary}</p>
        )}
      </div>
    </PanelCard>
  );
}

/* ── GM Property Panel ──────────────────────────────────── */
function GMPropertyView({ cmStatus, alerts, normalizedOverview }) {
  const alertCount = alerts?.count || 0;
  const criticalAlerts = alerts?.critical || 0;
  const driftActive = cmStatus?.drift?.active_drifts || 0;

  return (
    <div data-testid="gm-property-view" className="space-y-4">
      {/* Property Status Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard testId="gm-metric-cm" icon={Wifi} title="Channel Sync" value={cmStatus?.health || "N/A"} sub={`${cmStatus?.active_connections || 0} active`} />
        <MetricCard testId="gm-metric-drift" icon={AlertTriangle} title="Drift Issues" value={driftActive} sub={driftActive > 0 ? "Needs review" : "In sync"} />
        <MetricCard testId="gm-metric-alerts" icon={AlertTriangle} title="Alerts" value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} critical` : "Clear"} />
        <MetricCard testId="gm-metric-recon" icon={CheckCircle2} title="Reconciliation" value={cmStatus?.reconciliation?.status || "OK"} sub={cmStatus?.reconciliation?.unresolved_issues > 0 ? `${cmStatus.reconciliation.unresolved_issues} issues` : "Resolved"} />
      </div>

      {/* CM Property Details */}
      <PanelCard testId="gm-panel-cm" title="Channel Manager (Property)" icon={Wifi} status={cmStatus?.health} permissionGated>
        <div className="space-y-2 text-xs">
          <DataRow label="Sync Status" value={cmStatus?.sync_stats?.last_sync ? "Active" : "Idle"} />
          <DataRow label="Sync Success Rate" value={`${cmStatus?.sync_stats?.success_rate ?? 100}%`} />
          <DataRow label="Drift Issues" value={driftActive} valueClass={driftActive > 0 ? "text-amber-400" : "text-gray-900"} />
          <DataRow label="Providers" value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
        </div>
      </PanelCard>

      {/* Property Alerts */}
      <PanelCard testId="gm-panel-alerts" title="Property Alerts" icon={AlertTriangle}
        status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
        {alerts?.alerts?.length > 0 ? (
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {alerts.alerts.map((a, i) => (
              <div key={i} className="flex items-start gap-2 p-2 rounded bg-white border border-gray-200">
                <SeverityChip severity={a.severity} />
                <div className="min-w-0">
                  <p className="text-xs text-gray-700 truncate">{a.message || a.type}</p>
                  {a.metric && <p className="text-[11px] text-gray-600">{a.metric}: {a.value}</p>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={CheckCircle2} message="No active property alerts" />
        )}
      </PanelCard>
    </div>
  );
}

/* ── Admin Tenant Panel ─────────────────────────────────── */
function AdminTenantView({ cmStatus, queueHealth, secAudit, rateLimit, tenantGuard, logSanit, alerts, stuckTasks, auditMetrics, wsBridge, roomService, triggerDriftScan, driftScanLoading, triggerRecon, reconLoading }) {
  const alertCount = alerts?.count || 0;
  const criticalAlerts = alerts?.critical || 0;

  return (
    <div data-testid="admin-tenant-view" className="space-y-4">
      {/* Top Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard testId="admin-metric-cm" icon={Wifi} title="Channel Manager" value={cmStatus?.health || "N/A"} sub={`${cmStatus?.active_connections || 0} connections`} />
        <MetricCard testId="admin-metric-queue" icon={Database} title="Queue Health" value={queueHealth?.health || "N/A"} sub={`${queueHealth?.pending || 0} pending`} />
        <MetricCard testId="admin-metric-alerts" icon={AlertTriangle} title="Active Alerts" value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} critical` : "All clear"} />
        <MetricCard testId="admin-metric-stuck" icon={Clock} title="Stuck Tasks" value={stuckTasks?.count || 0} sub={stuckTasks?.count > 0 ? "Action needed" : "None"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* CM Panel with actions */}
        <PanelCard testId="admin-panel-cm" title="Channel Manager" icon={Wifi} status={cmStatus?.health}
          onAction={triggerDriftScan} actionLabel="Drift Scan" actionLoading={driftScanLoading}>
          <div className="space-y-2 text-xs">
            <DataRow label="Sync Status" value={cmStatus?.sync_stats?.last_sync ? "Active" : "Idle"} />
            <DataRow label="Drift Issues" value={cmStatus?.drift?.active_drifts || 0} />
            <DataRow label="Sync Success Rate" value={`${cmStatus?.sync_stats?.success_rate ?? 100}%`} />
            <div className="flex justify-between text-gray-600">
              <span>Reconciliation</span>
              <StatusBadge status={cmStatus?.reconciliation?.status || "ok"} />
            </div>
            <DataRow label="Providers" value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
            {cmStatus?.sync_stats?.sync_lag_seconds != null && (
              <DataRow label="Sync Lag" value={`${Math.round(cmStatus.sync_stats.sync_lag_seconds / 60)}m`} />
            )}
            <Button data-testid="admin-run-recon-btn" size="sm" variant="outline" onClick={triggerRecon} disabled={reconLoading}
              className="w-full mt-2 h-7 text-xs border-gray-200 bg-white hover:bg-gray-50 text-gray-700">
              {reconLoading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
              Run Reconciliation
            </Button>
          </div>
        </PanelCard>

        {/* Queue & Workers */}
        <PanelCard testId="admin-panel-queue" title="Queue & Workers" icon={Server} status={queueHealth?.health}>
          <div className="space-y-2 text-xs">
            <DataRow label="Pending Tasks" value={queueHealth?.pending || 0} />
            <DataRow label="Processing" value={queueHealth?.processing || 0} />
            <DataRow label="Failed" value={queueHealth?.failed || 0} valueClass={(queueHealth?.failed || 0) > 0 ? "text-red-400" : "text-gray-900"} />
            <DataRow label="Saturation" value={`${queueHealth?.saturation_pct ?? 0}%`} />
            <DataRow label="Stuck Tasks" value={stuckTasks?.count || 0} valueClass={(stuckTasks?.count || 0) > 0 ? "text-amber-400" : "text-gray-900"} />
            <DataRow label="Dead Letter" value={queueHealth?.dead_letter?.total || 0} />
            <div className="flex justify-between text-gray-600">
              <span>Workers</span>
              <StatusBadge status={queueHealth?.worker_heartbeat?.responding ? "active" : "critical"} />
            </div>
          </div>
        </PanelCard>

        {/* Security */}
        <PanelCard testId="admin-panel-security" title="Security Runtime" icon={Shield}
          status={secAudit?.severity === "critical" ? "critical" : (secAudit?.severity === "warning" ? "degraded" : "active")}>
          <div className="space-y-2 text-xs">
            <DataRow label="Audit Score" value={`${secAudit?.completeness_score ?? "N/A"}%`} />
            <DataRow label="Audit Gaps" value={secAudit?.gaps_found || 0} valueClass={(secAudit?.gaps_found || 0) > 0 ? "text-amber-400" : "text-gray-900"} />
            <div className="flex justify-between text-gray-600"><span>Rate Limiting</span><StatusBadge status={rateLimit?.enforcement || "active"} /></div>
            {rateLimit?.burst_detected && <DataRow label="Burst Detected" value="Yes" valueClass="text-red-400" />}
            <div className="flex justify-between text-gray-600"><span>Tenant Guard</span><StatusBadge status={tenantGuard?.enforcement || "active"} /></div>
            <DataRow label="Violations" value={tenantGuard?.total_violations || 0} valueClass={(tenantGuard?.total_violations || 0) > 0 ? "text-red-400" : "text-gray-900"} />
            <DataRow label="Log Sanitization" value={logSanit?.all_patterns_working ? "All OK" : "Issues"} />
          </div>
        </PanelCard>

        {/* Alerts */}
        <PanelCard testId="admin-panel-alerts" title="Runtime Alerts" icon={AlertTriangle}
          status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
          {alerts?.alerts?.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {alerts.alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-white border border-gray-200">
                  <SeverityChip severity={a.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-gray-700 truncate">{a.message || a.type}</p>
                    {a.metric && <p className="text-[11px] text-gray-600">{a.metric}: {a.value}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} message="No active alerts" />
          )}
        </PanelCard>

        {/* Multi-instance live chat bridge */}
        <WSBridgePanel wsBridge={wsBridge} testIdPrefix="admin-ws-bridge" />

        {/* Room-service realtime gauge (Task #92) */}
        <RoomServiceLivePanel roomService={roomService} testIdPrefix="admin-room-service" />
      </div>

      {/* Audit & Observability */}
      {auditMetrics && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4" /> Audit & Observability
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <MetricCard testId="admin-metric-drift" icon={Eye} title="Drift Scans" value={auditMetrics.drift?.scans_count ?? 0} sub={`${auditMetrics.drift?.total_drifts ?? 0} drifts`} />
            <MetricCard testId="admin-metric-recon" icon={CheckCircle2} title="Recon Success" value={`${auditMetrics.reconciliation?.success_rate ?? 100}%`} sub={`${auditMetrics.reconciliation?.total_runs ?? 0} runs`} />
            <MetricCard testId="admin-metric-backlog" icon={Database} title="Queue Backlog" value={auditMetrics.queue?.current_pending ?? 0} sub={`${auditMetrics.queue?.current_stuck ?? 0} stuck`} />
            <MetricCard testId="admin-metric-violations" icon={Shield} title="Violations" value={auditMetrics.security?.violations_period ?? 0} sub="24h period" />
            <MetricCard testId="admin-metric-dl" icon={XCircle} title="Dead Letter" value={auditMetrics.dead_letter?.total ?? 0} sub={`+${auditMetrics.dead_letter?.new_in_period ?? 0} new`} />
            <MetricCard testId="admin-metric-total-alerts" icon={AlertTriangle} title="Total Alerts" value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} critical` : "Clear"} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Superadmin Global Panel ────────────────────────────── */
function SuperadminGlobalView({ cmStatus, queueHealth, secAudit, rateLimit, tenantGuard, logSanit, alerts, stuckTasks, metrics, auditMetrics, normalizedOverview, wsBridge, roomService, triggerDriftScan, driftScanLoading, triggerRecon, reconLoading }) {
  const alertCount = alerts?.count || 0;
  const criticalAlerts = alerts?.critical || 0;

  return (
    <div data-testid="superadmin-global-view" className="space-y-4">
      {/* Top Metrics - expanded for superadmin */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
        <MetricCard testId="sa-metric-cm" icon={Wifi} title="Channel Manager" value={cmStatus?.health || "N/A"} sub={`${cmStatus?.active_connections || 0} conn`} />
        <MetricCard testId="sa-metric-queue" icon={Database} title="Queue Health" value={queueHealth?.health || "N/A"} sub={`${queueHealth?.pending || 0} pending`} />
        <MetricCard testId="sa-metric-alerts" icon={AlertTriangle} title="Alerts" value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} critical` : "Clear"} />
        <MetricCard testId="sa-metric-violations" icon={Shield} title="Guard Violations" value={tenantGuard?.total_violations || 0} sub="Cross-tenant" />
        <MetricCard testId="sa-metric-stuck" icon={Clock} title="Stuck / DL" value={`${stuckTasks?.count || 0} / ${queueHealth?.dead_letter?.total || 0}`} sub="Stuck / Dead Letter" />
      </div>

      {/* Critical Alert Banner */}
      {criticalAlerts > 0 && (
        <div data-testid="sa-critical-banner" className="p-3 rounded-lg bg-red-950/40 border border-red-800/50 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-300">{criticalAlerts} critical alert{criticalAlerts > 1 ? "s" : ""} — global scope</p>
            <p className="text-xs text-red-400/70 mt-0.5">Immediate cross-tenant intervention required</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* CM with full actions */}
        <PanelCard testId="sa-panel-cm" title="Channel Manager (Global)" icon={Wifi} status={cmStatus?.health}
          onAction={triggerDriftScan} actionLabel="Drift Scan" actionLoading={driftScanLoading}>
          <div className="space-y-2 text-xs">
            <DataRow label="Sync Status" value={cmStatus?.sync_stats?.last_sync ? "Active" : "Idle"} />
            <DataRow label="Drift Issues" value={cmStatus?.drift?.active_drifts || 0} />
            <DataRow label="Sync Success Rate" value={`${cmStatus?.sync_stats?.success_rate ?? 100}%`} />
            <div className="flex justify-between text-gray-600"><span>Reconciliation</span><StatusBadge status={cmStatus?.reconciliation?.status || "ok"} /></div>
            <DataRow label="Providers" value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
            {cmStatus?.sync_stats?.sync_lag_seconds != null && <DataRow label="Sync Lag" value={`${Math.round(cmStatus.sync_stats.sync_lag_seconds / 60)}m`} />}
            <Button data-testid="sa-run-recon-btn" size="sm" variant="outline" onClick={triggerRecon} disabled={reconLoading}
              className="w-full mt-2 h-7 text-xs border-gray-200 bg-white hover:bg-gray-50 text-gray-700">
              {reconLoading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
              Run Reconciliation
            </Button>
          </div>
        </PanelCard>

        {/* Queue & Workers */}
        <PanelCard testId="sa-panel-queue" title="Queue & Workers (Global)" icon={Server} status={queueHealth?.health}>
          <div className="space-y-2 text-xs">
            <DataRow label="Pending Tasks" value={queueHealth?.pending || 0} />
            <DataRow label="Processing" value={queueHealth?.processing || 0} />
            <DataRow label="Failed" value={queueHealth?.failed || 0} valueClass={(queueHealth?.failed || 0) > 0 ? "text-red-400" : "text-gray-900"} />
            <DataRow label="Saturation" value={`${queueHealth?.saturation_pct ?? 0}%`} />
            <DataRow label="Stuck Tasks" value={stuckTasks?.count || 0} valueClass={(stuckTasks?.count || 0) > 0 ? "text-amber-400" : "text-gray-900"} />
            <DataRow label="Dead Letter" value={queueHealth?.dead_letter?.total || 0} />
            <div className="flex justify-between text-gray-600">
              <span>Workers</span>
              <StatusBadge status={queueHealth?.worker_heartbeat?.responding ? "active" : "critical"} />
            </div>
          </div>
        </PanelCard>

        {/* Security - expanded */}
        <PanelCard testId="sa-panel-security" title="Security Posture (Global)" icon={Shield}
          status={secAudit?.severity === "critical" ? "critical" : (secAudit?.severity === "warning" ? "degraded" : "active")}>
          <div className="space-y-2 text-xs">
            <DataRow label="Audit Score" value={`${secAudit?.completeness_score ?? "N/A"}%`} />
            <DataRow label="Audit Gaps" value={secAudit?.gaps_found || 0} valueClass={(secAudit?.gaps_found || 0) > 0 ? "text-amber-400" : "text-gray-900"} />
            <div className="flex justify-between text-gray-600"><span>Rate Limiting</span><StatusBadge status={rateLimit?.enforcement || "active"} /></div>
            {rateLimit?.burst_detected && <DataRow label="Burst Detected" value="Yes" valueClass="text-red-400" />}
            <div className="flex justify-between text-gray-600"><span>Tenant Guard</span><StatusBadge status={tenantGuard?.enforcement || "active"} /></div>
            <DataRow label="Cross-Tenant Violations" value={tenantGuard?.total_violations || 0} valueClass={(tenantGuard?.total_violations || 0) > 0 ? "text-red-400" : "text-gray-900"} />
            <DataRow label="Log Sanitization" value={logSanit?.all_patterns_working ? "All OK" : "Issues"} />
          </div>
        </PanelCard>

        {/* Alerts */}
        <PanelCard testId="sa-panel-alerts" title="Global Alerts" icon={AlertTriangle}
          status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
          {alerts?.alerts?.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {alerts.alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-white border border-gray-200">
                  <SeverityChip severity={a.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-gray-700 truncate">{a.message || a.type}</p>
                    {a.metric && <p className="text-[11px] text-gray-600">{a.metric}: {a.value}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} message="No active alerts globally" />
          )}
        </PanelCard>

        {/* Multi-instance live chat bridge */}
        <WSBridgePanel wsBridge={wsBridge} testIdPrefix="sa-ws-bridge" />

        {/* Room-service realtime gauge (Task #92) */}
        <RoomServiceLivePanel roomService={roomService} testIdPrefix="sa-room-service" />
      </div>

      {/* Audit & Observability */}
      {auditMetrics && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4" /> Audit & Observability (Global)
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <MetricCard testId="sa-audit-drift" icon={Eye} title="Drift Scans" value={auditMetrics.drift?.scans_count ?? 0} sub={`${auditMetrics.drift?.total_drifts ?? 0} drifts`} />
            <MetricCard testId="sa-audit-recon" icon={CheckCircle2} title="Recon Success" value={`${auditMetrics.reconciliation?.success_rate ?? 100}%`} sub={`${auditMetrics.reconciliation?.total_runs ?? 0} runs`} />
            <MetricCard testId="sa-audit-backlog" icon={Database} title="Queue Backlog" value={auditMetrics.queue?.current_pending ?? 0} sub={`${auditMetrics.queue?.current_stuck ?? 0} stuck`} />
            <MetricCard testId="sa-audit-violations" icon={Shield} title="Violations" value={auditMetrics.security?.violations_period ?? 0} sub="24h period" />
            <MetricCard testId="sa-audit-dl" icon={XCircle} title="Dead Letter" value={auditMetrics.dead_letter?.total ?? 0} sub={`+${auditMetrics.dead_letter?.new_in_period ?? 0} new`} />
            <MetricCard testId="sa-audit-total" icon={AlertTriangle} title="Total Alerts" value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} critical` : "Clear"} />
          </div>
        </div>
      )}

      {/* Runtime Metrics */}
      {metrics && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Runtime Metrics (Global)</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {metrics.sync && <MetricCard testId="sa-rt-sync" icon={Clock} title="Sync Lag" value={`${metrics.sync.lag_seconds ?? 0}s`} />}
            {metrics.drift && <MetricCard testId="sa-rt-drift" icon={AlertTriangle} title="Active Drifts" value={metrics.drift.active_count ?? 0} />}
            {metrics.reconciliation && <MetricCard testId="sa-rt-recon" icon={CheckCircle2} title="Recon Rate" value={`${metrics.reconciliation.success_rate ?? 100}%`} />}
            {metrics.queue && <MetricCard testId="sa-rt-queue" icon={Database} title="Queue" value={metrics.queue.backlog ?? 0} />}
            {metrics.security && <MetricCard testId="sa-rt-sec" icon={Shield} title="Violations" value={metrics.security.violations ?? 0} />}
          </div>
        </div>
      )}

      {/* Subsystem Health */}
      {normalizedOverview?.subsystems && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Subsystem Health (Global)</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
            {Object.entries(normalizedOverview.subsystems).map(([key, sub]) => (
              <div key={key} data-testid={`normalized-${key}`} className="p-3 rounded-lg bg-white border border-gray-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-700 capitalize">{key.replace(/_/g, " ")}</span>
                  <StatusBadge status={sub.status} />
                </div>
                <div className="text-[11px] text-gray-600 space-y-1">
                  <SeverityChip severity={sub.severity} />
                  {sub.evidence_summary && <p className="mt-1 text-gray-600">{sub.evidence_summary}</p>}
                  {sub.degraded_reason && <p className="text-amber-400/80">{sub.degraded_reason}</p>}
                  {sub.suggested_action && <p className="text-sky-400/70">{sub.suggested_action}</p>}
                  <p className="text-gray-600">Updated: {sub.last_updated_at ? new Date(sub.last_updated_at).toLocaleTimeString() : "N/A"}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main Dashboard ──────────────────────────────────────── */

export default function SystemHealthDashboard({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [cmStatus, setCmStatus] = useState(null);
  const [queueHealth, setQueueHealth] = useState(null);
  const [secAudit, setSecAudit] = useState(null);
  const [rateLimit, setRateLimit] = useState(null);
  const [tenantGuard, setTenantGuard] = useState(null);
  const [logSanit, setLogSanit] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [stuckTasks, setStuckTasks] = useState(null);
  const [driftScanLoading, setDriftScanLoading] = useState(false);
  const [reconLoading, setReconLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [normalizedOverview, setNormalizedOverview] = useState(null);
  const [roleDashboard, setRoleDashboard] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [liveEvents, setLiveEvents] = useState([]);
  const [auditMetrics, setAuditMetrics] = useState(null);
  const socketRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const token = localStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  /* ── WebSocket Connection ────────────────────────────── */
  useEffect(() => {
    if (!API) return;
    const baseUrl = API.replace(/\/api$/, "");

    const socket = io(baseUrl, {
      path: "/socket.io/",
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
      reconnectionDelayMax: 30000,
      timeout: 10000,
    });
    socketRef.current = socket;

    socket.on("connect", () => {
      setWsConnected(true);
      socket.emit("join_room", { room: "system-health" });
    });
    socket.on("disconnect", () => setWsConnected(false));
    socket.on("connect_error", () => setWsConnected(false));

    socket.on("system_health_event", (data) => {
      setLiveEvents((prev) => [data, ...prev].slice(0, 20));
      if (data?.severity === "critical") fetchAll();
    });

    socket.on("health_metric_update", (data) => {
      if (!data) return;
      const { metric_type, data: metricData } = data;
      if (metric_type === "queue_depth" && metricData) {
        setQueueHealth((prev) => prev ? { ...prev, ...metricData } : metricData);
      }
    });

    socket.on("room_joined", (data) => {
      if (data?.room === "system-health") setWsConnected(true);
    });

    return () => {
      socket.disconnect();
      socketRef.current = null;
      if (reconnectTimerRef.current) clearInterval(reconnectTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!wsConnected) {
      reconnectTimerRef.current = setInterval(() => fetchAll(true), 30000);
    } else {
      if (reconnectTimerRef.current) {
        clearInterval(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    }
    return () => { if (reconnectTimerRef.current) clearInterval(reconnectTimerRef.current); };
  }, [wsConnected]);

  /* ── Data Fetching ───────────────────────────────────── */
  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [cm, q, audit, rl, tg, ls, al, mt, st, norm, role, am] = await Promise.allSettled([
        axios.get(`/channel-manager/runtime/status`, { headers }),
        axios.get(`/workers/queues/health`, { headers }),
        axios.get(`/security/audit/status`, { headers }),
        axios.get(`/security/rate-limit/status`, { headers }),
        axios.get(`/security/tenant-guard/status`, { headers }),
        axios.get(`/security/log-sanitization/status`, { headers }),
        axios.get(`/observability/runtime/alerts`, { headers }),
        axios.get(`/observability/runtime/metrics`, { headers }),
        axios.get(`/workers/tasks/stuck`, { headers }),
        axios.get(`/system-health/normalized/overview`, { headers }),
        axios.get(`/system-health/role-dashboard`, { headers }),
        axios.get(`/system-health/audit/metrics`, { headers }),
      ]);
      if (cm.status === "fulfilled") setCmStatus(cm.value.data);
      if (q.status === "fulfilled") setQueueHealth(q.value.data);
      if (audit.status === "fulfilled") setSecAudit(audit.value.data);
      if (rl.status === "fulfilled") setRateLimit(rl.value.data);
      if (tg.status === "fulfilled") setTenantGuard(tg.value.data);
      if (ls.status === "fulfilled") setLogSanit(ls.value.data);
      if (al.status === "fulfilled") setAlerts(al.value.data);
      if (mt.status === "fulfilled") setMetrics(mt.value.data);
      if (st.status === "fulfilled") setStuckTasks(st.value.data);
      if (norm.status === "fulfilled") setNormalizedOverview(norm.value.data);
      if (role.status === "fulfilled") setRoleDashboard(role.value.data);
      if (am.status === "fulfilled") setAuditMetrics(am.value.data);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const triggerDriftScan = async () => {
    setDriftScanLoading(true);
    try { await axios.post(`/channel-manager/drift/scan`, null, { headers }); await fetchAll(); }
    catch (e) { console.error(e); }
    setDriftScanLoading(false);
  };

  const triggerRecon = async () => {
    setReconLoading(true);
    try { await axios.post(`/channel-manager/reconciliation/run?auto_fix=true`, null, { headers }); await fetchAll(); }
    catch (e) { console.error(e); }
    setReconLoading(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-gray-600 animate-spin" />
      </div>
    );
  }

  const userRole = roleDashboard?.role || user?.role || "admin";
  const userScope = roleDashboard?.scope || "";
  const wsBridge = normalizedOverview?.subsystems?.ws_bridge || null;
  const roomService = normalizedOverview?.subsystems?.room_service || null;

  return (
    <>
    <div data-testid="system-health-dashboard" className="min-h-screen bg-white text-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Button data-testid="back-btn" variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-gray-600 hover:text-gray-900">
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <h1 className="text-xl font-bold tracking-tight">System Health</h1>
              <p className="text-xs text-gray-600 mt-0.5">Runtime hardening & operations console</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ScopeBanner role={userRole} scope={userScope} />
            <div data-testid="ws-status-badge" className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
              wsConnected ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" : "bg-amber-500/10 text-amber-400 border-amber-500/30"
            }`}>
              {wsConnected ? <Radio className="w-3 h-3 animate-pulse" /> : <WifiOff className="w-3 h-3" />}
              {wsConnected ? "Live" : "Polling"}
            </div>
            {lastUpdated && <span className="text-[11px] text-gray-600">Updated {lastUpdated}</span>}
            <Button data-testid="refresh-all-btn" size="sm" variant="outline" onClick={fetchAll}
              className="h-8 border-gray-200 bg-white hover:bg-gray-50 text-gray-700">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
            </Button>
          </div>
        </div>

        {/* Normalized Status Bar */}
        {normalizedOverview && (
          <div data-testid="normalized-overview-bar" className="mb-6 p-3 rounded-lg border flex items-center gap-4"
            style={{
              background: normalizedOverview.overall_status === "critical" ? "rgba(239,68,68,0.08)" :
                normalizedOverview.overall_status === "degraded" ? "rgba(245,158,11,0.08)" : "rgba(16,185,129,0.08)",
              borderColor: normalizedOverview.overall_status === "critical" ? "rgba(239,68,68,0.3)" :
                normalizedOverview.overall_status === "degraded" ? "rgba(245,158,11,0.3)" : "rgba(16,185,129,0.3)",
            }}>
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-gray-700" />
              <span className="text-sm font-medium text-gray-900">Overall:</span>
              <StatusBadge status={normalizedOverview.overall_status} />
              <SeverityChip severity={normalizedOverview.overall_severity} />
            </div>
          </div>
        )}

        {/* Live Events Strip */}
        {liveEvents.length > 0 && (
          <div data-testid="live-events-strip" className="mb-4 flex gap-2 overflow-x-auto pb-1">
            {liveEvents.slice(0, 8).map((ev, i) => (
              <div key={i} className="flex-shrink-0 px-3 py-1.5 rounded-md bg-white border border-gray-200 text-[11px] flex items-center gap-2">
                <Zap className="w-3 h-3 text-amber-400" />
                <SeverityChip severity={ev.severity || "info"} />
                <span className="text-gray-700">{ev.event_type}</span>
                <span className="text-gray-600">{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ""}</span>
              </div>
            ))}
          </div>
        )}

        {/* Role-Based Content Panels */}
        {userRole === "gm" && (
          <GMPropertyView cmStatus={cmStatus} alerts={alerts} normalizedOverview={normalizedOverview} />
        )}

        {userRole === "admin" && (
          <AdminTenantView
            cmStatus={cmStatus} queueHealth={queueHealth} secAudit={secAudit}
            rateLimit={rateLimit} tenantGuard={tenantGuard} logSanit={logSanit}
            alerts={alerts} stuckTasks={stuckTasks} auditMetrics={auditMetrics}
            wsBridge={wsBridge} roomService={roomService}
            triggerDriftScan={triggerDriftScan} driftScanLoading={driftScanLoading}
            triggerRecon={triggerRecon} reconLoading={reconLoading}
          />
        )}

        {(userRole === "superadmin" || (userRole !== "gm" && userRole !== "admin")) && (
          <SuperadminGlobalView
            cmStatus={cmStatus} queueHealth={queueHealth} secAudit={secAudit}
            rateLimit={rateLimit} tenantGuard={tenantGuard} logSanit={logSanit}
            alerts={alerts} stuckTasks={stuckTasks} metrics={metrics}
            auditMetrics={auditMetrics} normalizedOverview={normalizedOverview}
            wsBridge={wsBridge} roomService={roomService}
            triggerDriftScan={triggerDriftScan} driftScanLoading={driftScanLoading}
            triggerRecon={triggerRecon} reconLoading={reconLoading}
          />
        )}
      </div>
    </div>
    </>
  );
}
