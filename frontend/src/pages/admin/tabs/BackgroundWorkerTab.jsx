import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, Play, Zap } from 'lucide-react';
import { API } from '../shared';

const JOB_TYPES = [
  { value: 'reservation_import', label: 'Reservation Import', interval: '5 min' },
  { value: 'inventory_safety_sync', label: 'Inventory Safety Sync', interval: '30 min' },
  { value: 'connector_health_check', label: 'Health Check', interval: '15 min' },
  { value: 'metrics_aggregation', label: 'Metrics Aggregation', interval: '30 min' },
];

const STATUS_CLASSES = {
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  running: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
  pending: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
  retrying: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  failed: 'bg-red-500/10 text-red-400 border-red-500/30',
  skipped: 'bg-slate-500/10 text-slate-500 border-slate-500/30',
};

const BackgroundWorkerTab = () => {
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [jobsRes, statsRes] = await Promise.all([
        axios.get(`${API}/worker/jobs?limit=50`),
        axios.get(`${API}/worker/stats`),
      ]);
      setJobs(jobsRes.data.jobs || []);
      setStats(statsRes.data);
    } catch { /* silent */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const runJob = async (jobType) => {
    setRunning(jobType);
    try {
      await axios.post(`${API}/worker/jobs/run?job_type=${jobType}`);
      toast.success(`${jobType} job started`);
      await fetchData();
    } catch { toast.error('Job failed'); } finally { setRunning(null); }
  };

  const runAll = async () => {
    setRunning('all');
    try {
      await axios.post(`${API}/worker/jobs/run-all`);
      toast.success('All jobs triggered');
      await fetchData();
    } catch { toast.error('Run all failed'); } finally { setRunning(null); }
  };

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div data-testid="background-worker-dashboard" className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Zap className="w-5 h-5 text-amber-400" /> Background Worker</h3>
        <div className="flex gap-2">
          <Button data-testid="run-all-jobs-btn" size="sm" onClick={runAll} disabled={running === 'all'}>
            {running === 'all' ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Play className="w-3.5 h-3.5 mr-1" />} Run All
          </Button>
          <Button data-testid="refresh-worker-btn" variant="outline" size="sm" onClick={fetchData} className="border-slate-700 text-slate-300">
            <RefreshCw className="w-3.5 h-3.5 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* Job Type Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {JOB_TYPES.map(jt => {
          const s = stats?.stats?.[jt.value] || {};
          return (
            <Card key={jt.value} data-testid={`job-type-card-${jt.value}`} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-3">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <div className="text-sm font-medium text-slate-200">{jt.label}</div>
                    <div className="text-xs text-slate-500">Every {jt.interval}</div>
                  </div>
                  <Button data-testid={`run-job-${jt.value}`} variant="outline" size="sm" onClick={() => runJob(jt.value)}
                    disabled={running === jt.value} className="border-slate-700 text-slate-300 h-7 px-2">
                    {running === jt.value ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                  </Button>
                </div>
                <div className="flex gap-3 text-xs">
                  <span className="text-emerald-400">{s.completed || 0} ok</span>
                  <span className="text-red-400">{s.failed || 0} fail</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Recent Jobs */}
      <Card className="bg-slate-800/50 border-slate-700">
        <CardContent className="p-0">
          <div className="px-4 py-2 border-b border-slate-700/50">
            <h4 className="text-sm font-medium text-slate-300">Recent Jobs</h4>
          </div>
          {jobs.length === 0 ? (
            <div className="text-center py-6 text-slate-500 text-sm">No worker jobs yet.</div>
          ) : (
            <table className="w-full text-xs">
              <thead><tr className="text-slate-500 border-b border-slate-700/50">
                <th className="text-left py-2 px-3">Type</th><th className="text-left py-2 px-3">Status</th>
                <th className="text-left py-2 px-3">Connector</th><th className="text-left py-2 px-3">Started</th>
                <th className="text-left py-2 px-3">Completed</th><th className="text-left py-2 px-3">Retries</th>
              </tr></thead>
              <tbody>{jobs.map(j => (
                <tr key={j.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="py-1.5 px-3 text-slate-300">{j.job_type}</td>
                  <td className="py-1.5 px-3">
                    <Badge className={`${STATUS_CLASSES[j.status] || 'text-slate-400'} border text-xs`}>{j.status}</Badge>
                  </td>
                  <td className="py-1.5 px-3 text-slate-400 font-mono">{j.connector_id?.slice(0, 8) || '-'}</td>
                  <td className="py-1.5 px-3 text-slate-400">{j.started_at ? new Date(j.started_at).toLocaleString('tr-TR') : '-'}</td>
                  <td className="py-1.5 px-3 text-slate-400">{j.completed_at ? new Date(j.completed_at).toLocaleString('tr-TR') : '-'}</td>
                  <td className="py-1.5 px-3 text-slate-400">{j.retry_count || 0}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default BackgroundWorkerTab;
