import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Pencil, Check, Loader2, Plus, Receipt, ArrowRightLeft, Clock, Lock, Gift, X } from 'lucide-react';
import { API, fmtDate, fmtTL, fmtTs, FormField, SelectField } from './helpers';
import EarlyLateChargeModal from '@/components/EarlyLateChargeModal';
import { useTranslation } from 'react-i18next';

const parseDecimalInput = value => {
  const normalized = String(value ?? '').trim();
  if (!/^\d+(?:[.,]\d+)?$/.test(normalized)) return Number.NaN;
  return Number(normalized.replace(',', '.'));
};

export function DailyRatesTab({
  dailyRates,
  booking,
  onRefresh,
  readOnly = false,
  businessDate,
}) {
  const {
    t
  } = useTranslation();
  const [editMode, setEditMode] = useState(false);
  const [rates, setRates] = useState([]);
  const [saving, setSaving] = useState(false);
  const [showCompForm, setShowCompForm] = useState(false);
  const [compReason, setCompReason] = useState('');
  useEffect(() => {
    setRates(dailyRates || []);
  }, [dailyRates]);
  const normalizedBusinessDate = String(businessDate || '').slice(0, 10);
  const isClosedRate = rate => Boolean(normalizedBusinessDate && String(rate?.date || '').slice(0, 10) < normalizedBusinessDate);
  const anyEditable = rates.some(rate => !isClosedRate(rate));
  const hasClosedRates = rates.some(isClosedRate);
  const isComplimentary = Boolean(booking?.is_complimentary);
  const handleSave = async () => {
    if (rates.some(rate => !Number.isFinite(parseDecimalInput(rate.rate)) || parseDecimalInput(rate.rate) <= 0)) {
      toast.error('Günlük fiyat sıfırdan büyük olmalıdır');
      return;
    }
    setSaving(true);
    try {
      const payloadRates = rates.map(r => ({ ...r, rate: parseDecimalInput(r.rate) }));
      await axios.put(`/pms/reservations/${booking.id}/daily-rates`, {
        rates: payloadRates
      });
      toast.success('Günlük fiyatlar güncellendi');
      setEditMode(false);
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  };
  const handleComplimentary = async () => {
    const reason = compReason.trim();
    if (reason.length < 3) {
      toast.error('Comp gerekçesi en az 3 karakter olmalı');
      return;
    }
    setSaving(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/mark-complimentary`, { reason });
      toast.success('Rezervasyon comp olarak kaydedildi');
      setShowCompForm(false);
      setCompReason('');
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  };
  return <div data-testid="daily-rates-tab" className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">{t('cm.pages_reservationdetail_PricingTabs.gunluk_fiyatlar')}</span>
        <div className="flex items-center gap-2">
          {!isComplimentary && <Button size="sm" variant="outline" onClick={() => setShowCompForm(value => !value)} disabled={saving || readOnly || !anyEditable} className="h-7 text-xs border-amber-300 text-amber-800 hover:bg-amber-50" title={readOnly ? 'Geçmiş rezervasyonlar salt okunurdur' : !anyEditable ? 'Night Audit ile kapanmış günler comp yapılamaz' : 'Gerekçeli olarak ücretsiz konaklama tanımla'}>
              <Gift className="w-3 h-3 mr-1" />
              Comp Ver
            </Button>}
          <Button size="sm" variant="outline" onClick={() => editMode ? handleSave() : setEditMode(true)} disabled={saving || readOnly || !anyEditable || isComplimentary} className="h-7 text-xs" title={isComplimentary ? 'Comp rezervasyonun günlük fiyatları değiştirilemez' : readOnly ? 'Geçmiş rezervasyonlar salt okunurdur' : !anyEditable ? 'Night Audit ile kapanmış günlerin fiyatı değiştirilemez' : undefined}>
            {saving ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : editMode ? <Check className="w-3 h-3 mr-1" /> : <Pencil className="w-3 h-3 mr-1" />}
            {editMode ? 'Kaydet' : 'Düzenle'}
          </Button>
        </div>
      </div>
      {isComplimentary && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" data-testid="complimentary-summary">
          <div className="flex items-center gap-1.5 font-medium"><Gift className="h-4 w-4" /> Comp konaklama</div>
          {booking?.complimentary_reason && <p className="mt-0.5 text-xs text-emerald-800">Gerekçe: {booking.complimentary_reason}</p>}
        </div>}
      {showCompForm && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2" data-testid="complimentary-form">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-amber-950">Rezervasyonu comp yap</p>
              <p className="text-xs text-amber-800">Ödeme kaydı oluşmaz. Tahakkuk, ödeme veya fatura varsa finansal comp/indirim fişi gerekir.</p>
            </div>
            <Button type="button" variant="ghost" size="icon" className="h-6 w-6" aria-label="Comp formunu kapat" onClick={() => setShowCompForm(false)}><X className="h-4 w-4" /></Button>
          </div>
          <Input value={compReason} onChange={event => setCompReason(event.target.value)} placeholder="Comp gerekçesi (zorunlu)" maxLength={500} disabled={saving} />
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setShowCompForm(false)} disabled={saving}>Vazgeç</Button>
            <Button type="button" size="sm" onClick={handleComplimentary} disabled={saving} className="bg-amber-600 hover:bg-amber-700">{saving && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Comp Olarak Kaydet</Button>
          </div>
        </div>}
      {readOnly && <p className="text-xs text-slate-500">Geçmiş veya tamamlanmış rezervasyonlarda fiyat değiştirilemez.</p>}
      {!readOnly && hasClosedRates && <p className="text-xs text-slate-500">Night Audit ile kapanan tarihler kilitlidir; yalnızca açık iş günü ve sonrası düzenlenebilir.</p>}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr><th className="text-left py-2 px-3 text-xs text-gray-500 font-medium">{t('cm.pages_reservationdetail_PricingTabs.tarih')}</th><th className="text-right py-2 px-3 text-xs text-gray-500 font-medium">Fiyat (TL)</th></tr></thead>
          <tbody>
            {rates.map((r, i) => <tr key={r.id || i} className="border-t">
                <td className="py-2 px-3 text-gray-700">{fmtDate(r.date)}</td>
                <td className="py-2 px-3 text-right">
                  {editMode && !isClosedRate(r) ? <Input type="text" inputMode="decimal" value={r.rate} onChange={e => {
                const u = [...rates];
                u[i] = {
                  ...u[i],
                  rate: e.target.value
                };
                setRates(u);
              }} className="h-7 text-sm text-right w-24 ml-auto" /> : <span className="inline-flex items-center justify-end gap-1.5 font-medium text-gray-800">{editMode && isClosedRate(r) && <><Lock className="h-3 w-3 text-slate-400" /><span className="sr-only">Gün sonu kapalı</span></>}{fmtTL(r.rate)} TL</span>}
                </td>
              </tr>)}
          </tbody>
          <tfoot className="bg-gray-50 border-t-2"><tr><td className="py-2 px-3 font-semibold">{t('cm.pages_reservationdetail_PricingTabs.toplam')}</td><td className="py-2 px-3 text-right font-bold">{fmtTL(rates.reduce((s, r) => s + (parseDecimalInput(r.rate) || 0), 0))} TL</td></tr></tfoot>
        </table>
      </div>
    </div>;
}
export function ExtraChargesTab({
  extra_charges,
  charges,
  booking,
  onRefresh,
  allBookings
}) {
  const {
    t
  } = useTranslation();
  const [showAdd, setShowAdd] = useState(false);
  const [showSplit, setShowSplit] = useState(null);
  const [elDirection, setElDirection] = useState(null);
  const [form, setForm] = useState({
    description: '',
    category: 'other',
    amount: '',
    quantity: '1'
  });
  const [splitForm, setSplitForm] = useState({
    target_booking_id: '',
    split_amount: '',
    reason: ''
  });
  const [loading, setLoading] = useState(false);
  const allCharges = [...(extra_charges || []), ...(charges || [])].filter(c => !c.voided);
  const cats = {
    room_service: 'Oda Servisi',
    room: 'Oda',
    food: 'Yemek',
    beverage: 'İçecek',
    minibar: 'Minibar',
    spa: 'SPA',
    laundry: 'Çamaşır',
    parking: 'Otopark',
    telephone: 'Telefon',
    transfer: 'Transfer',
    other: 'Diğer'
  };
  const handleAdd = async () => {
    const amount = Number(form.amount);
    const quantity = Number(form.quantity);
    if (!form.description || !Number.isFinite(amount) || amount <= 0 || !Number.isFinite(quantity) || quantity <= 0) {
      toast.error('Açıklama ile sıfırdan büyük tutar ve adet zorunlu');
      return;
    }
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/add-extra-charge`, {
        ...form,
        amount,
        quantity
      });
      toast.success('Ekstra ücret eklendi');
      setShowAdd(false);
      setForm({
        description: '',
        category: 'other',
        amount: '',
        quantity: '1'
      });
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };
  const handleSplit = async chargeId => {
    if (!splitForm.split_amount || !splitForm.target_booking_id) {
      toast.error('Tutar ve hedef seçimi zorunlu');
      return;
    }
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/split-charge`, {
        charge_id: chargeId,
        target_booking_id: splitForm.target_booking_id,
        split_amount: parseFloat(splitForm.split_amount),
        reason: splitForm.reason
      });
      toast.success('Masraf bölündü');
      setShowSplit(null);
      setSplitForm({
        target_booking_id: '',
        split_amount: '',
        reason: ''
      });
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };
  return <div data-testid="extra-charges-tab" className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">{t('cm.pages_reservationdetail_PricingTabs.ek_ucretler')}</span>
        <div className="flex gap-1.5">
          <Button size="sm" variant="outline" onClick={() => setElDirection('early_checkin')} className="h-7 text-xs"><Clock className="w-3 h-3 mr-1" /> {t('cm.pages_reservationdetail_PricingTabs.erken_giris')}</Button>
          <Button size="sm" variant="outline" onClick={() => setElDirection('late_checkout')} className="h-7 text-xs"><Clock className="w-3 h-3 mr-1" /> {t('cm.pages_reservationdetail_PricingTabs.gec_cikis')}</Button>
          <Button size="sm" onClick={() => setShowAdd(!showAdd)} className="h-7 text-xs bg-amber-600 hover:bg-amber-700 text-white"><Plus className="w-3 h-3 mr-1" /> {t('cm.pages_reservationdetail_PricingTabs.ekle')}</Button>
        </div>
      </div>
      <EarlyLateChargeModal open={!!elDirection} onClose={() => setElDirection(null)} bookingId={booking?.id} direction={elDirection || 'early_checkin'} defaultHour={elDirection === 'late_checkout' ? 14 : 10} onApplied={onRefresh} />
      {showAdd && <div className="border rounded-lg p-4 bg-amber-50/50 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <FormField label={t('cm.pages_reservationdetail_PricingTabs.aciklama')} value={form.description} onChange={v => setForm(p => ({
          ...p,
          description: v
        }))} placeholder="Ornek: Minibar" />
            <SelectField label="Kategori" value={form.category} onChange={v => setForm(p => ({
          ...p,
          category: v
        }))} options={Object.entries(cats)} />
            <FormField label={t('cm.pages_reservationdetail_PricingTabs.tutar_tl')} type="number" value={form.amount} onChange={v => setForm(p => ({
          ...p,
          amount: v
        }))} />
            <FormField label="Adet" type="number" value={form.quantity} onChange={v => setForm(p => ({
          ...p,
          quantity: v
        }))} />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAdd} disabled={loading} className="bg-amber-600 hover:bg-amber-700 text-white h-8 text-xs">{loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Ekle'}</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)} className="h-8 text-xs">{t('cm.pages_reservationdetail_PricingTabs.iptal')}</Button>
          </div>
        </div>}
      <div className="space-y-2">
        {allCharges.length === 0 ? <div className="text-center py-6 text-gray-400 text-sm">{t('cm.pages_reservationdetail_PricingTabs.ek_ucret_bulunmuyor')}</div> : allCharges.map((c, i) => <div key={c.id || i} className="border rounded-lg p-3 relative">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center"><Receipt className="w-4 h-4 text-amber-600" /></div>
                <div className="flex-1">
                  <div className="text-sm font-medium">{c.description || c.charge_name || '-'}</div>
                  <div className="text-xs text-gray-400">{cats[c.category || c.charge_category] || ''} {c.split_from_booking_id && <span className="text-blue-500">{t('cm.pages_reservationdetail_PricingTabs.aktarildi')}</span>}</div>
                </div>
                <div className="text-sm font-bold text-amber-700">{fmtTL(c.total ?? c.charge_amount ?? c.amount)} TL</div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowSplit(showSplit === c.id ? null : c.id)}
                  className="h-7 px-2 text-xs text-blue-600"
                  aria-label={`${c.description || c.charge_name || 'Masraf'} masrafını böl`}
                  title="Masrafı böl"
                ><ArrowRightLeft className="w-3 h-3" /></Button>
              </div>
              {showSplit === c.id && <div className="mt-3 border-t pt-3 space-y-2">
                  <div className="text-xs font-semibold text-gray-700">{t('cm.pages_reservationdetail_PricingTabs.masraf_bol')}</div>
                  <div className="grid grid-cols-3 gap-2">
                    <FormField label={t('cm.pages_reservationdetail_PricingTabs.tutar')} type="number" value={splitForm.split_amount} onChange={v => setSplitForm(p => ({
              ...p,
              split_amount: v
            }))} />
                    <SelectField label={t('cm.pages_reservationdetail_PricingTabs.hedef_oda')} value={splitForm.target_booking_id} onChange={v => setSplitForm(p => ({
              ...p,
              target_booking_id: v
            }))} options={[['', 'Seçiniz...'], ...(allBookings || []).filter(b => b.id !== booking.id).map(b => [b.id, `${b.room_number || ''} - ${b.guest_name || b.id?.slice(0, 8)}`])]} />
                    <div className="flex items-end">
                      <Button size="sm" onClick={() => handleSplit(c.id)} disabled={loading} className="w-full h-8 text-xs bg-blue-600">{t('cm.pages_reservationdetail_PricingTabs.bol')}</Button>
                    </div>
                  </div>
                </div>}
            </div>)}
      </div>
    </div>;
}
