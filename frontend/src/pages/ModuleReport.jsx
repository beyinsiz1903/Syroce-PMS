import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  CheckCircle2, XCircle, FileSpreadsheet, Plus, RefreshCw, Search,
  Building2, Sparkles, Receipt, BarChart3,
} from 'lucide-react';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import CreateTenantModal from './admin/CreateTenantModal';
import { useTranslation } from 'react-i18next';

const TIER_META = {
  mini:         { label: 'MINI', intent: 'success' },
  basic:        { label: 'BASIC', intent: 'success' },
  professional: { label: 'PRO',   intent: 'info'    },
  enterprise:   { label: 'ENT',   intent: 'default' },
};

const COLUMNS = [
  { key: 'mod_pms',                  label: 'PMS' },
  { key: 'mod_pms_mobile',           label: 'Mobil' },
  { key: 'mod_mobile_housekeeping',  label: 'HK Mobil' },
  { key: 'mod_mobile_revenue',       label: 'Revenue Mobil' },
  { key: 'mod_gm_dashboards',        label: 'GM' },
  { key: 'mod_reports',              label: 'Rapor' },
  { key: 'mod_invoices',             label: 'Fatura' },
  { key: 'mod_ai',                   label: 'AI Genel' },
  { key: 'mod_ai_chatbot',           label: 'AI Chatbot' },
  { key: 'mod_ai_pricing',           label: 'AI Pricing' },
  { key: 'mod_ai_whatsapp',          label: 'AI WhatsApp' },
];

const BoolCell = ({ value }) => (
  value
    ? <CheckCircle2 className="w-4 h-4 text-emerald-600 inline" aria-label="aktif" />
    : <XCircle className="w-4 h-4 text-rose-500 inline" aria-label={t('cm.pages_ModuleReport.kapali')} />
);

const ModuleReport = () => {
  const { t } = useTranslation();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [onlyWithAI, setOnlyWithAI] = useState(false);
  const [onlyWithoutInvoices, setOnlyWithoutInvoices] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const loadReport = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/module-report');
      setRows(res.data?.rows || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Modül raporu yüklenirken bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadReport(); }, []);

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (filter) {
        const term = filter.toLowerCase();
        const name = (r.property_name || '').toLowerCase();
        const loc = (r.location || '').toLowerCase();
        const id = (r.tenant_id || '').toLowerCase();
        if (!name.includes(term) && !loc.includes(term) && !id.includes(term)) return false;
      }
      if (onlyWithAI && !r.mod_ai) return false;
      if (onlyWithoutInvoices && r.mod_invoices) return false;
      return true;
    });
  }, [rows, filter, onlyWithAI, onlyWithoutInvoices]);

  const stats = useMemo(() => ({
    total: rows.length,
    ai: rows.filter((r) => r.mod_ai).length,
    invoices: rows.filter((r) => r.mod_invoices).length,
    enterprise: rows.filter((r) => (r.subscription_tier || '').toLowerCase() === 'enterprise').length,
  }), [rows]);

  const handleExportCsv = () => {
    if (!filteredRows.length) return;
    const headers = [
      'tenant_id', 'property_name', 'location', 'subscription_tier',
      'pms', 'pms_mobile', 'mobile_housekeeping', 'mobile_revenue',
      'gm_dashboards', 'reports', 'invoices',
      'ai', 'ai_chatbot', 'ai_pricing', 'ai_whatsapp',
      'ai_predictive', 'ai_reputation', 'ai_revenue_autopilot', 'ai_social_radar',
    ];
    const escape = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`;
    const lines = [headers.join(',')];
    filteredRows.forEach((r) => {
      lines.push([
        escape(r.tenant_id || ''),
        escape(r.property_name || ''),
        escape(r.location || ''),
        escape(r.subscription_tier || 'basic'),
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
      ].join(','));
    });
    const blob = new Blob(['\uFEFF' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `module_report_${new Date().toISOString().slice(0,10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success('CSV dışa aktarıldı');
  };

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
      <PageHeader
        icon={BarChart3}
        title={t('cm.pages_ModuleReport.modul_lisans_raporu')}
        subtitle={t('cm.pages_ModuleReport.tum_oteller_icin_hangi_modullerin_aktif_')}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleExportCsv} disabled={loading || !filteredRows.length}>
              <FileSpreadsheet className="w-4 h-4 mr-1.5" aria-hidden="true" /> {t('cm.pages_ModuleReport.csv_disa_aktar')}
            </Button>
            <Button variant="outline" size="sm" onClick={loadReport} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" /> {t('cm.pages_ModuleReport.yenile')}
            </Button>
            <Button size="sm" onClick={() => setShowCreateModal(true)}>
              <Plus className="w-4 h-4 mr-1.5" aria-hidden="true" /> {t('cm.pages_ModuleReport.yeni_otel_olustur')}
            </Button>
          </div>
        }
      />

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={Building2}  label={t('cm.pages_ModuleReport.toplam_otel')}            value={stats.total}      intent="default" />
        <KpiCard icon={Sparkles}   label="AI Kullanan"            value={stats.ai}         intent="info"
          active={onlyWithAI} onClick={() => setOnlyWithAI((v) => !v)}
        />
        <KpiCard icon={Receipt}    label={t('cm.pages_ModuleReport.fatura_aktif')}           value={stats.invoices}   intent="success" />
        <KpiCard icon={Building2}  label="Enterprise Plan"        value={stats.enterprise} intent="default" />
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-3 flex flex-col md:flex-row gap-3 md:items-center">
          <div className="relative flex-1 max-w-md w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
            <Input
              type="text"
              placeholder={t('cm.pages_ModuleReport.otel_adi_lokasyon_veya_id_ile_ara')}
              className="pl-9"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Otel arama"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
            <Checkbox
              checked={onlyWithAI}
              onCheckedChange={(v) => setOnlyWithAI(!!v)}
              aria-label={t('cm.pages_ModuleReport.yalnizca_ai_kullanan_oteller')}
            />
            <span>{t('cm.pages_ModuleReport.yalnizca_ai_kullanan_oteller_4b851')}</span>
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
            <Checkbox
              checked={onlyWithoutInvoices}
              onCheckedChange={(v) => setOnlyWithoutInvoices(!!v)}
              aria-label={t('cm.pages_ModuleReport.fatura_modulu_kapali_olanlar')}
            />
            <span>{t('cm.pages_ModuleReport.fatura_modulu_kapali_olanlar_6c8ee')}</span>
          </label>
          {(filter || onlyWithAI || onlyWithoutInvoices) && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-slate-500"
              onClick={() => { setFilter(''); setOnlyWithAI(false); setOnlyWithoutInvoices(false); }}
            >
              Filtreleri temizle
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Table */}
      {loading ? (
        <div className="text-sm text-slate-500 text-center py-12">{t('cm.pages_ModuleReport.modul_raporu_yukleniyor')}</div>
      ) : (
        <Card className="overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>{t('cm.pages_ModuleReport.otellere_gore_modul_durumu')}</span>
              <span className="text-xs text-slate-500" data-testid="row-count">
                {t('cm.pages_ModuleReport.toplam')} {filteredRows.length} / {rows.length} otel
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {filteredRows.length === 0 ? (
              <div className="p-10 text-center text-slate-500 text-sm">
                <BarChart3 className="w-10 h-10 mx-auto text-slate-300 mb-2" aria-hidden="true" />
                <p className="font-medium text-slate-600">{t('cm.pages_ModuleReport.eslesen_otel_yok')}</p>
                <p className="text-xs text-slate-400 mt-1">{t('cm.pages_ModuleReport.filtreleri_degistirerek_tekrar_deneyin')}</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs border-t">
                  <thead className="bg-slate-50 border-b sticky top-0 z-10">
                    <tr className="text-left whitespace-nowrap">
                      <th className="px-3 py-2 font-semibold text-slate-700">Otel</th>
                      <th className="px-3 py-2 font-semibold text-slate-700">Lokasyon</th>
                      <th className="px-3 py-2 font-semibold text-slate-700">Plan</th>
                      {COLUMNS.map((c) => (
                        <th key={c.key} className="px-3 py-2 font-semibold text-slate-700 text-center">{c.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((r) => {
                      const tier = (r.subscription_tier || 'basic').toLowerCase();
                      const meta = TIER_META[tier] || TIER_META.basic;
                      return (
                        <tr key={r.tenant_id || r.property_name} className="border-b hover:bg-slate-50/60">
                          <td className="px-3 py-2">
                            <div className="flex flex-col">
                              <span className="font-medium text-slate-800">{r.property_name || 'Otel'}</span>
                              {r.tenant_id && (
                                <span className="text-[10px] text-slate-400 font-mono">ID: {r.tenant_id}</span>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-2 text-slate-600">{r.location || '—'}</td>
                          <td className="px-3 py-2">
                            <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                          </td>
                          {COLUMNS.map((c) => (
                            <td key={c.key} className="px-3 py-2 text-center">
                              <BoolCell value={r[c.key]} />
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <CreateTenantModal
        open={showCreateModal}
        onOpenChange={setShowCreateModal}
        onSuccess={() => { toast.success('Yeni otel oluşturuldu'); loadReport(); }}
      />
    </div>
  );
};

export default ModuleReport;
