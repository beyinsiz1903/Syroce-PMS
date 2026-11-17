import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { confirmDialog } from '@/lib/dialogs';

const MESSAGES = {
  NOT_REQUESTED: 'Rezervasyon PMS’de iptal edildi. İptal henüz Exely’ye gönderilmedi.',
  PENDING: 'PMS’de iptal edildi. Exely’ye gönderim bekleniyor.',
  SENDING: 'Exely onayı henüz doğrulanmadı. Sonucu kontrol edin; yeniden göndermeyin.',
  CONFIRMED: 'Exely iptali onayladı.',
  REMOTE_CANCELLED: 'İptal Exely’den alındı. Tekrar gönderim gerekmiyor.',
  UNKNOWN: 'Exely’nin iptali alıp almadığı doğrulanamadı. Tekrar göndermeden önce Exely kaydını kontrol edin.',
  REJECTED: 'Exely iptali kabul etmedi. Bağlantı ve rezervasyon kaydını kontrol edin.',
  BLOCKED: 'PMS’de iptal edildi. Exely’ye gönderim için rezervasyon ve bağlantı kontrolü gerekiyor.',
};

export default function ExelyCancellationStatus({ booking }) {
  return <CancellationStatus key={booking?.id} booking={booking} />;
}

function CancellationStatus({ booking }) {
  const [delivery, setDelivery] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const eligible = booking?.status === 'cancelled' && booking?.source?.provider === 'exely';
  const load = useCallback(async () => {
    if (!eligible || !booking?.id) return;
    try {
      const { data } = await axios.get(`/pms-core/bookings/${booking.id}/exely-cancellation`);
      setDelivery(data);
      setError('');
    } catch {
      setError('Exely iptal durumu alınamadı. Yetkinizi ve bağlantıyı kontrol edin.');
    }
  }, [eligible, booking?.id]);
  useEffect(() => { setDelivery(null); setError(''); void load(); }, [load]);
  useEffect(() => {
    if (!['PENDING', 'SENDING'].includes(delivery?.state)) return undefined;
    const timer = setInterval(() => { void load(); }, 10000);
    return () => clearInterval(timer);
  }, [delivery?.state, load]);
  if (!eligible) return null;

  const send = async () => {
    setBusy(true);
    try {
      if (!await confirmDialog({ message: delivery?.can_retry
        ? 'Önceki iptal Exely tarafından reddedildi. Sorunu giderdiyseniz bu rezervasyonun tamamı için iptal yeniden gönderilsin mi?'
        : 'PMS’de iptal edilen bu rezervasyonun tamamı için Exely’ye iptal gönderilsin mi?', variant: 'danger' })) return;
      const { data } = await axios.post(`/pms-core/bookings/${booking.id}/exely-cancellation`, {
        reason: booking.cancellation_reason?.trim() || 'Cancelled by hotel operator',
        ...(delivery?.can_retry ? { retry_attempt: delivery.attempt } : {}),
      });
      setDelivery(data);
      setError('');
    } catch {
      // Reconcile first: the request may have been queued even if the response was lost.
      await load();
      setError('Gönderim sonucu yeniden kontrol edildi. Exely onayı görünmeden teslim edildi sayılmaz.');
    } finally { setBusy(false); }
  };
  const confirmed = ['CONFIRMED', 'REMOTE_CANCELLED'].includes(delivery?.state);
  const text = delivery?.code === 'EXELY_WHOLE_BOOKING_REQUIRED'
    ? 'Exely yalnız rezervasyonun tamamının iptalini kabul eder. Diğer odalar aktif olduğu için iptal gönderilmedi.'
    : MESSAGES[delivery?.state] || 'Exely iptal durumu kontrol ediliyor…';
  return <section data-testid="exely-cancellation-status" className={`rounded-lg border p-4 space-y-2 ${confirmed ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
    <h3 className="font-semibold text-sm">Exely iptal bildirimi</h3>
    <p className="text-sm">{text}</p>
    {delivery?.provider_codes?.length > 0 && <p className="text-sm">Exely hata kodu: {delivery.provider_codes.join(', ')}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <div className="flex gap-2">
      {delivery?.can_send && <Button type="button" size="sm" disabled={busy} onClick={send}>İptali Exely’ye gönder</Button>}
      {delivery?.can_retry && <Button type="button" size="sm" disabled={busy} onClick={send}>İptali yeniden gönder</Button>}
      <Button type="button" size="sm" variant="outline" disabled={busy} onClick={load}>Durumu yenile</Button>
    </div>
  </section>;
}
