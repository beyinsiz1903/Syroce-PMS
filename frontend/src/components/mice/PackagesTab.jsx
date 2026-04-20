import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

const PKG_TYPES = [
  { key: 'wedding',    label: 'Düğün' },
  { key: 'conference', label: 'Konferans' },
  { key: 'corporate',  label: 'Kurumsal' },
  { key: 'social',     label: 'Sosyal' },
  { key: 'incentive',  label: 'Incentive' },
];

const blank = {
  name: '', type: 'wedding', description: '',
  min_pax: 0, max_pax: 0, base_price: 0, per_pax_price: 0,
  currency: 'TRY', items: [], active: true,
};

export default function PackagesTab() {
  const [packages, setPackages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(blank);
  const [editId, setEditId] = useState(null);
  const [quotePkg, setQuotePkg] = useState(null);
  const [quotePax, setQuotePax] = useState(50);
  const [quote, setQuote] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/mice/sales/packages', { params: { active_only: false } });
      setPackages(r.data?.packages || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    try {
      const payload = {
        ...form,
        min_pax: Number(form.min_pax) || 0,
        max_pax: Number(form.max_pax) || 0,
        base_price: Number(form.base_price) || 0,
        per_pax_price: Number(form.per_pax_price) || 0,
        items: (form.items || []).map((it) => ({
          ...it,
          quantity: Number(it.quantity) || 1,
          unit_price: Number(it.unit_price) || 0,
        })),
      };
      if (editId) await axios.put(`/mice/sales/packages/${editId}`, payload);
      else await axios.post('/mice/sales/packages', payload);
      setShowForm(false); setForm(blank); setEditId(null);
      await load();
    } catch (e) { alert('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const remove = async (id) => {
    if (!confirm('Paketi silmek istiyor musunuz?')) return;
    try { await axios.delete(`/mice/sales/packages/${id}`); await load(); }
    catch (e) { alert(e.response?.data?.detail || e.message); }
  };

  const edit = (p) => {
    setForm({ ...blank, ...p, items: p.items || [] });
    setEditId(p.id); setShowForm(true);
  };

  const runQuote = async () => {
    try {
      const r = await axios.post(`/mice/sales/packages/${quotePkg.id}/quote`, null,
        { params: { pax: Number(quotePax) || 1 } });
      setQuote(r.data);
    } catch (e) { alert(e.response?.data?.detail || e.message); }
  };

  const addItem = () => setForm({
    ...form,
    items: [...(form.items || []), { kind: 'addon', name: '', quantity: 1, unit_price: 0 }],
  });
  const updItem = (i, k, v) => {
    const items = [...form.items];
    items[i] = { ...items[i], [k]: v };
    setForm({ ...form, items });
  };
  const delItem = (i) => setForm({ ...form, items: form.items.filter((_, j) => j !== i) });

  const fmt = (v) => `₺${Number(v || 0).toLocaleString('tr-TR')}`;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Düğün, Konferans & Kurumsal Paketler</CardTitle>
          <Button size="sm" onClick={() => { setForm(blank); setEditId(null); setShowForm(true); }}>
            + Yeni Paket
          </Button>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b text-left">
              <tr>
                <th className="p-2">Paket</th>
                <th className="p-2">Tür</th>
                <th className="p-2 text-center">Pax</th>
                <th className="p-2 text-right">Baz</th>
                <th className="p-2 text-right">Pax Başı</th>
                <th className="p-2 text-center">Kalem</th>
                <th className="p-2">Durum</th>
                <th className="p-2 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={8} className="p-6 text-center text-gray-500">Yükleniyor...</td></tr>}
              {!loading && packages.length === 0 && (
                <tr><td colSpan={8} className="p-6 text-center text-gray-500">Paket yok.</td></tr>
              )}
              {packages.map((p) => (
                <tr key={p.id} className="border-b hover:bg-slate-50">
                  <td className="p-2">
                    <div className="font-medium">{p.name}</div>
                    {p.description && <div className="text-xs text-gray-500 line-clamp-1">{p.description}</div>}
                  </td>
                  <td className="p-2"><Badge variant="outline">{PKG_TYPES.find(t => t.key === p.type)?.label || p.type}</Badge></td>
                  <td className="p-2 text-center text-xs">{p.min_pax || 0}–{p.max_pax || '∞'}</td>
                  <td className="p-2 text-right">{fmt(p.base_price)}</td>
                  <td className="p-2 text-right">{fmt(p.per_pax_price)}</td>
                  <td className="p-2 text-center">{(p.items || []).length}</td>
                  <td className="p-2">{p.active
                    ? <Badge className="bg-emerald-100 text-emerald-700">Aktif</Badge>
                    : <Badge className="bg-gray-100 text-gray-600">Pasif</Badge>}</td>
                  <td className="p-2 text-right whitespace-nowrap">
                    <Button size="sm" variant="outline"
                            onClick={() => { setQuotePkg(p); setQuote(null); setQuotePax(p.min_pax || 50); }}>
                      Teklif
                    </Button>{' '}
                    <Button size="sm" variant="outline" onClick={() => edit(p)}>Düzenle</Button>{' '}
                    <Button size="sm" variant="ghost" className="text-rose-600"
                            onClick={() => remove(p.id)}>Sil</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Edit/create dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editId ? 'Paketi Düzenle' : 'Yeni Paket'}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Ad</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>Tür</Label>
              <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PKG_TYPES.map((t) => <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Açıklama</Label>
              <Textarea value={form.description}
                        onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div>
              <Label>Min Pax</Label>
              <Input type="number" value={form.min_pax}
                     onChange={(e) => setForm({ ...form, min_pax: e.target.value })} />
            </div>
            <div>
              <Label>Max Pax</Label>
              <Input type="number" value={form.max_pax}
                     onChange={(e) => setForm({ ...form, max_pax: e.target.value })} />
            </div>
            <div>
              <Label>Baz Fiyat (₺)</Label>
              <Input type="number" value={form.base_price}
                     onChange={(e) => setForm({ ...form, base_price: e.target.value })} />
            </div>
            <div>
              <Label>Pax Başı Fiyat (₺)</Label>
              <Input type="number" value={form.per_pax_price}
                     onChange={(e) => setForm({ ...form, per_pax_price: e.target.value })} />
            </div>

            <div className="col-span-2">
              <div className="flex justify-between items-center mb-2">
                <Label>Paket Kalemleri (Mekan / Menü / Oda / Ekstra)</Label>
                <Button size="sm" variant="outline" onClick={addItem}>+ Kalem Ekle</Button>
              </div>
              <div className="space-y-2">
                {(form.items || []).map((it, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 items-end p-2 bg-slate-50 rounded">
                    <div className="col-span-2">
                      <Label className="text-xs">Tür</Label>
                      <Select value={it.kind} onValueChange={(v) => updItem(i, 'kind', v)}>
                        <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="space">Mekan</SelectItem>
                          <SelectItem value="menu">Menü</SelectItem>
                          <SelectItem value="room">Oda</SelectItem>
                          <SelectItem value="resource">Kaynak</SelectItem>
                          <SelectItem value="addon">Ekstra</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="col-span-5">
                      <Label className="text-xs">Ad</Label>
                      <Input className="h-8" value={it.name}
                             onChange={(e) => updItem(i, 'name', e.target.value)} />
                    </div>
                    <div className="col-span-2">
                      <Label className="text-xs">Adet</Label>
                      <Input className="h-8" type="number" value={it.quantity}
                             onChange={(e) => updItem(i, 'quantity', e.target.value)} />
                    </div>
                    <div className="col-span-2">
                      <Label className="text-xs">Birim ₺</Label>
                      <Input className="h-8" type="number" value={it.unit_price}
                             onChange={(e) => updItem(i, 'unit_price', e.target.value)} />
                    </div>
                    <div className="col-span-1">
                      <Button size="sm" variant="ghost" className="text-rose-600 h-8"
                              onClick={() => delItem(i)}>×</Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="col-span-2 flex items-center gap-2">
              <input type="checkbox" id="active" checked={form.active}
                     onChange={(e) => setForm({ ...form, active: e.target.checked })} />
              <Label htmlFor="active">Aktif</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowForm(false)}>İptal</Button>
            <Button onClick={submit} disabled={!form.name}>Kaydet</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Quote dialog */}
      <Dialog open={!!quotePkg} onOpenChange={(o) => !o && setQuotePkg(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Fiyat Teklifi: {quotePkg?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Label>Pax</Label>
                <Input type="number" min={1} value={quotePax}
                       onChange={(e) => setQuotePax(e.target.value)} />
              </div>
              <Button onClick={runQuote}>Hesapla</Button>
            </div>
            {quote && (
              <Card><CardContent className="p-3 space-y-1 text-sm">
                <div className="flex justify-between"><span>Baz fiyat:</span> <span>{fmt(quote.breakdown.base_price)}</span></div>
                <div className="flex justify-between"><span>Pax × birim ({quote.pax}):</span> <span>{fmt(quote.breakdown.per_pax_total)}</span></div>
                <div className="flex justify-between"><span>Kalemler:</span> <span>{fmt(quote.breakdown.items_total)}</span></div>
                <div className="flex justify-between border-t pt-1 font-bold">
                  <span>Ara Toplam:</span>
                  <span className="text-emerald-600">{fmt(quote.subtotal)}</span>
                </div>
              </CardContent></Card>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
