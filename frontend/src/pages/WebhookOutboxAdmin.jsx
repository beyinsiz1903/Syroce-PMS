import React, { useEffect, useMemo, useState, useCallback } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { toast } from "sonner";
import { confirmDialog } from "@/lib/dialogs";
import {
  Activity, RefreshCw, Send, AlertTriangle, CheckCircle2,
  XCircle, Clock, Inbox, RotateCcw, Trash2, Hourglass, ServerCrash, ShieldCheck,
} from "lucide-react";
import { useTranslation } from 'react-i18next';

// status → Sprint A intent mapping (StatusBadge intent palette: success/warning/danger/info/neutral)
const STATUS_INTENT = {
  pending: "info",
  processing: "warning",
  delivering: "warning",
  retry: "warning",
  retrying: "warning",
  succeeded: "success",
  processed: "success",
  resolved: "success",
  failed: "danger",
  dlq: "danger",
  dismissed: "neutral",
};

const fmtDate = (iso) => {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("tr-TR", {
      day: "2-digit", month: "2-digit", year: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return iso; }
};

const fmtAge = (seconds) => {
  if (seconds == null) return "-";
  const s = Math.round(Number(seconds));
  if (Number.isNaN(s)) return "-";
  if (s < 60) return `${s} sn`;
  if (s < 3600) return `${Math.round(s / 60)} dk`;
  if (s < 86400) return `${Math.round(s / 3600)} sa`;
  return `${Math.round(s / 86400)} gün`;
};

const StatusPill = ({ status }) => (
  <StatusBadge intent={STATUS_INTENT[status] || "neutral"}>
    {status}
  </StatusBadge>
);

export default function WebhookOutboxAdmin({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState("outbox");
  const [outboxStatus, setOutboxStatus] = useState(null);
  const [webhookStatus, setWebhookStatus] = useState(null);
  const [outboxEvents, setOutboxEvents] = useState([]);
  const [outboxFilter, setOutboxFilter] = useState("failed");
  const [dlqItems, setDlqItems] = useState([]);
  const [dlqFilter, setDlqFilter] = useState("pending");
  const [deliveries, setDeliveries] = useState([]);
  const [deliveryFilter, setDeliveryFilter] = useState("retrying");
  const [loading, setLoading] = useState(false);

  // Status cards her zaman gerekli, sekme/filtre bağımlılığı yok.
  // Tab listeleri ise sadece aktif sekmede + ilgili filtre değişiminde yüklenir.
  // Eski loadAll() filtre değişiminde 5 endpoint'i birden tetikliyordu —
  // 3'ü inaktif sekme için boşa gidiyordu.
  const buildParams = (val) => (val === "all" ? { limit: 50 } : { status: val, limit: 50 });

  const loadStatus = useCallback(async () => {
    const results = await Promise.allSettled([
      axios.get("/outbox/status"),
      axios.get("/webhooks/status"),
    ]);
    const [oStatus, wStatus] = results;
    if (oStatus.status === "fulfilled") setOutboxStatus(oStatus.value.data);
    if (wStatus.status === "fulfilled") setWebhookStatus(wStatus.value.data);
    const failed = results.filter((r) => r.status === "rejected");
    if (failed.length > 0) {
      const labels = ["Outbox status", "Webhook status"];
      const failedLabels = results.map((r, i) => (r.status === "rejected" ? labels[i] : null)).filter(Boolean);
      toast.warning(`Bazı durum bilgileri yüklenemedi: ${failedLabels.join(", ")}`);
    }
  }, []);

  const loadOutboxEvents = useCallback(async () => {
    try {
      const r = await axios.get("/outbox/events", { params: buildParams(outboxFilter) });
      setOutboxEvents(r.data.events || []);
    } catch (e) {
      toast.warning("Outbox olayları yüklenemedi: " + (e?.message || "bilinmeyen"));
    }
  }, [outboxFilter]);

  const loadDlq = useCallback(async () => {
    try {
      const r = await axios.get("/webhooks/dlq", { params: buildParams(dlqFilter) });
      setDlqItems(r.data.items || []);
    } catch (e) {
      toast.warning("DLQ yüklenemedi: " + (e?.message || "bilinmeyen"));
    }
  }, [dlqFilter]);

  const loadDeliveries = useCallback(async () => {
    try {
      const r = await axios.get("/webhooks/deliveries", { params: buildParams(deliveryFilter) });
      setDeliveries(r.data.items || []);
    } catch (e) {
      toast.warning("Teslimatlar yüklenemedi: " + (e?.message || "bilinmeyen"));
    }
  }, [deliveryFilter]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      // Aktif sekmenin verisi + status. Diğer sekmeler tıklandığında lazy yüklenir.
      const tabLoader = tab === "dlq" ? loadDlq : tab === "deliveries" ? loadDeliveries : loadOutboxEvents;
      await Promise.allSettled([loadStatus(), tabLoader()]);
    } finally {
      setLoading(false);
    }
  }, [tab, loadStatus, loadOutboxEvents, loadDlq, loadDeliveries]);

  // İlk mount + manuel Yenile butonu için tek effect.
  useEffect(() => { loadStatus(); }, [loadStatus]);
  // Aktif sekmeye özel: sekme veya o sekmenin filtresi değişince fetch.
  useEffect(() => { if (tab === "outbox") loadOutboxEvents(); }, [tab, loadOutboxEvents]);
  useEffect(() => { if (tab === "dlq") loadDlq(); }, [tab, loadDlq]);
  useEffect(() => { if (tab === "deliveries") loadDeliveries(); }, [tab, loadDeliveries]);

  const handleRequeue = async (eventId) => {
    try {
      await axios.post(`/outbox/${eventId}/requeue`);
      toast.success("Olay tekrar kuyruğa alındı");
      loadAll();
    } catch (e) {
      toast.error("Requeue başarısız: " + (e?.response?.data?.detail || e?.message));
    }
  };

  const handleReplayAll = async () => {
    if (!await confirmDialog({ message: "Tüm başarısız olayları tekrar kuyruğa almak istiyor musunuz?" })) return;
    try {
      const r = await axios.post("/outbox/replay");
      toast.success(`${r.data.requeued_count} olay tekrar kuyruğa alındı`);
      loadAll();
    } catch (e) {
      toast.error("Replay başarısız: " + (e?.response?.data?.detail || e?.message));
    }
  };

  const handleRetryDlq = async (dlqId) => {
    try {
      await axios.post(`/webhooks/dlq/${dlqId}/retry`);
      toast.success("Webhook tekrar gönderildi");
      loadAll();
    } catch (e) {
      toast.error("Retry başarısız: " + (e?.response?.data?.detail || e?.message));
    }
  };

  const handleDismissDlq = async (dlqId) => {
    if (!await confirmDialog({ message: "Bu DLQ kaydını dismiss etmek istiyor musunuz? (Bir daha denenmez)", variant: "danger" })) return;
    try {
      await axios.post(`/webhooks/dlq/${dlqId}/dismiss`);
      toast.success("DLQ kaydı dismiss edildi");
      loadAll();
    } catch (e) {
      toast.error("Dismiss başarısız: " + (e?.response?.data?.detail || e?.message));
    }
  };

  // KpiCard click → tab + filter senkronizasyonu
  const focusFailed = () => { setTab("outbox"); setOutboxFilter("failed"); };
  const focusRetry  = () => { setTab("outbox"); setOutboxFilter("retry"); };
  const focusPending = () => { setTab("outbox"); setOutboxFilter("pending"); };
  const focusDlq    = () => { setTab("dlq");    setDlqFilter("pending"); };

  const workerRunning = outboxStatus?.worker?.running;
  const workerHealthy = workerRunning === true;
  const workerKnown = typeof workerRunning === "boolean";

  const oldestPendingLabel = useMemo(() => {
    const s = outboxStatus?.oldest_pending_seconds;
    if (s == null) return null;
    const isStale = s > 600; // 10 dakikadan eski pending → uyarı
    return { text: fmtAge(s), stale: isStale };
  }, [outboxStatus]);

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto">
      <PageHeader
        icon={Inbox}
        title="Outbox & Webhook Admin"
        subtitle={t('cm.pages_WebhookOutboxAdmin.olay_kuyrugu_webhook_teslimatlari_ve_dlq')}
        actions={
          <Button onClick={loadAll} disabled={loading} variant="outline" size="sm">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
            {t('cm.pages_WebhookOutboxAdmin.yenile')}
          </Button>
        }
      />

      {/* Worker / kuyruk sağlık çubuğu — eski sürümde gösterilmiyordu, oysa
          worker durmuşsa pending şişer; en eski pending'in yaşı = SLA göstergesi */}
      <Card>
        <CardContent className="p-3 flex flex-wrap gap-3 items-center text-sm">
          <div className="flex items-center gap-2">
            {workerHealthy ? (
              <ShieldCheck className="w-4 h-4 text-emerald-600" aria-hidden="true" />
            ) : workerKnown ? (
              <ServerCrash className="w-4 h-4 text-rose-600" aria-hidden="true" />
            ) : (
              <ShieldCheck className="w-4 h-4 text-slate-400" aria-hidden="true" />
            )}
            <span className="font-medium">Outbox Worker:</span>
            <StatusBadge intent={workerHealthy ? "success" : (workerKnown ? "danger" : "neutral")}>
              {workerHealthy ? "Çalışıyor" : (workerKnown ? "Durdu" : "Bilinmiyor")}
            </StatusBadge>
          </div>
          <div className="h-4 w-px bg-slate-200" aria-hidden="true" />
          <div className="flex items-center gap-2">
            <Hourglass className="w-4 h-4 text-slate-500" aria-hidden="true" />
            <span className="text-slate-600">En eski bekleyen:</span>
            {oldestPendingLabel ? (
              <StatusBadge intent={oldestPendingLabel.stale ? "warning" : "neutral"}>
                {oldestPendingLabel.text}
              </StatusBadge>
            ) : (
              <span className="text-slate-400">yok</span>
            )}
          </div>
          <div className="h-4 w-px bg-slate-200" aria-hidden="true" />
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-500" aria-hidden="true" />
            <span className="text-slate-600">{t('cm.pages_WebhookOutboxAdmin.son_islenen')}</span>
            <span className="font-mono text-xs text-slate-700">{fmtDate(outboxStatus?.last_processed_at)}</span>
          </div>
          <div className="h-4 w-px bg-slate-200" aria-hidden="true" />
          <div className="flex items-center gap-2">
            <Send className="w-4 h-4 text-slate-500" aria-hidden="true" />
            <span className="text-slate-600">Son webhook:</span>
            <span className="font-mono text-xs text-slate-700">{fmtDate(webhookStatus?.last_delivery_at)}</span>
          </div>
        </CardContent>
      </Card>

      {/* KPI Grid — Sprint A KpiCard, tıklanabilir (filter+tab senkron) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard
          icon={Clock}
          label="Outbox Pending"
          value={outboxStatus?.pending ?? "-"}
          intent="info"
          active={tab === "outbox" && outboxFilter === "pending"}
          onClick={focusPending}
        />
        <KpiCard
          icon={RotateCcw}
          label="Outbox Retry"
          value={outboxStatus?.retry ?? "-"}
          intent="warning"
          active={tab === "outbox" && outboxFilter === "retry"}
          onClick={focusRetry}
        />
        <KpiCard
          icon={XCircle}
          label="Outbox Failed"
          value={outboxStatus?.failed ?? "-"}
          intent="danger"
          highlight={(outboxStatus?.failed ?? 0) > 0}
          active={tab === "outbox" && outboxFilter === "failed"}
          onClick={focusFailed}
        />
        <KpiCard
          icon={CheckCircle2}
          label="Outbox 24sa OK"
          value={outboxStatus?.processed_24h ?? "-"}
          intent="success"
        />
        <KpiCard
          icon={AlertTriangle}
          label="DLQ Pending"
          value={webhookStatus?.dlq_pending ?? "-"}
          sub={webhookStatus?.dlq_total != null ? `toplam ${webhookStatus.dlq_total}` : undefined}
          intent="danger"
          highlight={(webhookStatus?.dlq_pending ?? 0) > 0}
          active={tab === "dlq" && dlqFilter === "pending"}
          onClick={focusDlq}
        />
        <KpiCard
          icon={Send}
          label="Webhook 24sa"
          value={webhookStatus?.deliveries_succeeded_24h ?? "-"}
          sub={webhookStatus?.deliveries_failed_24h != null ? `${webhookStatus.deliveries_failed_24h} hata` : undefined}
          intent="success"
        />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="outbox">{t('cm.pages_WebhookOutboxAdmin.outbox_olaylari')}</TabsTrigger>
          <TabsTrigger value="dlq">Webhook DLQ</TabsTrigger>
          <TabsTrigger value="deliveries">{t('cm.pages_WebhookOutboxAdmin.webhook_teslimatlari')}</TabsTrigger>
        </TabsList>

        {/* ─── OUTBOX EVENTS ───────────────────────────────── */}
        <TabsContent value="outbox" className="space-y-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="w-4 h-4 text-slate-700" aria-hidden="true" /> {t('cm.pages_WebhookOutboxAdmin.outbox_olaylari_df9db')}
              </CardTitle>
              <div className="flex items-center gap-2">
                <Select value={outboxFilter} onValueChange={setOutboxFilter}>
                  <SelectTrigger className="w-40 h-8 text-xs" aria-label="Outbox filtre"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t('cm.pages_WebhookOutboxAdmin.tumu')}</SelectItem>
                    <SelectItem value="failed">{t('cm.pages_WebhookOutboxAdmin.basarisiz')}</SelectItem>
                    <SelectItem value="retry">Retry</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="processed">Processed</SelectItem>
                  </SelectContent>
                </Select>
                {(outboxFilter === "failed" || outboxFilter === "all") && outboxEvents.some((e) => e.status === "failed") && (
                  <Button onClick={handleReplayAll} size="sm" variant="outline">
                    <RotateCcw className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" /> {t('cm.pages_WebhookOutboxAdmin.basarisizlari_replay_et')}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {outboxEvents.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-500">
                  <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500" aria-hidden="true" />
                  {t('cm.pages_WebhookOutboxAdmin.bu_filtrede_kayit_yok')}
                </div>
              ) : (
                <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                  {outboxEvents.map((ev) => (
                    <div key={ev.id} className="border rounded-lg p-3 text-sm hover:bg-slate-50">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <StatusPill status={ev.status} />
                            <span className="font-mono text-xs text-slate-500">{ev.event_type || ev.event}</span>
                            {ev.provider && <Badge variant="secondary" className="text-xs">{ev.provider}</Badge>}
                            {typeof ev.attempt_count === "number" && (
                              <span className="text-xs text-slate-400">deneme: {ev.attempt_count}</span>
                            )}
                          </div>
                          <div className="text-xs text-slate-400 font-mono truncate">{ev.id}</div>
                          <div className="text-xs text-slate-500 mt-1">
                            {fmtDate(ev.created_at)} · tenant: {ev.tenant_id?.slice(0, 8) || "-"}
                          </div>
                          {ev.last_error && (
                            <div className="mt-2 text-xs text-rose-700 bg-rose-50 border border-rose-200 p-2 rounded font-mono">
                              {String(ev.last_error).slice(0, 240)}
                            </div>
                          )}
                        </div>
                        {(ev.status === "failed" || ev.status === "retry") && (
                          <Button onClick={() => handleRequeue(ev.id)} size="sm" variant="outline">
                            <RotateCcw className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" /> Requeue
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {outboxStatus?.provider_failures && Object.keys(outboxStatus.provider_failures).length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">{t('cm.pages_WebhookOutboxAdmin.saglayici_bazli_hata_sayilari')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(outboxStatus.provider_failures).map(([prov, count]) => (
                    <StatusBadge key={prov} intent="danger">
                      {prov}: {count}
                    </StatusBadge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ─── WEBHOOK DLQ ────────────────────────────────── */}
        <TabsContent value="dlq" className="space-y-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-600" aria-hidden="true" /> Webhook DLQ (Dead Letter Queue)
              </CardTitle>
              <Select value={dlqFilter} onValueChange={setDlqFilter}>
                <SelectTrigger className="w-40 h-8 text-xs" aria-label="DLQ filtre"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('cm.pages_WebhookOutboxAdmin.tumu_ff12f')}</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="retrying">Retrying</SelectItem>
                  <SelectItem value="resolved">Resolved</SelectItem>
                  <SelectItem value="dismissed">Dismissed</SelectItem>
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              {dlqItems.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-500">
                  <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500" aria-hidden="true" />
                  DLQ temiz
                </div>
              ) : (
                <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                  {dlqItems.map((it) => (
                    <div key={it.id} className="border rounded-lg p-3 text-sm hover:bg-slate-50">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <StatusPill status={it.status} />
                            <span className="font-mono text-xs">{it.event}</span>
                            <span className="text-xs text-slate-400">deneme: {it.attempt_count}</span>
                          </div>
                          <div className="text-xs text-slate-500 truncate">→ {it.url}</div>
                          <div className="text-xs text-slate-500 mt-1">
                            {fmtDate(it.created_at)} · agency: {it.agency_id?.slice(0, 8) || "-"}
                          </div>
                          {it.last_error && (
                            <div className="mt-2 text-xs text-rose-700 bg-rose-50 border border-rose-200 p-2 rounded font-mono">
                              HTTP {it.last_status_code || "-"}: {String(it.last_error).slice(0, 240)}
                            </div>
                          )}
                        </div>
                        {(it.status === "pending" || it.status === "retrying") && (
                          <div className="flex flex-col gap-1">
                            <Button onClick={() => handleRetryDlq(it.id)} size="sm" variant="outline">
                              <Send className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" /> Retry
                            </Button>
                            <Button onClick={() => handleDismissDlq(it.id)} size="sm" variant="ghost">
                              <Trash2 className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" /> Dismiss
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── DELIVERIES ─────────────────────────────────── */}
        <TabsContent value="deliveries" className="space-y-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Send className="w-4 h-4 text-slate-700" aria-hidden="true" /> {t('cm.pages_WebhookOutboxAdmin.webhook_teslimatlari_130b6')}
              </CardTitle>
              <Select value={deliveryFilter} onValueChange={setDeliveryFilter}>
                <SelectTrigger className="w-40 h-8 text-xs" aria-label="Teslimat filtre"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('cm.pages_WebhookOutboxAdmin.tumu_ff12f')}</SelectItem>
                  <SelectItem value="retrying">Retrying</SelectItem>
                  <SelectItem value="delivering">Delivering</SelectItem>
                  <SelectItem value="succeeded">Succeeded</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                  <SelectItem value="dlq">DLQ</SelectItem>
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              {deliveries.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-500">
                  Bu filtrede teslimat yok
                </div>
              ) : (
                <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                  {deliveries.map((d) => (
                    <div key={d.id} className="border rounded-lg p-3 text-sm hover:bg-slate-50">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <StatusPill status={d.status} />
                        <span className="font-mono text-xs">{d.event}</span>
                        <span className="text-xs text-slate-400">
                          {d.attempt_count}/{d.max_attempts} deneme
                        </span>
                        {d.last_status_code != null && d.last_status_code !== 0 && (
                          <Badge variant="outline" className="text-xs">HTTP {d.last_status_code}</Badge>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 truncate">→ {d.url}</div>
                      <div className="text-xs text-slate-500 mt-1">
                        {t('cm.pages_WebhookOutboxAdmin.olusturuldu')} {fmtDate(d.created_at)}
                        {d.next_retry_at && <> · Sonraki retry: {fmtDate(d.next_retry_at)}</>}
                      </div>
                      {d.last_error && (
                        <div className="mt-2 text-xs text-rose-700 bg-rose-50 border border-rose-200 p-2 rounded font-mono">
                          {String(d.last_error).slice(0, 240)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
