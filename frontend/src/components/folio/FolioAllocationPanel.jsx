import { useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/currency';
import { parseMoneyInput } from '@/lib/moneyInput';

const code = value => String(value || 'TRY').trim().toUpperCase().replace(/^TL$/, 'TRY');
const label = folio => `${folio.folio_number || folio.id} · ${folio.cari_account_name || ({ guest: 'Misafir', company: 'Şirket', agency: 'Acente', master: 'Master' }[folio.payor_type || folio.folio_type] || 'Folyo')}`;

export default function FolioAllocationPanel({ bookingId, currency, folios, charges, onChanged, onClose }) {
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [mode, setMode] = useState('items');
  const [selected, setSelected] = useState([]);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [uncertain, setUncertain] = useState(false);
  const inFlight = useRef(false);
  const attempt = useRef(null);
  const open = folios.filter(folio => folio.status === 'open' && !folio.invoice_id);
  const source = open.find(folio => folio.id === sourceId);
  const target = open.find(folio => folio.id === targetId);
  const sourceCurrency = code(source?.currency || currency);
  const targets = open.filter(folio => folio.id !== sourceId && code(folio.currency || currency) === sourceCurrency);
  const items = charges.filter(row => row.folio_id === sourceId && !row.voided && !row.invoice_id &&
    row.charge_category !== 'split_adjustment' && Number(row.total ?? row.amount) > 0 && code(row.currency || sourceCurrency) === sourceCurrency);
  const itemTotal = items.filter(row => selected.includes(row.id)).reduce((sum, row) => sum + Math.round(Number(row.total ?? row.amount) * 100), 0) / 100;
  const total = mode === 'items' ? itemTotal : parseMoneyInput(amount);
  const valid = source && target && target.id !== source.id && code(target.currency || currency) === sourceCurrency &&
    Number.isFinite(total) && total > 0 && total <= Number(source.balance) && reason.trim().length >= 3 && reason.trim().length <= 500 &&
    (mode !== 'items' || (selected.length > 0 && selected.every(id => items.some(item => item.id === id))));
  const money = value => formatCurrency(value, sourceCurrency);
  const submit = async event => {
    event.preventDefault();
    if ((!valid && !uncertain) || inFlight.current || result) return;
    inFlight.current = true; setBusy(true); setError('');
    const payload = uncertain ? attempt.current.payload : { booking_id: bookingId, source_folio_id: sourceId, target_folio_id: targetId, mode,
      ...(mode === 'items' ? { charge_ids: [...selected].sort(), expected_amount: total } : { amount: total }), reason: reason.trim() };
    const fingerprint = JSON.stringify(payload);
    if (attempt.current?.fingerprint !== fingerprint) attempt.current = { fingerprint, payload, id: crypto.randomUUID() };
    try {
      const { data } = await axios.post('/folio-windows/allocate', { ...payload, request_id: attempt.current.id });
      if (data?.success !== true || data.allocation_id !== attempt.current.id || data.source_folio_id !== payload.source_folio_id ||
          data.target_folio_id !== payload.target_folio_id || !Number.isFinite(data.transferred_amount) || data.transferred_amount <= 0) {
        throw new Error('Paylaştırma yanıtı seçilen işlemle eşleşmiyor');
      }
      setResult(data);
      setUncertain(false);
      try { await onChanged?.(payload.target_folio_id); }
      catch { setError('Paylaştırma kaydedildi; güncel bakiyeler alınamadı. Ekranı yenileyin. İşlemi tekrar göndermeyin.'); }
    } catch (e) {
      const detail = e.response?.data?.detail;
      setUncertain(!e.response || e.response.status >= 500);
      setError(typeof detail === 'string' ? detail : 'Paylaştırma sonucu doğrulanamadı. Aynı seçimle tekrar denemek aynı işlem anahtarını kullanır.');
    } finally { inFlight.current = false; setBusy(false); }
  };
  return <form onSubmit={submit} className="space-y-4 rounded-xl border bg-card p-4 text-card-foreground" data-testid="folio-allocation-panel">
    <h3 className="font-semibold">Mevcut folyolar arasında paylaştır</h3>
    <p className="text-sm text-muted-foreground">Önce misafir ve şirket/acente hesaplarını açıp ödeyeni bağlayın. Bu işlem yalnız açık tahakkuk borcunu taşır; tahsilat, cari aktarımı, indirim veya comp değildir. Sonraki gece ücretleri otomatik yönlendirilmez.</p>
    {open.length < 2 && <p role="status">Paylaştırma için en az iki açık, faturasız folyo gerekir.</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {result ? <div role="status" className="rounded border p-3">
      <p>Paylaştırma kaydedildi: {money(result.transferred_amount)}.</p>
      <p>Kaynak bakiye: {money(result.source_balance)} · Hedef bakiye: {money(result.target_balance)}</p>
      <p className="text-sm">Şirket/acente payını seçili cari hesaba, misafir payını kart/nakit ödeme ile ayrı ayrı kapatabilirsiniz.</p>
    </div> : <fieldset disabled={busy || uncertain} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Kaynak hesap<select aria-label="Paylaştırma kaynak folyo" value={sourceId} onChange={e => { setSourceId(e.target.value); setTargetId(''); setSelected([]); }} className="mt-1 block w-full rounded border bg-background p-2"><option value="">Seçin</option>{open.map(folio => <option key={folio.id} value={folio.id}>{label(folio)}</option>)}</select></label>
        <label className="text-sm">Hedef hesap<select aria-label="Paylaştırma hedef folyo" value={targetId} onChange={e => setTargetId(e.target.value)} className="mt-1 block w-full rounded border bg-background p-2"><option value="">Seçin</option>{targets.map(folio => <option key={folio.id} value={folio.id}>{label(folio)}</option>)}</select></label>
      </div>
      <label className="block text-sm">Paylaştırma yöntemi<select aria-label="Paylaştırma yöntemi" value={mode} onChange={e => setMode(e.target.value)} className="ml-2 rounded border bg-background p-2"><option value="items">Kalem seç (vergisiyle birlikte)</option><option value="amount">Belirli tutar (bakiye payı)</option></select></label>
      {mode === 'items' ? <div className="max-h-64 space-y-2 overflow-y-auto">{items.map(row => <label key={row.id} className="flex items-center gap-2 rounded border p-2 text-sm">
        <input type="checkbox" checked={selected.includes(row.id)} onChange={e => setSelected(previous => e.target.checked ? [...previous, row.id] : previous.filter(id => id !== row.id))} />
        <span>{row.description || row.charge_name || row.id}</span><span className="ml-auto whitespace-nowrap">{money(row.total ?? row.amount)}</span>
      </label>)}{source && items.length === 0 && <p className="text-sm">Aktarılabilir asıl masraf yok. Henüz folyoya işlenmemiş ek ücretler bu listede bulunmaz.</p>}</div>
        : <label className="block text-sm">Aktarılacak tutar ({sourceCurrency})<input aria-label="Paylaştırma tutarı" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} className="ml-2 rounded border bg-background p-2" /></label>}
      <label className="block text-sm">İşlem açıklaması<input aria-label="Paylaştırma açıklaması" maxLength={500} value={reason} onChange={e => setReason(e.target.value)} className="mt-1 block w-full rounded border bg-background p-2" placeholder="Örn. konaklama şirkete, kişisel harcamalar misafire" /></label>
      {source && target && Number.isFinite(total) && <div className="rounded border p-3 text-sm" data-testid="allocation-preview">
        <p>Aktarılacak: {money(total)}</p><p>{label(source)}: {money(source.balance)} → {money(Number(source.balance) - total)}</p>
        <p>{label(target)}: {money(target.balance)} → {money(Number(target.balance) + total)}</p><p>Toplam borç değişmez. Ödemeler taşınmaz.</p>
      </div>}
    </fieldset>}
    {!result && <Button type="submit" disabled={(!valid && !uncertain) || busy}>{busy ? 'Paylaştırılıyor…' : uncertain ? 'Aynı İşlemi Doğrula / Tekrar Dene' : 'Paylaştırmayı Onayla'}</Button>}
    {uncertain && <p role="status" className="text-sm">Sonuç belirsizken seçimi değiştirmeyin veya yeni işlem başlatmayın. Aynı işlem anahtarıyla sonucu doğrulayın.</p>}
    <Button type="button" variant="outline" onClick={onClose} disabled={busy || uncertain}>Kapat</Button>
  </form>;
}
