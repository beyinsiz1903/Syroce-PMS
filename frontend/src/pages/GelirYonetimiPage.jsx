import React, { useState, lazy, Suspense } from 'react';
import Layout from '@/components/Layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart3, Shield, CalendarRange, Rocket, Loader2 } from 'lucide-react';

const RMSModule = lazy(() => import('@/pages/RMSModule'));
const YieldRulesPanel = lazy(() => import('@/pages/YieldRulesPanel'));
const SeasonCalendarPanel = lazy(() => import('@/pages/SeasonCalendarPanel'));
const RevenueAutopilotDashboard = lazy(() => import('@/pages/RevenueAutopilotDashboard'));

function TabLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="ml-3 text-muted-foreground">Yükleniyor...</span>
    </div>
  );
}

export default function GelirYonetimiPage({ user, tenant, onLogout }) {
  const [tab, setTab] = useState('dashboard');

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rms">
      <div className="p-4 lg:p-6 space-y-4" data-testid="gelir-yonetimi-page">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Gelir Yönetimi</h1>
          <p className="text-sm text-muted-foreground">Dinamik fiyatlama, yield kuralları ve sezon yönetimi</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid w-full grid-cols-4 max-w-2xl" data-testid="gelir-tabs">
            <TabsTrigger value="dashboard" data-testid="tab-dashboard" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" /> Dashboard
            </TabsTrigger>
            <TabsTrigger value="yield" data-testid="tab-yield" className="flex items-center gap-2">
              <Shield className="h-4 w-4" /> Yield Kurallari
            </TabsTrigger>
            <TabsTrigger value="sezon" data-testid="tab-sezon" className="flex items-center gap-2">
              <CalendarRange className="h-4 w-4" /> Sezon Takvimi
            </TabsTrigger>
            <TabsTrigger value="autopilot" data-testid="tab-autopilot" className="flex items-center gap-2">
              <Rocket className="h-4 w-4" /> Autopilot
            </TabsTrigger>
          </TabsList>

          <TabsContent value="dashboard">
            <Suspense fallback={<TabLoading />}>
              <RMSModule user={user} tenant={tenant} onLogout={onLogout} embedded />
            </Suspense>
          </TabsContent>

          <TabsContent value="yield">
            <Suspense fallback={<TabLoading />}>
              <YieldRulesPanel />
            </Suspense>
          </TabsContent>

          <TabsContent value="sezon">
            <Suspense fallback={<TabLoading />}>
              <SeasonCalendarPanel />
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
