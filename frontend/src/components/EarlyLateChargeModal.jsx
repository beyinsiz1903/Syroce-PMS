import { useState, useEffect, useRef } from 'react';
import api from '@/api/axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Clock, Calculator } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { moneyInputProps, parseMoneyInput } from '@/lib/moneyInput';
import { formatCurrency } from '@/lib/currency';

export default function EarlyLateChargeModal({ open, onClose, bookingId, direction, defaultHour = 10, serviceDate = '', onApplied }) {
  const { t } = useTranslation();
  const [hour, setHour] = useState(defaultHour);
  const [calc, setCalc] = useState(null);
  const [busy, setBusy] = useState(false);
  const [overrideAmount, setOverrideAmount] = useState('');
  const [overrideReason, setOverrideReason] = useState('');
  const [date, setDate] = useState(serviceDate);
  const [uncertain, setUncertain] = useState(false);
  const requestRef = useRef(0);
  const applyingRef = useRef(false);

  useEffect(() => {
    requestRef.current += 1;
    if (open) { setCalc(null); setOverrideAmount(''); setOverrideReason(''); setHour(defaultHour); setDate(serviceDate); setUncertain(false); setBusy(false); }
    return () => { requestRef.current += 1; };
  }, [open, defaultHour, serviceDate, bookingId, direction]);

  const calculate = async () => {
    if (applyingRef.current || uncertain) return;
    const request = ++requestRef.current;
    setCalc(null);
    setBusy(true);
    try {
      // hour float (dakika hassasiyeti) — backend ge=0, le=24 kabul ediyor.
      const h = Number(hour);
      if (!Number.isFinite(h) || h < 0 || h >= 24) throw new Error('Geçerli bir saat seçin.');
      const { data } = await api.post('/pms/early-late/calculate', {
        booking_id: bookingId, direction, actual_hour: h,
      });
      if (request === requestRef.current) setCalc(data);
    } catch (e) { toast.error('Tutar hesaplanırken bir hata oluştu: ' + (e.response?.data?.detail || e.message)); }
    finally { if (request === requestRef.current) setBusy(false); }
  };

  const hasOverride = overrideAmount.trim() !== '';
  const amount = hasOverride ? parseMoneyInput(overrideAmount) : calc?.amount;
  const canApply = !!calc?.currency && !!date && Number.isFinite(amount) && amount >= 0 &&
    (hasOverride ? overrideReason.trim().length >= 3 : calc?.applicable) && !uncertain;
  const time = `${String(Math.floor(Number(hour) || 0)).padStart(2, '0')}:${String(Math.round(((Number(hour) || 0) % 1) * 60)).padStart(2, '0')}`;

  const apply = async () => {
    if (!canApply || busy || applyingRef.current) return;
    const label = (calc?.label || (direction === 'early_checkin' ? 'Erken Giriş' : 'Geç Çıkış')) + ` (${date} ${time})`;
    const description = hasOverride
      ? `${label} — Tutar düzeltme nedeni: ${overrideReason.trim()}`
      : label;
    applyingRef.current = true;
    setBusy(true);
    try {
      await api.post(`/pms/reservations/${bookingId}/add-extra-charge`, {
        description,
        category: 'other',
        amount,
        quantity: 1,
        input_currency: calc?.currency,
        service_date: date,
        service_time: time,
      });
      toast.success('Ek ücret folyoya işlendi');
      await onApplied?.();
      onClose();
    } catch (e) {
      if (!e.response || e.response.status >= 500) setUncertain(true);
      toast.error('İşlem Hatası: ' + (e.response?.data?.detail || e.message));
    }
    finally { applyingRef.current = false; setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(value) => { if (!value && !applyingRef.current) onClose(); }}>
      <DialogContent className="z-[80] max-w-md" overlayClassName="z-[70]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-amber-600" />
            {direction === 'early_checkin' ? 'Erken Giriş Ek Ücreti' : 'Geç Çıkış Ek Ücreti'}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-slate-600">Bu işlem yalnız ek ücret kaydeder; misafirin giriş veya çıkış durumunu değiştirmez.</p>
          {uncertain && <p role="alert" className="text-sm text-red-700">İşlemin sonucu doğrulanamadı. Mükerrer ücret oluşturmamak için tekrar eklemeyin; kapatıp folyo ve işlem geçmişini kontrol edin.</p>}
          <div>
            <Label htmlFor="early-late-service-date">Hizmet tarihi</Label>
            <Input id="early-late-service-date" type="date" value={date} disabled={busy || uncertain} onChange={e => setDate(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="early-late-service-time" className="text-xs">Hizmet saati</Label>
            <div className="flex gap-2">
              <Input id="early-late-service-time" type="time" value={time} disabled={applyingRef.current || uncertain} onChange={e => {
                const [h, m] = e.target.value.split(':').map(Number);
                requestRef.current += 1; setBusy(false); setCalc(null); setHour(h + m / 60);
              }} className="h-9" />
              <Button onClick={calculate} disabled={busy || uncertain} variant="outline" aria-label="Ücreti hesapla">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Calculator className="w-4 h-4" />}
              </Button>
            </div>
          </div>

          {calc && (
            <div className={`border rounded p-3 text-sm ${calc.applicable ? 'bg-amber-50 border-amber-200' : 'bg-emerald-50 border-emerald-200'}`}>
              {calc.applicable ? (
                <>
                  <div className="font-semibold">{calc.label}</div>
                  <div className="text-xs text-gray-600 mt-1">Gecelik: {formatCurrency(calc.nightly_rate, calc.currency)} · {calc.nights} gece</div>
                  <div className="text-lg font-bold mt-1">{formatCurrency(calc.amount, calc.currency)}</div>
                </>
              ) : (
                <div className="text-emerald-800">{calc.reason}</div>
              )}
            </div>
          )}

          <div className="border-t pt-2">
            <Label className="text-xs text-gray-500">Tutarı değiştir (isteğe bağlı, gerekçe zorunlu)</Label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <Input {...moneyInputProps} aria-label="Düzeltilmiş tutar" disabled={busy || !calc || uncertain} placeholder={t('cm.components_EarlyLateChargeModal.tutar')} value={overrideAmount} onChange={e => setOverrideAmount(e.target.value)} className="h-9" />
              <Input aria-label="Düzeltme nedeni" disabled={busy || !calc || uncertain} placeholder="Gerekçe" value={overrideReason} onChange={e => setOverrideReason(e.target.value)} className="h-9" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={applyingRef.current} onClick={onClose}>{t('cm.components_EarlyLateChargeModal.iptal')}</Button>
          <Button onClick={apply} disabled={busy || !canApply}>
            {t('cm.components_EarlyLateChargeModal.folyoya_ekle')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
