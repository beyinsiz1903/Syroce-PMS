import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, RefreshCw, Save, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { formatCurrency } from '@/lib/currency';
import { followUpLocalInput, followUpTimestamp, SALES_STAGES } from '@/lib/moduleSalesRequests';
import { signalModuleSalesChanged } from '@/hooks/useModuleSalesInbox';

const PAGE_SIZE = 50;
const emailLabels = { sent: 'Gönderildi', failed: 'Gönderilemedi', pending: 'Sonucu bekleniyor', not_configured: 'Yapılandırılmamış' };
const makeDraft = row => ({ status: row.status || 'new', assignee: row.assignee || '', internal_note: row.internal_note || '', follow_up_at: followUpLocalInput(row.follow_up_at) });

export default function AdminModuleSalesRequests() {
  const [params] = useSearchParams();
  const deepLink = params.get('request') || '';
  const [filters, setFilters] = useState({ status: deepLink ? 'all' : 'open', search: deepLink, offset: 0 });
  const [search, setSearch] = useState(deepLink);
  const [result, setResult] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState('');
  const [saveError, setSaveError] = useState({});
  const requestId = useRef(0);
  const invalidate = useCallback(() => { ++requestId.current; }, []);

  useEffect(() => {
    setSearch(deepLink);
    const status = deepLink ? 'all' : 'open';
    setFilters(previous => previous.status === status && previous.search === deepLink && previous.offset === 0
      ? previous : { status, search: deepLink, offset: 0 });
  }, [deepLink]);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true); setError(''); setResult(null);
    try {
      const { data } = await axios.get('/module-store/admin/quote-requests', { params: {
        status_filter: filters.status, search: filters.search, limit: PAGE_SIZE, offset: filters.offset,
      } });
      if (id !== requestId.current) return;
      if (data.total > 0 && filters.offset >= data.total) {
        setFilters(previous => ({ ...previous, offset: Math.floor((data.total - 1) / PAGE_SIZE) * PAGE_SIZE }));
        return;
      }
      setResult(data);
      setDrafts(Object.fromEntries((data.requests || []).map(row => [row.id, makeDraft(row)])));
    } catch (failure) {
      if (id === requestId.current) setError(failure?.response?.data?.detail || 'Satış talepleri yüklenemedi. Liste boş kabul edilmedi; yeniden deneyin.');
    } finally { if (id === requestId.current) setLoading(false); }
  }, [filters]);

  useEffect(() => { void load(); return invalidate; }, [load, invalidate]);

  const updateDraft = (id, field, value) => setDrafts(previous => ({ ...previous, [id]: { ...previous[id], [field]: value } }));
  const save = async row => {
    const draft = drafts[row.id];
    setSaving(row.id); setSaveError(previous => ({ ...previous, [row.id]: '' }));
    try {
      await axios.patch(`/module-store/admin/quote-requests/${encodeURIComponent(row.id)}`, {
        status: draft.status, assignee: draft.assignee.trim() || null, internal_note: draft.internal_note.trim() || null,
        follow_up_at: draft.follow_up_at ? new Date(draft.follow_up_at).toISOString() : null,
      });
      toast.success('Teklif talebi güncellendi.');
      signalModuleSalesChanged();
      await load();
    } catch (failure) {
      setSaveError(previous => ({ ...previous, [row.id]: failure?.response?.data?.detail || 'Talep kaydedilemedi; değişiklikleriniz korunuyor.' }));
    } finally { setSaving(''); }
  };

  return <main className="mx-auto max-w-7xl space-y-5 p-4 md:p-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Süperadmin · Satış kuyruğu</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950">Satış ve modül talepleri</h1>
        <p className="mt-2 text-sm text-slate-600">Tüm tesislerden gelen teklif talepleri. Bildirimi okumak talebi kapatmaz; aşamayı Kaydet ile değiştirin.</p></div>
      <div className="flex gap-2"><Button variant="outline" asChild><Link to="/app/admin-hub"><ArrowLeft className="mr-2 h-4 w-4" />Yönetim merkezi</Link></Button>
        <Button variant="outline" onClick={load} disabled={loading || Boolean(saving)}><RefreshCw className="mr-2 h-4 w-4" />Yenile</Button></div>
    </header>
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {[['Açık talepler', result?.summary?.open], ['Yeni', result?.summary?.new], ['Teklif verildi', result?.summary?.quote_sent], ['Toplam', result?.summary?.total]].map(([label, count]) =>
        <div key={label} className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-sm text-slate-600">{label}</p><p className="mt-1 text-2xl font-bold text-slate-950">{count ?? '—'}</p></div>)}
    </div>
    <form className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4" onSubmit={event => { event.preventDefault(); setFilters(previous => ({ ...previous, search: search.trim(), offset: 0 })); }}>
      <label className="w-full text-sm text-slate-600 sm:min-w-60 sm:flex-1">Talep no, tesis, ürün veya e-posta<Input value={search} maxLength={200} onChange={event => setSearch(event.target.value)} disabled={Boolean(saving)} className="mt-1" /></label>
      <label className="text-sm text-slate-600">Aşama filtresi<select value={filters.status} disabled={Boolean(saving)} onChange={event => setFilters(previous => ({ ...previous, status: event.target.value, offset: 0 }))} className="mt-1 block h-10 rounded-md border border-input bg-transparent px-3"><option value="open">Açık talepler</option><option value="all">Tümü</option>{Object.entries(SALES_STAGES).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <Button type="submit" disabled={Boolean(saving)}><Search className="mr-2 h-4 w-4" />Ara</Button>
    </form>
    {loading && <p role="status" className="text-sm text-slate-600">Talepler yükleniyor…</p>}
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{String(error)} <Button variant="outline" size="sm" onClick={load}>Yeniden dene</Button></div>}
    {result && <>
      <p className="text-sm text-slate-600">{result.total} eşleşen talep · {result.total ? filters.offset + 1 : 0}–{filters.offset + (result.requests?.length || 0)} gösteriliyor</p>
      {!result.requests?.length && <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">Bu filtrede teklif talebi bulunamadı.</p>}
      <div className="space-y-4">{(result.requests || []).map(row => {
        const draft = drafts[row.id] || makeDraft(row);
        const followUp = followUpTimestamp(row.follow_up_at);
        const overdue = followUp && followUp.getTime() < Date.now() && !['won', 'lost'].includes(row.status);
        const email = row.user_email || row.tenant_email;
        return <article key={row.id} className="rounded-xl border border-slate-200 bg-white p-4 md:p-5" data-testid={`sales-request-${row.id}`}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="min-w-0 break-words"><h2 className="text-lg font-semibold text-slate-950">{row.product_name || row.product_key}</h2>
              <p className="text-sm text-slate-700">{row.tenant_name || row.tenant_id}</p>
              <p className="mt-1 break-all text-xs text-slate-500">Talep no: {row.id} · {row.created_at ? new Date(row.created_at).toLocaleString('tr-TR') : 'Tarih bilinmiyor'}</p>
              <p className="mt-2 break-words text-sm">{email ? <a href={`mailto:${email}`} className="break-all text-blue-700 underline">{email}</a> : 'E-posta belirtilmemiş'}{row.tenant_phone ? ` · ${row.tenant_phone}` : ''}</p>
              {row.note && <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">Müşteri notu: {row.note}</p>}
            </div>
            <div className="space-y-1 text-sm text-slate-600"><p>Aşama: <strong>{SALES_STAGES[row.status] || row.status}</strong></p>
              <p>Talep edilen adet: {row.quantity ?? 'Eski kayıtta belirtilmemiş'}</p>
              {row.price_snapshot?.total_try != null && <p>Talep anındaki tahmini toplam (KDV dahil): {formatCurrency(row.price_snapshot.total_try, 'TRY', { decimals: 2, compactDecimals: false })}</p>}
              <p>Satış e-postası: {emailLabels[row.delivery?.email] || 'Durum bilinmiyor'}. Talep bu kuyrukta kayıtlıdır.</p>
              {overdue && <p className="font-semibold text-red-600">Takip tarihi geçti</p>}
            </div>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-sm text-slate-600">Aşama<select aria-label={`Aşama ${row.id}`} className="mt-1 h-10 w-full rounded-md border border-input bg-transparent px-2" value={draft.status} disabled={Boolean(saving)} onChange={event => updateDraft(row.id, 'status', event.target.value)}>{Object.entries(SALES_STAGES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="text-sm text-slate-600">Sorumlu<Input aria-label={`Sorumlu ${row.id}`} className="mt-1" value={draft.assignee} maxLength={200} disabled={Boolean(saving)} onChange={event => updateDraft(row.id, 'assignee', event.target.value)} /></label>
            <label className="text-sm text-slate-600">Takip tarihi (yerel saat)<Input aria-label={`Takip tarihi ${row.id}`} type="datetime-local" className="mt-1" value={draft.follow_up_at} disabled={Boolean(saving)} onChange={event => updateDraft(row.id, 'follow_up_at', event.target.value)} /></label>
            <label className="text-sm text-slate-600">Yönetici notu<Input aria-label={`Yönetici notu ${row.id}`} className="mt-1" value={draft.internal_note} maxLength={1000} disabled={Boolean(saving)} onChange={event => updateDraft(row.id, 'internal_note', event.target.value)} /></label>
          </div>
          {saveError[row.id] && <p role="alert" className="mt-3 text-sm text-red-600">{String(saveError[row.id])}</p>}
          <Button className="mt-3" disabled={Boolean(saving)} onClick={() => save(row)}><Save className="mr-2 h-4 w-4" />{saving === row.id ? 'Kaydediliyor…' : 'Kaydet'}</Button>
        </article>;
      })}</div>
      <div className="flex justify-end gap-2"><Button variant="outline" disabled={loading || Boolean(saving) || filters.offset === 0} onClick={() => setFilters(previous => ({ ...previous, offset: Math.max(0, previous.offset - PAGE_SIZE) }))}>Önceki sayfa</Button>
        <Button variant="outline" disabled={loading || Boolean(saving) || !result.has_more} onClick={() => setFilters(previous => ({ ...previous, offset: previous.offset + PAGE_SIZE }))}>Sonraki sayfa</Button></div>
    </>}
  </main>;
}
