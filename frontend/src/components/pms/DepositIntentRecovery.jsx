import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { submitDepositIntent } from '@/lib/depositIntent';

// Recovery uses the stored body, not a newly entered form or a newly selected
// auto-created folio. It must remain available even after checkout/full refund.
export default function DepositIntentRecovery({ bookingId, onRecovered }) {
  const [busy, setBusy] = useState(false);
  const [, refresh] = useState(0);
  const pending = ['receive', 'refund'].flatMap(action => {
    try {
      const item = JSON.parse(sessionStorage.getItem(`pms:deposit-intent:v1:${bookingId}:${action}`) || 'null');
      return item?.body?.request_id ? [{ action, body: item.body }] : [];
    } catch { return []; }
  });
  const recover = async ({ action, body }) => {
    setBusy(true);
    const payload = { ...body };
    delete payload.request_id;
    try {
      await submitDepositIntent(bookingId, action, payload, exact => axios.post(
        `/pms/reservations/${bookingId}/${action === 'receive' ? 'record-deposit' : 'refund-deposit'}`, exact));
      toast.success('Depozito sonucu aynı işlem anahtarıyla doğrulandı.');
      onRecovered?.();
    } catch (error) { toast.error(error.response?.data?.detail || error.message); }
    setBusy(false);
    refresh(value => value + 1);
  };
  return pending.map(item => <div key={item.action} role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">
    <p>Önceki depozito {item.action === 'receive' ? 'tahsilatının' : 'iadesinin'} sonucu doğrulanmalı. Tutar: {item.body.amount ?? item.body.refund_amount} · {item.body.method ?? item.body.refund_method}. Aynı işlem anahtarıyla kontrol edilir.</p>
    <Button size="sm" disabled={busy} onClick={() => recover(item)}>Önceki {item.action === 'receive' ? 'tahsilatı' : 'iadeyi'} doğrula</Button>
  </div>);
}
