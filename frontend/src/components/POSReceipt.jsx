import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { formatCurrency } from '@/lib/currency';
import { confirmDialog } from '@/lib/dialogs';
import { Input } from './ui/input';

export default function POSReceipt({ orderId, onRefund }) {
  const [open, setOpen] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [printers, setPrinters] = useState([]);
  const [printer, setPrinter] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const keyRef = useRef(null);
  const previewRef = useRef(null);
  const refundRequestRef = useRef(null);
  const refundBusyRef = useRef(false);
  const [refundReason, setRefundReason] = useState('');
  const [refundUncertain, setRefundUncertain] = useState(false);
  useEffect(() => {
    refundRequestRef.current = null;
    setRefundReason(''); setRefundUncertain(false);
  }, [orderId]);
  const receiptUrl = `/pos/v2/orders/${encodeURIComponent(orderId)}/receipt`;
  const refreshRefund = async () => {
    if (refundBusyRef.current) return;
    refundBusyRef.current = true; setBusy(true);
    try {
      const latest = (await axios.get(receiptUrl)).data;
      setReceipt(latest);
      const pending = refundRequestRef.current;
      if (pending && Math.round(Number(latest.refunded_amount || 0) * 100) !== pending.refundedCents) {
        // A committed or competing refund must be reviewed before any new write.
        refundRequestRef.current = null; setRefundReason('');
      }
      setRefundUncertain(false); setError('');
      onRefund?.();
    } catch { setError('İade durumu okunamadı; yeniden iade göndermeyin.'); }
    finally { refundBusyRef.current = false; setBusy(false); }
  };
  const refund = async () => {
    if (refundBusyRef.current || refundUncertain || !refundReason.trim()) return;
    refundBusyRef.current = true; setBusy(true); setError('');
    let submitted = false;
    try {
      const latest = (await axios.get(receiptUrl)).data;
      setReceipt(latest);
      const refundedCents = Math.round(Number(latest.refunded_amount || 0) * 100);
      const amountCents = Math.round(Number(latest.total) * 100) - refundedCents;
      if (!Number.isFinite(amountCents) || amountCents <= 0) return;
      let request = refundRequestRef.current;
      if (request && request.refundedCents !== refundedCents) {
        refundRequestRef.current = null; setRefundReason('');
        setError('İade tutarı değişmiş. Güncel fişi inceleyip nedeni yeniden girin.'); return;
      }
      if (!request) request = { refundedCents, body: { amount: amountCents / 100, reason: refundReason.trim(), idempotency_key: crypto.randomUUID() } };
      if (!await confirmDialog({ message: `${latest.order_number || orderId} adisyonunun kalan ${formatCurrency(request.body.amount, latest.currency)} tutarı iade edilsin mi? İşlem özgün ödemeye bağlanır ve kaydedilir.` })) return;
      refundRequestRef.current = request; submitted = true;
      await axios.post(`/pos/v2/orders/${encodeURIComponent(orderId)}/refund`, request.body);
      setReceipt((await axios.get(receiptUrl)).data);
      refundRequestRef.current = null; setRefundReason('');
      toast.success('İade kaydedildi'); onRefund?.();
    } catch {
      if (submitted) setRefundUncertain(true);
      setError(submitted ? 'İade sonucu uzlaştırılmalı. Önce iade durumunu yenileyin; tekrar gönderilmedi.' : 'Güncel fiş okunamadı; iade gönderilmedi.');
    } finally { refundBusyRef.current = false; setBusy(false); }
  };
  const load = async () => {
    setOpen(true); setBusy(true); setReceipt(null); setError(''); keyRef.current = null;
    try {
      const result = await axios.get(`/pos/v2/orders/${encodeURIComponent(orderId)}/receipt`);
      setReceipt(result.data);
      try {
        const devices = await axios.get('/pos/ext/print/printers');
        setPrinters((devices.data.printers || []).filter(row => row.enabled !== false));
      } catch { setPrinters([]); }
    } catch { setError('Fiş alınamadı; boş veya sıfır tutarlı belge oluşturulmadı.'); }
    finally { setBusy(false); }
  };
  const printBrowser = () => {
    const popup = window.open('', '_blank', 'width=450,height=700');
    if (!popup) { toast.error('Yazdırma penceresi engellendi.'); return; }
    const document = popup.document;
    document.title = 'Müşteri hesap fişi · Mali belge değildir';
    const pre = document.createElement('pre');
    pre.style.cssText = 'white-space:pre-wrap;font:14px monospace;padding:20px;max-width:320px';
    pre.textContent = previewRef.current?.innerText || '';
    document.body.appendChild(pre);
    popup.print();
  };
  const printDevice = async () => {
    if (busy || !printer) return;
    setBusy(true);
    if (!keyRef.current) keyRef.current = crypto.randomUUID();
    try {
      const result = await axios.post(`/pos/v2/orders/${encodeURIComponent(orderId)}/receipt/print`, { printer_id: printer, idempotency_key: keyRef.current });
      if (result.data.success) toast.success(result.data.message);
      else toast.error(result.data.message || 'Baskı doğrulanamadı.');
      keyRef.current = null;
    } catch { toast.error('Baskı sonucu belirsiz. Aynı işlemi tekrar denemeden önce yazıcıyı kontrol edin.'); }
    finally { setBusy(false); }
  };
  const money = value => formatCurrency(value || 0, receipt?.currency, { decimals: 2 });
  return <>
    <Button variant="outline" onClick={load} disabled={!orderId}>Müşteri fişi / Yeniden yazdır</Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent><DialogHeader><DialogTitle>Müşteri hesap fişi</DialogTitle></DialogHeader>
      {busy && !receipt && <p role="status">Fiş yükleniyor…</p>}
      {error && <p role="alert">{error}</p>}
      {receipt && <><div ref={previewRef} className="max-h-80 overflow-y-auto space-y-2 rounded border p-4 text-sm">
        <strong>{receipt.header}</strong><p>{receipt.order_number} · {receipt.business_date}</p><p>Masa: {receipt.table || '—'}</p>
        {receipt.items.map((item, index) => <p key={index}>{item.quantity} × {item.name} · {money(item.line_total)}</p>)}
        <p>KDV: {money(receipt.tax_amount)}</p><p>İndirim: {money(receipt.discount_amount)}</p><p>Servis: {money(receipt.service_charge_amount)}</p><p>Bahşiş: {money(receipt.tip_amount)}</p>
        <strong className="block">Toplam: {money(receipt.total)}</strong>{receipt.refunded_amount > 0 && <p>İade: {money(receipt.refunded_amount)}</p>}
        <p>{receipt.footer}</p>
      </div><Button variant="outline" onClick={printBrowser}>Tarayıcıdan yazdır</Button>
      <label className="text-sm">Fiş yazıcısı<select className="mt-1 block w-full rounded border p-2" value={printer} onChange={event => { setPrinter(event.target.value); keyRef.current = null; }}><option value="">Yazıcı seçin</option>{printers.map(row => <option key={row.printer_id} value={row.printer_id}>{row.name || row.printer_id}{row.driver === 'simulator' ? ' · Simülasyon' : ''}</option>)}</select></label>
      <Button onClick={printDevice} disabled={!printer || busy}>{busy ? 'Gönderiliyor…' : 'Yazıcıya gönder / Kopya yazdır'}</Button>
      <section className="space-y-2 border-t pt-3" aria-label="Adisyon iadesi">
        <p className="text-sm">Geçmiş adisyonun kalan tutarını özgün ödeme yöntemlerine iade edin. İade için yönetici yetkisi gerekir.</p>
        <label className="block text-sm">İade nedeni<Input value={refundReason} onChange={event => setRefundReason(event.target.value)} disabled={busy || refundUncertain || Boolean(refundRequestRef.current)} /></label>
        <Button variant="outline" onClick={refund} disabled={busy || refundUncertain || !refundReason.trim() || Number(receipt.total) <= Number(receipt.refunded_amount || 0)}>Kalan tutarı iade et</Button>
        {refundUncertain && <Button variant="outline" onClick={refreshRefund} disabled={busy}>İade durumunu yenile</Button>}
      </section>
      <p className="text-xs text-gray-500">Bu belge mali fiş değildir. Ağ yazıcısına sunucunun erişebilmesi gerekir; simülasyon gerçek baskı yapmaz.</p></>}
    </DialogContent></Dialog>
  </>;
}
