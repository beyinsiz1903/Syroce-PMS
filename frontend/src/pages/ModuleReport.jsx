import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslation } from 'react-i18next';
import { alertDialog } from '@/lib/dialogs';
import { CheckCircle2, XCircle } from 'lucide-react';

const BOOL_ICON = (val) => val
  ? <CheckCircle2 className="w-4 h-4 text-emerald-600 inline" aria-label="evet" />
  : <XCircle className="w-4 h-4 text-rose-600 inline" aria-label="hayır" />;

const ModuleReport = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('');
  const [onlyWithAI, setOnlyWithAI] = useState(false);
  const [onlyWithoutInvoices, setOnlyWithoutInvoices] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createForm, setCreateForm] = useState({
    property_name: '',
    email: '',
    password: '',
    name: '',
    phone: '',
    address: '',
    location: '',
    description: '',
    subscription_days: 30  // Default 30 days
  });

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/admin/module-report');
      setRows(res.data?.rows || []);
    } catch (err) {
      console.error('Failed to load module report', err);
      setError('Modül raporu yüklenirken bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (filter) {
        const name = (r.property_name || '').toLowerCase();
        const loc = (r.location || '').toLowerCase();
        const term = filter.toLowerCase();
        if (!name.includes(term) && !loc.includes(term)) return false;
      }
      if (onlyWithAI && !r.mod_ai) return false;
      if (onlyWithoutInvoices && r.mod_invoices) return false;
      return true;
    });
  }, [rows, filter, onlyWithAI, onlyWithoutInvoices]);

  const handleCreateTenant = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    
    try {
      await axios.post('/admin/tenants', createForm);
      setShowCreateModal(false);
      setCreateForm({
        property_name: '',
        email: '',
        password: '',
        name: '',
        phone: '',
        address: '',
        location: '',
        description: '',
        subscription_days: 30
      });
      await loadReport(); // Reload list
      alertDialog({ message: 'Otel başarıyla oluşturuldu!' });
    } catch (err) {
      console.error('Failed to create tenant', err);
      setError(err.response?.data?.detail || 'Otel oluşturulurken bir hata oluştu');
    } finally {
      setCreating(false);
    }
  };

  const handleExportCsv = () => {
    if (!filteredRows.length) return;

    const headers = [
      'tenant_id',
      'property_name',
      'location',
      'subscription_tier',
      'pms',
      'pms_mobile',
      'mobile_housekeeping',
      'mobile_revenue',
      'gm_dashboards',
      'reports',
      'invoices',
      'ai',
      'ai_chatbot',
      'ai_pricing',
      'ai_whatsapp',
      'ai_predictive',
      'ai_reputation',
      'ai_revenue_autopilot',
      'ai_social_radar',
    ];

    const lines = [];
    lines.push(headers.join(','));

    filteredRows.forEach((r) => {
      const row = [
        r.tenant_id || '',
        (r.property_name || '').replace(/,/g, ' '),
        (r.location || '').replace(/,/g, ' '),
        r.subscription_tier || 'basic',
        r.mod_pms ? '1' : '0',
        r.mod_pms_mobile ? '1' : '0',
        r.mod_mobile_housekeeping ? '1' : '0',
        r.mod_mobile_revenue ? '1' : '0',
        r.mod_gm_dashboards ? '1' : '0',
        r.mod_reports ? '1' : '0',
        r.mod_invoices ? '1' : '0',
        r.mod_ai ? '1' : '0',
        r.mod_ai_chatbot ? '1' : '0',
        r.mod_ai_pricing ? '1' : '0',
        r.mod_ai_whatsapp ? '1' : '0',
        r.mod_ai_predictive ? '1' : '0',
        r.mod_ai_reputation ? '1' : '0',
        r.mod_ai_revenue_autopilot ? '1' : '0',
        r.mod_ai_social_radar ? '1' : '0',
      ];
      lines.push(row.join(','));
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'module_report.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="p-4 md:p-6 space-y-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold">Modül / Lisans Raporu</h1>
            <p className="text-sm text-gray-600 max-w-2xl">
              Tüm oteller için hangi modüllerin aktif olduğunu tek ekranda görüntüleyin. Bu tabloyu,
              hangi otelin hangi paketi kullandığını hızlıca görmek için kullanabilirsiniz.
            </p>
          </div>
          <div className="flex flex-col md:flex-row gap-2 md:items-center">
            <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
              <DialogTrigger asChild>
                <Button variant="default" size="sm" className="text-xs bg-blue-600 hover:bg-blue-700 text-white">
                  Yeni Otel Oluştur
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>Yeni Otel Oluştur</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleCreateTenant} className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="property_name">Otel Adı *</Label>
                      <Input
                        id="property_name"
                        required
                        value={createForm.property_name}
                        onChange={(e) => setCreateForm({ ...createForm, property_name: e.target.value })}
                        placeholder="Örn: Grand Hotel İstanbul"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="location">Lokasyon</Label>
                      <Input
                        id="location"
                        value={createForm.location}
                        onChange={(e) => setCreateForm({ ...createForm, location: e.target.value })}
                        placeholder="Örn: İstanbul, Türkiye"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="address">Adres *</Label>
                    <Input
                      id="address"
                      required
                      value={createForm.address}
                      onChange={(e) => setCreateForm({ ...createForm, address: e.target.value })}
                      placeholder="Otel adresi"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="description">Açıklama</Label>
                    <Input
                      id="description"
                      value={createForm.description}
                      onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                      placeholder="Otel hakkında kısa bilgi"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="subscription_days">Üyelik Süresi *</Label>
                    <select
                      id="subscription_days"
                      required
                      value={createForm.subscription_days || ''}
                      onChange={(e) => setCreateForm({ ...createForm, subscription_days: e.target.value ? parseInt(e.target.value) : null })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="30">30 Gün (1 Ay) - Trial</option>
                      <option value="60">60 Gün (2 Ay)</option>
                      <option value="90">90 Gün (3 Ay)</option>
                      <option value="180">180 Gün (6 Ay)</option>
                      <option value="365">365 Gün (1 Yıl)</option>
                      <option value="">Sınırsız (Lifetime)</option>
                    </select>
                    <p className="text-xs text-gray-500">
                      Üyelik başlangıç tarihi: Bugün | Bitiş: {
                        createForm.subscription_days 
                          ? new Date(Date.now() + createForm.subscription_days * 24 * 60 * 60 * 1000).toLocaleDateString('tr-TR')
                          : 'Sınırsız'
                      }
                    </p>
                  </div>

                  <div className="border-t pt-4 mt-4">
                    <h3 className="font-semibold mb-3">Admin Kullanıcı Bilgileri</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="name">Admin Adı *</Label>
                        <Input
                          id="name"
                          required
                          value={createForm.name}
                          onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                          placeholder="Örn: Ahmet Yılmaz"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="phone">Telefon *</Label>
                        <Input
                          id="phone"
                          required
                          value={createForm.phone}
                          onChange={(e) => setCreateForm({ ...createForm, phone: e.target.value })}
                          placeholder="+90 5XX XXX XX XX"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mt-4">
                      <div className="space-y-2">
                        <Label htmlFor="email">Email *</Label>
                        <Input
                          id="email"
                          type="email"
                          required
                          value={createForm.email}
                          onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                          placeholder="admin@otel.com"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="password">Şifre *</Label>
                        <Input
                          id="password"
                          type="password"
                          required
                          value={createForm.password}
                          onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                          placeholder="En az 6 karakter"
                        />
                      </div>
                    </div>
                  </div>

                  {error && (
                    <div className="p-3 rounded-md bg-red-50 text-red-700 text-sm">{error}</div>
                  )}

                  <div className="flex justify-end gap-2 pt-4">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setShowCreateModal(false)}
                      disabled={creating}
                    >
                      İptal
                    </Button>
                    <Button type="submit" disabled={creating}>
                      {creating ? 'Oluşturuluyor...' : 'Otel Oluştur'}
                    </Button>
                  </div>
                </form>
              </DialogContent>
            </Dialog>

            <input
              type="text"
              placeholder="Otel adı veya lokasyona göre filtrele..."
              className="border rounded-md px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <label className="flex items-center gap-1 text-xs text-gray-700">
              <input
                type="checkbox"
                className="h-3 w-3"
                checked={onlyWithAI}
                onChange={(e) => setOnlyWithAI(e.target.checked)}
              />
              <span>Yalnızca AI kullanan oteller</span>
            </label>
            <label className="flex items-center gap-1 text-xs text-gray-700">
              <input
                type="checkbox"
                className="h-3 w-3"
                checked={onlyWithoutInvoices}
                onChange={(e) => setOnlyWithoutInvoices(e.target.checked)}
              />
              <span>Fatura modülü kapalı olanlar</span>
            </label>
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              onClick={handleExportCsv}
              disabled={loading || !filteredRows.length}
            >
              CSV Dışa Aktar
            </Button>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-md bg-red-50 text-red-700 text-sm">{error}</div>
        )}

        {loading ? (
          <div className="text-sm text-gray-500">Modül raporu yükleniyor...</div>
        ) : (
          <Card className="overflow-hidden">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center justify-between">
                <span>Otellere Göre Modül Durumu</span>
                <span className="text-xs text-gray-500">
                  Toplam {filteredRows.length} / {rows.length} otel
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs border-t">
                  <thead className="bg-gray-50 border-b">
                    <tr className="text-left whitespace-nowrap">
                      <th className="px-3 py-2 font-medium text-gray-700">Otel</th>
                      <th className="px-3 py-2 font-medium text-gray-700">Lokasyon</th>
                      <th className="px-3 py-2 font-medium text-gray-700">Plan</th>
                      <th className="px-3 py-2 font-medium text-gray-700">PMS</th>
                      <th className="px-3 py-2 font-medium text-gray-700">Mobil</th>
                      <th className="px-3 py-2 font-medium text-gray-700">HK Mobil</th>
                      <th className="px-3 py-2 font-medium text-gray-700">Revenue Mobil</th>
                      <th className="px-3 py-2 font-medium text-gray-700">GM</th>
                      <th className="px-3 py-2 font-medium text-gray-700">Rapor</th>
                      <th className="px-3 py-2 font-medium text-gray-700">Fatura</th>
                      <th className="px-3 py-2 font-medium text-gray-700">AI Genel</th>
                      <th className="px-3 py-2 font-medium text-gray-700">AI Chatbot</th>
                      <th className="px-3 py-2 font-medium text-gray-700">AI Pricing</th>
                      <th className="px-3 py-2 font-medium text-gray-700">AI WhatsApp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((r) => (
                      <tr key={r.tenant_id || r.property_name} className="border-b hover:bg-gray-50/60">
                        <td className="px-3 py-2">
                          <div className="flex flex-col">
                            <span className="font-medium text-gray-800">{r.property_name || 'Otel'}</span>
                            {r.tenant_id && (
                              <span className="text-[10px] text-gray-400">ID: {r.tenant_id}</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-gray-600">{r.location || '-'}</td>
                        <td className="px-3 py-2">
                          <Badge variant="outline" className="text-[10px] uppercase">
                            {r.subscription_tier || 'basic'}
                          </Badge>
                        </td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_pms)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_pms_mobile)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_mobile_housekeeping)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_mobile_revenue)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_gm_dashboards)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_reports)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_invoices)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_ai)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_ai_chatbot)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_ai_pricing)}</td>
                        <td className="px-3 py-2">{BOOL_ICON(r.mod_ai_whatsapp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
};

export default ModuleReport;
