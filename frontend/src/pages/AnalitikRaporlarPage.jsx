import React, { useState, lazy, Suspense } from 'react';
import Layout from '@/components/Layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Download, Clock, Loader2 } from 'lucide-react';

const AnalyticsExportDashboard = lazy(() => import('@/pages/AnalyticsExportDashboard'));
const MLSchedulerDashboard = lazy(() => import('@/pages/MLSchedulerDashboard'));

function TabLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="ml-3 text-muted-foreground">Yukleniyor...</span>
    </div>
  );
}

export default function AnalitikRaporlarPage({ user, tenant, onLogout }) {
  const [tab, setTab] = useState('rapor-export');

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rms">
      <div className="p-4 lg:p-6 space-y-4" data-testid="analitik-raporlar-page">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Analitik & Raporlar</h1>
          <p className="text-sm text-muted-foreground">Rapor disa aktarma ve ML model zamanlayicisi</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid w-full grid-cols-2 max-w-md" data-testid="analitik-tabs">
            <TabsTrigger value="rapor-export" data-testid="tab-rapor-export" className="flex items-center gap-2">
              <Download className="h-4 w-4" /> Rapor Disa Aktarma
            </TabsTrigger>
            <TabsTrigger value="ml-scheduler" data-testid="tab-ml-scheduler" className="flex items-center gap-2">
              <Clock className="h-4 w-4" /> ML Zamanlayici
            </TabsTrigger>
          </TabsList>

          <TabsContent value="rapor-export">
            <Suspense fallback={<TabLoading />}>
              <AnalyticsExportDashboard />
            </Suspense>
          </TabsContent>

          <TabsContent value="ml-scheduler">
            <Suspense fallback={<TabLoading />}>
              <MLSchedulerDashboard />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
