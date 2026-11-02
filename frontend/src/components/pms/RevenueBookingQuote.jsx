import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/currency';

export default function RevenueBookingQuote({ roomId, arrival, departure, currency, disabled, applied, onApply }) {
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const version = useRef(0);
  const inFlight = useRef(false);
  useEffect(() => {
    version.current += 1;
    inFlight.current = false;
    setQuote(null); setError(''); setBusy(false);
    return () => { version.current += 1; };
  }, [roomId, arrival, departure, currency]);
  const calculate = async () => {
    if (inFlight.current) return;
    const requestVersion = ++version.current;
    inFlight.current = true; setBusy(true); setError('');
    try {
      const result = await axios.post('/revenue/booking-quote', { room_id: roomId, check_in: arrival,
        check_out: departure, currency, confirm_currency: true });
      if (requestVersion !== version.current) return;
      const value = result.data;
      if (!value || value.currency !== currency || typeof value.quote_hash !== 'string' || value.quote_hash.length !== 64
        || !Number.isFinite(value.total_amount) || value.total_amount <= 0
        || !Array.isArray(value.daily_rates) || !value.daily_rates.length) throw new Error('Invalid pricing result');
      setQuote(value);
    } catch (failure) {
      if (requestVersion === version.current) {
        setQuote(null);
        setError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : 'Gelir planı hesaplanamadı; oda, tarih ve planı kontrol edin.');
      }
    } finally {
      if (requestVersion === version.current) { inFlight.current = false; setBusy(false); }
    }
  };
  return <div className="space-y-2 rounded border p-3 text-xs">
    <p>Gelir Kontrolleri’ndeki BAR/gün planını otelin kayıtlı para biriminde hesaplayın, toplamı kontrol ederek uygulayın. Farklı para birimi için kur çevrilmez. Mevcut rezervasyonlar ve kanallar değişmez; fazla satış izni verilmez.</p>
    <Button type="button" variant="outline" size="sm" disabled={disabled || busy || !roomId || !arrival || !departure} onClick={calculate}>Planı {currency} olarak hesapla</Button>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {quote && <div>
      <p>{quote.daily_rates.length} gece · {formatCurrency(quote.total_amount, currency)} · Minimum {quote.min_stay} gece</p>
      <Button type="button" size="sm" disabled={disabled || busy} onClick={() => onApply(quote)}>Onayla ve rezervasyona uygula</Button>
    </div>}
    {applied && <div role="status">Gelir planı seçildi; güncel kaynak kaydetme sırasında yeniden doğrulanır. <Button type="button" variant="outline" size="sm" onClick={() => onApply(null)}>Manuel fiyata dön</Button></div>}
  </div>;
}
