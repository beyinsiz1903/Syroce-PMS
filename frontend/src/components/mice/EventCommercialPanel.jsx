import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { formatCurrency } from '@/lib/currency';
import { promptDialog } from '@/lib/dialogs';
import apiErrorText from '@/utils/apiErrorText';

const emptyActuals = { actual_pax: 0, guaranteed_pax: 0, budget_cost: 0, costs: [], costs_complete: false, notes: '' };
export default function EventCommercialPanel({ eventId, canManage, canFinance, canActuals, refreshKey, onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [actuals, setActuals] = useState(null);
  const [report, setReport] = useState(null);
  const requestKey = useRef(crypto.randomUUID());
  const load = async () => {
    const [event, versions] = await Promise.all([axios.get(`/mice/events/${eventId}`), axios.get(`/mice/events/${eventId}/documents`)]);
    setData({ event: event.data, ...versions.data }); setError('');
  };
  useEffect(() => {
    let current = true;
    Promise.all([axios.get(`/mice/events/${eventId}`), axios.get(`/mice/events/${eventId}/documents`)])
      .then(([event, versions]) => { if (current) setData({ event: event.data, ...versions.data }); })
      .catch(e => { if (current) setError(apiErrorText(e, 'Ayrıntılar yüklenemedi')); });
    return () => { current = false; };
  }, [eventId, refreshKey]);
  const action = async operation => {
    if (busy) return;
    setBusy(true);
    try { await operation(); await load(); }
    catch (e) { toast.error(apiErrorText(e, 'İşlem tamamlanamadı')); }
    finally { setBusy(false); }
  };
  const issue = async () => {
    const reason = await promptDialog({ title: 'BEO sürümü oluştur', message: 'Belge notu (en az 5 karakter)', defaultValue: 'Satış teklifi düzenlendi' });
    if (!reason) return;
    await action(async () => {
      await axios.post(`/mice/events/${eventId}/documents`, { reason, expected_revision: data.event.updated_at || data.event.created_at, client_request_id: requestKey.current });
      requestKey.current = crypto.randomUUID(); toast.success('Belge sürümü kaydedildi');
    });
  };
  const amend = async () => {
    const reason = await promptDialog({ title: 'Onaylı belgeyi revize et', message: 'Önceki belge ve onay arşivlenecek. Değişiklikten sonra müşteriden YENİ onay gerekir. Gerekçe (en az 10 karakter)' });
    if (!reason) return;
    await action(async () => {
      await axios.post(`/mice/events/${eventId}/amendment`, { reason, expected_revision: data.event.updated_at || data.event.created_at });
      await onChanged?.();
      toast.success('Revizyon açıldı. Etkinlik listesini yenileyip düzenleyin; ardından yeni onay isteyin.');
    });
  };
  const download = document => action(async () => {
    const response = await axios.get(`/mice/events/${eventId}/documents/${document.id}/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const anchor = window.document.createElement('a'); anchor.href = url; anchor.download = `beo-v${document.number}.pdf`;
    window.document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
  });
  const readActuals = async () => {
    const response = await axios.get(`/mice/events/${eventId}/actuals`);
    setActuals({ ...emptyActuals, ...response.data.actuals, expected_revision: response.data.expected_revision }); setReport(response.data);
  };
  const saveActuals = async () => action(async () => {
    await axios.put(`/mice/events/${eventId}/actuals`, actuals); await readActuals(); toast.success('Katılım ve maliyet kaydedildi');
  });
  if (error) return <div role="alert" className="rounded border p-3 text-sm">{error}<Button variant="outline" onClick={() => action(load)}>Tekrar dene</Button></div>;
  if (!data) return <p role="status">Belge sürümleri yükleniyor…</p>;
  return <section className="space-y-4 rounded-lg border p-3">
    <h3 className="font-semibold">Belge sürümleri ve etkinlik analizi</h3>
    <p className="text-xs text-muted-foreground">Kayıtlı PDF değişmez. Müşteri onay bağlantısı oluşturulurken de ayrı sürüm kaydedilir. Normal PDF İndir / Yazdır güncel taslağı gösterir.</p>
    <div className="flex flex-wrap gap-2">
      {canManage && <Button size="sm" variant="outline" disabled={busy || Boolean(data.event.signature) || ['completed', 'cancelled'].includes(data.event.status)} onClick={issue}>BEO sürümü kaydet</Button>}
      {canManage && Boolean(data.event.signature) && <Button size="sm" variant="outline" disabled={busy || Boolean(data.event.gl_journal_entry_id)} onClick={amend}>Onaylı belgeye revizyon aç</Button>}
      {canFinance && canActuals && <Button size="sm" variant="outline" disabled={busy} onClick={() => action(readActuals)}>Katılım / maliyet analizi</Button>}
    </div>
    {!data.documents?.length && <p className="text-xs">Henüz kayıtlı belge sürümü yok.</p>}
    {data.documents?.map(document => <div key={document.id} className="flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-xs">
      <span>v{document.number} · {document.issued_at?.slice(0, 16)} · {document.reason}{document.signature ? ' · Önceki müşteri onayı arşivlendi' : ''}</span>
      <Button variant="outline" size="sm" disabled={busy} onClick={() => download(document)}>v{document.number} PDF</Button>
    </div>)}
    {actuals && <form onSubmit={e => { e.preventDefault(); saveActuals(); }} className="space-y-3 border-t pt-3">
      <p className="text-xs text-muted-foreground">{report?.notice}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        {[['actual_pax', 'Gerçek katılım'], ['guaranteed_pax', 'Garanti kişi (bilgi)'], ['budget_cost', 'Bütçe maliyeti (net)']].map(([key, label]) => <label key={key} className="text-xs">{label}<Input required type="number" min="0" step={key === 'budget_cost' ? '0.01' : '1'} value={actuals[key]} onChange={e => setActuals({ ...actuals, [key]: Number(e.target.value) })} /></label>)}
      </div>
      <p className="text-xs">Bu bilgiler satış fiyatını veya müşteri onayını değiştirmez. Eksik tüketim kalemleri kârı olduğundan yüksek gösterebilir.</p>
      {actuals.costs.map((line, index) => <div key={index} className="grid grid-cols-2 gap-2 rounded border p-2 sm:grid-cols-5">
        <label className="text-xs">Maliyet kalemi<Input required value={line.name} onChange={e => setActuals({ ...actuals, costs: actuals.costs.map((r, i) => i === index ? { ...r, name: e.target.value } : r) })} /></label>
        <label className="text-xs">Tür<select className="w-full rounded border p-2" value={line.category} onChange={e => setActuals({ ...actuals, costs: actuals.costs.map((r, i) => i === index ? { ...r, category: e.target.value } : r) })}>{[['food', 'Yiyecek'], ['beverage', 'İçecek'], ['staff', 'Personel'], ['equipment', 'Ekipman'], ['entertainment', 'Eğlence'], ['other', 'Diğer']].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        {['quantity', 'unit_cost'].map(key => <label key={key} className="text-xs">{key === 'quantity' ? 'Tüketim / saat / adet' : 'Birim net maliyet'}<Input required type="number" min="0" step="0.01" value={line[key]} onChange={e => setActuals({ ...actuals, costs: actuals.costs.map((r, i) => i === index ? { ...r, [key]: Number(e.target.value) } : r) })} /></label>)}
        <Button type="button" variant="ghost" onClick={() => setActuals({ ...actuals, costs: actuals.costs.filter((_, i) => i !== index) })}>Kalemi kaldır</Button>
      </div>)}
      <Button type="button" size="sm" variant="outline" disabled={actuals.costs.length >= 100} onClick={() => setActuals({ ...actuals, costs: [...actuals.costs, { name: '', category: 'food', quantity: 1, unit_cost: 0 }] })}>Maliyet kalemi ekle</Button>
      <label className="block text-xs">Analiz notu<Input maxLength={2000} value={actuals.notes} onChange={e => setActuals({ ...actuals, notes: e.target.value })} /></label>
      <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={actuals.costs_complete} onChange={e => setActuals({ ...actuals, costs_complete: e.target.checked })} />Tüm yiyecek, içecek, personel ve diğer maliyetleri girdim. Teklif bazlı katkıyı hesapla.</label>
      {report && <p className="text-sm">Vergisiz teklif: {formatCurrency(report.report.quoted_net_revenue, report.currency)} · Kayıtlı maliyet: {report.report.actual_cost == null ? 'Henüz girilmedi' : formatCurrency(report.report.actual_cost, report.currency)} · Teklif bazlı katkı: {report.report.quote_based_contribution == null ? 'Henüz hesaplanamaz' : formatCurrency(report.report.quote_based_contribution, report.currency)}</p>}
      <Button disabled={busy} type="submit">Katılım ve maliyeti kaydet</Button>
    </form>}
  </section>;
}
