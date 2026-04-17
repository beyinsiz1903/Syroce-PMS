import { useState, useEffect, useCallback, useMemo } from "react";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import {
  Calendar, Clock, Mail, Plus, Play, Pause, Trash2, Edit,
  Send, RefreshCw, AlertTriangle, CheckCircle, XCircle,
  FileText, BarChart3, Loader2, RotateCcw, Eye,
} from "lucide-react";

const BACKEND = import.meta.env.VITE_BACKEND_URL || "";
const headers = () => ({
  "Content-Type": "application/json",
  Authorization: "Bearer " + localStorage.getItem("token"),
});

const FREQ_LABELS = { daily: "Günlük", weekly: "Haftalık", monthly: "Aylık" };
const FORMAT_LABELS = { pdf: "PDF", csv: "CSV", link: "Link" };
const DAY_LABELS = {
  monday: "Pazartesi", tuesday: "Sali", wednesday: "Carsamba",
  thursday: "Persembe", friday: "Cuma", saturday: "Cumartesi", sunday: "Pazar",
};
const STATUS_MAP = {
  sent: { label: "Gonderildi", variant: "default", icon: CheckCircle, color: "text-green-600" },
  failed: { label: "Basarisiz", variant: "destructive", icon: XCircle, color: "text-red-600" },
  partial: { label: "Kismi", variant: "secondary", icon: AlertTriangle, color: "text-yellow-600" },
  processing: { label: "Isleniyor", variant: "outline", icon: Loader2, color: "text-blue-600" },
  retrying: { label: "Tekrar Deneniyor", variant: "outline", icon: RotateCcw, color: "text-orange-600" },
};

const EMPTY_FORM = {
  name: "", report_type: "", frequency: "daily", recipients: "",
  format: "pdf", send_time: "08:00", day_of_week: "monday",
  day_of_month: 1, include_charts: true, notes: "", date_range: "auto",
};

export default function ReportScheduler({ user, tenant, onLogout }) {
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

  useEffect(() => { loadData(); }, [loadData]);

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
      setModalOpen(false);
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
    if (!confirm("Bu zamanlamayı silmek istediğinize emin misiniz?")) return;
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-600" />
        <span className="ml-3 text-gray-500">Yükleniyor...</span>
      </div>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="report-scheduler">
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />
          <span className="text-sm text-red-700">{error}</span>
          <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setError(null)}>Kapat</Button>
        </div>
      )}

      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Rapor Zamanlayici</h1>
          <p className="text-sm text-gray-500 mt-1">Otomatik rapor gonderim zamanlamalarini yonetin</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="h-4 w-4 mr-1" /> Yenile
          </Button>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4 mr-1" /> Yeni Zamanlama
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-purple-600">{stats.total}</div>
            <div className="text-xs text-gray-500 mt-1">Toplam Zamanlama</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-green-600">{stats.active}</div>
            <div className="text-xs text-gray-500 mt-1">Aktif</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.totalSent}</div>
            <div className="text-xs text-gray-500 mt-1">Gonderilen</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-red-600">{stats.totalFailed}</div>
            <div className="text-xs text-gray-500 mt-1">Basarisiz</div>
          </CardContent>
        </Card>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="schedules" className="gap-1">
            <Calendar className="h-4 w-4" /> Zamanlamalar
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-1">
            <FileText className="h-4 w-4" /> Gonderim Geçmişi
          </TabsTrigger>
        </TabsList>

        <TabsContent value="schedules" className="mt-4">
          {schedules.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Mail className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                <h3 className="font-semibold text-gray-700 mb-2">Henüz zamanlama yok</h3>
                <p className="text-sm text-gray-500 mb-4">Yeni bir rapor zamanlama olusturarak baslayin</p>
                <Button size="sm" onClick={openCreate}>
                  <Plus className="h-4 w-4 mr-1" /> Olustur
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
                          <h3 className="font-semibold text-gray-900 truncate">{s.name}</h3>
                          <Badge variant={s.is_active ? "default" : "secondary"}>
                            {s.is_active ? "Aktif" : "Pasif"}
                          </Badge>
                          <Badge variant="outline">{FREQ_LABELS[s.frequency] || s.frequency}</Badge>
                          <Badge variant="outline">{FORMAT_LABELS[s.format] || s.format}</Badge>
                          {s.last_status && (
                            <Badge variant={STATUS_MAP[s.last_status]?.variant || "outline"}>
                              {STATUS_MAP[s.last_status]?.label || s.last_status}
                            </Badge>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-gray-500">
                          <span className="flex items-center gap-1">
                            <BarChart3 className="h-3 w-3" /> {getReportLabel(s.report_type)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" /> {s.send_time}
                            {s.frequency === "weekly" && s.day_of_week && ` - ${DAY_LABELS[s.day_of_week] || s.day_of_week}`}
                            {s.frequency === "monthly" && s.day_of_month && ` - Ayin ${s.day_of_month}. gunu`}
                          </span>
                          <span className="flex items-center gap-1">
                            <Mail className="h-3 w-3" /> {(s.recipients || []).length} alici
                          </span>
                          {s.total_sent > 0 && (
                            <span className="flex items-center gap-1">
                              <CheckCircle className="h-3 w-3 text-green-500" /> {s.total_sent} gonderildi
                            </span>
                          )}
                          {s.total_failed > 0 && (
                            <span className="flex items-center gap-1">
                              <XCircle className="h-3 w-3 text-red-500" /> {s.total_failed} başarısız
                            </span>
                          )}
                        </div>
                        {s.next_run && (
                          <div className="text-xs text-purple-600 mt-1">
                            Sonraki gonderim: {new Date(s.next_run).toLocaleString("tr-TR")}
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
                          <TooltipContent>Simdi Gonder</TooltipContent>
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
                          <TooltipContent>Duzenle</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-red-600 hover:text-red-700"
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
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Filtrele" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tumunu Goster</SelectItem>
                <SelectItem value="sent">Gonderildi</SelectItem>
                <SelectItem value="failed">Basarisiz</SelectItem>
                <SelectItem value="partial">Kismi</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {filteredHistory.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                <h3 className="font-semibold text-gray-700">Gonderim geçmişi bos</h3>
                <p className="text-sm text-gray-500 mt-1">Zamanlamalar calistiginda burada gorunecek</p>
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
                      <TableHead>Alicilar</TableHead>
                      <TableHead>Tetikleyen</TableHead>
                      <TableHead className="text-right">Islem</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredHistory.map((h) => {
                      const st = STATUS_MAP[h.status] || STATUS_MAP.processing;
                      const StIcon = st.icon;
                      return (
                        <TableRow key={h._id}>
                          <TableCell className="font-medium max-w-[160px] truncate">{h.schedule_name}</TableCell>
                          <TableCell className="text-sm">{h.report_label || getReportLabel(h.report_type)}</TableCell>
                          <TableCell className="text-sm text-gray-500 whitespace-nowrap">
                            {h.sent_at ? new Date(h.sent_at).toLocaleString("tr-TR") : "-"}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1">
                              <StIcon className={`h-4 w-4 ${st.color}`} />
                              <span className="text-sm">{st.label}</span>
                            </div>
                          </TableCell>
                          <TableCell className="text-sm">{(h.recipients || []).length}</TableCell>
                          <TableCell className="text-sm text-gray-500">{h.triggered_by === "system" ? "Otomatik" : h.triggered_by}</TableCell>
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
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-orange-600"
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

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingId ? "Zamanlama Duzenle" : "Yeni Zamanlama Olustur"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-700">Zamanlama Adi *</label>
              <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="ornegin: Günlük Doluluk Raporu" className="mt-1" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Rapor Tipi *</label>
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
                <label className="text-sm font-medium text-gray-700">Format</label>
                <Select value={form.format} onValueChange={(v) => setForm((f) => ({ ...f, format: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pdf">PDF</SelectItem>
                    <SelectItem value="csv">CSV</SelectItem>
                    <SelectItem value="link">Link</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Frekans *</label>
                <Select value={form.frequency} onValueChange={(v) => setForm((f) => ({ ...f, frequency: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">Günlük</SelectItem>
                    <SelectItem value="weekly">Haftalik</SelectItem>
                    <SelectItem value="monthly">Aylik</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Gonderim Saati</label>
                <Input type="time" value={form.send_time}
                  onChange={(e) => setForm((f) => ({ ...f, send_time: e.target.value }))} className="mt-1" />
              </div>
            </div>
            {form.frequency === "weekly" && (
              <div>
                <label className="text-sm font-medium text-gray-700">Gonderim Gunu</label>
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
                <label className="text-sm font-medium text-gray-700">Ayin Gunu (1-28)</label>
                <Input type="number" min={1} max={28} value={form.day_of_month}
                  onChange={(e) => setForm((f) => ({ ...f, day_of_month: Number(e.target.value) }))} className="mt-1" />
              </div>
            )}
            <div>
              <label className="text-sm font-medium text-gray-700">Alicilar (virgul ile ayirin) *</label>
              <Input value={form.recipients}
                onChange={(e) => setForm((f) => ({ ...f, recipients: e.target.value }))}
                placeholder="ad@otel.com, yonetici@otel.com" className="mt-1" />
              <p className="text-xs text-gray-400 mt-1">Birden fazla alici için virgul ile ayirin</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">Notlar</label>
              <Input value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="Opsiyonel aciklama" className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>İptal</Button>
            <Button onClick={handleSave} disabled={saving || !form.name || !form.report_type || !form.recipients}>
              {saving ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Kaydediliyor</> : (editingId ? "Guncelle" : "Olustur")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Gonderim Detayi</DialogTitle>
          </DialogHeader>
          {detailEntry && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <span className="text-gray-500">Zamanlama:</span>
                <span className="font-medium">{detailEntry.schedule_name}</span>
                <span className="text-gray-500">Rapor:</span>
                <span>{detailEntry.report_label || detailEntry.report_type}</span>
                <span className="text-gray-500">Tarih:</span>
                <span>{detailEntry.sent_at ? new Date(detailEntry.sent_at).toLocaleString("tr-TR") : "-"}</span>
                <span className="text-gray-500">Durum:</span>
                <span>
                  <Badge variant={STATUS_MAP[detailEntry.status]?.variant || "outline"}>
                    {STATUS_MAP[detailEntry.status]?.label || detailEntry.status}
                  </Badge>
                </span>
                <span className="text-gray-500">Tetikleyen:</span>
                <span>{detailEntry.triggered_by === "system" ? "Otomatik" : detailEntry.triggered_by}</span>
                <span className="text-gray-500">Alicilar:</span>
                <span>{(detailEntry.recipients || []).join(", ")}</span>
              </div>
              {detailEntry.error_message && (
                <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-xs">
                  {detailEntry.error_message}
                </div>
              )}
              {detailEntry.delivery_details && (
                <div className="bg-gray-50 rounded p-3 text-xs space-y-1">
                  <div>Gonderilen: {detailEntry.delivery_details.sent_count || 0}</div>
                  <div>Basarisiz: {detailEntry.delivery_details.failed_count || 0}</div>
                  {(detailEntry.delivery_details.failed_recipients || []).length > 0 && (
                    <div className="text-red-600">
                      Basarisiz alicilar: {detailEntry.delivery_details.failed_recipients.join(", ")}
                    </div>
                  )}
                </div>
              )}
              {detailEntry.retry_count > 0 && (
                <div className="text-xs text-gray-500">Tekrar deneme sayisi: {detailEntry.retry_count}</div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
    </Layout>
  );
}
