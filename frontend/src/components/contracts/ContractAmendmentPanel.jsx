import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

// Amend an approved contract without terminating it, from either side:
// one party proposes, the other approves or rejects, the proposer may
// withdraw. Current terms stay in force until approval.

const TERMS = { prepaid: 'Ön ödemeli', on_arrival: 'Girişte', net_7: '7 gün vadeli', net_15: '15 gün vadeli', net_30: '30 gün vadeli' };
const PARTY = { hotel: 'Otel', agency: 'Acente' };
const STATUS = { approved: 'onaylandı', rejected: 'reddedildi', withdrawn: 'geri çekildi' };

export function describeChanges(changes = {}, contract = {}) {
  const parts = [];
  if (changes.payment_terms) parts.push(`Ödeme: ${TERMS[contract.payment_terms] || contract.payment_terms || '—'} → ${TERMS[changes.payment_terms] || changes.payment_terms}`);
  if (changes.commission_pct != null) parts.push(`Komisyon: %${Number(contract.commission_pct ?? 0)} → %${Number(changes.commission_pct)}`);
  if (changes.cancellation_policy) {
    const p = changes.cancellation_policy;
    parts.push(`İptal: ${p.free_until_days_before} gün öncesine kadar ücretsiz, sonra %${p.penalty_pct}, no-show %${p.no_show_penalty_pct}`);
  }
  if (changes.valid_from || changes.valid_to) parts.push(`Geçerlilik: ${changes.valid_from || contract.valid_from} – ${changes.valid_to || contract.valid_to}`);
  return parts.join(' · ');
}

const formFrom = contract => ({
  payment_terms: contract.payment_terms || 'on_arrival',
  commission_pct: contract.commission_pct ?? '',
  free_until_days_before: contract.cancellation_policy?.free_until_days_before ?? 7,
  penalty_pct: contract.cancellation_policy?.penalty_pct ?? 50,
  no_show_penalty_pct: contract.cancellation_policy?.no_show_penalty_pct ?? 100,
  valid_from: contract.valid_from || '',
  valid_to: contract.valid_to || '',
  note: '',
});

export default function ContractAmendmentPanel({ side, api, base, contract, onChanged }) {
  const [form, setForm] = useState(null);
  const [reason, setReason] = useState('');
  const [limit, setLimit] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = contract.pending_amendment;
  const history = (contract.amendments || []).slice(-3).reverse();
  const id = `amend-${side}-${contract.id}`;

  const call = async (path, body, success) => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}${path}`, body);
      toast.success(success);
      setForm(null);
      setReason('');
      setLimit('');
      onChanged?.(data.contract);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem tamamlanamadı.');
      if (err.response?.status === 409) onChanged?.();
    } finally { setBusy(false); }
  };

  const propose = event => {
    event.preventDefault();
    const body = { note: form.note.trim() };
    if (form.payment_terms !== contract.payment_terms) body.payment_terms = form.payment_terms;
    if (contract.contract_type !== 'net_rate' && form.commission_pct !== '' && Number(form.commission_pct) !== Number(contract.commission_pct)) body.commission_pct = Number(form.commission_pct);
    const policy = { free_until_days_before: Number(form.free_until_days_before), penalty_pct: Number(form.penalty_pct), no_show_penalty_pct: Number(form.no_show_penalty_pct) };
    const current = contract.cancellation_policy || {};
    if (['free_until_days_before', 'penalty_pct', 'no_show_penalty_pct'].some(key => Number(current[key]) !== policy[key])) body.cancellation_policy = policy;
    if (form.valid_from !== contract.valid_from) body.valid_from = form.valid_from;
    if (form.valid_to !== contract.valid_to) body.valid_to = form.valid_to;
    if (Object.keys(body).length === 1) return toast.error('En az bir koşulu değiştirin.');
    call('', body, `Değişiklik teklifi ${side === 'hotel' ? 'acenteye' : 'otele'} iletildi; onaylanana kadar mevcut koşullar geçerli.`);
  };

  const approve = () => {
    const body = { note: '' };
    if (side === 'hotel' && limit !== '') Object.assign(body, { credit_limit: Number(limit), credit_currency: contract.credit_currency || contract.currency || 'TRY' });
    call(`/${pending.id}/approve`, body, 'Değişiklik onaylandı; yeni koşullar bundan sonraki rezervasyonlara uygulanır.');
  };

  return (
    <div className="mt-3 space-y-2 border-t pt-3 text-sm" data-testid={`amendments-${contract.id}`}>
      {pending ? (
        <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/40">
          <div className="font-medium">Değişiklik teklifi · {PARTY[pending.proposed_by_side]} önerdi</div>
          <div className="text-xs">{describeChanges(pending.changes, contract)}</div>
          {pending.note && <div className="text-xs text-slate-600 dark:text-slate-300">Not: {pending.note}</div>}
          <p className="text-xs text-slate-500">Onaylanana kadar mevcut koşullar geçerli. Onaydan sonra yeni koşullar yalnız yeni rezervasyonlara uygulanır.</p>
          {pending.proposed_by_side === side ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => call(`/${pending.id}/withdraw`, {}, 'Teklif geri çekildi.')}>Teklifi geri çek</Button>
          ) : (
            <div className="space-y-2">
              {side === 'hotel' && <div><Label htmlFor={`${id}-limit`}>Kredi limiti (isteğe bağlı, şu an {contract.credit_limit ?? 'tanımsız'})</Label>
                <Input id={`${id}-limit`} type="number" min="0" step="0.01" value={limit} onChange={e => setLimit(e.target.value)} /></div>}
              <Input aria-label="Ret gerekçesi" placeholder="Ret gerekçesi (reddederken zorunlu, en az 5 karakter)" value={reason} onChange={e => setReason(e.target.value)} />
              <div className="flex gap-2">
                <Button size="sm" disabled={busy} onClick={approve}>Değişikliği onayla</Button>
                <Button size="sm" variant="outline" className="text-red-700" disabled={busy || reason.trim().length < 5}
                  onClick={() => call(`/${pending.id}/reject`, { reason: reason.trim() }, 'Teklif reddedildi.')}>Reddet</Button>
              </div>
            </div>
          )}
        </div>
      ) : contract.status === 'approved' && (form ? (
        <form onSubmit={propose} className="grid gap-2 rounded-md border p-3 sm:grid-cols-2" data-testid={`amend-form-${contract.id}`}>
          <div><Label htmlFor={`${id}-terms`}>Ödeme koşulu</Label>
            <select id={`${id}-terms`} className="h-10 w-full rounded-md border px-3 text-sm" value={form.payment_terms} onChange={e => setForm(f => ({ ...f, payment_terms: e.target.value }))}>
              {Object.entries(TERMS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></div>
          {contract.contract_type !== 'net_rate' && <div><Label htmlFor={`${id}-pct`}>Komisyon %</Label>
            <Input id={`${id}-pct`} type="number" min="0" max="100" step="0.1" value={form.commission_pct} onChange={e => setForm(f => ({ ...f, commission_pct: e.target.value }))} /></div>}
          <div><Label htmlFor={`${id}-free`}>Ücretsiz iptal (gün önce)</Label>
            <Input id={`${id}-free`} type="number" min="0" max="365" value={form.free_until_days_before} onChange={e => setForm(f => ({ ...f, free_until_days_before: e.target.value }))} /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label htmlFor={`${id}-pen`}>İptal cezası %</Label><Input id={`${id}-pen`} type="number" min="0" max="100" value={form.penalty_pct} onChange={e => setForm(f => ({ ...f, penalty_pct: e.target.value }))} /></div>
            <div><Label htmlFor={`${id}-ns`}>No-show %</Label><Input id={`${id}-ns`} type="number" min="0" max="100" value={form.no_show_penalty_pct} onChange={e => setForm(f => ({ ...f, no_show_penalty_pct: e.target.value }))} /></div>
          </div>
          <div><Label htmlFor={`${id}-from`}>Başlangıç</Label><Input id={`${id}-from`} type="date" value={form.valid_from} onChange={e => setForm(f => ({ ...f, valid_from: e.target.value }))} /></div>
          <div><Label htmlFor={`${id}-to`}>Bitiş</Label><Input id={`${id}-to`} type="date" value={form.valid_to} onChange={e => setForm(f => ({ ...f, valid_to: e.target.value }))} /></div>
          <div className="sm:col-span-2"><Input aria-label="Değişiklik notu" placeholder="Not (isteğe bağlı)" maxLength={1000} value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))} /></div>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" size="sm" disabled={busy}>Teklifi gönder</Button>
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => setForm(null)}>Vazgeç</Button>
          </div>
        </form>
      ) : (
        <Button size="sm" variant="outline" onClick={() => setForm(formFrom(contract))}>Değişiklik öner</Button>
      ))}
      {history.length > 0 && <div className="space-y-1 text-xs text-slate-500">
        {history.map(item => <div key={item.id}>{String(item.decided_at || item.proposed_at).slice(0, 10)} · {PARTY[item.proposed_by_side]} önerdi, {STATUS[item.status] || item.status}: {describeChanges(item.changes, item.previous ? { ...contract, ...item.previous } : contract)}{item.decision_note ? ` (${item.decision_note})` : ''}</div>)}
      </div>}
    </div>
  );
}
