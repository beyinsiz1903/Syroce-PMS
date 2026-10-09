import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, Brain, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import EmptyState from '@/components/EmptyState';
import { toast } from 'sonner';
import SalesCRM from '@/pages/SalesCRM';
import GuestRelationsDashboard from '@/pages/GuestRelationsDashboard';
import KVKKManager from '@/components/pms/KVKKManager';
import { Link, useSearchParams } from 'react-router-dom';

const number = new Intl.NumberFormat('tr-TR');
const CRM_TABS = new Set(['intelligence', 'duplicates', 'relations', 'campaigns', 'journeys', 'sales', 'privacy']);
const SOURCE_TABS = new Set(['intelligence', 'duplicates', 'campaigns', 'journeys']);
const EMPTY_SOURCE = { data: null, meta: {}, loading: false, loaded: false, error: '' };
const REASON_LABELS = { email_exact: 'E-posta aynı', phone_exact: 'Telefon aynı', name_high: 'İsim güçlü eşleşme', name_medium: 'İsim olası eşleşme' };
const TRIGGER_LABELS = { booking_confirmed: 'Rezervasyon onaylandı', pre_arrival: 'Giriş öncesi', checked_in: 'Giriş yapıldı', checked_out: 'Çıkış yapıldı' };
const CHANNEL_LABELS = { email: 'E-posta', whatsapp: 'WhatsApp', sms: 'SMS' };
const STATUS_LABELS = { draft: 'Taslak', active: 'Aktif', paused: 'Duraklatıldı', completed: 'Tamamlandı' };
const SEGMENT_LABELS = { all: 'Tüm misafirler', vip: 'VIP', loyal: 'Sadık misafirler', inactive: 'Pasif misafirler' };

const maskEmail = (value) => {
  if (!value || !value.includes('@')) return '—';
  const [name, domain] = value.split('@');
  return `${name.slice(0, 2)}***@${domain}`;
};
const maskPhone = (value) => value ? `*** *** ${String(value).replace(/\D/g, '').slice(-4)}` : '—';
const reasonLabel = (reason) => REASON_LABELS[String(reason || '').split('(')[0]] || 'Profil benzerliği';

const CRMWorkspace = (props) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [sources, setSources] = useState({
    intelligence: { ...EMPTY_SOURCE }, duplicates: { ...EMPTY_SOURCE }, campaigns: { ...EMPTY_SOURCE }, journeys: { ...EMPTY_SOURCE },
  });
  const [duplicatePage, setDuplicatePage] = useState(0);
  const [duplicateSearch, setDuplicateSearch] = useState('');
  const [mergeCandidate, setMergeCandidate] = useState(null);
  const [mergeVerified, setMergeVerified] = useState(false);
  const [merging, setMerging] = useState(false);
  const requestedTab = searchParams.get('tab');
  const activeTab = CRM_TABS.has(requestedTab) ? requestedTab : 'intelligence';

  const selectTab = (tab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'intelligence') next.delete('tab'); else next.set('tab', tab);
    setSearchParams(next, { replace: true });
  };

  const loadSource = useCallback(async (source, { force = false, page = duplicatePage } = {}) => {
    if (!SOURCE_TABS.has(source)) return;
    let shouldLoad = true;
    setSources((prev) => {
      if (!force && (prev[source].loaded || prev[source].loading)) { shouldLoad = false; return prev; }
      return { ...prev, [source]: { ...prev[source], loading: true, error: '' } };
    });
    if (!shouldLoad) return;
    try {
      let response;
      if (source === 'intelligence') response = await axios.get('/data-intelligence/guests/dashboard', { params: { limit: 30, include_test_data: false } });
      if (source === 'duplicates') {
        const [scan, history] = await Promise.all([
          axios.get('/cross-property/duplicates/scan', { params: { min_score: 0.6, skip: page * 20, limit: 20 } }),
          axios.get('/cross-property/guests/merges', { params: { limit: 10 } }),
        ]);
        response = { data: { ...(scan.data || {}), merge_history: history.data?.merges || [] } };
      }
      if (source === 'campaigns') response = await axios.get('/marketing/campaigns', { params: { limit: 100 } });
      if (source === 'journeys') response = await axios.get('/messaging-center/automation/rules');
      const payload = response?.data || {};
      const data = source === 'duplicates' ? (payload.matches || []) : source === 'campaigns' ? (payload.campaigns || []) : source === 'journeys' ? (payload.rules || []) : payload;
      setSources((prev) => ({ ...prev, [source]: { data, meta: payload, loading: false, loaded: true, error: '' } }));
    } catch (err) {
      const label = source === 'intelligence' ? 'CRM özeti' : source === 'duplicates' ? 'Mükerrer kayıtlar' : source === 'campaigns' ? 'Kampanyalar' : 'Otomatik yolculuklar';
      setSources((prev) => ({ ...prev, [source]: { ...prev[source], data: null, loading: false, loaded: true, error: err?.response?.data?.detail || `${label} yüklenemedi.` } }));
    }
  }, [duplicatePage]);

  useEffect(() => { loadSource('intelligence'); }, [loadSource]);
  useEffect(() => { if (SOURCE_TABS.has(activeTab)) loadSource(activeTab); }, [activeTab, loadSource]);
  useEffect(() => {
    if (sources.duplicates.loaded) loadSource('duplicates', { force: true, page: duplicatePage });
    // Only page changes should request a new duplicate slice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duplicatePage]);

  const refreshActive = () => loadSource(SOURCE_TABS.has(activeTab) ? activeTab : 'intelligence', { force: true, page: duplicatePage });
  const dashboard = sources.intelligence.data;
  const duplicates = useMemo(() => sources.duplicates.data || [], [sources.duplicates.data]);
  const campaigns = sources.campaigns.data || [];
  const journeys = sources.journeys.data || [];
  const currentSource = sources[activeTab] || sources.intelligence;
  const duplicateTotal = sources.duplicates.loaded ? (sources.duplicates.meta.matches_count ?? duplicates.length) : null;
  const visibleDuplicates = useMemo(() => {
    const query = duplicateSearch.trim().toLocaleLowerCase('tr-TR');
    if (!query) return duplicates;
    return duplicates.filter((row) => [row.left?.name, row.right?.name, row.left?.property_name, row.right?.property_name].some((v) => String(v || '').toLocaleLowerCase('tr-TR').includes(query)));
  }, [duplicates, duplicateSearch]);

  const undoMerge = async (mergeId) => {
    try {
      const result = await axios.post(`/cross-property/guests/merges/${encodeURIComponent(mergeId)}/undo`);
      toast.success(`${result.data?.bookings_restored || 0} rezervasyon ve ${result.data?.folios_restored || 0} folyo geri taşındı.`);
      await Promise.all([
        loadSource('duplicates', { force: true, page: duplicatePage }),
        loadSource('intelligence', { force: true }),
      ]);
    } catch (err) { toast.error(err?.response?.data?.detail || 'Birleştirme geri alınamadı.'); }
  };

  const mergeProfiles = async () => {
    const primaryId = mergeCandidate?.left?.id;
    const duplicateId = mergeCandidate?.right?.id;
    if (!primaryId || !duplicateId || !mergeVerified) return;
    setMerging(true);
    try {
      const result = await axios.post(`/cross-property/guests/${encodeURIComponent(primaryId)}/merge`, { target_guest_id: duplicateId });
      const message = `${result.data?.bookings_repointed || 0} rezervasyon ve ${result.data?.folios_repointed || 0} folyo birincil profile bağlandı.`;
      toast.success(message, result.data?.merge_id ? { action: { label: 'Geri al', onClick: () => undoMerge(result.data.merge_id) } } : undefined);
      setMergeCandidate(null); setMergeVerified(false);
      await loadSource('duplicates', { force: true, page: duplicatePage });
    } catch (err) { toast.error(err?.response?.data?.detail || 'Profiller birleştirilemedi.'); }
    finally { setMerging(false); }
  };

  const total = dashboard?.guests_analyzed || 0;
  const highValue = dashboard?.top_value_guests?.length || 0;
  const churn = dashboard?.high_churn_guests?.length || 0;
  const opportunities = dashboard?.upsell_opportunities?.length || 0;

  return <main className="min-h-screen bg-slate-50/70 p-4 lg:p-6" data-testid="crm-workspace"><div className="mx-auto max-w-[1500px] space-y-5">
    <header className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">Misafir yaşam döngüsü</p><h1 className="mt-1 text-3xl font-black tracking-tight text-slate-950">CRM Merkezi</h1><p className="mt-1 max-w-3xl text-sm text-slate-600">Misafir profili, değer, risk, ilişki, satış ve veri izinlerini tek çalışma alanından yönetin.</p></div><Button variant="outline" onClick={refreshActive} disabled={currentSource.loading} aria-label="Açık CRM sekmesini yenile"><RefreshCw className={`mr-2 h-4 w-4 ${currentSource.loading ? 'animate-spin' : ''}`} /> Yenile</Button></header>
    {sources.intelligence.error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{sources.intelligence.error}</div>}
    {dashboard?.data_quality?.suspicious_test_records_in_sample > 0 && <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Son {dashboard.data_quality.sample_size} kayıtta {dashboard.data_quality.suspicious_test_records_in_sample} olası test/demo kaydı bulundu. İşaretli test kayıtları analize dahil edilmedi; kalan kayıtları veri yönetişimi ekranından doğrulayın.</div>}
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="CRM özeti">{[
      ['Analiz edilen misafir', total, Users], ['Yüksek değerli', highValue, Brain], ['Kaybetme riski yüksek', churn, AlertTriangle], ['Gelir fırsatı', opportunities, Brain], ['Birleştirme adayı', duplicateTotal, ShieldCheck],
    ].map(([label, value, Icon]) => <Card key={label}><CardContent className="flex items-center gap-3 p-4"><span className="rounded-xl bg-blue-50 p-2 text-blue-700"><Icon className="h-5 w-5" /></span><div><p className="text-2xl font-bold text-slate-950">{value == null ? '—' : number.format(value)}</p><p className="text-xs text-slate-500">{label}</p></div></CardContent></Card>)}</section>
    <Tabs value={activeTab} onValueChange={selectTab}><TabsList className="h-auto w-full justify-start overflow-x-auto p-1"><TabsTrigger value="intelligence">Misafir 360</TabsTrigger><TabsTrigger value="duplicates">Mükerrer kayıtlar</TabsTrigger><TabsTrigger value="relations">Misafir ilişkileri</TabsTrigger><TabsTrigger value="campaigns">Kampanyalar</TabsTrigger><TabsTrigger value="journeys">Otomatik yolculuklar</TabsTrigger><TabsTrigger value="sales">Satış CRM</TabsTrigger><TabsTrigger value="privacy">KVKK ve izinler</TabsTrigger></TabsList>
      <TabsContent value="intelligence" className="space-y-4 pt-3">{sources.intelligence.loading ? <Loading /> : !dashboard ? <EmptyState title="Misafir verisi bulunamadı" description="CRM analizi için gerçek misafir ve konaklama verisi gereklidir." /> : <><p className={`text-right text-xs ${dashboard.performance?.slo_met === false ? 'font-medium text-amber-700' : 'text-slate-500'}`}>Toplu analiz · {number.format(dashboard.performance?.duration_ms || 0)} ms · hedef &lt; {number.format(dashboard.performance?.slo_target_ms || 1000)} ms</p><div className="grid gap-4 lg:grid-cols-3"><MetricList title="En değerli misafirler" rows={dashboard.top_value_guests} valueKey="total_revenue" detailKey="tier" suffix=" ₺" /><MetricList title="Kaybetme riski" rows={dashboard.high_churn_guests} valueKey="churn_score" detailKey="next_action" /><MetricList title="Ek gelir fırsatları" rows={dashboard.upsell_opportunities} valueKey="potential" detailKey="top_recommendation" suffix=" ₺" /></div></>}</TabsContent>
      <TabsContent value="duplicates" className="space-y-4 pt-3"><SourceCard source={sources.duplicates}><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><CardTitle>Kontrollü profil birleştirme kuyruğu</CardTitle>{sources.duplicates.loaded && <p className="mt-1 text-xs text-slate-500">Toplam {number.format(duplicateTotal || 0)} aday · bu sayfada {duplicates.length} kayıt · hash tabanlı tarama</p>}</div><Input className="max-w-xs" value={duplicateSearch} onChange={(e) => setDuplicateSearch(e.target.value)} placeholder="İsim veya tesis ara" aria-label="Mükerrer kayıtlarda ara" /></div>{(sources.duplicates.meta.candidate_pairs_truncated || sources.duplicates.meta.scan?.legacy_scan_truncated) && <div role="status" className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">Aday havuzu güvenli işlem sınırına ulaştı. Şifreleme backfill’ini tamamlayın veya aramayı daraltın.</div>}{visibleDuplicates.length === 0 ? <p className="text-sm text-slate-500">Eşik üzerinde birleştirme adayı bulunamadı. Kayıtlar otomatik olarak birleştirilmez.</p> : <div className="space-y-2">{visibleDuplicates.map((row, index) => <DuplicateRow key={`${row.left?.id}-${row.right?.id}-${index}`} row={row} onOpen={() => { setMergeCandidate(row); setMergeVerified(false); }} />)}</div>}<div className="mt-4 flex justify-end gap-2"><Button variant="outline" size="sm" disabled={!duplicatePage || sources.duplicates.loading} onClick={() => setDuplicatePage((p) => p - 1)}>Önceki</Button><Button variant="outline" size="sm" disabled={!sources.duplicates.meta.has_more || sources.duplicates.loading} onClick={() => setDuplicatePage((p) => p + 1)}>Sonraki</Button></div></SourceCard><MergeHistory rows={sources.duplicates.meta.merge_history || []} onUndo={undoMerge} /></TabsContent>
      <TabsContent value="relations"><GuestRelationsDashboard embedded /></TabsContent>
      <TabsContent value="campaigns" className="pt-3"><SourceCard source={sources.campaigns}><div className="mb-3 flex items-center justify-between gap-3"><CardTitle>Kampanya ve gerçekleşen gelir</CardTitle><Button asChild size="sm" variant="outline"><Link to="/app/mailing">Kampanya yönetimi</Link></Button></div>{campaigns.length ? <div className="space-y-2">{campaigns.map((campaign) => <div key={campaign.id} className="grid gap-2 rounded-lg border p-3 text-sm sm:grid-cols-[1fr_auto_auto]"><div><p className="font-medium text-slate-900">{campaign.name}</p><p className="text-xs text-slate-500">{SEGMENT_LABELS[campaign.segment] || 'Özel hedef kitle'} · {STATUS_LABELS[campaign.status] || 'Durum belirtilmedi'}</p></div><span>{number.format(campaign.attribution?.conversions || 0)} rezervasyon</span><span className="font-semibold">{number.format(campaign.attribution?.net_revenue || 0)} ₺ net gelir</span></div>)}</div> : <p className="text-sm text-slate-500">Henüz gerçek kampanya kaydı bulunmuyor.</p>}</SourceCard></TabsContent>
      <TabsContent value="journeys" className="pt-3"><SourceCard source={sources.journeys}><div className="mb-3 flex items-center justify-between gap-3"><div><CardTitle>Misafir iletişim otomasyonları</CardTitle>{sources.journeys.meta.duplicates_suppressed > 0 && <p className="mt-1 text-xs text-amber-700">{sources.journeys.meta.duplicates_suppressed} yinelenen kural güvenlik amacıyla çalıştırılmıyor.</p>}</div><Button asChild size="sm" variant="outline"><Link to="/messaging-dashboard">Otomasyonları yönet</Link></Button></div>{journeys.length ? <div className="space-y-2">{journeys.map((rule) => <div key={rule.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm"><div><p className="font-medium">{rule.name}</p><p className="text-xs text-slate-500">{TRIGGER_LABELS[rule.trigger_event] || 'Özel tetikleyici'} · {CHANNEL_LABELS[rule.channel] || 'İletişim kanalı'} · {rule.delay_minutes || 0} dakika gecikme</p></div><span className={`rounded-full px-2 py-1 text-xs font-medium ${rule.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>{rule.enabled ? 'Aktif' : 'Kapalı'}</span></div>)}</div> : <p className="text-sm text-slate-500">Etkin otomatik yolculuk bulunmuyor. İletişim izinleri gönderim sırasında uygulanır.</p>}</SourceCard></TabsContent>
      <TabsContent value="sales"><SalesCRM {...props} /></TabsContent><TabsContent value="privacy"><KVKKManager /></TabsContent>
    </Tabs>
    <Dialog open={Boolean(mergeCandidate)} onOpenChange={(open) => { if (!open && !merging) { setMergeCandidate(null); setMergeVerified(false); } }}><DialogContent><DialogHeader><DialogTitle>Misafir profillerini birleştir</DialogTitle></DialogHeader><div className="space-y-3 text-sm text-slate-700"><ProfileIdentity label="Korunacak profil" profile={mergeCandidate?.left} /><ProfileIdentity label="Arşivlenecek profil" profile={mergeCandidate?.right} /><p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900">Rezervasyon ve folyolar taşınır; geri alma yönetici müdahalesi gerektirir.</p><label className="flex items-start gap-2"><input className="mt-1" type="checkbox" checked={mergeVerified} onChange={(e) => setMergeVerified(e.target.checked)} /><span>İsim, tesis, maskeli e-posta ve telefon bilgilerini karşılaştırdım.</span></label></div><DialogFooter><Button variant="outline" onClick={() => setMergeCandidate(null)} disabled={merging}>Vazgeç</Button><Button onClick={mergeProfiles} disabled={merging || !mergeVerified}>{merging ? 'Birleştiriliyor…' : 'Onayla ve birleştir'}</Button></DialogFooter></DialogContent></Dialog>
  </div></main>;
};

const Loading = () => <p role="status" className="py-8 text-center text-sm text-slate-500">Yükleniyor…</p>;
const SourceCard = ({ source, children }) => <Card><CardContent className="p-5">{source.loading && !source.loaded ? <Loading /> : source.error ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{source.error}</div> : children}</CardContent></Card>;
const ProfileIdentity = ({ label, profile }) => <div className="rounded-lg border p-3"><p className="text-xs font-semibold uppercase text-slate-500">{label}</p><p className="font-semibold text-slate-900">{profile?.name || 'İsimsiz profil'}</p><p className="text-xs text-slate-600">{profile?.property_name || 'Tesis belirtilmedi'} · {maskEmail(profile?.email)} · {maskPhone(profile?.phone)}</p></div>;
const DuplicateRow = ({ row, onOpen }) => <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm"><div><div className="font-medium text-slate-900">{row.left?.name || 'Birincil profil'} ↔ {row.right?.name || 'Aday profil'}</div><div className="mt-1 text-xs text-slate-500">{row.left?.property_name || 'Tesis belirtilmedi'} ↔ {row.right?.property_name || 'Tesis belirtilmedi'} · Eşleşme %{Math.round(Number(row.score || 0) * 100)} · {(row.reasons || []).map(reasonLabel).join(', ')}</div><div className="mt-1 text-xs text-slate-500">{maskEmail(row.left?.email)} / {maskPhone(row.left?.phone)} ↔ {maskEmail(row.right?.email)} / {maskPhone(row.right?.phone)}</div></div><Button size="sm" variant="outline" onClick={onOpen}>İncele ve birleştir</Button></div>;
const MergeHistory = ({ rows, onUndo }) => <Card><CardHeader><CardTitle className="text-base">Son profil birleştirmeleri</CardTitle></CardHeader><CardContent>{rows.length ? <div className="space-y-2">{rows.map((row) => <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm"><div><p className="font-medium">{row.duplicate_guest_name || row.duplicate_guest_id} → {row.primary_guest_name || row.primary_guest_id}</p><p className="text-xs text-slate-500">{row.duplicate_property_name || 'Tesis belirtilmedi'} → {row.primary_property_name || 'Tesis belirtilmedi'} · {row.bookings_repointed || 0} rezervasyon · {row.folios_repointed || 0} folyo · {row.status === 'undone' ? 'Geri alındı' : row.status === 'completed' ? 'Tamamlandı' : 'İşleniyor'}</p></div>{row.status === 'completed' && <Button size="sm" variant="outline" onClick={() => onUndo(row.id)}>Birleştirmeyi geri al</Button>}</div>)}</div> : <p className="text-sm text-slate-500">Henüz birleştirme geçmişi yok.</p>}</CardContent></Card>;
const MetricList = ({ title, rows = [], valueKey, detailKey, suffix = '' }) => <Card><CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader><CardContent className="space-y-2">{rows?.length ? rows.slice(0, 10).map((row) => <div key={row.guest_id} className="flex items-start justify-between gap-3 rounded-lg border px-3 py-2"><span className="min-w-0"><span className="block truncate text-sm font-medium">{row.name || row.guest_name || row.guest_id}</span>{detailKey && row[detailKey] && <span className="mt-0.5 block text-xs text-slate-500">{row[detailKey]}</span>}</span><span className="shrink-0 text-sm tabular-nums text-slate-600">{number.format(Number(row[valueKey] || 0))}{suffix}</span></div>) : <p className="text-sm text-slate-500">Gerçek veri bulunamadı.</p>}</CardContent></Card>;

export default CRMWorkspace;
