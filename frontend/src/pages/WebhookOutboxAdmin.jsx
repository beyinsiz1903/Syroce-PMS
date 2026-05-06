import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { confirmDialog } from '@/lib/dialogs';
import {
  Activity, RefreshCw, Send, AlertTriangle, CheckCircle2,
  XCircle, Clock, Inbox, RotateCcw, Trash2,
} from "lucide-react";

const STATUS_COLOR = {
  pending: "bg-blue-500/10 text-blue-600 border-blue-500/30",
  processing: "bg-amber-500/10 text-amber-600 border-amber-500/30",
  delivering: "bg-amber-500/10 text-amber-600 border-amber-500/30",
  retry: "bg-orange-500/10 text-orange-600 border-orange-500/30",
  retrying: "bg-orange-500/10 text-orange-600 border-orange-500/30",
  succeeded: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
  processed: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
  failed: "bg-red-500/10 text-red-600 border-red-500/30",
  dlq: "bg-red-500/10 text-red-600 border-red-500/30",
  dismissed: "bg-slate-500/10 text-slate-500 border-slate-500/30",
  resolved: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
};

const fmtDate = (iso) => {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("tr-TR", {
      day: "2-digit", month: "2-digit", year: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return iso; }
};

const StatusBadge = ({ status }) => (
  <Badge variant="outline" className={STATUS_COLOR[status] || "bg-slate-100"}>
    {status}
  </Badge>
);

const StatTile = ({ icon: Icon, label, value, tone = "slate" }) => {
  const toneMap = {
    slate: "text-slate-600 bg-slate-50",
    blue: "text-blue-600 bg-blue-50",
    amber: "text-amber-600 bg-amber-50",
    red: "text-red-600 bg-red-50",
    emerald: "text-emerald-600 bg-emerald-50",
  };
  return (
    <div className={`rounded-lg p-3 ${toneMap[tone]}`}>
      <div className="flex items-center gap-2 text-xs font-medium opacity-80">
        <Icon className="w-3.5 h-3.5" />
        {label}
      </div>
      <div className="text-2xl font-bold mt-1">{value ?? "-"}</div>
    </div>
  );
};

export default function WebhookOutboxAdmin({ user, tenant, onLogout }) {
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

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [oStatus, wStatus, oEvents, dlq, dlv] = await Promise.allSettled([
        axios.get("/outbox/status"),
        axios.get("/webhooks/status"),
        axios.get("/outbox/events", { params: { status: outboxFilter, limit: 50 } }),
        axios.get("/webhooks/dlq", { params: { status: dlqFilter, limit: 50 } }),
        axios.get("/webhooks/deliveries", { params: { status: deliveryFilter, limit: 50 } }),
      ]);
      if (oStatus.status === "fulfilled") setOutboxStatus(oStatus.value.data);
      if (wStatus.status === "fulfilled") setWebhookStatus(wStatus.value.data);
      if (oEvents.status === "fulfilled") setOutboxEvents(oEvents.value.data.events || []);
      if (dlq.status === "fulfilled") setDlqItems(dlq.value.data.items || []);
      if (dlv.status === "fulfilled") setDeliveries(dlv.value.data.items || []);
    } catch (e) {
      toast.error("Veriler yüklenirken hata: " + (e?.message || "bilinmeyen"));
    } finally {
      setLoading(false);
    }
  }, [outboxFilter, dlqFilter, deliveryFilter]);

  useEffect(() => { loadAll(); }, [loadAll]);

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
    if (!await confirmDialog({ message: "Bu DLQ kaydını dismiss etmek istiyor musunuz? (Bir daha denenmez)", variant: 'danger' })) return;
    try {
      await axios.post(`/webhooks/dlq/${dlqId}/dismiss`);
      toast.success("DLQ kaydı dismiss edildi");
      loadAll();
    } catch (e) {
      toast.error("Dismiss başarısız: " + (e?.response?.data?.detail || e?.message));
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="webhook-outbox-admin">
      <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Inbox className="w-6 h-6 text-blue-600" />
              Outbox & Webhook Admin
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Olay kuyruğu, webhook teslimatları ve DLQ yönetimi
            </p>
          </div>
          <Button onClick={loadAll} disabled={loading} variant="outline" size="sm">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            Yenile
          </Button>
        </div>

        {/* Status overview */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatTile icon={Clock} label="Outbox Pending" value={outboxStatus?.pending} tone="blue" />
          <StatTile icon={RotateCcw} label="Outbox Retry" value={outboxStatus?.retry} tone="amber" />
          <StatTile icon={XCircle} label="Outbox Failed" value={outboxStatus?.failed} tone="red" />
          <StatTile icon={CheckCircle2} label="Outbox 24s OK" value={outboxStatus?.processed_24h} tone="emerald" />
          <StatTile icon={AlertTriangle} label="DLQ Pending" value={webhookStatus?.dlq_pending} tone="red" />
          <StatTile icon={Send} label="Webhook 24s OK" value={webhookStatus?.deliveries_succeeded_24h} tone="emerald" />
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="outbox">Outbox Olayları</TabsTrigger>
            <TabsTrigger value="dlq">Webhook DLQ</TabsTrigger>
            <TabsTrigger value="deliveries">Webhook Teslimatları</TabsTrigger>
          </TabsList>

          {/* ─── OUTBOX EVENTS ───────────────────────────────── */}
          <TabsContent value="outbox" className="space-y-3">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Activity className="w-4 h-4" /> Outbox Olayları
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Select value={outboxFilter} onValueChange={setOutboxFilter}>
                    <SelectTrigger className="w-40 h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="failed">Başarısız</SelectItem>
                      <SelectItem value="retry">Retry</SelectItem>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="processed">Processed</SelectItem>
                    </SelectContent>
                  </Select>
                  {outboxFilter === "failed" && outboxEvents.length > 0 && (
                    <Button onClick={handleReplayAll} size="sm" variant="destructive">
                      <RotateCcw className="w-3.5 h-3.5 mr-1" /> Tümünü Replay Et
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {outboxEvents.length === 0 ? (
                  <div className="py-8 text-center text-sm text-slate-500">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500" />
                    Bu filtrede kayıt yok
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[55vh] overflow-y-auto">
                    {outboxEvents.map((ev) => (
                      <div key={ev.id} className="border rounded-lg p-3 text-sm hover:bg-slate-50">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <StatusBadge status={ev.status} />
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
                              <div className="mt-2 text-xs text-red-600 bg-red-50 p-2 rounded font-mono">
                                {String(ev.last_error).slice(0, 240)}
                              </div>
                            )}
                          </div>
                          {(ev.status === "failed" || ev.status === "retry") && (
                            <Button onClick={() => handleRequeue(ev.id)} size="sm" variant="outline">
                              <RotateCcw className="w-3.5 h-3.5 mr-1" /> Requeue
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
                  <CardTitle className="text-sm">Sağlayıcı Bazlı Hata Sayıları</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(outboxStatus.provider_failures).map(([prov, count]) => (
                      <Badge key={prov} variant="outline" className="bg-red-50 text-red-600">
                        {prov}: {count}
                      </Badge>
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
                  <AlertTriangle className="w-4 h-4 text-red-600" /> Webhook DLQ (Dead Letter Queue)
                </CardTitle>
                <Select value={dlqFilter} onValueChange={setDlqFilter}>
                  <SelectTrigger className="w-40 h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="retrying">Retrying</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="dismissed">Dismissed</SelectItem>
                  </SelectContent>
                </Select>
              </CardHeader>
              <CardContent>
                {dlqItems.length === 0 ? (
                  <div className="py-8 text-center text-sm text-slate-500">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500" />
                    DLQ temiz
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[55vh] overflow-y-auto">
                    {dlqItems.map((it) => (
                      <div key={it.id} className="border rounded-lg p-3 text-sm hover:bg-slate-50">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <StatusBadge status={it.status} />
                              <span className="font-mono text-xs">{it.event}</span>
                              <span className="text-xs text-slate-400">deneme: {it.attempt_count}</span>
                            </div>
                            <div className="text-xs text-slate-500 truncate">→ {it.url}</div>
                            <div className="text-xs text-slate-500 mt-1">
                              {fmtDate(it.created_at)} · agency: {it.agency_id?.slice(0, 8) || "-"}
                            </div>
                            {it.last_error && (
                              <div className="mt-2 text-xs text-red-600 bg-red-50 p-2 rounded font-mono">
                                HTTP {it.last_status_code || "-"}: {String(it.last_error).slice(0, 240)}
                              </div>
                            )}
                          </div>
                          {it.status === "pending" && (
                            <div className="flex flex-col gap-1">
                              <Button onClick={() => handleRetryDlq(it.id)} size="sm" variant="outline">
                                <Send className="w-3.5 h-3.5 mr-1" /> Retry
                              </Button>
                              <Button onClick={() => handleDismissDlq(it.id)} size="sm" variant="ghost">
                                <Trash2 className="w-3.5 h-3.5 mr-1" /> Dismiss
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
                  <Send className="w-4 h-4" /> Webhook Teslimatları
                </CardTitle>
                <Select value={deliveryFilter} onValueChange={setDeliveryFilter}>
                  <SelectTrigger className="w-40 h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
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
                  <div className="py-8 text-center text-sm text-slate-500">
                    Bu filtrede teslimat yok
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[55vh] overflow-y-auto">
                    {deliveries.map((d) => (
                      <div key={d.id} className="border rounded-lg p-3 text-sm hover:bg-slate-50">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <StatusBadge status={d.status} />
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
                          Oluşturuldu: {fmtDate(d.created_at)}
                          {d.next_retry_at && <> · Sonraki retry: {fmtDate(d.next_retry_at)}</>}
                        </div>
                        {d.last_error && (
                          <div className="mt-2 text-xs text-red-600 bg-red-50 p-2 rounded font-mono">
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
    </Layout>
  );
}
