import { useState, useEffect, useCallback, useMemo, useRef } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from "@/components/ui/tooltip";
import { confirmDialog } from '@/lib/dialogs';
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  Calendar, Clock, Mail, Plus, Play, Pause, Trash2, Edit,
  Send, RefreshCw, AlertTriangle, CheckCircle, XCircle,
  FileText, BarChart3, Loader2, RotateCcw, Eye, ScrollText, Info,
} from "lucide-react";

const BACKEND = import.meta.env.VITE_BACKEND_URL || "";
const headers = () => ({
  "Content-Type": "application/json",
  Authorization: "Bearer " + localStorage.getItem("token"),
});

const FREQ_LABELS = { daily: "Günlük", weekly: "Haftalık", monthly: "Aylık" };
const FORMAT_LABELS = { pdf: "PDF", csv: "CSV", link: "Link" };
const DAY_LABELS = {
  monday: "Pazartesi", tuesday: "Salı", wednesday: "Çarşamba",
  thursday: "Perşembe", friday: "Cuma", saturday: "Cumartesi", sunday: "Pazar",
};
const STATUS_INTENT = {
  sent:       { label: "Gönderildi",      intent: "success", icon: CheckCircle },
  failed:     { label: "Başarısız",       intent: "danger",  icon: XCircle },
  partial:    { label: "Kısmi",           intent: "warning", icon: AlertTriangle },
  processing: { label: "İşleniyor",       intent: "info",    icon: Loader2 },
  retrying:   { label: "Tekrar Deneniyor", intent: "warning", icon: RotateCcw },
  mock:       { label: "Mock (SMTP yok)", intent: "neutral", icon: Info },
};

const EMPTY_FORM = {
  name: "", report_type: "", frequency: "daily", recipients: "",
  format: "pdf", send_time: "08:00", day_of_week: "monday",
  day_of_month: 1, include_charts: true, notes: "", date_range: "auto",
};

export default function ReportScheduler() {
  const [schedules, setSchedules] = useState([]);
  const [history, setHistory] = useState([]);
  const [reportTypes, setReportTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("schedules");

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState({});

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailEntry, setDetailEntry] = useState(null);

  const [historyFilter, setHistoryFilter] = useState("all");

  const pollRef = useRef(null);

  const api = useCallback(async (path, opts = {}) => {
    const res = await fetch(BACKEND + path, { headers: headers(), ...opts });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sData, hData, rtData] = await Promise.all([
        api("/api/report-scheduler/schedules"),
        api("/api/report-scheduler/history?limit=100"),
        api("/api/report-scheduler/report-types"),
      ]);
      setSchedules(sData.schedules || []);
      setHistory(hData.history || []);
      setReportTypes(rtData.report_types || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [api]);

  // Sessiz refresh: polling sırasında loader spinner çıkmaz
  const refreshSilent = useCallback(async () => {
    try {
      const [sData, hData] = await Promise.all([
        api("/api/report-scheduler/schedules"),
        api("/api/report-scheduler/history?limit=100"),
      ]);
      setSchedules(sData.schedules || []);
      setHistory(hData.history || []);
    } catch {/* swallow polling errors */}
  }, [api]);

  useEffect(() => { loadData(); }, [loadData]);

  // Processing/retrying olan kayıt varsa 4 sn'de bir polling
  useEffect(() => {
    const hasInflight = history.some(h => h.status === "processing" || h.status === "retrying");
    if (hasInflight) {
      pollRef.current = setInterval(refreshSilent, 4000);
      return () => clearInterval(pollRef.current);
    }
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [history, refreshSilent]);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setModalOpen(true);
  };

  const openEdit = (s) => {
    setEditingId(s._id);
    setForm({
      name: s.name || "",
      report_type: s.report_type || "",
      frequency: s.frequency || "daily",
      recipients: (s.recipients || []).join(", "),
      format: s.format || "pdf",
      send_time: s.send_time || "08:00",
      day_of_week: s.day_of_week || "monday",
      day_of_month: s.day_of_month || 1,
      include_charts: s.include_charts !== false,
      notes: s.notes || "",
      date_range: s.date_range || "auto",
    });
    setModalOpen(true);
  };

  // Modal kapanınca formu sıfırla — eski "Düzenle" değerleri "Yeni" tıklayınca taşmasın.
  const handleModalChange = (open) => {
    setModalOpen(open);
    if (!open) {
      setEditingId(null);
      setForm(EMPTY_FORM);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...form,
        recipients: form.recipients.split(",").map((e) => e.trim()).filter(Boolean),
        day_of_month: form.frequency === "monthly" ? Number(form.day_of_month) : undefined,
        day_of_week: form.frequency === "weekly" ? form.day_of_week : undefined,
      };

      if (editingId) {
        await api(`/api/report-scheduler/schedules/${editingId}`, {
          method: "PUT", body: JSON.stringify(payload),
        });
      } else {
        await api("/api/report-scheduler/schedules", {
          method: "POST", body: JSON.stringify(payload),
        });
      }
      handleModalChange(false);
      loadData();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (id) => {
    setActionLoading((p) => ({ ...p, [id]: "toggle" }));
    try {
      await api(`/api/report-scheduler/schedules/${id}/toggle`, { method: "POST" });
      loadData();
    } catch (e) { setError(e.message); }
    finally { setActionLoading((p) => ({ ...p, [id]: null })); }
  };

  const handleDelete = async (id) => {
    if (!await confirmDialog({ message: "Bu zamanlamayı silmek istediğinize emin misiniz?" })) return;
    setActionLoading((p) => ({ ...p, [id]: "delete" }));
    try {
      await api(`/api/report-scheduler/schedules/${id}`, { method: "DELETE" });
      loadData();
    } catch (e) { setError(e.message); }
    finally { setActionLoading((p) => ({ ...p, [id]: null })); }
  };

  const handleSendNow = async (id) => {
    setActionLoading((p) => ({ ...p, [id]: "send" }));
    try {
      await api(`/api/report-scheduler/schedules/${id}/send-now`, { method: "POST" });
      loadData();
    } catch (e) { setError(e.message); }
    finally { setActionLoading((p) => ({ ...p, [id]: null })); }
  };

  const handleRetry = async (historyId) => {
    setActionLoading((p) => ({ ...p, [historyId]: "retry" }));
    try {
      await api(`/api/report-scheduler/history/${historyId}/retry`, { method: "POST" });
      loadData();
    } catch (e) { setError(e.message); }
    finally { setActionLoading((p) => ({ ...p, [historyId]: null })); }
  };

  const openDetail = (entry) => {
    setDetailEntry(entry);
    setDetailOpen(true);
  };

  const filteredHistory = useMemo(() => {
    if (historyFilter === "all") return history;
    return history.filter((h) => h.status === historyFilter);
  }, [history, historyFilter]);

  const stats = useMemo(() => ({
    total: schedules.length,
    active: schedules.filter((s) => s.is_active).length,
    totalSent: history.filter((h) => h.status === "sent").length,
    totalFailed: history.filter((h) => h.status === "failed").length,
  }), [schedules, history]);

  const getReportLabel = (key) => {
    const rt = reportTypes.find((r) => r.key === key);
    return rt ? rt.label : key;
  };

  const formInvalid =
    !form.name ||
    !form.report_type ||
    !form.recipients ||
    (form.frequency === "weekly" && !form.day_of_week) ||
    (form.frequency === "monthly" && (!form.day_of_month || form.day_of_month < 1 || form.day_of_month > 28));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
        <span className="ml-3 text-slate-500 text-sm">Yükleniyor...</span>
      </div>
    );
  }

  return (
    <>
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-rose-600 shrink-0" />
          <span className="text-sm text-rose-700 flex-1">{error}</span>
          <Button variant="ghost" size="sm" onClick={() => setError(null)}>Kapat</Button>
        </div>
      )}

      <PageHeader
        icon={ScrollText}
        title="Rapor Zamanlayıcı"
        subtitle="Otomatik rapor gönderim zamanlamalarını yönetin"
        actions={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={loadData}>
              <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
            </Button>
            <Button size="sm" onClick={openCreate}>
              <Plus className="h-4 w-4 mr-1.5" /> Yeni Zamanlama
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard icon={Calendar}    label="Toplam Zamanlama" value={stats.total}      intent="info" />
        <KpiCard icon={Play}        label="Aktif"            value={stats.active}     intent="success" />
        <KpiCard icon={CheckCircle} label="Gönderilen"       value={stats.totalSent}  intent="success" />
        <KpiCard icon={XCircle}     label="Başarısız"        value={stats.totalFailed} intent="danger" />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="schedules" className="gap-1">
            <Calendar className="h-4 w-4" /> Zamanlamalar
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-1">
            <FileText className="h-4 w-4" /> Gönderim Geçmişi
          </TabsTrigger>
        </TabsList>

        <TabsContent value="schedules" className="mt-4">
          {schedules.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Mail className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                <h3 className="font-semibold text-slate-700 mb-2">Henüz zamanlama yok</h3>
                <p className="text-sm text-slate-500 mb-4">Yeni bir rapor zamanlaması oluşturarak başlayın</p>
                <Button size="sm" onClick={openCreate}>
                  <Plus className="h-4 w-4 mr-1.5" /> Oluştur
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {schedules.map((s) => (
                <Card key={s._id} className={`transition-opacity ${!s.is_active ? 'opacity-60' : ''}`}>
                  <CardContent className="p-4">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-semibold text-slate-900 truncate">{s.name}</h3>
                          <StatusBadge intent={s.is_active ? "success" : "neutral"}>
                            {s.is_active ? "Aktif" : "Pasif"}
                          </StatusBadge>
                          <StatusBadge intent="info">{FREQ_LABELS[s.frequency] || s.frequency}</StatusBadge>
                          <StatusBadge intent="neutral">{FORMAT_LABELS[s.format] || s.format}</StatusBadge>
                          {s.last_status && STATUS_INTENT[s.last_status] && (
                            <StatusBadge intent={STATUS_INTENT[s.last_status].intent} icon={STATUS_INTENT[s.last_status].icon}>
                              {STATUS_INTENT[s.last_status].label}
                            </StatusBadge>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-slate-500">
                          <span className="flex items-center gap-1">
                            <BarChart3 className="h-3 w-3" /> {getReportLabel(s.report_type)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" /> {s.send_time}
                            {s.frequency === "weekly" && s.day_of_week && ` — ${DAY_LABELS[s.day_of_week] || s.day_of_week}`}
                            {s.frequency === "monthly" && s.day_of_month && ` — Ayın ${s.day_of_month}. günü`}
                          </span>
                          <span className="flex items-center gap-1">
                            <Mail className="h-3 w-3" /> {(s.recipients || []).length} alıcı
                          </span>
                          {s.total_sent > 0 && (
                            <span className="flex items-center gap-1">
                              <CheckCircle className="h-3 w-3 text-emerald-500" /> {s.total_sent} gönderildi
                            </span>
                          )}
                          {s.total_failed > 0 && (
                            <span className="flex items-center gap-1">
                              <XCircle className="h-3 w-3 text-rose-500" /> {s.total_failed} başarısız
                            </span>
                          )}
                        </div>
                        {s.next_run && (
                          <div className="text-xs text-slate-600 mt-1">
                            Sonraki gönderim: {new Date(s.next_run).toLocaleString("tr-TR")}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8"
                              onClick={() => handleSendNow(s._id)}
                              disabled={!!actionLoading[s._id]}>
                              {actionLoading[s._id] === "send" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Şimdi Gönder</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8"
                              onClick={() => handleToggle(s._id)}
                              disabled={!!actionLoading[s._id]}>
                              {s.is_active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>{s.is_active ? "Duraklat" : "Aktif Et"}</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(s)}>
                              <Edit className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Düzenle</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-rose-600 hover:text-rose-700"
                              onClick={() => handleDelete(s._id)}
                              disabled={!!actionLoading[s._id]}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Sil</TooltipContent>
                        </Tooltip>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-4 space-y-4">
          <div className="flex items-center gap-2">
            <Select value={historyFilter} onValueChange={setHistoryFilter}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder="Filtrele" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tümünü Göster</SelectItem>
                <SelectItem value="sent">Gönderildi</SelectItem>
                <SelectItem value="failed">Başarısız</SelectItem>
                <SelectItem value="partial">Kısmi</SelectItem>
                <SelectItem value="mock">Mock (SMTP yok)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {filteredHistory.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <FileText className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                <h3 className="font-semibold text-slate-700">Gönderim geçmişi boş</h3>
                <p className="text-sm text-slate-500 mt-1">Zamanlamalar çalıştığında burada görünecek</p>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Zamanlama</TableHead>
                      <TableHead>Rapor</TableHead>
                      <TableHead>Tarih</TableHead>
                      <TableHead>Durum</TableHead>
                      <TableHead>Alıcılar</TableHead>
                      <TableHead>Tetikleyen</TableHead>
                      <TableHead className="text-right">İşlem</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredHistory.map((h) => {
                      const st = STATUS_INTENT[h.status] || STATUS_INTENT.processing;
                      return (
                        <TableRow key={h._id}>
                          <TableCell className="font-medium max-w-[160px] truncate">{h.schedule_name}</TableCell>
                          <TableCell className="text-sm">{h.report_label || getReportLabel(h.report_type)}</TableCell>
                          <TableCell className="text-sm text-slate-500 whitespace-nowrap">
                            {h.sent_at ? new Date(h.sent_at).toLocaleString("tr-TR") : "-"}
                          </TableCell>
                          <TableCell>
                            <StatusBadge intent={st.intent} icon={st.icon}>{st.label}</StatusBadge>
                          </TableCell>
                          <TableCell className="text-sm">{(h.recipients || []).length}</TableCell>
                          <TableCell className="text-sm text-slate-500">{h.triggered_by === "system" ? "Otomatik" : h.triggered_by}</TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openDetail(h)}>
                                    <Eye className="h-3.5 w-3.5" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Detay</TooltipContent>
                              </Tooltip>
                              {h.status === "failed" && (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-amber-600"
                                      onClick={() => handleRetry(h._id)}
                                      disabled={!!actionLoading[h._id]}>
                                      {actionLoading[h._id] === "retry" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Tekrar Dene</TooltipContent>
                                </Tooltip>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={modalOpen} onOpenChange={handleModalChange}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingId ? "Zamanlama Düzenle" : "Yeni Zamanlama Oluştur"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700">Zamanlama Adı *</label>
              <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="örn: Günlük Doluluk Raporu" className="mt-1" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-slate-700">Rapor Tipi *</label>
                <Select value={form.report_type} onValueChange={(v) => setForm((f) => ({ ...f, report_type: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue placeholder="Rapor seçin" /></SelectTrigger>
                  <SelectContent>
                    {reportTypes.map((rt) => (
                      <SelectItem key={rt.key} value={rt.key}>{rt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Format</label>
                <Select value={form.format} onValueChange={(v) => setForm((f) => ({ ...f, format: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pdf">PDF (e-posta eki)</SelectItem>
                    <SelectItem value="csv">CSV (e-posta eki)</SelectItem>
                    <SelectItem value="link">Link (sadece bağlantı)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-slate-700">Frekans *</label>
                <Select value={form.frequency} onValueChange={(v) => setForm((f) => ({ ...f, frequency: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">Günlük</SelectItem>
                    <SelectItem value="weekly">Haftalık</SelectItem>
                    <SelectItem value="monthly">Aylık</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Gönderim Saati</label>
                <Input type="time" value={form.send_time}
                  onChange={(e) => setForm((f) => ({ ...f, send_time: e.target.value }))} className="mt-1" />
              </div>
            </div>
            {form.frequency === "weekly" && (
              <div>
                <label className="text-sm font-medium text-slate-700">Gönderim Günü *</label>
                <Select value={form.day_of_week} onValueChange={(v) => setForm((f) => ({ ...f, day_of_week: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(DAY_LABELS).map(([k, v]) => (
                      <SelectItem key={k} value={k}>{v}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {form.frequency === "monthly" && (
              <div>
                <label className="text-sm font-medium text-slate-700">Ayın Günü (1-28) *</label>
                <Input type="number" min={1} max={28} value={form.day_of_month}
                  onChange={(e) => setForm((f) => ({ ...f, day_of_month: Number(e.target.value) }))} className="mt-1" />
                <p className="text-xs text-slate-500 mt-1 flex items-start gap-1">
                  <Info className="h-3 w-3 mt-0.5 shrink-0" />
                  Şubat ayında 29-31 olmadığı için aralık 1-28 ile sınırlandırılmıştır.
                </p>
              </div>
            )}
            <div>
              <label className="text-sm font-medium text-slate-700">Alıcılar (virgül ile ayırın) *</label>
              <Input value={form.recipients}
                onChange={(e) => setForm((f) => ({ ...f, recipients: e.target.value }))}
                placeholder="ad@otel.com, yonetici@otel.com" className="mt-1" />
              <p className="text-xs text-slate-500 mt-1">Birden fazla alıcı için virgül ile ayırın</p>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Notlar</label>
              <Input value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="Opsiyonel açıklama" className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => handleModalChange(false)}>İptal</Button>
            <Button onClick={handleSave} disabled={saving || formInvalid}>
              {saving ? <><Loader2 className="h-4 w-4 animate-spin mr-1.5" /> Kaydediliyor</> : (editingId ? "Güncelle" : "Oluştur")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Gönderim Detayı</DialogTitle>
          </DialogHeader>
          {detailEntry && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <span className="text-slate-500">Zamanlama:</span>
                <span className="font-medium">{detailEntry.schedule_name}</span>
                <span className="text-slate-500">Rapor:</span>
                <span>{detailEntry.report_label || detailEntry.report_type}</span>
                <span className="text-slate-500">Tarih:</span>
                <span>{detailEntry.sent_at ? new Date(detailEntry.sent_at).toLocaleString("tr-TR") : "-"}</span>
                <span className="text-slate-500">Durum:</span>
                <span>
                  {STATUS_INTENT[detailEntry.status] && (
                    <StatusBadge intent={STATUS_INTENT[detailEntry.status].intent} icon={STATUS_INTENT[detailEntry.status].icon}>
                      {STATUS_INTENT[detailEntry.status].label}
                    </StatusBadge>
                  )}
                </span>
                <span className="text-slate-500">Tetikleyen:</span>
                <span>{detailEntry.triggered_by === "system" ? "Otomatik" : detailEntry.triggered_by}</span>
                <span className="text-slate-500">Alıcılar:</span>
                <span className="break-all">{(detailEntry.recipients || []).join(", ")}</span>
              </div>
              {detailEntry.error_message && (
                <div className="bg-rose-50 border border-rose-200 rounded p-3 text-rose-700 text-xs whitespace-pre-wrap break-words">
                  {String(detailEntry.error_message)}
                </div>
              )}
              {detailEntry.delivery_details && (
                <div className="bg-slate-50 rounded p-3 text-xs space-y-1">
                  <div>Gönderilen: {detailEntry.delivery_details.sent_count || 0}</div>
                  <div>Başarısız: {detailEntry.delivery_details.failed_count || 0}</div>
                  {detailEntry.delivery_details.mock_count > 0 && (
                    <div className="text-slate-600">Mock (SMTP yok): {detailEntry.delivery_details.mock_count}</div>
                  )}
                  {detailEntry.delivery_details.attachment_count > 0 && (
                    <div>Ek dosya sayısı: {detailEntry.delivery_details.attachment_count}</div>
                  )}
                  {(detailEntry.delivery_details.failed_recipients || []).length > 0 && (
                    <div className="text-rose-600 break-all">
                      Başarısız alıcılar: {detailEntry.delivery_details.failed_recipients.join(", ")}
                    </div>
                  )}
                  {(detailEntry.delivery_details.report_summary || []).length > 0 && (
                    <div className="pt-2 border-t border-slate-200">
                      <div className="font-medium text-slate-700 mb-1">Rapor özeti:</div>
                      {detailEntry.delivery_details.report_summary.map((r, i) => (
                        <div key={i} className="text-slate-600">• {r.label}: {String(r.value)}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {detailEntry.retry_count > 0 && (
                <div className="text-xs text-slate-500">Tekrar deneme sayısı: {detailEntry.retry_count}</div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
    </>
  );
}
