import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Stethoscope, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import apiErrorText from '@/utils/apiErrorText';

// Why is an agency not selling? One checklist per agency, problems first,
// each with the screen that fixes it; the next 30 nights on demand.

const LEVEL = {
  error: { icon: XCircle, tone: 'text-red-700 dark:text-red-300', badge: 'bg-red-100 text-red-800', label: 'Satış engelli' },
  warn: { icon: AlertTriangle, tone: 'text-amber-700 dark:text-amber-300', badge: 'bg-amber-100 text-amber-800', label: 'Dikkat' },
  ok: { icon: CheckCircle2, tone: 'text-emerald-700 dark:text-emerald-300', badge: 'bg-emerald-100 text-emerald-800', label: 'Hazır' },
};
const NIGHT = {
  ok: ['Satılabilir', 'bg-emerald-500'],
  no_rate: ['Fiyat paylaşılmamış', 'bg-red-500'],
  no_price: ['Fiyat tanımı uygun değil', 'bg-red-400'],
  restricted: ['Satış kısıtı', 'bg-amber-300'],
  no_availability: ['Kontenjan yok', 'bg-amber-500'],
  no_room: ['Uygun oda yok', 'bg-slate-500'],
  closed: ['Satışa kapalı', 'bg-slate-400'],
  no_contract: ['Sözleşme yok', 'bg-slate-300'],
};

function Nights({ agencyId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const check = async () => {
    setLoading(true);
    try {
      setData((await axios.get(`/marketplace/hotel/agency-readiness/${encodeURIComponent(agencyId)}/nights`, { params: { days: 30 } })).data);
    } catch (err) { toast.error(apiErrorText(err, 'Kontrol yapılamadı.')); }
    finally { setLoading(false); }
  };
  if (!data) {
    return <Button size="sm" variant="outline" onClick={check} disabled={loading} data-testid={`check-nights-${agencyId}`}>
      {loading ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Stethoscope size={14} className="mr-2" />}Önümüzdeki 30 geceyi kontrol et
    </Button>;
  }
  const problems = Object.entries(data.counts || {}).filter(([status]) => status !== 'ok');
  return (
    <div className="space-y-2" data-testid={`nights-${agencyId}`}>
      <div className="flex flex-wrap gap-1">
        {data.nights.map(night => <span key={night.date} title={`${night.date}: ${NIGHT[night.status]?.[0] || night.status}`}
          className={`h-5 w-5 rounded-sm ${NIGHT[night.status]?.[1] || 'bg-slate-300'}`} />)}
      </div>
      <div className="text-xs">
        <span className="text-emerald-700">{data.counts?.ok || 0} gece satılabilir</span>
        {problems.map(([status, count]) => {
          const action = data.actions?.[status];
          return <span key={status} className="ml-3">{NIGHT[status]?.[0] || status}: {count}
            {action && <Link to={action.path} className="ml-1 underline">{action.label}</Link>}</span>;
        })}
      </div>
    </div>
  );
}

export default function AgencyReadiness() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try { setData((await axios.get('/marketplace/hotel/agency-readiness')).data); }
    catch (err) { toast.error(apiErrorText(err, 'Satış durumu yüklenemedi.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const agencies = Array.isArray(data?.agencies) ? data.agencies : [];

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><Stethoscope size={22} /> Acente Satış Durumu</h1>
          <p className="text-sm text-slate-500">Acente neden satış yapamıyor? Hesap, davet, sözleşme, kredi, son {data?.search_window_days || 30} günün aramaları ve rezervasyonlar; her sorunun yanında çözüm ekranı.</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}><RefreshCw size={14} className="mr-2" />Yenile</Button>
      </div>
      {loading && !data ? <div className="py-10 text-center"><Loader2 className="mx-auto animate-spin" /></div>
        : agencies.length === 0 ? <p className="text-sm text-slate-400">Henüz acente sözleşmesi yok.</p>
          : agencies.map(agency => {
            const level = LEVEL[agency.status] || LEVEL.ok;
            return (
              <Card key={agency.agency_id} data-testid={`readiness-${agency.agency_id}`}>
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-base">{agency.agency_name || agency.agency_id}</CardTitle>
                    <Badge className={level.badge}>{level.label}</Badge>
                  </div>
                  <p className="text-xs text-slate-500">{agency.contract?.code} · {agency.searches_here} arama bu otelde · {agency.bookings} rezervasyon</p>
                </CardHeader>
                <CardContent className="space-y-3">
                  <ul className="space-y-1 text-sm">
                    {agency.checks.map(check => {
                      const item = LEVEL[check.level] || LEVEL.ok;
                      const Icon = item.icon;
                      return <li key={check.key} className="flex flex-wrap items-start gap-2">
                        <Icon size={16} className={`mt-0.5 shrink-0 ${item.tone}`} aria-label={item.label} />
                        <span className="flex-1">{check.message}</span>
                        {check.action && check.level !== 'ok' && <Link to={check.action.path} className="text-xs font-medium underline">{check.action.label}</Link>}
                      </li>;
                    })}
                  </ul>
                  {agency.contract?.status === 'approved' && <Nights agencyId={agency.agency_id} />}
                </CardContent>
              </Card>
            );
          })}
    </div>
  );
}
