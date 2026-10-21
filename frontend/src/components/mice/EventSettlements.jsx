import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { confirmDialog } from '@/lib/dialogs';
import { formatCurrency } from '@/lib/currency';
import apiErrorText from '@/utils/apiErrorText';

const blank = () => ({ request_id: crypto.randomUUID(), kind: 'collection', amount: '', method: 'cash', bank_account_id: '', original_payment_id: '', exchange_rate: '', reference: '', reason: '' });
export default function EventSettlements({ eventId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { const r = await axios.get(`/mice/events/${eventId}/settlements`); setData(r.data); setError(''); }, [eventId]);
  useEffect(() => { let active = true; axios.get(`/mice/events/${eventId}/settlements`).then(r => { if (active) setData(r.data); }).catch(e => { if (active) setError(apiErrorText(e, 'Tahsilat bilgisi yüklenemedi')); }); return () => { active = false; }; }, [eventId]);
  const submit = async e => {
    e.preventDefault();
    if (busy) return;
    if (!await confirmDialog({ message: `Bu işlem gerçek ${form.kind === 'refund' ? 'iadeyi' : 'tahsilatı'} kaydeder ve muhasebeye işler. Paranın gerçekten hareket ettiğini doğruluyor musunuz?` })) return;
    setBusy(true);
    const payload = { ...form, amount: Number(form.amount), exchange_rate: form.exchange_rate === '' ? null : Number(form.exchange_rate), bank_account_id: form.bank_account_id || null, original_payment_id: form.original_payment_id || null };
    try {
      await axios.post(`/mice/events/${eventId}/settlements`, payload);
      setForm(blank()); await load(); toast.success('Finansal hareket kaydedildi');
    } catch (err) { toast.error(apiErrorText(err, 'Finansal hareket tamamlanamadı; aynı isteği tekrar deneyin')); try { await load(); } catch { /* Preserve the original error and request key. */ } }
    finally { setBusy(false); }
  };
  if (error) return <p role="alert">{error}<Button variant="outline" onClick={() => load().catch(e => setError(apiErrorText(e, 'Yüklenemedi')))}>Tekrar dene</Button></p>;
  if (!data?.totals) return <p role="status">Tahsilatlar yükleniyor…</p>;
  const locked = Boolean(data.pending);
  const pendingForm = data.pending?.request;
  const startRefund = payment => setForm({ ...blank(), kind: 'refund', method: payment.method, bank_account_id: payment.bank_account_id || '', original_payment_id: payment.id, exchange_rate: payment.gl_exchange_rate });
  return <section className="space-y-3 rounded border p-3">
    <h3 className="font-semibold">Gerçek tahsilat ve kısmi iade</h3>
    <p className="text-xs text-muted-foreground">{data.notice}</p>
    <p className="text-sm">Net tahsilat: {formatCurrency(data.totals.net_collected, data.currency)} · Açık tutar: {formatCurrency(data.totals.outstanding, data.currency)} · Müşteri alacağı: {formatCurrency(data.totals.customer_credit, data.currency)}</p>
    {locked && <div role="alert" className="space-y-2 rounded border p-2 text-xs">Bekleyen finans işlemi var. Yeni işlem açmayın; muhasebe ayarları düzeltildikten sonra aynı isteği tamamlayın.<Button type="button" size="sm" variant="outline" onClick={() => setForm({ ...pendingForm, bank_account_id: pendingForm.bank_account_id || '', original_payment_id: pendingForm.original_payment_id || '', exchange_rate: pendingForm.exchange_rate ?? '' })}>Bekleyen isteği forma al</Button></div>}
    {data.payments.map(p => <div key={p.id} className="flex flex-wrap items-center justify-between gap-2 border-t py-2 text-xs"><span>{p.payment_type === 'refund' ? 'İade' : 'Tahsilat'} · {formatCurrency(p.amount, data.currency)} · {p.reference} · {p.business_date} · Muhasebe: {p.gl_journal_entry_id}</span>{p.payment_type !== 'refund' && <Button type="button" size="sm" variant="outline" disabled={busy || locked} onClick={() => startRefund(p)}>Kısmi / tam iade kaydet</Button>}</div>)}
    <form onSubmit={submit} className="space-y-2">
      <p className="text-sm font-medium">{form.kind === 'refund' ? 'Seçilen tahsilata iade' : 'Yeni tahsilat'}</p>
      <fieldset disabled={busy || locked} className="grid gap-2 sm:grid-cols-2">
        <label className="text-xs">Tutar ({data.currency})<Input required type="number" min="0.01" step="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></label>
        <label className="text-xs">Yöntem<select className="w-full rounded border p-2" disabled={form.kind === 'refund'} value={form.method} onChange={e => setForm({ ...form, method: e.target.value, bank_account_id: '' })}><option value="cash">Nakit</option><option value="card">Kart</option><option value="bank_transfer">Banka havalesi</option></select></label>
        {form.method !== 'cash' && <label className="text-xs">Aynı dövizde banka / kart hesabı<select required disabled={form.kind === 'refund'} className="w-full rounded border p-2" value={form.bank_account_id} onChange={e => setForm({ ...form, bank_account_id: e.target.value })}><option value="">Hesap seçin</option>{data.bank_accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>}
        {data.currency !== 'TRY' && <label className="text-xs">TRY muhasebe kuru<Input required disabled={form.kind === 'refund'} type="number" min="0.000001" step="any" value={form.exchange_rate} onChange={e => setForm({ ...form, exchange_rate: e.target.value })} /></label>}
        <label className="text-xs">Makbuz / banka referansı<Input required minLength={3} maxLength={200} value={form.reference} onChange={e => setForm({ ...form, reference: e.target.value })} /></label>
        <label className="text-xs">Açıklama / iade gerekçesi<Input required minLength={10} maxLength={1000} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></label>
        {!locked && <Button type="button" variant="ghost" onClick={() => setForm(blank())}>Formu temizle</Button>}
      </fieldset>
      <Button type="submit" disabled={busy || (locked && form.request_id !== pendingForm.request_id)}>{busy ? 'Kaydediliyor…' : locked ? 'Aynı bekleyen işlemi tamamla' : 'Gerçek hareketi kaydet'}</Button>
    </form>
  </section>;
}
