import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, Bell, BellOff, Check, X, Eye } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { API, SeverityBadge, MetricCard } from '../shared';

const AlertsTab = () => {
  const [alerts, setAlerts] = useState([]);
  const [summary, setSummary] = useState({});
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('active');
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [showRules, setShowRules] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterStatus !== 'all') params.append('status', filterStatus);
      if (filterSeverity !== 'all') params.append('severity', filterSeverity);
      const { data } = await axios.get(`${API}/alerts?${params}`);
      setAlerts(data.alerts || []);
      setSummary(data.summary || {});
    } catch { /* silent */ }
    setLoading(false);
  }, [filterStatus, filterSeverity]);

  const fetchRules = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/alerts/rules`); setRules(data.rules || []); } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchAlerts(); fetchRules(); }, [fetchAlerts, fetchRules]);

  const handleEvaluate = async () => {
    setActionLoading('evaluate');
    try {
      const { data } = await axios.post(`${API}/alerts/evaluate`);
      toast.success(`${data.alerts_created} yeni alarm olusturuldu`);
      fetchAlerts();
    } catch { toast.error('Degerlendirme hatasi'); }
    setActionLoading(null);
  };

  const handleAction = async (alertId, action) => {
    setActionLoading(`${alertId}-${action}`);
    try {
      await axios.post(`${API}/alerts/${alertId}/${action}`, { reason: 'Admin action', hours: 24 });
      toast.success(`Alarm ${action} yapildi`);
      fetchAlerts();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
    setActionLoading(null);
  };

  const toggleRule = async (ruleId, enabled) => {
    try {
      await axios.put(`${API}/alerts/rules/${ruleId}`, { trigger: '', threshold: 0, severity: '', description: '', enabled: !enabled });
      toast.success(`Kural ${!enabled ? 'aktif' : 'deaktif'} edildi`);
      fetchRules();
    } catch { toast.error('Kural guncelleme hatasi'); }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard title="Aktif Alarm" value={summary.active || 0} icon={Bell} color="text-red-400" />
        <MetricCard title="Onaylanan" value={summary.acknowledged || 0} icon={Eye} color="text-amber-400" />
        <MetricCard title="Cozulen" value={summary.resolved || 0} icon={Check} color="text-emerald-400" />
        <MetricCard title="Susturulan" value={summary.muted || 0} icon={BellOff} color="text-slate-400" />
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger data-testid="alert-status-filter" className="w-36 bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Durum</SelectItem>
            <SelectItem value="active">Aktif</SelectItem>
            <SelectItem value="acknowledged">Onaylanan</SelectItem>
            <SelectItem value="resolved">Cozulen</SelectItem>
            <SelectItem value="muted">Susturulan</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filterSeverity} onValueChange={setFilterSeverity}>
          <SelectTrigger data-testid="alert-severity-filter" className="w-32 bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Seviye</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="info">Info</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchAlerts}><RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile</Button>
        <Button data-testid="evaluate-alerts-btn" size="sm" variant="outline" className="border-blue-700 text-blue-400" disabled={actionLoading === 'evaluate'} onClick={handleEvaluate}>
          {actionLoading === 'evaluate' ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Bell className="w-3.5 h-3.5 mr-1" />} Degerlendirme Calistir
        </Button>
        <Button size="sm" variant={showRules ? 'default' : 'outline'} className={showRules ? 'bg-blue-600 ml-auto' : 'border-slate-700 text-slate-300 ml-auto'} onClick={() => setShowRules(!showRules)}>
          Kurallar ({rules.length})
        </Button>
      </div>

      {showRules ? (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-slate-300">Alarm Kurallari</h4>
          {rules.map(rule => (
            <Card key={rule.id} data-testid={`rule-${rule.id}`} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-3 flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <SeverityBadge severity={rule.severity} />
                    <Badge className="bg-slate-700/50 text-slate-300 border-slate-600 text-xs border">{rule.trigger?.replace(/_/g,' ')}</Badge>
                    <span className="text-xs text-slate-400">Esik: {rule.threshold}</span>
                  </div>
                  <p className="text-xs text-slate-400 truncate">{rule.description}</p>
                </div>
                <Button size="sm" variant="ghost" className={rule.enabled ? 'text-emerald-400' : 'text-slate-500'} onClick={() => toggleRule(rule.id, rule.enabled)}>
                  {rule.enabled ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : alerts.length === 0 ? (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Alarm bulunamadi</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {alerts.map(alert => (
            <Card key={alert.id} data-testid={`alert-${alert.id}`} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <SeverityBadge severity={alert.severity} />
                      <Badge className="bg-slate-700/50 text-slate-300 border-slate-600 text-xs border">{alert.trigger?.replace(/_/g,' ')}</Badge>
                      <Badge className={`border text-xs ${
                        alert.status === 'active' ? 'bg-red-500/10 text-red-400 border-red-500/30' :
                        alert.status === 'acknowledged' ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' :
                        'bg-slate-500/10 text-slate-400 border-slate-500/30'
                      }`}>{alert.status}</Badge>
                    </div>
                    <p className="text-sm text-white">{alert.description}</p>
                    <div className="flex gap-3 text-[10px] text-slate-500 mt-1">
                      <span>{alert.display_name}</span>
                      <span>Score: {alert.health_score_snapshot}</span>
                      <span>{new Date(alert.created_at).toLocaleString('tr-TR')}</span>
                    </div>
                    {alert.recommended_action && <p className="text-[10px] text-blue-400 mt-1">{alert.recommended_action}</p>}
                  </div>
                  <div className="flex gap-1 flex-shrink-0">
                    {alert.status === 'active' && (
                      <Button size="sm" variant="ghost" className="text-amber-400 h-7 px-2" disabled={actionLoading === `${alert.id}-acknowledge`} onClick={() => handleAction(alert.id, 'acknowledge')}>
                        <Eye className="w-3 h-3" />
                      </Button>
                    )}
                    {['active', 'acknowledged'].includes(alert.status) && (
                      <>
                        <Button size="sm" variant="ghost" className="text-emerald-400 h-7 px-2" onClick={() => handleAction(alert.id, 'resolve')}><Check className="w-3 h-3" /></Button>
                        <Button size="sm" variant="ghost" className="text-slate-400 h-7 px-2" onClick={() => handleAction(alert.id, 'mute')}><BellOff className="w-3 h-3" /></Button>
                        <Button size="sm" variant="ghost" className="text-red-400 h-7 px-2" onClick={() => handleAction(alert.id, 'dismiss')}><X className="w-3 h-3" /></Button>
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default AlertsTab;
