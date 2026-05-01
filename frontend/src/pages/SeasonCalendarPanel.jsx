import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Plus, Trash2, Pencil, CalendarRange, X, Loader2 } from 'lucide-react';

const SEASON_TYPES = [
  { value: 'peak', label: 'Pik Sezon', color: '#f59e0b' },
  { value: 'high', label: 'Yüksek Sezon', color: '#ef4444' },
  { value: 'mid', label: 'Ara Sezon', color: '#22c55e' },
  { value: 'low', label: 'Düşük Sezon', color: '#3b82f6' },
];

const emptySeason = {
  name: '', season_type: 'high', start_date: '', end_date: '',
  rate_multiplier: 1.0, min_stay: 1, color: '#ef4444', is_active: true,
};

export default function SeasonCalendarPanel() {
  const [seasons, setSeasons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState({ ...emptySeason });

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const res = await axios.get('/rms/seasonal-calendar');
      setSeasons(res.data.seasons || []);
    } catch { toast.error('Sezon takvimi yüklenemedi'); }
    finally { setLoading(false); }
  };

  const openAdd = () => { setForm({ ...emptySeason }); setEditId(null); setShowForm(true); };

  const openEdit = (s) => {
    setForm({
      name: s.name, season_type: s.season_type,
      start_date: s.start_date, end_date: s.end_date,
      rate_multiplier: s.rate_multiplier, min_stay: s.min_stay,
      color: s.color || '#3b82f6', is_active: s.is_active,
    });
    setEditId(s.id);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.name || !form.start_date || !form.end_date) {
      toast.error('Gerekli alanlari doldurun');
      return;
    }
    try {
      const payload = {
        ...form,
        rate_multiplier: Number(form.rate_multiplier),
        min_stay: Number(form.min_stay),
      };
      if (editId) {
        await axios.put(`/rms/seasonal-calendar/${editId}`, payload);
        toast.success('Sezon güncellendi');
      } else {
        await axios.post('/rms/seasonal-calendar', payload);
        toast.success('Sezon eklendi');
      }
      setShowForm(false);
      load();
    } catch { toast.error('Sezon kaydedilemedi'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Bu sezonu silmek istediğinize emin misiniz?')) return;
    try {
      await axios.delete(`/rms/seasonal-calendar/${id}`);
      toast.success('Sezon silindi');
      load();
    } catch { toast.error('Sezon silinemedi'); }
  };

  const getTypeInfo = (t) => SEASON_TYPES.find(s => s.value === t) || SEASON_TYPES[0];

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;

  // Visual timeline
  const months = ['Oca', 'Sub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Agu', 'Eyl', 'Eki', 'Kas', 'Ara'];

  return (
    <div data-testid="season-calendar-panel" className="space-y-4 p-1">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-800">Sezon Takvimi</h2>
          <p className="text-sm text-slate-500">Fiyat carpanlarini ve minimum konaklama kurallarini belirleyin</p>
        </div>
        <Button size="sm" onClick={openAdd} data-testid="add-season-btn">
          <Plus className="w-4 h-4 mr-1" /> Yeni Sezon
        </Button>
      </div>

      {/* Visual Timeline */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-slate-600">Yıllık Gorunum</CardTitle>
        </CardHeader>
        <CardContent>
          <div data-testid="season-timeline" className="relative">
            <div className="flex border-b mb-3">
              {months.map((m, i) => (
                <div key={i} className="flex-1 text-center text-xs text-slate-500 pb-1 border-r last:border-r-0">{m}</div>
              ))}
            </div>
            <div className="space-y-1.5">
              {seasons.filter(s => s.is_active).map(s => {
                const startMonth = parseInt(s.start_date?.split('-')[1] || '1') - 1;
                const startDay = parseInt(s.start_date?.split('-')[2] || '1');
                const endMonth = parseInt(s.end_date?.split('-')[1] || '12') - 1;
                const endDay = parseInt(s.end_date?.split('-')[2] || '28');
                const leftPct = ((startMonth * 30 + startDay) / 365 * 100);
                const widthPct = Math.max(((endMonth * 30 + endDay) - (startMonth * 30 + startDay)) / 365 * 100, 3);

                return (
                  <div key={s.id} className="relative h-6">
                    <div className="absolute h-full rounded-sm flex items-center px-2 overflow-hidden text-xs font-medium text-white truncate"
                      style={{ left: `${leftPct}%`, width: `${widthPct}%`, backgroundColor: s.color || '#3b82f6' }}>
                      {s.name} (x{s.rate_multiplier})
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Form */}
      {showForm && (
        <Card className="border-amber-200 bg-amber-50/30" data-testid="season-form">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">{editId ? 'Sezonu Düzenle' : 'Yeni Sezon Ekle'}</CardTitle>
            <Button size="icon" variant="ghost" onClick={() => setShowForm(false)}><X className="w-4 h-4" /></Button>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Sezon Adi</Label>
                <Input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="Yaz Sezonu" data-testid="season-name-input" />
              </div>
              <div>
                <Label className="text-xs">Sezon Tipi</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm bg-white" value={form.season_type}
                  onChange={e => {
                    const info = getTypeInfo(e.target.value);
                    setForm(p => ({ ...p, season_type: e.target.value, color: info.color }));
                  }}>
                  {SEASON_TYPES.map(st => <option key={st.value} value={st.value}>{st.label}</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Baslangic Tarihi</Label>
                <Input type="date" value={form.start_date} onChange={e => setForm(p => ({ ...p, start_date: e.target.value }))} data-testid="season-start-input" />
              </div>
              <div>
                <Label className="text-xs">Bitis Tarihi</Label>
                <Input type="date" value={form.end_date} onChange={e => setForm(p => ({ ...p, end_date: e.target.value }))} data-testid="season-end-input" />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Fiyat Carpani</Label>
                <Input type="number" step="0.05" value={form.rate_multiplier}
                  onChange={e => setForm(p => ({ ...p, rate_multiplier: e.target.value }))} placeholder="1.30" data-testid="season-multiplier-input" />
                <span className="text-xs text-slate-400">1.0 = degisim yok, 1.3 = %30 artis</span>
              </div>
              <div>
                <Label className="text-xs">Min. Konaklama (gece)</Label>
                <Input type="number" value={form.min_stay}
                  onChange={e => setForm(p => ({ ...p, min_stay: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Renk</Label>
                <div className="flex items-center gap-2">
                  <input type="color" value={form.color} onChange={e => setForm(p => ({ ...p, color: e.target.value }))} className="w-8 h-8 rounded cursor-pointer" />
                  <span className="text-xs text-slate-500">{form.color}</span>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>İptal</Button>
              <Button size="sm" onClick={handleSave} data-testid="save-season-btn">{editId ? 'Guncelle' : 'Kaydet'}</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Seasons List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {seasons.length === 0 ? (
          <Card className="md:col-span-2"><CardContent className="py-8 text-center text-sm text-slate-400">Henüz sezon tanimlanmamis.</CardContent></Card>
        ) : (
          seasons.map(s => {
            const info = getTypeInfo(s.season_type);
            return (
              <Card key={s.id} className={`transition-opacity ${s.is_active ? '' : 'opacity-50'}`} data-testid={`season-${s.id}`}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-3 h-10 rounded-sm" style={{ backgroundColor: s.color || info.color }} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{s.name}</span>
                          <Badge variant="outline" className="text-xs" style={{ borderColor: s.color }}>{info.label}</Badge>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          <CalendarRange className="w-3 h-3 inline mr-1" />
                          {s.start_date} ~ {s.end_date}
                        </p>
                        <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                          <span>Carpan: <strong className="text-slate-700">x{s.rate_multiplier}</strong></span>
                          <span>Min. konaklama: <strong className="text-slate-700">{s.min_stay} gece</strong></span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button size="icon" variant="ghost" onClick={() => openEdit(s)} data-testid={`edit-season-${s.id}`}>
                        <Pencil className="w-4 h-4 text-slate-400" />
                      </Button>
                      <Button size="icon" variant="ghost" onClick={() => handleDelete(s.id)} data-testid={`delete-season-${s.id}`}>
                        <Trash2 className="w-4 h-4 text-red-400" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
