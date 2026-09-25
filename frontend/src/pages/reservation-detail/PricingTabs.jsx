import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Pencil, Check, Loader2, Plus, Receipt, ArrowRightLeft, Clock, Lock, Gift, X } from 'lucide-react';
import { API, fmtDate, fmtCurrency, fmtTs, FormField, SelectField } from './helpers';
import EarlyLateChargeModal from '@/components/EarlyLateChargeModal';
import { useTranslation } from 'react-i18next';

const parseDecimalInput = value => {
  const normalized = String(value ?? '').trim();
  if (!/^\d+(?:[.,]\d+)?$/.test(normalized)) return Number.NaN;
  return Number(normalized.replace(',', '.'));
};

export const distributeTotalAcrossEditableRates = (rates, total, isLocked = () => false) => {
  const totalValue = parseDecimalInput(total);
  const editableIndexes = rates.map((rate, index) => isLocked(rate) ? -1 : index).filter(index => index >= 0);
  if (!Number.isFinite(totalValue) || totalValue <= 0 || editableIndexes.length === 0) return null;

  const targetCents = Math.round(totalValue * 100);
  const lockedCents = rates.reduce((sum, rate) => sum + (isLocked(rate) ? Math.round((parseDecimalInput(rate.rate) || 0) * 100) : 0), 0);
  const distributableCents = targetCents - lockedCents;
  if (distributableCents < editableIndexes.length) return null;

  const centsPerNight = Math.floor(distributableCents / editableIndexes.length);
  let remainder = distributableCents % editableIndexes.length;
  return rates.map((rate, index) => {
    if (!editableIndexes.includes(index)) return rate;
    const cents = centsPerNight + (remainder-- > 0 ? 1 : 0);
    return { ...rate, rate: (cents / 100).toFixed(2) };
  });
};

export const filterDailyRatesForStay = (dailyRates = [], booking = {}) => {
  const checkIn = String(booking?.check_in || '').slice(0, 10);
  const checkOut = String(booking?.check_out || '').slice(0, 10);
  if (!checkIn || !checkOut || checkOut <= checkIn) return dailyRates;
  return dailyRates.filter(rate => {
    const date = String(rate?.date || '').slice(0, 10);
    return date >= checkIn && date < checkOut;
  });
};

export function DailyRatesTab({
  dailyRates,
  booking,
  onRefresh,
  readOnly = false,
  businessDate,
  summary = {},
}) {
  const currency = booking?.currency || "TL";
  const {
    t
  } = useTranslation();
  const [editMode, setEditMode] = useState(false);
  const [rates, setRates] = useState([]);
  const [totalInput, setTotalInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [showCompForm, setShowCompForm] = useState(false);
  const [compReason, setCompReason] = useState('');
  const [compScope, setCompScope] = useState('accommodation_only');
  const bookingCheckIn = booking?.check_in;
  const bookingCheckOut = booking?.check_out;
  const stayRange = { check_in: bookingCheckIn, check_out: bookingCheckOut };
  const applicableDailyRates = filterDailyRatesForStay(dailyRates, stayRange);
  useEffect(() => {
    const stayRates = filterDailyRatesForStay(dailyRates, {
      check_in: bookingCheckIn,
      check_out: bookingCheckOut,
    });
    setRates(stayRates);
    setTotalInput(stayRates.reduce((sum, rate) => sum + (parseDecimalInput(rate.rate) || 0), 0).toFixed(2));
  }, [dailyRates, bookingCheckIn, bookingCheckOut]);
  const normalizedBusinessDate = String(businessDate || '').slice(0, 10);
  const isClosedRate = rate => Boolean(normalizedBusinessDate && String(rate?.date || '').slice(0, 10) < normalizedBusinessDate);
  const anyEditable = rates.some(rate => !isClosedRate(rate));
  const hasClosedRates = rates.some(isClosedRate);
  const isComplimentary = Boolean(booking?.is_complimentary);
  const hasComplimentaryTotalDrift = isComplimentary && Number(booking?.total_amount || 0) > 0;
  const ratesTotal = rates.reduce((sum, rate) => sum + (parseDecimalInput(rate.rate) || 0), 0);
  const originalTotal = applicableDailyRates.reduce((sum, rate) => sum + (parseDecimalInput(rate.rate) || 0), 0);
  const paidTotal = Number(summary?.total_payments ?? summary?.paid_amount ?? summary?.prepayment_total ?? booking?.paid_amount ?? 0) || 0;
  const remainingAfterChange = Math.max(0, ratesTotal - paidTotal);
  const beginEditing = () => {
    setSaveError('');
    setTotalInput(ratesTotal.toFixed(2));
    setEditMode(true);
  };
  const cancelEditing = () => {
    setRates(applicableDailyRates);
    setTotalInput(originalTotal.toFixed(2));
    setSaveError('');
    setEditMode(false);
  };
  const handleTotalChange = event => {
    const value = event.target.value;
    setTotalInput(value);
    const distributed = distributeTotalAcrossEditableRates(rates, value, isClosedRate);
    if (distributed) setRates(distributed);
  };
  const handleReconcileComplimentaryTotal = async () => {
    setSaving(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/reconcile-complimentary-total`);
      toast.success('Comp konaklama tutarı düzeltildi');
      onRefresh?.();
    } catch (e) {
      toast.error('Düzeltme yapılamadı: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };
  const handleSave = async () => {
    setSaveError('');
    const requestedTotal = parseDecimalInput(totalInput);
    if (!Number.isFinite(requestedTotal) || Math.round(requestedTotal * 100) !== Math.round(ratesTotal * 100)) {
      const message = 'Toplam tutar açık gecelere dağıtılamadı; kapalı gecelerin toplamından büyük bir tutar girin';
      setSaveError(message);
      toast.error(message);
      return;
    }
    if (rates.some(rate => !Number.isFinite(parseDecimalInput(rate.rate)) || parseDecimalInput(rate.rate) <= 0)) {
      setSaveError('Günlük fiyat sıfırdan büyük olmalıdır');
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
      const detail = e.response?.status === 404
        ? 'Günlük fiyat güncelleme servisi bulunamadı. Uygulamanın backend sürümü güncel olmayabilir.'
        : (e.response?.data?.detail || e.message);
      setSaveError(detail);
      toast.error('İşlem Hatası: ' + detail);
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
      await axios.post(`/pms/reservations/${booking.id}/mark-complimentary`, { reason, scope: compScope });
      toast.success(compScope === 'full' ? 'Rezervasyon tamamen ikram olarak kaydedildi' : 'Konaklama ikram olarak kaydedildi');
      setShowCompForm(false);
      setCompReason('');
      onRefresh?.();
    } catch (e) {
      toast.error('İşlem Hatası: ' + (e.response?.data?.detail || e.message));
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
          {editMode && <Button size="sm" variant="ghost" onClick={cancelEditing} disabled={saving} className="h-7 text-xs">Vazgeç</Button>}
          <Button size="sm" variant="outline" onClick={() => editMode ? handleSave() : beginEditing()} disabled={saving || readOnly || !anyEditable || isComplimentary} className="h-7 text-xs" title={isComplimentary ? 'Comp rezervasyonun günlük fiyatları değiştirilemez' : readOnly ? 'Geçmiş rezervasyonlar salt okunurdur' : !anyEditable ? 'Night Audit ile kapanmış günlerin fiyatı değiştirilemez' : undefined}>
            {saving ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : editMode ? <Check className="w-3 h-3 mr-1" /> : <Pencil className="w-3 h-3 mr-1" />}
            {editMode ? 'Kaydet' : 'Düzenle'}
          </Button>
        </div>
      </div>
      {isComplimentary && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" data-testid="complimentary-summary">
          <div className="flex items-center gap-1.5 font-medium"><Gift className="h-4 w-4" /> {booking?.complimentary_scope === 'full' ? 'Tam İkram' : 'Konaklama İkramı'}</div>
          {booking?.complimentary_reason && <p className="mt-0.5 text-xs text-emerald-800">Gerekçe: {booking.complimentary_reason}</p>}
          {booking?.complimentary_original_total > 0 && <p className="mt-0.5 text-xs text-emerald-800">Raporlanan konaklama değeri: {fmtCurrency(booking.complimentary_original_total, currency)}</p>}
        </div>}
      {hasComplimentaryTotalDrift && <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950" data-testid="complimentary-total-drift">
          <p>Comp konaklamada {fmtCurrency(booking.total_amount, currency)} tutar hatalı görünüyor. Tahakkuk, ödeme veya fatura yoksa güvenli düzeltme yapılabilir.</p>
          <Button type="button" size="sm" variant="outline" onClick={handleReconcileComplimentaryTotal} disabled={saving || readOnly} className="mt-2 border-amber-400 text-amber-950">Comp konaklama tutarını düzelt</Button>
        </div>}
      {showCompForm && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2" data-testid="complimentary-form">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-amber-950">Rezervasyonu comp yap</p>
              <p className="text-xs text-amber-800">Ödeme kaydı oluşmaz. Tahakkuk, ödeme veya fatura varsa finansal comp/indirim fişi gerekir.</p>
            </div>
            <Button type="button" variant="ghost" size="icon" className="h-6 w-6" aria-label="Comp formunu kapat" onClick={() => setShowCompForm(false)}><X className="h-4 w-4" /></Button>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-amber-950" htmlFor="complimentary-scope">Komp kapsamı</label>
              <select id="complimentary-scope" value={compScope} onChange={event => setCompScope(event.target.value)} disabled={saving} className="h-9 w-full rounded-md border border-amber-300 bg-white px-3 text-sm">
                <option value="accommodation_only">Sadece Konaklama</option>
                <option value="full">Tam İkram</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-amber-950" htmlFor="complimentary-reason">Komp gerekçesi</label>
              <Input id="complimentary-reason" value={compReason} onChange={event => setCompReason(event.target.value)} placeholder="Comp gerekçesi (zorunlu)" maxLength={500} disabled={saving} />
            </div>
          </div>
          <p className="text-xs text-amber-800">{compScope === 'full' ? 'Konaklama ve mevcut/sonraki ekstra hizmetler ikram olarak sıfırlanır.' : 'Konaklama ikramdır; ekstra hizmetler ücretli kalır.'}</p>
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setShowCompForm(false)} disabled={saving}>Vazgeç</Button>
            <Button type="button" size="sm" onClick={handleComplimentary} disabled={saving} className="bg-amber-600 hover:bg-amber-700">{saving && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Comp Olarak Kaydet</Button>
          </div>
        </div>}
      {readOnly && <p className="text-xs text-slate-500">Geçmiş veya tamamlanmış rezervasyonlarda fiyat değiştirilemez.</p>}
      {!readOnly && hasClosedRates && <p className="text-xs text-slate-500">Night Audit ile kapanan tarihler kilitlidir; yalnızca açık iş günü ve sonrası düzenlenebilir.</p>}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr><th className="text-left py-2 px-3 text-xs text-gray-500 font-medium">{t('cm.pages_reservationdetail_PricingTabs.tarih')}</th><th className="text-right py-2 px-3 text-xs text-gray-500 font-medium">Fiyat ({currency === 'TRY' ? 'TL' : currency})</th></tr></thead>
          <tbody>
            {rates.map((r, i) => <tr key={r.id || i} className="border-t">
                <td className="py-2 px-3 text-gray-700">{fmtDate(r.date)}</td>
                <td className="py-2 px-3 text-right">
                  {editMode && !isClosedRate(r) ? <Input aria-label={`${fmtDate(r.date)} gece fiyatı`} type="text" inputMode="decimal" value={r.rate} onChange={e => {
                const u = [...rates];
                u[i] = {
                  ...u[i],
                  rate: e.target.value
                };
                setRates(u);
                setTotalInput(u.reduce((sum, rate) => sum + (parseDecimalInput(rate.rate) || 0), 0).toFixed(2));
              }} className="h-7 text-sm text-right w-24 ml-auto" /> : <span className="inline-flex items-center justify-end gap-1.5 font-medium text-gray-800">{editMode && isClosedRate(r) && <><Lock className="h-3 w-3 text-slate-400" /><span className="sr-only">Gün sonu kapalı</span></>}{fmtCurrency(r.rate, currency)}</span>}
                </td>
              </tr>)}
          </tbody>
          <tfoot className="bg-gray-50 border-t-2"><tr><td className="py-2 px-3 font-semibold">{t('cm.pages_reservationdetail_PricingTabs.toplam')}</td><td className="py-2 px-3 text-right font-bold">{editMode ? <Input aria-label="Toplam konaklama fiyatı" type="text" inputMode="decimal" value={totalInput} onChange={handleTotalChange} className="h-8 w-32 ml-auto text-right font-bold" /> : fmtCurrency(ratesTotal, currency)}</td></tr></tfoot>
        </table>
      </div>
      {editMode && <div className="grid grid-cols-3 gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs" data-testid="rate-change-summary">
        <div><span className="block text-slate-500">Yeni konaklama</span><strong className="text-slate-900">{fmtCurrency(ratesTotal, currency)}</strong>{Math.round(originalTotal * 100) !== Math.round(ratesTotal * 100) && <span className="mt-0.5 block text-amber-700">Önceki: {fmtCurrency(originalTotal, currency)}</span>}</div>
        <div><span className="block text-slate-500">Tahsil edilen</span><strong className="text-emerald-700">{fmtCurrency(paidTotal, currency)}</strong></div>
        <div><span className="block text-slate-500">Kaydetme sonrası kalan</span><strong className={remainingAfterChange > 0.01 ? 'text-rose-700' : 'text-emerald-700'}>{fmtCurrency(remainingAfterChange, currency)}</strong></div>
      </div>}
      {saveError && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{saveError}</div>}
      {editMode && <p className="text-xs text-slate-500">Toplam tutar değiştirildiğinde açık gecelere kuruş farkı bırakmadan eşit dağıtılır. Night Audit ile kapanan geceler korunur.</p>}
    </div>;
}
export function ExtraChargesTab({
  extra_charges,
  charges,
  booking,
  onRefresh,
  allBookings,
  readOnly = false,
}) {
  const currency = booking?.currency || "TL";
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
  const [formError, setFormError] = useState('');
  const isFullComp = booking?.is_complimentary && booking?.complimentary_scope === 'full';
  const lifecycleStatus = String(booking?.status || '').toLowerCase();
  const canAddEarlyCheckin = ['pending', 'confirmed', 'guaranteed'].includes(lifecycleStatus);
  const canAddLateCheckout = ['checked_in', 'in_house'].includes(lifecycleStatus);
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
    if (!form.description.trim() || !Number.isFinite(amount) || amount < 0 || !Number.isFinite(quantity) || quantity <= 0) {
      const message = 'Açıklama, sıfır veya üzeri tutar ve sıfırdan büyük adet zorunlu';
      setFormError(message);
      toast.error(message);
      return;
    }
    setFormError('');
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${booking.id}/add-extra-charge`, {
        ...form,
        amount,
        quantity
      });
      toast.success(amount === 0 || isFullComp ? 'Komp / ikram kaydı eklendi' : 'Ekstra ücret eklendi');
      setShowAdd(false);
      setForm({
        description: '',
        category: 'other',
        amount: '',
        quantity: '1'
      });
      onRefresh?.();
    } catch (e) {
      const message = 'İşlem Hatası: ' + (e.response?.data?.detail || e.message);
      setFormError(message);
      toast.error(message);
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
      toast.error('İşlem Hatası: ' + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };
  return <div data-testid="extra-charges-tab" className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700">{t('cm.pages_reservationdetail_PricingTabs.ek_ucretler')}</span>
        <div className="flex gap-1.5">
          {!readOnly && <>
            {canAddEarlyCheckin && <Button size="sm" variant="outline" onClick={() => setElDirection('early_checkin')} className="h-7 text-xs"><Clock className="w-3 h-3 mr-1" /> {t('cm.pages_reservationdetail_PricingTabs.erken_giris')}</Button>}
            {canAddLateCheckout && <Button size="sm" variant="outline" onClick={() => setElDirection('late_checkout')} className="h-7 text-xs"><Clock className="w-3 h-3 mr-1" /> {t('cm.pages_reservationdetail_PricingTabs.gec_cikis')}</Button>}
            <Button size="sm" onClick={() => setShowAdd(!showAdd)} className="h-7 text-xs bg-amber-600 hover:bg-amber-700 text-white"><Plus className="w-3 h-3 mr-1" /> {t('cm.pages_reservationdetail_PricingTabs.ekle')}</Button>
          </>}
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
          <p className="text-xs text-amber-800">{isFullComp ? 'Tam ikram kapsamında girdiğiniz tutar yalnızca ikram değeri olarak saklanır; bakiyeye 0 TL yansır.' : '0 TL girilen kalemler bakiyeyi etkilemeden ikram olarak kaydedilir.'}</p>
          {formError && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{formError}</div>}
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
                  <div className="text-xs text-gray-400">{cats[c.category || c.charge_category] || ''} {c.is_complimentary && <span className="font-medium text-emerald-600">Komp / İkram</span>} {c.complimentary_original_amount > 0 && <span className="text-slate-500">Liste değeri: {fmtCurrency(c.complimentary_original_amount, currency)}</span>} {c.split_from_booking_id && <span className="text-blue-500">{t('cm.pages_reservationdetail_PricingTabs.aktarildi')}</span>}</div>
                </div>
                <div className="text-sm font-bold text-amber-700">{fmtCurrency(c.total ?? c.charge_amount ?? c.amount, currency)}</div>
                {!readOnly && !c.is_complimentary && <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowSplit(showSplit === c.id ? null : c.id)}
                  className="h-7 px-2 text-xs text-blue-600"
                  aria-label={`${c.description || c.charge_name || 'Masraf'} masrafını böl`}
                  title="Masrafı böl"
                ><ArrowRightLeft className="w-3 h-3" /></Button>}
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
