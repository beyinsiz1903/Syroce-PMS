import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ShieldCheck, AlertTriangle, CheckCircle2, Cloud, MinusCircle,
  Download, FileText, RefreshCw, Lock,
} from 'lucide-react';

const STATUS_META = {
  met: { label: 'Karşılandı', color: 'bg-emerald-100 text-emerald-800 border-emerald-200', icon: CheckCircle2 },
  partial: { label: 'Kısmen', color: 'bg-amber-100 text-amber-800 border-amber-200', icon: AlertTriangle },
  shared: { label: 'Paylaşılan', color: 'bg-sky-100 text-sky-800 border-sky-200', icon: Cloud },
  not_applicable: { label: 'Geçersiz', color: 'bg-gray-100 text-gray-700 border-gray-200', icon: MinusCircle },
};

const StatusBadge = ({ status }) => {
  const meta = STATUS_META[status] || STATUS_META.not_applicable;
  const Icon = meta.icon;
  return (
    <Badge className={`${meta.color} border`}>
      <Icon className="w-3 h-3 mr-1" /> {meta.label}
    </Badge>
  );
};

const PCIComplianceDashboard = ({ user, tenant, onLogout }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get('/compliance/pci/controls');
      setData(r.data);
    } catch (e) {
      const msg = e.response?.status === 403
        ? 'Bu sayfayı görmek için yönetici yetkisine ihtiyacınız var.'
        : (e.response?.data?.detail || 'Rapor yüklenemedi.');
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const download = async (kind) => {
    setDownloading(kind);
    try {
      const path = kind === 'csv' ? '/compliance/pci/report.csv' : '/compliance/pci/attestation';
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

  if (loading) {
    return (
      <div className="p-8 text-center text-gray-500">
        <RefreshCw className="w-6 h-6 animate-spin inline mr-2" /> Yükleniyor…
      </div>
    );
  }
  if (!data) {
    return (
      <div className="p-8 text-center text-gray-500">
        Rapor mevcut değil.
        <div className="mt-2"><Button onClick={load}>Tekrar Dene</Button></div>
      </div>
    );
  }

  const { summary, controls } = data;

  return (
    <>
    <div className="max-w-6xl mx-auto p-4 space-y-4">
      <div className="flex items-start justify-end flex-wrap gap-3">
        <div className="hidden"></div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
          <Button variant="outline" onClick={() => download('csv')} disabled={downloading === 'csv'}>
            <Download className="w-4 h-4 mr-2" /> CSV
          </Button>
          <Button onClick={() => download('json')} disabled={downloading === 'json'}>
            <FileText className="w-4 h-4 mr-2" /> Beyan Paketi (JSON)
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryCard
          title="Uygulama Skoru"
          value={`%${summary.implementation_score_pct}`}
          icon={ShieldCheck}
          accent="indigo"
          subtitle={`${summary.fully_met}/${summary.fully_met + summary.needs_attention} kontrol`}
        />
        <SummaryCard
          title="Tam Karşılanan"
          value={summary.counts.met}
          icon={CheckCircle2}
          accent="emerald"
        />
        <SummaryCard
          title="Eylem Gerekli"
          value={summary.counts.partial}
          icon={AlertTriangle}
          accent="amber"
        />
        <SummaryCard
          title="Paylaşılan"
          value={summary.counts.shared}
          icon={Cloud}
          accent="sky"
        />
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 flex gap-3 text-sm">
        <Lock className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
        <div className="text-amber-900">
          <strong>Bilgilendirme:</strong> Bu panel teknik kontrollerin durumunu gösteren
          bir öz-değerlendirmedir. Resmi PCI-DSS sertifikası için yetkili bir QSA
          (Qualified Security Assessor) değerlendirmesi gereklidir. Kart verisi
          işlemediğiniz akışlar için SAQ-A form'u yeterli olabilir.
        </div>
      </div>

      {/* Requirements list */}
      <div className="space-y-3">
        {controls.map((c) => (
          <Card key={c.req_id} className="border-l-4" style={{ borderLeftColor: borderColor(c.status) }}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <CardTitle className="text-base">
                    <span className="text-gray-400 font-mono mr-2">Req {c.req_id}</span>
                    {c.title}
                  </CardTitle>
                </div>
                <StatusBadge status={c.status} />
              </div>
            </CardHeader>
            <CardContent className="pt-0 space-y-3">
              <div>
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  Uygulanan Kontroller
                </div>
                <ul className="list-disc list-inside text-sm text-gray-700 space-y-0.5">
                  {c.evidence.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </div>
              {c.recommendations.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-1">
                    Öneriler
                  </div>
                  <ul className="list-disc list-inside text-sm text-amber-800 space-y-0.5">
                    {c.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
    </>
  );
};

const SummaryCard = ({ title, value, icon: Icon, accent, subtitle }) => {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    sky: 'bg-sky-50 text-sky-600',
  };
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg ${colors[accent]} flex items-center justify-center shrink-0`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <div className="text-xs text-gray-500 truncate">{title}</div>
          <div className="text-2xl font-bold text-gray-900 leading-tight">{value}</div>
          {subtitle && <div className="text-xs text-gray-500">{subtitle}</div>}
        </div>
      </CardContent>
    </Card>
  );
};

const borderColor = (status) => ({
  met: '#10b981',
  partial: '#f59e0b',
  shared: '#0ea5e9',
  not_applicable: '#9ca3af',
}[status] || '#9ca3af');

export default PCIComplianceDashboard;
