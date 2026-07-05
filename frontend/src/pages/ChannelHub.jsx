import React, { Suspense, lazy } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, PlugZap, BarChart3, Settings2, AlertTriangle } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const ChannelConnections = lazy(() => import('@/pages/ChannelConnections'));
const ChannelManagerDashboardV2 = lazy(() => import('@/pages/ChannelManagerDashboardV2'));
const ChannelOpsPage = lazy(() => import('@/pages/ChannelOpsPage'));
const ConflictQueuePage = lazy(() => import('@/pages/ConflictQueuePage'));

const ALL_TABS = ['connections', 'dashboard', 'conflicts', 'ops'];
const SUPER_ADMIN_ONLY_TABS = new Set(['ops']);

export default function ChannelHub({ user, tenant, onLogout }) { // eslint-disable-line no-unused-vars
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  const isSuperAdmin = user?.role === 'super_admin'
    || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));

  // Per-tenant sub-tab entitlement: tenant.modules['channels.<key>'] === false
  // hides that tab. Missing/undefined = visible (backward compatible).
  // Super admin bypasses gating (sees everything).
  const tenantModulesMap = tenant?.modules || {};
  const isChannelSubTabEnabled = (tabKey) => {
    if (isSuperAdmin) return true;
    if (tabKey === 'ops') return true; // already gated by SUPER_ADMIN_ONLY_TABS
    return tenantModulesMap[`channels.${tabKey}`] !== false;
  };

  const allowedTabs = ALL_TABS.filter(tab => {
    if (!isSuperAdmin && SUPER_ADMIN_ONLY_TABS.has(tab)) return false;
    return isChannelSubTabEnabled(tab);
  });
  const requested = searchParams.get('tab');
  const fallback = allowedTabs.includes('connections') ? 'connections' : (allowedTabs[0] || 'dashboard');
  const activeTab = allowedTabs.includes(requested) ? requested : fallback;

  const handleTabChange = (next) => {
    setSearchParams({ tab: next }, { replace: true });
  };

  const childProps = { user, tenant, onLogout, embedded: true };

  return (
    <>
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" data-testid="channel-hub">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
            <PlugZap className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t('channelHub.title', 'Kanallar')}
            </h1>
            <p className="text-sm text-gray-500">
              {t('channelHub.subtitle', 'Bağlantılar, dashboard ve operasyon tek yerde')}
            </p>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList className={`grid w-full max-w-3xl ${
            allowedTabs.length === 4 ? 'grid-cols-4'
              : allowedTabs.length === 3 ? 'grid-cols-3'
                : (allowedTabs.length === 2 ? 'grid-cols-2' : 'grid-cols-1')
          }`}>
            {allowedTabs.includes('connections') && (
              <TabsTrigger value="connections" data-testid="tab-channel-connections">
                <PlugZap className="w-4 h-4 mr-2" />
                {t('channelHub.tabs.connections', 'Bağlantılar')}
              </TabsTrigger>
            )}
            {allowedTabs.includes('dashboard') && (
              <TabsTrigger value="dashboard" data-testid="tab-channel-dashboard">
                <BarChart3 className="w-4 h-4 mr-2" />
                {t('channelHub.tabs.dashboard', 'Dashboard')}
              </TabsTrigger>
            )}
            {allowedTabs.includes('conflicts') && (
              <TabsTrigger value="conflicts" data-testid="tab-channel-conflicts">
                <AlertTriangle className="w-4 h-4 mr-2" />
                {t('channelHub.tabs.conflicts', 'Çakışmalar')}
              </TabsTrigger>
            )}
            {allowedTabs.includes('ops') && (
              <TabsTrigger value="ops" data-testid="tab-channel-ops">
                <Settings2 className="w-4 h-4 mr-2" />
                {t('channelHub.tabs.ops', 'Operasyon')}
              </TabsTrigger>
            )}
          </TabsList>

          <Suspense fallback={
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-amber-600" />
            </div>
          }>
            {allowedTabs.includes('connections') && (
              <TabsContent value="connections" className="mt-6">
                {activeTab === 'connections' && <ChannelConnections {...childProps} />}
              </TabsContent>
            )}
            {allowedTabs.includes('dashboard') && (
              <TabsContent value="dashboard" className="mt-6">
                {activeTab === 'dashboard' && <ChannelManagerDashboardV2 {...childProps} />}
              </TabsContent>
            )}
            {allowedTabs.includes('conflicts') && (
              <TabsContent value="conflicts" className="mt-6">
                {activeTab === 'conflicts' && <ConflictQueuePage {...childProps} />}
              </TabsContent>
            )}
            {allowedTabs.includes('ops') && (
              <TabsContent value="ops" className="mt-6">
                {activeTab === 'ops' && <ChannelOpsPage {...childProps} />}
              </TabsContent>
            )}
          </Suspense>
        </Tabs>
      </div>
    </>
  );
}
