import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

const labels = { pending: 'Sırada', processing: 'İşleniyor', retry: 'Tekrar denenecek', waiting: 'Dağıtım bekleniyor', failed: 'Müdahale gerekli' };
export default function AgencyIntegrationRepairs() {
  const [data, setData] = useState({ items: [], total: 0 });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try { setData((await axios.get('/marketplace/v1/admin/integrations', { params: { offset, limit: 100 } })).data); }
    catch { setError('Liste alınamadı. Yetkinizi ve bağlantınızı kontrol edin.'); }
    finally { setBusy(false); }
  }, [offset]);
  useEffect(() => { load(); }, [load]);
  const retry = async (id) => {
    setBusy(true); setError('');
    try { await axios.post(`/marketplace/v1/admin/integrations/${encodeURIComponent(id)}/retry`); await load(); }
    catch { setError('Yeniden deneme başlatılamadı. Durum değişmiş olabilir; listeyi yenileyin.'); setBusy(false); }
  };
  return <main className="p-6 space-y-4">
    <Link to="/admin/agencies">Acente yönetimine dön</Link>
    <h1 className="text-2xl font-semibold">Entegrasyonu eksik acente rezervasyonları</h1>
    <p>Rezervasyon PMS’e kaydedilmiştir. Yeniden rezervasyon oluşturmayın. Eksik adımlar otomatik tekrar denenir; sekiz başarısız denemeden sonra müdahale gerekir.</p>
    <p>Bu takip, kalıcı tamamlama desteğiyle oluşturulan yeni rezervasyonları kapsar. Eski rezervasyonlar otomatik olarak onarılmış sayılmaz.</p>
    <p>Tamamlanma, yerel kayıtlar ve dağıtım sistemine aktarımı ifade eder; harici kanalın son teslim durumu ilgili kanal izleme ekranından ayrıca doğrulanır.</p>
    <button disabled={busy} onClick={load}>Yenile</button>
    {error && <p role="alert">{error}</p>}
    <p role="status">{busy ? 'Yükleniyor…' : `${data.total} eksik rezervasyon`}</p>
    <div className="overflow-x-auto"><table className="w-full text-left">
      <thead><tr>{['Rezervasyon', 'Tesis / Acente', 'Durum', 'Tamamlanan adımlar', 'Hata / Deneme', 'İşlem'].map(s => <th className="p-2" key={s}>{s}</th>)}</tr></thead>
      <tbody>{data.items.map(row => <tr key={row.id}>
        <td className="p-2">{row.confirmation_code || row.id}</td><td>{row.tenant_id} / {row.agency_id}</td>
        <td>{labels[row.integration.status] || row.integration.status}</td>
        <td>{(row.integration.done || []).join(', ') || 'Henüz yok'}</td>
        <td>{row.integration.last_error || '—'} / {row.integration.attempts || 0}</td>
        <td><button disabled={busy || !['failed', 'retry', 'waiting'].includes(row.integration.status)} onClick={() => retry(row.id)}>Eksik işlemleri tekrar dene</button></td>
      </tr>)}</tbody></table></div>
    <button disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Önceki</button>
    <button disabled={busy || offset + 100 >= data.total} onClick={() => setOffset(offset + 100)}>Sonraki</button>
  </main>;
}
