import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, ArrowLeft, List } from 'lucide-react';
import { HOTEL_EVENT_TIME_ZONE_LABEL, formatHotelEventTimestamp, hotelEventDay } from '@/lib/hotelEventTime';

const PAGE_SIZE = 20;
const statuses = {
  completed: 'Tamamlandı', running: 'Çalışıyor', in_progress: 'Devam ediyor',
  failed: 'Başarısız', blocked: 'Engellendi', partial_recovery_required: 'Kurtarma gerekli',
  dry_run_completed: 'Simülasyon tamamlandı', rerun_superseded: 'Yerine yeni koşu işlendi',
  aborted: 'Durduruldu',
};
const count = value => Number.isInteger(value) && value >= 0 ? value : '—';
const scalarText = value => typeof value === 'string' && value.trim() ? value
  : typeof value === 'number' && Number.isFinite(value) ? String(value) : null;
// Older real runs store the actor as {id, email}, newer runs as a string.
// Render only display-safe fields, never the whole actor/auth object.
const actorText = run => scalarText(run.started_by_name) || scalarText(run.started_by?.name)
  || scalarText(run.started_by?.email) || scalarText(run.started_by?.id) || scalarText(run.started_by) || '—';
const getDateOffset = offsetDays => {
  const day = new Date(`${hotelEventDay()}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() + offsetDays);
  return day.toISOString().split('T')[0];
};

// Canonical execution runs, not legacy per-step logs. Never sum financial
// enrichment: simulations/re-runs share a day and currencies cannot be added.
export default function NightAuditLogs() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(() => ({ start_date: getDateOffset(-7), end_date: getDateOffset(0), status: 'all' }));
  const [runs, setRuns] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const requestVersion = useRef(0);

  const loadRuns = async (nextPage = 0) => {
    const version = ++requestVersion.current;
    setRuns([]); setTotal(0); setLoaded(false); setError(''); setExpandedId(null);
    if (filters.start_date && filters.end_date && filters.start_date > filters.end_date) {
      setLoading(false); setError('Başlangıç iş günü bitişten sonra olamaz.'); return;
    }
    setLoading(true);
    try {
      const params = { limit: PAGE_SIZE, skip: nextPage * PAGE_SIZE };
      if (filters.start_date) params.start_date = filters.start_date;
      if (filters.end_date) params.end_date = filters.end_date;
      if (filters.status !== 'all') params.status = filters.status;
      const { data } = await axios.get('/night-audit/runs', { params });
      if (version !== requestVersion.current) return;
      if (!Array.isArray(data?.runs) || !Number.isInteger(data.total) || data.total < data.runs.length
        || data.runs.some(run => !run?.id || !run.business_date)
        || new Set(data.runs.map(run => run.id)).size !== data.runs.length) throw new Error('Invalid run contract');
      setRuns(data.runs); setTotal(data.total); setPage(nextPage); setLoaded(true);
    } catch {
      if (version === requestVersion.current) setError('Gün sonu geçmişi yüklenemedi. Yenile ile tekrar deneyin.');
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  };

  useEffect(() => {
    loadRuns();
    return () => { requestVersion.current += 1; };
  // Filters are operator-applied, not a request on every keystroke.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changeFilter = (name, value) => {
    requestVersion.current += 1;
    setFilters(previous => ({ ...previous, [name]: value }));
    setRuns([]); setTotal(0); setPage(0); setLoaded(false); setLoading(false); setError(''); setExpandedId(null);
  };
  const pageCompleted = runs.filter(run => run.status === 'completed' && run.dry_run === false).length;
  const pageSimulations = runs.filter(run => run.dry_run === true).length;

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex items-start gap-3">
        <Button variant="outline" size="sm" onClick={() => navigate('/reports')} aria-label="Raporlara dön"><ArrowLeft className="w-4 h-4" /></Button>
        <div>
          <h1 className="text-xl md:text-2xl font-bold flex items-center gap-2"><List className="w-5 h-5 text-blue-600" />Gün Sonu Geçmişi</h1>
          <p className="text-sm text-gray-600">Gerçek gün sonları, simülasyonlar ve yeniden çalıştırmalar ayrı kayıtlar olarak gösterilir.</p>
          <p className="text-xs text-gray-500">İşlem zamanı: {HOTEL_EVENT_TIME_ZONE_LABEL}. Filtreler iş gününe uygulanır; işlem saati ayrı gösterilir.</p>
        </div>
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Filtreler</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="text-sm space-y-1"><span>Başlangıç iş günü</span><Input type="date" aria-label="Başlangıç iş günü" value={filters.start_date} onChange={event => changeFilter('start_date', event.target.value)} /></label>
            <label className="text-sm space-y-1"><span>Bitiş iş günü</span><Input type="date" aria-label="Bitiş iş günü" value={filters.end_date} onChange={event => changeFilter('end_date', event.target.value)} /></label>
            <label className="text-sm space-y-1"><span>Durum</span><select aria-label="Durum" className="h-10 w-full border rounded-md px-2" value={filters.status} onChange={event => changeFilter('status', event.target.value)}>
              <option value="all">Tümü</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => loadRuns(0)} disabled={loading}><RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />Yenile</Button>
            <Button size="sm" onClick={() => loadRuns(0)} disabled={loading}>Uygula</Button>
          </div>
        </CardContent>
      </Card>
      {error && <div role="alert" className="border border-red-200 rounded-lg p-3 text-sm text-red-700 bg-red-50">{error}</div>}
      {loaded && <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
        {[['Filtredeki toplam koşu', total], ['Bu sayfadaki gerçek tamamlanan', pageCompleted], ['Bu sayfadaki simülasyon', pageSimulations]].map(([label, value]) => (
          <Card key={label}><CardContent className="p-4"><p className="text-gray-500">{label}</p><p className="text-xl font-semibold">{value}</p></CardContent></Card>
        ))}
      </div>}
      <p className="text-xs text-gray-500">Mali tutarlar günlük gelir raporundan incelenir; aynı iş gününün simülasyon ve tekrarları burada gelir olarak toplanmaz.</p>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Gün sonu koşuları</CardTitle></CardHeader>
        <CardContent>
          {loading ? <p role="status" className="py-10 text-center text-gray-500">Yükleniyor…</p>
            : !error && !loaded ? <p className="py-10 text-center text-gray-500">Filtreleri uygulamak için Uygula düğmesine basın.</p>
              : !error && runs.length === 0 ? <p className="py-10 text-center text-gray-500">Bu filtrelerle kayıt bulunamadı.</p>
                : !error && <div className="overflow-x-auto"><table className="w-full text-xs md:text-sm">
                  <thead><tr className="border-b text-left text-gray-600">
                    {['İş günü', 'Başlangıç', 'Bitiş', 'Başlatan', 'Tür', 'Durum', 'İşlenen kayıt', 'Detay'].map(label => <th key={label} className="py-2 pr-3 whitespace-nowrap">{label}</th>)}
                  </tr></thead>
                  <tbody>{runs.map(run => <React.Fragment key={run.id}>
                    <tr className="border-b last:border-0">
                      <td className="py-2 pr-3 whitespace-nowrap">{run.business_date}</td>
                      <td className="py-2 pr-3 whitespace-nowrap" title={HOTEL_EVENT_TIME_ZONE_LABEL}>{formatHotelEventTimestamp(run.started_at || run.created_at)}</td>
                      <td className="py-2 pr-3 whitespace-nowrap" title={HOTEL_EVENT_TIME_ZONE_LABEL}>{formatHotelEventTimestamp(run.completed_at)}</td>
                      <td className="py-2 pr-3">{actorText(run)}</td>
                      <td className="py-2 pr-3 whitespace-nowrap">{run.dry_run === true ? 'Simülasyon' : run.dry_run === false ? 'Gerçek gün sonu' : 'Belirtilmemiş'}</td>
                      <td className="py-2 pr-3"><Badge variant="outline">{statuses[run.status] || run.status || 'Belirtilmemiş'}</Badge></td>
                      <td className="py-2 pr-3 text-right">{count(run.processed_count)}</td>
                      <td className="py-2 pr-3"><Button variant="ghost" size="sm" aria-expanded={expandedId === run.id} onClick={() => setExpandedId(expandedId === run.id ? null : run.id)}>{expandedId === run.id ? 'Kapat' : 'Detay'}</Button></td>
                    </tr>
                    {expandedId === run.id && <tr className="bg-gray-50 border-b"><td colSpan={8} className="p-3">
                      <dl className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                        {[['Koşu kimliği', run.id], ['Aşama', run.stage], ['Başlatma kaynağı', run.trigger_source], ['Gerekçe', run.reason],
                          ['Aday kayıt', count(run.candidate_count)], ['Atlanan kayıt', count(run.skipped_count)], ['Başarısız kayıt', count(run.failed_count)]].map(([label, value]) => (
                          <div key={label}><dt className="text-gray-500">{label}</dt><dd className="break-words">{scalarText(value) ?? '—'}</dd></div>
                        ))}
                      </dl>
                    </td></tr>}
                  </React.Fragment>)}</tbody>
                </table></div>}
          {loaded && <div className="flex flex-wrap items-center justify-between gap-2 mt-4 text-sm">
            <span>{total === 0 ? '0 / 0' : `${page * PAGE_SIZE + 1}–${page * PAGE_SIZE + runs.length} / ${total}`}</span>
            <div className="flex gap-2"><Button variant="outline" size="sm" disabled={loading || page === 0} onClick={() => loadRuns(page - 1)}>Önceki</Button>
              <Button variant="outline" size="sm" disabled={loading || (page + 1) * PAGE_SIZE >= total} onClick={() => loadRuns(page + 1)}>Sonraki</Button></div>
          </div>}
        </CardContent>
      </Card>
    </div>
  );
}
