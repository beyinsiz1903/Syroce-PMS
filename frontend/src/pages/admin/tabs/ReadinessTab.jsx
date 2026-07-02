import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, CheckCircle, AlertTriangle, XCircle, Shield } from 'lucide-react';
import { API } from '../shared';
import { useTranslation } from 'react-i18next';
const ReadinessTab = () => {
  const {
    t
  } = useTranslation();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(null);
  const fetchOverview = useCallback(async () => {
    setLoading(true);
    try {
      const {
        data
      } = await axios.get(`${API}/admin/production-readiness/overview`);
      setReports(data.reports || []);
    } catch {/* silent */}
    setLoading(false);
  }, []);
  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);
  const handleRunCheck = async connectorId => {
    setRunLoading(connectorId);
    try {
      const {
        data
      } = await axios.post(`${API}/admin/production-readiness/${connectorId}`);
      setReports(prev => prev.map(r => r.connector_id === connectorId ? data : r));
      toast.success('Kontrol tamamlandi');
    } catch {
      toast.error('Hata');
    }
    setRunLoading(null);
  };
  const checkIcon = status => {
    if (status === 'passed') return <CheckCircle className="w-4 h-4 text-emerald-400" />;
    if (status === 'warning') return <AlertTriangle className="w-4 h-4 text-amber-400" />;
    return <XCircle className="w-4 h-4 text-red-400" />;
  };
  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  return <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Production Readiness Report</h3>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchOverview}><RefreshCw className="w-3.5 h-3.5 mr-1" /> {t('cm.pages_admin_tabs_ReadinessTab.yenile')}</Button>
      </div>
      {reports.map(r => <Card key={r.connector_id} data-testid={`readiness-${r.connector_id}`} className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-medium text-white">{r.display_name}</p>
                <p className="text-xs text-slate-500">{r.provider} - {r.connector_id?.slice(0, 8)}...</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge data-testid={`readiness-badge-${r.connector_id}`} className={`border text-xs ${r.production_recommendation === 'READY_FOR_PRODUCTION' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : r.production_recommendation === 'READY_WITH_WARNINGS' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'}`}>{r.production_recommendation?.replace(/_/g, ' ')}</Badge>
                <Button size="sm" variant="ghost" className="text-blue-400 h-7" disabled={runLoading === r.connector_id} onClick={() => handleRunCheck(r.connector_id)}>
                  {runLoading === r.connector_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                </Button>
              </div>
            </div>
            <div className="flex gap-4 mb-3 text-xs">
              <span className="text-emerald-400">{r.passed_checks} passed</span>
              <span className="text-red-400">{r.failed_checks} failed</span>
              <span className="text-amber-400">{r.warning_checks} warnings</span>
            </div>
            <div className="space-y-1.5">
              {(r.checks || []).map((check, i) => <div key={check.id || i} className="flex items-center gap-2 bg-slate-900/40 rounded p-2">
                  {checkIcon(check.status)}
                  <span className="text-xs text-white flex-1">{check.check?.replace(/_/g, ' ')}</span>
                  <span className="text-[10px] text-slate-500 max-w-[50%] truncate text-right">{check.detail}</span>
                </div>)}
            </div>
            {r.blocker_issues?.length > 0 && <div className="mt-2 p-2 bg-red-500/10 rounded border border-red-500/20">
                <p className="text-xs text-red-400 font-medium">Blocker Issues:</p>
                {r.blocker_issues.map((b, i) => <p key={b.id || i} className="text-xs text-red-300">{b.replace(/_/g, ' ')}</p>)}
              </div>}
          </CardContent>
        </Card>)}
      {reports.length === 0 && <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">{t('cm.pages_admin_tabs_ReadinessTab.connector_bulunamadi')}</CardContent></Card>}
    </div>;
};
export default ReadinessTab;