import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw, Heart, AlertTriangle } from 'lucide-react';
import { API, ScoreRing } from '../shared';

const SEVERITY_COLORS = {
  HEALTHY: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30', dot: 'bg-emerald-400' },
  DEGRADED: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30', dot: 'bg-amber-400' },
  CRITICAL: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', dot: 'bg-red-400' },
};

function HealthScoreBar({ score, classification }) {
  const color = classification === 'HEALTHY' ? '#10b981' : classification === 'DEGRADED' ? '#f59e0b' : '#ef4444';
  return (
    <div data-testid="health-score-bar" className="w-full">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Health Score</span>
        <span className="text-sm font-bold" style={{ color }}>{score}</span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${score}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function ConnectorCard({ connector }) {
  const cls = connector.classification || 'CRITICAL';
  const colors = SEVERITY_COLORS[cls] || SEVERITY_COLORS.CRITICAL;

  return (
    <Card data-testid={`connector-health-card-${connector.connector_id}`} className={`${colors.bg} ${colors.border} border`}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${colors.dot}`} />
            <span className="text-sm font-medium text-slate-200">{connector.display_name || connector.connector_id}</span>
          </div>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded ${colors.text} ${colors.bg}`}>{cls}</span>
        </div>

        <HealthScoreBar score={connector.health_score || 0} classification={cls} />

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex justify-between"><span className="text-slate-500">Uptime</span><span className="text-slate-300">{connector.uptime_percentage ?? 0}%</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Sync Rate</span><span className="text-slate-300">{connector.sync_success_rate ?? 0}%</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Import Rate</span><span className="text-slate-300">{connector.import_success_rate ?? 0}%</span></div>
          <div className="flex justify-between">
            <span className="text-slate-500">Alerts</span>
            <span className={connector.critical_alerts > 0 ? 'text-red-400' : 'text-slate-300'}>
              {connector.active_alerts ?? 0} ({connector.critical_alerts ?? 0} crit)
            </span>
          </div>
          <div className="flex justify-between"><span className="text-slate-500">Retries</span><span className="text-slate-300">{connector.retry_count ?? 0}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Total Syncs</span><span className="text-slate-300">{connector.total_syncs ?? 0}</span></div>
        </div>

        <div className="text-xs text-slate-500 pt-1 border-t border-slate-700/50 space-y-1">
          <div className="flex justify-between">
            <span>Last Sync</span>
            <span className="text-slate-400">{connector.last_successful_sync ? new Date(connector.last_successful_sync).toLocaleString('tr-TR') : '-'}</span>
          </div>
          <div className="flex justify-between">
            <span>Last Import</span>
            <span className="text-slate-400">{connector.last_successful_import ? new Date(connector.last_successful_import).toLocaleString('tr-TR') : '-'}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const ConnectorHealthTab = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const { data: json } = await axios.get(`${API}/health-dashboard/connectors`);
      setData(json);
    } catch (e) {
      toast.error('Sağlık verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHealth(); }, [fetchHealth]);

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  }

  const connectors = data?.connectors || [];

  return (
    <div data-testid="connector-health-dashboard" className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Heart className="w-5 h-5 text-emerald-400" /> Connector Health Dashboard</h3>
          <p className="text-xs text-slate-500 mt-0.5">Average Score: <span className="text-cyan-400 font-medium">{data?.average_health_score ?? 0}</span></p>
        </div>
        <Button data-testid="refresh-health-btn" variant="outline" size="sm" onClick={fetchHealth} className="border-slate-700 text-slate-300">
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Refresh
        </Button>
      </div>

      {/* Summary */}
      <div data-testid="health-summary" className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total', value: data?.total ?? 0, color: 'text-slate-200' },
          { label: 'Healthy', value: data?.healthy ?? 0, color: 'text-emerald-400' },
          { label: 'Degraded', value: data?.degraded ?? 0, color: 'text-amber-400' },
          { label: 'Critical', value: data?.critical ?? 0, color: 'text-red-400' },
        ].map(item => (
          <Card key={item.label} className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-3 text-center">
              <div className={`text-2xl font-bold ${item.color}`}>{item.value}</div>
              <div className="text-xs text-slate-500 mt-1">{item.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {connectors.length === 0 ? (
        <div className="text-center py-8 text-slate-500 text-sm">No connectors found.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {connectors.map(c => <ConnectorCard key={c.connector_id} connector={c} />)}
        </div>
      )}
    </div>
  );
};

export default ConnectorHealthTab;
