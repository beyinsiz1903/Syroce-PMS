import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { promptDialog } from '@/lib/dialogs';
import apiErrorText from '@/utils/apiErrorText';

const departments = { banquet: 'Banket', kitchen: 'Mutfak', av: 'Teknik / AV', housekeeping: 'Kat hizmetleri', security: 'Güvenlik', other: 'Diğer' };
const blank = { title: '', department: 'banquet', owner_name: '', owner_user_id: '', due_at: '', notes: '', kind: 'task', inventory_id: '', quantity: 1 };
export default function OperationTasks({ eventId, canManage }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const key = useRef(crypto.randomUUID());
  const handoverKeys = useRef({});
  const load = async () => { const response = await axios.get(`/mice/events/${eventId}/tasks`); setData(response.data); setError(''); };
  useEffect(() => { let active = true; axios.get(`/mice/events/${eventId}/tasks`).then(r => { if (active) setData(r.data); }).catch(e => { if (active) setError(apiErrorText(e, 'Görevler yüklenemedi')); }); return () => { active = false; }; }, [eventId]);
  const run = async fn => {
    if (busy) return;
    setBusy(true);
    try { await fn(); await load(); }
    catch (e) { toast.error(apiErrorText(e, 'Görev işlemi tamamlanamadı')); }
    finally { setBusy(false); }
  };
  const save = e => { e.preventDefault(); run(async () => {
    await axios.post(`/mice/events/${eventId}/tasks`, { ...form, due_at: form.due_at || null, owner_user_id: form.owner_user_id || null, inventory_id: form.inventory_id || null, client_request_id: key.current });
    key.current = crypto.randomUUID(); setForm(null); toast.success('Görev kaydedildi');
  }); };
  const transition = async (task, status) => {
    const reason = status === 'cancelled' ? await promptDialog({ title: 'Görev iptali', message: 'En az 10 karakter iptal gerekçesi' }) : '';
    if (reason == null) return;
    run(() => axios.post(`/mice/events/${eventId}/tasks/${task.id}/transition`, { status, reason }));
  };
  const handover = async (task, action) => {
    const raw = await promptDialog({ title: action === 'deliver' ? 'Kısmi ekipman teslimi' : 'Kısmi ekipman iadesi', message: 'Bu işlemde fiziksel olarak teslim/iade edilen miktarı girin.', defaultValue: '' });
    if (raw == null) return;
    const quantity = Number(String(raw).replace(',', '.'));
    if (!Number.isFinite(quantity) || quantity <= 0) { toast.error('Pozitif miktar girin'); return; }
    const id = `${task.id}:${action}:${quantity}`;
    handoverKeys.current[id] ||= crypto.randomUUID();
    run(async () => { await axios.post(`/mice/events/${eventId}/tasks/${task.id}/handover`, { action, quantity, request_id: handoverKeys.current[id] }); await load(); delete handoverKeys.current[id]; });
  };
  if (error) return <p role="alert">{error}<Button variant="outline" onClick={() => run(load)}>Tekrar dene</Button></p>;
  if (!data) return <p role="status">Departman görevleri yükleniyor…</p>;
  return <section className="space-y-3 rounded border p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">Departman görevleri ve ekipman teslimi</h3><Button size="sm" variant="outline" disabled={busy} onClick={() => run(load)}>Görevleri yenile</Button></div>
    <p className="text-xs text-muted-foreground">{data.notice}</p>
    {canManage && !['completed', 'cancelled'].includes(data.event_status) && <Button size="sm" variant="outline" onClick={() => { key.current = crypto.randomUUID(); setForm({ ...blank }); }}>Yeni görev / teslim planı</Button>}
    {form && <form onSubmit={save} className="space-y-2 rounded border p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-xs">Görev başlığı<Input required maxLength={200} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} /></label>
        <label className="text-xs">Sorumlu kişi<Input required maxLength={200} value={form.owner_name} onChange={e => setForm({ ...form, owner_name: e.target.value })} /></label>
        <label className="text-xs">Yetkili personel hesabı<select className="w-full rounded border p-2" value={form.owner_user_id} onChange={e => { const person = data.assignees?.find(u => u.id === e.target.value); setForm({ ...form, owner_user_id: e.target.value, owner_name: person?.name || form.owner_name }); }}><option value="">Yalnız yönetici / departman yetkisi</option>{data.assignees?.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
        <label className="text-xs">Departman<select className="w-full rounded border p-2" value={form.department} onChange={e => setForm({ ...form, department: e.target.value })}>{Object.entries(departments).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label className="text-xs">Hedef zaman (tesis yerel saati)<Input type="datetime-local" value={form.due_at} onChange={e => setForm({ ...form, due_at: e.target.value })} /></label>
        <label className="text-xs">İşlem türü<select className="w-full rounded border p-2" value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })}><option value="task">Departman görevi</option><option value="equipment">Ekipman teslim / iade</option></select></label>
        {form.kind === 'equipment' && <>
          <label className="text-xs">Ayrılan ekipman<select required className="w-full rounded border p-2" value={form.inventory_id} onChange={e => setForm({ ...form, inventory_id: e.target.value })}><option value="">Seçin</option>{(data.equipment || []).filter((r, i, all) => all.findIndex(x => x.id === r.id) === i).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
          <label className="text-xs">Teslim miktarı<Input required type="number" min="0.01" step="0.01" value={form.quantity} onChange={e => setForm({ ...form, quantity: Number(e.target.value) })} /></label>
        </>}
      </div>
      <label className="block text-xs">Görev / teslim notu<Input maxLength={1000} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
      <div className="flex gap-2"><Button size="sm" type="submit" disabled={busy}>Görevi kaydet</Button><Button size="sm" type="button" variant="ghost" disabled={busy} onClick={() => setForm(null)}>Vazgeç</Button></div>
    </form>}
    {!data.tasks.length && <p className="text-xs">Henüz departman görevi yok.</p>}
    {data.tasks.map(task => <article key={task.id} className="space-y-2 rounded border p-2 text-xs">
      <p className="font-semibold">{task.title} · {departments[task.department]} · {task.owner_name}</p>
      <p>{task.kind === 'equipment' ? `${task.quantity} birim · ` : ''}{({ pending: 'Bekliyor', acknowledged: task.kind === 'equipment' ? 'Teslim edildi' : 'Teslim alındı', completed: task.kind === 'equipment' ? 'İade alındı' : 'Tamamlandı', cancelled: 'İptal' })[task.status]}{task.due_at ? ` · Hedef: ${task.due_at.slice(0, 16).replace('T', ' ')}` : ''}</p>
      {task.notes && <p>{task.notes}</p>}
      {task.kind === 'equipment' && <p>Teslim: {task.delivered_quantity ?? (task.status === 'acknowledged' ? task.quantity : 0)} / {task.quantity} · İade: {task.returned_quantity ?? (task.status === 'completed' ? task.quantity : 0)}</p>}
      {task.completed_by && <p>Kaydeden: {task.completed_by} · {task.completed_at?.slice(0, 16)}</p>}
      {(canManage || task.can_transition) && <div className="flex flex-wrap gap-2">
        {task.status === 'pending' && <Button size="sm" variant="outline" disabled={busy || data.event_status === 'cancelled'} onClick={() => transition(task, 'acknowledged')}>{task.kind === 'equipment' ? 'Teslim edildi kaydet' : 'Görevi teslim al'}</Button>}
        {task.status === 'acknowledged' && <Button size="sm" disabled={busy} onClick={() => transition(task, 'completed')}>{task.kind === 'equipment' ? 'İade alındı kaydet' : 'Görevi tamamla'}</Button>}
        {['pending', 'acknowledged'].includes(task.status) && !(task.kind === 'equipment' && task.status === 'acknowledged') && <Button size="sm" variant="ghost" disabled={busy} onClick={() => transition(task, 'cancelled')}>Görevi iptal et</Button>}
        {task.kind === 'equipment' && !['completed', 'cancelled'].includes(task.status) && <>
          <Button size="sm" variant="outline" disabled={busy || ['completed', 'cancelled'].includes(data.event_status)} onClick={() => handover(task, 'deliver')}>Kısmi teslim</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => handover(task, 'return')}>Kısmi iade</Button>
        </>}
      </div>}
    </article>)}
  </section>;
}
