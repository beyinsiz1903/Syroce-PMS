import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import {
  Play, Pause, AlertTriangle, Loader2, RefreshCw, Brain,
} from 'lucide-react';
import { toast } from 'sonner';

const hdrs = () => ({
  Authorization: `Bearer ${localStorage.getItem('token')}`,
  'Content-Type': 'application/json',
});

async function safeFetch(path, init) {
  const res = await fetch(path, { ...(init || {}), headers: { ...hdrs(), ...(init?.headers || {}) } });
  let body = null;
  const ctype = res.headers.get('content-type') || '';
  if (ctype.includes('application/json')) {
    try { body = await res.json(); } catch { body = null; }
  }
  if (!res.ok) {
    const detail = (body && body.detail) || `HTTP ${res.status}`;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return body;
}

// Backend henüz bir "label/colors" listesi yayınlamıyor (issue #8). Bilinen üç
// model için gösterim eşlemesi; bilinmeyen tipler raw id ile gelir (graceful).
const MODEL_LABELS = {
  revenue_ml: 'Revenue ML',
  operational_ai: 'Operational AI',
  guest_intelligence: 'Guest Intelligence',
};

const STATUS_BADGE = {
  completed: 'bg-emerald-100 text-emerald-800',
  running: 'bg-sky-100 text-sky-800',
  failed: 'bg-rose-100 text-rose-800',
  pending: 'bg-amber-100 text-amber-800',
};

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_MS = 60000;

export default function MLSchedulerDashboard() {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [triggering, setTriggering] = useState({});
  const pollTimers = useRef({}); // model_type -> { timeoutId, deadline }

  const fetchDashboard = useCallback(async () => {
    try {
      const d = await safeFetch('/api/data-intelligence/schedules/dashboard');
      setDashboard(d || {});
      setError(null);
      return d || {};
    } catch (e) {
      const msg =
        e.status === 401 ? 'Oturum süresi doldu. Lütfen tekrar giriş yapın.'
        : e.status === 403 ? 'Yetki yok: Zamanlayıcı için izniniz yok.'
        : `Zamanlayıcı yüklenemedi: ${e.message}`;
      setError(msg);
      throw e;
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try { await fetchDashboard(); } catch { /* error state already set */ }
    finally { setLoading(false); }
  }, [fetchDashboard]);

  useEffect(() => {
    load();
    return () => {
      // Cleanup pending poll timers on unmount.
      Object.values(pollTimers.current).forEach((t) => t && clearTimeout(t.timeoutId));
      pollTimers.current = {};
    };
  }, [load]);

  // Bug #7: 2 sn'lik magic timeout yerine polling — son çalışma zamanı veya
  // status değişene kadar her POLL_INTERVAL_MS'de dashboard yenile, en geç
  // POLL_MAX_MS'de durdur (race condition / ML işi uzasa bile UI güncel kalır).
  const pollUntilUpdate = useCallback((modelType, baselineLastRun) => {
    // Mevcut bir poll varsa iptal et ki çift tetiklenmesin.
    const existing = pollTimers.current[modelType];
    if (existing) clearTimeout(existing.timeoutId);

    const deadline = Date.now() + POLL_MAX_MS;

    const tick = async () => {
      try {
        const d = await fetchDashboard();
        const sched = (d?.schedules || []).find((s) => s.model_type === modelType);
        const newLastRun = sched?.last_run_at || null;
        const recent = (d?.recent_executions || []).find((j) => j.model_type === modelType);
        const finished =
          (newLastRun && newLastRun !== baselineLastRun) ||
          (recent && (recent.status === 'completed' || recent.status === 'failed'));

        if (finished) {
          if (recent?.status === 'failed') toast.error(`${MODEL_LABELS[modelType] || modelType} çalışması başarısız.`);
          else toast.success(`${MODEL_LABELS[modelType] || modelType} çalışması tamamlandı.`);
          setTriggering((p) => ({ ...p, [modelType]: false }));
          delete pollTimers.current[modelType];
          return;
        }
        if (Date.now() >= deadline) {
          toast.warning(`${MODEL_LABELS[modelType] || modelType} hâlâ çalışıyor. Sonuç için Yenile'ye tıklayın.`);
          setTriggering((p) => ({ ...p, [modelType]: false }));
          delete pollTimers.current[modelType];
          return;
        }
        const id = setTimeout(tick, POLL_INTERVAL_MS);
        pollTimers.current[modelType] = { timeoutId: id, deadline };
      } catch {
        // Hata durumunda spinner'ı kapat ve poll'u bırak — fetchDashboard error state'i set eder.
        setTriggering((p) => ({ ...p, [modelType]: false }));
        delete pollTimers.current[modelType];
      }
    };

    const id = setTimeout(tick, POLL_INTERVAL_MS);
    pollTimers.current[modelType] = { timeoutId: id, deadline };
  }, [fetchDashboard]);

  const trigger = async (modelType) => {
    setTriggering((p) => ({ ...p, [modelType]: true }));
    const baseline = (dashboard?.schedules || []).find((s) => s.model_type === modelType)?.last_run_at || null;
    try {
      await safeFetch('/api/data-intelligence/schedules/trigger', {
        method: 'POST',
        body: JSON.stringify({ model_type: modelType }),
      });
      toast.message(`${MODEL_LABELS[modelType] || modelType} tetiklendi, sonuç bekleniyor…`);
      pollUntilUpdate(modelType, baseline);
    } catch (e) {
      const msg =
        e.status === 403 ? 'Bu modeli tetikleme yetkiniz yok.'
        : `Tetikleme başarısız: ${e.message}`;
      toast.error(msg);
      setTriggering((p) => ({ ...p, [modelType]: false }));
    }
  };

  const toggleSchedule = async (modelType, enabled) => {
    try {
      await safeFetch(`/api/data-intelligence/schedules/policies/${modelType}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled: !enabled }),
      });
      toast.success(enabled ? 'Zamanlayıcı durduruldu.' : 'Zamanlayıcı etkinleştirildi.');
      load();
    } catch (e) {
      toast.error(`Durum güncellenemedi: ${e.message}`);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (error && !dashboard) {
    return (
      <Card data-testid="ml-scheduler-error">
        <CardContent className="py-12 text-center space-y-3">
          <AlertTriangle className="h-10 w-10 text-amber-500 mx-auto" />
          <p className="text-sm text-slate-700">{error}</p>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4 mr-1.5" /> Yeniden Dene
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { schedules = [], recent_executions = [], stale_models = [] } = dashboard || {};

  return (
    <div data-testid="ml-scheduler-dashboard" className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-slate-900">{t('techDashboards.mlScheduler')}</h2>
          <p className="text-sm text-slate-500">Model çalıştırma zamanlaması, durum izleme ve anlık görüntü yönetimi.</p>
        </div>
        <Button data-testid="refresh-scheduler" variant="outline" size="sm" onClick={load}>
          <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
        </Button>
      </div>

      {stale_models.length > 0 && (
        <Card className="border-amber-500/30 bg-amber-50/50">
          <CardContent className="py-3 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <span className="text-sm font-medium text-amber-800">
              {stale_models.length} model güncel değil:{' '}
              {stale_models.map((s) => MODEL_LABELS[s.model_type] || s.model_type).join(', ')}
            </span>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {schedules.map((s) => (
          <Card key={s.id} data-testid={`schedule-card-${s.model_type}`}>
            <CardHeader className="pb-2">
              <div className="flex justify-between items-center">
                <CardTitle className="text-base text-slate-900">
                  {MODEL_LABELS[s.model_type] || s.model_type}
                </CardTitle>
                <Badge variant={s.enabled ? 'default' : 'secondary'}>
                  {s.enabled ? 'Aktif' : 'Devre Dışı'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-slate-500">Aralık:</span> <strong>{s.interval_hours}sa</strong></div>
                <div><span className="text-slate-500">Saklama:</span> <strong>{s.snapshot_retention_days}g</strong></div>
                <div className="col-span-2">
                  <span className="text-slate-500">Son çalışma:</span>{' '}
                  <strong>{s.last_run_at ? new Date(s.last_run_at).toLocaleString('tr-TR') : 'Hiç'}</strong>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  data-testid={`trigger-${s.model_type}`}
                  size="sm" className="flex-1"
                  disabled={!!triggering[s.model_type]}
                  onClick={() => trigger(s.model_type)}
                >
                  {triggering[s.model_type]
                    ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    : <Play className="h-4 w-4 mr-1" />}
                  {triggering[s.model_type] ? 'Çalışıyor…' : 'Çalıştır'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => toggleSchedule(s.model_type, s.enabled)}>
                  {s.enabled ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {schedules.length === 0 && (
          <Card><CardContent className="py-8 text-center text-sm text-slate-500">
            Tanımlı model zamanlaması yok.
          </CardContent></Card>
        )}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base text-slate-900">Son Çalışmalar</CardTitle></CardHeader>
        <CardContent>
          {recent_executions.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-4">Henüz çalışma yok.</p>
          ) : (
            <div className="space-y-2">
              {recent_executions.map((j) => (
                <div
                  key={j.id}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                  data-testid={`execution-${j.id}`}
                >
                  <div className="flex items-center gap-3">
                    <Brain className="h-4 w-4 text-slate-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-900">
                        {MODEL_LABELS[j.model_type] || j.model_type}
                      </p>
                      <p className="text-xs text-slate-500">
                        {new Date(j.created_at).toLocaleString('tr-TR')} · {j.triggered_by}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {j.duration_ms != null && (
                      <span className="text-xs text-slate-500">{j.duration_ms}ms</span>
                    )}
                    {j.confidence_avg != null && (
                      <span className="text-xs font-medium text-slate-700">
                        {(j.confidence_avg * 100).toFixed(0)}%
                      </span>
                    )}
                    <Badge className={STATUS_BADGE[j.status] || 'bg-slate-100 text-slate-700'}>
                      {j.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
