import { useState, useEffect } from 'react';
import api from '@/api/axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Clock, Calculator } from 'lucide-react';
import { toast } from 'sonner';

export default function EarlyLateChargeModal({ open, onClose, bookingId, direction, defaultHour = 10, onApplied }) {
  const [hour, setHour] = useState(defaultHour);
  const [calc, setCalc] = useState(null);
  const [busy, setBusy] = useState(false);
  const [overrideAmount, setOverrideAmount] = useState('');
  const [overrideReason, setOverrideReason] = useState('');

  useEffect(() => { if (open) { setCalc(null); setOverrideAmount(''); setOverrideReason(''); setHour(defaultHour); } }, [open, defaultHour]);

  const calculate = async () => {
    setBusy(true);
    try {
      const { data } = await api.post('/pms/early-late/calculate', { booking_id: bookingId, direction, actual_hour: hour });
      setCalc(data);
    } catch (e) { toast.error('Hesaplama hatası: ' + (e.response?.data?.detail || e.message)); }
    finally { setBusy(false); }
  };

  const apply = async () => {
    if (!calc?.applicable && !overrideAmount) { toast.error('Tutar yok'); return; }
    const amount = overrideAmount ? parseFloat(overrideAmount) : calc.amount;
    const label = (calc?.label || (direction === 'early_checkin' ? 'Erken Giriş' : 'Geç Çıkış')) + ` (saat ${hour})`;
    setBusy(true);
    try {
      await api.post(`/reservations/${bookingId}/extra-charges`, {
        charge_name: label,
        charge_amount: amount,
        notes: overrideAmount ? `Manuel override: ${overrideReason || 'sebep belirtilmedi'}` : 'Saat-bazli otomatik ucret',
      });
      toast.success('Ek ücret folyoya işlendi');
      onApplied?.();
      onClose();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-orange-600" />
            {direction === 'early_checkin' ? 'Erken Giriş Ek Ücreti' : 'Geç Çıkış Ek Ücreti'}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs">Gerçekleşen Saat (0-23)</Label>
            <div className="flex gap-2">
              <Input type="number" min={0} max={23} value={hour} onChange={e => setHour(parseInt(e.target.value) || 0)} className="h-9" />
              <Button onClick={calculate} disabled={busy} variant="outline">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Calculator className="w-4 h-4" />}
              </Button>
            </div>
          </div>

          {calc && (
            <div className={`border rounded p-3 text-sm ${calc.applicable ? 'bg-orange-50 border-orange-200' : 'bg-emerald-50 border-emerald-200'}`}>
              {calc.applicable ? (
                <>
                  <div className="font-semibold">{calc.label}</div>
                  <div className="text-xs text-gray-600 mt-1">Gecelik: {calc.nightly_rate} {calc.currency} · {calc.nights} gece</div>
                  <div className="text-lg font-bold mt-1">{calc.amount} {calc.currency}</div>
                </>
              ) : (
                <div className="text-emerald-800">{calc.reason}</div>
              )}
            </div>
          )}

          <div className="border-t pt-2">
            <Label className="text-xs text-gray-500">Manuel Override (opsiyonel)</Label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <Input type="number" placeholder="Tutar" value={overrideAmount} onChange={e => setOverrideAmount(e.target.value)} className="h-9" />
              <Input placeholder="Sebep" value={overrideReason} onChange={e => setOverrideReason(e.target.value)} className="h-9" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>İptal</Button>
          <Button onClick={apply} disabled={busy || (!calc?.applicable && !overrideAmount)} className="bg-orange-600 hover:bg-orange-700">
            Folyoya Ekle
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
