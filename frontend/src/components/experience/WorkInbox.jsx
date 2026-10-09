import { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import ProductState from '@/components/shared/ProductState';
import { normalizeWorkItems } from '@/lib/productExperience';

export default function WorkInbox({ items, scope, onOpenSource }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [sources, setSources] = useState({});
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('all');
  const [updatedAt, setUpdatedAt] = useState(null);
  const keys = items.map(item => item.key).sort().join(',');
  useEffect(() => {
    const allowed = new Set(keys.split(','));
    const requests = [];
    if (allowed.has('tasks_workspace')) requests.push(['tasks', '/pms/staff-tasks', { page_size: 100 }]);
    if (allowed.has('shift_handover')) requests.push(['handover', '/pms/shift-handover', { status: 'unresolved', limit: 100 }]);
    if (allowed.has('pms')) requests.push(['alerts', '/pms/operational-alerts', {}]);
    const controller = new AbortController();
    setLoading(true); setSources({}); setErrors([]);
    Promise.all(requests.map(async ([key, path, params]) => {
      try { const { data } = await axios.get(path, { params, signal: controller.signal }); return { key, data }; }
      catch { return { key, failed: true }; }
    })).then(results => {
      if (controller.signal.aborted) return;
      setSources(Object.fromEntries(results.filter(r => !r.failed).map(r => [r.key, r.data])));
      setErrors(results.filter(r => r.failed).map(r => r.key));
      setUpdatedAt(new Date()); setLoading(false);
    });
    return () => controller.abort();
  }, [keys, scope, refresh]);
  const paths = new Set(items.map(item => item.path));
  const rows = normalizeWorkItems(sources).filter(row => paths.has(row.path)).filter(row =>
    (source === 'all' || source === row.source) && `${row.title} ${row.owner || ''}`.toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr')));
  const truncated = (sources.tasks?.total > (sources.tasks?.tasks?.length || 0)) || sources.handover?.has_more;
  return <section className="space-y-4" aria-label={t('experience.inbox', 'İş takibi')}>
    <div className="flex flex-wrap items-center justify-between gap-2"><p className="max-w-xl text-sm text-muted-foreground">{t('experience.inboxHelp', 'Görevler, vardiya notları ve operasyon uyarıları. İşlemler kendi ekranlarında tamamlanır; yeni kayıt oluşturulmaz.')}</p><Button variant="outline" disabled={loading} onClick={() => setRefresh(v => v + 1)}>{t('common.refresh', 'Yenile')}</Button></div>
    <div className="flex flex-wrap gap-2"><Input className="min-w-0 flex-1" value={query} onChange={e => setQuery(e.target.value)} aria-label={t('experience.workSearch', 'İş veya sorumlu ara')} placeholder={t('experience.workSearch', 'İş veya sorumlu ara')} /><select className="rounded-md border bg-background p-2 text-sm" value={source} onChange={e => setSource(e.target.value)} aria-label={t('experience.source', 'Kaynak')}>{['all', 'tasks', 'handover', 'alerts'].map(key => <option key={key} value={key}>{t(`experience.sources.${key}`, key)}</option>)}</select></div>
    {errors.length > 0 && <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">{t('experience.partialError', 'Bazı kaynaklar yüklenemedi; liste eksik olabilir:')} {errors.map(key => t(`experience.sources.${key}`, key)).join(', ')}</div>}
    {truncated && <p role="status" className="text-sm text-muted-foreground">{t('experience.previewLimit', 'Bu liste bir önizlemedir. Tüm kayıtlar için kaynak ekranını açın.')}</p>}
    {loading ? <ProductState state="loading" compact /> : rows.length ? <ul className="space-y-2">{rows.map(row => <li key={row.key} className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs font-medium text-muted-foreground">{t(`experience.sources.${row.source}`, row.source)} · {t(`experience.workStatus.${row.status}`, { defaultValue: t('experience.workStatus.open', 'Açık') })}</span>{['high', 'urgent'].includes(row.priority) && <span className="rounded-full bg-amber-100 px-2 py-1 text-xs text-amber-950">{t('experience.priority', 'Öncelikli')}</span>}</div>
      <h3 className="mt-2 whitespace-pre-wrap break-words text-sm font-semibold">{row.title}</h3><p className="mt-1 text-xs text-muted-foreground">{t('experience.owner', 'Sorumlu')}: {row.owner || t('experience.unassigned', 'Atanmadı')}</p>
      {row.due && <p className="text-xs">{t('experience.due', 'Son tarih')}: {new Date(row.due).toLocaleDateString()}</p>}
      <Button variant="outline" size="sm" className="mt-3" onClick={() => { onOpenSource?.(); navigate(row.path); }}>{t('experience.openSource', 'Kaynak ekranını aç')}</Button>
    </li>)}</ul> : <ProductState state="empty" compact description={t('experience.inboxEmpty', 'Erişebildiğiniz ve yüklenen kaynaklarda bu filtrelere uygun açık iş yok.')} />}
    {updatedAt && <p className="text-xs text-muted-foreground">{t('experience.updated', 'Son yenileme')}: {updatedAt.toLocaleTimeString()}</p>}
  </section>;
}
