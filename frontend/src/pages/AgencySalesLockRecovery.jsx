import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

export default function AgencySalesLockRecovery() {
  const [data, setData] = useState({ items: [], total: 0 });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState({});
  const [confirmed, setConfirmed] = useState({});

  const load = useCallback(async () => {
    setBusy(true); setError('');
    try { setData((await axios.get('/marketplace/v1/admin/sales-locks')).data); }
    catch (err) { setError(err.response?.data?.detail || 'Satış kilitleri alınamadı.'); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reconcile = async (item, resolution) => {
    const note = (reason[item.lock_id] || '').trim();
    if (!confirmed[item.lock_id] || note.length < 10) {
      setError('Yazıcının durduğunu onaylayın ve en az 10 karakterlik gerekçe girin.');
      return;
    }
    setBusy(true); setError('');
    try {
      await axios.post(`/marketplace/v1/admin/sales-locks/${encodeURIComponent(item.lock_id)}/reconcile`, {
        owner: item.owner, resolution, reason: note, writer_stopped_confirmed: true,
      });
      await load();
    } catch (err) { setError(err.response?.data?.detail || 'Kilit uzlaştırılamadı.'); setBusy(false); }
  };

  return <main className="p-6 space-y-4 max-w-7xl mx-auto">
    <Link to="/admin/agencies">Acente yönetimine dön</Link>
    <h1 className="text-2xl font-semibold">Takılı Acente Satış İşlemleri</h1>
    <p>Bu kilitler otomatik süre aşımıyla kaldırılmaz. Önce özgün yazıcının durduğunu, rezervasyon ve işlem kanıtlarını doğrulayın. Her serbest bırakma denetim kaydına yazılır.</p>
    <button disabled={busy} onClick={load}>Yenile</button>
    {error && <p role="alert">{error}</p>}
    <p role="status">{busy ? 'Yükleniyor…' : `${data.total} takılı satış kilidi`}</p>
    <div className="overflow-x-auto"><table className="w-full text-left">
      <thead><tr>{['Tesis / Acente', 'İşlem', 'Oluşan rezervasyon', 'İdempotency', 'Kurtarma'].map(x => <th className="p-2" key={x}>{x}</th>)}</tr></thead>
      <tbody>{data.items.map(item => <tr key={item.lock_id} className="border-t align-top">
        <td className="p-2">{item.tenant_id}<br />{item.agency_id}</td>
        <td className="p-2">{item.operation}<br /><small>{item.created_at ? new Date(item.created_at).toLocaleString('tr-TR') : '—'}</small>{item.proposal && <><br /><small>Teklif: {item.proposal.id} · {item.proposal.status}</small></>}</td>
        <td className="p-2">{item.booking ? `${item.booking.confirmation_code || item.booking.id} · ${item.booking.status}` : 'Bulunamadı'}</td>
        <td className="p-2">{item.idempotency?.status || 'Yok'}</td>
        <td className="p-2 min-w-[290px]"><textarea className="w-full border rounded p-1" rows="2" placeholder="Uzlaştırma gerekçesi" value={reason[item.lock_id] || ''} onChange={e => setReason({ ...reason, [item.lock_id]: e.target.value })} />
          <label className="block text-xs mt-1"><input type="checkbox" checked={!!confirmed[item.lock_id]} onChange={e => setConfirmed({ ...confirmed, [item.lock_id]: e.target.checked })} /> Özgün yazıcının durduğunu doğruladım.</label>
          <button disabled={busy || item.idempotency?.status === 'processing'} onClick={() => reconcile(item, item.booking ? 'booking_committed' : 'no_booking_committed')}>Kanıtla ve kilidi kaldır</button></td>
      </tr>)}</tbody>
    </table></div>
  </main>;
}
