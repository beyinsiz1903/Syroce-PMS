import { useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { formatCurrency } from '@/lib/currency';

export default function POSReceipt({ orderId }) {
  const [open, setOpen] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [printers, setPrinters] = useState([]);
  const [printer, setPrinter] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const keyRef = useRef(null);
  const previewRef = useRef(null);
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
      <p className="text-xs text-gray-500">Bu belge mali fiş değildir. Ağ yazıcısına sunucunun erişebilmesi gerekir; simülasyon gerçek baskı yapmaz.</p></>}
    </DialogContent></Dialog>
  </>;
}
