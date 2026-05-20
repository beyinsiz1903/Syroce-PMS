import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import axios from "axios";
import { io } from "socket.io-client";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";

import {
  Activity, Shield, Server, AlertTriangle, RefreshCw, CheckCircle2,
  XCircle, Clock, Wifi, WifiOff, Lock, Eye, Loader2,
  Database, Radio, Zap, TrendingUp, TrendingDown, Minus, Users, Building2, Layers, Network,
  ShieldAlert,
} from "lucide-react";
import { useTranslation } from 'react-i18next';

/* ── Status mapping (TR + Sprint A intent palette) ─────────────────── */
const STATUS_META = {
  healthy:  { label: "Sağlıklı",  intent: "success" },
  ok:       { label: "Tamam",     intent: "success" },
  active:   { label: "Aktif",     intent: "success" },
  degraded: { label: "Düşük",     intent: "warning" },
  warning:  { label: "Uyarı",     intent: "warning" },
  critical: { label: "Kritik",    intent: "danger" },
  inactive: { label: "Pasif",     intent: "neutral" },
  unknown:  { label: "Bilinmiyor", intent: "neutral" },
};
function HealthBadge({ status }) {
  const { t } = useTranslation();
  const m = STATUS_META[(status || "").toLowerCase()] || STATUS_META.unknown;
  return <StatusBadge intent={m.intent}>{m.label}</StatusBadge>;
}

const SEVERITY_META = {
  critical: { label: "Kritik", intent: "danger" },
  high:     { label: "Yüksek", intent: "warning" },
  warning:  { label: "Uyarı",  intent: "warning" },
  info:     { label: "Bilgi",  intent: "info" },
};
function SeverityChip({ severity }) {
  const m = SEVERITY_META[(severity || "").toLowerCase()] || SEVERITY_META.info;
  return <StatusBadge intent={m.intent}>{m.label}</StatusBadge>;
}

/* ── Section row & cards ───────────────────────────────────────────── */
function MetricCard({ icon: Icon, title, value, sub, testId }) {
  return (
    <div data-testid={testId} className="bg-white border border-slate-200 rounded-lg p-4 flex items-start gap-3">
      <div className="p-2 rounded-md bg-slate-50"><Icon className="w-4 h-4 text-slate-600" /></div>
      <div className="min-w-0">
        <p className="text-xs text-slate-600 mb-0.5">{title}</p>
        <p className="text-lg font-semibold text-slate-900 leading-none truncate">{value}</p>
        {sub && <p className="text-[11px] text-slate-600 mt-1 truncate">{sub}</p>}
      </div>
    </div>
  );
}

function PanelCard({ title, icon: Icon, children, status, onAction, actionLabel, actionLoading, testId, permissionGated }) {
  const { t } = useTranslation();
  return (
    <Card data-testid={testId} className="bg-white border-slate-200">
      <CardHeader className="pb-3 flex flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className="w-4 h-4 text-slate-600 shrink-0" />
          <CardTitle className="text-sm font-semibold text-slate-900 truncate">{title}</CardTitle>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status && <HealthBadge status={status} />}
          {onAction && !permissionGated && (
            <Button data-testid={testId ? `${testId}-action` : undefined}
              size="sm" variant="outline" onClick={onAction} disabled={actionLoading}>
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
              {actionLabel || "Tara"}
            </Button>
          )}
          {permissionGated && (
            <span className="text-[10px] text-slate-600 flex items-center gap-1"><Lock className="w-3 h-3" /> {t('cm.pages_SystemHealthDashboard.salt_gorunum')}</span>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  );
}

function EmptyState({ icon: Icon, message }) {
  return (
    <div data-testid="empty-state" className="flex flex-col items-center justify-center py-6 text-slate-600">
      <Icon className="w-6 h-6 mb-2 opacity-50" />
      <span className="text-xs">{message}</span>
    </div>
  );
}

function ScopeBanner({ role, scope }) {
  const roleConfig = {
    superadmin: { icon: Layers,    intent: "info",    label: "Süperadmin — Global" },
    admin:      { icon: Building2, intent: "info",    label: "Admin — Kiracı kapsamı" },
    gm:         { icon: Users,     intent: "warning", label: "GM — Tesis kapsamı" },
  };
  const cfg = roleConfig[role] || roleConfig.admin;
  const Icon = cfg.icon;
  return (
    <span data-testid="scope-banner">
      <StatusBadge intent={cfg.intent} icon={Icon}>
        {cfg.label}{scope ? ` (${scope})` : ""}
      </StatusBadge>
    </span>
  );
}

function DataRow({ label, value, valueClass }) {
  return (
    <div className="flex justify-between text-slate-600">
      <span>{label}</span>
      <span className={valueClass || "text-slate-900"}>{value}</span>
    </div>
  );
}

/* ── WS Bridge Sparkline ─────────────────────────────────────────── */
function ErrorSparkline({ points, testId }) {
  const { t } = useTranslation();
  const series = Array.isArray(points) ? points : [];
  if (series.length < 2) {
    return (
      <div data-testid={`${testId}-empty`} className="text-[11px] text-slate-400 italic">
        {t('cm.pages_SystemHealthDashboard.trend_icin_yeterli_veri_yok_2_ornek_gere')}
      </div>
    );
  }
  const W = 220, H = 36, PAD = 2;
  const values = series.map((p) => Math.max(0, Number(p.publish_errors_delta) || 0));
  const max = Math.max(1, ...values);
  const stepX = (W - PAD * 2) / Math.max(1, values.length - 1);
  const coords = values.map((v, i) => {
    const x = PAD + i * stepX;
    const y = H - PAD - (v / max) * (H - PAD * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const linePath = coords.join(" ");
  const areaPath = `${PAD},${H - PAD} ${linePath} ${(W - PAD).toFixed(1)},${H - PAD}`;
  return (
    <svg data-testid={testId} viewBox={`0 0 ${W} ${H}`} width="100%" height={H}
      role="img" aria-label={`Son ${series.length} örnekte zirve hata sayısı ${max}`} className="block">
      <polyline points={areaPath} fill="rgba(225,29,72,0.12)" stroke="none" />
      <polyline points={linePath} fill="none" stroke="rgb(225,29,72)" strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function WSBridgePanel({ wsBridge, testIdPrefix = "ws-bridge" }) {
  const { t } = useTranslation();
  if (!wsBridge) return null;
  const detail = wsBridge.detail || {};
  const status = wsBridge.status || "unknown";
  const errors = detail.publish_errors ?? 0;
  const threshold = detail.publish_error_threshold ?? 10;
  const errorsClass = errors >= threshold ? "text-rose-700" : (errors > 0 ? "text-amber-700" : "text-slate-900");
  const lastErrAt = detail.last_publish_error_at ? new Date(detail.last_publish_error_at).toLocaleString("tr-TR") : null;
  const mode = detail.single_instance_mode ? "Tek sunucu (Redis pasif)"
    : (detail.active ? "Aktif (Redis pub/sub)" : "Pasif");

  const history = detail.metrics_history || {};
  const points = Array.isArray(history.points) ? history.points : [];
  const trend = history.error_trend || "flat";
  const errorsInWindow = history.errors_in_window ?? 0;
  const intervalMin = Math.max(1, Math.round((history.interval_seconds ?? 60) / 60));
  const windowMin = points.length * intervalMin;
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;
  const trendClass = trend === "up" ? "text-rose-600" : trend === "down" ? "text-emerald-600" : "text-slate-500";
  const trendLabel = trend === "up" ? "Hata oranı yükseliyor" : trend === "down" ? "Hata oranı düşüyor" : "Hata oranı sabit";

  return (
    <PanelCard testId={`${testIdPrefix}-panel`} title={t('cm.pages_SystemHealthDashboard.coklu_sunucu_sohbet_koprusu')} icon={Network} status={status}>
      <div className="space-y-2 text-xs">
        <DataRow label="Mod" value={mode} />
        {detail.instance_id && <DataRow label="Sunucu" value={detail.instance_id} />}
        <DataRow label={t('cm.pages_SystemHealthDashboard.aktif_kanal')} value={detail.channels_active ?? 0} />
        <DataRow label={t('cm.pages_SystemHealthDashboard.yayinlanan_mesaj')} value={detail.messages_published ?? 0} />
        <DataRow label={t('cm.pages_SystemHealthDashboard.alinan_mesaj')} value={detail.messages_received ?? 0} />
        <DataRow label={t('cm.pages_SystemHealthDashboard.iletilen_mesaj')} value={detail.messages_forwarded ?? 0} />
        <DataRow label={`Yayın hatası (≥${threshold} alarm)`} value={errors} valueClass={errorsClass} />

        <div data-testid={`${testIdPrefix}-trend`} className="mt-2 p-2 rounded border border-slate-200 bg-slate-50/60">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-semibold text-slate-700">Son {windowMin || 0} dk hata trendi</span>
            <span data-testid={`${testIdPrefix}-trend-chip`}
              className={`inline-flex items-center gap-1 text-[11px] font-medium ${trendClass}`}
              title={trendLabel} aria-label={trendLabel}>
              <TrendIcon className="w-3.5 h-3.5" />
              {trend === "up" ? "Artıyor" : trend === "down" ? "Azalıyor" : "Sabit"}
            </span>
          </div>
          <ErrorSparkline points={points} testId={`${testIdPrefix}-sparkline`} />
          <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
            <span>{points.length} {t('cm.pages_SystemHealthDashboard.ornek')}</span>
            <span>Pencerede {errorsInWindow} hata</span>
          </div>
        </div>

        {detail.last_publish_error && (
          <div data-testid={`${testIdPrefix}-last-error`} className="mt-2 p-2 rounded bg-rose-50 border border-rose-200">
            <p className="text-[11px] font-semibold text-rose-700">{t('cm.pages_SystemHealthDashboard.son_yayin_hatasi')}</p>
            <p className="text-[11px] text-rose-700 break-all">{detail.last_publish_error}</p>
            {lastErrAt && <p className="text-[10px] text-rose-500/80 mt-0.5">{lastErrAt}</p>}
          </div>
        )}
        {wsBridge.degraded_reason && (
          <p data-testid={`${testIdPrefix}-degraded`} className="text-[11px] text-amber-700">{wsBridge.degraded_reason}</p>
        )}
        {wsBridge.suggested_action && (
          <p className="text-[11px] text-sky-700">{wsBridge.suggested_action}</p>
        )}
      </div>
    </PanelCard>
  );
}

function RoomServiceLivePanel({ roomService, testIdPrefix = "room-service" }) {
  const { t } = useTranslation();
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
    <PanelCard testId={`${testIdPrefix}-panel`} title={t('cm.pages_SystemHealthDashboard.oda_servisi_canli_baglantilari')} icon={Radio} status={status}>
      <div className="space-y-2 text-xs">
        <DataRow label={t('cm.pages_SystemHealthDashboard.aktif_rezervasyonlar_bu_sunucu')} value={bookings} />
        <DataRow label={t('cm.pages_SystemHealthDashboard.misafir_soketleri')} value={guestSockets} />
        <DataRow label={t('cm.pages_SystemHealthDashboard.personel_panelleri_kiraci')} value={`${staffTenants} kiracı / ${staffSockets} soket`} />
        <DataRow label={`Son ${windowMin} dk teslim edilen güncelleme`}
          value={eventsLastHour}
          valueClass={eventsLastHour > 0 ? "text-emerald-700" : "text-slate-900"} />
        <p className="text-[10px] text-slate-500 -mt-1">
          {t('cm.pages_SystemHealthDashboard.her_ekrana_teslim_her_guncelleme_bir_kez')}
        </p>
        <div className="flex justify-between text-slate-600">
          <span>{t('cm.pages_SystemHealthDashboard.coklu_sunucu_koprusu')}</span>
          <HealthBadge status={bridgeActive ? "active" : "unknown"} />
        </div>
        <DataRow label={t('cm.pages_SystemHealthDashboard.koprude_room_service_kanali')} value={bridgeChannels} />
        {roomService.evidence_summary && (
          <p className="text-[11px] text-slate-500 mt-1">{roomService.evidence_summary}</p>
        )}
      </div>
    </PanelCard>
  );
}

/* ── GM Property Panel ───────────────────────────────────── */
function GMPropertyView({ cmStatus, alerts }) {
  const { t } = useTranslation();
  const alertCount = alerts?.count || 0;
  const criticalAlerts = alerts?.critical || 0;
  const driftActive = cmStatus?.drift?.active_drifts || 0;

  return (
    <div data-testid="gm-property-view" className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <MetricCard testId="gm-metric-cm" icon={Wifi} title="Kanal senkronu" value={cmStatus?.health || "—"} sub={`${cmStatus?.active_connections || 0} aktif`} />
        <MetricCard testId="gm-metric-drift" icon={AlertTriangle} title={t('cm.pages_SystemHealthDashboard.sapma_sorunlari')} value={driftActive} sub={driftActive > 0 ? "İnceleme gerekli" : "Senkron"} />
        <MetricCard testId="gm-metric-alerts" icon={AlertTriangle} title="Alarmlar" value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} kritik` : "Temiz"} />
        <MetricCard testId="gm-metric-recon" icon={CheckCircle2} title="Mutabakat" value={cmStatus?.reconciliation?.status || "OK"}
          sub={cmStatus?.reconciliation?.unresolved_issues > 0 ? `${cmStatus.reconciliation.unresolved_issues} sorun` : "Çözüldü"} />
      </div>

      <PanelCard testId="gm-panel-cm" title={t('cm.pages_SystemHealthDashboard.kanal_yoneticisi_tesis')} icon={Wifi} status={cmStatus?.health} permissionGated>
        <div className="space-y-2 text-xs">
          <DataRow label="Senkron durumu" value={cmStatus?.sync_stats?.last_sync ? "Aktif" : "Boşta"} />
          <DataRow label={t('cm.pages_SystemHealthDashboard.senkron_basari_orani')} value={`${cmStatus?.sync_stats?.success_rate ?? 100}%`} />
          <DataRow label={t('cm.pages_SystemHealthDashboard.sapma_sorunlari_d7fbf')} value={driftActive} valueClass={driftActive > 0 ? "text-amber-700" : "text-slate-900"} />
          <DataRow label={t('cm.pages_SystemHealthDashboard.saglayicilar')} value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
        </div>
      </PanelCard>

      <PanelCard testId="gm-panel-alerts" title={t('cm.pages_SystemHealthDashboard.tesis_alarmlari')} icon={AlertTriangle}
        status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
        {alerts?.alerts?.length > 0 ? (
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {alerts.alerts.map((a, i) => (
              <div key={i} className="flex items-start gap-2 p-2 rounded bg-white border border-slate-200">
                <SeverityChip severity={a.severity} />
                <div className="min-w-0">
                  <p className="text-xs text-slate-700 truncate">{a.message || a.type}</p>
                  {a.metric && <p className="text-[11px] text-slate-600">{a.metric}: {a.value}</p>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={CheckCircle2} message="Aktif tesis alarmı yok" />
        )}
      </PanelCard>
    </div>
  );
}

/* ── Admin Tenant Panel ─────────────────────────────────── */
function AdminTenantView(props) {
  const { t } = useTranslation();
  const { cmStatus, queueHealth, secAudit, rateLimit, tenantGuard, logSanit, alerts, stuckTasks, auditMetrics, wsBridge, roomService, triggerDriftScan, driftScanLoading, triggerRecon, reconLoading, canTrigger } = props;
  const alertCount = alerts?.count || 0;
  const criticalAlerts = alerts?.critical || 0;

  return (
    <div data-testid="admin-tenant-view" className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <MetricCard testId="admin-metric-cm" icon={Wifi} title={t('cm.pages_SystemHealthDashboard.kanal_yoneticisi')} value={cmStatus?.health || "—"} sub={`${cmStatus?.active_connections || 0} bağlantı`} />
        <MetricCard testId="admin-metric-queue" icon={Database} title={t('cm.pages_SystemHealthDashboard.kuyruk_sagligi')} value={queueHealth?.health || "—"} sub={`${queueHealth?.pending || 0} bekleyen`} />
        <MetricCard testId="admin-metric-alerts" icon={AlertTriangle} title={t('cm.pages_SystemHealthDashboard.aktif_alarmlar')} value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} kritik` : "Temiz"} />
        <MetricCard testId="admin-metric-stuck" icon={Clock} title={t('cm.pages_SystemHealthDashboard.takili_gorevler')} value={stuckTasks?.count || 0} sub={stuckTasks?.count > 0 ? "Aksiyon gerekli" : "Yok"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PanelCard testId="admin-panel-cm" title={t('cm.pages_SystemHealthDashboard.kanal_yoneticisi_53252')} icon={Wifi} status={cmStatus?.health}
          onAction={canTrigger ? triggerDriftScan : undefined} actionLabel="Sapma taraması" actionLoading={driftScanLoading}>
          <div className="space-y-2 text-xs">
            <DataRow label="Senkron durumu" value={cmStatus?.sync_stats?.last_sync ? "Aktif" : "Boşta"} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.sapma_sorunlari_d7fbf')} value={cmStatus?.drift?.active_drifts || 0} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.senkron_basari_orani_c9fa3')} value={`${cmStatus?.sync_stats?.success_rate ?? 100}%`} />
            <div className="flex justify-between text-slate-600">
              <span>Mutabakat</span>
              <HealthBadge status={cmStatus?.reconciliation?.status || "ok"} />
            </div>
            <DataRow label={t('cm.pages_SystemHealthDashboard.saglayicilar_b696f')} value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
            {cmStatus?.sync_stats?.sync_lag_seconds != null && (
              <DataRow label="Senkron gecikmesi" value={`${Math.round(cmStatus.sync_stats.sync_lag_seconds / 60)}dk`} />
            )}
            {canTrigger && (
              <Button data-testid="admin-run-recon-btn" variant="outline" size="sm" onClick={triggerRecon} disabled={reconLoading} className="w-full mt-2">
                {reconLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
                {t('cm.pages_SystemHealthDashboard.mutabakati_calistir')}
              </Button>
            )}
          </div>
        </PanelCard>

        <PanelCard testId="admin-panel-queue" title={t('cm.pages_SystemHealthDashboard.kuyruk_isciler')} icon={Server} status={queueHealth?.health}>
          <div className="space-y-2 text-xs">
            <DataRow label={t('cm.pages_SystemHealthDashboard.bekleyen_gorevler')} value={queueHealth?.pending || 0} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.isleniyor')} value={queueHealth?.processing || 0} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.basarisiz')} value={queueHealth?.failed || 0} valueClass={(queueHealth?.failed || 0) > 0 ? "text-rose-700" : "text-slate-900"} />
            <DataRow label="Doluluk" value={`${queueHealth?.saturation_pct ?? 0}%`} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.takili_gorevler_9fac9')} value={stuckTasks?.count || 0} valueClass={(stuckTasks?.count || 0) > 0 ? "text-amber-700" : "text-slate-900"} />
            <DataRow label="Dead-letter" value={queueHealth?.dead_letter?.total || 0} />
            <div className="flex justify-between text-slate-600">
              <span>{t('cm.pages_SystemHealthDashboard.isciler')}</span>
              <HealthBadge status={queueHealth?.worker_heartbeat?.responding ? "active" : "critical"} />
            </div>
          </div>
        </PanelCard>

        <PanelCard testId="admin-panel-security" title={t('cm.pages_SystemHealthDashboard.guvenlik_runtime')} icon={Shield}
          status={secAudit?.severity === "critical" ? "critical" : (secAudit?.severity === "warning" ? "degraded" : "active")}>
          <div className="space-y-2 text-xs">
            <DataRow label="Denetim skoru" value={`${secAudit?.completeness_score ?? "—"}%`} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.denetim_aciklari')} value={secAudit?.gaps_found || 0} valueClass={(secAudit?.gaps_found || 0) > 0 ? "text-amber-700" : "text-slate-900"} />
            <div className="flex justify-between text-slate-600"><span>{t('cm.pages_SystemHealthDashboard.hiz_sinirlama')}</span><HealthBadge status={rateLimit?.enforcement || "active"} /></div>
            {rateLimit?.burst_detected && <DataRow label="Patlama tespit" value="Evet" valueClass="text-rose-700" />}
            <div className="flex justify-between text-slate-600"><span>{t('cm.pages_SystemHealthDashboard.kiraci_izolasyonu')}</span><HealthBadge status={tenantGuard?.enforcement || "active"} /></div>
            <DataRow label={t('cm.pages_SystemHealthDashboard.ihlaller')} value={tenantGuard?.total_violations || 0} valueClass={(tenantGuard?.total_violations || 0) > 0 ? "text-rose-700" : "text-slate-900"} />
            <DataRow label="Log sanitizasyonu" value={logSanit?.all_patterns_working ? "Tamam" : "Sorun"} />
          </div>
        </PanelCard>

        <PanelCard testId="admin-panel-alerts" title={t('cm.pages_SystemHealthDashboard.runtime_alarmlari')} icon={AlertTriangle}
          status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
          {alerts?.alerts?.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {alerts.alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-white border border-slate-200">
                  <SeverityChip severity={a.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-slate-700 truncate">{a.message || a.type}</p>
                    {a.metric && <p className="text-[11px] text-slate-600">{a.metric}: {a.value}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} message="Aktif alarm yok" />
          )}
        </PanelCard>

        <WSBridgePanel wsBridge={wsBridge} testIdPrefix="admin-ws-bridge" />
        <RoomServiceLivePanel roomService={roomService} testIdPrefix="admin-room-service" />
      </div>

      {auditMetrics && (
        <div>
          <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4" /> {t('cm.pages_SystemHealthDashboard.denetim_gozlemlenebilirlik')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <MetricCard testId="admin-audit-drift" icon={Eye} title={t('cm.pages_SystemHealthDashboard.sapma_taramasi')} value={auditMetrics.drift?.scans_count ?? 0} sub={`${auditMetrics.drift?.total_drifts ?? 0} sapma`} />
            <MetricCard testId="admin-audit-recon" icon={CheckCircle2} title={t('cm.pages_SystemHealthDashboard.mutabakat_basarisi')} value={`${auditMetrics.reconciliation?.success_rate ?? 100}%`} sub={`${auditMetrics.reconciliation?.total_runs ?? 0} koşu`} />
            <MetricCard testId="admin-audit-backlog" icon={Database} title="Kuyruk birikimi" value={auditMetrics.queue?.current_pending ?? 0} sub={`${auditMetrics.queue?.current_stuck ?? 0} takılı`} />
            <MetricCard testId="admin-audit-violations" icon={Shield} title={t('cm.pages_SystemHealthDashboard.ihlaller_92982')} value={auditMetrics.security?.violations_period ?? 0} sub="Son 24 saat" />
            <MetricCard testId="admin-audit-dl" icon={XCircle} title="Dead-letter" value={auditMetrics.dead_letter?.total ?? 0} sub={`+${auditMetrics.dead_letter?.new_in_period ?? 0} yeni`} />
            <MetricCard testId="admin-audit-total" icon={AlertTriangle} title={t('cm.pages_SystemHealthDashboard.toplam_alarm')} value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} kritik` : "Temiz"} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Superadmin Global Panel ─────────────────────────────── */
function SuperadminGlobalView(props) {
  const { t } = useTranslation();
  const { cmStatus, queueHealth, secAudit, rateLimit, tenantGuard, logSanit, alerts, stuckTasks, metrics, auditMetrics, normalizedOverview, wsBridge, roomService, triggerDriftScan, driftScanLoading, triggerRecon, reconLoading, canTrigger } = props;
  const alertCount = alerts?.count || 0;
  const criticalAlerts = alerts?.critical || 0;

  return (
    <div data-testid="superadmin-global-view" className="space-y-4">
      {criticalAlerts > 0 && (
        <div data-testid="sa-critical-banner" className="p-3 rounded-lg bg-rose-50 border border-rose-200 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-700 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-rose-800">{criticalAlerts} kritik alarm — global kapsam</p>
            <p className="text-xs text-rose-700 mt-0.5">{t('cm.pages_SystemHealthDashboard.acil_capraz_kiraci_mudahale_gerekli')}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PanelCard testId="sa-panel-cm" title={t('cm.pages_SystemHealthDashboard.kanal_yoneticisi_global')} icon={Wifi} status={cmStatus?.health}
          onAction={canTrigger ? triggerDriftScan : undefined} actionLabel="Sapma taraması" actionLoading={driftScanLoading}>
          <div className="space-y-2 text-xs">
            <DataRow label="Senkron durumu" value={cmStatus?.sync_stats?.last_sync ? "Aktif" : "Boşta"} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.sapma_sorunlari_d7fbf')} value={cmStatus?.drift?.active_drifts || 0} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.senkron_basari_orani_c9fa3')} value={`${cmStatus?.sync_stats?.success_rate ?? 100}%`} />
            <div className="flex justify-between text-slate-600"><span>Mutabakat</span><HealthBadge status={cmStatus?.reconciliation?.status || "ok"} /></div>
            <DataRow label={t('cm.pages_SystemHealthDashboard.saglayicilar_b696f')} value={`${cmStatus?.providers?.healthy || 0} / ${cmStatus?.providers?.total || 0}`} />
            {cmStatus?.sync_stats?.sync_lag_seconds != null && <DataRow label="Senkron gecikmesi" value={`${Math.round(cmStatus.sync_stats.sync_lag_seconds / 60)}dk`} />}
            {canTrigger && (
              <Button data-testid="sa-run-recon-btn" variant="outline" size="sm" onClick={triggerRecon} disabled={reconLoading} className="w-full mt-2">
                {reconLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
                {t('cm.pages_SystemHealthDashboard.mutabakati_calistir_b0906')}
              </Button>
            )}
          </div>
        </PanelCard>

        <PanelCard testId="sa-panel-queue" title={t('cm.pages_SystemHealthDashboard.kuyruk_isciler_global')} icon={Server} status={queueHealth?.health}>
          <div className="space-y-2 text-xs">
            <DataRow label={t('cm.pages_SystemHealthDashboard.bekleyen_gorevler_4cb10')} value={queueHealth?.pending || 0} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.isleniyor_41e28')} value={queueHealth?.processing || 0} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.basarisiz_3260d')} value={queueHealth?.failed || 0} valueClass={(queueHealth?.failed || 0) > 0 ? "text-rose-700" : "text-slate-900"} />
            <DataRow label="Doluluk" value={`${queueHealth?.saturation_pct ?? 0}%`} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.takili_gorevler_9fac9')} value={stuckTasks?.count || 0} valueClass={(stuckTasks?.count || 0) > 0 ? "text-amber-700" : "text-slate-900"} />
            <DataRow label="Dead-letter" value={queueHealth?.dead_letter?.total || 0} />
            <div className="flex justify-between text-slate-600">
              <span>{t('cm.pages_SystemHealthDashboard.isciler_19594')}</span>
              <HealthBadge status={queueHealth?.worker_heartbeat?.responding ? "active" : "critical"} />
            </div>
          </div>
        </PanelCard>

        <PanelCard testId="sa-panel-security" title={t('cm.pages_SystemHealthDashboard.guvenlik_durusu_global')} icon={Shield}
          status={secAudit?.severity === "critical" ? "critical" : (secAudit?.severity === "warning" ? "degraded" : "active")}>
          <div className="space-y-2 text-xs">
            <DataRow label="Denetim skoru" value={`${secAudit?.completeness_score ?? "—"}%`} />
            <DataRow label={t('cm.pages_SystemHealthDashboard.denetim_aciklari_6bd7a')} value={secAudit?.gaps_found || 0} valueClass={(secAudit?.gaps_found || 0) > 0 ? "text-amber-700" : "text-slate-900"} />
            <div className="flex justify-between text-slate-600"><span>{t('cm.pages_SystemHealthDashboard.hiz_sinirlama_50ab4')}</span><HealthBadge status={rateLimit?.enforcement || "active"} /></div>
            {rateLimit?.burst_detected && <DataRow label="Patlama tespit" value="Evet" valueClass="text-rose-700" />}
            <div className="flex justify-between text-slate-600"><span>{t('cm.pages_SystemHealthDashboard.kiraci_izolasyonu_740eb')}</span><HealthBadge status={tenantGuard?.enforcement || "active"} /></div>
            <DataRow label={t('cm.pages_SystemHealthDashboard.capraz_kiraci_ihlaller')} value={tenantGuard?.total_violations || 0} valueClass={(tenantGuard?.total_violations || 0) > 0 ? "text-rose-700" : "text-slate-900"} />
            <DataRow label="Log sanitizasyonu" value={logSanit?.all_patterns_working ? "Tamam" : "Sorun"} />
          </div>
        </PanelCard>

        <PanelCard testId="sa-panel-alerts" title="Global alarmlar" icon={AlertTriangle}
          status={criticalAlerts > 0 ? "critical" : alertCount > 0 ? "degraded" : "healthy"}>
          {alerts?.alerts?.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {alerts.alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-white border border-slate-200">
                  <SeverityChip severity={a.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-slate-700 truncate">{a.message || a.type}</p>
                    {a.metric && <p className="text-[11px] text-slate-600">{a.metric}: {a.value}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} message="Global ölçekte aktif alarm yok" />
          )}
        </PanelCard>

        <WSBridgePanel wsBridge={wsBridge} testIdPrefix="sa-ws-bridge" />
        <RoomServiceLivePanel roomService={roomService} testIdPrefix="sa-room-service" />
      </div>

      {auditMetrics && (
        <div>
          <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4" /> {t('cm.pages_SystemHealthDashboard.denetim_gozlemlenebilirlik_global')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <MetricCard testId="sa-audit-drift" icon={Eye} title={t('cm.pages_SystemHealthDashboard.sapma_taramasi_d7f10')} value={auditMetrics.drift?.scans_count ?? 0} sub={`${auditMetrics.drift?.total_drifts ?? 0} sapma`} />
            <MetricCard testId="sa-audit-recon" icon={CheckCircle2} title={t('cm.pages_SystemHealthDashboard.mutabakat_basarisi_5f3f5')} value={`${auditMetrics.reconciliation?.success_rate ?? 100}%`} sub={`${auditMetrics.reconciliation?.total_runs ?? 0} koşu`} />
            <MetricCard testId="sa-audit-backlog" icon={Database} title="Kuyruk birikimi" value={auditMetrics.queue?.current_pending ?? 0} sub={`${auditMetrics.queue?.current_stuck ?? 0} takılı`} />
            <MetricCard testId="sa-audit-violations" icon={Shield} title={t('cm.pages_SystemHealthDashboard.ihlaller_92982')} value={auditMetrics.security?.violations_period ?? 0} sub="Son 24 saat" />
            <MetricCard testId="sa-audit-dl" icon={XCircle} title="Dead-letter" value={auditMetrics.dead_letter?.total ?? 0} sub={`+${auditMetrics.dead_letter?.new_in_period ?? 0} yeni`} />
            <MetricCard testId="sa-audit-total" icon={AlertTriangle} title={t('cm.pages_SystemHealthDashboard.toplam_alarm_c2c15')} value={alertCount} sub={criticalAlerts > 0 ? `${criticalAlerts} kritik` : "Temiz"} />
          </div>
        </div>
      )}

      {metrics && (
        <div>
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Runtime metrikleri (Global)</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {metrics.sync && <MetricCard testId="sa-rt-sync" icon={Clock} title="Senkron gecikmesi" value={`${metrics.sync.lag_seconds ?? 0}sn`} />}
            {metrics.drift && <MetricCard testId="sa-rt-drift" icon={AlertTriangle} title={t('cm.pages_SystemHealthDashboard.aktif_sapmalar')} value={metrics.drift.active_count ?? 0} />}
            {metrics.reconciliation && <MetricCard testId="sa-rt-recon" icon={CheckCircle2} title={t('cm.pages_SystemHealthDashboard.mutabakat_orani')} value={`${metrics.reconciliation.success_rate ?? 100}%`} />}
            {metrics.queue && <MetricCard testId="sa-rt-queue" icon={Database} title="Kuyruk" value={metrics.queue.backlog ?? 0} />}
            {metrics.security && <MetricCard testId="sa-rt-sec" icon={Shield} title={t('cm.pages_SystemHealthDashboard.ihlaller_92982')} value={metrics.security.violations ?? 0} />}
          </div>
        </div>
      )}

      {normalizedOverview?.subsystems && (
        <div>
          <h2 className="text-sm font-semibold text-slate-700 mb-3">{t('cm.pages_SystemHealthDashboard.alt_sistem_sagligi_global')}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {Object.entries(normalizedOverview.subsystems).map(([key, sub]) => (
              <div key={key} data-testid={`normalized-${key}`} className="p-3 rounded-lg bg-white border border-slate-200">
                <div className="flex items-center justify-between mb-2 gap-2">
                  <span className="text-xs font-medium text-slate-700 capitalize truncate">{key.replace(/_/g, " ")}</span>
                  <HealthBadge status={sub.status} />
                </div>
                <div className="text-[11px] text-slate-600 space-y-1">
                  <SeverityChip severity={sub.severity} />
                  {sub.evidence_summary && <p className="mt-1 text-slate-600">{sub.evidence_summary}</p>}
                  {sub.degraded_reason && <p className="text-amber-700">{sub.degraded_reason}</p>}
                  {sub.suggested_action && <p className="text-sky-700">{sub.suggested_action}</p>}
                  <p className="text-slate-500">
                    {t('cm.pages_SystemHealthDashboard.guncellendi')} {sub.last_updated_at ? new Date(sub.last_updated_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }) : "—"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Skeletons (no full-screen flash) ─────────────────────── */
function DashboardSkeleton() {
  return (
    <div data-testid="system-health-skeleton" className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {[0,1,2,3,4].map(i => <Skeleton key={i} className="h-24" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[0,1,2,3].map(i => <Skeleton key={i} className="h-48" />)}
      </div>
    </div>
  );
}

/* ── Main Dashboard ──────────────────────────────────────── */
export default function SystemHealthDashboard({ user }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
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
  const [pilotReadiness, setPilotReadiness] = useState(null);
  const [rnlSummary, setRnlSummary] = useState(null);
  const socketRef = useRef(null);
  const pollTimerRef = useRef(null);
  const lastCriticalFetchRef = useRef(0);
  const fetchInFlightRef = useRef(false);

  /* ── Fetch ────────────────────────────────────────────── */
  // Not: axios baseURL & Authorization interceptor App.jsx'de tanımlı —
  // burada manuel header geçmeyiz (silent refresh / 401 işlemleri çalışsın).
  const fetchAll = useCallback(async ({ silent = false } = {}) => {
    if (fetchInFlightRef.current) return; // basit guard
    fetchInFlightRef.current = true;
    if (silent) setRefreshing(true);
    try {
      const [cm, q, audit, rl, tg, ls, al, mt, st, norm, role, am, pr, rnl] = await Promise.allSettled([
        axios.get(`/channel-manager/runtime/status`),
        axios.get(`/workers/queues/health`),
        axios.get(`/security/audit/status`),
        axios.get(`/security/rate-limit/status`),
        axios.get(`/security/tenant-guard/status`),
        axios.get(`/security/log-sanitization/status`),
        axios.get(`/observability/runtime/alerts`),
        axios.get(`/observability/runtime/metrics`),
        axios.get(`/workers/tasks/stuck`),
        axios.get(`/system-health/normalized/overview`),
        axios.get(`/system-health/role-dashboard`),
        axios.get(`/system-health/audit/metrics`),
        axios.get(`/production-golive/readiness`),
        // Task #233: super-admin only; non-super-admins get 403 and the
        // widget is hidden — that's fine, Promise.allSettled swallows it.
        axios.get(`/admin/db/room-night-lock-duplicates/summary`),
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
      if (pr.status === "fulfilled") setPilotReadiness(pr.value.data);
      if (rnl.status === "fulfilled") setRnlSummary(rnl.value.data);
      else if (rnl.status === "rejected") setRnlSummary(null);

      // Eğer hepsi reddedildiyse kullanıcıya bildir (sessizce yutmayalım).
      const anyOk = [cm, q, audit, rl, tg, ls, al, mt, st, norm, role, am, pr].some((r) => r.status === "fulfilled");
      if (!anyOk && !silent) toast.error("Sağlık verileri alınamadı. Backend'e ulaşılamıyor olabilir.");

      setLastUpdated(new Date());
    } catch (e) {
      if (!silent) toast.error("Sağlık verileri alınamadı.");
      // İlk yüklemede hata varsa sessizce eski state'i koru
      // (refresh sırasında flash'sız kalsın diye setLoading'e dokunmuyoruz)
    } finally {
      fetchInFlightRef.current = false;
      if (silent) setRefreshing(false);
      else setLoading(false);
    }
  }, []);

  // İlk yükleme
  useEffect(() => {
    fetchAll();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── WebSocket bağlantı + polling tek effect içinde ────── */
  useEffect(() => {
    // Vite proxy host'ta socket.io aynı origin; relative bağlanırız.
    const socket = io("/", {
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
      // Filtre: yalnız warning+critical canlı strip'e işlenir, infos sessizce atılır.
      const sev = (data?.severity || "").toLowerCase();
      if (sev === "info") return;
      setLiveEvents((prev) => [data, ...prev].slice(0, 20));
      // Kritik olay fırtınasına karşı throttle: 10 sn'de bir fetchAll
      if (sev === "critical") {
        const now = Date.now();
        if (now - lastCriticalFetchRef.current >= 10000) {
          lastCriticalFetchRef.current = now;
          fetchAll({ silent: true });
        }
      }
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
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Polling: yalnız WS bağlı değilse 30 sn'de bir sessiz fetch
  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (!wsConnected) {
      pollTimerRef.current = setInterval(() => fetchAll({ silent: true }), 30000);
    }
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [wsConnected, fetchAll]);

  /* ── Eylemler ────────────────────────────────────────── */
  const userRole = roleDashboard?.role || user?.role || "admin";
  const userScope = roleDashboard?.scope || "";
  // Reconciliation/Drift sadece admin & superadmin için (GM görüntüler).
  const canTrigger = userRole === "admin" || userRole === "superadmin";

  const triggerDriftScan = async () => {
    if (!canTrigger) return;
    setDriftScanLoading(true);
    try {
      await axios.post(`/channel-manager/drift/scan`);
      toast.success("Sapma taraması başlatıldı");
      await fetchAll({ silent: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Sapma taraması başlatılamadı");
    } finally {
      setDriftScanLoading(false);
    }
  };

  const triggerRecon = async () => {
    if (!canTrigger) return;
    setReconLoading(true);
    try {
      await axios.post(`/channel-manager/reconciliation/run?auto_fix=true`);
      toast.success("Mutabakat çalıştırıldı");
      await fetchAll({ silent: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Mutabakat çalıştırılamadı");
    } finally {
      setReconLoading(false);
    }
  };

  const handleRefresh = () => {
    if (refreshing || loading) return; // debounce
    fetchAll({ silent: true });
  };

  const wsBridge = normalizedOverview?.subsystems?.ws_bridge || null;
  const roomService = normalizedOverview?.subsystems?.room_service || null;

  // KPI top-row özet (P1 #4)
  const overallStatus = (normalizedOverview?.overall_status || "unknown").toLowerCase();
  const overallMeta = STATUS_META[overallStatus] || STATUS_META.unknown;
  const cmHealth = (cmStatus?.health || "unknown").toLowerCase();
  const qHealth = (queueHealth?.health || "unknown").toLowerCase();
  const alertCount = alerts?.count || 0;
  const criticalAlerts = alerts?.critical || 0;
  const violations = tenantGuard?.total_violations || 0;
  const stuckCount = stuckTasks?.count || 0;
  const dlCount = queueHealth?.dead_letter?.total || 0;

  const kpiIntent = (status) => {
    const s = (status || "").toLowerCase();
    if (s === "healthy" || s === "ok" || s === "active") return "success";
    if (s === "degraded" || s === "warning") return "warning";
    if (s === "critical") return "danger";
    return "neutral";
  };

  const updatedLabel = useMemo(() => {
    if (!lastUpdated) return null;
    return lastUpdated.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  }, [lastUpdated]);

  return (
    <div data-testid="system-health-dashboard" className="max-w-7xl mx-auto p-4 space-y-4">
      <PageHeader
        icon={Activity}
        title={t('cm.pages_SystemHealthDashboard.sistem_sagligi')}
        subtitle={t('cm.pages_SystemHealthDashboard.runtime_sertlestirme_operasyon_konsolu')}
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <ScopeBanner role={userRole} scope={userScope} />
            <span data-testid="ws-status-badge">
              <StatusBadge intent={wsConnected ? "success" : "warning"}
                icon={wsConnected ? Radio : WifiOff}>
                {wsConnected ? "Canlı" : "Yoklama"}
              </StatusBadge>
            </span>
            {updatedLabel && (
              <span className="text-[11px] text-slate-600">{t('cm.pages_SystemHealthDashboard.guncelleme')} {updatedLabel}</span>
            )}
            <Button data-testid="refresh-all-btn" variant="outline" size="sm"
              onClick={handleRefresh} disabled={loading || refreshing}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? "animate-spin" : ""}`} />
              {t('cm.pages_SystemHealthDashboard.yenile')}
            </Button>
          </div>
        }
      />

      {/* Genel durum şeridi */}
      {normalizedOverview && (
        <div data-testid="normalized-overview-bar"
          className={`p-3 rounded-lg border flex items-center gap-3 ${
            overallStatus === "critical" ? "bg-rose-50 border-rose-200" :
            overallStatus === "degraded" ? "bg-amber-50 border-amber-200" :
            "bg-emerald-50 border-emerald-200"
          }`}>
          <Activity className="w-4 h-4 text-slate-700" />
          <span className="text-sm font-medium text-slate-900">Genel:</span>
          <HealthBadge status={overallStatus} />
          <SeverityChip severity={normalizedOverview.overall_severity} />
        </div>
      )}

      {/* Task #233: unresolved duplicate room-night locks (super-admin only).
          Hidden when count == 0 or summary endpoint isn't reachable. */}
      {!loading && rnlSummary && (rnlSummary.manual_required_count || 0) > 0 && (() => {
        const count = rnlSummary.manual_required_count || 0;
        const since = rnlSummary.active_since || rnlSummary.last_alert_at || null;
        let activeForLabel = null;
        if (since) {
          const sinceMs = Date.parse(since);
          if (!Number.isNaN(sinceMs)) {
            const delta = Math.max(0, Date.now() - sinceMs);
            const hours = Math.floor(delta / 3600000);
            const mins = Math.floor((delta % 3600000) / 60000);
            activeForLabel = hours > 0 ? `${hours}sa ${mins}dk` : `${mins}dk`;
          }
        }
        const sinceLabel = since ? new Date(since).toLocaleString("tr-TR") : null;
        return (
          <a
            data-testid="rnl-duplicates-widget"
            href="/app/admin-control-panel#rnl-duplicates"
            className="block p-3 rounded-lg border bg-rose-50 border-rose-200 hover:bg-rose-100/70 transition-colors"
          >
            <div className="flex items-center gap-3 flex-wrap">
              <ShieldAlert className="w-5 h-5 text-rose-700 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-rose-800">
                  {t('rnlDuplicates.widgetTitle', { count })}
                </p>
                <p className="text-[11px] text-rose-700 mt-0.5">
                  {since
                    ? t('rnlDuplicates.widgetActiveSince', {
                        since: sinceLabel,
                        duration: activeForLabel || '—',
                      })
                    : t('rnlDuplicates.widgetNoAlertYet')}
                </p>
              </div>
              <StatusBadge intent="danger" icon={AlertTriangle}>
                {t('rnlDuplicates.widgetInspect')}
              </StatusBadge>
            </div>
          </a>
        );
      })()}

      {/* Pilot Production Safety — readiness + CM outbox + CB + backup + observability */}
      {!loading && pilotReadiness && (() => {
        const checks = pilotReadiness.checks || {};
        const verdict = (pilotReadiness.verdict || "unknown").toUpperCase();
        const verdictIntent =
          verdict === "PASS" ? "success" :
          verdict === "REVIEW" ? "warning" :
          verdict === "FAIL" ? "danger" : "neutral";
        const ox = checks.cm_outbox || {};
        const cb = checks.cm_circuit_breakers || {};
        const bk = checks.backup || {};
        const ob = checks.observability || {};
        const oxIntent =
          ox.status === "fail" ? "danger" :
          ox.status === "degraded" ? "warning" :
          ox.status === "ok" ? "success" : "neutral";
        const cbIntent =
          cb.status === "fail" ? "danger" :
          cb.status === "degraded" ? "warning" :
          cb.status === "ok" ? "success" : "neutral";
        const bkIntent =
          bk.status === "atlas_managed" || bk.status === "ok" ? "success" :
          bk.status === "degraded" ? "warning" :
          bk.status === "fail" ? "danger" : "neutral";
        const sentryActive = ob.sentry_active === true;
        const otelActive = ob.otel_active === true;
        const obIntent =
          (sentryActive && otelActive) ? "success" :
          (sentryActive || otelActive) ? "warning" :
          ob.status === "active" ? "success" : "danger";
        return (
          <div data-testid="pilot-production-safety" className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <Shield className="w-4 h-4 text-slate-600" />
                Pilot Production Safety
              </h3>
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <span title="docs/REPLIT_OPS_CHEATSHEET.md" className="cursor-help">OPS Cheat-sheet</span>
                <span>·</span>
                <span title="docs/PILOT_FIRST_24H_MONITORING.md" className="cursor-help">İlk 24h Runbook</span>
                <span>·</span>
                <span title="docs/CM_OBSERVABILITY.md" className="cursor-help">CM Observability</span>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <KpiCard icon={CheckCircle2} label="Readiness"
                value={verdict}
                sub={typeof pilotReadiness.score === "number" ? `Skor ${(pilotReadiness.score * 100).toFixed(0)}/100` : "—"}
                intent={verdictIntent} />
              <KpiCard icon={Database} label="CM Outbox"
                value={ox.backlog ?? 0}
                sub={ox.failed > 0 ? `${ox.failed} failed` : (ox.oldest_seconds != null ? `En eski ${Math.round(ox.oldest_seconds)}s` : "Temiz")}
                intent={oxIntent} />
              <KpiCard icon={Network} label="Circuit Breakers"
                value={`${cb.open ?? 0} / ${cb.total ?? 0}`}
                sub={cb.half_open > 0 ? `${cb.half_open} half-open` : "OPEN / Toplam"}
                intent={cbIntent} />
              <KpiCard icon={Server} label="Atlas Backup"
                value={bk.status === "atlas_managed" ? "Atlas Managed" : (STATUS_META[bk.status]?.label || bk.status || "—")}
                sub={bk.tier ? `Tier ${bk.tier}` : "Yedek durumu"}
                intent={bkIntent} />
              <KpiCard icon={Eye} label="Observability"
                value={(sentryActive && otelActive) ? "Sentry + OTel" : sentryActive ? "Sentry" : otelActive ? "OTel" : "Pasif"}
                sub={(sentryActive || otelActive) ? "Aktif" : "Yapılandırma eksik"}
                intent={obIntent} />
            </div>
          </div>
        );
      })()}

      {/* KPI satırı — Sprint A KpiCard intent palette */}
      {!loading && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <KpiCard icon={Wifi} label={t('cm.pages_SystemHealthDashboard.kanal_yoneticisi_53252')}
            value={overallMeta.label === "Bilinmiyor" ? "—" : (STATUS_META[cmHealth]?.label || cmHealth)}
            sub={`${cmStatus?.active_connections || 0} bağlantı`}
            intent={kpiIntent(cmHealth)} />
          <KpiCard icon={Database} label={t('cm.pages_SystemHealthDashboard.kuyruk_sagligi_2d447')}
            value={STATUS_META[qHealth]?.label || qHealth}
            sub={`${queueHealth?.pending || 0} bekleyen`}
            intent={kpiIntent(qHealth)} />
          <KpiCard icon={AlertTriangle} label="Alarmlar" value={alertCount}
            sub={criticalAlerts > 0 ? `${criticalAlerts} kritik` : "Temiz"}
            intent={criticalAlerts > 0 ? "danger" : alertCount > 0 ? "warning" : "success"} />
          <KpiCard icon={Shield} label={t('cm.pages_SystemHealthDashboard.izolasyon_ihlalleri')} value={violations}
            sub="Çapraz-kiracı"
            intent={violations > 0 ? "danger" : "success"} />
          <KpiCard icon={Clock} label={t('cm.pages_SystemHealthDashboard.takili_dead_letter')}
            value={`${stuckCount} / ${dlCount}`}
            sub="Takılı / Dead-letter"
            intent={(stuckCount + dlCount) > 0 ? "warning" : "neutral"} />
        </div>
      )}

      {/* Skeleton (ilk yükleme — refresh'te göstermez) */}
      {loading && <DashboardSkeleton />}

      {/* Canlı olay şeridi (sadece warning+critical) */}
      {!loading && liveEvents.length > 0 && (
        <div data-testid="live-events-strip" className="flex gap-2 overflow-x-auto pb-1">
          {liveEvents.slice(0, 8).map((ev, i) => (
            <div key={i} className="flex-shrink-0 px-3 py-1.5 rounded-md bg-white border border-slate-200 text-[11px] flex items-center gap-2">
              <Zap className="w-3 h-3 text-amber-600" />
              <SeverityChip severity={ev.severity || "info"} />
              <span className="text-slate-700">{ev.event_type}</span>
              <span className="text-slate-500">
                {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }) : ""}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Rol bazlı içerik (skeleton bittikten sonra) */}
      {!loading && userRole === "gm" && (
        <GMPropertyView cmStatus={cmStatus} alerts={alerts} />
      )}

      {!loading && userRole === "admin" && (
        <AdminTenantView
          cmStatus={cmStatus} queueHealth={queueHealth} secAudit={secAudit}
          rateLimit={rateLimit} tenantGuard={tenantGuard} logSanit={logSanit}
          alerts={alerts} stuckTasks={stuckTasks} auditMetrics={auditMetrics}
          wsBridge={wsBridge} roomService={roomService}
          triggerDriftScan={triggerDriftScan} driftScanLoading={driftScanLoading}
          triggerRecon={triggerRecon} reconLoading={reconLoading}
          canTrigger={canTrigger}
        />
      )}

      {!loading && (userRole === "superadmin" || (userRole !== "gm" && userRole !== "admin")) && (
        <SuperadminGlobalView
          cmStatus={cmStatus} queueHealth={queueHealth} secAudit={secAudit}
          rateLimit={rateLimit} tenantGuard={tenantGuard} logSanit={logSanit}
          alerts={alerts} stuckTasks={stuckTasks} metrics={metrics}
          auditMetrics={auditMetrics} normalizedOverview={normalizedOverview}
          wsBridge={wsBridge} roomService={roomService}
          triggerDriftScan={triggerDriftScan} driftScanLoading={driftScanLoading}
          triggerRecon={triggerRecon} reconLoading={reconLoading}
          canTrigger={canTrigger}
        />
      )}
    </div>
  );
}
