import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Plus, Trash2 } from 'lucide-react';
import { Field, Modal } from './_shared';
import { confirmDialog } from '@/lib/dialogs';

const COMP_EVENT_TYPES = [
  ['meeting', 'Toplantı'], ['conference', 'Konferans'],
  ['wedding', 'Düğün'], ['gala', 'Gala'],
  ['training', 'Eğitim'], ['other', 'Diğer'],
];
const SEASONS = [['all', 'Hepsi'], ['high', 'Yüksek'],
                  ['shoulder', 'Orta'], ['low', 'Düşük']];

const BanquetCompetitorTab = () => {
  const [comps, setComps] = useState([]);
  const [pos, setPos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', hotel_class: 5, capacity_max: 0,
                                     venues: '', notes: '', active: true });
  const [showRate, setShowRate] = useState(null);
  const [rates, setRates] = useState([]);
  const [rateForm, setRateForm] = useState({
    event_type: 'wedding', season: 'all',
    per_pax_price: 0, min_pax: 0, max_pax: 0,
    source: 'web', note: '',
  });

  const load = async () => {
    setLoading(true);
    try {
      const [c, p] = await Promise.all([
        axios.get('/banquet/competitors'),
        axios.get('/banquet/competitor-positioning'),
      ]);
      setComps(c.data.competitors || []);
      setPos(p.data.rows || []);
    } catch (e) {
      toast.error('Rakip listesi alınamadı');
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const openNew = () => {
    setEditing(null);
    setForm({ name: '', hotel_class: 5, capacity_max: 0,
              venues: '', notes: '', active: true });
    setShowForm(true);
  };
  const openEdit = (c) => {
    setEditing(c);
    setForm({ name: c.name, hotel_class: c.hotel_class || 5,
              capacity_max: c.capacity_max || 0,
              venues: (c.venues || []).join(', '),
              notes: c.notes || '', active: c.active !== false });
    setShowForm(true);
  };
  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      name: form.name.trim(),
      hotel_class: +form.hotel_class,
      capacity_max: +form.capacity_max,
      venues: form.venues.split(',').map((s) => s.trim()).filter(Boolean),
      notes: form.notes,
      active: form.active,
    };
    try {
      if (editing) await axios.put(`/banquet/competitors/${editing.id}`, payload);
      else await axios.post('/banquet/competitors', payload);
      toast.success(editing ? 'Rakip güncellendi' : 'Rakip eklendi');
      setShowForm(false);
      await load();
    } catch (e) { toast.error('Kaydedilemedi'); }
  };
  const remove = async (c) => {
    if (!await confirmDialog({ message: `"${c.name}" silinsin mi?`, variant: 'danger' })) return;
    try { await axios.delete(`/banquet/competitors/${c.id}`); await load(); }
    catch { toast.error('Silinemedi'); }
  };

  const openRates = async (c) => {
    setShowRate(c);
    setRateForm({
      event_type: 'wedding', season: 'all',
      per_pax_price: 0, min_pax: 0, max_pax: 0,
      source: 'web', note: '',
    });
    try {
      const r = await axios.get(`/banquet/competitors/${c.id}/rates`);
      setRates(r.data.rates || []);
    } catch { setRates([]); }
  };
  const submitRate = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`/banquet/competitors/${showRate.id}/rates`, {
        ...rateForm, per_pax_price: +rateForm.per_pax_price,
        min_pax: +rateForm.min_pax, max_pax: +rateForm.max_pax,
      });
      toast.success('Fiyat kaydedildi');
      const r = await axios.get(`/banquet/competitors/${showRate.id}/rates`);
      setRates(r.data.rates || []);
      await load();
    } catch { toast.error('Kaydedilemedi'); }
  };
  const removeRate = async (rid) => {
    try {
      await axios.delete(`/banquet/competitors/${showRate.id}/rates/${rid}`);
      setRates(rates.filter((r) => r.id !== rid));
      await load();
    } catch { toast.error('Silinemedi'); }
  };

  const positionLabel = {
    below_market: { t: 'Pazar altı', cls: 'bg-amber-100 text-amber-800' },
    in_band: { t: 'Pazarda', cls: 'bg-emerald-100 text-emerald-800' },
    above_market: { t: 'Pazar üstü', cls: 'bg-sky-100 text-sky-800' },
    no_data: { t: 'Veri yok', cls: 'bg-slate-100 text-slate-600' },
  };
  const evTypeLabel = Object.fromEntries(COMP_EVENT_TYPES);

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Rakip Oteller</CardTitle>
            <CardDescription>
              Banket pazarındaki rakip mekanlar ve fiyat snapshot'ları
            </CardDescription>
          </div>
          <Button size="sm" onClick={openNew}>
            <Plus className="w-3 h-3 mr-1" /> Rakip Ekle
          </Button>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          {loading ? (
            <p className="text-sm text-gray-500 p-4">Yükleniyor…</p>
          ) : comps.length === 0 ? (
            <p className="text-sm text-gray-500 p-4 text-center">
              Henüz rakip eklenmedi.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b text-left">
                <tr>
                  <th className="p-2">Otel</th><th className="p-2">Yıldız</th>
                  <th className="p-2">Maks Kapasite</th><th className="p-2">Salonlar</th>
                  <th className="p-2 text-right">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {comps.map((c) => (
                  <tr key={c.id} className="border-b hover:bg-slate-50">
                    <td className="p-2 font-medium">{c.name}
                      {!c.active && <Badge className="ml-1" variant="outline">Pasif</Badge>}
                    </td>
                    <td className="p-2">{c.hotel_class || '—'} </td>
                    <td className="p-2">{(c.capacity_max || 0).toLocaleString('tr-TR')}</td>
                    <td className="p-2 text-xs">{(c.venues || []).join(', ') || '—'}</td>
                    <td className="p-2 text-right space-x-1">
                      <Button size="sm" variant="outline" onClick={() => openRates(c)}>
                        Fiyatlar ({(c.competitor_rates || []).length})
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => openEdit(c)}>Düzenle</Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(c)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pozisyonlama</CardTitle>
          <CardDescription>
            Etkinlik tipi bazında sizin kişi başı ortalama gelir vs rakip aralığı
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          {pos.length === 0 ? (
            <p className="text-sm text-gray-500 p-4 text-center">
              Yeterli veri yok. Rakip fiyat ve kendi etkinliklerinizi ekleyin.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b text-left">
                <tr>
                  <th className="p-2">Etkinlik</th>
                  <th className="p-2">Bizim Ort. (₺/pax)</th>
                  <th className="p-2">Rakip Min</th>
                  <th className="p-2">Rakip Ort.</th>
                  <th className="p-2">Rakip Maks</th>
                  <th className="p-2">Kayıt</th>
                  <th className="p-2">Konum</th>
                </tr>
              </thead>
              <tbody>
                {pos.map((r) => (
                  <tr key={r.event_type} className="border-b">
                    <td className="p-2 font-medium">{evTypeLabel[r.event_type] || r.event_type}</td>
                    <td className="p-2">{r.our_avg_per_pax
                      ? `₺${r.our_avg_per_pax.toLocaleString('tr-TR')} (${r.events_count})`
                      : '—'}</td>
                    <td className="p-2">{r.competitor_min ? `₺${r.competitor_min.toLocaleString('tr-TR')}` : '—'}</td>
                    <td className="p-2">{r.competitor_avg ? `₺${r.competitor_avg.toLocaleString('tr-TR')}` : '—'}</td>
                    <td className="p-2">{r.competitor_max ? `₺${r.competitor_max.toLocaleString('tr-TR')}` : '—'}</td>
                    <td className="p-2 text-xs">{r.competitor_count || 0}</td>
                    <td className="p-2">
                      <Badge className={positionLabel[r.position]?.cls}>
                        {positionLabel[r.position]?.t || r.position}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {showForm && (
        <Modal title={editing ? 'Rakip Düzenle' : 'Yeni Rakip'} onClose={() => setShowForm(false)}>
          <form onSubmit={submit} className="space-y-2">
            <Field label="Otel Adı">
              <Input required value={form.name}
                     onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Yıldız (0-7)">
                <Input type="number" min="0" max="7" value={form.hotel_class}
                       onChange={(e) => setForm({ ...form, hotel_class: e.target.value })} />
              </Field>
              <Field label="Maks Kapasite">
                <Input type="number" min="0" value={form.capacity_max}
                       onChange={(e) => setForm({ ...form, capacity_max: e.target.value })} />
              </Field>
            </div>
            <Field label="Salonlar (virgülle ayrılmış)">
              <Input value={form.venues}
                     onChange={(e) => setForm({ ...form, venues: e.target.value })}
                     placeholder="Grand Salon, Bahçe, Teras" />
            </Field>
            <Field label="Notlar">
              <Input value={form.notes}
                     onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.active}
                     onChange={(e) => setForm({ ...form, active: e.target.checked })} />
              Aktif
            </label>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>İptal</Button>
              <Button type="submit">{editing ? 'Güncelle' : 'Ekle'}</Button>
            </div>
          </form>
        </Modal>
      )}

      {showRate && (
        <Modal title={`Fiyat Snapshot — ${showRate.name}`}
               onClose={() => setShowRate(null)} wide>
          <div className="space-y-3">
            <form onSubmit={submitRate}
                  className="grid grid-cols-7 gap-2 items-end border rounded p-2 bg-slate-50">
              <Field label="Etkinlik">
                <select className="w-full border rounded px-2 py-1.5 text-xs"
                        value={rateForm.event_type}
                        onChange={(e) => setRateForm({ ...rateForm, event_type: e.target.value })}>
                  {COMP_EVENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
              <Field label="Sezon">
                <select className="w-full border rounded px-2 py-1.5 text-xs"
                        value={rateForm.season}
                        onChange={(e) => setRateForm({ ...rateForm, season: e.target.value })}>
                  {SEASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
              <Field label="₺/pax">
                <Input type="number" min="0" value={rateForm.per_pax_price}
                       onChange={(e) => setRateForm({ ...rateForm, per_pax_price: e.target.value })}
                       required />
              </Field>
              <Field label="Min Pax">
                <Input type="number" min="0" value={rateForm.min_pax}
                       onChange={(e) => setRateForm({ ...rateForm, min_pax: e.target.value })} />
              </Field>
              <Field label="Maks Pax">
                <Input type="number" min="0" value={rateForm.max_pax}
                       onChange={(e) => setRateForm({ ...rateForm, max_pax: e.target.value })} />
              </Field>
              <Field label="Kaynak">
                <select className="w-full border rounded px-2 py-1.5 text-xs"
                        value={rateForm.source}
                        onChange={(e) => setRateForm({ ...rateForm, source: e.target.value })}>
                  <option value="web">Web</option>
                  <option value="phone">Telefon</option>
                  <option value="lost-deal">Kayıp Teklif</option>
                  <option value="other">Diğer</option>
                </select>
              </Field>
              <Button type="submit" size="sm">
                <Plus className="w-3 h-3 mr-1" /> Ekle
              </Button>
            </form>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 border-b text-left">
                  <tr>
                    <th className="p-2">Tarih</th><th className="p-2">Etkinlik</th>
                    <th className="p-2">Sezon</th><th className="p-2">₺/pax</th>
                    <th className="p-2">Min/Maks Pax</th><th className="p-2">Kaynak</th>
                    <th className="p-2 text-right">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.length === 0 ? (
                    <tr><td colSpan={7} className="p-3 text-center text-gray-500">
                      Henüz fiyat kaydı yok.
                    </td></tr>
                  ) : rates.map((r) => (
                    <tr key={r.id} className="border-b">
                      <td className="p-2">{(r.recorded_at || '').slice(0, 10)}</td>
                      <td className="p-2">{evTypeLabel[r.event_type] || r.event_type}</td>
                      <td className="p-2">{r.season}</td>
                      <td className="p-2 font-medium">
                        ₺{(r.per_pax_price || 0).toLocaleString('tr-TR')}
                      </td>
                      <td className="p-2">{r.min_pax || 0} - {r.max_pax || 0}</td>
                      <td className="p-2">{r.source || '—'}</td>
                      <td className="p-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => removeRate(r.id)}>
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default BanquetCompetitorTab;
