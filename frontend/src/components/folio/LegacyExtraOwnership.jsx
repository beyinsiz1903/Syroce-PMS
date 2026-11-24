import { useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/currency';

const code = value => String(value || 'TRY').toUpperCase().replace(/^TL$/, 'TRY');
const total = row => Number(row.total ?? row.charge_amount ?? row.amount ?? 0);

export default function LegacyExtraOwnership({ bookingId, folios, extras, currency, readOnly, onChanged }) {
  const [selected, setSelected] = useState([]);
  const [target, setTarget] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const attempt = useRef(null);
  const rows = (extras || []).filter(r => r.id && !r.folio_id && !r.voided && !r.invoice_id
    && Number.isFinite(total(r)) && total(r) >= 0 && code(r.currency || currency) === code(currency));
  if ((folios || []).length < 2 || !rows.length) return null;
  const amount = rows.filter(r => selected.includes(r.id)).reduce((sum, r) => sum + Math.round(total(r) * 100), 0) / 100;
  const valid = selected.length > 0 && target && reason.trim().length >= 3;
  const submit = async () => {
    if (!valid || readOnly || saving) return;
    const payload = { booking_id: bookingId, target_folio_id: target, extra_ids: selected.slice().sort(),
      expected_total: amount, currency: code(currency), reason: reason.trim() };
    const fingerprint = JSON.stringify(payload);
    if (attempt.current?.fingerprint !== fingerprint) attempt.current = { fingerprint, id: crypto.randomUUID() };
    setSaving(true); setError('');
    try {
      await axios.post('/folio-windows/assign-legacy-extras', { ...payload, request_id: attempt.current.id });
      setSelected([]); setReason(''); attempt.current = null;
      await onChanged?.();
    } catch (e) {
      setError(e.response?.data?.detail || 'Hesap seçimi kaydedilemedi. Yenileyip tekrar deneyin.');
    } finally { setSaving(false); }
  };
  return <section className="rounded-md border border-amber-200 bg-amber-50 p-3 space-y-3" aria-label="Hesabı belirlenmemiş ek ücretler">
    <h4 className="font-medium text-amber-900">Hesabı belirlenmemiş ek ücretler</h4>
    <p className="text-sm text-amber-900">Bu eski kalemler rezervasyon toplamında bulunuyor, ancak hangi hesaba ait oldukları belirtilmemiş. Kalemleri ve ait oldukları hesabı seçin. Yeni ücret veya ödeme oluşturulmaz.</p>
    {rows.map(r => <label key={r.id} className="flex gap-2 items-center text-sm text-gray-900">
      <input type="checkbox" disabled={readOnly || saving} checked={selected.includes(r.id)}
        onChange={e => setSelected(value => e.target.checked ? [...value, r.id] : value.filter(id => id !== r.id))} />
      {r.description || r.name || 'Ek ücret'}{r.service_date ? ` · ${r.service_date}` : ''} · {formatCurrency(total(r), code(currency))}
    </label>)}
    <label className="block text-sm text-gray-900">Ek ücretlerin hesabı
      <select aria-label="Ek ücretlerin hesabı" className="block w-full rounded border border-gray-300 bg-white p-2" value={target} disabled={readOnly || saving} onChange={e => setTarget(e.target.value)}>
        <option value="">Hesap seçin</option>
        {(folios || []).filter(f => f.status === 'open' && !f.invoice_id && code(f.currency || currency) === code(currency))
          .map(f => <option key={f.id} value={f.id}>{f.folio_number || f.id}</option>)}
      </select>
    </label>
    <label className="block text-sm text-gray-900">Hesap seçimi açıklaması
      <input aria-label="Hesap seçimi açıklaması" className="block w-full rounded border border-gray-300 bg-white p-2" value={reason} maxLength={500} disabled={readOnly || saving} onChange={e => setReason(e.target.value)} />
    </label>
    <p className="text-sm text-gray-900">Seçilen toplam: {formatCurrency(amount, code(currency))}</p>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <Button type="button" disabled={!valid || readOnly || saving} onClick={submit}>{saving ? 'Kaydediliyor…' : 'Seçilen ücretleri hesaba bağla'}</Button>
  </section>;
}
