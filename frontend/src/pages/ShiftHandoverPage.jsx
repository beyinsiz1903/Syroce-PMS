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
import { Loader2, ClipboardCheck, AlertTriangle, Check, Trash2, Plus, Inbox } from 'lucide-react';
import { toast } from 'sonner';

import { confirmDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';

const SHIFTS = [
  { v: 'morning',   l: 'Sabah (07:00–15:00)' },
  { v: 'afternoon', l: 'Öğleden Sonra (15:00–23:00)' },
  { v: 'night',     l: 'Gece (23:00–07:00)' },
];
const PRIORITIES = [
  { v: 'low',    l: 'Düşük',  cls: 'bg-slate-100 text-slate-700 border-slate-200' },
  { v: 'normal', l: 'Normal', cls: 'bg-sky-100 text-sky-800 border-sky-200' },
  { v: 'high',   l: 'Acil',   cls: 'bg-rose-100 text-rose-800 border-rose-200' },
];

const today = () => new Date().toISOString().slice(0, 10);

export default function ShiftHandoverPage({ user, tenant, onLogout }) {
  const { t } = useTranslation();
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
    if (!await confirmDialog({ message: 'Bu devir notunu silmek istediğinize emin misiniz?', variant: 'danger' })) return;
    try {
      await api.delete(`/pms/shift-handover/${id}`);
      toast.success('Silindi');
      load();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const prioMeta = (p) => PRIORITIES.find(x => x.v === p) || PRIORITIES[1];
  const shiftLabel = (s) => SHIFTS.find(x => x.v === s)?.l || s;

  return (
    <>
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4" data-testid="shift-handover-page">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-900">
            <ClipboardCheck className="w-6 h-6 text-amber-600" /> {t('cm.pages_ShiftHandoverPage.vardiya_devir_notlari')}
          </h1>
          <p className="text-sm text-slate-500 mt-1">{t('cm.pages_ShiftHandoverPage.resepsiyon_vardiyalari_arasinda_kritik_n')}</p>
        </div>

        {/* Yeni devir notu formu */}
        <Card className="p-4 border-amber-200 bg-amber-50/30">
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2 text-slate-900">
            <Plus className="w-4 h-4 text-amber-600" /> {t('cm.pages_ShiftHandoverPage.yeni_devir_notu')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <Label className="text-xs">{t('cm.pages_ShiftHandoverPage.is_gunu')}</Label>
              <Input type="date" value={form.business_date} onChange={e => setForm(p => ({ ...p, business_date: e.target.value }))} className="h-9" />
            </div>
            <div>
              <Label className="text-xs">Devreden Vardiya</Label>
              <Select value={form.shift} onValueChange={v => setForm(p => ({ ...p, shift: v }))}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>{SHIFTS.map(s => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Devralan Vardiya</Label>
              <Select value={form.to_shift} onValueChange={v => setForm(p => ({ ...p, to_shift: v }))}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>{SHIFTS.map(s => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">{t('cm.pages_ShiftHandoverPage.oncelik')}</Label>
              <Select value={form.priority} onValueChange={v => setForm(p => ({ ...p, priority: v }))}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>{PRIORITIES.map(p => <SelectItem key={p.v} value={p.v}>{p.l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            <div>
              <Label className="text-xs text-slate-600">{t('cm.pages_ShiftHandoverPage.ilgili_oda')} <span className="opacity-60">(opsiyonel)</span></Label>
              <Input value={form.related_room} onChange={e => setForm(p => ({ ...p, related_room: e.target.value }))} placeholder={t('cm.pages_ShiftHandoverPage.orn_204')} className="h-9" />
            </div>
            <div>
              <Label className="text-xs text-slate-600">{t('cm.pages_ShiftHandoverPage.ilgili_rezervasyon_id')} <span className="opacity-60">(opsiyonel)</span></Label>
              <Input value={form.related_booking_id} onChange={e => setForm(p => ({ ...p, related_booking_id: e.target.value }))} className="h-9" />
            </div>
          </div>
          <div className="mt-3">
            <Label className="text-xs">Not <span className="text-rose-500">*</span></Label>
            <Textarea
              value={form.note}
              onChange={e => setForm(p => ({ ...p, note: e.target.value }))}
              rows={4}
              className="min-h-[110px] resize-y"
              placeholder={t('cm.pages_ShiftHandoverPage.orn_312_nolu_odada_klima_arizasi_teknik_')}
            />
          </div>
          <div className="mt-3 flex justify-end">
            <Button onClick={create} disabled={creating} className="bg-amber-600 hover:bg-amber-700 text-white">
              {creating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              {t('cm.pages_ShiftHandoverPage.devir_notu_ekle')}
            </Button>
          </div>
        </Card>

        {/* Liste filtreleri + içerik */}
        <Card className="p-4 border-slate-200">
          <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
            <Tabs value={statusFilter} onValueChange={setStatusFilter}>
              <TabsList>
                <TabsTrigger value="open">{t('cm.pages_ShiftHandoverPage.acik')}</TabsTrigger>
                <TabsTrigger value="acknowledged">Onaylanan</TabsTrigger>
                <TabsTrigger value="all">{t('cm.pages_ShiftHandoverPage.tumu')}</TabsTrigger>
              </TabsList>
            </Tabs>
            <div className="flex items-center gap-2">
              <Label className="text-xs whitespace-nowrap text-slate-600">{t('cm.pages_ShiftHandoverPage.tarih')}</Label>
              <Input type="date" value={businessDate} onChange={e => setBusinessDate(e.target.value)} className="h-8 w-40" />
              <Button size="sm" variant="outline" onClick={() => setBusinessDate('')} className="border-slate-300 text-slate-600">
                Filtreyi Temizle
              </Button>
            </div>
          </div>

          {loading && (
            <div className="text-center py-8 text-slate-500">
              <Loader2 className="inline w-5 h-5 animate-spin" /> {t('cm.pages_ShiftHandoverPage.yukleniyor')}
            </div>
          )}

          {!loading && items.length === 0 && (
            <div className="text-center py-12 px-4 border-2 border-dashed border-slate-200 rounded-lg">
              <Inbox className="w-10 h-10 text-slate-300 mx-auto mb-2" />
              <div className="text-sm font-medium text-slate-700">{t('cm.pages_ShiftHandoverPage.bu_vardiyada_henuz_devir_notu_yok')}</div>
              <div className="text-xs text-slate-500 mt-1">{t('cm.pages_ShiftHandoverPage.ustteki_formdan_ilk_notu_siz_ekleyin')}</div>
            </div>
          )}

          <div className="space-y-2">
            {items.map(it => {
              const pm = prioMeta(it.priority);
              return (
                <div key={it.id} className={`border rounded-lg p-3 ${it.acknowledged ? 'bg-slate-50 opacity-75 border-slate-200' : it.priority === 'high' ? 'bg-white border-rose-200' : 'bg-white border-slate-200'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1.5">
                        <Badge className={pm.cls}>
                          {it.priority === 'high' && <AlertTriangle className="w-3 h-3 mr-1" />}
                          {pm.l}
                        </Badge>
                        <Badge variant="outline" className="text-xs border-slate-200">{it.business_date}</Badge>
                        <Badge variant="outline" className="text-xs border-slate-200">
                          {shiftLabel(it.shift)}{it.to_shift ? ` → ${shiftLabel(it.to_shift)}` : ''}
                        </Badge>
                        {it.related_room && <Badge variant="outline" className="text-xs border-slate-200">{t('cm.pages_ShiftHandoverPage.oda')} {it.related_room}</Badge>}
                        {it.acknowledged && (
                          <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">
                            <Check className="w-3 h-3 mr-1" />{t('cm.pages_ShiftHandoverPage.onaylandi')}
                          </Badge>
                        )}
                      </div>
                      <div className="text-sm text-slate-800 whitespace-pre-wrap">{it.note}</div>
                      <div className="text-[11px] text-slate-500 mt-2">
                        {it.from_user_name} · {new Date(it.created_at).toLocaleString('tr-TR')}
                        {it.acknowledged && it.acknowledged_by_name && (
                          <> · Onay: {it.acknowledged_by_name} ({new Date(it.acknowledged_at).toLocaleString('tr-TR')})</>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5 shrink-0">
                      {!it.acknowledged && (
                        <Button size="sm" onClick={() => ack(it.id)} className="bg-emerald-600 hover:bg-emerald-700 h-8">
                          <Check className="w-3.5 h-3.5 mr-1" /> {t('cm.pages_ShiftHandoverPage.onayla')}
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => remove(it.id)} className="h-8 text-rose-600 hover:text-rose-700 hover:bg-rose-50">
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
    </>
  );
}
