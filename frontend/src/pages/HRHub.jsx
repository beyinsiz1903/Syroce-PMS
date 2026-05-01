import React, { Suspense, lazy } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, Users, Activity } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Layout from '@/components/Layout';

const HRComplete = lazy(() => import('@/pages/HRComplete'));
const HRv2OpsDashboard = lazy(() => import('@/pages/HRv2OpsDashboard'));

const VALID_TABS = ['suite', 'ops'];

export default function HRHub({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab');
  const activeTab = VALID_TABS.includes(requested) ? requested : 'suite';

  const handleTabChange = (next) => {
    setSearchParams({ tab: next }, { replace: true });
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="hr">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" data-testid="hr-hub">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
            <Users className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t('hrHub.title', 'İK')}
            </h1>
            <p className="text-sm text-gray-500">
              {t('hrHub.subtitle', 'İK suite ve operasyon dashboard tek yerde')}
            </p>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList className="grid w-full grid-cols-2 max-w-md">
            <TabsTrigger value="suite" data-testid="tab-hr-suite">
              <Users className="w-4 h-4 mr-2" />
              {t('hrHub.tabs.suite', 'Suite')}
            </TabsTrigger>
            <TabsTrigger value="ops" data-testid="tab-hr-ops">
              <Activity className="w-4 h-4 mr-2" />
              {t('hrHub.tabs.ops', 'Operasyon')}
            </TabsTrigger>
          </TabsList>

          <Suspense fallback={
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-emerald-600" />
            </div>
          }>
            <TabsContent value="suite" className="mt-6">
              {activeTab === 'suite' && <HRComplete />}
            </TabsContent>
            <TabsContent value="ops" className="mt-6">
              {activeTab === 'ops' && <HRv2OpsDashboard />}
            </TabsContent>
          </Suspense>
        </Tabs>
      </div>
    </Layout>
  );
}
