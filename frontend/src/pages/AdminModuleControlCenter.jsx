import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import {
  Activity, ArrowLeftRight, Building2, Check, ChevronRight, CircleAlert,
  Clock3, PackageCheck, Pencil, RotateCcw, Save, Search, ShieldCheck, SlidersHorizontal, Users,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  PRODUCT_MODULES, moduleCounts, moduleIntegrationLabel, moduleSetupLabel, moduleUsageLabel,
  moduleWorkspaceLabel, resolveModuleState,
} from '@/lib/moduleCatalog';
import { persistEnteredTenantContext } from '@/lib/adminTenantContext';

const tenantId = (tenant) => tenant?.id || tenant?._id;

export default function AdminModuleControlCenter() {
  const navigate = useNavigate();
  const [tenants, setTenants] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState({});
  const [baseline, setBaseline] = useState({});
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [openingModule, setOpeningModule] = useState('');
  const [error, setError] = useState('');
  const [statusData, setStatusData] = useState({ entitlements: null, usage: null });
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState('');
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [products, setProducts] = useState([]);
  const [productDrafts, setProductDrafts] = useState({});
  const [savingProduct, setSavingProduct] = useState('');
  const [setupTasks, setSetupTasks] = useState([]);
  const [refundRequests, setRefundRequests] = useState([]);
  const [quoteRequests, setQuoteRequests] = useState([]);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await axios.get('/admin/tenants');
      const next = response.data?.tenants || [];
      setTenants(next);
      setSelectedId((current) => current || tenantId(next[0]) || '');
    } catch (err) {
      setError(err.response?.data?.detail || 'Oteller yüklenemedi.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const loadProducts = async () => {
    try {
      const [response, tasksResponse, refundsResponse, quotesResponse] = await Promise.all([
        axios.get('/module-store/admin/products'),
        axios.get('/module-store/admin/setup-tasks'),
        axios.get('/module-store/admin/refund-requests'),
        axios.get('/module-store/admin/quote-requests'),
      ]);
      const rows = Array.isArray(response.data?.products) ? response.data.products : [];
      setProducts(rows);
      setProductDrafts(Object.fromEntries(rows.map((item) => [item.key, { ...item }])));
      setSetupTasks(tasksResponse.data?.tasks || []);
      setRefundRequests(refundsResponse.data?.requests || []);
      setQuoteRequests(quotesResponse.data?.requests || []);
    } catch (err) { toast.error(err.response?.data?.detail || 'Mağaza fiyatları yüklenemedi.'); }
  };

  const updateSetupTask = async (task, status) => {
    try {
      await axios.patch(`/module-store/admin/setup-tasks/${task.id}`, { status, assignee: task.assignee || null });
      toast.success('Kurulum görevi güncellendi.'); await loadProducts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Kurulum görevi güncellenemedi.'); }
  };

  const approveRefund = async (request) => {
    try {
      await axios.post(`/module-store/admin/refund-requests/${request.id}/approve`);
      toast.success('İade ödeme sağlayıcısı üzerinden tamamlandı.'); await loadProducts();
    } catch (err) { toast.error(err.response?.data?.detail || 'İade tamamlanamadı.'); }
  };

  const updateQuoteRequest = async (request, status) => {
    try {
      await axios.patch(`/module-store/admin/quote-requests/${request.id}`, { status, assignee: request.assignee || null, internal_note: request.internal_note || null });
      toast.success('Teklif talebi güncellendi.'); await loadProducts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Teklif talebi güncellenemedi.'); }
  };

  const toggleCatalog = () => {
    const next = !catalogOpen; setCatalogOpen(next);
    if (next && !products.length) void loadProducts();
  };

  const saveProduct = async (key) => {
    setSavingProduct(key);
    try {
      const draftProduct = productDrafts[key];
      await axios.post('/module-store/admin/products', draftProduct);
      toast.success(`${draftProduct.name} fiyatı ve ticari sözleşmesi güncellendi.`);
      await loadProducts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Ürün kaydedilemedi.'); }
    finally { setSavingProduct(''); }
  };

  const selected = useMemo(
    () => tenants.find((tenant) => tenantId(tenant) === selectedId),
    [selectedId, tenants],
  );

  useEffect(() => {
    const next = { ...(selected?.modules || {}) };
    setDraft(next);
    setBaseline(next);
  }, [selected]);

  useEffect(() => {
    if (!selectedId) return undefined;
    let active = true;
    setStatusLoading(true);
    setStatusError('');
    Promise.all([
      axios.get(`/admin/tenants/${selectedId}/entitlements`),
      axios.get(`/admin/tenants/${selectedId}/usage`, { params: { days: 30 } }),
    ]).then(([entitlementsResponse, usageResponse]) => {
      if (!active) return;
      setStatusData({
        entitlements: entitlementsResponse.data || null,
        usage: usageResponse.data || null,
      });
    }).catch((err) => {
      if (!active) return;
      setStatusData({ entitlements: null, usage: null });
      setStatusError(err.response?.data?.detail || 'Lisans ve kullanım durumu alınamadı.');
    }).finally(() => {
      if (active) setStatusLoading(false);
    });
    return () => { active = false; };
  }, [selectedId]);

  const changes = useMemo(() => PRODUCT_MODULES.filter((item) => (
    Boolean(draft[item.key]) !== Boolean(baseline[item.key])
  )), [baseline, draft]);

  const previewTenant = useMemo(() => ({ ...selected, modules: draft }), [draft, selected]);
  const counts = useMemo(() => moduleCounts(previewTenant || {}), [previewTenant]);
  const visibleModules = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('tr-TR');
    return PRODUCT_MODULES.filter((item) => {
      const state = resolveModuleState(item, previewTenant || {});
      if (filter === 'active' && !state.enabled) return false;
      if (filter === 'inactive' && state.enabled) return false;
      if (filter === 'attention' && (!state.enabled || state.path)) return false;
      if (!needle) return true;
      return `${item.label} ${item.hint || ''} ${item.groupTitle}`.toLocaleLowerCase('tr-TR').includes(needle);
    });
  }, [filter, previewTenant, query]);

  const publish = async () => {
    if (!selected || changes.length === 0) return;
    setSaving(true);
    try {
      const response = await axios.patch(`/admin/tenants/${selectedId}/modules`, { modules: draft });
      const published = response.data?.modules || draft;
      setTenants((items) => items.map((tenant) => (
        tenantId(tenant) === selectedId ? { ...tenant, modules: published } : tenant
      )));
      setBaseline({ ...published });
      toast.success(`${changes.length} modül değişikliği yayınlandı.`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Modül değişiklikleri yayınlanamadı.');
    } finally {
      setSaving(false);
    }
  };

  const discard = () => setDraft({ ...baseline });

  const openInHotel = async (item) => {
    if (!selected || !item.path) return;
    setOpeningModule(item.key);
    try {
      const response = await axios.post(`/admin/tenants/${selectedId}/context`);
      persistEnteredTenantContext(response.data);
      navigate(item.path, { replace: true });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Otel çalışma alanı açılamadı.');
      setOpeningModule('');
    }
  };

  return (
    <main className="mx-auto max-w-[1500px] space-y-5 p-4 md:p-6" data-testid="module-control-center">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Süperadmin</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-950">Modül Kontrol Merkezi</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">Lisansı ve tesis erişimini tek ekrandan yönetin. Değişiklikler yayınlanana kadar taslakta kalır.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={toggleCatalog} data-testid="manage-marketplace-prices"><Pencil className="mr-2 h-4 w-4" /> Mağaza fiyatlarını yönet</Button>
          <Button variant="outline" onClick={discard} disabled={!changes.length || saving}>
            <RotateCcw className="mr-2 h-4 w-4" /> Taslağı geri al
          </Button>
          <Button onClick={publish} disabled={!changes.length || saving} data-testid="publish-module-changes">
            <Check className="mr-2 h-4 w-4" /> {saving ? 'Yayınlanıyor...' : `Yayınla${changes.length ? ` (${changes.length})` : ''}`}
          </Button>
        </div>
      </header>

      {catalogOpen && <section className="rounded-xl border border-blue-200 bg-white p-4 shadow-sm" aria-label="Modül mağazası fiyat yönetimi">
        <div className="mb-4"><h2 className="font-semibold text-slate-950">Modül mağazası fiyat ve sözleşme yönetimi</h2><p className="mt-1 text-xs text-slate-500">Değişiklikler fiyat versiyonu ve kaynak bilgisiyle denetim geçmişine kaydedilir. Checkout her zaman bu sözleşmeyi kullanır.</p></div>
        <div className="grid gap-3 xl:grid-cols-2">{products.map((product) => { const draftProduct = productDrafts[product.key] || product; const update = (field, value) => setProductDrafts((current) => ({ ...current, [product.key]: { ...current[product.key], [field]: value } })); return <article key={product.key} className="rounded-xl border border-slate-200 p-4">
          <div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold text-slate-900">{product.name}</h3><p className="text-xs text-slate-500">{product.key} · v{product.price_version || 1}</p></div><Button size="sm" onClick={() => saveProduct(product.key)} disabled={savingProduct === product.key}><Save className="mr-1.5 h-4 w-4" /> Kaydet</Button></div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <label className="text-xs text-slate-600">Birim fiyat ₺<Input type="number" value={draftProduct.unit_price_try ?? draftProduct.price_try ?? 0} onChange={(event) => { const value = Number(event.target.value); update('unit_price_try', value); update('price_try', value); }} /></label>
            <label className="text-xs text-slate-600">KDV %<Input type="number" value={draftProduct.tax_rate_pct ?? 20} onChange={(event) => update('tax_rate_pct', Number(event.target.value))} /></label>
            <label className="text-xs text-slate-600">Dahil birim<Input type="number" value={draftProduct.included_units ?? 1} onChange={(event) => update('included_units', Number(event.target.value))} /></label>
            <label className="text-xs text-slate-600">Kurulum dk<Input type="number" value={draftProduct.setup_minutes ?? 30} onChange={(event) => update('setup_minutes', Number(event.target.value))} /></label>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-3"><label className="text-xs text-slate-600">Fiyat ölçüsü<Input value={draftProduct.pricing_model || 'property'} onChange={(event) => update('pricing_model', event.target.value)} /></label><label className="text-xs text-slate-600">Kaynak<Input value={draftProduct.price_source || ''} onChange={(event) => update('price_source', event.target.value)} /></label><label className="text-xs text-slate-600">Geçerlilik başlangıcı<Input type="date" value={draftProduct.price_valid_from || ''} onChange={(event) => update('price_valid_from', event.target.value)} /></label></div>
        </article>; })}</div>
        {!products.length && <p className="py-8 text-center text-sm text-slate-500">Ürünler yükleniyor…</p>}
        <div className="mt-6 grid gap-4 xl:grid-cols-3">
          <div><h3 className="font-semibold text-slate-950">Teklif talepleri</h3><div className="mt-2 space-y-2">{quoteRequests.map((request) => <div key={request.id} className="rounded-lg border p-3 text-xs"><div className="flex items-start justify-between gap-2"><span><strong>{request.product_name}</strong><br />{request.tenant_name || request.tenant_id}<br /><a className="text-blue-700 underline" href={`mailto:${request.user_email || request.tenant_email}`}>{request.user_email || request.tenant_email || 'E-posta yok'}</a>{request.tenant_phone ? ` · ${request.tenant_phone}` : ''}<br /><span className="text-slate-500">No: {request.id?.slice(0, 8)} · {request.status}</span></span><div className="flex shrink-0 flex-col gap-1">{request.status === 'new' && <Button size="sm" variant="outline" onClick={() => updateQuoteRequest(request, 'contacted')}>İletişime geçildi</Button>}{!['closed', 'rejected'].includes(request.status) && <Button size="sm" onClick={() => updateQuoteRequest(request, 'closed')}>Kapat</Button>}</div></div></div>)}{!quoteRequests.length && <p className="text-xs text-slate-500">Bekleyen teklif talebi yok.</p>}</div></div>
          <div><h3 className="font-semibold text-slate-950">Dış entegrasyon kurulumları</h3><div className="mt-2 space-y-2">{setupTasks.map((task) => <div key={task.id} className="rounded-lg border p-3 text-xs"><div className="flex items-center justify-between gap-2"><strong>{task.product_key} · {task.tenant_id}</strong><span className={task.sla_due_at && task.sla_due_at < new Date().toISOString() && task.status !== 'completed' ? 'text-red-600' : 'text-slate-500'}>{task.status} · SLA {task.sla_due_at ? new Date(task.sla_due_at).toLocaleString('tr-TR') : '—'}</span></div><div className="mt-2 flex gap-2">{task.status === 'new' && <Button size="sm" variant="outline" onClick={() => updateSetupTask(task, 'in_progress')}>Başlat</Button>}{task.status !== 'completed' && <Button size="sm" onClick={() => updateSetupTask(task, 'completed')}>Tamamla</Button>}</div></div>)}{!setupTasks.length && <p className="text-xs text-slate-500">Bekleyen kurulum görevi yok.</p>}</div></div>
          <div><h3 className="font-semibold text-slate-950">İade talepleri</h3><div className="mt-2 space-y-2">{refundRequests.map((request) => <div key={request.id} className="flex items-center justify-between gap-2 rounded-lg border p-3 text-xs"><span><strong>{request.order_id}</strong><br />{request.reason} · {request.status}</span>{request.status === 'new' && <Button size="sm" onClick={() => approveRefund(request)}>Sağlayıcıdan iade et</Button>}</div>)}{!refundRequests.length && <p className="text-xs text-slate-500">Bekleyen iade talebi yok.</p>}</div></div>
        </div>
      </section>}

      {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error} <button className="font-semibold underline" onClick={load}>Yeniden dene</button></div>}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          [Building2, 'Oteller', tenants.length, 'Sistemdeki tesisler'],
          [PackageCheck, 'Açık modül', counts.enabled, `${counts.total} ürün modülü içinde`],
          [Activity, 'Başlatılabilir', counts.launchable, 'Gerçek çalışma alanına bağlı'],
          [CircleAlert, 'Giriş noktası eksik', counts.needsSetup, 'Açık fakat çalışma alanı tanımsız'],
        ].map(([Icon, label, value, note]) => (
          <article key={label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between"><p className="text-sm font-medium text-slate-600">{label}</p><Icon className="h-4 w-4 text-slate-400" /></div>
            <p className="mt-2 text-2xl font-bold text-slate-950">{loading ? '—' : value}</p>
            <p className="mt-1 text-xs text-slate-500">{note}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="h-fit rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Otel seçin</p>
          <div className="space-y-1" role="listbox" aria-label="Oteller">
            {tenants.map((tenant) => {
              const id = tenantId(tenant);
              const active = id === selectedId;
              const summary = moduleCounts(tenant);
              return (
                <button key={id} type="button" onClick={() => setSelectedId(id)} className={`w-full rounded-lg border p-3 text-left transition ${active ? 'border-slate-900 bg-slate-900 text-white' : 'border-transparent hover:bg-slate-50'}`}>
                  <span className="flex items-center justify-between gap-2"><span className="truncate text-sm font-semibold">{tenant.property_name || tenant.name || id}</span><ChevronRight className="h-4 w-4 opacity-60" /></span>
                  <span className={`mt-1 block text-xs ${active ? 'text-slate-300' : 'text-slate-500'}`}>{summary.enabled} modül · {tenant.subscription_tier || tenant.tier || 'basic'}</span>
                </button>
              );
            })}
          </div>
        </aside>

        <div className="min-w-0 space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
              <div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><Input className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Modül, işlev veya departman ara" /></div>
              <div className="flex flex-wrap gap-1" aria-label="Modül filtreleri">
                {[['all', 'Tümü'], ['active', 'Açık'], ['inactive', 'Kapalı'], ['attention', 'Kurulum gerekli']].map(([value, label]) => <Button key={value} size="sm" variant={filter === value ? 'default' : 'ghost'} onClick={() => setFilter(value)}>{label}</Button>)}
              </div>
            </div>
          </div>

          {changes.length > 0 && (
            <div className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <ArrowLeftRight className="h-5 w-5 shrink-0" /><span><strong>{changes.length} taslak değişiklik</strong> var. Etki yalnızca seçili otele uygulanacak.</span>
            </div>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="Seçili tesisin lisans ve kullanım özeti">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-slate-950">Tesis lisans ve kullanım özeti</h2>
                <p className="mt-1 text-xs text-slate-500">Paket, kullanıcı ve kullanım bilgileri yetkilendirme servisinden canlı okunur.</p>
              </div>
              {statusError && <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">{statusError}</span>}
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs text-slate-500"><PackageCheck className="h-3.5 w-3.5" /> Lisans ve paket</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{statusLoading ? 'Yükleniyor…' : statusData.entitlements?.plan_name || selected?.subscription_tier || 'Bilgi yok'}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">Durum: {statusData.entitlements?.subscription_status || 'bilinmiyor'}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs text-slate-500"><Users className="h-3.5 w-3.5" /> Aktif kullanıcı</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{statusLoading ? '—' : statusData.usage?.current_resources?.active_users ?? 'Ölçülmüyor'}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">Toplam: {statusData.usage?.current_resources?.users ?? '—'}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs text-slate-500"><Activity className="h-3.5 w-3.5" /> Son 30 gün</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{statusLoading ? '—' : Object.values(statusData.usage?.events || {}).reduce((sum, value) => sum + Number(value || 0), 0)} işlem</p>
                <p className="mt-0.5 text-[11px] text-slate-500">Ölçümlenen sistem olayları</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs text-slate-500"><Clock3 className="h-3.5 w-3.5" /> Son etkinlik</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{statusLoading ? '—' : statusData.usage?.last_activity_at ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(statusData.usage.last_activity_at)) : 'Kayıt yok'}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">Kullanım ölçüm kaydı</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs text-slate-500"><ShieldCheck className="h-3.5 w-3.5" /> Son modül yayını</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{selected?.module_control_updated_at ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(selected.module_control_updated_at)) : 'Kayıt yok'}</p>
                <p className="mt-0.5 truncate text-[11px] text-slate-500">{selected?.module_control_updated_by_name || selected?.module_control_updated_by || 'Henüz yayın yapılmadı'}</p>
              </div>
            </div>
          </section>

          <div className="grid gap-3 xl:grid-cols-2">
            {visibleModules.map((item) => {
              const state = resolveModuleState(item, previewTenant || {});
              const changed = Boolean(draft[item.key]) !== Boolean(baseline[item.key]);
              return (
                <article key={item.key} className={`rounded-xl border bg-white p-4 shadow-sm ${changed ? 'border-amber-300 ring-1 ring-amber-100' : 'border-slate-200'}`}>
                  <div className="flex gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100"><SlidersHorizontal className="h-5 w-5 text-slate-600" /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div><h2 className="text-sm font-semibold text-slate-950">{item.label}</h2><p className="mt-0.5 text-xs text-slate-500">{item.groupTitle}</p></div>
                        <Switch checked={state.enabled} onCheckedChange={(checked) => setDraft((current) => ({ ...current, [item.key]: checked }))} aria-label={`${item.label} modülünü ${state.enabled ? 'kapat' : 'aç'}`} />
                      </div>
                      <p className="mt-3 min-h-8 text-xs leading-5 text-slate-600">{item.hint || 'Modül açıklaması bulunmuyor.'}</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                        <span className={`rounded-full px-2 py-1 font-medium ${state.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>{state.enabled ? 'Erişim açık' : 'Erişim kapalı'}</span>
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600">{state.included ? 'Pakete dahil' : item.alwaysPaid || item.addon ? 'Ek lisans' : 'Özel seçim'}</span>
                        <span className={`rounded-full px-2 py-1 ${state.path ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-800'}`}>{moduleWorkspaceLabel(item, state)}</span>
                        {changed && <span className="rounded-full bg-amber-100 px-2 py-1 font-semibold text-amber-800">Taslak</span>}
                      </div>
                      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 rounded-lg border border-slate-100 bg-slate-50 p-3 text-[11px]">
                        <div><dt className="text-slate-500">Lisans</dt><dd className="mt-0.5 font-semibold text-slate-800">{state.licensed ? 'Etkin' : 'Lisans gerekli'}</dd></div>
                        <div><dt className="text-slate-500">Kurulum</dt><dd className="mt-0.5 font-semibold text-slate-800">{moduleSetupLabel(item, state)}</dd></div>
                        <div><dt className="text-slate-500">Entegrasyon</dt><dd className="mt-0.5 font-semibold text-slate-800">{moduleIntegrationLabel(item, state)}</dd></div>
                        <div><dt className="text-slate-500">Kullanım</dt><dd className="mt-0.5 font-semibold text-slate-800">{moduleUsageLabel(item, statusData.usage || {})}</dd></div>
                        <div><dt className="text-slate-500">Kullanıcı kapsamı</dt><dd className="mt-0.5 font-semibold text-slate-800">Tesis: {statusData.usage?.current_resources?.active_users ?? 'ölçülmüyor'} aktif</dd></div>
                        <div><dt className="text-slate-500">Yetkilendirme</dt><dd className="mt-0.5 font-semibold text-slate-800">Rol ve kullanıcı izni ayrıca uygulanır</dd></div>
                        <div className="col-span-2"><dt className="text-slate-500">Son değişiklik</dt><dd className="mt-0.5 font-semibold text-slate-800">{selected?.module_control_changes?.[item.key]?.changed_at ? `${new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(selected.module_control_changes[item.key].changed_at))} · ${selected.module_control_changes[item.key].changed_by_name || selected.module_control_changes[item.key].changed_by || 'Sistem'}` : 'Kayıt yok'}</dd></div>
                      </dl>
                      {state.launchable && (
                        <Button type="button" size="sm" variant="outline" className="mt-3 h-8" onClick={() => openInHotel(item)} disabled={Boolean(openingModule)}>
                          {openingModule === item.key ? 'Otel açılıyor...' : 'Otelde görüntüle'}
                        </Button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
          {!visibleModules.length && <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">Bu filtreye uyan modül bulunamadı.</div>}
        </div>
      </section>

      <footer className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600"><ShieldCheck className="h-4 w-4 text-emerald-600" /> Yayınlama mevcut yetkilendirme API’sini kullanır; kullanıcı rol ve izinleri ayrıca uygulanmaya devam eder.</footer>
    </main>
  );
}
