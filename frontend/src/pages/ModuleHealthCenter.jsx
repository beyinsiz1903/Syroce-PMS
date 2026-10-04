import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Activity, AlertTriangle, CheckCircle2, CircleHelp, Clock3, PackageCheck, PlugZap, RefreshCw, Search, Settings2, XCircle } from 'lucide-react';

import ProductState from '@/components/shared/ProductState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { KpiCard } from '@/components/ui/kpi-card';
import { PageHeader } from '@/components/ui/page-header';
import { StatusBadge } from '@/components/ui/status-badge';

const STATUS_META = {
  healthy: { label: 'Üretimde sağlıklı', intent: 'success', Icon: CheckCircle2 },
  unknown: { label: 'Üretim kanıtı bekleniyor', intent: 'neutral', Icon: CircleHelp },
  setup_required: { label: 'Kurulum bekliyor', intent: 'warning', Icon: Settings2 },
  attention: { label: 'Dikkat gerekiyor', intent: 'warning', Icon: AlertTriangle },
  error: { label: 'Hata var', intent: 'danger', Icon: XCircle },
};

const LICENSE_META = {
  included: { label: 'Pakete dahil', intent: 'success' },
  licensed: { label: 'Lisanslı', intent: 'success' },
  expired: { label: 'Lisans süresi dolmuş', intent: 'danger' },
  not_licensed: { label: 'Lisans yok', intent: 'neutral' },
};

const INSTALLATION_META = {
  installed: { label: 'Etkin', intent: 'success' },
  not_installed: { label: 'Etkin değil', intent: 'neutral' },
};

const INTEGRATION_META = {
  configured: { label: 'Bağlantı yapılandırılmış', intent: 'success' },
  not_configured: { label: 'Bağlantı kurulmamış', intent: 'warning' },
  not_applicable: { label: 'Entegrasyon gerekmiyor', intent: 'neutral' },
};

function dateTime(value) {
  if (!value) return 'Kayıt yok';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Bilinmiyor';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.unknown;
}

function MetaBadge({ value, catalog, fallback }) {
  const meta = catalog[value] || { label: fallback || 'Bilinmiyor', intent: 'neutral' };
  return <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>;
}

export default function ModuleHealthCenter() {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get('/module-health');
      setSnapshot(response.data || null);
    } catch (requestError) {
      setError(requestError);
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const modules = useMemo(() => snapshot?.modules || [], [snapshot]);
  const summary = snapshot?.summary || {};
  const visibleModules = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('tr-TR');
    return modules.filter((module) => {
      if (filter !== 'all' && module.status !== filter) return false;
      return !needle || `${module.name} ${module.key}`.toLocaleLowerCase('tr-TR').includes(needle);
    });
  }, [filter, modules, query]);

  if (loading && !snapshot) {
    return <ProductState state="error" moduleName="Modül Sağlık Merkezi" title="Modül sağlık verisi yükleniyor" description="Lisans, kurulum, bağlantı ve kullanım kanıtları okunuyor." compact showDashboardLink={false} />;
  }

  if (error) {
    const forbidden = error?.response?.status === 401 || error?.response?.status === 403;
    return <ProductState state={forbidden ? "forbidden" : "error"} moduleName="Modül Sağlık Merkezi" onRetry={load} />;
  }

  return (
    <main className="mx-auto max-w-[1500px] space-y-5 p-4 md:p-6" data-testid="module-health-center">
      <PageHeader
        icon={Activity}
        title="Modül Sağlık Merkezi"
        subtitle="Lisans, kurulum, bağlantı, son kullanım, hata ve üretim kanıtını tesisiniz için tek ekranda görün."
        actions={<Button variant="outline" onClick={load} disabled={loading}><RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Yenile</Button>}
      />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Modül sağlık özeti">
        <KpiCard icon={PackageCheck} label="İzlenen modül" value={summary.total ?? modules.length} intent="default" />
        <KpiCard icon={CheckCircle2} label="Üretimde sağlıklı" value={summary.healthy ?? 0} intent="success" active={filter === 'healthy'} onClick={() => setFilter((current) => current === 'healthy' ? 'all' : 'healthy')} />
        <KpiCard icon={Settings2} label="Kurulum bekliyor" value={summary.setup_required ?? 0} intent="warning" active={filter === 'setup_required'} onClick={() => setFilter((current) => current === 'setup_required' ? 'all' : 'setup_required')} />
        <KpiCard icon={AlertTriangle} label="Dikkat" value={summary.attention ?? 0} intent="warning" active={filter === 'attention'} onClick={() => setFilter((current) => current === 'attention' ? 'all' : 'attention')} />
        <KpiCard icon={XCircle} label="Hata" value={summary.error ?? 0} intent="danger" active={filter === 'error'} onClick={() => setFilter((current) => current === 'error' ? 'all' : 'error')} />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><Input className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Modül veya anahtar ara" aria-label="Modül ara" /></div>
          <div className="flex flex-wrap gap-1" aria-label="Sağlık durumu filtresi">
            {[['all', 'Tümü'], ['healthy', 'Sağlıklı'], ['unknown', 'Kanıt bekliyor'], ['setup_required', 'Kurulum'], ['attention', 'Dikkat'], ['error', 'Hata']].map(([value, label]) => <Button key={value} size="sm" variant={filter === value ? 'default' : 'ghost'} onClick={() => setFilter(value)}>{label}</Button>)}
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">Son üretim kanıtı: {dateTime(snapshot?.generated_at)} · Telemetri penceresi: son {snapshot?.telemetry_window_days || 30} gün · Abonelik: {snapshot?.subscription?.plan || 'bilinmiyor'} ({snapshot?.subscription?.status || 'bilinmiyor'})</p>
      </section>

      {visibleModules.length === 0 ? (
        <ProductState state="empty" moduleName="Modül Sağlık Merkezi" compact showDashboardLink={false} />
      ) : (
        <section className="grid gap-3 lg:grid-cols-2" aria-label="Modül sağlık kayıtları">
          {visibleModules.map((module) => {
            const production = statusMeta(module.status);
            const ProductionIcon = production.Icon;
            return (
              <article key={module.key} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={`module-health-${module.key}`}>
                <div className="flex items-start justify-between gap-3">
                  <div><h2 className="text-base font-semibold text-slate-950">{module.name}</h2><p className="mt-0.5 font-mono text-xs text-slate-500">{module.key}</p></div>
                  <StatusBadge intent={production.intent} icon={ProductionIcon}>{production.label}</StatusBadge>
                </div>
                <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div><dt className="text-xs text-slate-500">Lisans</dt><dd className="mt-1"><MetaBadge value={module.license_status} catalog={LICENSE_META} /></dd></div>
                  <div><dt className="text-xs text-slate-500">Kurulum</dt><dd className="mt-1"><MetaBadge value={module.installation_status} catalog={INSTALLATION_META} /></dd></div>
                  <div><dt className="text-xs text-slate-500">Bağlantı</dt><dd className="mt-1"><MetaBadge value={module.integration_status} catalog={INTEGRATION_META} /></dd></div>
                  <div><dt className="flex items-center gap-1 text-xs text-slate-500"><Clock3 className="h-3.5 w-3.5" /> Son kullanım</dt><dd className="mt-1 text-sm font-medium text-slate-800">{dateTime(module.last_used_at)}</dd></div>
                </dl>
                <div className={`mt-4 rounded-lg border p-3 text-sm ${module.last_error ? 'border-rose-200 bg-rose-50 text-rose-900' : 'border-slate-100 bg-slate-50 text-slate-700'}`}>
                  <div className="flex items-center gap-1.5 font-medium"><PlugZap className="h-4 w-4" /> Son hata</div>
                  <p className="mt-1">{module.last_error || 'Son telemetri penceresinde hata kaydı yok.'}</p>
                  {module.last_error_at && <p className="mt-1 text-xs opacity-75">{dateTime(module.last_error_at)}</p>}
                </div>
              </article>
            );
          })}
        </section>
      )}
    </main>
  );
}
