import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Play, Pause, Clock, CheckCircle2, XCircle, AlertTriangle,
  BarChart3, Loader2, RefreshCw, Timer, Zap, Brain,
} from 'lucide-react';

const API = "";
const hdrs = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });
const get = async (p) => (await fetch(`${API}${p}`, { headers: hdrs() })).json();
const post = async (p, b) => (await fetch(`${API}${p}`, { method: 'POST', headers: hdrs(), body: JSON.stringify(b) })).json();
const put = async (p, b) => (await fetch(`${API}${p}`, { method: 'PUT', headers: hdrs(), body: JSON.stringify(b) })).json();

const MODEL_LABELS = { revenue_ml: 'Revenue ML', operational_ai: 'Operational AI', guest_intelligence: 'Guest Intelligence' };
const MODEL_COLORS = { revenue_ml: 'blue', operational_ai: 'amber', guest_intelligence: 'purple' };
const STATUS_BADGE = {
  completed: 'bg-emerald-100 text-emerald-800',
  running: 'bg-blue-100 text-blue-800',
  failed: 'bg-red-100 text-red-800',
  pending: 'bg-amber-100 text-amber-800',
};

export default function MLSchedulerDashboard() {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    const d = await get('/api/data-intelligence/schedules/dashboard');
    setDashboard(d);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const trigger = async (modelType) => {
    setTriggering(p => ({ ...p, [modelType]: true }));
    await post('/api/data-intelligence/schedules/trigger', { model_type: modelType });
    setTimeout(() => { load(); setTriggering(p => ({ ...p, [modelType]: false })); }, 2000);
  };

  const toggleSchedule = async (modelType, enabled) => {
    await put(`/api/data-intelligence/schedules/policies/${modelType}`, { enabled: !enabled });
    load();
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const { schedules = [], recent_executions = [], stale_models = [] } = dashboard || {};

  return (
    <div data-testid="ml-scheduler-dashboard" className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("techDashboards.mlScheduler")}</h1>
          <p className="text-sm text-muted-foreground">Model çalıştırma zamanlaması, durum izleme ve snapshot yönetimi</p>
        </div>
        <Button data-testid="refresh-scheduler" variant="outline" size="sm" onClick={load}>
          <RefreshCw className="h-4 w-4 mr-1" /> Yenile
        </Button>
      </div>

      {stale_models.length > 0 && (
        <Card className="border-amber-500/30 bg-amber-50/50">
          <CardContent className="py-3 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <span className="text-sm font-medium text-amber-800">
              {stale_models.length} model güncel değil: {stale_models.map(s => MODEL_LABELS[s.model_type] || s.model_type).join(', ')}
            </span>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {schedules.map(s => {
          const color = MODEL_COLORS[s.model_type] || 'blue';
          return (
            <Card key={s.id} data-testid={`schedule-card-${s.model_type}`}>
              <CardHeader className="pb-2">
                <div className="flex justify-between items-center">
                  <CardTitle className="text-base">{MODEL_LABELS[s.model_type] || s.model_type}</CardTitle>
                  <Badge variant={s.enabled ? 'default' : 'secondary'}>{s.enabled ? 'Aktif' : 'Devre Dışı'}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div><span className="text-muted-foreground">Interval:</span> <strong>{s.interval_hours}h</strong></div>
                  <div><span className="text-muted-foreground">Retention:</span> <strong>{s.snapshot_retention_days}d</strong></div>
                  <div className="col-span-2"><span className="text-muted-foreground">Son çalışma:</span>{' '}
                    <strong>{s.last_run_at ? new Date(s.last_run_at).toLocaleString('tr-TR') : 'Hiç'}</strong>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    data-testid={`trigger-${s.model_type}`}
                    size="sm" className="flex-1"
                    disabled={triggering[s.model_type]}
                    onClick={() => trigger(s.model_type)}
                  >
                    {triggering[s.model_type] ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Play className="h-4 w-4 mr-1" />}
                    Çalıştır
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => toggleSchedule(s.model_type, s.enabled)}>
                    {s.enabled ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Son Çalışmalar</CardTitle></CardHeader>
        <CardContent>
          {recent_executions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">Henüz çalışma yok</p>
          ) : (
            <div className="space-y-2">
              {recent_executions.map(j => (
                <div key={j.id} className="flex items-center justify-between py-2 border-b last:border-0" data-testid={`execution-${j.id}`}>
                  <div className="flex items-center gap-3">
                    <Brain className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-sm font-medium">{MODEL_LABELS[j.model_type] || j.model_type}</p>
                      <p className="text-xs text-muted-foreground">{new Date(j.created_at).toLocaleString('tr-TR')} · {j.triggered_by}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {j.duration_ms && <span className="text-xs text-muted-foreground">{j.duration_ms}ms</span>}
                    {j.confidence_avg && <span className="text-xs font-medium">{(j.confidence_avg * 100).toFixed(0)}%</span>}
                    <Badge className={STATUS_BADGE[j.status] || 'bg-gray-100'}>{j.status}</Badge>
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
