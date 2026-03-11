import { useState, Suspense, lazy } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Loader2, Activity, AlertTriangle, Clock, Key, AlertOctagon, BarChart3, Shield, Bell, TrendingUp, Boxes, Building2 } from 'lucide-react';

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

const TABS = [
  { id: 'sync-health', label: 'Sync Health', icon: Activity },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'reliability', label: 'Reliability', icon: TrendingUp },
  { id: 'reconciliation', label: 'Reconciliation', icon: AlertTriangle },
  { id: 'scheduler', label: 'Scheduler', icon: Clock },
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
    'alerts': <AlertsTab />,
    'reliability': <ReliabilityTab />,
    'reconciliation': <ReconciliationTab />,
    'scheduler': <SchedulerTab />,
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

  return (
    <div data-testid="admin-control-panel" className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white tracking-tight">Admin Control Panel</h1>
          <p className="text-sm text-slate-400 mt-1">Hotel Integration Platform — Operasyonel Yonetim</p>
        </div>

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
