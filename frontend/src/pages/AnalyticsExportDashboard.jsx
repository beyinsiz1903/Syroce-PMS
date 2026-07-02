import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Download, FileText, BarChart3, Loader2, RefreshCw, CheckCircle2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
const hdrs = () => ({
  'Content-Type': 'application/json'
});
async function safeFetch(path, init) {
  const res = await fetch(path, {
    ...(init || {}),
    headers: {
      ...hdrs(),
      ...(init?.headers || {})
    },
    credentials: "include"
  });
  const ctype = res.headers.get('content-type') || '';
  let body = null;
  if (ctype.includes('application/json')) {
    try {
      body = await res.json();
    } catch {
      body = null;
    }
  } else {
    try {
      body = await res.text();
    } catch {
      body = null;
    }
  }
  if (!res.ok) {
    const detail = body && typeof body === 'object' && body.detail || `HTTP ${res.status}`;
    const err = new Error(detail);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}
const REPORT_ICONS = {
  revenue_ml_outputs: BarChart3,
  operational_ai_forecasts: BarChart3,
  guest_intelligence_summary: BarChart3,
  messaging_delivery_performance: BarChart3,
  autopilot_decisions: BarChart3,
  audit_summary: FileText,
  property_comparison: BarChart3,
  management_summary: FileText
};

// Bug #6: CSV formula injection + delimiter/newline kaçışı.
// RFC 4180 + Excel/Sheets formula koruması (=, +, -, @, TAB, CR'le başlayan
// hücreleri tek tırnakla etkisizleştir; ardından çift tırnak içine al ve
// içerideki çift tırnakları "" olarak çiftle).
const CSV_FORMULA_LEAD = /^[=+\-@\t\r]/;
function csvEscape(value) {
  if (value === null || value === undefined) return '';
  let s = typeof value === 'string' ? value : String(value);
  if (CSV_FORMULA_LEAD.test(s)) s = `'${s}`;
  // Her hücreyi koruyucu olarak tırnak içine al → virgül/yeni satır güvenli.
  return `"${s.replace(/"/g, '""')}"`;
}
function buildCsv(headers, rows) {
  const head = (headers || []).map(csvEscape).join(',');
  const body = (rows || []).map(r => (Array.isArray(r) ? r : []).map(csvEscape).join(',')).join('\n');
  // Excel'in UTF-8 algılaması için BOM ekle.
  return '\uFEFF' + head + '\n' + body;
}
export default function AnalyticsExportDashboard() {
  const {
    t
  } = useTranslation();
  const [reports, setReports] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [generating, setGenerating] = useState({});
  const [generatedData, setGeneratedData] = useState(null);
  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [reps, hist] = await Promise.all([safeFetch('/api/reports/export/available'), safeFetch('/api/reports/export/history')]);
      setReports(reps && reps.reports || []);
      setHistory(hist && hist.history || []);
    } catch (e) {
      const msg = e.status === 401 ? 'Oturum süresi doldu. Lütfen tekrar giriş yapın.' : e.status === 403 ? 'Yetki yok: Rapor dışa aktarımı için izniniz yok.' : e.status === 404 ? 'Rapor servisi bulunamadı.' : `Raporlar yüklenemedi: ${e.message}`;
      setLoadError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const generate = async (reportType, format = 'csv') => {
    setGenerating(p => ({
      ...p,
      [reportType]: true
    }));
    try {
      const result = await safeFetch('/api/reports/export/generate', {
        method: 'POST',
        body: JSON.stringify({
          report_type: reportType,
          export_format: format
        })
      });
      if (result && (result.success || result.headers || result.rows)) {
        setGeneratedData(result);
        toast.success('Rapor hazır.');
        load();
      } else {
        toast.warning('Rapor oluşturuldu fakat içerik boş döndü.');
      }
    } catch (e) {
      const msg = e.status === 403 ? 'Bu raporu üretme yetkiniz yok.' : e.status === 404 ? 'Rapor tipi bulunamadı.' : `Rapor üretilemedi: ${e.message}`;
      toast.error(msg);
    } finally {
      // Bug #5: Spinner sonsuz kalmasın diye finally ile her durumda kapatılır.
      setGenerating(p => ({
        ...p,
        [reportType]: false
      }));
    }
  };
  const downloadCSV = data => {
    if (!data?.headers || !data?.rows) {
      toast.warning('İndirilecek veri yok.');
      return;
    }
    try {
      const csv = buildCsv(data.headers, data.rows);
      const blob = new Blob([csv], {
        type: 'text/csv;charset=utf-8;'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${data.report_type || 'export'}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(`CSV oluşturulamadı: ${e.message}`);
    }
  };
  if (loading) {
    return <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>;
  }
  if (loadError) {
    return <Card data-testid="analytics-export-error">
        <CardContent className="py-12 text-center space-y-3">
          <AlertTriangle className="h-10 w-10 text-amber-500 mx-auto" />
          <p className="text-sm text-slate-700">{loadError}</p>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4 mr-1.5" /> Yeniden Dene
          </Button>
        </CardContent>
      </Card>;
  }
  return <div data-testid="analytics-export-dashboard" className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-slate-900">{t('techDashboards.analyticsExport')}</h2>
          <p className="text-sm text-slate-500">Gelir, operasyon, misafir ve mesajlaşma raporlarını dışa aktarın.</p>
        </div>
        <Button data-testid="refresh-exports" variant="outline" size="sm" onClick={load}>
          <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {reports.map(r => {
        const Icon = REPORT_ICONS[r.type] || FileText;
        return <Card key={r.type} data-testid={`report-card-${r.type}`}>
              <CardContent className="py-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-10 w-10 rounded-lg bg-sky-100 flex items-center justify-center">
                    <Icon className="h-5 w-5 text-sky-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium text-sm text-slate-900 truncate">{r.label}</p>
                    <p className="text-xs text-slate-500 truncate">{r.type}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button data-testid={`export-csv-${r.type}`} size="sm" className="flex-1" disabled={!!generating[r.type]} onClick={() => generate(r.type, 'csv')}>
                    {generating[r.type] ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
                    CSV
                  </Button>
                  <Button data-testid={`export-json-${r.type}`} size="sm" variant="outline" disabled={!!generating[r.type]} onClick={() => generate(r.type, 'json')}>
                    JSON
                  </Button>
                </div>
              </CardContent>
            </Card>;
      })}
        {reports.length === 0 && <Card><CardContent className="py-8 text-center text-sm text-slate-500">
            Tanımlı rapor bulunamadı.
          </CardContent></Card>}
      </div>

      {generatedData && <Card className="border-emerald-500/30">
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center">
              <CardTitle className="text-base flex items-center gap-2 text-slate-900">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" /> Rapor Hazır
              </CardTitle>
              <Button size="sm" onClick={() => downloadCSV(generatedData)}>
                <Download className="h-4 w-4 mr-1" /> İndir
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-500 mb-2">
              {generatedData.report_type} · {generatedData.row_count ?? (generatedData.rows?.length || 0)} satır
            </p>
            {generatedData.headers && <div className="overflow-x-auto">
                <table className="w-full text-xs border">
                  <thead>
                    <tr className="bg-slate-50">
                      {generatedData.headers.map((h, i) => <th key={h.id || i} className="p-2 text-left border-b text-slate-700">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {(generatedData.rows || []).slice(0, 10).map((row, ri) => <tr key={ri} className="border-b">
                        {(Array.isArray(row) ? row : []).map((cell, ci) => <td key={ci} className="p-2">{cell == null ? '' : String(cell)}</td>)}
                      </tr>)}
                  </tbody>
                </table>
              </div>}
          </CardContent>
        </Card>}

      <Card>
        <CardHeader><CardTitle className="text-base text-slate-900">Dışa Aktarma Geçmişi</CardTitle></CardHeader>
        <CardContent>
          {history.length === 0 ? <p className="text-sm text-slate-500 text-center py-4">Henüz dışa aktarma yok.</p> : <div className="space-y-2">
              {history.map(h => <div key={h.id} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{h.report_type}</p>
                    <p className="text-xs text-slate-500">
                      {new Date(h.created_at).toLocaleString('tr-TR')} · {h.export_format} · {h.row_count || 0} satır
                    </p>
                  </div>
                  <Badge variant={h.status === 'completed' ? 'default' : 'destructive'}>{h.status}</Badge>
                </div>)}
            </div>}
        </CardContent>
      </Card>
    </div>;
}