import React, { useState, lazy, Suspense } from 'react';
import Layout from '@/components/Layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DollarSign, TrendingUp, Rocket, Loader2 } from 'lucide-react';

const RMSModule = lazy(() => import('@/pages/RMSModule'));
const RevenueEngineDashboard = lazy(() => import('@/pages/RevenueEngineDashboard'));
const RevenueAutopilotDashboard = lazy(() => import('@/pages/RevenueAutopilotDashboard'));

function TabLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="ml-3 text-muted-foreground">Yukleniyor...</span>
    </div>
  );
}

export default function GelirYonetimiPage({ user, tenant, onLogout }) {
  const [tab, setTab] = useState('fiyatlama');

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rms">
      <div className="p-4 lg:p-6 space-y-4" data-testid="gelir-yonetimi-page">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Gelir Yonetimi</h1>
          <p className="text-sm text-muted-foreground">Fiyatlama, tahmin, yield ve otomatik gelir optimizasyonu</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid w-full grid-cols-3 max-w-lg" data-testid="gelir-tabs">
            <TabsTrigger value="fiyatlama" data-testid="tab-fiyatlama" className="flex items-center gap-2">
              <DollarSign className="h-4 w-4" /> Fiyat Stratejisi
            </TabsTrigger>
            <TabsTrigger value="gelir-motoru" data-testid="tab-gelir-motoru" className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4" /> Gelir Motoru
            </TabsTrigger>
            <TabsTrigger value="autopilot" data-testid="tab-autopilot" className="flex items-center gap-2">
              <Rocket className="h-4 w-4" /> Autopilot
            </TabsTrigger>
          </TabsList>

          <TabsContent value="fiyatlama">
            <Suspense fallback={<TabLoading />}>
              <RMSModule user={user} tenant={tenant} onLogout={onLogout} embedded />
            </Suspense>
          </TabsContent>

          <TabsContent value="gelir-motoru">
            <Suspense fallback={<TabLoading />}>
              <RevenueEngineDashboard user={user} tenant={tenant} onLogout={onLogout} embedded />
            </Suspense>
          </TabsContent>

          <TabsContent value="autopilot">
            <Suspense fallback={<TabLoading />}>
              <RevenueAutopilotDashboard />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
