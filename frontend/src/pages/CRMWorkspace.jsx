import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, Brain, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import EmptyState from '@/components/EmptyState';
import { toast } from 'sonner';
import SalesCRM from '@/pages/SalesCRM';
import GuestRelationsDashboard from '@/pages/GuestRelationsDashboard';
import KVKKManager from '@/components/pms/KVKKManager';
import { useSearchParams } from 'react-router-dom';

const number = new Intl.NumberFormat('tr-TR');
const CRM_TABS = new Set(['intelligence', 'duplicates', 'relations', 'campaigns', 'journeys', 'sales', 'privacy']);

const CRMWorkspace = (props) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [dashboard, setDashboard] = useState(null);
  const [duplicates, setDuplicates] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [journeys, setJourneys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [mergeCandidate, setMergeCandidate] = useState(null);
  const [merging, setMerging] = useState(false);
  const requestedTab = searchParams.get('tab');
  const activeTab = CRM_TABS.has(requestedTab) ? requestedTab : 'intelligence';

  const selectTab = (tab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'intelligence') next.delete('tab');
    else next.set('tab', tab);
    setSearchParams(next, { replace: true });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const [intel, duplicateResult, campaignResult, journeyResult] = await Promise.allSettled([
      axios.get('/data-intelligence/guests/dashboard', { params: { limit: 30 } }),
      axios.get('/cross-property/duplicates/scan', { params: { min_score: 0.6, limit: 50 } }),
      axios.get('/marketing/campaigns', { params: { limit: 100 } }),
      axios.get('/messaging-center/automation/rules'),
    ]);
    if (intel.status === 'fulfilled') setDashboard(intel.value.data || null);
    else {
      setDashboard(null);
      setError(intel.reason?.response?.data?.detail || 'CRM özeti yüklenemedi.');
    }
    setDuplicates(duplicateResult.status === 'fulfilled' ? (duplicateResult.value.data?.matches || []) : []);
    setCampaigns(campaignResult.status === 'fulfilled' ? (campaignResult.value.data?.campaigns || []) : []);
    setJourneys(journeyResult.status === 'fulfilled' ? (journeyResult.value.data?.rules || []) : []);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const total = dashboard?.guests_analyzed || 0;
  const highValue = dashboard?.top_value_guests?.length || 0;
  const churn = dashboard?.high_churn_guests?.length || 0;
  const opportunities = dashboard?.upsell_opportunities?.length || 0;

  const mergeProfiles = async () => {
    const primaryId = mergeCandidate?.left?.id;
    const duplicateId = mergeCandidate?.right?.id;
    if (!primaryId || !duplicateId) return;
    setMerging(true);
    try {
      const result = await axios.post(`/cross-property/guests/${encodeURIComponent(primaryId)}/merge`, { target_guest_id: duplicateId });
      toast.success(`${result.data?.bookings_repointed || 0} rezervasyon ve ${result.data?.folios_repointed || 0} folyo birincil profile bağlandı.`);
      setMergeCandidate(null);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Profiller birleştirilemedi.');
    } finally {
      setMerging(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-50/70 p-4 lg:p-6" data-testid="crm-workspace">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">Misafir yaşam döngüsü</p>
            <h1 className="mt-1 text-3xl font-black tracking-tight text-slate-950">CRM Merkezi</h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-600">Misafir profili, değer, risk, ilişki, satış ve veri izinlerini tek çalışma alanından yönetin.</p>
          </div>
          <Button variant="outline" onClick={load} disabled={loading} aria-label="CRM verilerini yenile">
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Yenile
          </Button>
        </header>

        {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="CRM özeti">
          {[
            ['Analiz edilen misafir', total, Users],
            ['Yüksek değerli', highValue, Brain],
            ['Kaybetme riski yüksek', churn, AlertTriangle],
            ['Gelir fırsatı', opportunities, Brain],
            ['Birleştirme adayı', duplicates.length, ShieldCheck],
          ].map(([label, value, Icon]) => (
            <Card key={label}><CardContent className="flex items-center gap-3 p-4"><span className="rounded-xl bg-blue-50 p-2 text-blue-700"><Icon className="h-5 w-5" /></span><div><p className="text-2xl font-bold text-slate-950">{number.format(value)}</p><p className="text-xs text-slate-500">{label}</p></div></CardContent></Card>
          ))}
        </section>

        <Tabs value={activeTab} onValueChange={selectTab}>
          <TabsList className="h-auto w-full justify-start overflow-x-auto p-1">
            <TabsTrigger value="intelligence">Misafir 360</TabsTrigger>
            <TabsTrigger value="duplicates">Mükerrer kayıtlar</TabsTrigger>
            <TabsTrigger value="relations">Misafir ilişkileri</TabsTrigger>
            <TabsTrigger value="campaigns">Kampanyalar</TabsTrigger>
            <TabsTrigger value="journeys">Otomatik yolculuklar</TabsTrigger>
            <TabsTrigger value="sales">Satış CRM</TabsTrigger>
            <TabsTrigger value="privacy">KVKK ve izinler</TabsTrigger>
          </TabsList>

          <TabsContent value="intelligence" className="space-y-4 pt-3">
            {!loading && !dashboard ? <EmptyState title="Misafir verisi bulunamadı" description="CRM analizi için gerçek misafir ve konaklama verisi gereklidir." /> : <div className="grid gap-4 lg:grid-cols-3">
              <MetricList title="En değerli misafirler" rows={dashboard?.top_value_guests} valueKey="total_revenue" suffix=" ₺" />
              <MetricList title="Kaybetme riski" rows={dashboard?.high_churn_guests} valueKey="churn_score" />
              <MetricList title="Ek gelir fırsatları" rows={dashboard?.upsell_opportunities} valueKey="potential" suffix=" ₺" />
            </div>}
          </TabsContent>
          <TabsContent value="duplicates" className="pt-3">
            <Card><CardHeader><CardTitle>Kontrollü profil birleştirme kuyruğu</CardTitle></CardHeader><CardContent>
              {duplicates.length === 0 ? <p className="text-sm text-slate-500">Eşik üzerinde birleştirme adayı bulunamadı. Kayıtlar otomatik olarak birleştirilmez.</p> : <div className="space-y-2">{duplicates.map((row, index) => <div key={`${row.left?.id}-${row.right?.id}-${index}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm"><div><div className="font-medium text-slate-900">{row.left?.name || 'Birincil profil'} ↔ {row.right?.name || 'Aday profil'}</div><div className="mt-1 text-xs text-slate-500">Eşleşme skoru: {Math.round(Number(row.score || 0) * 100)}% · {(row.reasons || []).join(', ')}</div></div><Button size="sm" variant="outline" onClick={() => setMergeCandidate(row)}>İncele ve birleştir</Button></div>)}</div>}
            </CardContent></Card>
          </TabsContent>
          <TabsContent value="relations"><GuestRelationsDashboard embedded /></TabsContent>
          <TabsContent value="campaigns" className="pt-3"><Card><CardHeader><CardTitle>Kampanya ve gerçekleşen gelir</CardTitle></CardHeader><CardContent>{campaigns.length ? <div className="space-y-2">{campaigns.map((campaign) => <div key={campaign.id} className="grid gap-2 rounded-lg border p-3 text-sm sm:grid-cols-[1fr_auto_auto]"><div><p className="font-medium text-slate-900">{campaign.name}</p><p className="text-xs text-slate-500">{campaign.segment || 'all'} · {campaign.status}</p></div><span>{number.format(campaign.attribution?.conversions || 0)} rezervasyon</span><span className="font-semibold">{number.format(campaign.attribution?.net_revenue || 0)} ₺ net gelir</span></div>)}</div> : <p className="text-sm text-slate-500">Henüz gerçek kampanya kaydı bulunmuyor.</p>}</CardContent></Card></TabsContent>
          <TabsContent value="journeys" className="pt-3"><Card><CardHeader><CardTitle>Misafir iletişim otomasyonları</CardTitle></CardHeader><CardContent className="space-y-2">{journeys.length ? journeys.map((rule) => <div key={rule.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm"><div><p className="font-medium">{rule.name}</p><p className="text-xs text-slate-500">{rule.trigger_event} · {rule.channel} · {rule.delay_minutes || 0} dakika gecikme</p></div><span className={`rounded-full px-2 py-1 text-xs font-medium ${rule.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>{rule.enabled ? 'Aktif' : 'Kapalı'}</span></div>) : <p className="text-sm text-slate-500">Etkin otomatik yolculuk bulunmuyor. Kurallar İletişim Merkezi’nden oluşturulur ve iletişim izinleri gönderim sırasında uygulanır.</p>}</CardContent></Card></TabsContent>
          <TabsContent value="sales"><SalesCRM {...props} /></TabsContent>
          <TabsContent value="privacy"><KVKKManager /></TabsContent>
        </Tabs>
        <Dialog open={Boolean(mergeCandidate)} onOpenChange={(open) => !open && !merging && setMergeCandidate(null)}>
          <DialogContent>
            <DialogHeader><DialogTitle>Misafir profillerini birleştir</DialogTitle></DialogHeader>
            <div className="space-y-3 text-sm text-slate-700">
              <p><strong>{mergeCandidate?.left?.name}</strong> birincil profil olarak korunacak.</p>
              <p><strong>{mergeCandidate?.right?.name}</strong> arşivlenecek; rezervasyon ve folyoları birincil profile taşınacak.</p>
              <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900">Bu işlem otomatik yapılmaz ve geri alma işlemi yönetici müdahalesi gerektirir. Kimlik, e-posta ve telefon bilgilerini doğrulamadan onaylamayın.</p>
            </div>
            <DialogFooter><Button variant="outline" onClick={() => setMergeCandidate(null)} disabled={merging}>Vazgeç</Button><Button onClick={mergeProfiles} disabled={merging}>{merging ? 'Birleştiriliyor…' : 'Onayla ve birleştir'}</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </main>
  );
};

const MetricList = ({ title, rows = [], valueKey, suffix = '' }) => <Card><CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader><CardContent className="space-y-2">{rows?.length ? rows.slice(0, 10).map((row) => <div key={row.guest_id} className="flex items-center justify-between rounded-lg border px-3 py-2"><span className="truncate text-sm font-medium">{row.name || row.guest_name || row.guest_id}</span><span className="ml-3 text-sm tabular-nums text-slate-600">{number.format(Number(row[valueKey] || 0))}{suffix}</span></div>) : <p className="text-sm text-slate-500">Gerçek veri bulunamadı.</p>}</CardContent></Card>;

export default CRMWorkspace;
