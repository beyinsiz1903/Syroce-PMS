import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Building2, Handshake, KeyRound, Pencil, Plus, RefreshCw, Search,
  TrendingUp, WalletCards,
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

const EMPTY_FORM = {
  name: '', contact_email: '', contact_phone: '', country: 'TR',
  default_commission_pct: '12', platform_fee_pct: '1',
};

const money = (value) => new Intl.NumberFormat('tr-TR', {
  style: 'currency', currency: 'TRY', maximumFractionDigits: 2,
}).format(Number(value || 0));

export default function AdminMarketplaceAgencies() {
  const [agencies, setAgencies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [createdKey, setCreatedKey] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/marketplace/v1/admin/agencies');
      setAgencies(response.data?.agencies || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Acenteler yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

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
    });
    setDialogOpen(true);
  };

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    const payload = {
      ...form,
      default_commission_pct: Number(form.default_commission_pct),
      platform_fee_pct: Number(form.platform_fee_pct),
    };
    try {
      if (editing) {
        await axios.patch(`/marketplace/v1/admin/agencies/${editing.id}`, payload);
        toast.success('Acente ayarları güncellendi');
      } else {
        const response = await axios.post('/marketplace/v1/admin/agencies', payload);
        setCreatedKey(response.data?.api_key || null);
        toast.success('Acente oluşturuldu');
      }
      setDialogOpen(false);
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Acente kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
      <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm" aria-label="Süperadmin kayıt türü">
        <Button asChild variant="ghost" size="sm" className="text-slate-600">
          <Link to="/admin/tenants"><Building2 className="mr-1.5 h-4 w-4" />Oteller</Link>
        </Button>
        <Button size="sm" className="pointer-events-none"><Handshake className="mr-1.5 h-4 w-4" />Acenteler</Button>
      </div>

      <PageHeader
        icon={Handshake}
        title="Acente Yönetimi"
        subtitle="Acenteleri, otel bağlantılarını, işlem hacmini ve acentenin Syroce'a ödeyeceği hizmet bedelini tek yerden yönetin."
        actions={<>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Yenile
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
                <th className="px-4 py-3">Syroce hizmet bedeli</th><th className="px-4 py-3">Hacim / Gelir</th>
                <th className="px-4 py-3 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? <tr><td colSpan="7" className="px-4 py-12 text-center text-slate-500">Acenteler yükleniyor…</td></tr>
                : filtered.length === 0 ? <tr><td colSpan="7" className="px-4 py-12 text-center text-slate-500">Eşleşen acente bulunamadı.</td></tr>
                  : filtered.map((agency) => (
                    <tr key={agency.id} className="hover:bg-slate-50/70">
                      <td className="px-4 py-3"><div className="font-semibold text-slate-900">{agency.name}</div><div className="text-xs text-slate-500">{agency.contact_email || 'İletişim e-postası yok'}{agency.contact_phone ? ` · ${agency.contact_phone}` : ''}</div></td>
                      <td className="px-4 py-3"><StatusBadge intent={agency.status === 'active' ? 'success' : 'danger'}>{agency.status === 'active' ? 'Aktif' : 'Devre dışı'}</StatusBadge></td>
                      <td className="px-4 py-3"><div className="font-medium">{agency.connected_hotels || 0} otel</div><div className="text-xs text-slate-500">{agency.booking_count || 0} rezervasyon</div></td>
                      <td className="px-4 py-3"><span className="font-semibold">%{Number(agency.default_commission_pct ?? 12).toLocaleString('tr-TR')}</span><div className="text-xs text-slate-500">Otel–acente payı</div></td>
                      <td className="px-4 py-3">{agency.platform_fee_pct == null ? <><span className="font-semibold text-indigo-700">Kanala göre</span><div className="text-xs text-slate-500">API %1 · Portal %2 (eski tarife)</div></> : <><span className="font-semibold text-indigo-700">%{Number(agency.platform_fee_pct).toLocaleString('tr-TR')}</span><div className="text-xs text-slate-500">Acente → Syroce hizmet bedeli</div></>}</td>
                      <td className="px-4 py-3"><div className="font-medium">{money(agency.gross_volume)}</div><div className="text-xs text-emerald-700">Gelir {money(agency.platform_revenue)}</div></td>
                      <td className="px-4 py-3 text-right"><Button variant="outline" size="sm" onClick={() => openEdit(agency)}><Pencil className="mr-1.5 h-3.5 w-3.5" />Düzenle</Button></td>
                    </tr>
                  ))}
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
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Vazgeç</Button><Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor…' : 'Kaydet'}</Button></div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(createdKey)} onOpenChange={(open) => !open && setCreatedKey(null)}>
        <DialogContent><DialogHeader><DialogTitle>API anahtarı oluşturuldu</DialogTitle></DialogHeader><div className="space-y-3"><div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><KeyRound className="mt-0.5 h-4 w-4 shrink-0" />Bu anahtar yalnızca şimdi gösterilir. Güvenli bir parola kasasına kaydedin.</div><Input readOnly value={createdKey || ''} className="font-mono text-xs" /><Button className="w-full" onClick={() => navigator.clipboard.writeText(createdKey || '').then(() => toast.success('API anahtarı kopyalandı'))}>Anahtarı kopyala</Button></div></DialogContent>
      </Dialog>
    </div>
  );
}
