import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/currency';
import { parseFinancialDecimal, toMinorUnits } from '@/lib/financialInput';
import SecurityFundsPanel from './SecurityFundsPanel';

const labels = { requested: 'Eski bekleyen işlem', applied: 'Uygulandı — tahsilat değil', rejected: 'İptal edildi' };
const errorText = error => typeof error?.response?.data?.detail === 'string'
  ? error.response.data.detail : 'İşlem sonucu doğrulanamadı. Aynı taleple yeniden deneyin.';

export default function EnterpriseBillingPanel({ bookingId, folios, charges, currency = 'TRY', readOnly, onChanged, onLockChange }) {
  const [data, setData] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [items, setItems] = useState([]);
  const [folioId, setFolioId] = useState('');
  const [selected, setSelected] = useState([]);
  const [kind, setKind] = useState('selected_services_comp');
  const [mode, setMode] = useState('full');
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [pendingReasons, setPendingReasons] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const [pendingRetry, setPendingRetry] = useState(null);
  const [showFunds, setShowFunds] = useState(false);
  const [fundsLocked, setFundsLocked] = useState(false);
  const attempt = useRef(null);
  const active = useRef(true);
  const inFlight = useRef(false);
  useEffect(() => { onLockChange?.(busy || uncertain || Boolean(pendingRetry) || fundsLocked); }, [busy, uncertain, pendingRetry, fundsLocked, onLockChange]);
  const refresh = async () => {
    const [catalog, settings, requests] = await Promise.all([
      axios.get('/enterprise-billing/catalog'), axios.get('/enterprise-billing/policy'),
      axios.get('/enterprise-billing/concessions', { params: { booking_id: bookingId } }),
    ]);
    if (!active.current) return;
    if (!Array.isArray(requests.data?.items) || !Array.isArray(catalog.data?.non_collection_operations)) throw new Error('Geçersiz veri');
    setData(catalog.data); setPolicy(settings.data); setItems(requests.data.items);
  };
  useEffect(() => {
    active.current = true;
    refresh().catch(() => { if (active.current) setError('Kurumsal ödeme kontrolleri yüklenemedi; yeniden açın.'); });
    return () => { active.current = false; };
    // Parent remounts this panel for each reservation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);
  const remainingMinor = row => {
    let remaining = Math.round(Number(row.total ?? row.amount) * 100);
    for (const item of items.filter(item => item.status === 'applied' && item.charge_ids?.includes(row.id))) {
      if (!Number.isSafeInteger(item.allocated_charge_minor?.[row.id])) return 0;
      remaining -= item.allocated_charge_minor[row.id];
    }
    return Math.max(0, remaining);
  };
  const eligible = charges.filter(row => row.folio_id === folioId && !row.voided && !row.invoice_id &&
    row.id && Number(row.total ?? row.amount) > 0 && row.charge_category !== 'split_adjustment' &&
    row.charge_category !== 'opening_balance' && remainingMinor(row) > 0 && (kind !== 'room_comp' || row.charge_category === 'room'));
  const totalMinor = eligible.filter(row => selected.includes(row.id)).reduce((sum, row) => sum + remainingMinor(row), 0);
  const parsed = parseFinancialDecimal(value);
  const amountMinor = mode === 'full' ? totalMinor : mode === 'percentage' ? Math.round(totalMinor * (parsed || 0) / 100) : toMinorUnits(value);
  const valid = selected.length > 0 && selected.every(id => eligible.some(row => row.id === id)) && reason.trim().length >= 3 &&
    amountMinor > 0 && amountMinor <= totalMinor && (mode !== 'percentage' || (parsed > 0 && parsed <= 100));
  const money = (minor, code = currency) => formatCurrency(minor / 100, code);
  const operate = async action => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); setNotice('');
    try { await action(); }
    catch (e) { if (active.current) setError(errorText(e)); }
    finally { inFlight.current = false; if (active.current) setBusy(false); }
  };
  const submit = event => {
    event.preventDefault();
    if ((!valid && !uncertain) || readOnly || !policy?.can_apply || pendingRetry) return;
    operate(async () => {
      const payload = { booking_id: bookingId, folio_id: folioId, charge_ids: [...selected].sort(), kind, mode, reason: reason.trim(),
        ...(mode === 'percentage' ? { percentage: parsed } : mode === 'amount' ? { amount_minor: amountMinor } : {}) };
      const key = JSON.stringify(payload);
      if (!attempt.current || (!uncertain && attempt.current.key !== key)) attempt.current = { key, payload, request_id: crypto.randomUUID() };
      try {
        const response = await axios.post('/enterprise-billing/concessions', { ...attempt.current.payload, request_id: attempt.current.request_id });
        if (response.data?.id !== attempt.current.request_id || response.data.status !== 'applied') throw new Error('Geçersiz işlem yanıtı');
        setUncertain(false); setSelected([]); setReason(''); attempt.current = null;
        setNotice('İkram/indirim uygulandı; açıklama ve işlemi yapan kişi loga kaydedildi. Nakit veya kart tahsilatı yapılmadı.');
        try { await Promise.all([refresh(), onChanged?.()]); } catch { setError('İkram/indirim uygulandı; liste yenilenemedi. Yeni işlem oluşturmayın, paneli yeniden açın.'); }
      } catch (e) { setUncertain(!e.response || e.response.status >= 500); throw e; }
    });
  };
  const decide = (item, approve) => operate(async () => {
    const explanation = pendingRetry?.reason ?? (pendingReasons[item.id] ?? item.reason ?? '').trim();
    if (explanation.length < 3 || explanation.length > 500) throw new Error('Açıklama zorunlu');
    try {
      const { data: result } = await axios.post(`/enterprise-billing/concessions/${item.id}/${approve ? 'apply' : 'decision'}`,
        approve ? { reason: explanation } : { approve: false, reason: explanation });
      if (result?.id !== item.id || result.status !== (approve ? 'applied' : 'rejected')) throw new Error('Geçersiz işlem yanıtı');
      setPendingRetry(null);
    } catch (e) {
      setPendingRetry(!e.response || e.response.status >= 500 ? { item, approve, reason: explanation } : null);
      throw e;
    }
    setNotice(approve ? 'İkram/indirim uygulandı; açıklama ve işlemi yapan kişi loga kaydedildi. Nakit veya kart tahsilatı yapılmadı.' : 'Bekleyen işlem gerekçesiyle iptal edildi.');
    try { await Promise.all([refresh(), onChanged?.()]); }
    catch { setError('Karar kaydedildi; güncel veriler alınamadı. Kararı değiştirmeyin, ekranı yenileyin.'); }
  });
  return <section className="space-y-4 rounded-xl border bg-card p-4 text-card-foreground" data-testid="enterprise-billing-panel">
    <h3 className="font-semibold">Kurumsal ödeme kontrolleri</h3>
    <p className="text-sm text-muted-foreground">Tahsilat, cari aktarımı, ikram ve provizyon farklı işlemlerdir. Bu paneldeki ikram/indirim yalnız seçilen işlenmiş masrafları kapsar; gelecek geceleri veya paket haklarını değiştirmez.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="text-sm">{notice}</p>}
    {pendingRetry && <div className="space-y-2"><p className="text-sm text-destructive">Bekleyen işlemin sonucu belirsiz. Yeni işlem yapmayın; aynı kayıt ve açıklamayla sonucu doğrulayın.</p><Button type="button" disabled={busy} onClick={() => decide(pendingRetry.item, pendingRetry.approve)}>Bekleyen işlemin sonucunu doğrula</Button></div>}
    {!data ? <p>Kontroller yükleniyor…</p> : <div className="rounded border p-3 text-sm">
      <p>Ödeme sağlayıcısı: {data.provider || 'Yapılandırılmamış'} · {data.provider_readiness === 'configured_not_live_verified' ? 'Yapılandırılmış; canlı kabul doğrulaması gerekli' : 'Entegre kart tahsilatı hazır değil'}</p>
      <p>Harici tahsilat kaydı: nakit, POS/kart, doğrulanmış banka transferi. Hediye kartı, cüzdan, sadakat ve barter bu panelde etkin değildir.</p>
    </div>}
    {!readOnly && data && !policy?.can_apply && <p className="text-sm text-muted-foreground">İkram/indirim için masraf işleme ve fiyat değiştirme yetkileri gerekir.</p>}
    {!readOnly && data && policy?.can_apply && <form onSubmit={submit} className="space-y-3">
      <h4 className="font-medium">Gerekçeli ikram / indirim</h4>
      <fieldset disabled={busy || uncertain || Boolean(pendingRetry)} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Hedef folyo<select aria-label="İkram hedef folyo" className="mt-1 block w-full rounded border bg-background p-2" value={folioId} onChange={e => { setFolioId(e.target.value); setSelected([]); }}><option value="">Seçin</option>{folios.filter(row => row.status === 'open' && !row.invoice_id).map(row => <option key={row.id} value={row.id}>{row.folio_number || row.id}</option>)}</select></label>
          <label className="text-sm">İşlem türü<select aria-label="İkram türü" className="mt-1 block w-full rounded border bg-background p-2" value={kind} onChange={e => { setKind(e.target.value); setSelected([]); }}><option value="selected_services_comp">Seçili hizmet ikramı</option><option value="room_comp">Yalnız oda ikramı</option><option value="service_recovery">Memnuniyet telafisi</option><option value="discount">Ticari indirim</option></select></label>
        </div>
        <div className="max-h-48 space-y-2 overflow-auto">{eligible.map(row => <label key={row.id} className="flex gap-2 text-sm"><input type="checkbox" checked={selected.includes(row.id)} onChange={e => setSelected(previous => e.target.checked ? [...previous, row.id] : previous.filter(id => id !== row.id))} />{row.description || row.id}<span className="ml-auto">{money(remainingMinor(row), row.currency || currency)}</span></label>)}</div>
        <p className="text-xs text-muted-foreground">Listelenen tutarlar önceki uygulanan ikramlar sonrası kalan hizmet değeridir. Açık borç ve fatura durumu sunucuda yeniden kontrol edilir.</p>
        <label className="block text-sm">Kapsam<select aria-label="İkram kapsamı" className="ml-2 rounded border bg-background p-2" value={mode} onChange={e => setMode(e.target.value)}><option value="full">Seçilenlerin tamamı</option><option value="percentage">Yüzde</option><option value="amount">Belirli tutar</option></select></label>
        {mode !== 'full' && <label className="block text-sm">{mode === 'percentage' ? 'Yüzde' : `Tutar (${currency})`}<input aria-label="İkram değeri" inputMode="decimal" className="ml-2 rounded border bg-background p-2" value={value} onChange={e => setValue(e.target.value)} /></label>}
        <label className="block text-sm">Açıklama (zorunlu)<input aria-label="İkram gerekçesi" className="mt-1 block w-full rounded border bg-background p-2" required minLength={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /></label>
        <p className="text-sm">Uygulanacak tutar: {money(amountMinor || 0)}. Ayrı onay beklemeden uygulanır; açıklama, kullanıcı ve hizmetler loga kaydedilir. Tahsilat oluşturmaz. Faturalı kalemler ayrı belge düzeltmesi gerektirir.</p>
      </fieldset>
      <Button type="submit" disabled={busy || Boolean(pendingRetry) || (!valid && !uncertain)}>{uncertain ? 'Aynı talebin sonucunu doğrula' : 'İkramı / indirimi uygula'}</Button>
      {uncertain && <p className="text-sm text-destructive">Sonuç belirsiz. Seçimler kilitlendi; yeniden denemede aynı işlem anahtarı kullanılacak.</p>}
    </form>}
    <div className="space-y-2">{items.map(item => <div key={item.id} className="rounded border p-3 text-sm">
      <p>{money(item.amount_minor, item.currency)} · {labels[item.status] || item.status}</p><p>Açıklama: {item.reason}</p>
      {item.decided_by && <p>İşlemi yapan: {item.performed_by_name || item.decided_by} · {item.business_date || item.decided_at}</p>}
      {item.service_details?.length > 0 && <p>Hizmetler: {item.service_details.map(row => row.description || row.category || row.id).join(', ')}</p>}
      {item.status === 'requested' && policy?.can_apply && !readOnly && <div className="mt-2 space-y-2">
        <label className="block">Uygulama / iptal açıklaması<input aria-label={`Bekleyen işlem açıklaması ${item.id}`} className="mt-1 block w-full rounded border bg-background p-2" disabled={busy || uncertain || Boolean(pendingRetry)} minLength={3} maxLength={500} value={pendingReasons[item.id] ?? item.reason ?? ''} onChange={e => setPendingReasons(previous => ({ ...previous, [item.id]: e.target.value }))} /></label>
        <div className="flex gap-2"><Button type="button" size="sm" disabled={busy || uncertain || Boolean(pendingRetry) || (pendingReasons[item.id] ?? item.reason ?? '').trim().length < 3} onClick={() => decide(item, true)}>Uygula</Button><Button type="button" size="sm" variant="outline" disabled={busy || uncertain || Boolean(pendingRetry) || (pendingReasons[item.id] ?? item.reason ?? '').trim().length < 3} onClick={() => decide(item, false)}>İptal et</Button></div>
      </div>}
    </div>)}</div>
    <Button type="button" variant="outline" disabled={fundsLocked || busy || uncertain || Boolean(pendingRetry)} onClick={() => setShowFunds(value => !value)}>İade edilebilir güvence kayıtları</Button>
    {showFunds && <SecurityFundsPanel key={bookingId} bookingId={bookingId} currency={currency} folios={folios} readOnly={readOnly} onChanged={onChanged} onLockChange={setFundsLocked} />}
  </section>;
}
