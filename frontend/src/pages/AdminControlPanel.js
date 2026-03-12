import { useState, Suspense, lazy } from 'react';
import { Loader2, Activity, AlertTriangle, Clock, Key, AlertOctagon, BarChart3, Shield, Bell, TrendingUp, Boxes, Building2, FileText, PlayCircle, Heart, Send, Zap, Map, LineChart, Gauge, Wifi } from 'lucide-react';
import { useAdminWebSocket } from '../hooks/useAdminWebSocket';

const SyncHealthTab = lazy(() => import('./admin/tabs/SyncHealthTab'));
const ReconciliationTab = lazy(() => import('./admin/tabs/ReconciliationTab'));
const SchedulerTab = lazy(() => import('./admin/tabs/SchedulerTab'));
const CredentialsTab = lazy(() => import('./admin/tabs/CredentialsTab'));
const ErrorQueueTab = lazy(() => import('./admin/tabs/ErrorQueueTab'));
const ObservabilityTab = lazy(() => import('./admin/tabs/ObservabilityTab'));
const ReadinessTab = lazy(() => import('./admin/tabs/ReadinessTab'));
const AlertsTab = lazy(() => import('./admin/tabs/AlertsTab'));
const ReliabilityTab = lazy(() => import('./admin/tabs/ReliabilityTab'));
const SandboxValidationTab = lazy(() => import('./admin/tabs/SandboxValidationTab'));
const MultiPropertyTab = lazy(() => import('./admin/tabs/MultiPropertyTab'));
const ReservationsTab = lazy(() => import('./admin/tabs/ReservationsTab'));
const ImportJobsTab = lazy(() => import('./admin/tabs/ImportJobsTab'));
const ConnectorHealthTab = lazy(() => import('./admin/tabs/ConnectorHealthTab'));
const AlertDeliveryTab = lazy(() => import('./admin/tabs/AlertDeliveryTab'));
const BackgroundWorkerTab = lazy(() => import('./admin/tabs/BackgroundWorkerTab'));
const HealthTrendTab = lazy(() => import('./admin/tabs/HealthTrendTab'));
const MappingCompletenessTab = lazy(() => import('./admin/tabs/MappingCompletenessTab'));
const RatePushMetricsTab = lazy(() => import('./admin/tabs/RatePushMetricsTab'));

const TABS = [
  { id: 'sync-health', label: 'Sync Health', icon: Activity },
  { id: 'connector-health', label: 'Health Dashboard', icon: Heart },
  { id: 'health-trend', label: 'Health Trends', icon: LineChart },
  { id: 'mapping-completeness', label: 'Mapping Readiness', icon: Map },
  { id: 'rate-push-metrics', label: 'Rate Push', icon: Gauge },
  { id: 'reservations', label: 'Reservations', icon: FileText },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'alert-delivery', label: 'Alert Delivery', icon: Send },
  { id: 'reliability', label: 'Reliability', icon: TrendingUp },
  { id: 'reconciliation', label: 'Reconciliation', icon: AlertTriangle },
  { id: 'scheduler', label: 'Scheduler', icon: Clock },
  { id: 'import-jobs', label: 'Import Jobs', icon: PlayCircle },
  { id: 'background-worker', label: 'Background Worker', icon: Zap },
  { id: 'credentials', label: 'Credentials', icon: Key },
  { id: 'error-queue', label: 'Error Queue', icon: AlertOctagon },
  { id: 'observability', label: 'Observability', icon: BarChart3 },
  { id: 'readiness', label: 'Readiness', icon: Shield },
  { id: 'sandbox-validation', label: 'Sandbox Validation', icon: Boxes },
  { id: 'multi-property', label: 'Multi-Property', icon: Building2 },
];

const TabContent = ({ tabId }) => {
  const map = {
    'sync-health': <SyncHealthTab />,
    'connector-health': <ConnectorHealthTab />,
    'health-trend': <HealthTrendTab />,
    'mapping-completeness': <MappingCompletenessTab />,
    'rate-push-metrics': <RatePushMetricsTab />,
    'reservations': <ReservationsTab />,
    'alerts': <AlertsTab />,
    'alert-delivery': <AlertDeliveryTab />,
    'reliability': <ReliabilityTab />,
    'reconciliation': <ReconciliationTab />,
    'scheduler': <SchedulerTab />,
    'import-jobs': <ImportJobsTab />,
    'background-worker': <BackgroundWorkerTab />,
    'credentials': <CredentialsTab />,
    'error-queue': <ErrorQueueTab />,
    'observability': <ObservabilityTab />,
    'readiness': <ReadinessTab />,
    'sandbox-validation': <SandboxValidationTab />,
    'multi-property': <MultiPropertyTab />,
  };
  return map[tabId] || null;
};

const AdminControlPanel = () => {
  const [activeTab, setActiveTab] = useState('sync-health');
  const { connected, lastEvent } = useAdminWebSocket('default');

  return (
    <div data-testid="admin-control-panel" className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Admin Control Panel</h1>
            <p className="text-sm text-slate-400 mt-1">Hotel Integration Platform — Operasyonel Yonetim</p>
          </div>
          <div data-testid="ws-status" className="flex items-center gap-2 text-xs">
            <Wifi className={`w-3.5 h-3.5 ${connected ? 'text-emerald-400' : 'text-slate-600'}`} />
            <span className={connected ? 'text-emerald-400' : 'text-slate-500'}>
              {connected ? 'Live' : 'Offline'}
            </span>
          </div>
        </div>

        {/* Real-time Event Banner */}
        {lastEvent && (
          <div data-testid="realtime-event-banner" className="mb-4 px-3 py-2 bg-blue-950/50 border border-blue-800/30 rounded-lg flex items-center gap-2 text-xs animate-pulse">
            <Activity className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-blue-300">
              {lastEvent.type?.replace(/_/g, ' ')} — {lastEvent.data?.connector_id || lastEvent.data?.alert_id || ''}
            </span>
            <span className="text-slate-500 ml-auto">{lastEvent.timestamp ? new Date(lastEvent.timestamp).toLocaleTimeString('tr-TR') : ''}</span>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex gap-1 overflow-x-auto pb-2 mb-6 scrollbar-thin scrollbar-track-slate-900 scrollbar-thumb-slate-700">
          {TABS.map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                data-testid={`tab-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all duration-200 ${
                  isActive
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                    : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <Suspense fallback={<div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>}>
          <TabContent tabId={activeTab} />
        </Suspense>
      </div>
    </div>
  );
};

export default AdminControlPanel;
