import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { Loader2, RefreshCw, History, AlertTriangle, CheckCircle2, ExternalLink } from "lucide-react";

const fmt = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
};

export default function RnlAutoResolveRuns() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get("/admin/db/rnl-auto-resolve-runs", { params: { limit: 20 } });
      setRuns(r.data.runs || []);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      setError(msg);
      toast.error(`Geçmiş yüklenemedi: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const totals = useMemo(() => {
    const t = { resolved: 0, manual: 0, scanned: 0 };
    for (const r of runs) {
      t.resolved += r.resolved_count || 0;
      t.manual += r.manual_required_count || 0;
      t.scanned += r.scanned || 0;
    }
    return t;
  }, [runs]);

  const lastRunHasManual = runs.length > 0 && (runs[0].manual_required_count || 0) > 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <History className="w-7 h-7" /> RNL Otomatik Çözücü — Çalışma Geçmişi
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            Günlük Celery beat görevi (<code>rnl_duplicate_auto_resolve_task</code>) duplikat oda-gece
            kilitlerini otomatik temizler. Son çalışmaların sonuçları burada listelenir.
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
          Yenile
        </Button>
      </div>

      {lastRunHasManual && (
        <Alert variant="destructive">
          <AlertTriangle className="w-4 h-4" />
          <AlertTitle>Manuel müdahale gerekiyor</AlertTitle>
          <AlertDescription>
            Son çalışmada {runs[0].manual_required_count} grup otomatik çözülemedi.{" "}
            <Link to="/admin/rnl-duplicates" className="underline font-medium inline-flex items-center gap-1">
              Çözüm panelini aç <ExternalLink className="w-3 h-3" />
            </Link>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <SummaryCard label="Toplam Çalışma" value={runs.length} />
        <SummaryCard label="Toplam Taranan" value={totals.scanned} />
        <SummaryCard label="Toplam Çözülen" value={totals.resolved} intent="success" />
        <SummaryCard label="Toplam Manuel Gereken" value={totals.manual} intent={totals.manual > 0 ? "warn" : "neutral"} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Son {runs.length || "—"} Çalışma</CardTitle>
          <CardDescription>En yeni en üstte. Günlük 03:30 UTC.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor…
            </div>
          ) : error ? (
            <div className="text-red-600 text-sm">{error}</div>
          ) : runs.length === 0 ? (
            <div className="text-gray-500 text-sm py-8 text-center">
              Henüz çalışma kaydı yok. İlk beat tetiklemesinden sonra burada listelenecek.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="text-left py-2 px-2">Başlangıç</th>
                    <th className="text-left py-2 px-2">Bitiş</th>
                    <th className="text-right py-2 px-2">Taranan</th>
                    <th className="text-right py-2 px-2">Çözülen</th>
                    <th className="text-right py-2 px-2">Atlanan</th>
                    <th className="text-right py-2 px-2">Manuel Gereken</th>
                    <th className="text-left py-2 px-2">İndeks</th>
                    <th className="text-left py-2 px-2">Aksiyon</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r, i) => {
                    const manual = r.manual_required_count || 0;
                    const idx = r.index_rebuild || {};
                    return (
                      <tr key={`${r.started_at}-${i}`} className="border-b last:border-0">
                        <td className="py-2 px-2 whitespace-nowrap">{fmt(r.started_at)}</td>
                        <td className="py-2 px-2 whitespace-nowrap">{fmt(r.finished_at)}</td>
                        <td className="py-2 px-2 text-right">{r.scanned ?? 0}</td>
                        <td className="py-2 px-2 text-right font-medium text-emerald-700">{r.resolved_count ?? 0}</td>
                        <td className="py-2 px-2 text-right">{r.skipped_count ?? 0}</td>
                        <td className="py-2 px-2 text-right">
                          {manual > 0 ? (
                            <Badge variant="destructive">{manual}</Badge>
                          ) : (
                            <span className="text-gray-400">0</span>
                          )}
                        </td>
                        <td className="py-2 px-2">
                          {idx.ran ? (
                            <span className="inline-flex items-center gap-1 text-emerald-700">
                              <CheckCircle2 className="w-3.5 h-3.5" /> yeniden kuruldu
                            </span>
                          ) : idx.error ? (
                            <span className="text-red-600" title={idx.error}>hata</span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="py-2 px-2">
                          {manual > 0 ? (
                            <Link to="/admin/rnl-duplicates">
                              <Button size="sm" variant="outline">
                                Çöz <ExternalLink className="w-3 h-3 ml-1" />
                              </Button>
                            </Link>
                          ) : (
                            <span className="text-gray-400 text-xs">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryCard({ label, value, intent = "neutral" }) {
  const tone =
    intent === "success" ? "text-emerald-700"
    : intent === "warn" ? "text-amber-700"
    : "text-slate-900";
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-xs uppercase text-gray-500">{label}</div>
        <div className={`text-3xl font-bold mt-1 ${tone}`}>{value}</div>
      </CardContent>
    </Card>
  );
}
