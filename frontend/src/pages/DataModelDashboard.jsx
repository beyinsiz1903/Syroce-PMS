import { t } from "i18next";
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { TrendCharts } from '../components/TrendCharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Database, Link2, Grid3X3, FileText, GitBranch, AlertTriangle, RefreshCw, Trash2, CheckCircle, Loader2, Server, Layers, ArrowRightLeft, Clock, Play, Repeat, Download, Activity, Shield, Eye, XCircle, Search, BarChart3, Bell, Radio, Zap, Heart } from 'lucide-react';
const API = "";
const ProviderBadge = ({
  provider
}) => {
  const map = {
    hotelrunner: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    exely: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
  };
  return <Badge data-testid={`provider-badge-${provider}`} className={`${map[provider] || 'bg-zinc-500/15 text-zinc-400'} border text-xs font-medium`}>
      {provider}
    </Badge>;
};
const StatusDot = ({
  status
}) => {
  const colors = {
    active: 'bg-emerald-400',
    draft: 'bg-amber-400',
    paused: 'bg-zinc-400',
    error: 'bg-red-400',
    disabled: 'bg-zinc-600',
    open: 'bg-red-400',
    investigating: 'bg-amber-400',
    resolved: 'bg-emerald-400',
    dismissed: 'bg-zinc-400',
    confirmed: 'bg-emerald-400',
    modified: 'bg-amber-400',
    cancelled: 'bg-red-400',
    pending: 'bg-blue-400'
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] || 'bg-zinc-500'}`} />;
};
const CollectionCard = ({
  name,
  count,
  icon: Icon,
  color
}) => <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
    <CardContent className="p-4 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${color}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-500 font-mono truncate">{name}</p>
        <p className="text-xl font-bold text-zinc-100">{count}</p>
      </div>
    </CardContent>
  </Card>;
const ProcessingBadge = ({
  status
}) => {
  const map = {
    pending: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    processed: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    failed: 'bg-red-500/15 text-red-400 border-red-500/30',
    duplicate: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
    stale: 'bg-amber-500/15 text-amber-400 border-amber-500/30'
  };
  return <Badge className={`${map[status] || 'bg-zinc-500/15 text-zinc-400'} border text-xs`}>{status}</Badge>;
};
const SlackConfigPanel = ({
  headers
}) => {
  const [config, setConfig] = useState(null);
  const [slackUrl, setSlackUrl] = useState('');
  const [slackEnabled, setSlackEnabled] = useState(false);
  const [slackSeverities, setSlackSeverities] = useState(['critical', 'high']);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const {
          data
        } = await axios.get(`/channel-manager/monitoring/dispatch-config`, {
          headers: headers()
        });
        setConfig(data);
        const s = data.slack || {};
        setSlackEnabled(s.enabled || false);
        setSlackUrl(s.webhook_url || '');
        setSlackSeverities(s.severities || ['critical', 'high']);
      } catch (e) {
        console.error(e);
      }
    };
    fetchConfig();
  }, [headers]);
  const saveSlack = async () => {
    setSaving(true);
    try {
      await axios.post(`/channel-manager/monitoring/dispatch-config/slack`, {
        enabled: slackEnabled,
        webhook_url: slackUrl,
        severities: slackSeverities
      }, {
        headers: headers()
      });
      toast.success('Slack configuration saved');
    } catch {
      toast.error('Save failed');
    }
    setSaving(false);
  };
  const testSlack = async () => {
    setTesting(true);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/monitoring/dispatch-config/slack/test`, {}, {
        headers: headers()
      });
      if (data.success) toast.success('Test message sent to Slack!');else toast.error(data.message || 'Test failed');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test failed');
    }
    setTesting(false);
  };
  const toggleSeverity = sev => {
    setSlackSeverities(prev => prev.includes(sev) ? prev.filter(s => s !== sev) : [...prev, sev]);
  };
  return <Card data-testid="slack-config-panel" className="bg-zinc-900/60 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
          <Bell className="w-4 h-4 text-amber-400" />{t("cm.pages_DataModelDashboard.alert_dispatch_slack")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <button data-testid="slack-toggle" onClick={() => setSlackEnabled(!slackEnabled)} className={`relative w-10 h-5 rounded-full transition-colors ${slackEnabled ? 'bg-emerald-500' : 'bg-zinc-600'}`}>
            <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${slackEnabled ? 'translate-x-5' : ''}`} />
          </button>
          <span className="text-sm text-zinc-300">{slackEnabled ? 'Slack alerts enabled' : 'Slack alerts disabled'}</span>
        </div>

        <div>
          <label className="block text-xs text-zinc-500 mb-1">{t("cm.pages_DataModelDashboard.webhook_url")}</label>
          <input data-testid="slack-webhook-url" type="text" placeholder={t("cm.pages_DataModelDashboard.https_hooks_slack_com_services")} className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none" value={slackUrl} onChange={e => setSlackUrl(e.target.value)} />
        </div>

        <div>
          <label className="block text-xs text-zinc-500 mb-2">{t("cm.pages_DataModelDashboard.alert_severities")}</label>
          <div className="flex gap-2 flex-wrap">
            {['critical', 'high', 'medium', 'info'].map(sev => <button key={sev} data-testid={`slack-severity-${sev}`} onClick={() => toggleSeverity(sev)} className={`px-3 py-1 rounded text-xs font-medium border transition-colors ${slackSeverities.includes(sev) ? sev === 'critical' ? 'bg-red-500/20 text-red-400 border-red-500/40' : sev === 'high' ? 'bg-amber-500/20 text-amber-400 border-amber-500/40' : sev === 'medium' ? 'bg-blue-500/20 text-blue-400 border-blue-500/40' : 'bg-zinc-500/20 text-zinc-400 border-zinc-500/40' : 'bg-zinc-900 text-zinc-600 border-zinc-700'}`}>
                {sev}
              </button>)}
          </div>
        </div>

        <div className="flex gap-2">
          <Button data-testid="save-slack-config" size="sm" className="bg-cyan-600 hover:bg-cyan-700 text-white text-xs" onClick={saveSlack} disabled={saving}>
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <CheckCircle className="w-3.5 h-3.5 mr-1" />}{t("cm.pages_DataModelDashboard.save_config")}</Button>
          <Button data-testid="test-slack" variant="outline" size="sm" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 text-xs" onClick={testSlack} disabled={testing || !slackUrl || !slackEnabled}>
            {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Zap className="w-3.5 h-3.5 mr-1" />}{t("cm.pages_DataModelDashboard.send_test")}</Button>
        </div>
      </CardContent>
    </Card>;
};
const DataModelDashboard = ({
  user,
  tenant,
  onLogout
}) => {
  const [loading, setLoading] = useState(false);
  const [schema, setSchema] = useState(null);
  const [connections, setConnections] = useState([]);
  const [roomMappings, setRoomMappings] = useState([]);
  const [ratePlanMappings, setRatePlanMappings] = useState([]);
  const [rawEvents, setRawEvents] = useState([]);
  const [lineages, setLineages] = useState([]);
  const [reconCases, setReconCases] = useState([]);
  const [reconSummary, setReconSummary] = useState(null);
  const [reconDashboard, setReconDashboard] = useState(null);
  const [reconMetrics, setReconMetrics] = useState(null);
  const [reconFilter, setReconFilter] = useState({
    status: '',
    severity: '',
    case_type: '',
    provider: ''
  });
  const [reconRunning, setReconRunning] = useState(false);
  const [ingestStatus, setIngestStatus] = useState(null);
  const [workerAction, setWorkerAction] = useState(null);
  const [monitoringOverview, setMonitoringOverview] = useState(null);
  const [monitoringAlerts, setMonitoringAlerts] = useState([]);
  const [monitoringMetrics, setMonitoringMetrics] = useState(null);
  const [providerConfigs, setProviderConfigs] = useState([]);
  const [validationRunning, setValidationRunning] = useState({});
  const [validationResults, setValidationResults] = useState({});
  const [credForms, setCredForms] = useState({});
  const [activeTab, setActiveTab] = useState('ingest');
  const propertyId = tenant?.property_id || 'prop-001';
  const headers = useCallback(() => {
    const token = localStorage.getItem('token');
    return token ? {
      Authorization: `Bearer ${token}`
    } : {};
  }, []);
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const h = headers();
      switch (activeTab) {
        case 'ingest':
          {
            const [eventsRes, ingestRes] = await Promise.all([axios.get(`/channel-manager/ingest/events?property_id=${propertyId}`, {
              headers: h
            }).catch(() => ({
              data: {
                events: []
              }
            })), axios.get(`/channel-manager/ingest/status?property_id=${propertyId}`, {
              headers: h
            }).catch(() => ({
              data: null
            }))]);
            setRawEvents(eventsRes.data.events || []);
            setIngestStatus(ingestRes.data);
            break;
          }
        case 'lineage':
          {
            const [lineageRes, schemaRes] = await Promise.all([axios.get(`/channel-manager/model/lineage?property_id=${propertyId}`, {
              headers: h
            }).catch(() => ({
              data: {
                lineages: []
              }
            })), axios.get(`/channel-manager/model/schema`, {
              headers: h
            }).catch(() => ({
              data: null
            }))]);
            setLineages(lineageRes.data.lineages || []);
            setSchema(schemaRes.data);
            break;
          }
        case 'connections':
          {
            const connRes = await axios.get(`/channel-manager/model/connections`, {
              headers: h
            }).catch(() => ({
              data: {
                connections: []
              }
            }));
            setConnections(connRes.data.connections || []);
            break;
          }
        case 'mappings':
          {
            const [roomRes, rateRes] = await Promise.all([axios.get(`/channel-manager/model/room-mappings?property_id=${propertyId}`, {
              headers: h
            }).catch(() => ({
              data: {
                mappings: []
              }
            })), axios.get(`/channel-manager/model/rate-plan-mappings?property_id=${propertyId}`, {
              headers: h
            }).catch(() => ({
              data: {
                mappings: []
              }
            }))]);
            setRoomMappings(roomRes.data.mappings || []);
            setRatePlanMappings(rateRes.data.mappings || []);
            break;
          }
        case 'reconciliation':
          {
            const [casesRes, summaryRes, reconDashRes, reconMetricsRes] = await Promise.all([axios.get(`/channel-manager/reconciliation/cases`, {
              headers: h
            }).catch(() => ({
              data: {
                cases: []
              }
            })), axios.get(`/channel-manager/model/reconciliation/summary`, {
              headers: h
            }).catch(() => ({
              data: null
            })), axios.get(`/channel-manager/reconciliation/dashboard`, {
              headers: h
            }).catch(() => ({
              data: null
            })), axios.get(`/channel-manager/reconciliation/metrics`, {
              headers: h
            }).catch(() => ({
              data: null
            }))]);
            setReconCases(casesRes.data.cases || []);
            setReconSummary(summaryRes.data);
            setReconDashboard(reconDashRes.data);
            setReconMetrics(reconMetricsRes.data);
            break;
          }
        case 'monitoring':
          {
            const [monOverviewRes, monAlertsRes] = await Promise.all([axios.get(`/channel-manager/monitoring/overview`, {
              headers: h
            }).catch(() => ({
              data: null
            })), axios.get(`/channel-manager/monitoring/alerts`, {
              headers: h
            }).catch(() => ({
              data: {
                alerts: []
              }
            }))]);
            setMonitoringOverview(monOverviewRes.data);
            setMonitoringAlerts(monAlertsRes.data?.alerts || []);
            break;
          }
        default:
          break;
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [propertyId, headers, activeTab]);
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);
  const activateConnection = async id => {
    try {
      await axios.post(`/channel-manager/model/connections/${id}/activate`, {}, {
        headers: headers()
      });
      toast.success('Connection activated');
      fetchAll();
    } catch {
      toast.error('Activation failed');
    }
  };
  const deleteConnection = async id => {
    try {
      await axios.delete(`/channel-manager/model/connections/${id}`, {
        headers: headers()
      });
      toast.success('Connection deleted');
      fetchAll();
    } catch {
      toast.error('Delete failed');
    }
  };
  const resolveCase = async caseId => {
    try {
      await axios.post(`/channel-manager/reconciliation/cases/${caseId}/resolve`, {
        resolution: 'Manually resolved'
      }, {
        headers: headers()
      });
      toast.success('Case resolved');
      fetchAll();
    } catch {
      toast.error('Resolve failed');
    }
  };
  const ignoreCase = async caseId => {
    try {
      await axios.post(`/channel-manager/reconciliation/cases/${caseId}/ignore`, {
        reason: 'Manually ignored'
      }, {
        headers: headers()
      });
      toast.success('Case ignored');
      fetchAll();
    } catch {
      toast.error('Ignore failed');
    }
  };
  const acknowledgeCase = async caseId => {
    try {
      await axios.post(`/channel-manager/reconciliation/cases/${caseId}/acknowledge`, {
        note: 'Under review'
      }, {
        headers: headers()
      });
      toast.success('Case acknowledged');
      fetchAll();
    } catch {
      toast.error('Acknowledge failed');
    }
  };
  const triggerReconciliation = async () => {
    setReconRunning(true);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/reconciliation/run`, {}, {
        headers: headers()
      });
      const r = data.result || {};
      toast.success(`Reconciliation done: ${r.mismatches_found || 0} mismatches, ${r.cases_created || 0} cases created`);
      fetchAll();
    } catch {
      toast.error('Reconciliation failed');
    }
    setReconRunning(false);
  };
  const fetchFilteredCases = async () => {
    const h = headers();
    const params = new URLSearchParams();
    if (reconFilter.status) params.set('status', reconFilter.status);
    if (reconFilter.severity) params.set('severity', reconFilter.severity);
    if (reconFilter.case_type) params.set('case_type', reconFilter.case_type);
    if (reconFilter.provider) params.set('provider', reconFilter.provider);
    try {
      const {
        data
      } = await axios.get(`/channel-manager/reconciliation/cases?${params.toString()}`, {
        headers: h
      });
      setReconCases(data.cases || []);
    } catch {
      toast.error('Filter failed');
    }
  };
  const triggerWorker = async action => {
    setWorkerAction(action);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/ingest/workers/${action}`, {}, {
        headers: headers()
      });
      const r = data.result || {};
      if (action === 'process') {
        toast.success(`Processed: ${r.processed || 0} events (${r.created || 0} created, ${r.updated || 0} updated, ${r.skipped || 0} skipped)`);
      } else if (action === 'replay') {
        toast.success(`Replayed: ${r.replayed || 0} events`);
      } else {
        toast.success(`${action} completed`);
      }
      fetchAll();
    } catch {
      toast.error(`Worker ${action} failed`);
    }
    setWorkerAction(null);
  };
  const ackAlert = async alertId => {
    try {
      await axios.post(`/channel-manager/monitoring/alerts/${alertId}/ack`, {
        note: ''
      }, {
        headers: headers()
      });
      toast.success('Alert acknowledged');
      fetchAll();
    } catch {
      toast.error('Acknowledge failed');
    }
  };
  const resolveAlert = async alertId => {
    try {
      await axios.post(`/channel-manager/monitoring/alerts/${alertId}/resolve`, {
        resolution: 'Manually resolved'
      }, {
        headers: headers()
      });
      toast.success('Alert resolved');
      fetchAll();
    } catch {
      toast.error('Resolve failed');
    }
  };
  const fetchMonitoringMetrics = async () => {
    try {
      const {
        data
      } = await axios.get(`/channel-manager/monitoring/metrics`, {
        headers: headers()
      });
      setMonitoringMetrics(data);
    } catch {
      toast.error('Metrics fetch failed');
    }
  };
  const fetchProviderConfigs = useCallback(async () => {
    try {
      const {
        data
      } = await axios.get(`/channel-manager/config/providers`, {
        headers: headers()
      });
      setProviderConfigs(data.providers || []);
    } catch (e) {
      console.error('Provider config fetch failed:', e);
    }
  }, [headers]);
  useEffect(() => {
    fetchProviderConfigs();
  }, [fetchProviderConfigs]);
  const saveCredentials = async provider => {
    const form = credForms[provider] || {};
    try {
      await axios.post(`/channel-manager/config/providers/${provider}/credentials`, {
        credentials: form,
        property_id: 'default'
      }, {
        headers: headers()
      });
      toast.success('Credentials saved');
      fetchProviderConfigs();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    }
  };
  const deleteCredentials = async provider => {
    try {
      await axios.delete(`/channel-manager/config/providers/${provider}/credentials`, {
        headers: headers()
      });
      toast.success('Credentials deleted');
      setCredForms(prev => ({
        ...prev,
        [provider]: {}
      }));
      fetchProviderConfigs();
    } catch {
      toast.error('Delete failed');
    }
  };
  const runValidation = async provider => {
    setValidationRunning(prev => ({
      ...prev,
      [provider]: true
    }));
    try {
      const {
        data
      } = await axios.post(`/channel-manager/config/providers/${provider}/validate`, {}, {
        headers: headers()
      });
      setValidationResults(prev => ({
        ...prev,
        [provider]: data
      }));
      if (data.overall_status === 'passed') toast.success(`${provider} validation passed!`);else if (data.overall_status === 'partial') toast.info(`${provider}: ${data.passed}/${data.total} checks passed`);else toast.error(`${provider} validation failed`);
      fetchProviderConfigs();
    } catch {
      toast.error('Validation failed');
    }
    setValidationRunning(prev => ({
      ...prev,
      [provider]: false
    }));
  };
  const testConnection = async provider => {
    setValidationRunning(prev => ({
      ...prev,
      [`${provider}_conn`]: true
    }));
    try {
      const {
        data
      } = await axios.post(`/channel-manager/config/providers/${provider}/test-connection`, {}, {
        headers: headers()
      });
      if (data.connected) toast.success(`${provider} connected! (${data.duration_ms}ms)`);else toast.error(`Connection failed: ${data.error}`);
      setValidationResults(prev => ({
        ...prev,
        [`${provider}_conn`]: data
      }));
      fetchProviderConfigs();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Connection test failed');
    }
    setValidationRunning(prev => ({
      ...prev,
      [`${provider}_conn`]: false
    }));
  };
  const eventStats = ingestStatus?.pipeline?.raw_events || {};
  const lineageStats = ingestStatus?.pipeline?.lineage || {};
  return <>
      <div data-testid="data-model-dashboard" className="space-y-6 p-4 md:p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100 flex items-center gap-2">
              <Database className="w-6 h-6 text-cyan-400" />{t("cm.pages_DataModelDashboard.channel_manager")}</h1>
            <p className="text-sm text-zinc-500 mt-1">
              {schema ? `v${schema.model_version} — ${schema.total_collections} collections` : 'Loading...'}{t("cm.pages_DataModelDashboard._hotelrunner_exely")}</p>
          </div>
          <Button data-testid="refresh-btn" variant="outline" size="sm" onClick={fetchAll} disabled={loading} className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="ml-1.5">{t("cm.pages_DataModelDashboard.refresh")}</span>
          </Button>
        </div>

        {/* Pipeline Overview Cards */}
        <div data-testid="collection-overview" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <CollectionCard name="raw_events" count={eventStats.total || 0} icon={FileText} color="bg-amber-500/15 text-amber-400" />
          <CollectionCard name="processed" count={eventStats.processed || 0} icon={CheckCircle} color="bg-emerald-500/15 text-emerald-400" />
          <CollectionCard name="pending" count={eventStats.pending || 0} icon={Clock} color="bg-blue-500/15 text-blue-400" />
          <CollectionCard name="lineage" count={lineageStats.total || 0} icon={GitBranch} color="bg-cyan-500/15 text-cyan-400" />
          <CollectionCard name="connections" count={connections.length} icon={Link2} color="bg-violet-500/15 text-violet-400" />
          <CollectionCard name="recon_cases" count={reconSummary?.total_open || 0} icon={AlertTriangle} color="bg-red-500/15 text-red-400" />
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList data-testid="model-tabs" className="bg-zinc-900 border border-zinc-800 p-1 flex-wrap h-auto">
            <TabsTrigger value="ingest" className="data-[state=active]:bg-zinc-800 text-xs">
              <Activity className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.ingest_pipeline")}</TabsTrigger>
            <TabsTrigger value="lineage" className="data-[state=active]:bg-zinc-800 text-xs">
              <GitBranch className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.lineage")}</TabsTrigger>
            <TabsTrigger value="connections" className="data-[state=active]:bg-zinc-800 text-xs">
              <Link2 className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.connections")}</TabsTrigger>
            <TabsTrigger value="mappings" className="data-[state=active]:bg-zinc-800 text-xs">
              <ArrowRightLeft className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.mappings")}</TabsTrigger>
            <TabsTrigger value="reconciliation" className="data-[state=active]:bg-zinc-800 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.reconciliation")}</TabsTrigger>
            <TabsTrigger value="monitoring" data-testid="monitoring-tab" className="data-[state=active]:bg-zinc-800 text-xs">
              <Radio className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.monitoring")}</TabsTrigger>
            <TabsTrigger value="provider-config" data-testid="provider-config-tab" className="data-[state=active]:bg-zinc-800 text-xs">
              <Shield className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.provider_config")}</TabsTrigger>
          </TabsList>

          {/* Ingest Pipeline Tab */}
          <TabsContent value="ingest">
            <div className="space-y-4">
              {/* Worker Controls */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                      <Server className="w-4 h-4 text-cyan-400" />{t("cm.pages_DataModelDashboard.workers")}</CardTitle>
                    <div className="flex gap-2">
                      <Button data-testid="trigger-process" size="sm" variant="outline" className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10" onClick={() => triggerWorker('process')} disabled={!!workerAction}>
                        {workerAction === 'process' ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Play className="w-3 h-3 mr-1" />}{t("cm.pages_DataModelDashboard.process_pending")}</Button>
                      <Button data-testid="trigger-replay" size="sm" variant="outline" className="h-7 text-xs border-amber-600 text-amber-400 hover:bg-amber-500/10" onClick={() => triggerWorker('replay')} disabled={!!workerAction}>
                        {workerAction === 'replay' ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Repeat className="w-3 h-3 mr-1" />}{t("cm.pages_DataModelDashboard.replay_failed")}</Button>
                      <Button data-testid="trigger-hr-pull" size="sm" variant="outline" className="h-7 text-xs border-blue-600 text-blue-400 hover:bg-blue-500/10" onClick={() => triggerWorker('pull/hotelrunner')} disabled={!!workerAction}>
                        <Download className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.hr_pull")}</Button>
                      <Button data-testid="trigger-exely-pull" size="sm" variant="outline" className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10" onClick={() => triggerWorker('pull/exely')} disabled={!!workerAction}>
                        <Download className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.exely_pull")}</Button>
                    </div>
                  </div>
                </CardHeader>
                {ingestStatus?.workers && <CardContent>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                      {Object.entries(ingestStatus.workers).map(([name, w]) => <div key={name} className="p-2 rounded bg-zinc-800/50 border border-zinc-700/50">
                          <p className="text-xs font-mono text-zinc-400">{name.replace('_', ' ')}</p>
                          <p className="text-xs text-zinc-500 mt-1">{t("cm.pages_DataModelDashboard.last")}{w.last_run ? new Date(w.last_run).toLocaleTimeString() : 'never'}
                          </p>
                          <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.interval")}{w.interval_seconds}s</p>
                        </div>)}
                    </div>
                  </CardContent>}
              </Card>

              {/* Raw Events */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-amber-400" />{t("cm.pages_DataModelDashboard.raw_channel_events")}{rawEvents.length})
                    <div className="flex gap-1 ml-auto">
                      <Badge className="bg-emerald-500/15 text-emerald-400 text-xs">{eventStats.processed || 0}{t("cm.pages_DataModelDashboard.processed")}</Badge>
                      <Badge className="bg-red-500/15 text-red-400 text-xs">{eventStats.failed || 0}{t("cm.pages_DataModelDashboard.failed")}</Badge>
                      <Badge className="bg-zinc-500/15 text-zinc-400 text-xs">{eventStats.duplicate || 0}{t("cm.pages_DataModelDashboard.dup")}</Badge>
                      <Badge className="bg-amber-500/15 text-amber-400 text-xs">{eventStats.stale || 0}{t("cm.pages_DataModelDashboard.stale")}</Badge>
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {rawEvents.length === 0 ? <p data-testid="no-raw-events" className="text-zinc-500 text-sm text-center py-6">{t("cm.pages_DataModelDashboard.no_raw_events")}</p> : <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.provider")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.ext_res_id")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.event_type")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.via")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.status")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.received")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rawEvents.slice(0, 20).map(e => <tr key={e.id} data-testid={`raw-event-${e.id}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                              <td className="py-2 px-3"><ProviderBadge provider={e.provider} /></td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{e.external_reservation_id || '-'}</td>
                              <td className="py-2 px-3 text-zinc-300 text-xs">{e.event_type}</td>
                              <td className="py-2 px-3"><Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{e.received_via}</Badge></td>
                              <td className="py-2 px-3"><ProcessingBadge status={e.processing_status} /></td>
                              <td className="py-2 px-3 text-zinc-500 text-xs">{new Date(e.received_at).toLocaleString()}</td>
                            </tr>)}
                        </tbody>
                      </table>
                    </div>}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Lineage Tab */}
          <TabsContent value="lineage">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <GitBranch className="w-4 h-4 text-emerald-400" />{t("cm.pages_DataModelDashboard.reservation_lineage")}{lineages.length})
                  {lineageStats.by_status && Object.entries(lineageStats.by_status).map(([s, c]) => <Badge key={s} className="bg-zinc-700/50 text-zinc-300 text-xs ml-1">{s}: {c}</Badge>)}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {lineages.length === 0 ? <p data-testid="no-lineages" className="text-zinc-500 text-sm text-center py-6">{t("cm.pages_DataModelDashboard.no_reservation_lineage_records")}</p> : <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.provider")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.external_id")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.guest")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.stay")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.amount")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.source")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.ver")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.status")}</th>
                          <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.decision")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lineages.map(l => <tr key={l.id} data-testid={`lineage-${l.id}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                            <td className="py-2 px-3"><ProviderBadge provider={l.provider} /></td>
                            <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{l.external_reservation_id}</td>
                            <td className="py-2 px-3 text-zinc-300 text-xs">{l.guest_name || '-'}</td>
                            <td className="py-2 px-3 text-zinc-400 text-xs">{l.arrival_date} → {l.departure_date}</td>
                            <td className="py-2 px-3 text-zinc-200 text-xs font-mono">{l.total_amount} {l.currency}</td>
                            <td className="py-2 px-3 text-zinc-500 text-xs">{l.source_system}</td>
                            <td className="py-2 px-3 text-zinc-400 text-xs">v{l.version}</td>
                            <td className="py-2 px-3">
                              <div className="flex items-center gap-1.5">
                                <StatusDot status={l.status} />
                                <span className="text-xs text-zinc-300">{l.status}</span>
                              </div>
                            </td>
                            <td className="py-2 px-3">
                              <Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{l.last_decision}</Badge>
                            </td>
                          </tr>)}
                      </tbody>
                    </table>
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Connections Tab */}
          <TabsContent value="connections">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <Server className="w-4 h-4 text-blue-400" />{t("cm.pages_DataModelDashboard.provider_connections")}{connections.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {connections.length === 0 ? <p data-testid="no-connections" className="text-zinc-500 text-sm text-center py-6">{t("cm.pages_DataModelDashboard.no_connections_configured")}</p> : <div className="space-y-3">
                    {connections.map(c => <div key={c.id} data-testid={`connection-${c.provider}`} className="flex items-center justify-between p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                        <div className="flex items-center gap-3 min-w-0">
                          <StatusDot status={c.status} />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-zinc-200 truncate">{c.display_name}</p>
                            <p className="text-xs text-zinc-500">{c.property_id}{t("cm.pages_DataModelDashboard._syncs")}{c.total_syncs}{t("cm.pages_DataModelDashboard._errors")}{c.total_errors}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-2 shrink-0">
                          <ProviderBadge provider={c.provider} />
                          <Badge className="bg-zinc-700/50 text-zinc-300 border-zinc-600 text-xs">{c.status}</Badge>
                          {c.status === 'draft' && <Button data-testid={`activate-${c.provider}`} size="sm" variant="outline" className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10" onClick={() => activateConnection(c.id)}>
                              <CheckCircle className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.activate")}</Button>}
                          <Button data-testid={`delete-${c.provider}`} size="sm" variant="ghost" className="h-7 text-xs text-red-400 hover:bg-red-500/10" onClick={() => deleteConnection(c.id)}>
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>)}
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Mappings Tab */}
          <TabsContent value="mappings">
            <div className="space-y-4">
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <Grid3X3 className="w-4 h-4 text-cyan-400" />{t("cm.pages_DataModelDashboard.room_mappings")}{roomMappings.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {roomMappings.length === 0 ? <p className="text-zinc-500 text-sm text-center py-4">{t("cm.pages_DataModelDashboard.no_room_mappings")}</p> : <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.provider")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.pms_room_type")}</th>
                            <th className="py-2 px-1">→</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.provider_code")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.status")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {roomMappings.map(m => <tr key={m.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                              <td className="py-2 px-3"><ProviderBadge provider={m.provider} /></td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.pms_room_type_id}</td>
                              <td className="py-2 px-1 text-zinc-600">→</td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.provider_room_code}</td>
                              <td className="py-2 px-3">
                                <Badge className={m.is_active ? 'bg-emerald-500/15 text-emerald-400 text-xs' : 'bg-zinc-500/15 text-zinc-400 text-xs'}>
                                  {m.is_active ? 'Active' : 'Inactive'}
                                </Badge>
                              </td>
                            </tr>)}
                        </tbody>
                      </table>
                    </div>}
                </CardContent>
              </Card>
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <Layers className="w-4 h-4 text-violet-400" />{t("cm.pages_DataModelDashboard.rate_plan_mappings")}{ratePlanMappings.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {ratePlanMappings.length === 0 ? <p className="text-zinc-500 text-sm text-center py-4">{t("cm.pages_DataModelDashboard.no_rate_plan_mappings")}</p> : <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.provider")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.pms_rate_plan")}</th>
                            <th className="py-2 px-1">→</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.provider_code")}</th>
                            <th className="text-left py-2 px-3">{t("cm.pages_DataModelDashboard.status")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ratePlanMappings.map(m => <tr key={m.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                              <td className="py-2 px-3"><ProviderBadge provider={m.provider} /></td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.pms_rate_plan_id}</td>
                              <td className="py-2 px-1 text-zinc-600">→</td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.provider_rate_code}</td>
                              <td className="py-2 px-3">
                                <Badge className={m.is_active ? 'bg-emerald-500/15 text-emerald-400 text-xs' : 'bg-zinc-500/15 text-zinc-400 text-xs'}>
                                  {m.is_active ? 'Active' : 'Inactive'}
                                </Badge>
                              </td>
                            </tr>)}
                        </tbody>
                      </table>
                    </div>}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Reconciliation Tab */}
          <TabsContent value="reconciliation">
            <div className="space-y-4">
              {/* Reconciliation Worker & Controls */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                      <Shield className="w-4 h-4 text-cyan-400" />{t("cm.pages_DataModelDashboard.reconciliation_engine")}</CardTitle>
                    <div className="flex gap-2">
                      <Button data-testid="trigger-reconciliation" size="sm" variant="outline" className="h-7 text-xs border-cyan-600 text-cyan-400 hover:bg-cyan-500/10" onClick={triggerReconciliation} disabled={reconRunning}>
                        {reconRunning ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Play className="w-3 h-3 mr-1" />}{t("cm.pages_DataModelDashboard.run_reconciliation")}</Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    {reconDashboard && <>
                        <div className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                          <p className="text-2xl font-bold text-red-400">{reconDashboard.open_cases}</p>
                          <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.open_cases")}</p>
                        </div>
                        {Object.entries(reconDashboard.severity_counts || {}).map(([sev, count]) => <div key={sev} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                            <p className={`text-2xl font-bold ${sev === 'critical' ? 'text-red-400' : sev === 'high' ? 'text-amber-400' : sev === 'medium' ? 'text-amber-400' : 'text-zinc-400'}`}>{count}</p>
                            <p className="text-xs text-zinc-500 capitalize">{sev}</p>
                          </div>)}
                      </>}
                    {reconDashboard?.worker && <div className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                        <p className="text-2xl font-bold text-cyan-400">{reconDashboard.worker.runs_total}</p>
                        <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.total_runs")}</p>
                      </div>}
                  </div>
                </CardContent>
              </Card>

              {/* Metrics */}
              {reconMetrics && <Card data-testid="recon-metrics" className="bg-zinc-900/60 border-zinc-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-violet-400" />{t("cm.pages_DataModelDashboard.mismatch_metrics")}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                      {[{
                    label: 'Missing Res.',
                    value: reconMetrics.missing_reservations,
                    color: 'text-amber-400'
                  }, {
                    label: 'Ghost Res.',
                    value: reconMetrics.ghost_reservations,
                    color: 'text-amber-400'
                  }, {
                    label: 'Status Conflict',
                    value: reconMetrics.status_conflicts,
                    color: 'text-red-400'
                  }, {
                    label: 'Amount Mismatch',
                    value: reconMetrics.amount_mismatches,
                    color: 'text-yellow-400'
                  }, {
                    label: 'Date Conflict',
                    value: reconMetrics.date_conflicts,
                    color: 'text-amber-400'
                  }, {
                    label: 'Duplicates',
                    value: reconMetrics.duplicate_reservations,
                    color: 'text-zinc-400'
                  }].map(m => <div key={m.label} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                          <p className={`text-xl font-bold ${m.color}`}>{m.value || 0}</p>
                          <p className="text-xs text-zinc-500">{m.label}</p>
                        </div>)}
                    </div>
                  </CardContent>
                </Card>}

              {/* Provider Breakdown */}
              {reconDashboard?.provider_breakdown && Object.keys(reconDashboard.provider_breakdown).length > 0 && <Card className="bg-zinc-900/60 border-zinc-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm text-zinc-200">{t("cm.pages_DataModelDashboard.provider_breakdown")}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-4 flex-wrap">
                      {Object.entries(reconDashboard.provider_breakdown).map(([prov, count]) => <div key={prov} className="flex items-center gap-2">
                          <ProviderBadge provider={prov} />
                          <span className="text-zinc-200 font-bold">{count}</span>
                          <span className="text-zinc-500 text-xs">{t("cm.pages_DataModelDashboard.open_cases")}</span>
                        </div>)}
                    </div>
                  </CardContent>
                </Card>}

              {/* Filters */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardContent className="p-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Search className="w-4 h-4 text-zinc-500" />
                    <select data-testid="filter-status" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300" value={reconFilter.status} onChange={e => setReconFilter(f => ({
                    ...f,
                    status: e.target.value
                  }))}>
                      <option value="">{t("cm.pages_DataModelDashboard.all_status")}</option>
                      <option value="open">{t("cm.pages_DataModelDashboard.open")}</option>
                      <option value="acknowledged">{t("cm.pages_DataModelDashboard.acknowledged")}</option>
                      <option value="resolved">{t("cm.pages_DataModelDashboard.resolved")}</option>
                      <option value="ignored">{t("cm.pages_DataModelDashboard.ignored")}</option>
                    </select>
                    <select data-testid="filter-severity" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300" value={reconFilter.severity} onChange={e => setReconFilter(f => ({
                    ...f,
                    severity: e.target.value
                  }))}>
                      <option value="">{t("cm.pages_DataModelDashboard.all_severity")}</option>
                      <option value="critical">{t("cm.pages_DataModelDashboard.critical")}</option>
                      <option value="high">{t("cm.pages_DataModelDashboard.high")}</option>
                      <option value="medium">{t("cm.pages_DataModelDashboard.medium")}</option>
                      <option value="low">{t("cm.pages_DataModelDashboard.low")}</option>
                    </select>
                    <select data-testid="filter-type" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300" value={reconFilter.case_type} onChange={e => setReconFilter(f => ({
                    ...f,
                    case_type: e.target.value
                  }))}>
                      <option value="">{t("cm.pages_DataModelDashboard.all_types")}</option>
                      <option value="missing_reservation">{t("cm.pages_DataModelDashboard.missing_reservation")}</option>
                      <option value="ghost_reservation">{t("cm.pages_DataModelDashboard.ghost_reservation")}</option>
                      <option value="amount_mismatch">{t("cm.pages_DataModelDashboard.amount_mismatch")}</option>
                      <option value="date_conflict">{t("cm.pages_DataModelDashboard.date_conflict")}</option>
                      <option value="status_conflict">{t("cm.pages_DataModelDashboard.status_conflict")}</option>
                      <option value="duplicate_reservation">{t("cm.pages_DataModelDashboard.duplicate_reservation")}</option>
                      <option value="missing_mapping">{t("cm.pages_DataModelDashboard.missing_mapping")}</option>
                    </select>
                    <select data-testid="filter-provider" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300" value={reconFilter.provider} onChange={e => setReconFilter(f => ({
                    ...f,
                    provider: e.target.value
                  }))}>
                      <option value="">{t("cm.pages_DataModelDashboard.all_providers")}</option>
                      <option value="hotelrunner">{t("cm.pages_DataModelDashboard.hotelrunner")}</option>
                      <option value="exely">{t("cm.pages_DataModelDashboard.exely")}</option>
                    </select>
                    <Button data-testid="apply-filters" size="sm" variant="outline" className="h-7 text-xs border-zinc-700 text-zinc-300" onClick={fetchFilteredCases}>{t("cm.pages_DataModelDashboard.apply")}</Button>
                  </div>
                </CardContent>
              </Card>

              {/* Cases List */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />{t("cm.pages_DataModelDashboard.cases")}{reconCases.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {reconCases.length === 0 ? <p data-testid="no-recon-cases" className="text-zinc-500 text-sm text-center py-6">{t("cm.pages_DataModelDashboard.no_cases_found")}</p> : <div className="space-y-2">
                      {reconCases.map(c => <div key={c.id} data-testid={`recon-case-${c.id}`} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <StatusDot status={c.status} />
                                <ProviderBadge provider={c.provider} />
                                <Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{c.case_type?.replace(/_/g, ' ')}</Badge>
                                <Badge className={`text-xs border ${c.severity === 'critical' ? 'bg-red-500/15 text-red-400 border-red-500/30' : c.severity === 'high' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : c.severity === 'medium' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'}`}>{c.severity}</Badge>
                                <Badge className={`text-xs border ${c.status === 'open' ? 'bg-red-500/15 text-red-400 border-red-500/30' : c.status === 'acknowledged' ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' : c.status === 'resolved' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'}`}>{c.status}</Badge>
                              </div>
                              <p className="text-xs text-zinc-400 truncate">{c.description}</p>
                              {c.external_reservation_id && <p className="text-xs text-zinc-600 font-mono mt-0.5">{t("cm.pages_DataModelDashboard.ext")}{c.external_reservation_id}</p>}
                              {c.suggested_action && <p className="text-xs text-cyan-400/70 mt-0.5">{c.suggested_action}</p>}
                              {c.resolution && <p className="text-xs text-emerald-400/70 mt-0.5">{t("cm.pages_DataModelDashboard.resolution")}{c.resolution}</p>}
                            </div>
                            {(c.status === 'open' || c.status === 'acknowledged') && <div className="flex gap-1 shrink-0">
                                {c.status === 'open' && <Button data-testid={`ack-case-${c.id}`} size="sm" variant="outline" className="h-7 text-xs border-blue-600 text-blue-400 hover:bg-blue-500/10" onClick={() => acknowledgeCase(c.id)}>
                                    <Eye className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.ack")}</Button>}
                                <Button data-testid={`resolve-case-${c.id}`} size="sm" variant="outline" className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10" onClick={() => resolveCase(c.id)}>
                                  <CheckCircle className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.resolve")}</Button>
                                <Button data-testid={`ignore-case-${c.id}`} size="sm" variant="outline" className="h-7 text-xs border-zinc-600 text-zinc-400 hover:bg-zinc-500/10" onClick={() => ignoreCase(c.id)}>
                                  <XCircle className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.ignore")}</Button>
                              </div>}
                          </div>
                        </div>)}
                    </div>}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Monitoring Tab */}
          <TabsContent value="monitoring">
            <div data-testid="monitoring-panel" className="space-y-4">
              {/* System Health Overview */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                    <Heart className="w-4 h-4 text-rose-400" />{t("cm.pages_DataModelDashboard.system_health_overview")}<Button data-testid="monitoring-refresh-btn" variant="ghost" size="sm" onClick={fetchAll} className="ml-auto text-zinc-400 hover:text-zinc-200 h-7 px-2">
                      <RefreshCw className="w-3.5 h-3.5" />
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {monitoringOverview ? <>
                      {/* Health Score */}
                      <div data-testid="system-health-score" className="flex items-center gap-4 p-4 rounded-lg bg-zinc-800/50">
                        <div className={`w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold ${monitoringOverview.system_health === 'healthy' ? 'bg-emerald-500/20 text-emerald-400 ring-2 ring-emerald-500/30' : monitoringOverview.system_health === 'degraded' ? 'bg-amber-500/20 text-amber-400 ring-2 ring-amber-500/30' : 'bg-red-500/20 text-red-400 ring-2 ring-red-500/30'}`}>
                          {monitoringOverview.system_health === 'healthy' ? <CheckCircle className="w-6 h-6" /> : monitoringOverview.system_health === 'degraded' ? <AlertTriangle className="w-6 h-6" /> : <XCircle className="w-6 h-6" />}
                        </div>
                        <div>
                          <p className="text-lg font-bold text-zinc-100 capitalize">{monitoringOverview.system_health}</p>
                          <p className="text-xs text-zinc-500">
                            {monitoringOverview.providers}{t("cm.pages_DataModelDashboard.providers")}{monitoringOverview.active_alerts}{t("cm.pages_DataModelDashboard.active_alerts")}{monitoringOverview.reconciliation_open_cases}{t("cm.pages_DataModelDashboard.open_cases")}</p>
                        </div>
                      </div>

                      {/* Domain Status Cards */}
                      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                        {[{
                      label: 'Providers',
                      status: Object.values(monitoringOverview.provider_statuses || {}).includes('critical') ? 'critical' : Object.values(monitoringOverview.provider_statuses || {}).every(s => s === 'healthy') ? 'healthy' : 'degraded',
                      icon: Server
                    }, {
                      label: 'Ingest',
                      status: monitoringOverview.ingest_status,
                      icon: Activity
                    }, {
                      label: 'ARI Push',
                      status: monitoringOverview.ari_status,
                      icon: Zap
                    }, {
                      label: 'Reconciliation',
                      status: monitoringOverview.recon_status,
                      icon: Shield
                    }, {
                      label: 'Queue',
                      status: monitoringOverview.queue_status,
                      icon: Layers
                    }].map(d => <div key={d.label} data-testid={`health-domain-${d.label.toLowerCase().replace(/ /g, '-')}`} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                            <div className="flex items-center gap-2 mb-1.5">
                              <d.icon className="w-3.5 h-3.5 text-zinc-400" />
                              <span className="text-xs font-medium text-zinc-400">{d.label}</span>
                            </div>
                            <Badge className={`text-xs border ${d.status === 'healthy' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : d.status === 'degraded' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : d.status === 'critical' ? 'bg-red-500/15 text-red-400 border-red-500/30' : 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'}`}>{d.status || 'unknown'}</Badge>
                          </div>)}
                      </div>

                      {/* Provider Health Detail */}
                      {monitoringOverview.provider_statuses && Object.keys(monitoringOverview.provider_statuses).length > 0 && <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {Object.entries(monitoringOverview.provider_statuses).map(([name, status]) => <div key={name} data-testid={`provider-health-${name}`} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <ProviderBadge provider={name} />
                                <Badge className={`text-xs border ${status === 'healthy' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : status === 'inactive' ? 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'}`}>{status}</Badge>
                              </div>
                            </div>)}
                        </div>}

                      {/* Quick Stats */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="p-3 rounded-lg bg-zinc-800/50 text-center">
                          <p className="text-2xl font-bold text-zinc-100">{monitoringOverview.active_alerts}</p>
                          <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.active_alerts")}</p>
                        </div>
                        <div className="p-3 rounded-lg bg-zinc-800/50 text-center">
                          <p className="text-2xl font-bold text-red-400">{monitoringOverview.critical_alerts}</p>
                          <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.critical_alerts")}</p>
                        </div>
                        <div className="p-3 rounded-lg bg-zinc-800/50 text-center">
                          <p className="text-2xl font-bold text-zinc-100">{monitoringOverview.queue_depth}</p>
                          <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.queue_depth")}</p>
                        </div>
                        <div className="p-3 rounded-lg bg-zinc-800/50 text-center">
                          <p className="text-2xl font-bold text-amber-400">{monitoringOverview.reconciliation_open_cases}</p>
                          <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.open_cases")}</p>
                        </div>
                      </div>
                    </> : <p className="text-sm text-zinc-500 text-center py-6">{t("cm.pages_DataModelDashboard.loading_monitoring_data")}</p>}
                </CardContent>
              </Card>

              {/* Active Alerts */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                    <Bell className="w-4 h-4 text-amber-400" />{t("cm.pages_DataModelDashboard.active_alerts")}<Badge data-testid="alert-count-badge" className="ml-2 bg-zinc-800 text-zinc-300 border border-zinc-700 text-xs">
                      {monitoringAlerts.filter(a => a.status !== 'resolved').length}
                    </Badge>
                    <Button data-testid="fetch-metrics-btn" variant="ghost" size="sm" onClick={fetchMonitoringMetrics} className="ml-auto text-zinc-400 hover:text-zinc-200 h-7 px-2">
                      <BarChart3 className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.metrics")}</Button>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {monitoringAlerts.length === 0 ? <div data-testid="no-alerts-message" className="text-center py-8">
                      <CheckCircle className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
                      <p className="text-sm text-zinc-400">{t("cm.pages_DataModelDashboard.no_active_alerts")}</p>
                      <p className="text-xs text-zinc-600 mt-1">{t("cm.pages_DataModelDashboard.system_is_operating_normally")}</p>
                    </div> : <div className="space-y-2 max-h-[400px] overflow-y-auto">
                      {monitoringAlerts.map(alert => <div key={alert.id} data-testid={`alert-item-${alert.id}`} className={`p-3 rounded-lg border ${alert.severity === 'critical' ? 'bg-red-950/30 border-red-800/50' : alert.severity === 'high' ? 'bg-amber-950/30 border-amber-800/50' : 'bg-zinc-800/50 border-zinc-700/50'}`}>
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge className={`text-xs border ${alert.severity === 'critical' ? 'bg-red-500/15 text-red-400 border-red-500/30' : alert.severity === 'high' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : alert.severity === 'medium' ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' : 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'}`}>{alert.severity}</Badge>
                                <Badge className={`text-xs border ${alert.status === 'active' ? 'bg-red-500/15 text-red-400 border-red-500/30' : alert.status === 'acknowledged' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'}`}>{alert.status}</Badge>
                                {alert.provider && <ProviderBadge provider={alert.provider} />}
                              </div>
                              <p className="text-sm font-medium text-zinc-200">{alert.title}</p>
                              <p className="text-xs text-zinc-500 mt-0.5">{alert.details}</p>
                              <p className="text-xs text-zinc-600 mt-1 font-mono">
                                {alert.alert_type} | {alert.created_at ? new Date(alert.created_at).toLocaleString('tr-TR') : ''}
                              </p>
                            </div>
                            {alert.status !== 'resolved' && <div className="flex gap-1.5 shrink-0">
                                {alert.status === 'active' && <Button data-testid={`ack-alert-${alert.id}`} variant="outline" size="sm" className="h-7 px-2 text-xs border-amber-700 text-amber-400 hover:bg-amber-900/30" onClick={() => ackAlert(alert.id)}>
                                    <Eye className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.ack")}</Button>}
                                <Button data-testid={`resolve-alert-${alert.id}`} variant="outline" size="sm" className="h-7 px-2 text-xs border-emerald-700 text-emerald-400 hover:bg-emerald-900/30" onClick={() => resolveAlert(alert.id)}>
                                  <CheckCircle className="w-3 h-3 mr-1" />{t("cm.pages_DataModelDashboard.resolve")}</Button>
                              </div>}
                          </div>
                        </div>)}
                    </div>}
                </CardContent>
              </Card>

              {/* Detailed Metrics Panel */}
              {monitoringMetrics && <Card className="bg-zinc-900/60 border-zinc-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-cyan-400" />{t("cm.pages_DataModelDashboard.detailed_metrics")}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {/* Ingest Metrics */}
                      <div className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                        <h4 className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
                          <Activity className="w-3 h-3" />{t("cm.pages_DataModelDashboard.ingest_pipeline")}</h4>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.total_events")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.ingest_health?.total_events || 0}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.pending")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.ingest_health?.pending || 0}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.failed_24h")}</span><span className="text-red-400 font-mono">{monitoringMetrics.ingest_health?.failed_recent_24h || 0}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.duplicate_rate")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.ingest_health?.duplicate_rate || 0}%</span></div>
                        </div>
                      </div>

                      {/* ARI Metrics */}
                      <div className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                        <h4 className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
                          <Zap className="w-3 h-3" />{t("cm.pages_DataModelDashboard.ari_push_engine")}</h4>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.pushes_24h")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.ari_health?.total_pushes_24h || 0}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.success_rate")}</span><span className="text-emerald-400 font-mono">{monitoringMetrics.ari_health?.success_rate || 0}%</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.p50_latency")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.ari_health?.latency_p50 || 0}{t("cm.pages_DataModelDashboard.ms")}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.p95_latency")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.ari_health?.latency_p95 || 0}{t("cm.pages_DataModelDashboard.ms")}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.pending_sets")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.ari_health?.pending_changesets || 0}</span></div>
                        </div>
                      </div>

                      {/* Reconciliation Metrics */}
                      <div className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                        <h4 className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
                          <Shield className="w-3 h-3" />{t("cm.pages_DataModelDashboard.reconciliation")}</h4>
                        <div className="space-y-1.5 text-xs">
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.open_cases")}</span><span className="text-zinc-200 font-mono">{monitoringMetrics.reconciliation_health?.open_cases || 0}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.critical")}</span><span className="text-red-400 font-mono">{monitoringMetrics.reconciliation_health?.critical_count || 0}</span></div>
                          <div className="flex justify-between"><span className="text-zinc-500">{t("cm.pages_DataModelDashboard.new_24h")}</span><span className="text-amber-400 font-mono">{monitoringMetrics.reconciliation_health?.case_growth_rate_24h || 0}</span></div>
                          {monitoringMetrics.reconciliation_health?.cases_by_type && Object.entries(monitoringMetrics.reconciliation_health.cases_by_type).map(([t, c]) => <div key={t} className="flex justify-between"><span className="text-zinc-600 truncate">{t}</span><span className="text-zinc-300 font-mono">{c}</span></div>)}
                        </div>
                      </div>
                    </div>

                    {/* Queue & Worker Details */}
                    {monitoringMetrics.queue_health && <div className="mt-4 p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                        <h4 className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
                          <Layers className="w-3 h-3" />{t("cm.pages_DataModelDashboard.queue_workers")}</h4>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                          <div><span className="text-zinc-500 block">{t("cm.pages_DataModelDashboard.queue_depth")}</span><span className="text-zinc-200 font-mono text-sm">{monitoringMetrics.queue_health.queue_depth}</span></div>
                          <div><span className="text-zinc-500 block">{t("cm.pages_DataModelDashboard.retry_backlog")}</span><span className="text-zinc-200 font-mono text-sm">{monitoringMetrics.queue_health.retry_backlog}</span></div>
                          <div><span className="text-zinc-500 block">{t("cm.pages_DataModelDashboard.stalled_workers")}</span><span className="text-red-400 font-mono text-sm">{monitoringMetrics.queue_health.stalled_workers?.length || 0}</span></div>
                          <div><span className="text-zinc-500 block">{t("cm.pages_DataModelDashboard.status")}</span>
                            <Badge className={`text-xs border ${monitoringMetrics.queue_health.status === 'healthy' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'}`}>{monitoringMetrics.queue_health.status}</Badge>
                          </div>
                        </div>
                        {monitoringMetrics.queue_health.workers && <div className="space-y-1">
                            {Object.entries(monitoringMetrics.queue_health.workers).map(([name, w]) => <div key={name} className="flex items-center justify-between text-xs py-1 border-t border-zinc-700/30">
                                <span className="text-zinc-400 font-mono">{name}</span>
                                <div className="flex items-center gap-2">
                                  {w.is_stalled && <Badge className="bg-red-500/15 text-red-400 border border-red-500/30 text-xs">{t("cm.pages_DataModelDashboard.stalled")}</Badge>}
                                  <span className="text-zinc-500">{w.last_run ? new Date(w.last_run).toLocaleTimeString('tr-TR') : 'never'}</span>
                                  <span className={`w-2 h-2 rounded-full ${w.running ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
                                </div>
                              </div>)}
                          </div>}
                      </div>}
                  </CardContent>
                </Card>}

              {/* Slack Alert Configuration */}
              <SlackConfigPanel headers={headers} />

              {/* 24h Trend Charts */}
              <TrendCharts headers={headers} />
            </div>
          </TabsContent>
          <TabsContent value="provider-config">
            <div className="space-y-6">
              {providerConfigs.map(p => <Card key={p.provider} data-testid={`provider-config-${p.provider}`} className="bg-zinc-900/60 border-zinc-800">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${p.provider === 'hotelrunner' ? 'bg-blue-500/15 text-blue-400' : 'bg-emerald-500/15 text-emerald-400'}`}>
                          <Server className="w-5 h-5" />
                        </div>
                        <div>
                          <CardTitle className="text-base text-zinc-100">{p.display_name}</CardTitle>
                          <div className="flex items-center gap-2 mt-1">
                            <StatusDot status={p.connection.status} />
                            <span className="text-xs text-zinc-500">{p.connection.status}</span>
                            {p.has_credentials && <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs border">{t("cm.pages_DataModelDashboard.credentials_saved")}</Badge>}
                            {!p.has_credentials && <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30 text-xs border">{t("cm.pages_DataModelDashboard.no_credentials")}</Badge>}
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button data-testid={`test-conn-${p.provider}`} variant="outline" size="sm" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 text-xs" onClick={() => testConnection(p.provider)} disabled={validationRunning[`${p.provider}_conn`] || !p.has_credentials}>
                          {validationRunning[`${p.provider}_conn`] ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Zap className="w-3.5 h-3.5 mr-1" />}{t("cm.pages_DataModelDashboard.test_connection")}</Button>
                        <Button data-testid={`validate-${p.provider}`} variant="outline" size="sm" className="border-cyan-700 text-cyan-300 hover:bg-cyan-900/30 text-xs" onClick={() => runValidation(p.provider)} disabled={validationRunning[p.provider]}>
                          {validationRunning[p.provider] ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Play className="w-3.5 h-3.5 mr-1" />}{t("cm.pages_DataModelDashboard.full_validation")}</Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Credential Form */}
                    <div className="p-4 bg-zinc-950/50 rounded-lg border border-zinc-800/50">
                      <h4 className="text-sm font-medium text-zinc-300 mb-3 flex items-center gap-2">
                        <Shield className="w-4 h-4 text-amber-400" />{t("cm.pages_DataModelDashboard.credentials")}</h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {p.fields.map(field => <div key={field.key}>
                            <label className="block text-xs text-zinc-500 mb-1">
                              {field.label} {field.required && <span className="text-red-400">*</span>}
                            </label>
                            <input data-testid={`cred-${p.provider}-${field.key}`} type={field.type === 'password' ? 'password' : 'text'} placeholder={p.credentials?.fields?.[field.key] || `Enter ${field.label}`} className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none" value={credForms[p.provider]?.[field.key] || ''} onChange={e => setCredForms(prev => ({
                        ...prev,
                        [p.provider]: {
                          ...(prev[p.provider] || {}),
                          [field.key]: e.target.value
                        }
                      }))} />
                          </div>)}
                      </div>
                      <div className="flex gap-2 mt-3">
                        <Button data-testid={`save-creds-${p.provider}`} size="sm" className="bg-cyan-600 hover:bg-cyan-700 text-white text-xs" onClick={() => saveCredentials(p.provider)} disabled={!credForms[p.provider] || Object.values(credForms[p.provider] || {}).every(v => !v)}>
                          <CheckCircle className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.save_credentials")}</Button>
                        {p.has_credentials && <Button data-testid={`delete-creds-${p.provider}`} variant="outline" size="sm" className="border-red-700 text-red-400 hover:bg-red-900/30 text-xs" onClick={() => deleteCredentials(p.provider)}>
                            <Trash2 className="w-3.5 h-3.5 mr-1" />{t("cm.pages_DataModelDashboard.remove")}</Button>}
                      </div>
                    </div>

                    {/* Connection Info */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="p-3 bg-zinc-950/50 rounded-lg border border-zinc-800/50">
                        <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.status")}</p>
                        <p className="text-sm font-medium text-zinc-200 flex items-center gap-1.5 mt-1">
                          <StatusDot status={p.connection.status} /> {p.connection.status}
                        </p>
                      </div>
                      <div className="p-3 bg-zinc-950/50 rounded-lg border border-zinc-800/50">
                        <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.room_mappings")}</p>
                        <p className="text-sm font-medium text-zinc-200 mt-1">{p.mappings.rooms}</p>
                      </div>
                      <div className="p-3 bg-zinc-950/50 rounded-lg border border-zinc-800/50">
                        <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.rate_plan_mappings")}</p>
                        <p className="text-sm font-medium text-zinc-200 mt-1">{p.mappings.rate_plans}</p>
                      </div>
                      <div className="p-3 bg-zinc-950/50 rounded-lg border border-zinc-800/50">
                        <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.last_sync")}</p>
                        <p className="text-sm font-medium text-zinc-200 mt-1 truncate">
                          {p.connection.last_successful_sync ? new Date(p.connection.last_successful_sync).toLocaleString('tr-TR') : 'Never'}
                        </p>
                      </div>
                    </div>

                    {/* Validation Results */}
                    {validationResults[p.provider] && <div className="p-4 bg-zinc-950/50 rounded-lg border border-zinc-800/50">
                        <div className="flex items-center justify-between mb-3">
                          <h4 className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                            <BarChart3 className="w-4 h-4 text-cyan-400" />{t("cm.pages_DataModelDashboard.validation_results")}</h4>
                          <Badge className={`text-xs border ${validationResults[p.provider].overall_status === 'passed' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : validationResults[p.provider].overall_status === 'partial' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'}`}>
                            {validationResults[p.provider].passed}/{validationResults[p.provider].total}{t("cm.pages_DataModelDashboard.passed")}</Badge>
                        </div>
                        <div className="space-y-2">
                          {validationResults[p.provider].results?.map((r, i) => <div key={i} data-testid={`validation-check-${r.check}`} className="flex items-center justify-between py-2 px-3 bg-zinc-900/50 rounded border border-zinc-800/30">
                              <div className="flex items-center gap-2">
                                {r.status === 'passed' ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : r.status === 'skipped' ? <Clock className="w-4 h-4 text-zinc-500" /> : <XCircle className="w-4 h-4 text-red-400" />}
                                <span className="text-sm text-zinc-300">{r.check.replace(/_/g, ' ')}</span>
                              </div>
                              <div className="flex items-center gap-3 text-xs">
                                <span className="text-zinc-500">{r.message}</span>
                                {r.duration_ms > 0 && <span className="text-zinc-600">{r.duration_ms}{t("cm.pages_DataModelDashboard.ms")}</span>}
                              </div>
                            </div>)}
                        </div>

                        {/* Readiness Score */}
                        {validationResults[p.provider].readiness && <div className="mt-4 p-3 bg-zinc-900/50 rounded-lg border border-zinc-800/30">
                            <h5 className="text-xs font-medium text-zinc-400 mb-2">{t("cm.pages_DataModelDashboard.readiness")}</h5>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                              <div className="text-center">
                                <div className={`text-lg font-bold ${validationResults[p.provider].readiness.auth_ok ? 'text-emerald-400' : 'text-red-400'}`}>
                                  {validationResults[p.provider].readiness.auth_ok ? 'OK' : 'FAIL'}
                                </div>
                                <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.auth")}</p>
                              </div>
                              <div className="text-center">
                                <div className={`text-lg font-bold ${validationResults[p.provider].readiness.pull_ok ? 'text-emerald-400' : 'text-red-400'}`}>
                                  {validationResults[p.provider].readiness.pull_ok ? 'OK' : 'FAIL'}
                                </div>
                                <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.pull")}</p>
                              </div>
                              <div className="text-center">
                                <div className="text-lg font-bold text-cyan-400">
                                  {validationResults[p.provider].readiness.mapping_readiness_pct}%
                                </div>
                                <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.mapping")}</p>
                              </div>
                              <div className="text-center">
                                <div className={`text-lg font-bold ${validationResults[p.provider].readiness.reservation_import_ready ? 'text-emerald-400' : 'text-amber-400'}`}>
                                  {validationResults[p.provider].readiness.reservation_import_ready ? 'READY' : 'NOT READY'}
                                </div>
                                <p className="text-xs text-zinc-500">{t("cm.pages_DataModelDashboard.import")}</p>
                              </div>
                            </div>
                          </div>}
                      </div>}
                  </CardContent>
                </Card>)}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </>;
};
export default DataModelDashboard;