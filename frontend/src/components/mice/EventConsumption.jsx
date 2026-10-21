import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { confirmDialog } from '@/lib/dialogs';
import { formatCurrency } from '@/lib/currency';
import apiErrorText from '@/utils/apiErrorText';

export default function EventConsumption({ eventId, onChanged }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ source: '', recipe_id: '', batches: '', reason: '' });
  const load = async () => { const r = await axios.get(`/mice/events/${eventId}/consumption-options`); setData(r.data); setError(''); };
  const run = async action => { if (busy) return; setBusy(true); try { await action(); } catch (e) { setError(apiErrorText(e, 'Sarf işlemi tamamlanamadı')); } finally { setBusy(false); } };
  const submit = async e => {
    e.preventDefault();
    if (!await confirmDialog({ message: 'Fiilen tüketilen reçete miktarını onaylıyor musunuz? Ortak mutfak stoğu düşülecek ve maliyet etkinliğe eklenecek.' })) return;
    run(async () => {
      const [order_id, index] = form.source.split('|');
      await axios.post(`/mice/events/${eventId}/stock-consumptions`, { order_id, line_index: Number(index), recipe_id: form.recipe_id, batches: Number(form.batches), reason: form.reason });
      await load(); await onChanged?.(); toast.success('Sarf ve maliyet birlikte kaydedildi');
    });
  };
  return <section className="space-y-2 rounded border p-3">
    <h4 className="font-semibold">Reçeteden gerçek stok sarfı</h4>
    <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => run(load)}>Tamamlanan üretimleri / sarfları yükle</Button>
    {error && <p role="alert" className="text-xs">{error}</p>}
    {data && <>
      <p className="text-xs text-muted-foreground">{data.notice}</p>
      {data.consumptions.map(c => <p key={c.id} className="text-xs">{c.recipe_snapshot?.name} · {c.batches} parti · {formatCurrency(c.total_cost, c.currency)}</p>)}
      <form className="grid gap-2 sm:grid-cols-2" onSubmit={submit}>
        <label className="text-xs">Tamamlanan üretim satırı<select required className="w-full rounded border p-2" value={form.source} onChange={e => setForm({ ...form, source: e.target.value })}><option value="">Seçin</option>{data.orders.flatMap(o => o.lines.map((line, i) => <option key={`${o.id}:${i}`} value={`${o.id}|${i}`}>{line.name} · {line.quantity} {line.unit} · {o.id.slice(0, 8)}</option>))}</select></label>
        <label className="text-xs">Fiilen kullanılan reçete<select required className="w-full rounded border p-2" value={form.recipe_id} onChange={e => setForm({ ...form, recipe_id: e.target.value })}><option value="">Seçin</option>{data.recipes.map(r => <option key={r.id} value={r.id}>{r.menu_item_name} · {r.serving_size || '?'} porsiyonluk tanım</option>)}</select></label>
        <label className="text-xs">Tüketilen reçete partisi<Input required type="number" min="0.0001" step="any" value={form.batches} onChange={e => setForm({ ...form, batches: e.target.value })} /></label>
        <label className="text-xs">Sarf açıklaması<Input required minLength={10} maxLength={1000} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></label>
        <Button type="submit" disabled={busy}>Stoktan düş / maliyete ekle</Button>
      </form>
    </>}
  </section>;
}
