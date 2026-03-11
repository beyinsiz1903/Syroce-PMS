import { useState, useEffect, useCallback } from 'react';
import { PlayCircle, RefreshCw, Clock, CheckCircle, XCircle, AlertTriangle, RotateCcw, Server, Settings } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_STYLES = {
  completed: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', icon: CheckCircle },
  running: { bg: 'bg-blue-500/10', text: 'text-blue-400', icon: RefreshCw },
  pending: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', icon: Clock },
  retrying: { bg: 'bg-orange-500/10', text: 'text-orange-400', icon: RotateCcw },
  failed: { bg: 'bg-red-500/10', text: 'text-red-400', icon: XCircle },
  skipped: { bg: 'bg-slate-500/10', text: 'text-slate-400', icon: AlertTriangle },
};

const Badge = ({ status }) => {
  const s = STATUS_STYLES[status] || STATUS_STYLES.pending;
  const Icon = s.icon;
  return (
    <span data-testid={`job-status-${status}`} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${s.bg} ${s.text}`}>
      <Icon size={12} /> {status}
    </span>
  );
};

export default function ImportJobsTab() {
  const [jobs, setJobs] = useState([]);
  const [environments, setEnvironments] = useState({});
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runningSafety, setRunningSafety] = useState(false);
  const token = localStorage.getItem('token');

  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    try {
      const [jobsRes, envsRes] = await Promise.all([
        fetch(`${API}/api/channel-manager/v2/import-jobs?limit=50`, { headers }),
        fetch(`${API}/api/channel-manager/v2/environments`, { headers }),
      ]);
      if (jobsRes.ok) { const d = await jobsRes.json(); setJobs(d.jobs || []); }
      if (envsRes.ok) { const d = await envsRes.json(); setEnvironments(d.environments || {}); }
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const runAll = async () => {
    setRunning(true);
    try {
      await fetch(`${API}/api/channel-manager/v2/import-jobs/run-all`, { method: 'POST', headers });
      await fetchData();
    } catch (e) { console.error(e); }
    setRunning(false);
  };

  const runSafetyNet = async () => {
    setRunningSafety(true);
    try {
      await fetch(`${API}/api/channel-manager/v2/safety-net/inventory-sync`, { method: 'POST', headers });
      await fetchData();
    } catch (e) { console.error(e); }
    setRunningSafety(false);
  };

  const retryJob = async (jobId) => {
    try {
      await fetch(`${API}/api/channel-manager/v2/import-jobs/${jobId}/retry`, { method: 'POST', headers });
      await fetchData();
    } catch (e) { console.error(e); }
  };

  if (loading) return <div className="flex justify-center py-12"><RefreshCw size={24} className="animate-spin text-slate-400" /></div>;

  const completed = jobs.filter(j => j.status === 'completed').length;
  const failed = jobs.filter(j => j.status === 'failed').length;
  const retrying = jobs.filter(j => j.status === 'retrying').length;

  return (
    <div data-testid="import-jobs-tab" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Scheduled Import Jobs</h2>
          <p className="text-sm text-slate-400 mt-0.5">Periyodik rezervasyon cekim islemleri</p>
        </div>
        <div className="flex gap-2">
          <button data-testid="run-safety-net-btn" onClick={runSafetyNet} disabled={runningSafety}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600/20 text-amber-400 border border-amber-600/30 rounded text-sm hover:bg-amber-600/30 transition disabled:opacity-50">
            {runningSafety ? <RefreshCw size={14} className="animate-spin" /> : <Server size={14} />} Safety Net Sync
          </button>
          <button data-testid="run-all-imports-btn" onClick={runAll} disabled={running}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600/20 text-blue-400 border border-blue-600/30 rounded text-sm hover:bg-blue-600/30 transition disabled:opacity-50">
            {running ? <RefreshCw size={14} className="animate-spin" /> : <PlayCircle size={14} />} Run All Imports
          </button>
          <button data-testid="refresh-jobs-btn" onClick={fetchData}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 text-slate-300 border border-slate-600/30 rounded text-sm hover:bg-slate-700 transition">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Total Jobs', value: jobs.length, color: 'text-white' },
          { label: 'Completed', value: completed, color: 'text-emerald-400' },
          { label: 'Failed', value: failed, color: 'text-red-400' },
          { label: 'Retrying', value: retrying, color: 'text-orange-400' },
        ].map(s => (
          <div key={s.label} className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3">
            <p className="text-xs text-slate-400">{s.label}</p>
            <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Environment Config */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Settings size={16} className="text-slate-400" />
          <h3 className="text-sm font-semibold text-white">Environment Configurations</h3>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(environments).map(([name, cfg]) => (
            <div key={name} data-testid={`env-${name}`} className="bg-slate-900/50 border border-slate-700/30 rounded p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white capitalize">{name}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded ${name === 'production' ? 'bg-red-500/20 text-red-400' : name === 'sandbox' ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-500/20 text-slate-400'}`}>
                  {name}
                </span>
              </div>
              <div className="space-y-1 text-xs text-slate-400">
                <p>URL: <span className="text-slate-300">{(cfg.api_base_url || '').substring(0, 45)}...</span></p>
                <p>Timeout: <span className="text-slate-300">{cfg.timeout_read}s</span></p>
                <p>Retry: <span className="text-slate-300">{cfg.retry_max}x</span></p>
                <p>Rate Limit: <span className="text-slate-300">{cfg.rate_limit_rps} RPS</span></p>
                <p>Polling: <span className="text-slate-300">{cfg.reservation_polling_interval_seconds}s</span></p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Jobs Table */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700/50">
          <h3 className="text-sm font-semibold text-white">Import Job History ({jobs.length})</h3>
        </div>
        {jobs.length === 0 ? (
          <div className="px-4 py-8 text-center text-slate-500 text-sm">Henuz import job calismadi</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/50">
                <tr className="text-left text-xs text-slate-400 uppercase">
                  <th className="px-4 py-2">Job ID</th>
                  <th className="px-4 py-2">Connector</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">Triggered By</th>
                  <th className="px-4 py-2">Retries</th>
                  <th className="px-4 py-2">Created</th>
                  <th className="px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/30">
                {jobs.map(job => (
                  <tr key={job.id} data-testid={`job-row-${job.id}`} className="hover:bg-slate-800/50 transition">
                    <td className="px-4 py-2 text-slate-300 font-mono text-xs">{(job.id || '').substring(0, 8)}...</td>
                    <td className="px-4 py-2 text-slate-300">{(job.connector_id || '').substring(0, 12)}...</td>
                    <td className="px-4 py-2"><Badge status={job.status} /></td>
                    <td className="px-4 py-2 text-slate-400">{job.triggered_by}</td>
                    <td className="px-4 py-2 text-slate-400">{job.retry_count || 0}/{job.max_retries || 3}</td>
                    <td className="px-4 py-2 text-slate-400 text-xs">{job.created_at ? new Date(job.created_at).toLocaleString('tr-TR') : '-'}</td>
                    <td className="px-4 py-2">
                      {job.status === 'failed' && (
                        <button data-testid={`retry-job-${job.id}`} onClick={() => retryJob(job.id)}
                          className="text-xs text-blue-400 hover:text-blue-300">Retry</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
