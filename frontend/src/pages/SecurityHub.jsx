import React, { Suspense, lazy } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, Shield, Activity, Lock } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Layout from '@/components/Layout';

const SecurityCenter = lazy(() => import('@/pages/SecurityCenter'));
const SecurityDashboard = lazy(() => import('@/pages/SecurityDashboard'));
const SecurityHardeningDashboard = lazy(() => import('@/pages/SecurityHardeningDashboard'));

const VALID_TABS = ['center', 'monitor', 'hardening'];

export default function SecurityHub({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab');
  const activeTab = VALID_TABS.includes(requested) ? requested : 'center';

  const handleTabChange = (next) => {
    setSearchParams({ tab: next }, { replace: true });
  };

  const childProps = { user, tenant, onLogout, embedded: true };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="security">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" data-testid="security-hub">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
            <Shield className="w-5 h-5 text-blue-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t('securityHub.title', 'Güvenlik')}
            </h1>
            <p className="text-sm text-gray-500">
              {t('securityHub.subtitle', 'Merkez, izleme ve sertleştirme tek yerde')}
            </p>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList className="grid w-full grid-cols-3 max-w-2xl">
            <TabsTrigger value="center" data-testid="tab-security-center">
              <Shield className="w-4 h-4 mr-2" />
              {t('securityHub.tabs.center', 'Merkez')}
            </TabsTrigger>
            <TabsTrigger value="monitor" data-testid="tab-security-monitor">
              <Activity className="w-4 h-4 mr-2" />
              {t('securityHub.tabs.monitor', 'İzleme')}
            </TabsTrigger>
            <TabsTrigger value="hardening" data-testid="tab-security-hardening">
              <Lock className="w-4 h-4 mr-2" />
              {t('securityHub.tabs.hardening', 'Sertleştirme')}
            </TabsTrigger>
          </TabsList>

          <Suspense fallback={
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            </div>
          }>
            <TabsContent value="center" className="mt-6">
              {activeTab === 'center' && <SecurityCenter {...childProps} />}
            </TabsContent>
            <TabsContent value="monitor" className="mt-6">
              {activeTab === 'monitor' && <SecurityDashboard {...childProps} />}
            </TabsContent>
            <TabsContent value="hardening" className="mt-6">
              {activeTab === 'hardening' && <SecurityHardeningDashboard {...childProps} />}
            </TabsContent>
          </Suspense>
        </Tabs>
      </div>
    </Layout>
  );
}
