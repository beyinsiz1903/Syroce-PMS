import { useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Play, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { API } from '../shared';

const SandboxValidationTab = () => {
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fetchingConnectors, setFetchingConnectors] = useState(true);

  const fetchConnectors = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/connectors`); setConnectors(data.connectors || []); } catch { /* silent */ }
    setFetchingConnectors(false);
  }, []);

  useState(() => { fetchConnectors(); });

  const runValidation = async () => {
    if (!selectedConnector) { toast.error('Connector seçin'); return; }
    setLoading(true); setReport(null);
    try {
      const { data } = await axios.post(`${API}/sandbox/validate/${selectedConnector}/full`);
      setReport(data);
      toast.success('Validation tamamlandi');
    } catch (e) { toast.error(e.response?.data?.detail || 'Validation hatası'); }
    setLoading(false);
  };

  const checkIcon = (success) => success ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-red-400" />;

  const impactColor = { low: 'text-emerald-400', medium: 'text-amber-400', high: 'text-red-400' };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Select value={selectedConnector} onValueChange={setSelectedConnector}>
          <SelectTrigger data-testid="sandbox-connector-select" className="w-64 bg-slate-800 border-slate-700 text-white"><SelectValue placeholder="Connector seçin..." /></SelectTrigger>
          <SelectContent>
            {connectors.map(c => <SelectItem key={c.id} value={c.id}>{c.display_name} ({c.provider})</SelectItem>)}
          </SelectContent>
        </Select>
        <Button data-testid="run-sandbox-validation" size="sm" className="bg-blue-600 hover:bg-blue-700" disabled={loading || !selectedConnector} onClick={runValidation}>
          {loading ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1" />} Full Validation Baslat
        </Button>
      </div>

      {loading && <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /><span className="ml-2 text-sm text-slate-400">Dogrulama calistiriliyor...</span></div>}

      {report && (
        <div className="space-y-4">
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-sm font-medium text-white">Integration Readiness Report</p>
                  <p className="text-xs text-slate-500">{report.connector_id?.slice(0,12)}... - {new Date(report.run_at).toLocaleString('tr-TR')}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={`border text-xs ${
                    report.production_recommendation?.includes('READY —') ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' :
                    report.production_recommendation?.includes('CONDITIONAL') ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                    'bg-red-500/15 text-red-400 border-red-500/30'
                  }`}>{report.production_recommendation?.split('—')[0]?.trim()}</Badge>
                  {report.connector_health_impact && (
                    <span className={`text-xs font-medium ${impactColor[report.connector_health_impact] || ''}`}>Impact: {report.connector_health_impact}</span>
                  )}
                </div>
              </div>
              <div className="flex gap-4 text-xs mb-4">
                <span className="text-emerald-400">{report.passed_checks} passed</span>
                <span className="text-red-400">{report.failed_checks} failed</span>
                <span className="text-slate-400">{report.total_checks} total</span>
              </div>

              <div className="space-y-2">
                {(report.checks || []).map((check, i) => (
                  <div key={i} className="flex items-start gap-2 bg-slate-900/40 rounded p-2.5">
                    {checkIcon(check.success)}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-white font-medium">{check.check_name?.replace(/_/g,' ')}</p>
                      <div className="flex gap-3 text-[10px] text-slate-500 mt-0.5">
                        <span>{check.latency_ms}ms</span>
                        {check.provider_status && <span>Provider: {check.provider_status}</span>}
                      </div>
                      {check.request_summary && <p className="text-[10px] text-slate-600 mt-0.5">{check.request_summary}</p>}
                      {check.response_summary && <p className="text-[10px] text-slate-400 mt-0.5">{check.response_summary}</p>}
                      {check.error && <p className="text-[10px] text-red-400 mt-0.5">{check.error}</p>}
                      {check.blocking_issue && <p className="text-[10px] text-red-300 font-medium mt-0.5">BLOCKER: {check.blocking_issue}</p>}
                    </div>
                  </div>
                ))}
              </div>

              {report.blocker_issues?.length > 0 && (
                <div className="mt-3 p-2 bg-red-500/10 rounded border border-red-500/20">
                  <p className="text-xs text-red-400 font-medium">Blocker Issues:</p>
                  {report.blocker_issues.map((b, i) => <p key={i} className="text-xs text-red-300">{b}</p>)}
                </div>
              )}

              {report.required_next_actions?.length > 0 && (
                <div className="mt-3 p-2 bg-blue-500/10 rounded border border-blue-500/20">
                  <p className="text-xs text-blue-400 font-medium">Gerekli Aksiyonlar:</p>
                  {report.required_next_actions.map((a, i) => <p key={i} className="text-xs text-blue-300">{a}</p>)}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {!loading && !report && (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Sandbox validation calistirmak için connector seçin</CardContent></Card>
      )}
    </div>
  );
};

export default SandboxValidationTab;
