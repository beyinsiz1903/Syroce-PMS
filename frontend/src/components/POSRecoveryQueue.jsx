import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { readQueue, removeQueuedOrder, sendQueuedOrder } from '../lib/posOfflineQueue';
import { confirmDialog } from '../lib/dialogs';

export default function POSRecoveryQueue({ scope, version, onReplayed }) {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(() => {
    try { setRows(scope ? readQueue(scope) : []); }
    catch (error) { toast.error(error.message); }
  }, [scope]);
  useEffect(() => { refresh(); }, [refresh, version]);
  const replay = useCallback(async (onlyId) => {
    if (!scope) return;
    setBusy(true);
    try {
      for (const row of readQueue(scope)) {
        if (onlyId ? row.id !== onlyId : row.state === 'conflict') continue;
        await sendQueuedOrder(scope, row.id, axios);
        onReplayed?.(row);
      }
    } catch (error) { toast.error(error.message || 'Bekleyen sipariş gönderilemedi.'); }
    finally { setBusy(false); refresh(); }
  }, [scope, refresh, onReplayed]);
  useEffect(() => {
    const online = () => replay();
    window.addEventListener('online', online);
    window.addEventListener('storage', refresh);
    return () => { window.removeEventListener('online', online); window.removeEventListener('storage', refresh); };
  }, [replay, refresh]);
  if (!rows.length) return null;
  return <section className="border border-amber-400 bg-amber-50 rounded p-3 mb-3" aria-label="Bekleyen siparişler">
    <h2 className="font-semibold">Cihazda bekleyen siparişler ({rows.length})</h2>
    <p>Sunucu onayı alınmadan mutfağa iletilmiş sayılmaz. Tahsilatlar otomatik tekrarlanmaz. Sipariş gönderildiğinde güncel menü fiyatı uygulanır.</p>
    {rows.map(row => <div key={row.id} className="border-t py-2 text-sm">
      <strong>{row.body.table_number ? `Masa ${row.body.table_number}` : 'Adisyona ek sipariş'}</strong>
      <span> · {row.body.items.length} kalem · {row.state === 'conflict' ? 'Operatör müdahalesi gerekli' : 'Gönderim bekliyor'}</span>
      <p role={row.error ? 'alert' : undefined}>{row.error}</p>
      <button className="underline mr-4" disabled={busy} onClick={() => replay(row.id)}>Aynı isteği yeniden gönder</button>
      {row.state === 'conflict' && <button className="underline" disabled={busy} onClick={async () => {
        if (!await confirmDialog({ message: 'Sunucuda adisyonu kontrol ettiniz mi? Bu reddedilmiş isteği cihaz kuyruğundan kaldırıp masa ve ürünleri yeniden seçmeniz gerekir.' })) return;
        removeQueuedOrder(scope, row.id); refresh(); onReplayed?.(row);
      }}>Çakışmayı temizle ve yeniden düzenle</button>}
    </div>)}
  </section>;
}
