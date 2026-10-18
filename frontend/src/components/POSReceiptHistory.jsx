import { useEffect, useState } from 'react';
import axios from 'axios';
import POSReceipt from './POSReceipt';

export default function POSReceiptHistory({ outletId }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setRows(null); setError('');
    axios.get('/pos/v2/receipts', { params: outletId ? { outlet_id: outletId } : {} }).then(response => {
      if (active) setRows(response.data.receipts || []);
    }).catch(() => { if (active) setError('Fiş geçmişi yüklenemedi.'); });
    return () => { active = false; };
  }, [outletId]);
  return <section className="rounded-xl border bg-white p-4"><h3 className="mb-3 font-semibold">Son müşteri fişleri · Yeniden yazdır</h3>
    {error ? <p role="alert">{error}</p> : rows === null ? <p>Fişler yükleniyor…</p> : !rows.length ? <p>Bu satış noktasında kapatılmış adisyon yok.</p> : rows.map(row => <div key={row.order_id} className="flex flex-wrap items-center justify-between gap-2 border-t py-3"><span className="text-sm">{row.order_number || row.order_id} · {row.transaction_date}</span><POSReceipt orderId={row.order_id} /></div>)}
  </section>;
}
