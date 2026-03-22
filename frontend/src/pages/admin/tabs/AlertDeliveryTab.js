import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw, Send, Plus, Trash2, TestTube } from 'lucide-react';
import { API } from '../shared';

const CHANNEL_TYPES = [
  { value: 'email', label: 'Email' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'slack', label: 'Slack' },
  { value: 'teams', label: 'Microsoft Teams' },
];

const SEVERITY_OPTIONS = ['info', 'warning', 'critical'];

function ChannelForm({ onSave, onCancel }) {
  const [form, setForm] = useState({
    channel_type: 'webhook', name: '', connector_id: '*',
    enabled: true, min_severity: 'warning', throttle_seconds: 300, config: {},
  });
  const [configStr, setConfigStr] = useState('{}');

  const handleSave = () => {
    try {
      onSave({ ...form, config: JSON.parse(configStr) });
    } catch { toast.error('Invalid JSON config'); }
  };

  return (
    <Card data-testid="channel-form" className="bg-slate-800/80 border-slate-700">
      <CardContent className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-400 block mb-1">Channel Type</label>
            <select data-testid="channel-type-select" value={form.channel_type}
              onChange={e => setForm({ ...form, channel_type: e.target.value })}
              className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200">
              {CHANNEL_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Name</label>
            <input data-testid="channel-name-input" value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200" placeholder="Channel name" />
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Min Severity</label>
            <select data-testid="min-severity-select" value={form.min_severity}
              onChange={e => setForm({ ...form, min_severity: e.target.value })}
              className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200">
              {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Throttle (sec)</label>
            <input data-testid="throttle-input" type="number" value={form.throttle_seconds}
              onChange={e => setForm({ ...form, throttle_seconds: parseInt(e.target.value) || 300 })}
              className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200" />
          </div>
        </div>
        <div>
          <label className="text-xs text-slate-400 block mb-1">Config (JSON)</label>
          <textarea data-testid="channel-config-textarea" value={configStr}
            onChange={e => setConfigStr(e.target.value)} rows={3}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-xs text-slate-200 font-mono"
            placeholder='{"webhook_url": "https://hooks.slack.com/..."}' />
        </div>
        <div className="flex gap-2">
          <Button data-testid="save-channel-btn" size="sm" onClick={handleSave}>Save</Button>
          <Button variant="outline" size="sm" onClick={onCancel} className="border-slate-700 text-slate-300">Cancel</Button>
        </div>
      </CardContent>
    </Card>
  );
}

const AlertDeliveryTab = () => {
  const [channels, setChannels] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [view, setView] = useState('channels');

  const fetchChannels = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/delivery/channels`); setChannels(data.channels || []); } catch { /* fetch error */ }
  }, []);
  const fetchLogs = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/delivery/log?limit=50`); setLogs(data.logs || []); } catch { /* fetch error */ }
  }, []);

  useEffect(() => { Promise.all([fetchChannels(), fetchLogs()]).finally(() => setLoading(false)); }, [fetchChannels, fetchLogs]);

  const saveChannel = async (d) => {
    try { await axios.post(`${API}/delivery/channels`, d); toast.success('Channel saved'); setShowForm(false); fetchChannels(); }
    catch { toast.error('Failed to save'); }
  };
  const deleteChannel = async (id) => {
    try { await axios.delete(`${API}/delivery/channels/${id}`); toast.success('Deleted'); fetchChannels(); }
    catch { toast.error('Delete failed'); }
  };
  const testChannel = async (id) => {
    try { const { data } = await axios.post(`${API}/delivery/test/${id}`); toast.info(`Delivered: ${data.result?.delivered || 0}`); fetchLogs(); }
    catch { toast.error('Test failed'); }
  };

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div data-testid="alert-delivery-dashboard" className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Send className="w-5 h-5 text-blue-400" /> Alert Delivery Channels</h3>
        <div className="flex gap-2">
          <Button data-testid="view-channels-btn" variant={view === 'channels' ? 'default' : 'outline'} size="sm"
            onClick={() => setView('channels')} className={view !== 'channels' ? 'border-slate-700 text-slate-300' : ''}>
            Channels ({channels.length})
          </Button>
          <Button data-testid="view-logs-btn" variant={view === 'logs' ? 'default' : 'outline'} size="sm"
            onClick={() => { setView('logs'); fetchLogs(); }} className={view !== 'logs' ? 'border-slate-700 text-slate-300' : ''}>
            Delivery Log
          </Button>
          <Button data-testid="add-channel-btn" size="sm" onClick={() => setShowForm(true)} className="bg-emerald-600 hover:bg-emerald-500">
            <Plus className="w-3.5 h-3.5 mr-1" /> Add
          </Button>
        </div>
      </div>

      {showForm && <ChannelForm onSave={saveChannel} onCancel={() => setShowForm(false)} />}

      {view === 'channels' ? (
        <div className="space-y-2">
          {channels.length === 0 ? (
            <div className="text-center py-8 text-slate-500 text-sm">No delivery channels configured.</div>
          ) : channels.map(ch => (
            <Card key={ch.id} data-testid={`channel-row-${ch.id}`} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${ch.enabled ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  <div>
                    <div className="text-sm text-slate-200 font-medium">{ch.name || ch.channel_type}</div>
                    <div className="text-xs text-slate-500">{ch.channel_type} | min: {ch.min_severity} | throttle: {ch.throttle_seconds}s</div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button data-testid={`test-channel-${ch.id}`} variant="outline" size="sm" onClick={() => testChannel(ch.id)} className="border-slate-700 text-slate-300">
                    <TestTube className="w-3 h-3 mr-1" /> Test
                  </Button>
                  <Button data-testid={`delete-channel-${ch.id}`} variant="outline" size="sm" onClick={() => deleteChannel(ch.id)} className="border-red-800 text-red-400 hover:bg-red-900/20">
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-0">
            {logs.length === 0 ? (
              <div className="text-center py-8 text-slate-500 text-sm">No delivery logs yet.</div>
            ) : (
              <table className="w-full text-xs">
                <thead><tr className="text-slate-500 border-b border-slate-700/50">
                  <th className="text-left py-2 px-3">Time</th><th className="text-left py-2 px-3">Channel</th>
                  <th className="text-left py-2 px-3">Type</th><th className="text-left py-2 px-3">Alert</th>
                  <th className="text-left py-2 px-3">Status</th>
                </tr></thead>
                <tbody>{logs.map((l, i) => (
                  <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                    <td className="py-1.5 px-3 text-slate-400">{l.delivered_at ? new Date(l.delivered_at).toLocaleString('tr-TR') : '-'}</td>
                    <td className="py-1.5 px-3 text-slate-300">{l.channel_id?.slice(0, 8)}</td>
                    <td className="py-1.5 px-3 text-slate-300">{l.channel_type}</td>
                    <td className="py-1.5 px-3 text-slate-400 font-mono">{l.alert_id?.slice(0, 8)}</td>
                    <td className="py-1.5 px-3">
                      <span className={`px-1.5 py-0.5 rounded ${l.success ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                        {l.success ? 'OK' : 'FAIL'}
                      </span>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default AlertDeliveryTab;
