import { useState, Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
import Layout from '../components/Layout';
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

const TAB_KEYS = [
  { id: 'sync-health', labelKey: 'adminPanel2.syncHealth', icon: Activity },
  { id: 'connector-health', labelKey: 'adminPanel2.healthDashboard', icon: Heart },
  { id: 'health-trend', labelKey: 'adminPanel2.healthTrends', icon: LineChart },
  { id: 'mapping-completeness', labelKey: 'adminPanel2.mappingReadiness', icon: Map },
  { id: 'rate-push-metrics', labelKey: 'adminPanel2.ratePush', icon: Gauge },
  { id: 'reservations', labelKey: 'adminPanel2.reservations', icon: FileText },
  { id: 'alerts', labelKey: 'adminPanel2.alerts', icon: Bell },
  { id: 'alert-delivery', labelKey: 'adminPanel2.alertDelivery', icon: Send },
  { id: 'reliability', labelKey: 'adminPanel2.reliability', icon: TrendingUp },
  { id: 'reconciliation', labelKey: 'adminPanel2.reconciliation', icon: AlertTriangle },
  { id: 'scheduler', labelKey: 'adminPanel2.scheduler', icon: Clock },
  { id: 'import-jobs', labelKey: 'adminPanel2.importJobs', icon: PlayCircle },
  { id: 'background-worker', labelKey: 'adminPanel2.backgroundWorker', icon: Zap },
  { id: 'credentials', labelKey: 'adminPanel2.credentials', icon: Key },
  { id: 'error-queue', labelKey: 'adminPanel2.errorQueue', icon: AlertOctagon },
  { id: 'observability', labelKey: 'adminPanel2.observability', icon: BarChart3 },
  { id: 'readiness', labelKey: 'adminPanel2.readiness', icon: Shield },
  { id: 'sandbox-validation', labelKey: 'adminPanel2.sandboxValidation', icon: Boxes },
  { id: 'multi-property', labelKey: 'adminPanel2.multiProperty', icon: Building2 },
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

const AdminControlPanel = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('sync-health');
  const { connected, lastEvent } = useAdminWebSocket('default');

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="admin_control_panel">
      <div data-testid="admin-control-panel" className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{t("adminPanel2.title")}</h1>
            <p className="text-sm text-gray-500 mt-1">{t("techDashboards.integrationHubDesc")}</p>
          </div>
          <div data-testid="ws-status" className="flex items-center gap-2 text-xs">
            <Wifi className={`w-3.5 h-3.5 ${connected ? 'text-emerald-500' : 'text-gray-400'}`} />
            <span className={connected ? 'text-emerald-600' : 'text-gray-400'}>
              {connected ? t("adminPanel2.wsConnected") : t("adminPanel2.wsDisconnected")}
            </span>
          </div>
        </div>

        {lastEvent && (
          <div data-testid="realtime-event-banner" className="mb-4 px-3 py-2 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-2 text-xs">
            <Activity className="w-3.5 h-3.5 text-blue-500" />
            <span className="text-blue-700">
              {lastEvent.type?.replace(/_/g, ' ')} — {lastEvent.data?.connector_id || lastEvent.data?.alert_id || ''}
            </span>
            <span className="text-gray-400 ml-auto">{lastEvent.timestamp ? new Date(lastEvent.timestamp).toLocaleTimeString('tr-TR') : ''}</span>
          </div>
        )}

        <div className="flex gap-1 overflow-x-auto pb-2 mb-6">
          {TAB_KEYS.map(tab => {
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
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t(tab.labelKey)}
              </button>
            );
          })}
        </div>

        <Suspense fallback={<div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>}>
          <TabContent tabId={activeTab} />
        </Suspense>
      </div>
    </Layout>
  );
};

export default AdminControlPanel;
