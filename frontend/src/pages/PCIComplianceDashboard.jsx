import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  ShieldCheck, AlertTriangle, CheckCircle2, Cloud, MinusCircle,
  Download, FileText, RefreshCw, Lock, ShieldAlert,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const STATUS_META = {
  met:            { label: 'Karşılandı',  intent: 'success', icon: CheckCircle2,  border: 'border-l-emerald-500' },
  partial:        { label: 'Kısmen',      intent: 'warning', icon: AlertTriangle, border: 'border-l-amber-500' },
  shared:         { label: 'Paylaşılan',  intent: 'info',    icon: Cloud,         border: 'border-l-sky-500' },
  not_applicable: { label: 'Geçersiz',    intent: 'neutral', icon: MinusCircle,   border: 'border-l-slate-400' },
};

const ControlStatus = ({ status }) => {
  const { t } = useTranslation();
  const meta = STATUS_META[status] || STATUS_META.not_applicable;
  const Icon = meta.icon;
  return (
    <StatusBadge intent={meta.intent} icon={Icon}>{meta.label}</StatusBadge>
  );
};

export default function PCIComplianceDashboard() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(null);
  const [anonymize, setAnonymize] = useState(true);  // KVKK varsayılan: anonim

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const r = await axios.get('/compliance/pci/controls', {
        params: refresh ? { refresh: 1 } : {},
      });
      setData(r.data);
    } catch (e) {
      const msg = e.response?.status === 403
        ? 'Bu sayfayı görmek için yönetici yetkisine ihtiyacınız var.'
        : (e.response?.data?.detail || 'Rapor yüklenemedi.');
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(false); }, [load]);

  const download = async (kind) => {
    setDownloading(kind);
    try {
      const path = kind === 'csv'
        ? '/compliance/pci/report.csv'
        : `/compliance/pci/attestation${anonymize ? '?anonymize=true' : ''}`;
      const r = await axios.get(path, { responseType: 'blob' });
      const blob = new Blob([r.data], { type: r.headers['content-type'] });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const cd = r.headers['content-disposition'] || '';
      const match = /filename="([^"]+)"/.exec(cd);
      a.download = match ? match[1] : (kind === 'csv' ? 'pci_report.csv' : 'pci_attestation.json');
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('İndirilemedi.');
    } finally {
      setDownloading(null);
    }
  };

  const summary = data?.summary;
  const controls = data?.controls || [];
  const totalReq = summary?.total_requirements ?? 12;
  const met = summary?.counts?.met ?? 0;
  const partial = summary?.counts?.partial ?? 0;
  const shared = summary?.counts?.shared ?? 0;
  const notApp = summary?.counts?.not_applicable ?? 0;
  const score = summary?.implementation_score_pct ?? 0;

  // Sprint A skeleton loading
  if (loading && !data) {
    return (
      <div className="max-w-6xl mx-auto p-4 space-y-4">
        <Skeleton className="h-12 w-full max-w-md" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
        <Skeleton className="h-16 w-full" />
        {[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-32 w-full" />)}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-6xl mx-auto p-8 text-center">
        <ShieldAlert className="w-10 h-10 text-rose-500 mx-auto mb-3" />
        <div className="text-slate-700 mb-3">{t('cm.pages_PCIComplianceDashboard.rapor_mevcut_degil')}</div>
        <Button variant="outline" onClick={() => load(true)}>
          <RefreshCw className="w-4 h-4 mr-1.5" /> Tekrar Dene
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-4">
      {/* Sprint A PageHeader */}
      <PageHeader
        icon={ShieldCheck}
        title="PCI-DSS Uyum Paneli"
        subtitle={`${summary?.version || 'PCI-DSS v4.0'} — ${totalReq} gereksinimden ${met}'i tam, ${partial}'i kısmi, ${shared}'i paylaşılan, ${notApp}'i geçersiz`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => load(true)} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> {t('cm.pages_PCIComplianceDashboard.yenile')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('csv')} disabled={downloading === 'csv'}>
              <Download className="w-4 h-4 mr-1.5" /> CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('json')} disabled={downloading === 'json'}>
              <FileText className="w-4 h-4 mr-1.5" /> Beyan Paketi (JSON)
            </Button>
          </div>
        }
      />

      {/* KPI Grid (Sprint A KpiCard, intent paleti) */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard
          icon={ShieldCheck}
          label="Uygulama Skoru"
          value={`%${score}`}
          sub={`${met}/${met + partial} kontrol`}
          intent="info"
        />
        <KpiCard
          icon={CheckCircle2}
          label={t('cm.pages_PCIComplianceDashboard.tam_karsilanan')}
          value={met}
          intent="success"
        />
        <KpiCard
          icon={AlertTriangle}
          label="Eylem Gerekli"
          value={partial}
          intent="warning"
        />
        <KpiCard
          icon={Cloud}
          label={t('cm.pages_PCIComplianceDashboard.paylasilan')}
          value={shared}
          intent="info"
          sub="Cloud / müşteri"
        />
        <KpiCard
          icon={MinusCircle}
          label={t('cm.pages_PCIComplianceDashboard.gecersiz_n_a')}
          value={notApp}
          intent="neutral"
        />
      </div>

      {/* Disclaimer (Sprint A: Card + warning palette) */}
      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="p-3 flex gap-3 text-sm">
          <Lock className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
          <div className="text-amber-900">
            <strong>Bilgilendirme:</strong> {t('cm.pages_PCIComplianceDashboard.bu_panel_teknik_kontrollerin_durumunu_go')}
          </div>
        </CardContent>
      </Card>

      {/* Anonim indirme tercihi (KVKK) */}
      <Card>
        <CardContent className="p-3 flex items-center justify-between gap-3 text-sm flex-wrap">
          <label className="flex items-center gap-2 cursor-pointer text-slate-700">
            <input
              type="checkbox"
              className="w-4 h-4"
              checked={anonymize}
              onChange={(e) => setAnonymize(e.target.checked)}
            />
            <span>{t('cm.pages_PCIComplianceDashboard.json_beyan_paketinde_kisisel_detaylari_e')} <span className="text-slate-500">{t('cm.pages_PCIComplianceDashboard.kvkk_gdpr_onerilen')}</span></span>
          </label>
          <span className="text-xs text-slate-500">{t('cm.pages_PCIComplianceDashboard.json_paketi_imza_anahtari_attestation_si')}</span>
        </CardContent>
      </Card>

      {/* Requirements grid (12 gereksinim — desktop 2 sütun) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {controls.map((c) => {
          const meta = STATUS_META[c.status] || STATUS_META.not_applicable;
          return (
            <Card key={c.req_id} className={`border-l-4 ${meta.border}`}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <CardTitle className="text-base">
                    <span className="text-slate-400 font-mono mr-2">Req {c.req_id}</span>
                    {c.title}
                  </CardTitle>
                  <ControlStatus status={c.status} />
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-3">
                {(c.evidence?.length ?? 0) > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
                      Uygulanan Kontroller
                    </div>
                    <ul className="list-disc list-inside text-sm text-slate-700 space-y-0.5">
                      {c.evidence.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </div>
                )}
                {(c.recommendations?.length ?? 0) > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-1">
                      {t('cm.pages_PCIComplianceDashboard.oneriler')}
                    </div>
                    <ul className="list-disc list-inside text-sm text-amber-800 space-y-0.5">
                      {c.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function VERSION_LABEL(s) {
  return s?.version || 'PCI-DSS v4.0';
}
