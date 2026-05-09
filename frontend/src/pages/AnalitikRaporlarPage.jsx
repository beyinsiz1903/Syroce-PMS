import React, { useState, lazy, Suspense, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Download, Clock, Loader2, Brain, BarChart3 } from 'lucide-react';
import { PageHeader } from '@/components/ui/page-header';

const AnalyticsExportDashboard = lazy(() => import('@/pages/AnalyticsExportDashboard'));
const MLSchedulerDashboard = lazy(() => import('@/pages/MLSchedulerDashboard'));
const RevenueMLPanel = lazy(() => import('@/pages/RevenueMLPanel'));

const VALID_TABS = ['revenue-ml', 'rapor-export', 'ml-scheduler'];
const DEFAULT_TAB = 'rapor-export';

function TabLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      <span className="ml-3 text-slate-500">Yükleniyor…</span>
    </div>
  );
}

export default function AnalitikRaporlarPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = VALID_TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : DEFAULT_TAB;
  const [tab, setTab] = useState(initial);

  const onTabChange = useCallback((value) => {
    setTab(value);
    const next = new URLSearchParams(searchParams);
    if (value === DEFAULT_TAB) next.delete('tab');
    else next.set('tab', value);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  // Browser ileri/geri ile URL değişirse state senkron tut.
  useEffect(() => {
    const fromUrl = VALID_TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : DEFAULT_TAB;
    if (fromUrl !== tab) setTab(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return (
    <div className="p-4 lg:p-6 space-y-4" data-testid="analitik-raporlar-page">
      <PageHeader
        icon={BarChart3}
        title="Analitik & Raporlar"
        subtitle="ML tahminleri, rapor dışa aktarma ve model zamanlayıcısı"
      />

      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList className="grid w-full grid-cols-3 max-w-xl" data-testid="analitik-tabs">
          <TabsTrigger value="revenue-ml" data-testid="tab-revenue-ml" className="flex items-center gap-2">
            <Brain className="h-4 w-4" /> Revenue ML
          </TabsTrigger>
          <TabsTrigger value="rapor-export" data-testid="tab-rapor-export" className="flex items-center gap-2">
            <Download className="h-4 w-4" /> Rapor Dışa Aktarma
          </TabsTrigger>
          <TabsTrigger value="ml-scheduler" data-testid="tab-ml-scheduler" className="flex items-center gap-2">
            <Clock className="h-4 w-4" /> ML Zamanlayıcı
          </TabsTrigger>
        </TabsList>

        <TabsContent value="revenue-ml">
          <Suspense fallback={<TabLoading />}>
            <RevenueMLPanel />
          </Suspense>
        </TabsContent>

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
  );
}
