import React, { useEffect, useState } from 'react';
import axios from 'axios';

export function newSalaryAgreement() {
  return {
    unit: 'monthly', basis: 'gross', amount: '',
    period_month: new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Istanbul' }).slice(0, 7),
    opening_tax_base: '', opening_exemption_base: '',
    minimum_wage_exemption: true, insurance_days: 30, paid_hours: '',
    source_note: '', standard_4a_confirmed: false,
  };
}

const fmt = value => Number(value).toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' });
export default function SalaryAgreementFields({ value, onChange }) {
  const [state, setState] = useState(null);
  const key = JSON.stringify(value);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const a = JSON.parse(key);
    const ready = a && ['amount', 'period_month', 'opening_tax_base', 'opening_exemption_base',
      'insurance_days', 'paid_hours', 'source_note'].every(k => a[k] !== '' && a[k] != null) && a.standard_4a_confirmed;
    if (!ready) return () => { active = false; };
    const timer = setTimeout(async () => {
      try {
        const { data } = await axios.post('/hr/salary/preview', a, { signal: controller.signal });
        if (active) setState({ key, data });
      } catch (error) {
        if (!active) return;
        const detail = error.response?.data?.detail;
        setState({ key, error: typeof detail === 'string' ? detail : 'Dönem, ücret ve matrah bilgilerini kontrol edin.' });
      }
    }, 350);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [key]);
  if (!value) return <div className="md:col-span-2 rounded border p-3 text-sm">
    <p>Eski saatlik kayıt: yaklaşık kesinti modeli. Gerçek matrah hesabı henüz tanımlı değil.</p>
    <button type="button" className="underline mt-2" onClick={() => onChange(newSalaryAgreement())}>
      Aylık / saatlik net-brüt ücret anlaşması tanımla
    </button>
  </div>;
  const set = (field, next) => onChange({ ...value, [field]: next });
  const input = (field, label, props = {}) => <label className="grid gap-1 text-xs" key={field}>
    {label}<input className="rounded border px-3 py-2 text-sm" required value={value[field]}
      onChange={e => set(field, e.target.value)} {...props} />
  </label>;
  const current = state?.key === key ? state : null;
  return <fieldset className="md:col-span-2 rounded border p-3 space-y-3">
    <legend className="text-sm font-semibold px-1">Ücret anlaşması · gerçek kümülatif matrah</legend>
    <div className="grid grid-cols-2 gap-3">
      <label className="grid gap-1 text-xs">Ücret dönemi
        <select className="border rounded p-2" value={value.unit} onChange={e => set('unit', e.target.value)}>
          <option value="monthly">Aylık</option><option value="hourly">Saatlik</option>
        </select>
      </label>
      <label className="grid gap-1 text-xs">Anlaşma türü
        <select className="border rounded p-2" value={value.basis} onChange={e => set('basis', e.target.value)}>
          <option value="gross">Brüt</option><option value="net">Net</option>
        </select>
      </label>
      {input('amount', `${value.unit === 'monthly' ? 'Aylık (30 gün)' : 'Saatlik'} ${value.basis === 'net' ? 'net' : 'brüt'} tutar (TRY)`, { type: 'number', min: '0.01', step: '0.01' })}
      {input('period_month', 'Hesaplama / matrah dönemi', { type: 'month', min: '2026-01', max: '2026-12' })}
      {input('insurance_days', 'SGK ve ücret günü (ücretsiz izin düşülmüş)', { type: 'number', min: 1, max: 30, step: 1 })}
      {input('paid_hours', 'Dönemin ücretli normal saati (mesai hariç)', { type: 'number', min: '0.01', max: 400, step: '0.01' })}
      {input('opening_tax_base', 'Dönem başı gerçek kümülatif GV matrahı', { type: 'number', min: 0, step: '0.01' })}
      {input('opening_exemption_base', 'Dönem başı kümülatif asgari ücret istisna matrahı', { type: 'number', min: 0, step: '0.01' })}
    </div>
    {input('source_note', 'Matrah kaynağı (ör. önceki ay bordro no / devir belgesi)', { maxLength: 300, minLength: 3 })}
    <label className="flex gap-2 text-xs"><input type="checkbox" checked={value.minimum_wage_exemption}
      onChange={e => set('minimum_wage_exemption', e.target.checked)} />Asgari ücret vergi istisnası bu işverende uygulanır</label>
    <label className="flex gap-2 text-xs"><input type="checkbox" required checked={value.standard_4a_confirmed}
      onChange={e => set('standard_4a_confirmed', e.target.checked)} />Standart özel sektör 4/a, 45 saat/hafta, emekli değil; özel indirim/istisna ve aynı ay başka ücret ödemesi yok. Matrah ve gün bilgilerini doğruladım.</label>
    <p className="text-xs text-slate-500">Boş matrah sıfır kabul edilmez. Sıfırsa açıkça 0 girin. Sonuç yalnız seçili dönem ve girilen matrah için geçerlidir; sonraki ay yeniden doğrulama gerekir. Ek mesai/prim bu önizlemeye dahil değildir. SGDP, engellilik indirimi, BES ve özel yardım istisnaları kapsam dışıdır.</p>
    <div aria-live="polite" className="rounded bg-slate-50 p-3 text-sm">
      {current?.data ? <>
        <p>Hesaplanan dönem brütü: <strong>{fmt(current.data.gross_pay)}</strong></p>
        <p>Hesaplanan dönem neti: <strong>{fmt(current.data.net_salary)}</strong></p>
        <p className="text-xs mt-1">SGK: {fmt(current.data.sgk_employee)} · İşsizlik: {fmt(current.data.unemployment)} · GV: {fmt(current.data.income_tax)} · Damga: {fmt(current.data.stamp_tax)}</p>
        <p className="text-xs">Dönem sonu GV matrahı: {fmt(current.data.tax_calculation.closing_tax_base)}</p>
        <p className="text-xs">İşveren SGK: {fmt(current.data.sgk_employer)} · İşveren işsizlik: {fmt(current.data.unemployment_employer)} · İşveren maliyeti: {fmt(current.data.employer_cost)}</p>
        <p className="text-xs">İşveren hesabı teşviksiz standart 4/a (%21,75 + %2). Teşvik ve özel rejimler uygulanmaz.</p>
      </> : current?.error ? <p role="alert" className="text-rose-700">{current.error}</p> : 'Zorunlu bilgileri doldurun; net/brüt karşılığı otomatik hesaplanır.'}
    </div>
  </fieldset>;
}
