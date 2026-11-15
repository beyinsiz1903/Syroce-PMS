import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import apiErrorText from '@/utils/apiErrorText';
import { toast } from 'sonner';
import FolioViewDialog from '@/components/pms/FolioViewDialog';

// Keep the reservation card mounted. Never reuse another folio's loaded rows.
export default function ReservationFolioDetails({ booking, guest, folios, initialFolioId, readOnly, onClose, onChanged }) {
  const [folioId, setFolioId] = useState(initialFolioId || '');
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const changed = useRef(false);
  const load = async id => {
    const request = ++generation.current;
    setDetails(null);
    if (!id) { setLoading(false); return; }
    setLoading(true);
    try {
      const { data } = await axios.get(`/folio/${id}`);
      if (request !== generation.current) return;
      if (data?.folio?.id !== id || data.folio.booking_id !== booking.id || !folios.some(f => f.id === id)) {
        throw new Error('Folyo bu rezervasyona ait değil. Kartı yenileyin.');
      }
      setDetails(data);
    } catch (error) {
      if (request === generation.current) toast.error(apiErrorText(error, error.message || 'Folyo yüklenemedi'));
    } finally {
      if (request === generation.current) setLoading(false);
    }
  };
  useEffect(() => {
    load(folioId);
    return () => { generation.current += 1; };
    // A new reservation mounts a new instance keyed by booking.id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folioId]);
  const refresh = async id => { changed.current = true; await load(id); };
  return <FolioViewDialog open onClose={() => {
    onClose();
    if (changed.current) void Promise.resolve().then(() => onChanged?.()).catch(() => toast.warning('İşlem kaydedildi. Kartı yenileyin.'));
  }}
    selectedFolio={details?.folio} folios={folios} folioCharges={details?.charges || []}
    folioPayments={details?.payments || []} guests={guest ? [guest] : []} bookings={[booking]}
    onPickFolio={id => id === folioId ? load(id) : setFolioId(id)} onChargePosted={refresh} onPaymentPosted={refresh}
    isLoading={loading} readOnly={readOnly} />;
}
