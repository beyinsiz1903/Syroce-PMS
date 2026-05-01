import React, { Suspense, lazy } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Loader2,
  TrendingUp,
  Sparkles,
  DollarSign,
  Zap,
  Globe,
  Cog,
  BrainCircuit,
  GitCompareArrows,
  AlertTriangle,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Layout from '@/components/Layout';

const GelirYonetimiPage = lazy(() => import('@/pages/GelirYonetimiPage'));
const RevenueAutopilotDashboard = lazy(() => import('@/pages/RevenueAutopilotDashboard'));
const UnifiedRateManager = lazy(() => import('@/pages/UnifiedRateManager'));
const DynamicPricing = lazy(() => import('@/pages/DynamicPricing'));
const CentralPricingManager = lazy(() => import('@/pages/CentralPricingManager'));
const RevenueEngineDashboard = lazy(() => import('@/pages/RevenueEngineDashboard'));
const PredictiveAnalytics = lazy(() => import('@/pages/PredictiveAnalytics'));
const DisplacementAnalysis = lazy(() => import('@/pages/DisplacementAnalysis'));
const NoShowAnalytics = lazy(() => import('@/pages/NoShowAnalytics'));

const ALL_TABS = [
  'overview',
  'autopilot',
  'rates',
  'dynamic',
  'central',
  'engine',
  'predictive',
  'displacement',
  'noshow',
];

export default function RevenueHub({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  const requested = searchParams.get('tab');
  const activeTab = ALL_TABS.includes(requested) ? requested : 'overview';

  const handleTabChange = (next) => {
    setSearchParams({ tab: next }, { replace: true });
  };

  const childProps = { user, tenant, onLogout, embedded: true };

  const tabConfig = [
    { value: 'overview',     icon: TrendingUp,       labelKey: 'revenueHub.tabs.overview',     fallback: 'Genel' },
    { value: 'autopilot',    icon: Sparkles,         labelKey: 'revenueHub.tabs.autopilot',    fallback: 'Autopilot' },
    { value: 'rates',        icon: DollarSign,       labelKey: 'revenueHub.tabs.rates',        fallback: 'Rate Manager' },
    { value: 'dynamic',      icon: Zap,              labelKey: 'revenueHub.tabs.dynamic',      fallback: 'Dinamik Fiyat' },
    { value: 'central',      icon: Globe,            labelKey: 'revenueHub.tabs.central',      fallback: 'Merkezi Fiyat' },
    { value: 'engine',       icon: Cog,              labelKey: 'revenueHub.tabs.engine',       fallback: 'Engine' },
    { value: 'predictive',   icon: BrainCircuit,     labelKey: 'revenueHub.tabs.predictive',   fallback: 'Tahmin' },
    { value: 'displacement', icon: GitCompareArrows, labelKey: 'revenueHub.tabs.displacement', fallback: 'Displacement' },
    { value: 'noshow',       icon: AlertTriangle,    labelKey: 'revenueHub.tabs.noshow',       fallback: 'No-Show' },
  ];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="revenue">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" data-testid="revenue-hub">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t('revenueHub.title', 'Gelir Yönetimi')}
            </h1>
            <p className="text-sm text-gray-500">
              {t('revenueHub.subtitle', 'Fiyatlama, autopilot, tahmin ve risk analitiği tek yerde')}
            </p>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList className="flex flex-wrap h-auto justify-start gap-1 bg-gray-100 p-1 rounded-md">
            {tabConfig.map(({ value, icon: Icon, labelKey, fallback }) => (
              <TabsTrigger
                key={value}
                value={value}
                data-testid={`tab-revenue-${value}`}
                className="data-[state=active]:bg-white data-[state=active]:shadow-sm"
              >
                <Icon className="w-4 h-4 mr-2" />
                {t(labelKey, fallback)}
              </TabsTrigger>
            ))}
          </TabsList>

          <Suspense fallback={
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-emerald-600" />
            </div>
          }>
            <TabsContent value="overview" className="mt-6">
              {activeTab === 'overview' && <GelirYonetimiPage {...childProps} />}
            </TabsContent>
            <TabsContent value="autopilot" className="mt-6">
              {activeTab === 'autopilot' && <RevenueAutopilotDashboard {...childProps} />}
            </TabsContent>
            <TabsContent value="rates" className="mt-6">
              {activeTab === 'rates' && <UnifiedRateManager {...childProps} />}
            </TabsContent>
            <TabsContent value="dynamic" className="mt-6">
              {activeTab === 'dynamic' && <DynamicPricing {...childProps} />}
            </TabsContent>
            <TabsContent value="central" className="mt-6">
              {activeTab === 'central' && <CentralPricingManager {...childProps} />}
            </TabsContent>
            <TabsContent value="engine" className="mt-6">
              {activeTab === 'engine' && <RevenueEngineDashboard {...childProps} />}
            </TabsContent>
            <TabsContent value="predictive" className="mt-6">
              {activeTab === 'predictive' && <PredictiveAnalytics {...childProps} />}
            </TabsContent>
            <TabsContent value="displacement" className="mt-6">
              {activeTab === 'displacement' && <DisplacementAnalysis {...childProps} />}
            </TabsContent>
            <TabsContent value="noshow" className="mt-6">
              {activeTab === 'noshow' && <NoShowAnalytics {...childProps} />}
            </TabsContent>
          </Suspense>
        </Tabs>
      </div>
    </Layout>
  );
}
