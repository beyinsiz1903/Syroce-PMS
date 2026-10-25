import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/currency';
import { toMinorUnits } from '@/lib/financialInput';

const funded = kind => ['gift_card_redemption', 'wallet'].includes(kind);
const blank = { kind: 'gift_card_redemption', amount: '', currency: 'TRY', account_code: '', funding_entry_id: '', point_value: '', reference: '', reason: '', expires_on: '', due_on: '' };
const inputClass = 'mt-1 block w-full rounded border bg-background p-2';
const Text = ({ label, ...props }) => <label className="block text-sm">{label}<input aria-label={label} className={inputClass} {...props} /></label>;
const failure = error => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'İşlem sonucu belirsiz. Aynı taleple sonucu doğrulayın.';

export default function SettlementInstrumentsPanel({ bookingId, folios, currency, readOnly, onChanged, onLockChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [issue, setIssue] = useState({ ...blank, currency });
  const [use, setUse] = useState({ instrument_id: '', folio_id: '', amount: '', rate: '', rate_reference: '', reference: '', reason: '', fx_gain_account: '', fx_loss_account: '' });
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(null);
  const [reverse, setReverse] = useState({ operation_id: '', reference: '', reason: '' });
  const alive = useRef(true);
  const flight = useRef(false);
  const load = async () => {
    const response = await axios.get('/enterprise-billing/instruments', { params: { booking_id: bookingId } });
    if (!Array.isArray(response.data?.items) || !Array.isArray(response.data?.operations)) throw new Error('Geçersiz veri');
    if (alive.current) setData(response.data);
  };
  useEffect(() => {
    alive.current = true;
    load().catch(() => { if (alive.current) setError('Mahsup kaynakları yüklenemedi. Yeniden deneyin.'); });
    return () => { alive.current = false; };
    // Parent remounts for a different reservation; never migrate an uncertain request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);
  useEffect(() => { onLockChange?.(busy || Boolean(pending)); }, [busy, pending, onLockChange]);
  const submit = async attempt => {
    if (flight.current || readOnly) return;
    flight.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const response = await axios.post(attempt.path, attempt.body);
      if (response.data?.id !== attempt.body.request_id) throw new Error('İşlem yanıtı doğrulanamadı');
      setPending(null);
      setNotice('İşlem kaydedildi; kaynak, folyo, muhasebe ve gerekçe aynı işlemde kaydedildi.');
      try { await Promise.all([load(), onChanged?.()]); }
      catch { setData(null); setError('İşlem kaydedildi; liste yenilenemedi. Yeni işlem yapmadan yeniden yükleyin.'); }
      setIssue({ ...blank, currency });
      setUse(previous => ({ ...previous, amount: '', reference: '', reason: '' }));
      setReverse({ operation_id: '', reference: '', reason: '' });
    } catch (e) {
      setPending(!e.response || e.response.status >= 500 ? attempt : null);
      setError(failure(e));
    } finally { flight.current = false; if (alive.current) setBusy(false); }
  };
  const start = (path, body) => submit({ path, body: { ...body, request_id: crypto.randomUUID() } });
  const selected = data?.items.find(item => item.id === use.instrument_id);
  const accounts = (types, selectedValue, onChange, label) => <label className="block text-sm">{label}<select aria-label={label} className={inputClass} value={selectedValue} onChange={e => onChange(e.target.value)} required><option value="">Seçin</option>{(data?.accounts || []).filter(row => types.includes(row.type)).map(row => <option key={row.code} value={row.code}>{row.code} · {row.name}</option>)}</select></label>;
  const makeIssue = event => {
    event.preventDefault();
    const amount = toMinorUnits(issue.amount);
    if (!Number.isSafeInteger(amount) || amount <= 0) { setError('Geçerli pozitif tutar girin.'); return; }
    const body = { booking_id: bookingId, kind: issue.kind, currency: issue.kind === 'cheque_pending_clearance' ? 'TRY' : issue.currency, amount_minor: amount, account_code: issue.account_code, reference: issue.reference.trim(), reason: issue.reason.trim(),
      ...(funded(issue.kind) ? { funding_entry_id: issue.funding_entry_id.trim() } : {}),
      ...(issue.kind === 'loyalty_redemption' ? { point_value_minor: toMinorUnits(issue.point_value) } : {}),
      ...(issue.expires_on ? { expires_on: issue.expires_on } : {}), ...(issue.kind === 'cheque_pending_clearance' ? { due_on: issue.due_on } : {}) };
    start('/enterprise-billing/instruments', body);
  };
  const makeApply = event => {
    event.preventDefault();
    const amount = toMinorUnits(use.amount);
    const rate = selected?.currency === 'TRY' ? '1' : use.rate.trim().replace(',', '.');
    if (!selected || !Number.isSafeInteger(amount) || amount <= 0 || amount > selected.remaining_minor || !/^(?:\d+)(?:\.\d{1,6})?$/.test(rate) || Number(rate) <= 0) { setError('Tutarı, kalan hakkı ve kuru kontrol edin.'); return; }
    start(`/enterprise-billing/instruments/${selected.id}/apply`, { booking_id: bookingId, folio_id: use.folio_id, amount_minor: amount,
      rate_to_try: rate, rate_reference: selected.currency === 'TRY' ? 'TRY sabit değer 1' : use.rate_reference.trim(),
      reference: use.reference.trim(), reason: use.reason.trim(),
      ...(use.fx_gain_account ? { fx_gain_account: use.fx_gain_account } : {}), ...(use.fx_loss_account ? { fx_loss_account: use.fx_loss_account } : {}) });
  };
  const reversed = new Set(data?.operations.filter(op => op.action === 'reverse').map(op => op.original_operation_id));
  return <section className="space-y-4 rounded border p-3" data-testid="settlement-instruments">
    <h4 className="font-medium">Kaynaklı kurumsal mahsuplar</h4>
    <p className="text-sm text-muted-foreground">Hediye kartı/cüzdan önceki mühürlü yükümlülük fişinden ayrılır; burada para yaratılmaz. Sadakat mevcut PMS üye puanından düşer (POS puan defteri ayrıdır). Barter ve alacaktan silme tahsilat değildir. Çek, bankada tahsil edilmeden borcu kapatmaz. Faturalı/kapalı hesaplar önce kendi düzeltme akışını gerektirir.</p>
    {error && <p role="alert" className="text-destructive">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!pending && <Button type="button" variant="outline" disabled={busy} onClick={() => load().catch(() => setError('Kaynaklar yüklenemedi.'))}>Mahsupları yenile</Button>}
    {pending && <Button type="button" disabled={busy} onClick={() => submit(pending)}>Aynı mahsup talebinin sonucunu doğrula</Button>}
    {pending && <p className="text-sm text-destructive">Sonuç belirsiz; form kilitli. Aynı anahtarla tekrar doğrulayın, yeni talep oluşturmayın.</p>}
    {data && !data.reconciliation?.healthy && <p role="alert" className="text-destructive">Kaynak–muhasebe mutabakatı doğrulanamadı; yeni işlem yapmadan inceleyin.</p>}
    {data && <div className="space-y-2">{data.items.length === 0 ? <p className="text-sm">Henüz tanımlı mahsup kaynağı yok.</p> : data.items.map(item => <div key={item.id} className="rounded border p-2 text-sm"><p>{data.kinds[item.kind]} · {item.reference} · {item.status}</p><p>Kalan: {formatCurrency(item.remaining_minor / 100, item.currency)}{item.expires_on ? ` · Son kullanım: ${item.expires_on}` : ''}</p><p>{item.reason}</p></div>)}</div>}
    {!readOnly && data?.can_issue && <form onSubmit={makeIssue} className="space-y-3"><h5 className="font-medium">Belgeye bağlı kaynak / limit tanımla</h5><fieldset disabled={busy || Boolean(pending)} className="grid gap-3 sm:grid-cols-2">
      <label className="block text-sm">Kaynak türü<select aria-label="Kaynak türü" className={inputClass} value={issue.kind} onChange={e => setIssue(previous => ({ ...blank, currency, kind: e.target.value }))}>{Object.entries(data.kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="block text-sm">Kaynak para birimi<select aria-label="Kaynak para birimi" className={inputClass} value={issue.kind === 'cheque_pending_clearance' ? 'TRY' : issue.currency} onChange={e => setIssue(previous => ({ ...previous, currency: e.target.value }))}>{(issue.kind === 'cheque_pending_clearance' ? ['TRY'] : ['TRY', 'USD', 'EUR', 'GBP', 'CHF']).map(code => <option key={code}>{code}</option>)}</select></label>
      <Text label="Kaynak tutarı / limit" inputMode="decimal" required value={issue.amount} onChange={e => setIssue(previous => ({ ...previous, amount: e.target.value }))} />
      {accounts(funded(issue.kind) ? ['liability'] : ['loyalty_redemption', 'write_off'].includes(issue.kind) ? ['expense'] : ['asset'], issue.account_code, account_code => setIssue(previous => ({ ...previous, account_code })), 'Kaynak muhasebe hesabı')}
      {funded(issue.kind) && <Text label="Mühürlü fonlama fişi kimliği" required value={issue.funding_entry_id} onChange={e => setIssue(previous => ({ ...previous, funding_entry_id: e.target.value }))} />}
      {issue.kind === 'loyalty_redemption' && <Text label="Bir puanın parasal değeri" inputMode="decimal" required value={issue.point_value} onChange={e => setIssue(previous => ({ ...previous, point_value: e.target.value }))} />}
      {issue.kind === 'cheque_pending_clearance' && <Text label="Çek vadesi" type="date" required value={issue.due_on} onChange={e => setIssue(previous => ({ ...previous, due_on: e.target.value, currency: 'TRY' }))} />}
      <Text label="Hakkın son kullanım günü (isteğe bağlı)" type="date" value={issue.expires_on} onChange={e => setIssue(previous => ({ ...previous, expires_on: e.target.value }))} />
      <Text label="Kaynak belge referansı" required minLength={3} maxLength={160} value={issue.reference} onChange={e => setIssue(previous => ({ ...previous, reference: e.target.value }))} />
      <Text label="Kaynak gerekçesi" required minLength={3} maxLength={500} value={issue.reason} onChange={e => setIssue(previous => ({ ...previous, reason: e.target.value }))} />
      <Button type="submit">Kaynağı / limiti kaydet</Button>
    </fieldset><p className="text-xs text-muted-foreground">Fonlama önce Muhasebe'de doğru yükümlülük hesabına işlenmiş olmalı; fiş kimliğini detayından alın. Fonlama satış değildir. Puan dönüştürme değeri ve belge limitleri açık seçiminizdir; varsayılan kur veya yetkisiz puan üretilmez.</p></form>}
    {!readOnly && data?.can_apply && <form onSubmit={makeApply} className="space-y-3"><h5 className="font-medium">Folyoya uygula / harici çek tahsilini kaydet</h5><fieldset disabled={busy || Boolean(pending) || !data.reconciliation?.healthy} className="grid gap-3 sm:grid-cols-2">
      <label className="block text-sm">Kullanılacak kaynak<select aria-label="Kullanılacak kaynak" className={inputClass} required value={use.instrument_id} onChange={e => setUse(previous => ({ ...previous, instrument_id: e.target.value, amount: '', rate: '', reference: '', reason: '' }))}><option value="">Seçin</option>{data.items.filter(row => ['active', 'pending'].includes(row.status) && row.remaining_minor > 0).map(row => <option key={row.id} value={row.id}>{data.kinds[row.kind]} · {row.reference} · {formatCurrency(row.remaining_minor / 100, row.currency)}</option>)}</select></label>
      <label className="block text-sm">Mahsup hedef folyo<select aria-label="Mahsup hedef folyo" className={inputClass} required value={use.folio_id} onChange={e => setUse(previous => ({ ...previous, folio_id: e.target.value }))}><option value="">Seçin</option>{folios.filter(row => row.status === 'open' && !row.invoice_id).map(row => <option key={row.id} value={row.id}>{row.folio_number || row.id} · {row.currency || currency}</option>)}</select></label>
      <Text label="Mahsup tutarı" inputMode="decimal" required value={use.amount} onChange={e => setUse(previous => ({ ...previous, amount: e.target.value }))} />
      {selected && selected.currency !== 'TRY' && <><Text label="Kaynak gününün TRY kuru" required value={use.rate} onChange={e => setUse(previous => ({ ...previous, rate: e.target.value }))} /><Text label="Kur dayanağı" required minLength={3} value={use.rate_reference} onChange={e => setUse(previous => ({ ...previous, rate_reference: e.target.value }))} />
        {funded(selected.kind) && <><Text label="Kur kazanç hesabı (fark varsa)" value={use.fx_gain_account} onChange={e => setUse(previous => ({ ...previous, fx_gain_account: e.target.value }))} /><Text label="Kur zarar hesabı (fark varsa)" value={use.fx_loss_account} onChange={e => setUse(previous => ({ ...previous, fx_loss_account: e.target.value }))} /></>}</>}
      <Text label={selected?.kind === 'cheque_pending_clearance' ? 'Harici banka tahsil dekontu' : 'Mahsup belge referansı'} required minLength={3} maxLength={160} value={use.reference} onChange={e => setUse(previous => ({ ...previous, reference: e.target.value }))} />
      <Text label="Mahsup gerekçesi" required minLength={3} maxLength={500} value={use.reason} onChange={e => setUse(previous => ({ ...previous, reason: e.target.value }))} />
      <Button type="submit">{selected?.kind === 'cheque_pending_clearance' ? 'Bankada tahsil edilen çeki kaydet' : 'Kaynaklı mahsubu uygula'}</Button>
    </fieldset></form>}
    {data && <div className="space-y-1 text-sm"><h5 className="font-medium">Kaynak ve işlem geçmişi</h5>{data.operations.map(op => <p key={op.id}>{data.kinds[op.kind]} · {op.action} · {op.reference} · {op.business_date} · {op.reason}</p>)}</div>}
    {!readOnly && data?.can_reverse && <form className="space-y-2" onSubmit={event => { event.preventDefault(); start(`/enterprise-billing/instrument-operations/${reverse.operation_id}/reverse`, { booking_id: bookingId, reference: reverse.reference.trim(), reason: reverse.reason.trim() }); }}><h5 className="font-medium">Özgün işleme bağlı tam ters kayıt</h5><fieldset disabled={busy || Boolean(pending)} className="space-y-2">
      <select aria-label="Ters kaydedilecek mahsup" className={inputClass} required value={reverse.operation_id} onChange={e => setReverse(previous => ({ ...previous, operation_id: e.target.value }))}><option value="">İşlem seçin</option>{data.operations.filter(op => op.action === 'apply' && !reversed.has(op.id)).map(op => <option key={op.id} value={op.id}>{data.kinds[op.kind]} · {op.reference}</option>)}</select>
      <Text label="Ters kayıt belge referansı" required minLength={3} maxLength={160} value={reverse.reference} onChange={e => setReverse(previous => ({ ...previous, reference: e.target.value }))} />
      <Text label="Ters kayıt gerekçesi" required minLength={3} maxLength={500} value={reverse.reason} onChange={e => setReverse(previous => ({ ...previous, reason: e.target.value }))} />
      <p className="text-xs text-muted-foreground">Tam ters kayıt hakkı/puanı iade eder; eski ödeme ve fişi değiştirmez. Çek için yalnız harici bankanın gerçekleşmiş iade belgesini kullanın; burada bankaya talimat verilmez.</p><Button type="submit" variant="outline">Bağlı ters kaydı oluştur</Button>
    </fieldset></form>}
  </section>;
}
