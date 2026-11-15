import { useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { formatCurrency } from '@/lib/currency';
import apiErrorText from '@/utils/apiErrorText';

// Reverse the authoritative POS source, never manufacture a folio payment or
// discount. The existing refund service emits the folio reversal atomically.
export default function POSRoomChargeReversal({ orderId, disabled, onChanged }) {
  const [open, setOpen] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const intent = useRef(null);
  const locked = useRef(false);
  const generation = useRef(0);
  const load = async () => {
    const version = ++generation.current;
    setOpen(true); setBusy(true); setReceipt(null); setError('');
    try {
      const { data } = await axios.get(`/pos/v2/orders/${encodeURIComponent(orderId)}/receipt`);
      if (version !== generation.current) return;
      if (data.order_id !== orderId || data.payment_method !== 'room_charge') throw new Error('Adisyon oda hesabına ait değil.');
      setReceipt(data);
    } catch (e) { if (version === generation.current) setError(apiErrorText(e, e.message || 'Adisyon okunamadı.')); }
    finally { if (version === generation.current) setBusy(false); }
  };
  const remaining = receipt ? Math.round((Number(receipt.total) - Number(receipt.refunded_amount || 0)) * 100) / 100 : 0;
  const submit = async () => {
    if (disabled || locked.current || !receipt || !Number.isFinite(remaining) || remaining <= 0 || !reason.trim()) return;
    locked.current = true; setBusy(true); setError('');
    // A lost response must retry the exact same request and key.
    intent.current ||= { reason: reason.trim(), idempotency_key: crypto.randomUUID() };
    try {
      await axios.post(`/pos/v2/orders/${encodeURIComponent(orderId)}/refund`, intent.current);
      intent.current = null; setOpen(false); setReason('');
      toast.success('POS ters kaydı kaydedildi. Folyo güncellemesi işlem kuyruğundan uygulanır.');
      try { await onChanged?.(); } catch { toast.warning('İşlem kaydedildi. Folyo hareketlerini yenileyin.'); }
    } catch (e) { setError(apiErrorText(e, 'İşlem sonucu doğrulanamadı. Aynı isteği tekrar deneyin veya kayıtları kontrol edin.')); }
    finally { locked.current = false; setBusy(false); }
  };
  return <>
    <Button size="sm" variant="outline" disabled={disabled || busy} onClick={load}>POS kaynak kaydını geri al</Button>
    <Dialog open={open} onOpenChange={value => { if (!locked.current) { setOpen(value); if (!value) generation.current += 1; } }}>
      <DialogContent className="z-[120]" overlayClassName="z-[110]">
        <DialogHeader><DialogTitle>Oda hesabı POS ters kaydı</DialogTitle><DialogDescription>Adisyonun kalan tutarının tamamı POS’ta ters kaydedilir ve bağlı folyo hareketleri geri alınır. Nakit veya karta para gönderilmez. Adisyon birden fazla hizmet içeriyorsa tümü geri alınır.</DialogDescription></DialogHeader>
        {busy && !receipt && <p role="status">Kaynak adisyon okunuyor…</p>}
        {receipt && <><p>{receipt.order_number} · İş günü: {receipt.business_date}</p><p>Kalan ters kayıt tutarı: {formatCurrency(remaining, receipt.currency, { decimals: 2 })}</p>{remaining <= 0 && <p>Bu adisyonda geri alınabilecek tutar yok.</p>}</>}
        <label>İşlem nedeni<Textarea value={reason} disabled={busy || !!intent.current} onChange={e => setReason(e.target.value)} /></label>
        {error && <p role="alert">{error}</p>}
        <Button disabled={disabled || busy || !Number.isFinite(remaining) || remaining <= 0 || !reason.trim()} onClick={submit}>{busy ? 'İşleniyor…' : 'POS ve folyo ters kaydını onayla'}</Button>
      </DialogContent>
    </Dialog>
  </>;
}
