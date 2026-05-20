import React, { useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import { Loader2, RefreshCw, AlertTriangle, History, PlayCircle } from "lucide-react";

const recommendationVariant = (rec) => {
  if (rec === "auto_safe" || rec === "auto_safe_all_inactive") return "secondary";
  if (rec === "manual_required") return "destructive";
  return "outline";
};

export default function RnlDuplicates() {
  const [groups, setGroups] = useState([]);
  const [total, setTotal] = useState(0);
  const [autoCount, setAutoCount] = useState(0);
  const [manualCount, setManualCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get("/admin/db/room-night-lock-duplicates", { params: { limit: 200 } });
      setGroups(r.data.groups || []);
      setTotal(r.data.total || 0);
      setAutoCount(r.data.auto_resolvable || 0);
      setManualCount(r.data.manual_required || 0);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const runAutoResolve = async () => {
    if (!window.confirm(
      `Auto-safe gruplar silinecek (manual_required gruplar dokunulmaz). Devam edilsin mi?`
    )) return;
    setRunning(true);
    try {
      const r = await axios.post(
        "/admin/db/room-night-lock-duplicates/resolve?dry_run=false&rebuild_index=true",
        { confirm: true, limit: 200 }
      );
      toast.success(
        `Çözüldü: ${r.data.resolved_count} · Atlandı: ${r.data.skipped_count}`
      );
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Çözüm başarısız");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-start gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <AlertTriangle className="w-7 h-7" /> RNL Duplikat Grupları
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            Duplikat oda-gece kilitleri. Auto-safe gruplar tek tıkla temizlenebilir;
            manual_required gruplar elle adjudikasyon ister.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/admin/rnl-auto-resolve-runs">
            <Button variant="outline">
              <History className="w-4 h-4 mr-2" /> Çalışma Geçmişi
            </Button>
          </Link>
          <Button variant="outline" onClick={load} disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
            Yenile
          </Button>
          <Button onClick={runAutoResolve} disabled={running || autoCount === 0}>
            {running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-2" />}
            Auto-Safe Çöz ({autoCount})
          </Button>
        </div>
      </div>

      {manualCount > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="w-4 h-4" />
          <AlertTitle>{manualCount} grup manuel adjudikasyon bekliyor</AlertTitle>
          <AlertDescription>
            Bu gruplarda birden fazla aktif rezervasyon aynı oda-gece kilidine sahip.
            Her bir grubun hangi rezervasyonun kalacağına süper admin karar vermelidir
            (DB seviyesi düzeltme: rezervasyonu iptal et / oda taşı).
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Toplam {total} grup · Otomatik {autoCount} · Manuel {manualCount}</CardTitle>
          <CardDescription>İlk 200 grup gösterilir.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor…
            </div>
          ) : groups.length === 0 ? (
            <div className="text-gray-500 text-sm py-8 text-center">
              Duplikat grup yok. ✔
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="text-left py-2 px-2">Tenant</th>
                    <th className="text-left py-2 px-2">Oda</th>
                    <th className="text-left py-2 px-2">Gece</th>
                    <th className="text-right py-2 px-2">Kilit Sayısı</th>
                    <th className="text-left py-2 px-2">Öneri</th>
                  </tr>
                </thead>
                <tbody>
                  {groups.map((g, i) => (
                    <tr key={`${g.tenant_id}-${g.room_id}-${g.night_date}-${i}`} className="border-b last:border-0">
                      <td className="py-2 px-2 font-mono text-xs">{g.tenant_id}</td>
                      <td className="py-2 px-2 font-mono text-xs">{g.room_id}</td>
                      <td className="py-2 px-2">{g.night_date}</td>
                      <td className="py-2 px-2 text-right">{g.lock_count ?? g.locks?.length ?? "?"}</td>
                      <td className="py-2 px-2">
                        <Badge variant={recommendationVariant(g.recommendation)}>
                          {g.recommendation}
                        </Badge>
                      </td>
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
