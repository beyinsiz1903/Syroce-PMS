import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useTranslation } from 'react-i18next';
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { RefreshCw, Clock, CheckCircle2, PlayCircle, XCircle, AlertTriangle, User, Phone, MessageSquare, Building, Loader2, QrCode, Sparkles } from "lucide-react";
import RoomQRPrintAction from "@/components/RoomQRPrintAction";
const STATUS_COLUMNS = [{
  key: "new",
  label: "Yeni",
  color: "bg-blue-50 border-blue-300",
  badge: "bg-blue-600"
}, {
  key: "assigned",
  label: "Atandı",
  color: "bg-indigo-50 border-indigo-300",
  badge: "bg-indigo-600"
}, {
  key: "in_progress",
  label: "İşlemde",
  color: "bg-amber-50 border-amber-300",
  badge: "bg-amber-600"
}, {
  key: "completed",
  label: "Tamamlandı",
  color: "bg-emerald-50 border-emerald-300",
  badge: "bg-emerald-600"
}];
const ALL_DEPTS = "__all__";
const DEPARTMENTS = [{
  id: ALL_DEPTS,
  label: "Tüm Departmanlar"
}, {
  id: "rooms",
  label: "Kat Hizmetleri"
}, {
  id: "technical",
  label: "Teknik"
}, {
  id: "fnb",
  label: "Yiyecek & İçecek"
}, {
  id: "laundry",
  label: "Çamaşır"
}, {
  id: "minibar",
  label: "Minibar"
}, {
  id: "transportation",
  label: "Ulaşım"
}, {
  id: "spa",
  label: "SPA"
}, {
  id: "other",
  label: "Diğer"
}];
const DEPT_LABEL = Object.fromEntries(DEPARTMENTS.map(d => [d.id, d.label]));
const PRIORITY_STYLE = {
  urgent: "bg-red-100 text-red-700 border-red-300",
  high: "bg-amber-100 text-amber-700 border-amber-300",
  normal: "bg-slate-100 text-slate-700 border-slate-300",
  low: "bg-gray-100 text-gray-600 border-gray-300"
};
function timeAgo(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "az önce";
  if (m < 60) return `${m} dk`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} sa`;
  return `${Math.floor(h / 24)} gün`;
}
function RequestCard({
  item,
  onOpen
}) {
  return <button onClick={() => onOpen(item)} className="w-full text-left bg-white rounded-lg border p-3 shadow-sm hover:shadow-md transition-all hover:border-slate-400">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="font-semibold text-sm">Oda {item.room_number}</div>
        <Badge variant="outline" className={PRIORITY_STYLE[item.priority] || PRIORITY_STYLE.normal}>
          {item.priority}
        </Badge>
      </div>
      <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
        <Building className="w-3 h-3" /> {DEPT_LABEL[item.department] || item.department}
      </div>
      <div className="text-sm font-medium text-slate-800 line-clamp-1">{item.title}</div>
      <div className="text-xs text-gray-600 mt-1 line-clamp-2">{item.description}</div>
      <div className="flex items-center justify-between mt-2 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" /> {timeAgo(item.created_at)}
        </span>
        {item.guest_name && <span className="flex items-center gap-1">
            <User className="w-3 h-3" /> {item.guest_name}
          </span>}
      </div>
    </button>;
}
export default function RoomRequests({
  user,
  tenant,
  onLogout
}) {
  const {
    t
  } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState(ALL_DEPTS);
  const [selected, setSelected] = useState(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  // Single request fetches all tenant requests; filtering and stat aggregation
  // happen client-side. Eliminates the second `/stats/summary` round-trip and
  // halves background polling cost (typical hotel has <50 active requests).
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get("/room-requests");
      setItems(r.data.items || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  // 60 sn'de bir tazele; sekme arka planda iken sessiz kal (gereksiz yük yok).
  useEffect(() => {
    const tick = () => {
      if (!document.hidden) load();
    };
    const i = setInterval(tick, 60000);
    const onVis = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearInterval(i);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [load]);

  // Department filter is applied client-side so the top stat cards always
  // show full-tenant totals while the kanban reflects the active filter.
  const filteredItems = useMemo(() => department === ALL_DEPTS ? items : items.filter(it => it.department === department), [items, department]);
  const grouped = useMemo(() => {
    const g = {
      new: [],
      assigned: [],
      in_progress: [],
      completed: []
    };
    filteredItems.forEach(it => {
      (g[it.status] || (g[it.status] = [])).push(it);
    });
    return g;
  }, [filteredItems]);
  const stats = useMemo(() => {
    const by_status = {};
    items.forEach(it => {
      by_status[it.status] = (by_status[it.status] || 0) + 1;
    });
    return {
      total: items.length,
      by_status
    };
  }, [items]);
  const updateStatus = async (id, patch, noteText) => {
    setSaving(true);
    try {
      const r = await axios.patch(`/room-requests/${id}`, {
        ...patch,
        note: noteText || undefined
      });
      setSelected(r.data);
      setNote("");
      toast.success("Güncellendi");
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Hata");
    } finally {
      setSaving(false);
    }
  };
  return <>
      <div className="p-6 space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold">Oda QR Talepleri</h1>
            <p className="text-gray-500 text-sm mt-1">Misafirlerden gelen talepleri departman bazında takip edin</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Select value={department} onValueChange={setDepartment}>
              <SelectTrigger className="w-52"><SelectValue /></SelectTrigger>
              <SelectContent>
                {DEPARTMENTS.map(d => <SelectItem key={d.id || "all"} value={d.id}>{d.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <RoomQRPrintAction hotelName={tenant?.property_name} variant="outline" />
            <Button variant="outline" onClick={load} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Yenile
            </Button>
          </div>
        </div>

        {/* İstatistik */}
        {stats && <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <StatCard label="Toplam" value={stats.total} icon={MessageSquare} color="bg-slate-100 text-slate-700" />
            <StatCard label="Yeni" value={stats.by_status?.new || 0} icon={AlertTriangle} color="bg-blue-100 text-blue-700" />
            <StatCard label="Atandı" value={stats.by_status?.assigned || 0} icon={User} color="bg-indigo-100 text-indigo-700" />
            <StatCard label={t('common.inProgress')} value={stats.by_status?.in_progress || 0} icon={PlayCircle} color="bg-amber-100 text-amber-700" />
            <StatCard label="Tamamlandı" value={stats.by_status?.completed || 0} icon={CheckCircle2} color="bg-emerald-100 text-emerald-700" />
          </div>}

        {/* Tenant'ta hiç talep yoksa Kanban yerine açıklayıcı bir
            empty state göster. Tek talep gelir gelmez kanban'a
            otomatik geçer. İlk yükleme sırasında titreşim olmasın
            diye loading state'inde de hero gösteriyoruz. */}
        {items.length === 0 ? <EmptyState hotelName={tenant?.property_name} /> : <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {STATUS_COLUMNS.map(col => <div key={col.key} className={`${col.color} border-2 rounded-xl p-3 min-h-[400px]`}>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-slate-700">{col.label}</h3>
                  <Badge className={`${col.badge} text-white`}>{(grouped[col.key] || []).length}</Badge>
                </div>
                <div className="space-y-2">
                  {(grouped[col.key] || []).map(it => <RequestCard key={it.id} item={it} onOpen={setSelected} />)}
                  {(grouped[col.key] || []).length === 0 && <div className="text-xs text-gray-400 text-center py-6">Talep yok</div>}
                </div>
              </div>)}
          </div>}
      </div>

      {/* Detay dialogu */}
      <Dialog open={!!selected} onOpenChange={v => !v && setSelected(null)}>
        <DialogContent className="max-w-2xl">
          {selected && <>
              <DialogHeader>
                <DialogTitle className="flex items-center justify-between">
                  <span>Oda {selected.room_number} — {selected.title}</span>
                  <Badge className={PRIORITY_STYLE[selected.priority]}>{selected.priority}</Badge>
                </DialogTitle>
                <DialogDescription className="flex items-center gap-2 text-xs">
                  <Building className="w-3 h-3" /> {DEPT_LABEL[selected.department] || selected.department}
                  <span className="mx-1">•</span>
                  <Clock className="w-3 h-3" /> {new Date(selected.created_at).toLocaleString("tr-TR")}
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 py-4">
                <div className="bg-slate-50 p-3 rounded-lg">
                  <div className="text-xs text-gray-500 mb-1">Açıklama</div>
                  <div className="text-sm whitespace-pre-wrap">{selected.description}</div>
                </div>

                {(selected.guest_name || selected.guest_phone) && <div className="flex gap-4 text-sm">
                    {selected.guest_name && <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-gray-400" /> {selected.guest_name}
                      </div>}
                    {selected.guest_phone && <a href={`tel:${selected.guest_phone}`} className="flex items-center gap-2 text-blue-600">
                        <Phone className="w-4 h-4" /> {selected.guest_phone}
                      </a>}
                  </div>}

                <div>
                  <div className="text-xs text-gray-500 mb-1">Geçmiş</div>
                  <div className="space-y-1 text-xs">
                    {(selected.status_history || []).map((h, i) => <div key={h.id || i} className="flex items-start gap-2 text-gray-600">
                        <span className="font-mono text-[10px] text-gray-400">
                          {new Date(h.at).toLocaleString("tr-TR")}
                        </span>
                        <span className="flex-1">
                          <strong>{h.by}</strong>
                          {h.status && <> — <Badge variant="outline" className="text-[10px]">{h.status}</Badge></>}
                          {h.note && <> — {h.note}</>}
                        </span>
                      </div>)}
                  </div>
                </div>

                <div>
                  <Textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Not ekle (opsiyonel)..." rows={2} />
                </div>

                <div className="flex flex-wrap gap-2">
                  {selected.status !== "in_progress" && selected.status !== "completed" && <Button onClick={() => updateStatus(selected.id, {
                status: "in_progress"
              }, note)} disabled={saving}>
                      <PlayCircle className="w-4 h-4 mr-2" /> İşleme Al
                    </Button>}
                  {selected.status !== "completed" && <Button onClick={() => updateStatus(selected.id, {
                status: "completed"
              }, note)} className="bg-emerald-600 hover:bg-emerald-700" disabled={saving}>
                      <CheckCircle2 className="w-4 h-4 mr-2" /> Tamamlandı
                    </Button>}
                  {selected.status !== "cancelled" && selected.status !== "completed" && <Button variant="outline" onClick={() => updateStatus(selected.id, {
                status: "cancelled"
              }, note)} disabled={saving}>
                      <XCircle className="w-4 h-4 mr-2" /> İptal
                    </Button>}
                  <Select value={selected.priority} onValueChange={v => updateStatus(selected.id, {
                priority: v
              })}>
                    <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Düşük</SelectItem>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="high">Yüksek</SelectItem>
                      <SelectItem value="urgent">Acil</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </>}
        </DialogContent>
      </Dialog>
    </>;
}
function EmptyState({
  hotelName
}) {
  const steps = [{
    n: 1,
    title: "QR kodlarını yazdırın",
    text: "Sağ üstteki butonla tüm odaların QR kartlarını A4 sayfada toplu yazdırabilirsiniz."
  }, {
    n: 2,
    title: "Odalara yerleştirin",
    text: "Kartı oda kapısının arkasına, masaya veya banyo aynasına yapıştırın."
  }, {
    n: 3,
    title: "Talepler buraya düşer",
    text: "Misafir QR'ı okutup talebini yazdığında departman bazında otomatik dağılır."
  }];
  const categories = DEPARTMENTS.filter(d => d.id !== ALL_DEPTS);
  return <Card className="border-dashed border-2 border-slate-200 bg-gradient-to-br from-white to-slate-50 dark:bg-none dark:bg-card">
      <CardContent className="p-8 md:p-12">
        <div className="max-w-3xl mx-auto text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-50 text-blue-600 mb-4">
            <QrCode className="w-8 h-8" />
          </div>
          <h2 className="text-2xl font-bold text-slate-800 mb-2">
            Henüz misafir talebi yok
          </h2>
          <p className="text-slate-500 mb-8">
            {hotelName ? `${hotelName} için ` : ""}misafirler odadaki QR
            kodunu okutarak havlu, oda servisi, teknik arıza gibi talepleri
            buraya gönderebilir. Başlamak için QR kartlarını basıp odalara
            yerleştirmeniz yeterli.
          </p>

          <div className="grid md:grid-cols-3 gap-4 text-left mb-8">
            {steps.map(s => <div key={s.n} className="bg-white rounded-xl border border-slate-200 p-4">
                <div className="w-7 h-7 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center mb-3">
                  {s.n}
                </div>
                <div className="font-semibold text-sm text-slate-800 mb-1">{s.title}</div>
                <div className="text-xs text-slate-500 leading-relaxed">{s.text}</div>
              </div>)}
          </div>

          <div className="flex justify-center mb-8">
            <RoomQRPrintAction hotelName={hotelName} size="lg" className="bg-blue-600 hover:bg-blue-700" />
          </div>

          <div className="text-left bg-slate-50 rounded-xl p-4 border border-slate-200">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-600 mb-3">
              <Sparkles className="w-3.5 h-3.5" />
              Misafirlerin seçebileceği kategoriler
            </div>
            <div className="flex flex-wrap gap-1.5">
              {categories.map(c => <Badge key={c.id} variant="outline" className="bg-white text-slate-600 font-normal">
                  {c.label}
                </Badge>)}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>;
}
function StatCard({
  label,
  value,
  icon: Icon,
  color
}) {
  return <Card>
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className="text-2xl font-bold">{value}</div>
          <div className="text-xs text-gray-500">{label}</div>
        </div>
      </CardContent>
    </Card>;
}