import React, { useState } from 'react';
import axios from 'axios';

const fields = {
  wage_expense_code: 'Ücret gideri (ör. 770)',
  employer_expense_code: 'İşveren prim gideri (ör. 770 alt hesabı)',
  net_payable_code: 'Personele borç (ör. 335)',
  withholding_payable_code: 'Gelir / damga vergisi (ör. 360)',
  sgk_payable_code: 'SGK ve işsizlik borcu (ör. 361)',
  advance_receivable_code: 'Personel avans alacağı (ör. 196)',
  other_deductions_code: 'Diğer kesinti karşılığı',
};

export default function PayrollMapping() {
  const [mapping, setMapping] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const load = async () => {
    setBusy(true); setMessage('');
    try { setMapping((await axios.get('/payroll-gl/mapping')).data.mapping || {}); }
    catch { setMessage('Hesap eşlemesi alınamadı; muhasebe yetkinizi kontrol edin.'); }
    finally { setBusy(false); }
  };
  const save = async e => {
    e.preventDefault(); setBusy(true); setMessage('');
    try {
      const payload = Object.fromEntries(Object.keys(fields).map(k => [k, mapping[k]?.trim() || null]));
      await axios.put('/payroll-gl/mapping', payload);
      setMessage('Eşleme kaydedildi. Önceden oluşmuş fişler değişmedi.');
    } catch (err) { setMessage(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Eşleme kaydedilemedi; hesap planındaki kodları seçin.'); }
    finally { setBusy(false); }
  };
  return <section className="border-t p-5 space-y-3" aria-label="Bordro muhasebe hesap eşlemesi">
    <button type="button" disabled={busy} onClick={load}>Muhasebe Hesap Eşlemesini Aç</button>
    {mapping && <form onSubmit={save} className="grid md:grid-cols-2 gap-3">
      <p className="md:col-span-2 text-sm">Kodlar otelinizin hesap planında bulunmalı. SGK ve vergi ayrı hesaplara aktarılır. Avans/diğer kesinti hesabı yalnız ilgili kalem varsa zorunludur.</p>
      {Object.entries(fields).map(([key, label]) => <label key={key}>{label}<input className="border rounded p-2 w-full" aria-label={label} required={!['advance_receivable_code', 'other_deductions_code'].includes(key)} maxLength={40} value={mapping[key] || ''} onChange={e => setMapping({ ...mapping, [key]: e.target.value })} /></label>)}
      <button disabled={busy} type="submit">Hesap Eşlemesini Kaydet</button>
    </form>}
    {message && <p role="status">{message}</p>}
  </section>;
}
