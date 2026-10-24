import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/currency';
import { toMinorUnits } from '@/lib/financialInput';

export default function SecurityFundsPanel({ bookingId, currency, folios, readOnly, onChanged, onLockChange }) {
  const [funds, setFunds] = useState([]);
  const [ready, setReady] = useState(false);
  const [action, setAction] = useState('receive');
  const [fundId, setFundId] = useState('');
  const [folioId, setFolioId] = useState('');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('bank_transfer');
  const [reference, setReference] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const active = useRef(true);
  const inFlight = useRef(false);
  const attempt = useRef(null);
  useEffect(() => { onLockChange?.(busy || uncertain); }, [busy, uncertain, onLockChange]);
  const refresh = async () => {
    const { data } = await axios.get('/enterprise-billing/security-funds', { params: { booking_id: bookingId } });
    if (!Array.isArray(data?.items)) throw new Error('Geçersiz güvence verisi');
    if (active.current) { setFunds(data.items); setReady(true); }
  };
  useEffect(() => {
    active.current = true;
    refresh().catch(() => { if (active.current) setError('Güvence kayıtları yüklenemedi; paneli yeniden açın.'); });
    return () => { active.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);
  const fund = funds.find(row => row.id === fundId);
  const amountMinor = toMinorUnits(amount);
  const valid = ready && amountMinor > 0 && reference.trim().length >= 3 && reason.trim().length >= 3 &&
    (action === 'receive' || (fund && amountMinor <= fund.remaining_minor)) &&
    (action !== 'apply' || folios.some(row => row.id === folioId && row.status === 'open'));
  const submit = async event => {
    event.preventDefault();
    if (inFlight.current || readOnly || (!valid && !uncertain)) return;
    inFlight.current = true; setBusy(true); setError(''); setNotice('');
    const payload = { amount_minor: amountMinor, reference: reference.trim(), reason: reason.trim(),
      ...(action === 'receive' ? { booking_id: bookingId, currency, method } : { action, ...(action === 'apply' ? { folio_id: folioId } : {}) }) };
    const url = action === 'receive' ? '/enterprise-billing/security-funds' : `/enterprise-billing/security-funds/${fundId}/movements`;
    const key = JSON.stringify([url, payload]);
    if (!attempt.current || (!uncertain && attempt.current.key !== key)) attempt.current = { key, url, payload: { ...payload, request_id: crypto.randomUUID() } };
    try {
      const { data } = await axios.post(attempt.current.url, attempt.current.payload);
      if (!data?.id || !Number.isInteger(data.remaining_minor)) throw new Error('İşlem sonucu doğrulanamadı');
      setUncertain(false); setAmount(''); setReference(''); setReason(''); attempt.current = null;
      setNotice(action === 'apply' ? 'Güvence folyoya mahsup edildi. Yeni tahsilat yapılmadı.' : 'Harici güvence hareketi kaydedildi. Banka/kart işlemi başlatılmadı.');
      try { await Promise.all([refresh(), onChanged?.()]); }
      catch { setError('İşlem kaydedildi; veriler yenilenemedi. İşlemi tekrar oluşturmayın.'); }
    } catch (e) {
      setUncertain(!e.response || e.response.status >= 500);
      setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Sonuç belirsiz. Aynı işlemle yeniden doğrulayın.');
    } finally { inFlight.current = false; if (active.current) setBusy(false); }
  };
  return <section className="space-y-3 rounded border p-3" data-testid="security-funds-panel">
    <h4 className="font-medium">İade edilebilir güvence — konaklama avansı değil</h4>
    <p className="text-sm text-muted-foreground">Gerçekte alınmış/iade edilmiş parayı dekont veya fişiyle kaydedin. Bu ekran kart çekimi, banka transferi veya provizyon yapmaz. Alınan güvence oda borcunu kapatmaz; mahsup ayrı işlemdir. Nakit için açık TRY kasa vardiyası zorunludur.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="text-sm">{notice}</p>}
    {funds.map(row => <div key={row.id} className="rounded border p-2 text-sm">Kalan güvence: {formatCurrency(row.remaining_minor / 100, row.currency)} · Alınan: {formatCurrency(row.received_minor / 100, row.currency)} · İade: {formatCurrency(row.refunded_minor / 100, row.currency)} · Mahsup: {formatCurrency(row.applied_minor / 100, row.currency)} · {row.reference}</div>)}
    {!readOnly && <form className="space-y-3" onSubmit={submit}><fieldset className="grid gap-3 sm:grid-cols-2" disabled={busy || uncertain || !ready}>
      <label className="text-sm">İşlem<select aria-label="Güvence işlemi" className="mt-1 block w-full rounded border bg-background p-2" value={action} onChange={e => setAction(e.target.value)}><option value="receive">Dışarıda alınan güvenceyi kaydet</option><option value="apply">Güvenceyi folyoya mahsup et</option><option value="refund">Dışarıda yapılan güvence iadesini kaydet</option></select></label>
      {action === 'receive' ? <label className="text-sm">Yöntem<select aria-label="Güvence yöntemi" className="mt-1 block w-full rounded border bg-background p-2" value={method} onChange={e => setMethod(e.target.value)}><option value="bank_transfer">Doğrulanmış banka transferi</option><option value="cash">Nakit</option><option value="card">Harici POS / kart</option></select></label>
        : <label className="text-sm">Güvence kaydı<select aria-label="Güvence kaydı" className="mt-1 block w-full rounded border bg-background p-2" value={fundId} onChange={e => setFundId(e.target.value)}><option value="">Seçin</option>{funds.filter(row => row.remaining_minor > 0).map(row => <option key={row.id} value={row.id}>{row.reference} · {formatCurrency(row.remaining_minor / 100, row.currency)}</option>)}</select></label>}
      {action === 'apply' && <label className="text-sm">Hedef folyo<select aria-label="Güvence hedef folyo" className="mt-1 block w-full rounded border bg-background p-2" value={folioId} onChange={e => setFolioId(e.target.value)}><option value="">Seçin</option>{folios.filter(row => row.status === 'open').map(row => <option key={row.id} value={row.id}>{row.folio_number || row.id}</option>)}</select></label>}
      <label className="text-sm">Tutar ({currency})<input aria-label="Güvence tutarı" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} className="mt-1 block w-full rounded border bg-background p-2" /></label>
      <label className="text-sm">Fiş / dekont / işlem referansı<input aria-label="Güvence referansı" maxLength={200} value={reference} onChange={e => setReference(e.target.value)} className="mt-1 block w-full rounded border bg-background p-2" /></label>
      <label className="text-sm">Gerekçe<input aria-label="Güvence gerekçesi" maxLength={500} value={reason} onChange={e => setReason(e.target.value)} className="mt-1 block w-full rounded border bg-background p-2" /></label>
    </fieldset><Button type="submit" disabled={busy || (!valid && !uncertain)}>{uncertain ? 'Aynı güvence işlemini doğrula' : 'Güvence işlemini kaydet'}</Button></form>}
  </section>;
}
