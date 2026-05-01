import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Plus, Trash2, Pencil, Shield, X, Loader2 } from 'lucide-react';

const CONDITION_TYPES = [
  { value: 'occupancy_above', label: 'Doluluk ustu (%)' },
  { value: 'occupancy_below', label: 'Doluluk alti (%)' },
  { value: 'lead_time_below', label: 'Varisa kalan gun alti' },
  { value: 'lead_time_above', label: 'Varisa kalan gun ustu' },
  { value: 'day_of_week', label: 'Haftanin gunu' },
];

const ACTION_TYPES = [
  { value: 'increase_percent', label: 'Fiyati artir (%)' },
  { value: 'decrease_percent', label: 'Fiyati azalt (%)' },
];

const emptyRule = {
  name: '', description: '', condition_type: 'occupancy_above',
  condition_value: '', action_type: 'increase_percent', action_value: '',
  is_active: true, priority: 10, room_types: [],
};

export default function YieldRulesPanel() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState({ ...emptyRule });

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const res = await axios.get('/rms/yield-rules');
      setRules(res.data.rules || []);
    } catch { toast.error('Kurallar yüklenemedi'); }
    finally { setLoading(false); }
  };

  const openAdd = () => { setForm({ ...emptyRule }); setEditId(null); setShowForm(true); };

  const openEdit = (r) => {
    setForm({
      name: r.name, description: r.description || '',
      condition_type: r.condition_type, condition_value: r.condition_value,
      action_type: r.action_type, action_value: r.action_value,
      is_active: r.is_active, priority: r.priority, room_types: r.room_types || [],
    });
    setEditId(r.id);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.name || !form.condition_value || !form.action_value) {
      toast.error('Tüm alanlari doldurun');
      return;
    }
    try {
      const payload = {
        ...form,
        condition_value: form.condition_type === 'day_of_week' ? form.condition_value : Number(form.condition_value),
        action_value: Number(form.action_value),
        priority: Number(form.priority),
      };
      if (editId) {
        await axios.put(`/rms/yield-rules/${editId}`, payload);
        toast.success('Kural güncellendi');
      } else {
        await axios.post('/rms/yield-rules', payload);
        toast.success('Kural eklendi');
      }
      setShowForm(false);
      load();
    } catch { toast.error('Kural kaydedilemedi'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Bu kuralı silmek istediğinize emin misiniz?')) return;
    try {
      await axios.delete(`/rms/yield-rules/${id}`);
      toast.success('Kural silindi');
      load();
    } catch { toast.error('Kural silinemedi'); }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;

  return (
    <div data-testid="yield-rules-panel" className="space-y-4 p-1">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-800">Yield Kurallari</h2>
          <p className="text-sm text-slate-500">Otomatik fiyat ayarlama kuralları tanimlayın</p>
        </div>
        <Button size="sm" onClick={openAdd} data-testid="add-rule-btn">
          <Plus className="w-4 h-4 mr-1" /> Yeni Kural
        </Button>
      </div>

      {/* Form */}
      {showForm && (
        <Card className="border-sky-200 bg-sky-50/30" data-testid="yield-rule-form">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">{editId ? 'Kurali Düzenle' : 'Yeni Kural Ekle'}</CardTitle>
            <Button size="icon" variant="ghost" onClick={() => setShowForm(false)}><X className="w-4 h-4" /></Button>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Kural Adi</Label>
                <Input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="Ornek: Yüksek Doluluk Artisi" data-testid="rule-name-input" />
              </div>
              <div>
                <Label className="text-xs">Oncelik (1=en yüksek)</Label>
                <Input type="number" value={form.priority} onChange={e => setForm(p => ({ ...p, priority: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label className="text-xs">Açıklama</Label>
              <Input value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} placeholder="Kural aciklamasi" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Kosul Tipi</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm bg-white" value={form.condition_type}
                  onChange={e => setForm(p => ({ ...p, condition_type: e.target.value }))}>
                  {CONDITION_TYPES.map(ct => <option key={ct.value} value={ct.value}>{ct.label}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">Kosul Degeri</Label>
                <Input value={form.condition_value}
                  onChange={e => setForm(p => ({ ...p, condition_value: e.target.value }))}
                  placeholder={form.condition_type === 'day_of_week' ? 'friday,saturday' : '80'} data-testid="rule-condition-input" />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Aksiyon Tipi</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm bg-white" value={form.action_type}
                  onChange={e => setForm(p => ({ ...p, action_type: e.target.value }))}>
                  {ACTION_TYPES.map(at => <option key={at.value} value={at.value}>{at.label}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">Aksiyon Degeri (%)</Label>
                <Input type="number" value={form.action_value}
                  onChange={e => setForm(p => ({ ...p, action_value: e.target.value }))} placeholder="15" data-testid="rule-action-input" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={form.is_active} onCheckedChange={v => setForm(p => ({ ...p, is_active: v }))} />
              <Label className="text-xs">Aktif</Label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>İptal</Button>
              <Button size="sm" onClick={handleSave} data-testid="save-rule-btn">{editId ? 'Guncelle' : 'Kaydet'}</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Rules List */}
      <div className="space-y-2">
        {rules.length === 0 ? (
          <Card><CardContent className="py-8 text-center text-sm text-slate-400">Henüz kural tanimlanmamis.</CardContent></Card>
        ) : (
          rules.map(r => (
            <Card key={r.id} className={`transition-opacity ${r.is_active ? '' : 'opacity-50'}`} data-testid={`yield-rule-${r.id}`}>
              <CardContent className="flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <Shield className={`w-5 h-5 ${r.is_active ? 'text-sky-500' : 'text-slate-300'}`} />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{r.name}</span>
                      <Badge variant="outline" className="text-xs">P{r.priority}</Badge>
                      {!r.is_active && <Badge variant="secondary" className="text-xs">Pasif</Badge>}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">{r.description}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {CONDITION_TYPES.find(c => c.value === r.condition_type)?.label}: <strong>{r.condition_value}</strong>
                      {' → '}
                      {ACTION_TYPES.find(a => a.value === r.action_type)?.label}: <strong>{r.action_value}%</strong>
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Button size="icon" variant="ghost" onClick={() => openEdit(r)} data-testid={`edit-rule-${r.id}`}>
                    <Pencil className="w-4 h-4 text-slate-400" />
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => handleDelete(r.id)} data-testid={`delete-rule-${r.id}`}>
                    <Trash2 className="w-4 h-4 text-red-400" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
