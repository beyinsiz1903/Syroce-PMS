import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Plus, Trash2 } from 'lucide-react';
import { Field, Modal } from './_shared';

const ResourcesView = ({ resources, reload }) => {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'av', total_stock: 1, unit: 'unit',
                                     unit_price: 0, currency: 'TRY' });
  const create = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/mice/resources', form);
      toast.success('Envanter eklendi');
      setShowForm(false);
      setForm({ name: '', type: 'av', total_stock: 1, unit: 'unit', unit_price: 0, currency: 'TRY' });
      await reload();
    } catch (err) { toast.error(err.response?.data?.detail || 'Hata'); }
  };
  const remove = async (id) => {
    if (!confirm('Silinsin mi?')) return;
    try { await axios.delete(`/mice/resources/${id}`); await reload(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  return (
    <Card><CardContent className="p-3">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-semibold">Kaynak Envanteri (AV / Dekor)</h3>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus className="w-3 h-3 mr-1" /> Yeni Kaynak
        </Button>
      </div>
      {resources.length === 0 && <p className="text-center text-gray-500 p-4">Envanter yok.</p>}
      <div className="grid md:grid-cols-3 gap-2">
        {resources.map((r) => (
          <Card key={r.id}>
            <CardContent className="p-3">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-semibold">{r.name}</div>
                  <div className="text-xs text-gray-500">{r.type}</div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => remove(r.id)}>
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
              <div className="mt-2 text-sm">
                Stok: <span className="font-bold">{r.total_stock}</span> {r.unit}
              </div>
              <div className="text-sm">
                Birim: <span className="font-bold">₺{r.unit_price?.toLocaleString('tr-TR')}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {showForm && (
        <Modal title="Yeni Kaynak" onClose={() => setShowForm(false)}>
          <form onSubmit={create} className="space-y-2">
            <Field label="Ad"><Input required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Tip">
                <select className="w-full border rounded px-2 py-1.5" value={form.type}
                        onChange={(e) => setForm({ ...form, type: e.target.value })}>
                  {['av', 'decor', 'fb', 'other'].map((x) => <option key={x}>{x}</option>)}
                </select>
              </Field>
              <Field label="Birim"><Input value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })} /></Field>
              <Field label="Toplam Stok"><Input type="number" required value={form.total_stock}
                onChange={(e) => setForm({ ...form, total_stock: +e.target.value })} /></Field>
              <Field label="Birim ₺"><Input type="number" value={form.unit_price}
                onChange={(e) => setForm({ ...form, unit_price: +e.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>İptal</Button>
              <Button type="submit">Oluştur</Button>
            </div>
          </form>
        </Modal>
      )}
    </CardContent></Card>
  );
};

export default ResourcesView;
