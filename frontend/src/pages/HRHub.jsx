import React, { Suspense, lazy } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, Users, Activity } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const HRComplete = lazy(() => import('@/pages/HRComplete'));
const HRv2OpsDashboard = lazy(() => import('@/pages/HRv2OpsDashboard'));

const VALID_TABS = ['suite', 'ops'];

export default function HRHub({ user, tenant, onLogout }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab');
  const activeTab = VALID_TABS.includes(requested) ? requested : 'suite';

  const handleTabChange = (next) => {
    setSearchParams({ tab: next }, { replace: true });
  };

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto" data-testid="hr-hub">
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full grid-cols-2 max-w-md mb-4">
          <TabsTrigger value="suite" data-testid="tab-hr-suite">
            <Users className="w-4 h-4 mr-2" />İK Suite
          </TabsTrigger>
          <TabsTrigger value="ops" data-testid="tab-hr-ops">
            <Activity className="w-4 h-4 mr-2" />Operasyon
          </TabsTrigger>
        </TabsList>

        <Suspense fallback={
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-slate-600" />
          </div>
        }>
          <TabsContent value="suite">
            {activeTab === 'suite' && <HRComplete tenant={tenant} user={user} />}
          </TabsContent>
          <TabsContent value="ops">
            {activeTab === 'ops' && <HRv2OpsDashboard tenant={tenant} />}
          </TabsContent>
        </Suspense>
      </Tabs>
    </div>
  );
}
