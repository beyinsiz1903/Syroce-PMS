import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import {
  Download, FileText, BarChart3, Loader2, RefreshCw,
  Calendar, Filter, CheckCircle2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const hdrs = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });
const get = async (p) => (await fetch(`${API}${p}`, { headers: hdrs() })).json();
const post = async (p, b) => (await fetch(`${API}${p}`, { method: 'POST', headers: hdrs(), body: JSON.stringify(b) })).json();

const REPORT_ICONS = {
  revenue_ml_outputs: BarChart3,
  operational_ai_forecasts: BarChart3,
  guest_intelligence_summary: BarChart3,
  messaging_delivery_performance: BarChart3,
  autopilot_decisions: BarChart3,
  audit_summary: FileText,
  property_comparison: BarChart3,
  management_summary: FileText,
};

export default function AnalyticsExportDashboard() {
  const { t } = useTranslation();
  const [reports, setReports] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState({});
  const [generatedData, setGeneratedData] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [reps, hist] = await Promise.all([
      get('/api/reports/export/available'),
      get('/api/reports/export/history'),
    ]);
    setReports(reps.reports || []);
    setHistory(hist.history || []);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const generate = async (reportType, format = 'csv') => {
    setGenerating(p => ({ ...p, [reportType]: true }));
    const result = await post('/api/reports/export/generate', { report_type: reportType, export_format: format });
    setGenerating(p => ({ ...p, [reportType]: false }));
    if (result.success) {
      setGeneratedData(result);
      load();
    }
  };

  const downloadCSV = (data) => {
    if (!data?.headers || !data?.rows) return;
    const csvContent = [data.headers.join(','), ...data.rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${data.report_type || 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div data-testid="analytics-export-dashboard" className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("techDashboards.analyticsExport")}</h1>
          <p className="text-sm text-muted-foreground">Gelir, operasyon, misafir ve mesajlaşma raporlarını dışa aktarın</p>
        </div>
        <Button data-testid="refresh-exports" variant="outline" size="sm" onClick={load}><RefreshCw className="h-4 w-4 mr-1" /> Yenile</Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {reports.map(r => {
          const Icon = REPORT_ICONS[r.type] || FileText;
          return (
            <Card key={r.type} data-testid={`report-card-${r.type}`}>
              <CardContent className="py-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                    <Icon className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="font-medium text-sm">{r.label}</p>
                    <p className="text-xs text-muted-foreground">{r.type}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    data-testid={`export-csv-${r.type}`}
                    size="sm" className="flex-1"
                    disabled={generating[r.type]}
                    onClick={() => generate(r.type, 'csv')}
                  >
                    {generating[r.type] ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
                    CSV
                  </Button>
                  <Button
                    data-testid={`export-json-${r.type}`}
                    size="sm" variant="outline"
                    disabled={generating[r.type]}
                    onClick={() => generate(r.type, 'json')}
                  >
                    JSON
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {generatedData && (
        <Card className="border-emerald-500/30">
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center">
              <CardTitle className="text-base flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" /> Rapor Hazır
              </CardTitle>
              <Button size="sm" onClick={() => downloadCSV(generatedData)}><Download className="h-4 w-4 mr-1" /> İndir</Button>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-2">{generatedData.report_type} · {generatedData.row_count} satır</p>
            {generatedData.headers && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs border">
                  <thead><tr className="bg-muted">
                    {generatedData.headers.map((h, i) => <th key={i} className="p-2 text-left border-b">{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {(generatedData.rows || []).slice(0, 10).map((row, ri) => (
                      <tr key={ri} className="border-b">
                        {row.map((cell, ci) => <td key={ci} className="p-2">{cell}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle className="text-base">Export Geçmişi</CardTitle></CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">Henüz export yok</p>
          ) : (
            <div className="space-y-2">
              {history.map(h => (
                <div key={h.id} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium">{h.report_type}</p>
                    <p className="text-xs text-muted-foreground">{new Date(h.created_at).toLocaleString('tr-TR')} · {h.export_format} · {h.row_count || 0} satır</p>
                  </div>
                  <Badge variant={h.status === 'completed' ? 'default' : 'destructive'}>{h.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
