import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { confirmDialog } from '@/lib/dialogs';
import { formatCurrency } from '@/lib/currency';
import apiErrorText from '@/utils/apiErrorText';

const blank = () => ({ request_id: crypto.randomUUID(), kind: 'collection', amount: '', method: 'cash',
  bank_account_id: '', original_payment_id: '', exchange_rate: '', reference: '', reason: '' });
const methods = { cash: 'Nakit', card: 'Kart', bank_transfer: 'Banka havalesi' };

export default function AppointmentSettlements({ appointmentId, onRecorded }) {
  const endpoint = `/spa/appointments/${appointmentId}/settlements`;
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const submitting = useRef(false);
  const load = useCallback(async () => {
    const response = await axios.get(endpoint);
    setData(response.data);
    setError('');
    return response.data;
  }, [endpoint]);
  useEffect(() => {
    let active = true;
    axios.get(endpoint).then(r => { if (active) setData(r.data); })
      .catch(e => { if (active) setError(apiErrorText(e, 'SPA tahsilatları yüklenemedi')); });
    return () => { active = false; };
  }, [endpoint]);

  const reconcile = async () => {
    try {
      const current = await load();
      if (current.payments.some(p => p.request_id === form.request_id)) {
        setForm(blank());
        onRecorded?.();
      }
      setUncertain(false);
    } catch (e) { setError(apiErrorText(e, 'İşlem durumu doğrulanamadı; yeni ödeme kaydetmeyin')); }
  };
  const submit = async e => {
    e.preventDefault();
    if (submitting.current || uncertain) return;
    submitting.current = true;
    setBusy(true);
    const payload = { ...form, amount: Number(form.amount),
      exchange_rate: form.exchange_rate === '' ? null : Number(form.exchange_rate),
      bank_account_id: form.bank_account_id || null, original_payment_id: form.original_payment_id || null };
    try {
      const accepted = await confirmDialog({ message: `${form.kind === 'refund' ? 'İade edilen' : 'Alınan'} ${formatCurrency(payload.amount, data.currency)} tutarı manuel deftere kaydedilecek. Bu işlem bankaya/karta talimat göndermez. Onaylıyor musunuz?` });
      if (!accepted) return;
      await axios.post(endpoint, payload);
      setForm(blank());
      await load();
      onRecorded?.();
      toast.success('SPA hareketi ve makbuz kaydı oluşturuldu');
    } catch (e) {
      setUncertain(true);
      toast.error(apiErrorText(e, 'Sonuç doğrulanamadı. Yeni işlem açmadan önce durumu yenileyin.'));
      try { await load(); } catch { /* Keep the exact request and block new writes. */ }
    } finally { setBusy(false); submitting.current = false; }
  };
  if (!data) return <section className="rounded-lg border p-4" aria-label="SPA tahsilatları">
    {error ? <p role="alert">{error}</p> : <p role="status">SPA tahsilatları yükleniyor…</p>}
    {error && <Button variant="outline" onClick={() => load().catch(e => setError(apiErrorText(e)))}>Tekrar dene</Button>}
  </section>;

  const pending = data.pending?.request;
  const locked = Boolean(pending) || uncertain;
  const startRefund = p => setForm({ ...blank(), kind: 'refund', method: p.method,
    bank_account_id: p.bank_account_id || '', original_payment_id: p.id, exchange_rate: p.gl_exchange_rate });
  return <section aria-label="SPA tahsilatları" className="space-y-4 rounded-xl border bg-white p-4">
    <div><h3 className="font-semibold">Dış misafir · Ödeme ve makbuz</h3>
      <p className="text-sm text-muted-foreground">{data.guest_name} · {data.service_name}</p></div>
    <p className="text-xs text-muted-foreground">{data.notice}</p>
    <dl className="grid gap-3 sm:grid-cols-3">
      {[['Hizmet bedeli', data.totals.service_total], ['Net tahsilat', data.totals.net_collected], ['Kalan', data.totals.outstanding]].map(([label, amount]) =>
        <div key={label} className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="font-semibold">{formatCurrency(amount, data.currency)}</dd></div>)}
    </dl>
    {error && <p role="alert">{error}</p>}
    {uncertain && <div role="alert" className="rounded border border-amber-300 p-3 text-sm">
      İşlem sonucu henüz uzlaştırılmadı. Yeni ödeme açmayın.
      <Button type="button" variant="outline" disabled={busy} onClick={reconcile}>Durumu yenile</Button>
    </div>}
    {pending && <div role="alert" className="space-y-2 rounded border border-amber-300 p-3 text-sm">
      Tamamlanmayı bekleyen kayıt var. Muhasebe sorunu giderildikten sonra aynı işlemi tamamlayın.
      <Button type="button" variant="outline" disabled={busy || uncertain} onClick={() => setForm({ ...pending,
        bank_account_id: pending.bank_account_id || '', original_payment_id: pending.original_payment_id || '', exchange_rate: pending.exchange_rate ?? '' })}>Bekleyen işlemi aç</Button>
    </div>}
    <div className="space-y-2">{data.payments.map(p => <article key={p.id} className="rounded-lg border p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>{p.payment_type === 'refund' ? 'İade' : 'Tahsilat'} · {formatCurrency(p.amount, data.currency)} · {methods[p.method]}</span>
        {p.payment_type !== 'refund' && <Button type="button" size="sm" variant="outline" disabled={busy || locked} onClick={() => startRefund(p)}>İade kaydet</Button>}
      </div>
      <details className="mt-2 text-xs"><summary className="cursor-pointer">Makbuz ayrıntıları</summary>
        <dl className="mt-2 grid gap-2 break-words sm:grid-cols-2">
          {[['Kayıt no', p.receipt_number], ['İş günü', p.business_date], ['Referans', p.reference], ['Kaydeden', p.processed_by],
            ['Açıklama', p.notes], ['Muhasebe kaydı', p.gl_journal_entry_id]].map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd>{value}</dd></div>)}
        </dl><p className="mt-2">Manuel tahsilat/iade kaydıdır; mali fatura veya banka işlem dekontu değildir.</p>
      </details>
    </article>)}</div>
    <form onSubmit={submit} className="space-y-3">
      <h4 className="text-sm font-medium">{form.kind === 'refund' ? 'Seçilen tahsilata iade' : 'Yeni tahsilat'}</h4>
      <fieldset disabled={busy || locked} className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Tutar ({data.currency})<Input required type="number" min="0.01" step="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></label>
        <label className="text-sm">Ödeme yöntemi<select className="w-full rounded border p-2" disabled={form.kind === 'refund'} value={form.method} onChange={e => setForm({ ...form, method: e.target.value, bank_account_id: '' })}>{Object.entries(methods).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
        {form.method !== 'cash' && <label className="text-sm">Banka / kart hesabı<select required disabled={form.kind === 'refund'} className="w-full rounded border p-2" value={form.bank_account_id} onChange={e => setForm({ ...form, bank_account_id: e.target.value })}><option value="">Hesap seçin</option>{data.bank_accounts.map(a => <option key={a.id} value={a.id}>{a.name} · {a.currency}</option>)}</select></label>}
        {data.currency !== 'TRY' && <label className="text-sm">TRY muhasebe kuru<Input required disabled={form.kind === 'refund'} type="number" min="0.000001" step="any" value={form.exchange_rate} onChange={e => setForm({ ...form, exchange_rate: e.target.value })} /></label>}
        <label className="text-sm">Makbuz / banka referansı<Input required minLength={3} maxLength={200} value={form.reference} onChange={e => setForm({ ...form, reference: e.target.value })} /></label>
        <label className="text-sm">Açıklama / iade gerekçesi<Input required minLength={10} maxLength={1000} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></label>
        <Button type="button" variant="ghost" onClick={() => setForm(blank())}>Formu temizle</Button>
      </fieldset>
      <Button type="submit" disabled={busy || uncertain || (pending && form.request_id !== pending.request_id)}>{busy ? 'Kaydediliyor…' : pending ? 'Aynı işlemi tamamla' : 'Hareketi kaydet'}</Button>
    </form>
  </section>;
}
