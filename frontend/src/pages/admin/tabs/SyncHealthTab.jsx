import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw } from 'lucide-react';
import { API, ScoreRing, StatusDot } from '../shared';
import { useTranslation } from 'react-i18next';

const SyncHealthTab = () => {
  const { t } = useTranslation();
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/admin/sync-health`);
      setHealth(data);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchHealth(); }, [fetchHealth]);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  if (!health) return null;

  const trend = health.sync_trend_24h || [];
  const maxTotal = Math.max(1, ...trend.map(t => t.total));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6">
        <ScoreRing score={health.overall_health_score} size={100} />
        <div>
          <p className="text-lg font-semibold text-white flex items-center gap-2">
            <StatusDot status={health.overall_status} /> Genel Saglik: {health.overall_status?.toUpperCase()}
          </p>
          <p className="text-sm text-slate-400">{health.connector_count} connector izleniyor</p>
          <div className="flex gap-4 mt-2 text-xs">
            <span className="text-red-400">{health.error_summary?.total || 0} hata</span>
            <span className="text-amber-400">{health.error_summary?.sync_failed || 0} {t('cm.pages_admin_tabs_SyncHealthTab.sync_hatasi')}</span>
          </div>
        </div>
        <Button size="sm" variant="outline" className="ml-auto border-slate-700 text-slate-300" onClick={fetchHealth}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> {t('cm.pages_admin_tabs_SyncHealthTab.yenile')}
        </Button>
      </div>

      {trend.length > 0 && (
        <Card className="bg-slate-800/50 border-slate-700">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-300">24 Saatlik Sync Trendi</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-end gap-1 h-32">
              {trend.map((t, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                  <div className="w-full flex flex-col-reverse" style={{height: 100}}>
                    <div className="bg-emerald-500/60 rounded-t" style={{height: `${(t.succeeded||0)/maxTotal*100}%`}} />
                    <div className="bg-red-500/60" style={{height: `${(t.failed||0)/maxTotal*100}%`}} />
                  </div>
                  <span className="text-[8px] text-slate-600 truncate w-full text-center">{t.hour?.slice(11) || ''}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-4 mt-2 text-[10px]">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-emerald-500" />{t('cm.pages_admin_tabs_SyncHealthTab.basarili')}</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-red-500" />Basarisiz</span>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3">
        {(health.connectors || []).map(c => (
          <Card key={c.connector_id} data-testid={`health-${c.connector_id}`} className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <ScoreRing score={c.health_score} size={50} />
                  <div>
                    <p className="text-sm font-medium text-white">{c.display_name}</p>
                    <p className="text-xs text-slate-500 flex items-center gap-1"><StatusDot status={c.status} /> {c.status} - {c.provider}</p>
                  </div>
                </div>
                <div className="text-right text-xs">
                  <p className="text-slate-400">Open Issues: <span className="text-white">{c.open_issues}</span></p>
                  <p className="text-slate-400">Failures: <span className="text-red-400">{c.details?.consecutive_failures || 0}</span></p>
                </div>
              </div>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                {Object.entries(c.by_severity || {}).map(([sev, count]) => (
                  <div key={sev} className="bg-slate-900/50 rounded p-1.5 text-center">
                    <p className="text-[9px] text-slate-500">{sev}</p>
                    <p className="text-sm font-semibold text-white">{count}</p>
                  </div>
                ))}
                {Object.entries(c.sync_metrics?.sync_jobs || {}).map(([st, count]) => (
                  <div key={st} className="bg-slate-900/50 rounded p-1.5 text-center">
                    <p className="text-[9px] text-slate-500">{st}</p>
                    <p className="text-sm font-semibold text-white">{count}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default SyncHealthTab;
