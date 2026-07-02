import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle2, XCircle, AlertTriangle, Shield, RefreshCcw, Lock, Unlock } from 'lucide-react';
import { toast } from 'sonner';
const API = "";
const ScoreRing = ({
  score,
  size = 120
}) => {
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - score / 100 * circumference;
  const color = score >= 80 ? '#10b981' : score >= 50 ? '#f59e0b' : '#ef4444';
  return <div data-testid="mapping-score-ring" className="relative inline-flex items-center justify-center" style={{
    width: size,
    height: size
  }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1e293b" strokeWidth="8" />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth="8" strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-700" />
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-bold text-white">{score}</div>
        <div className="text-[10px] text-slate-400">/ 100</div>
      </div>
    </div>;
};
const CheckItem = ({
  check
}) => {
  const isComplete = check.complete;
  const coverage = check.coverage_percentage ?? (check.mapped_count > 0 ? 100 : 0);
  return <div data-testid={`check-${check.entity_type}`} className="bg-slate-800/60 rounded-lg p-4 border border-slate-700/50">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isComplete ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-red-400" />}
          <span className="text-sm font-medium text-white capitalize">{check.entity_type.replace('_', ' ')}</span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full ${isComplete ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
          {isComplete ? 'Complete' : 'Incomplete'}
        </span>
      </div>
      {/* Progress bar */}
      <div className="w-full bg-slate-700 rounded-full h-1.5 mb-2">
        <div className="h-1.5 rounded-full transition-all duration-500" style={{
        width: `${coverage}%`,
        backgroundColor: isComplete ? '#10b981' : '#f59e0b'
      }} />
      </div>
      <div className="flex justify-between text-xs text-slate-400">
        <span>Mapped: {check.mapped_count || 0}</span>
        <span>Coverage: {coverage}%</span>
      </div>
      {check.unmapped_count > 0 && <div className="mt-2 text-xs text-amber-400">
          {check.unmapped_count} unmapped {check.entity_type.replace('_', ' ')}(s)
        </div>}
      {check.missing_details && check.missing_details.length > 0 && <div className="mt-1 space-y-0.5">
          {check.missing_details.slice(0, 3).map((d, i) => <div key={d.id || i} className="text-[11px] text-slate-500 truncate">{d}</div>)}
          {check.missing_details.length > 3 && <div className="text-[11px] text-slate-600">+{check.missing_details.length - 3} more</div>}
        </div>}
    </div>;
};
const MappingCompletenessTab = () => {
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const token = localStorage.getItem('token');
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch(`/api/channel-manager/v2/connectors`, {
        credentials: "include",
        headers
      });
      if (res.ok) {
        const data = await res.json();
        const list = data.connectors || data || [];
        setConnectors(list);
        if (list.length > 0 && !selectedConnector) setSelectedConnector(list[0].id);
      } else {
        toast.error('Konnektörler yüklenemedi');
      }
    } catch (e) {
      console.error(e);
      toast.error('Konnektörler yüklenemedi');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);
  const fetchReport = useCallback(async () => {
    if (!selectedConnector) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/channel-manager/v2/mapping-completeness/${selectedConnector}`, {
        credentials: "include",
        headers
      });
      if (res.ok) {
        setReport(await res.json());
      } else {
        toast.error('Eşleştirme tamlık raporu yüklenemedi');
      }
    } catch (e) {
      console.error(e);
      toast.error('Eşleştirme tamlık raporu yüklenemedi');
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedConnector]);
  useEffect(() => {
    fetchConnectors();
  }, [fetchConnectors]);
  useEffect(() => {
    if (selectedConnector) fetchReport();
  }, [selectedConnector, fetchReport]);
  const checks = report?.checks || {};
  const checkList = Object.values(checks);
  return <div data-testid="mapping-completeness-tab" className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <select data-testid="mapping-connector-select" value={selectedConnector} onChange={e => setSelectedConnector(e.target.value)} className="bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm">
          {connectors.map(c => <option key={c.id} value={c.id}>{c.display_name || c.id}</option>)}
        </select>
        <button data-testid="refresh-mapping-btn" onClick={fetchReport} className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition">
          <RefreshCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Validate
        </button>
      </div>

      {report && <>
          {/* Score + Gates */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="flex items-center justify-center py-6">
                <div className="text-center">
                  <ScoreRing score={report.readiness_score} />
                  <div className="text-xs text-slate-400 mt-2">Mapping Readiness</div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="flex items-center gap-4 py-6">
                <div className={`p-3 rounded-lg ${report.sync_allowed ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                  {report.sync_allowed ? <Unlock className="w-6 h-6 text-emerald-400" /> : <Lock className="w-6 h-6 text-red-400" />}
                </div>
                <div>
                  <div className="text-sm font-medium text-white">Sync Gate</div>
                  <div className={`text-xs ${report.sync_allowed ? 'text-emerald-400' : 'text-red-400'}`}>
                    {report.sync_allowed ? 'Allowed' : 'Blocked'}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="flex items-center gap-4 py-6">
                <div className={`p-3 rounded-lg ${report.import_allowed ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                  {report.import_allowed ? <Unlock className="w-6 h-6 text-emerald-400" /> : <Lock className="w-6 h-6 text-red-400" />}
                </div>
                <div>
                  <div className="text-sm font-medium text-white">Import Gate</div>
                  <div className={`text-xs ${report.import_allowed ? 'text-emerald-400' : 'text-red-400'}`}>
                    {report.import_allowed ? 'Allowed' : 'Manual Review Required'}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Blocked Reasons */}
          {report.blocked_reasons && report.blocked_reasons.length > 0 && <Card className="bg-red-950/30 border-red-800/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-red-300 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" /> Blocked Reasons
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1">
                  {report.blocked_reasons.map((r, i) => <li key={r.id || i} className="text-xs text-red-200/80 flex items-start gap-2">
                      <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      {r}
                    </li>)}
                </ul>
              </CardContent>
            </Card>}

          {/* Per-type Checks */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {checkList.map(check => <CheckItem key={check.entity_type} check={check} />)}
          </div>
        </>}
    </div>;
};
export default MappingCompletenessTab;