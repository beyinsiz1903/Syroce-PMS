import { useEffect, useState } from 'react';
import axios from 'axios';

export default function AgencyRatePolicy({ agencyId }) {
  const [contracts, setContracts] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    axios.get(`/agencies/${agencyId}/contracts`).then(({ data }) => {
      if (active) setContracts(data.contracts || []);
    }).catch(() => { if (active) setError('Sözleşmeler alınamadı.'); });
    return () => { active = false; };
  }, [agencyId]);
  const save = async (contract) => {
    setBusy(true); setError('');
    try {
      await axios.put(`/agencies/${agencyId}/contracts/${contract.id}/rate-policy`, {
        allow_base_rate_fallback: !!contract.allow_base_rate_fallback,
      });
    } catch (err) { setError(err.response?.data?.detail || 'Fiyat politikası kaydedilemedi.'); }
    finally { setBusy(false); }
  };
  return <section className="p-3 border rounded space-y-2">
    <h3>Sözleşme fiyat politikası</h3>
    <p className="text-sm">Varsayılan olarak yalnız acenteye paylaşılmış fiyatlar satılır. Aşağıdaki izin temel/takvim fiyatlarıyla satışı da açar.</p>
    {error && <p role="alert">{error}</p>}
    {!contracts.length && <p>Tanımlı sözleşme yok; temel fiyat izni kapalıdır.</p>}
    {contracts.map(contract => <div key={contract.id} className="flex gap-3 items-center">
      <label><input type="checkbox" disabled={busy} checked={!!contract.allow_base_rate_fallback}
        onChange={e => setContracts(rows => rows.map(row => row.id === contract.id ? { ...row, allow_base_rate_fallback: e.target.checked } : row))} />
        {contract.contract_name || contract.id} ({contract.start_date} – {contract.end_date}): temel fiyatla satışa izin ver</label>
      <button disabled={busy} onClick={() => save(contract)}>Kaydet</button>
    </div>)}
  </section>;
}
