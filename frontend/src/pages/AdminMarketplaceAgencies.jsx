import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { useQuery } from '@tanstack/react-query';
import {
  Ban, Building2, Handshake, KeyRound, Pencil, Plus, RefreshCw, RotateCcw,
  Search, ShieldCheck, TrendingUp, Users, WalletCards,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { KpiCard } from '@/components/ui/kpi-card';
import { PageHeader } from '@/components/ui/page-header';
import { StatusBadge } from '@/components/ui/status-badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { adminManagementQueries } from '@/lib/adminManagementQueries';
import { preloadRoute } from '@/routes/preload';

const EMPTY_FORM = {
  name: '', contact_email: '', contact_phone: '', country: 'TR',
  default_commission_pct: '12', platform_fee_pct: '1',
  issue_api_key: false, api_key_label: 'Ana entegrasyon',
};
const EMPTY_AGENCIES = [];

const money = (value) => new Intl.NumberFormat('tr-TR', {
  style: 'currency', currency: 'TRY', maximumFractionDigits: 2,
}).format(Number(value || 0));

const dateTime = (value) => value
  ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  : 'Henüz kullanılmadı';

const apiReadiness = (apiAccess) => {
  if (!apiAccess?.active) {
    return {
      intent: 'neutral',
      label: 'Kapalı',
      detail: 'Teknik API sırrı yok; acente yalnızca portal kullanıyor.',
    };
  }

  const hasVerifiedRequest = Boolean(apiAccess.last_used_at) || Number(apiAccess.usage_count || 0) > 0;
  if (!hasVerifiedRequest) {
    return {
      intent: 'warning',
      label: 'Etkinleştirme bekliyor',
      detail: 'Anahtar oluşturuldu; henüz doğrulanmış bir API isteği görülmedi.',
    };
  }

  return {
    intent: 'success',
    label: 'Kullanımda',
    detail: 'En az bir doğrulanmış API isteği kaydedildi.',
  };
};

export default function AdminMarketplaceAgencies() {
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [createdKey, setCreatedKey] = useState(null);
  const [accessAgency, setAccessAgency] = useState(null);
  const [accessAction, setAccessAction] = useState(null);
  const [accessBusy, setAccessBusy] = useState(false);
  const agenciesQuery = useQuery(adminManagementQueries.agencies);
  const agencies = agenciesQuery.data?.agencies ?? EMPTY_AGENCIES;
  const loading = agenciesQuery.isLoading;
  const refreshing = agenciesQuery.isFetching && !agenciesQuery.isLoading;

  const load = () => agenciesQuery.refetch();

  useEffect(() => {
    if (agenciesQuery.error) {
      toast.error(agenciesQuery.error.response?.data?.detail || 'Acenteler yüklenemedi');
    }
  }, [agenciesQuery.error]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('tr-TR');
    return agencies.filter((agency) => {
      const haystack = `${agency.name || ''} ${agency.contact_email || ''} ${agency.contact_phone || ''}`.toLocaleLowerCase('tr-TR');
      return (!needle || haystack.includes(needle)) && (status === 'all' || agency.status === status);
    });
  }, [agencies, query, status]);

  const totals = useMemo(() => agencies.reduce((acc, agency) => ({
    hotels: acc.hotels + Number(agency.connected_hotels || 0),
    bookings: acc.bookings + Number(agency.booking_count || 0),
    gross: acc.gross + Number(agency.gross_volume || 0),
    revenue: acc.revenue + Number(agency.platform_revenue || 0),
  }), { hotels: 0, bookings: 0, gross: 0, revenue: 0 }), [agencies]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (agency) => {
    setEditing(agency);
    setForm({
      name: agency.name || '',
      contact_email: agency.contact_email || '',
      contact_phone: agency.contact_phone || '',
      country: agency.country || 'TR',
      default_commission_pct: String(agency.default_commission_pct ?? 12),
      platform_fee_pct: String(agency.platform_fee_pct ?? 1),
      issue_api_key: false,
      api_key_label: 'Ana entegrasyon',
    });
    setDialogOpen(true);
  };

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    const payload = {
      name: form.name,
      contact_email: form.contact_email,
      contact_phone: form.contact_phone,
      country: form.country,
      default_commission_pct: Number(form.default_commission_pct),
      platform_fee_pct: Number(form.platform_fee_pct),
    };
    if (!editing) {
      payload.issue_api_key = form.issue_api_key;
      payload.api_key_label = form.api_key_label;
    }
    try {
      if (editing) {
        await axios.patch(`/marketplace/v1/admin/agencies/${editing.id}`, payload);
        toast.success('Acente ayarları güncellendi');
      } else {
        const response = await axios.post('/marketplace/v1/admin/agencies', payload);
        if (response.data?.api_key) {
          setCreatedKey({ value: response.data.api_key, agencyName: form.name, warning: response.data.warning });
        }
        toast.success(form.issue_api_key ? 'Acente ve API erişimi oluşturuldu' : 'Acente oluşturuldu; teknik API erişimi kapalı');
      }
      setDialogOpen(false);
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Acente kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };

  const confirmAccessAction = async () => {
    if (!accessAgency || !accessAction) return;
    setAccessBusy(true);
    try {
      if (accessAction === 'rotate') {
        const { data } = await axios.post(`/marketplace/v1/admin/agencies/${accessAgency.id}/api-keys/regenerate`, {
          label: accessAgency.api_access?.label || 'Ana entegrasyon',
        });
        setCreatedKey({ value: data.api_key, agencyName: accessAgency.name, warning: data.warning });
        toast.success(accessAgency.api_access?.active ? 'API anahtarı yenilendi; eski anahtar iptal edildi' : 'API erişimi oluşturuldu');
      } else {
        await axios.delete(`/marketplace/v1/admin/agencies/${accessAgency.id}/api-keys`);
        toast.success('Teknik API erişimi kapatıldı; portal kullanıcıları etkilenmedi');
      }
      setAccessAction(null);
      setAccessAgency(null);
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erişim işlemi tamamlanamadı');
    } finally {
      setAccessBusy(false);
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
      <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm" aria-label="Süperadmin kayıt türü">
        <Button asChild variant="ghost" size="sm" className="text-slate-600">
          <Link
            to="/admin/tenants"
            onMouseEnter={() => preloadRoute('/admin/tenants')}
            onFocus={() => preloadRoute('/admin/tenants')}
          ><Building2 className="mr-1.5 h-4 w-4" />Oteller</Link>
        </Button>
        <Button size="sm" className="pointer-events-none"><Handshake className="mr-1.5 h-4 w-4" />Acenteler</Button>
      </div>

      <PageHeader
        icon={Handshake}
        title="Acente Yönetimi"
        subtitle="Acenteleri, otel bağlantılarını, işlem hacmini ve acentenin Syroce'a ödeyeceği hizmet bedelini tek yerden yönetin."
        actions={<>
          <Button variant="outline" size="sm" onClick={load} disabled={agenciesQuery.isFetching}>
            <RefreshCw className={`mr-1.5 h-4 w-4 ${loading || refreshing ? 'animate-spin' : ''}`} />Yenile
          </Button>
          <Button size="sm" onClick={openCreate} data-testid="create-marketplace-agency">
            <Plus className="mr-1.5 h-4 w-4" />Yeni acente
          </Button>
        </>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard icon={Handshake} label="Toplam acente" value={agencies.length} />
        <KpiCard icon={Building2} label="Aktif otel bağlantısı" value={totals.hotels} intent="info" />
        <KpiCard icon={WalletCards} label="Rezervasyon" value={totals.bookings} intent="success" />
        <KpiCard icon={TrendingUp} label="Brüt işlem hacmi" value={money(totals.gross)} />
        <KpiCard icon={TrendingUp} label="Platform geliri" value={money(totals.revenue)} intent="success" />
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center">
          <div className="relative flex-1 md:max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Acente adı, e-posta veya telefon ara" />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-full md:w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm durumlar</SelectItem>
              <SelectItem value="active">Aktif</SelectItem>
              <SelectItem value="disabled">Devre dışı</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-slate-500">{filtered.length} sonuç</span>
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="border-b bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Acente</th><th className="px-4 py-3">Durum</th>
                <th className="px-4 py-3">Otel / Rezervasyon</th><th className="px-4 py-3">Satış komisyonu</th>
                <th className="px-4 py-3">Syroce hizmet bedeli</th><th className="px-4 py-3">Hacim / Gelir</th><th className="px-4 py-3">Erişim</th>
                <th className="px-4 py-3 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? <tr><td colSpan="8" className="px-4 py-12 text-center text-slate-500">Acenteler yükleniyor…</td></tr>
                : filtered.length === 0 ? <tr><td colSpan="8" className="px-4 py-12 text-center text-slate-500">Eşleşen acente bulunamadı.</td></tr>
                  : filtered.map((agency) => {
                    const readiness = apiReadiness(agency.api_access);
                    return <tr key={agency.id} className="hover:bg-slate-50/70">
                      <td className="px-4 py-3"><div className="font-semibold text-slate-900">{agency.name}</div><div className="text-xs text-slate-500">{agency.contact_email || 'İletişim e-postası yok'}{agency.contact_phone ? ` · ${agency.contact_phone}` : ''}</div></td>
                      <td className="px-4 py-3"><StatusBadge intent={agency.status === 'active' ? 'success' : 'danger'}>{agency.status === 'active' ? 'Aktif' : 'Devre dışı'}</StatusBadge></td>
                      <td className="px-4 py-3"><div className="font-medium">{agency.connected_hotels || 0} otel</div><div className="text-xs text-slate-500">{agency.booking_count || 0} rezervasyon</div></td>
                      <td className="px-4 py-3"><span className="font-semibold">%{Number(agency.default_commission_pct ?? 12).toLocaleString('tr-TR')}</span><div className="text-xs text-slate-500">Otel–acente payı</div></td>
                      <td className="px-4 py-3">{agency.platform_fee_pct == null ? <><span className="font-semibold text-indigo-700">Kanala göre</span><div className="text-xs text-slate-500">API %1 · Portal %2 (eski tarife)</div></> : <><span className="font-semibold text-indigo-700">%{Number(agency.platform_fee_pct).toLocaleString('tr-TR')}</span><div className="text-xs text-slate-500">Acente → Syroce hizmet bedeli</div></>}</td>
                      <td className="px-4 py-3"><div className="font-medium">{money(agency.gross_volume)}</div><div className="text-xs text-emerald-700">Gelir {money(agency.platform_revenue)}</div></td>
                      <td className="px-4 py-3"><div className="flex items-center gap-1.5 text-xs"><Users className="h-3.5 w-3.5 text-slate-400" />{agency.portal_access?.count || 0} portal kullanıcısı</div><div className={`mt-1 flex items-center gap-1.5 text-xs ${readiness.intent === 'success' ? 'text-emerald-700' : readiness.intent === 'warning' ? 'text-amber-700' : 'text-slate-500'}`} title={readiness.detail}><KeyRound className="h-3.5 w-3.5" />API {readiness.label}</div></td>
                      <td className="px-4 py-3 text-right"><div className="flex justify-end gap-2"><Button variant="outline" size="sm" onClick={() => { setAccessAgency(agency); setAccessAction(null); }}><ShieldCheck className="mr-1.5 h-3.5 w-3.5" />Erişim</Button><Button variant="outline" size="sm" onClick={() => openEdit(agency)}><Pencil className="mr-1.5 h-3.5 w-3.5" />Düzenle</Button></div></td>
                    </tr>;
                  })}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>{editing ? 'Acente ayarlarını düzenle' : 'Yeni acente oluştur'}</DialogTitle></DialogHeader>
          <form onSubmit={submit} className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2"><Label htmlFor="agency-name">Acente adı</Label><Input id="agency-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div className="space-y-2"><Label htmlFor="agency-email">İletişim e-postası</Label><Input id="agency-email" type="email" required value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} /></div>
              <div className="space-y-2"><Label htmlFor="agency-phone">Telefon</Label><Input id="agency-phone" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} /></div>
              <div className="space-y-2"><Label htmlFor="agency-country">Ülke kodu</Label><Input id="agency-country" maxLength={2} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase() })} /></div>
            </div>
            <div className="grid gap-4 rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 md:grid-cols-2">
              <div className="space-y-2"><Label htmlFor="agency-sales-rate">Otel–acente satış komisyonu (%)</Label><Input id="agency-sales-rate" type="number" min="0" max="100" step="0.01" required value={form.default_commission_pct} onChange={(e) => setForm({ ...form, default_commission_pct: e.target.value })} /><p className="text-xs text-slate-500">Otel sözleşmesinde özel oran yoksa kullanılır.</p></div>
              <div className="space-y-2"><Label htmlFor="agency-platform-rate">Syroce platform hizmet bedeli (%)</Label><Input id="agency-platform-rate" type="number" min="0" max="100" step="0.01" required value={form.platform_fee_pct} onChange={(e) => setForm({ ...form, platform_fee_pct: e.target.value })} /><p className="text-xs text-slate-500">Acentenin Syroce'a ödeyeceği uygulama bedelidir; otelin net hakedişini düşürmez.</p></div>
            </div>
            {!editing && <div className="space-y-3 rounded-xl border border-slate-200 p-4">
              <div><div className="font-semibold text-slate-900">Erişim yöntemi</div><p className="mt-1 text-xs text-slate-500">Acente portalı kullanıcı adı ve parola ile çalışır. API anahtarı yalnızca acentenin kendi yazılımını Syroce'a bağlayacağı zaman gerekir.</p></div>
              <button type="button" aria-pressed={form.issue_api_key} onClick={() => setForm({ ...form, issue_api_key: !form.issue_api_key })} className={`w-full rounded-lg border p-3 text-left transition-colors ${form.issue_api_key ? 'border-indigo-300 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'}`}>
                <div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 font-medium"><KeyRound className="h-4 w-4" />Teknik API entegrasyonu</span><StatusBadge intent={form.issue_api_key ? 'success' : 'neutral'}>{form.issue_api_key ? 'Anahtar oluşturulacak' : 'Kapalı'}</StatusBadge></div>
                <p className="mt-1 text-xs text-slate-500">Sunucudan sunucuya müsaitlik, fiyat ve rezervasyon işlemleri için kullanılır; insan kullanıcı girişi değildir.</p>
              </button>
              {form.issue_api_key && <div className="space-y-2"><Label htmlFor="agency-key-label">Entegrasyon adı</Label><Input id="agency-key-label" required minLength={2} maxLength={80} value={form.api_key_label} onChange={(e) => setForm({ ...form, api_key_label: e.target.value })} /><p className="text-xs text-amber-700">Anahtar yalnızca bir kez gösterilir. Acentenin teknik sorumlusuna güvenli bir sır paylaşım yöntemiyle iletin.</p></div>}
            </div>}
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Vazgeç</Button><Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor…' : 'Kaydet'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(accessAgency)} onOpenChange={(open) => { if (!open && !accessBusy) { setAccessAgency(null); setAccessAction(null); } }}>
        <DialogContent className="sm:max-w-xl"><DialogHeader><DialogTitle>{accessAgency?.name} · Erişim yönetimi</DialogTitle></DialogHeader>{accessAgency && <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2"><div className="rounded-lg border p-3"><div className="flex items-center gap-2 font-medium"><Users className="h-4 w-4" />Acente portalı</div><div className="mt-2 text-2xl font-semibold">{accessAgency.portal_access?.count || 0}</div><p className="text-xs text-slate-500">aktif insan kullanıcısı</p>{accessAgency.portal_access?.last_login && <p className="mt-2 text-xs text-slate-500">Son giriş: {dateTime(accessAgency.portal_access.last_login)}</p>}</div><div className="rounded-lg border p-3"><div className="flex items-center gap-2 font-medium"><KeyRound className="h-4 w-4" />Teknik API</div><div className="mt-2"><StatusBadge intent={apiReadiness(accessAgency.api_access).intent}>{apiReadiness(accessAgency.api_access).label}</StatusBadge></div><p className="mt-2 text-xs text-slate-500">Portal oturumundan bağımsızdır.</p></div></div>
          {accessAgency.api_access?.active ? <div className="space-y-3 rounded-lg bg-slate-50 p-3 text-sm"><div className="space-y-2"><div className="flex justify-between gap-4"><span className="text-slate-500">Entegrasyon</span><span className="font-medium">{accessAgency.api_access.label || 'Ana entegrasyon'}</span></div><div className="flex justify-between gap-4"><span className="text-slate-500">Anahtar</span><code className="text-xs">{accessAgency.api_access.key_prefix}</code></div><div className="flex justify-between gap-4"><span className="text-slate-500">Son kullanım</span><span>{dateTime(accessAgency.api_access.last_used_at)}</span></div><div className="flex justify-between gap-4"><span className="text-slate-500">İstek sayısı</span><span>{Number(accessAgency.api_access.usage_count || 0).toLocaleString('tr-TR')}</span></div>{accessAgency.api_access.last_used_ip && <div className="flex justify-between gap-4"><span className="text-slate-500">Son kaynak IP</span><code className="text-xs">{accessAgency.api_access.last_used_ip}</code></div>}</div><div className={`rounded-md border p-2.5 text-xs ${apiReadiness(accessAgency.api_access).intent === 'warning' ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-emerald-200 bg-emerald-50 text-emerald-900'}`}><p className="font-medium">{apiReadiness(accessAgency.api_access).detail}</p>{apiReadiness(accessAgency.api_access).intent === 'warning' && <p className="mt-1">Anahtarı yalnızca acentenin teknik sorumlusuna güvenli sır paylaşımıyla iletin; ilk başarılı istekten sonra durum otomatik olarak “Kullanımda” olur.</p>}</div><Link to="/b2b/docs" className="inline-flex text-xs font-medium text-indigo-700 hover:underline">B2B API belgelerini aç →</Link></div> : <p className="rounded-lg border border-dashed p-4 text-sm text-slate-600">Bu acente için teknik API sırrı bulunmuyor. Acente yalnızca portal kullanacaksa bu doğru ve daha güvenli durumdur.</p>}
          {accessAction && <div className={`rounded-lg border p-3 text-sm ${accessAction === 'revoke' ? 'border-red-200 bg-red-50 text-red-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`}><p>{accessAction === 'revoke' ? 'API erişimi hemen durdurulacak. Portal kullanıcıları etkilenmeyecek.' : accessAgency.api_access?.active ? 'Mevcut anahtar anında geçersiz olacak ve yeni anahtar yalnızca bir kez gösterilecek.' : 'Yeni API anahtarı yalnızca bir kez gösterilecek.'}</p><div className="mt-3 flex justify-end gap-2"><Button variant="outline" size="sm" onClick={() => setAccessAction(null)} disabled={accessBusy}>Vazgeç</Button><Button size="sm" variant={accessAction === 'revoke' ? 'destructive' : 'default'} onClick={confirmAccessAction} disabled={accessBusy}>{accessBusy ? 'İşleniyor…' : 'Onayla'}</Button></div></div>}
          {!accessAction && <div className="flex justify-end gap-2">{accessAgency.api_access?.active && <Button variant="destructive" size="sm" onClick={() => setAccessAction('revoke')}><Ban className="mr-1.5 h-4 w-4" />API erişimini kapat</Button>}<Button size="sm" onClick={() => setAccessAction('rotate')} disabled={accessAgency.status !== 'active'}><RotateCcw className="mr-1.5 h-4 w-4" />{accessAgency.api_access?.active ? 'Anahtarı yenile' : 'API anahtarı oluştur'}</Button></div>}
        </div>}</DialogContent>
      </Dialog>

      <Dialog open={Boolean(createdKey)} onOpenChange={(open) => !open && setCreatedKey(null)}>
        <DialogContent><DialogHeader><DialogTitle>Teknik API anahtarı oluşturuldu</DialogTitle></DialogHeader><div className="space-y-3"><div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><KeyRound className="mt-0.5 h-4 w-4 shrink-0" /><span><strong>{createdKey?.agencyName}</strong> için oluşturulan bu anahtar insan kullanıcı girişi değildir. Yalnızca acentenin sunucu entegrasyonunda <code>X-API-Key</code> başlığıyla kullanılmalı; parola kasasında saklanmalı ve açık e-posta/mesajla gönderilmemelidir.</span></div><Input readOnly value={createdKey?.value || ''} className="font-mono text-xs" /><Button className="w-full" onClick={() => navigator.clipboard.writeText(createdKey?.value || '').then(() => toast.success('API anahtarı kopyalandı'))}>Anahtarı güvenli teslim için kopyala</Button><div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600"><strong className="text-slate-800">Teslim ve doğrulama sırası:</strong> Anahtarı acentenin teknik sorumlusuna parola kasası veya güvenli sır paylaşımıyla iletin. Teknik ekip ilk başarılı isteği attığında erişim ekranındaki durum otomatik olarak “Kullanımda” olur.</div><Link to="/b2b/docs" className="block text-center text-xs font-medium text-indigo-700 hover:underline">B2B API belgelerini aç →</Link><p className="text-center text-xs text-slate-500">Pencere kapatıldıktan sonra tam anahtar tekrar görüntülenemez.</p></div></DialogContent>
      </Dialog>
    </div>
  );
}
