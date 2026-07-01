import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { Loader2, RefreshCw, Wallet, AlertTriangle } from "lucide-react";

const fmt = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
};

const money = (minor, currency) => {
  if (minor == null) return "—";
  const v = (Number(minor) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${v} ${currency || ""}`.trim();
};

const KIND_LABEL = {
  vcc_checkin: "Check-in VCC",
  no_show: "No-show cezası",
};

// Cozulmemus is = motorun yetkili `resolved` bayragi (succeeded haric HER durum
// resolved=False yazilir). Durum allowlist'i kullanmiyoruz: motor reconcile /
// requires_action / unrecorded / not_configured / failed / declined / unknown
// gibi durumlari da operator-aksiyonu olarak isaretliyor; tek dogruluk kaynagi
// `resolved !== true` (backend `unresolved_only` filtresi de bununla birebir).
const isUnresolved = (j) => j.resolved !== true;

// Renklendirme: succeeded yesil; para-belirsiz/bekleyen sarí; gercek
// basarisizlik kirmizi (unrecorded = para alindi ama kaydedilemedi -> kritik).
const SUCCESS_STATUSES = new Set(["succeeded", "paid"]);
const WARN_STATUSES = new Set(["reconcile", "requires_action", "not_configured"]);

const statusVariant = (status) => {
  if (SUCCESS_STATUSES.has(status)) return "success";
  if (WARN_STATUSES.has(status)) return "warn";
  return "danger";
};

function StatusBadge({ status }) {
  const s = status || "unknown";
  const tone = statusVariant(s);
  if (tone === "success") {
    return <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">{s}</Badge>;
  }
  if (tone === "warn") {
    return <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">{s}</Badge>;
  }
  return <Badge variant="destructive">{s}</Badge>;
}

export default function AutonomousCollectionJobs() {
  const [runs, setRuns] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [unresolvedOnly, setUnresolvedOnly] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [runsRes, jobsRes] = await Promise.all([
        axios.get("/admin/db/autonomous-collection-runs", { params: { limit: 200 } }),
        axios.get("/admin/db/autonomous-collection-jobs", {
          params: { limit: 200, unresolved_only: unresolvedOnly },
        }),
      ]);
      setRuns(runsRes.data.runs || []);
      setJobs(jobsRes.data.jobs || []);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      setError(msg);
      toast.error(`Veriler yüklenemedi: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [unresolvedOnly]); // eslint-disable-line react-hooks/exhaustive-deps

  const runTotals = useMemo(() => {
    const t = { charged: 0, failed: 0, requiresAction: 0, notConfigured: 0 };
    for (const r of runs) {
      t.charged += r.last_charged || 0;
      t.failed += r.last_failed || 0;
      t.requiresAction += r.last_requires_action || 0;
      t.notConfigured += r.last_not_configured || 0;
    }
    return t;
  }, [runs]);

  const unresolvedCount = useMemo(
    () => jobs.filter(isUnresolved).length,
    [jobs],
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Wallet className="w-7 h-7" /> Otonom Tahsilat — Sonuçlar
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            Günlük otonom tahsilat görevi check-in günü kasa kartlı (VCC) rezervasyonları ve
            no-show cezalarını otomatik tahsil eder. Kiracı bazlı koşu özetleri ve başarısız/bekleyen
            iş kuyruğu burada listelenir. Misafir PII'si gösterilmez.
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
          Yenile
        </Button>
      </div>

      {unresolvedCount > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="w-4 h-4" />
          <AlertTitle>Operatör aksiyonu gerekiyor</AlertTitle>
          <AlertDescription>
            {unresolvedCount} tahsilat işi çözülmemiş durumda (başarısız / reddedildi / ek doğrulama /
            yapılandırılmamış). Aşağıdaki kuyruğu inceleyin.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <SummaryCard label="Toplam Tahsil Edilen (son koşu)" value={runTotals.charged} intent="success" />
        <SummaryCard label="Çözülmemiş İş" value={unresolvedCount} intent={unresolvedCount > 0 ? "warn" : "neutral"} />
        <SummaryCard label="Başarısız (son koşu)" value={runTotals.failed} intent={runTotals.failed > 0 ? "warn" : "neutral"} />
        <SummaryCard label="Yapılandırılmamış (son koşu)" value={runTotals.notConfigured} intent={runTotals.notConfigured > 0 ? "warn" : "neutral"} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Kiracı Bazlı Koşu Özetleri</CardTitle>
          <CardDescription>Her kiracı için son otonom tahsilat koşusu. En yeni en üstte.</CardDescription>
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
              Henüz koşu kaydı yok. İlk dispatch tetiklemesinden sonra burada listelenecek.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="text-left py-2 px-2">Kiracı</th>
                    <th className="text-left py-2 px-2">Son Çalışma</th>
                    <th className="text-left py-2 px-2">Durum</th>
                    <th className="text-right py-2 px-2">Taranan</th>
                    <th className="text-right py-2 px-2">Tahsil</th>
                    <th className="text-right py-2 px-2">Başarısız</th>
                    <th className="text-right py-2 px-2">Aksiyon Gerek</th>
                    <th className="text-right py-2 px-2">Yapılandırılmamış</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r, i) => (
                    <tr key={`${r.tenant_id}-${i}`} className="border-b last:border-0">
                      <td className="py-2 px-2 font-mono text-xs">{r.tenant_id ?? "—"}</td>
                      <td className="py-2 px-2 whitespace-nowrap">{fmt(r.last_auto_run_completed_at || r.last_auto_run)}</td>
                      <td className="py-2 px-2"><StatusBadge status={r.last_auto_run_status} /></td>
                      <td className="py-2 px-2 text-right">{r.last_scanned ?? 0}</td>
                      <td className="py-2 px-2 text-right font-medium text-emerald-700">{r.last_charged ?? 0}</td>
                      <td className="py-2 px-2 text-right">{r.last_failed ?? 0}</td>
                      <td className="py-2 px-2 text-right">{r.last_requires_action ?? 0}</td>
                      <td className="py-2 px-2 text-right">{r.last_not_configured ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Tahsilat İş Kuyruğu</CardTitle>
            <CardDescription>
              (Kiracı, rezervasyon, tür) başına tek satır. Başarısızlıklar fail-closed kuyruğa yazılır.
            </CardDescription>
          </div>
          <Button
            variant={unresolvedOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setUnresolvedOnly((v) => !v)}
          >
            {unresolvedOnly ? "Tümünü Göster" : "Yalnız Çözülmemiş"}
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor…
            </div>
          ) : error ? (
            <div className="text-red-600 text-sm">{error}</div>
          ) : jobs.length === 0 ? (
            <div className="text-gray-500 text-sm py-8 text-center">
              {unresolvedOnly ? "Çözülmemiş iş yok." : "Henüz iş kaydı yok."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="text-left py-2 px-2">Kiracı</th>
                    <th className="text-left py-2 px-2">Rezervasyon</th>
                    <th className="text-left py-2 px-2">Tür</th>
                    <th className="text-right py-2 px-2">Tutar</th>
                    <th className="text-left py-2 px-2">Durum</th>
                    <th className="text-right py-2 px-2">Deneme</th>
                    <th className="text-left py-2 px-2">Hata</th>
                    <th className="text-left py-2 px-2">Güncellenme</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j, i) => (
                    <tr key={`${j.tenant_id}-${j.booking_id}-${j.charge_kind}-${i}`} className="border-b last:border-0">
                      <td className="py-2 px-2 font-mono text-xs">{j.tenant_id ?? "—"}</td>
                      <td className="py-2 px-2 font-mono text-xs">{j.booking_id ?? "—"}</td>
                      <td className="py-2 px-2">{KIND_LABEL[j.charge_kind] || j.charge_kind || "—"}</td>
                      <td className="py-2 px-2 text-right whitespace-nowrap">{money(j.amount_minor, j.currency)}</td>
                      <td className="py-2 px-2"><StatusBadge status={j.status} /></td>
                      <td className="py-2 px-2 text-right">{j.attempts ?? 0}</td>
                      <td className="py-2 px-2 text-xs text-gray-600 max-w-xs truncate" title={j.last_error_message || ""}>
                        {j.last_error_code || (j.last_error_message ? "—" : "")}
                      </td>
                      <td className="py-2 px-2 whitespace-nowrap">{fmt(j.updated_at)}</td>
                    </tr>
                  ))}
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
