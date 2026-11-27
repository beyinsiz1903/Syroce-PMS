import axios from 'axios';

const UNKNOWN = 'Giriş sonucu doğrulanamadı. Rezervasyonu yenileyip kontrol edin; giriş isteği otomatik tekrarlanmadı.';

// A lost response is not a failed transaction. Read the authoritative booking
// before a subsequent, explicitly confirmed attempt can submit another POST.
export function createCheckinConfirmation(client) {
  const pending = new Map();
  const uncertain = new Set();
  const readStatus = async (id) => {
    const { data } = await client.get(`/pms/reservations/${encodeURIComponent(id)}/full-detail`, { timeout: 10000 });
    if (data?.booking?.id !== id || !data.booking.status) throw new Error(UNKNOWN);
    return data.booking.status;
  };
  return (id) => {
    if (pending.has(id)) return pending.get(id);
    const run = async () => {
      if (uncertain.has(id)) {
        let status;
        try { status = await readStatus(id); } catch { throw new Error(UNKNOWN); }
        if (status === 'checked_in') {
          uncertain.delete(id);
          return { recovered: true };
        }
        if (!['pending', 'confirmed', 'guaranteed'].includes(status)) throw new Error(UNKNOWN);
      }
      try {
        const result = await client.post(`/frontdesk/checkin/${encodeURIComponent(id)}?create_folio=true`, null, { timeout: 15000 });
        uncertain.delete(id);
        return result;
      } catch (error) {
        const status = Number(error?.response?.status || 0);
        if (status && status !== 408 && status < 500) throw error;
        uncertain.add(id);
        try {
          if (await readStatus(id) === 'checked_in') {
            uncertain.delete(id);
            return { recovered: true };
          }
        } catch { /* Preserve uncertainty; never retry a mutation here. */ }
        throw new Error(UNKNOWN);
      }
    };
    const promise = run().finally(() => pending.delete(id));
    pending.set(id, promise);
    return promise;
  };
}

export const confirmReservationCheckIn = createCheckinConfirmation(axios);
