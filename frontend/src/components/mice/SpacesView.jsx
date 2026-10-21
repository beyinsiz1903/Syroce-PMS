import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Building2, Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { confirmDialog } from '@/lib/dialogs';
import { Modal } from './_shared';

const CAPACITIES = [
  ['capacity_theatre', 'Tiyatro'], ['capacity_classroom', 'Sınıf'],
  ['capacity_banquet', 'Banket'], ['capacity_cocktail', 'Kokteyl'],
  ['capacity_u_shape', 'U şekli'], ['capacity_boardroom', 'Yönetim kurulu'],
];
const emptySpace = () => ({ name: '', location: '', area_m2: 0, hourly_rate: 0,
  daily_rate: 0, currency: cachedTenantCurrency(), active: true, amenities: [], component_space_ids: [],
  ...Object.fromEntries(CAPACITIES.map(([key]) => [key, 0])) });

export default function SpacesView({ spaces, reload, canManage, limitReached }) {
  const [form, setForm] = useState(null);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const save = async e => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      const payload = { ...form, name: form.name.trim() };
      if (editing) await axios.put(`/mice/spaces/${editing}`, payload);
      else await axios.post('/mice/spaces', payload);
      setForm(null);
      toast.success('Mekan kaydedildi');
      await reload();
    } catch (error) {
      toast.error(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Mekan kaydedilemedi; alanları kontrol edin');
    } finally { setSaving(false); }
  };
  const remove = async space => {
    if (!await confirmDialog({ message: `${space.name} silinsin mi? Etkinliklerde kullanılmış salonlar silinemez.`, variant: 'danger' })) return;
    try {
      await axios.delete(`/mice/spaces/${space.id}`);
      await reload();
      toast.success('Mekan silindi');
    } catch (error) { toast.error(error.response?.data?.detail || 'Mekan silinemedi'); }
  };
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">Etkinliklerde kullanılan salonlar, düzen kapasiteleri ve kira tarifeleri.</p>
      {canManage && <Button disabled={limitReached} title={limitReached ? 'Mekan limitine ulaşıldı' : ''}
        onClick={() => { setEditing(null); setForm({ ...emptySpace(), client_request_id: crypto.randomUUID() }); }}><Plus className="mr-2 h-4 w-4" />Yeni Mekan</Button>}
    </div>
    {!spaces.length && <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">Henüz mekan tanımlanmadı. Örnek salonlar otomatik eklenmez.</p>}
    <div className="grid gap-4 md:grid-cols-2">
      {spaces.map(space => <Card key={space.id}>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="flex items-center gap-2 text-base"><Building2 className="h-4 w-4" />{space.name}</CardTitle>
            {canManage && <div className="flex gap-1">
              <Button size="sm" variant="ghost" aria-label={`${space.name} düzenle`}
                onClick={() => { setEditing(space.id); setForm({ ...emptySpace(), ...space }); }}><Pencil className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" aria-label={`${space.name} sil`} onClick={() => remove(space)}><Trash2 className="h-4 w-4" /></Button>
            </div>}
          </div>
          <p className="text-sm text-muted-foreground">{space.location || 'Konum belirtilmedi'} · {space.area_m2} m²</p>
          {space.active === false && <Badge variant="outline">Pasif — yeni etkinliklerde seçilemez</Badge>}
          {space.component_space_ids?.length > 0 && <p className="text-xs">Birleşik alan: {space.component_space_ids.map(id => spaces.find(s => s.id === id)?.name || id).join(' + ')}</p>}
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            {CAPACITIES.filter(([key]) => space[key] > 0).map(([key, label]) => <div key={key} className="rounded bg-muted p-2 text-center text-xs">
              <div className="text-muted-foreground">{label}</div><strong>{space[key]} kişi</strong>
            </div>)}
          </div>
          <p className="text-sm">Saatlik: {formatCurrency(space.hourly_rate, space.currency)} · Günlük: {formatCurrency(space.daily_rate, space.currency)}</p>
          <p className="text-xs text-muted-foreground">İlk saat minimum 1 saat; 6 saatten itibaren günlük, her başlayan 24 saat için ayrı kira.</p>
        </CardContent>
      </Card>)}
    </div>
    {form && <Modal title={editing ? 'Mekan Düzenle' : 'Yeni Mekan'} onClose={() => { if (!saving) setForm(null); }}>
      <form onSubmit={save} className="space-y-4">
        <label className="block space-y-1 text-sm">Mekan adı<Input required maxLength={200} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
        <label className="block space-y-1 text-sm">Konum / kat<Input value={form.location || ''} onChange={e => setForm({ ...form, location: e.target.value })} /></label>
        <div className="grid grid-cols-2 gap-3">
          {[['area_m2', 'Alan (m²)'], ...CAPACITIES, ['hourly_rate', 'Saatlik kira'], ['daily_rate', 'Günlük kira']].map(([key, label]) =>
            <label key={key} className="block space-y-1 text-sm">{label}<Input type="number" min="0" step={key.startsWith('capacity') ? '1' : '0.01'} required
              value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value === '' ? '' : Number(e.target.value) })} /></label>)}
          <label className="block space-y-1 text-sm">Para birimi<Input required minLength={3} maxLength={3} pattern="[A-Za-z]{3}"
            value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></label>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.active} onChange={e => setForm({ ...form, active: e.target.checked })} />Aktif</label>
        <fieldset className="space-y-2 rounded border p-3"><legend className="text-sm">Birleşik salonun fiziksel bileşenleri (isteğe bağlı)</legend><p className="text-xs text-muted-foreground">Boş bırakırsanız bağımsız salon olur. A+B tutulduğunda A ve B ayrı ayrı satılamaz. Etkinlik geçmişi oluşunca bileşim değiştirilemez.</p>{spaces.filter(s => s.id !== editing && s.active !== false).map(s => <label key={s.id} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={form.component_space_ids?.includes(s.id) || false} onChange={e => setForm({ ...form, component_space_ids: e.target.checked ? [...(form.component_space_ids || []), s.id] : form.component_space_ids.filter(id => id !== s.id) })} />{s.name}</label>)}</fieldset>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={saving} onClick={() => setForm(null)}>Vazgeç</Button><Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor…' : 'Kaydet'}</Button></div>
      </form>
    </Modal>}
  </div>;
}
