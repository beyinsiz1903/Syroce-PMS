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
  Database, Radio, Zap, TrendingUp, Users, Building2, Layers
} from "lucide-react";

const API = import.meta.env.VITE_BACKEND_URL;

/* ── Tiny Reusable Components ─────────────────────────── */

function StatusBadge({ status }) {
  const map = {
    healthy: { label: "Healthy", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
    degraded: { label: "Degraded", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
    critical: { label: "Critical", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
    warning: { label: "Warning", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
    active: { label: "Active", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
    ok: { label: "OK", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
    unknown: { label: "Unknown", cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30" },
  };
  const m = map[status] || { label: status || "Unknown", cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30" };
  return <Badge data-testid={`status-badge-${status}`} variant="outline" className={`${m.cls} text-xs font-mono`}>{m.label}</Badge>;
}

function SeverityChip({ severity }) {
  const map = {
    critical: "bg-red-500/20 text-red-300 border-red-500/40",
    high: "bg-orange-500/20 text-orange-300 border-orange-500/40",
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
    <div data-testid={testId} className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex items-start gap-3">
      <div className="p-2 rounded-md bg-zinc-800"><Icon className="w-4 h-4 text-zinc-400" /></div>
      <div>
        <p className="text-xs text-zinc-500 mb-0.5">{title}</p>
        <p className="text-lg font-semibold text-zinc-100 leading-none">{value}</p>
        {sub && <p className="text-[11px] text-zinc-500 mt-1">{sub}</p>}
      </div>
    </div>
  );
}

function PanelCard({ title, icon: Icon, children, status, onAction, actionLabel, actionLoading, testId, permissionGated }) {
  return (
    <Card data-testid={testId} className="bg-zinc-950 border-zinc-800/70 shadow-lg">
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-zinc-400" />
          <CardTitle className="text-sm font-semibold text-zinc-200">{title}</CardTitle>
        </div>
        <div className="flex items-center gap-2">
          {status && <StatusBadge status={status} />}
          {onAction && !permissionGated && (
            <Button data-testid={testId ? `${testId}-action` : `action-${title.toLowerCase().replace(/\s+/g, "-")}`}
              size="sm" variant="outline"
              className="h-7 text-xs border-zinc-700 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
              onClick={onAction} disabled={actionLoading}>
              {actionLoading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
              {actionLabel || "Scan"}
            </Button>
          )}
          {permissionGated && (
            <span className="text-[10px] text-zinc-600 flex items-center gap-1"><Lock className="w-3 h-3" /> View Only</span>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  );
}

function EmptyState({ icon: Icon, message }) {
  return (
    <div data-testid="empty-state" className="flex flex-col items-center justify-center py-6 text-zinc-600">
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
      {scope && <span className="text-zinc-500 ml-1">({scope})</span>}
    </div>
  );
}

/* ── Row Helper ─────────────────────────────────────────── */
function DataRow({ label, value, valueClass }) {
  return (
    <div className="flex justify-between text-zinc-400">
      <span>{label}</span>
      <span className={valueClass || "text-zinc-200"}>{value}</span>
    </div>
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
          <DataRow label="Drift Issues" value={driftActive} valueClass={driftActive > 0 ? "text-amber-400" : "text-zinc-200"} />
          <DataRow label="Providers" value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
        </div>
      </PanelCard>

      {/* Property Alerts */}
      <PanelCard testId="gm-panel-alerts" title="Property Alerts" icon={AlertTriangle}
        status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
        {alerts?.alerts?.length > 0 ? (
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {alerts.alerts.map((a, i) => (
              <div key={i} className="flex items-start gap-2 p-2 rounded bg-zinc-900/50 border border-zinc-800/50">
                <SeverityChip severity={a.severity} />
                <div className="min-w-0">
                  <p className="text-xs text-zinc-300 truncate">{a.message || a.type}</p>
                  {a.metric && <p className="text-[11px] text-zinc-500">{a.metric}: {a.value}</p>}
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
function AdminTenantView({ cmStatus, queueHealth, secAudit, rateLimit, tenantGuard, logSanit, alerts, stuckTasks, auditMetrics, triggerDriftScan, driftScanLoading, triggerRecon, reconLoading }) {
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
            <div className="flex justify-between text-zinc-400">
              <span>Reconciliation</span>
              <StatusBadge status={cmStatus?.reconciliation?.status || "ok"} />
            </div>
            <DataRow label="Providers" value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
            {cmStatus?.sync_stats?.sync_lag_seconds != null && (
              <DataRow label="Sync Lag" value={`${Math.round(cmStatus.sync_stats.sync_lag_seconds / 60)}m`} />
            )}
            <Button data-testid="admin-run-recon-btn" size="sm" variant="outline" onClick={triggerRecon} disabled={reconLoading}
              className="w-full mt-2 h-7 text-xs border-zinc-700 bg-zinc-900 hover:bg-zinc-800 text-zinc-300">
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
            <DataRow label="Failed" value={queueHealth?.failed || 0} valueClass={(queueHealth?.failed || 0) > 0 ? "text-red-400" : "text-zinc-200"} />
            <DataRow label="Saturation" value={`${queueHealth?.saturation_pct ?? 0}%`} />
            <DataRow label="Stuck Tasks" value={stuckTasks?.count || 0} valueClass={(stuckTasks?.count || 0) > 0 ? "text-amber-400" : "text-zinc-200"} />
            <DataRow label="Dead Letter" value={queueHealth?.dead_letter?.total || 0} />
            <div className="flex justify-between text-zinc-400">
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
            <DataRow label="Audit Gaps" value={secAudit?.gaps_found || 0} valueClass={(secAudit?.gaps_found || 0) > 0 ? "text-amber-400" : "text-zinc-200"} />
            <div className="flex justify-between text-zinc-400"><span>Rate Limiting</span><StatusBadge status={rateLimit?.enforcement || "active"} /></div>
            {rateLimit?.burst_detected && <DataRow label="Burst Detected" value="Yes" valueClass="text-red-400" />}
            <div className="flex justify-between text-zinc-400"><span>Tenant Guard</span><StatusBadge status={tenantGuard?.enforcement || "active"} /></div>
            <DataRow label="Violations" value={tenantGuard?.total_violations || 0} valueClass={(tenantGuard?.total_violations || 0) > 0 ? "text-red-400" : "text-zinc-200"} />
            <DataRow label="Log Sanitization" value={logSanit?.all_patterns_working ? "All OK" : "Issues"} />
          </div>
        </PanelCard>

        {/* Alerts */}
        <PanelCard testId="admin-panel-alerts" title="Runtime Alerts" icon={AlertTriangle}
          status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
          {alerts?.alerts?.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {alerts.alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-zinc-900/50 border border-zinc-800/50">
                  <SeverityChip severity={a.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-zinc-300 truncate">{a.message || a.type}</p>
                    {a.metric && <p className="text-[11px] text-zinc-500">{a.metric}: {a.value}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} message="No active alerts" />
          )}
        </PanelCard>
      </div>

      {/* Audit & Observability */}
      {auditMetrics && (
        <div>
          <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
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
function SuperadminGlobalView({ cmStatus, queueHealth, secAudit, rateLimit, tenantGuard, logSanit, alerts, stuckTasks, metrics, auditMetrics, normalizedOverview, triggerDriftScan, driftScanLoading, triggerRecon, reconLoading }) {
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
            <div className="flex justify-between text-zinc-400"><span>Reconciliation</span><StatusBadge status={cmStatus?.reconciliation?.status || "ok"} /></div>
            <DataRow label="Providers" value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
            {cmStatus?.sync_stats?.sync_lag_seconds != null && <DataRow label="Sync Lag" value={`${Math.round(cmStatus.sync_stats.sync_lag_seconds / 60)}m`} />}
            <Button data-testid="sa-run-recon-btn" size="sm" variant="outline" onClick={triggerRecon} disabled={reconLoading}
              className="w-full mt-2 h-7 text-xs border-zinc-700 bg-zinc-900 hover:bg-zinc-800 text-zinc-300">
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
            <DataRow label="Failed" value={queueHealth?.failed || 0} valueClass={(queueHealth?.failed || 0) > 0 ? "text-red-400" : "text-zinc-200"} />
            <DataRow label="Saturation" value={`${queueHealth?.saturation_pct ?? 0}%`} />
            <DataRow label="Stuck Tasks" value={stuckTasks?.count || 0} valueClass={(stuckTasks?.count || 0) > 0 ? "text-amber-400" : "text-zinc-200"} />
            <DataRow label="Dead Letter" value={queueHealth?.dead_letter?.total || 0} />
            <div className="flex justify-between text-zinc-400">
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
            <DataRow label="Audit Gaps" value={secAudit?.gaps_found || 0} valueClass={(secAudit?.gaps_found || 0) > 0 ? "text-amber-400" : "text-zinc-200"} />
            <div className="flex justify-between text-zinc-400"><span>Rate Limiting</span><StatusBadge status={rateLimit?.enforcement || "active"} /></div>
            {rateLimit?.burst_detected && <DataRow label="Burst Detected" value="Yes" valueClass="text-red-400" />}
            <div className="flex justify-between text-zinc-400"><span>Tenant Guard</span><StatusBadge status={tenantGuard?.enforcement || "active"} /></div>
            <DataRow label="Cross-Tenant Violations" value={tenantGuard?.total_violations || 0} valueClass={(tenantGuard?.total_violations || 0) > 0 ? "text-red-400" : "text-zinc-200"} />
            <DataRow label="Log Sanitization" value={logSanit?.all_patterns_working ? "All OK" : "Issues"} />
          </div>
        </PanelCard>

        {/* Alerts */}
        <PanelCard testId="sa-panel-alerts" title="Global Alerts" icon={AlertTriangle}
          status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
          {alerts?.alerts?.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {alerts.alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-zinc-900/50 border border-zinc-800/50">
                  <SeverityChip severity={a.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-zinc-300 truncate">{a.message || a.type}</p>
                    {a.metric && <p className="text-[11px] text-zinc-500">{a.metric}: {a.value}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} message="No active alerts globally" />
          )}
        </PanelCard>
      </div>

      {/* Audit & Observability */}
      {auditMetrics && (
        <div>
          <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
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
          <h2 className="text-sm font-semibold text-zinc-300 mb-3">Runtime Metrics (Global)</h2>
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
          <h2 className="text-sm font-semibold text-zinc-300 mb-3">Subsystem Health (Global)</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
            {Object.entries(normalizedOverview.subsystems).map(([key, sub]) => (
              <div key={key} data-testid={`normalized-${key}`} className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-zinc-300 capitalize">{key.replace(/_/g, " ")}</span>
                  <StatusBadge status={sub.status} />
                </div>
                <div className="text-[11px] text-zinc-500 space-y-1">
                  <SeverityChip severity={sub.severity} />
                  {sub.evidence_summary && <p className="mt-1 text-zinc-400">{sub.evidence_summary}</p>}
                  {sub.degraded_reason && <p className="text-amber-400/80">{sub.degraded_reason}</p>}
                  {sub.suggested_action && <p className="text-sky-400/70">{sub.suggested_action}</p>}
                  <p className="text-zinc-600">Updated: {sub.last_updated_at ? new Date(sub.last_updated_at).toLocaleTimeString() : "N/A"}</p>
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

export default function SystemHealthDashboard({ user }) {
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
      reconnectTimerRef.current = setInterval(() => fetchAll(), 30000);
    } else {
      if (reconnectTimerRef.current) {
        clearInterval(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    }
    return () => { if (reconnectTimerRef.current) clearInterval(reconnectTimerRef.current); };
  }, [wsConnected]);

  /* ── Data Fetching ───────────────────────────────────── */
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cm, q, audit, rl, tg, ls, al, mt, st, norm, role, am] = await Promise.allSettled([
        axios.get(`${API}/api/channel-manager/runtime/status`, { headers }),
        axios.get(`${API}/api/workers/queues/health`, { headers }),
        axios.get(`${API}/api/security/audit/status`, { headers }),
        axios.get(`${API}/api/security/rate-limit/status`, { headers }),
        axios.get(`${API}/api/security/tenant-guard/status`, { headers }),
        axios.get(`${API}/api/security/log-sanitization/status`, { headers }),
        axios.get(`${API}/api/observability/runtime/alerts`, { headers }),
        axios.get(`${API}/api/observability/runtime/metrics`, { headers }),
        axios.get(`${API}/api/workers/tasks/stuck`, { headers }),
        axios.get(`${API}/api/system-health/normalized/overview`, { headers }),
        axios.get(`${API}/api/system-health/role-dashboard`, { headers }),
        axios.get(`${API}/api/system-health/audit/metrics`, { headers }),
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
    try { await axios.post(`${API}/api/channel-manager/drift/scan`, null, { headers }); await fetchAll(); }
    catch (e) { console.error(e); }
    setDriftScanLoading(false);
  };

  const triggerRecon = async () => {
    setReconLoading(true);
    try { await axios.post(`${API}/api/channel-manager/reconciliation/run?auto_fix=true`, null, { headers }); await fetchAll(); }
    catch (e) { console.error(e); }
    setReconLoading(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-zinc-400 animate-spin" />
      </div>
    );
  }

  const userRole = roleDashboard?.role || user?.role || "admin";
  const userScope = roleDashboard?.scope || "";

  return (
    <div data-testid="system-health-dashboard" className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Button data-testid="back-btn" variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-zinc-400 hover:text-zinc-200">
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <h1 className="text-xl font-bold tracking-tight">System Health</h1>
              <p className="text-xs text-zinc-500 mt-0.5">Runtime hardening & operations console</p>
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
            {lastUpdated && <span className="text-[11px] text-zinc-600">Updated {lastUpdated}</span>}
            <Button data-testid="refresh-all-btn" size="sm" variant="outline" onClick={fetchAll}
              className="h-8 border-zinc-700 bg-zinc-900 hover:bg-zinc-800 text-zinc-300">
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
              <Activity className="w-4 h-4 text-zinc-300" />
              <span className="text-sm font-medium text-zinc-200">Overall:</span>
              <StatusBadge status={normalizedOverview.overall_status} />
              <SeverityChip severity={normalizedOverview.overall_severity} />
            </div>
          </div>
        )}

        {/* Live Events Strip */}
        {liveEvents.length > 0 && (
          <div data-testid="live-events-strip" className="mb-4 flex gap-2 overflow-x-auto pb-1">
            {liveEvents.slice(0, 8).map((ev, i) => (
              <div key={i} className="flex-shrink-0 px-3 py-1.5 rounded-md bg-zinc-900/70 border border-zinc-800 text-[11px] flex items-center gap-2">
                <Zap className="w-3 h-3 text-amber-400" />
                <SeverityChip severity={ev.severity || "info"} />
                <span className="text-zinc-300">{ev.event_type}</span>
                <span className="text-zinc-600">{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ""}</span>
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
            triggerDriftScan={triggerDriftScan} driftScanLoading={driftScanLoading}
            triggerRecon={triggerRecon} reconLoading={reconLoading}
          />
        )}
      </div>
    </div>
  );
}
