import { useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import apiErrorText from '@/utils/apiErrorText';

export function LayoutDrawing({ plan }) {
  return <svg viewBox={`0 0 ${plan.width} ${plan.height}`} role="img" aria-label="Ölçekli masa yerleşimi" className="max-h-80 w-full rounded border bg-muted/20"><rect x="0" y="0" width={plan.width} height={plan.height} fill="none" stroke="currentColor" strokeWidth="0.03" />{plan.tables.map(t => <g key={t.label}><rect x={t.x} y={t.y} width={t.width} height={t.height} className="fill-primary/10 stroke-primary" strokeWidth="0.03" /><text x={Number(t.x) + Number(t.width) / 2} y={Number(t.y) + Number(t.height) / 2} textAnchor="middle" dominantBaseline="middle" fontSize="0.25" fill="currentColor">{t.label} · {t.seats}</text></g>)}</svg>;
}

export default function SeatingPlan({ eventId, canManage, onChanged }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = async () => { const r = await axios.get(`/mice/events/${eventId}/seating-plans`); setData(r.data); };
  const run = async fn => { if (busy) return; setBusy(true); try { await fn(); setError(''); } catch (e) { setError(apiErrorText(e, 'Yerleşim işlemi başarısız')); } finally { setBusy(false); } };
  const edit = (index, plan) => setForm(plan ? { ...plan, expected_revision: data.expected_revision } : { booking_index: index, width: 10, height: 10, tables: [], expected_revision: data.expected_revision });
  return <section className="space-y-2 rounded border p-3">
    <h3 className="font-semibold">Masa ve oturma düzeni</h3>
    <Button size="sm" type="button" variant="outline" disabled={busy} onClick={() => run(load)}>Yerleşimleri yükle</Button>
    {error && <p role="alert" className="text-xs">{error}</p>}
    {data && <><p className="text-xs text-muted-foreground">{data.notice}</p>{data.bookings.map((b, i) => {
      const plan = data.plans.find(p => p.booking_index === i);
      const stale = plan && (plan.space_id !== b.space_id || plan.starts_at !== b.starts_at || plan.ends_at !== b.ends_at);
      return <div key={i} className="space-y-2 border-t pt-2"><p className="text-sm">{b.space_name} · {b.starts_at.slice(0, 16)}</p>{stale && <p role="alert" className="text-xs">Salon veya saat değişmiş. Eski çizimi kullanmayın; yerleşimi yeniden doğrulayın.</p>}{plan && <LayoutDrawing plan={plan} />}{canManage && <Button type="button" size="sm" variant="outline" onClick={() => edit(i, plan)}>Yerleşimi düzenle</Button>}</div>;
    })}</>}
    {form && <form className="space-y-2" onSubmit={e => { e.preventDefault(); run(async () => { await axios.put(`/mice/events/${eventId}/seating-plan`, form); await load(); setForm(null); await onChanged?.(); }); }}>
      <div className="grid grid-cols-2 gap-2">{['width', 'height'].map(k => <label key={k} className="text-xs">Salon {k === 'width' ? 'genişliği' : 'derinliği'} (m)<Input required type="number" min="0.1" max="100" step="0.1" value={form[k]} onChange={e => setForm({ ...form, [k]: Number(e.target.value) })} /></label>)}</div>
      {form.tables.map((t, i) => <div key={i} className="grid grid-cols-2 gap-2 rounded border p-2 sm:grid-cols-4">{[['label', 'Masa adı'], ['seats', 'Kişi'], ['x', 'X (m)'], ['y', 'Y (m)'], ['width', 'Genişlik (m)'], ['height', 'Derinlik (m)']].map(([k, label]) => <label key={k} className="text-xs">{label}<Input required type={k === 'label' ? 'text' : 'number'} min={k === 'seats' ? 1 : ['x', 'y'].includes(k) ? 0 : 0.1} step={k === 'seats' ? 1 : 'any'} value={t[k]} onChange={e => setForm({ ...form, tables: form.tables.map((r, index) => index === i ? { ...r, [k]: k === 'label' ? e.target.value : Number(e.target.value) } : r) })} /></label>)}<Button size="sm" type="button" variant="ghost" onClick={() => setForm({ ...form, tables: form.tables.filter((_, n) => n !== i) })}>Masayı kaldır</Button></div>)}
      <Button size="sm" type="button" variant="outline" disabled={form.tables.length >= 100} onClick={() => setForm({ ...form, tables: [...form.tables, { label: `Masa ${form.tables.length + 1}`, seats: 8, x: 0, y: 0, width: 2, height: 2 }] })}>Masa ekle</Button>
      {form.tables.length > 0 && <LayoutDrawing plan={form} />}
      <div className="flex gap-2"><Button size="sm" type="submit" disabled={busy}>Yerleşimi doğrula / kaydet</Button><Button size="sm" type="button" variant="ghost" disabled={busy} onClick={() => setForm(null)}>Vazgeç</Button></div>
    </form>}
  </section>;
}
