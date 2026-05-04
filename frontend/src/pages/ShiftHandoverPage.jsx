import { useEffect, useState, useCallback } from 'react';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, ClipboardCheck, AlertTriangle, Check, Trash2, Plus } from 'lucide-react';
import { toast } from 'sonner';

const SHIFTS = [
  { v: 'morning', l: 'Sabah (07:00–15:00)' },
  { v: 'afternoon', l: 'Öğleden Sonra (15:00–23:00)' },
  { v: 'night', l: 'Gece (23:00–07:00)' },
];
const PRIORITIES = [
  { v: 'low', l: 'Düşük', cls: 'bg-gray-100 text-gray-700 border-gray-200' },
  { v: 'normal', l: 'Normal', cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  { v: 'high', l: 'Yüksek', cls: 'bg-red-100 text-red-700 border-red-200' },
];

const today = () => new Date().toISOString().slice(0, 10);

export default function ShiftHandoverPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('open');
  const [businessDate, setBusinessDate] = useState(today());
  const [form, setForm] = useState({
    business_date: today(),
    shift: 'afternoon',
    to_shift: 'night',
    priority: 'normal',
    note: '',
    related_room: '',
    related_booking_id: '',
  });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: statusFilter, limit: 200 };
      if (businessDate) params.business_date = businessDate;
      const { data } = await api.get('/pms/shift-handover', { params });
      setItems(data.items || []);
    } catch (e) {
      toast.error('Yükleme hatası: ' + (e.response?.data?.detail || e.message));
    } finally { setLoading(false); }
  }, [statusFilter, businessDate]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.note.trim()) { toast.error('Not boş olamaz'); return; }
    setCreating(true);
    try {
      const payload = { ...form };
      Object.keys(payload).forEach(k => { if (payload[k] === '') delete payload[k]; });
      await api.post('/pms/shift-handover', payload);
      toast.success('Devir notu eklendi');
      setForm(p => ({ ...p, note: '', related_room: '', related_booking_id: '' }));
      load();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    finally { setCreating(false); }
  };

  const ack = async (id) => {
    try {
      await api.patch(`/pms/shift-handover/${id}/acknowledge`, {});
      toast.success('Devir notu onaylandı');
      load();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const remove = async (id) => {
    if (!confirm('Bu devir notunu silmek istediğinize emin misiniz?')) return;
    try {
      await api.delete(`/pms/shift-handover/${id}`);
      toast.success('Silindi');
      load();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const prioMeta = (p) => PRIORITIES.find(x => x.v === p) || PRIORITIES[1];
  const shiftLabel = (s) => SHIFTS.find(x => x.v === s)?.l || s;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4" data-testid="shift-handover-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardCheck className="w-6 h-6 text-orange-600" /> Vardiya Devir Notları
          </h1>
          <p className="text-sm text-gray-500 mt-1">Resepsiyon vardiyaları arasında kritik not aktarımı</p>
        </div>
      </div>

      <Card className="p-4 border-orange-200">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Plus className="w-4 h-4" /> Yeni Devir Notu</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <Label className="text-xs">İş Günü</Label>
            <Input type="date" value={form.business_date} onChange={e => setForm(p => ({ ...p, business_date: e.target.value }))} className="h-9" />
          </div>
          <div>
            <Label className="text-xs">Vardiya</Label>
            <Select value={form.shift} onValueChange={v => setForm(p => ({ ...p, shift: v }))}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>{SHIFTS.map(s => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Devredilen Vardiya</Label>
            <Select value={form.to_shift} onValueChange={v => setForm(p => ({ ...p, to_shift: v }))}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>{SHIFTS.map(s => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Öncelik</Label>
            <Select value={form.priority} onValueChange={v => setForm(p => ({ ...p, priority: v }))}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>{PRIORITIES.map(p => <SelectItem key={p.v} value={p.v}>{p.l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          <div>
            <Label className="text-xs">İlgili Oda (ops.)</Label>
            <Input value={form.related_room} onChange={e => setForm(p => ({ ...p, related_room: e.target.value }))} placeholder="Örn. 204" className="h-9" />
          </div>
          <div>
            <Label className="text-xs">İlgili Rezervasyon ID (ops.)</Label>
            <Input value={form.related_booking_id} onChange={e => setForm(p => ({ ...p, related_booking_id: e.target.value }))} className="h-9" />
          </div>
        </div>
        <div className="mt-3">
          <Label className="text-xs">Not</Label>
          <Textarea value={form.note} onChange={e => setForm(p => ({ ...p, note: e.target.value }))} rows={3}
            placeholder="Örn: 312 nolu odada klima arızası, teknik servis 09:00 gelecek." />
        </div>
        <div className="mt-3 flex justify-end">
          <Button onClick={create} disabled={creating} className="bg-orange-600 hover:bg-orange-700">
            {creating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />} Devir Notu Ekle
          </Button>
        </div>
      </Card>

      <Card className="p-4">
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <Tabs value={statusFilter} onValueChange={setStatusFilter}>
            <TabsList>
              <TabsTrigger value="open">Açık</TabsTrigger>
              <TabsTrigger value="acknowledged">Onaylanan</TabsTrigger>
              <TabsTrigger value="all">Tümü</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center gap-2">
            <Label className="text-xs whitespace-nowrap">İş Günü</Label>
            <Input type="date" value={businessDate} onChange={e => setBusinessDate(e.target.value)} className="h-8 w-40" />
            <Button size="sm" variant="outline" onClick={() => setBusinessDate('')}>Tümü</Button>
          </div>
        </div>

        {loading && <div className="text-center py-8 text-gray-500"><Loader2 className="inline w-5 h-5 animate-spin" /> Yükleniyor...</div>}

        {!loading && items.length === 0 && (
          <div className="text-center py-12 text-gray-400 text-sm">Devir notu yok</div>
        )}

        <div className="space-y-2">
          {items.map(it => {
            const pm = prioMeta(it.priority);
            return (
              <div key={it.id} className={`border rounded-lg p-3 ${it.acknowledged ? 'bg-gray-50 opacity-75' : 'bg-white'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <Badge className={pm.cls}>{pm.l}</Badge>
                      <Badge variant="outline" className="text-xs">{it.business_date}</Badge>
                      <Badge variant="outline" className="text-xs">{shiftLabel(it.shift)}{it.to_shift ? ` → ${shiftLabel(it.to_shift)}` : ''}</Badge>
                      {it.related_room && <Badge variant="outline" className="text-xs">Oda {it.related_room}</Badge>}
                      {it.acknowledged && <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200"><Check className="w-3 h-3 mr-1" />Onaylandı</Badge>}
                      {!it.acknowledged && it.priority === 'high' && <AlertTriangle className="w-4 h-4 text-red-600" />}
                    </div>
                    <div className="text-sm text-gray-800 whitespace-pre-wrap">{it.note}</div>
                    <div className="text-[11px] text-gray-500 mt-2">
                      {it.from_user_name} · {new Date(it.created_at).toLocaleString('tr-TR')}
                      {it.acknowledged && it.acknowledged_by_name && (
                        <> · Onay: {it.acknowledged_by_name} ({new Date(it.acknowledged_at).toLocaleString('tr-TR')})</>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col gap-1.5 shrink-0">
                    {!it.acknowledged && (
                      <Button size="sm" onClick={() => ack(it.id)} className="bg-emerald-600 hover:bg-emerald-700 h-8">
                        <Check className="w-3.5 h-3.5 mr-1" /> Onayla
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => remove(it.id)} className="h-8 text-red-600 hover:text-red-700">
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
