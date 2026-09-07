import React, { useState } from 'react';
import axios from 'axios';

const labels = { bonus: 'Prim (brüte eklenir)', advance: 'Avans mahsubu (netten)', deduction: 'Diğer kesinti (netten)', meal: 'Yemek (eski kalem)', transport: 'Yol (eski kalem)' };
const fmt = n => n == null ? 'Hesaplanmamış' : Number(n).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function PayrollExtras({ run, onSaved, onDirty }) {
  const [extras, setExtras] = useState(run.extras || []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const locked = run.status !== 'draft';
  const change = next => { setExtras(next); onDirty?.(true); };
  const update = (index, field, value) => change(extras.map((x, i) => i === index ? { ...x, [field]: value } : x));
  const save = async event => {
    event.preventDefault();
    if (locked || busy) return;
    setBusy(true); setError('');
    try {
      await axios.put(`/hr/payroll/runs/${run.id}/extras`, { expected_updated_at: run.updated_at, extras: extras.map(x => ({ ...x, amount: Number(x.amount) })) });
      await onSaved(run.id);
      onDirty?.(false);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Kalemler kaydedilemedi; tutarları ve personeli kontrol edin.');
    } finally { setBusy(false); }
  };
  return <section className="p-5 border-t space-y-3" aria-label="Prim ve avans kalemleri">
    <h3 className="font-semibold">Prim / Avans / Kesinti</h3>
    <p className="text-sm">Prim brütü ve vergileri artırır. Avans yalnız netten mahsup edilir; bu işlem avans ödemesi yapmaz. Kesinleşen kalemler yalnız revizyonla değişir.</p>
    <form onSubmit={save} className="space-y-3">
      <fieldset disabled={busy || locked} className="space-y-3">
        {extras.map((extra, i) => <div key={i} className="grid md:grid-cols-5 gap-2">
          <label>Personel<select aria-label={`Kalem ${i + 1} personel`} required value={extra.staff_id} onChange={e => update(i, 'staff_id', e.target.value)} className="border rounded p-2 w-full">
            <option value="">Seçin</option>
            {(run.rows || []).map(r => <option key={r.staff_id} value={r.staff_id}>{r.staff_name || r.staff_id}</option>)}
          </select></label>
          <label>Tür<select aria-label={`Kalem ${i + 1} tür`} value={extra.kind} onChange={e => update(i, 'kind', e.target.value)} className="border rounded p-2 w-full">
            {Object.entries(labels).filter(([k]) => ['bonus', 'advance', 'deduction'].includes(k) || k === extra.kind).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
          <label>Tutar (TRY)<input aria-label={`Kalem ${i + 1} tutar`} type="number" required min="0.01" max="1000000" step="0.01" value={extra.amount} onChange={e => update(i, 'amount', e.target.value)} className="border rounded p-2 w-full" /></label>
          <label>Belge / açıklama<input aria-label={`Kalem ${i + 1} açıklama`} required maxLength={200} value={extra.note || ''} onChange={e => update(i, 'note', e.target.value)} className="border rounded p-2 w-full" /></label>
          <button type="button" onClick={() => change(extras.filter((_, index) => i !== index))}>Kalem {i + 1} sil</button>
        </div>)}
        {!locked && <button type="button" onClick={() => change([...extras, { staff_id: '', kind: 'bonus', amount: '', note: '' }])}>Kalem Ekle</button>}
      </fieldset>
      {!locked && <button disabled={busy} type="submit" className="border rounded px-4 py-2">{busy ? 'Hesaplanıyor...' : 'Kalemleri Kaydet ve Yeniden Hesapla'}</button>}
    </form>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    <p className="text-sm">İşveren primleri: {fmt(run.summary?.total_employer_contributions)} TL · Toplam işveren maliyeti: {fmt(run.summary?.total_employer_cost)} TL</p>
    <p className="text-xs">Standart 4/a: teşviksiz %21,75 işveren SGK + %2 işsizlik. Teşvik ve özel rejimler uygulanmaz. Eski bordrolarda işveren tutarı hesaplanmamış olabilir.</p>
  </section>;
}
