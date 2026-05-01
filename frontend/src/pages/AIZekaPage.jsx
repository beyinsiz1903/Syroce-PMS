import React, { useState, lazy, Suspense } from 'react';
import Layout from '@/components/Layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Brain, BarChart3, Loader2 } from 'lucide-react';

const AIModule = lazy(() => import('@/pages/AIModule'));
const DataIntelligenceDashboard = lazy(() => import('@/pages/DataIntelligenceDashboard'));

function TabLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="ml-3 text-muted-foreground">Yükleniyor...</span>
    </div>
  );
}

export default function AIZekaPage({ user, tenant, onLogout }) {
  const [tab, setTab] = useState('ai-hub');

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="ai">
      <div className="p-4 lg:p-6 space-y-4" data-testid="ai-zeka-page">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI & Zeka</h1>
          <p className="text-sm text-muted-foreground">Yapay zeka asistanları, misafir zekası ve veri analitiği</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid w-full grid-cols-2 max-w-md" data-testid="ai-zeka-tabs">
            <TabsTrigger value="ai-hub" data-testid="tab-ai-hub" className="flex items-center gap-2">
              <Brain className="h-4 w-4" /> AI Hub
            </TabsTrigger>
            <TabsTrigger value="veri-zekasi" data-testid="tab-veri-zekasi" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" /> Veri Zekası
            </TabsTrigger>
          </TabsList>

          <TabsContent value="ai-hub">
            <Suspense fallback={<TabLoading />}>
              <AIModule user={user} tenant={tenant} onLogout={onLogout} embedded />
            </Suspense>
          </TabsContent>

          <TabsContent value="veri-zekasi">
            <Suspense fallback={<TabLoading />}>
              <DataIntelligenceDashboard />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
