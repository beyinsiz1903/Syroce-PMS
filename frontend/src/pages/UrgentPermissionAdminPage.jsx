/**
 * Task #28 — Acil Mesaj İzni Yönetimi
 *
 * ADMIN için tenant kullanıcılarını listeler. Her satırda
 * "Acil mesaj gönderme" izni için bir toggle. Optimistic update;
 * backend reddederse durum geri alınır.
 *
 * Endpoint'ler (axios.defaults.baseURL `/api`):
 *   GET   /admin/tenant-users
 *   PATCH /admin/users/{user_id}/granted-permissions  body {permissions}
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import Layout from "../components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { useToast } from "../hooks/use-toast";
import { AlertTriangle, BellRing, RefreshCw, Search, ShieldCheck, Loader2 } from "lucide-react";

const ROLE_LABELS = {
  super_admin: "Süper Admin",
  admin: "Yönetici",
  manager: "Müdür",
  supervisor: "Süpervizör",
  front_desk: "Resepsiyon",
  housekeeping: "Kat Hizmetleri",
  finance: "Finans",
  revenue: "Gelir",
  sales: "Satış",
};

function roleLabel(role) {
  return ROLE_LABELS[role] || role || "—";
}

function MetricNumber({ label, value, tone = "default" }) {
  const toneCls = {
    default: "text-gray-900",
    good: "text-emerald-700",
    bad: "text-rose-700",
    info: "text-indigo-700",
    muted: "text-gray-600",
  }[tone] || "text-gray-900";
  return (
    <div className="flex flex-col">
      <span className="text-xs uppercase tracking-wide text-gray-500">{label}</span>
      <span className={`text-2xl font-semibold tabular-nums ${toneCls}`}>{value}</span>
    </div>
  );
}

export default function UrgentPermissionAdminPage() {
  const { toast } = useToast();
  const [users, setUsers] = useState([]);
  const [grantable, setGrantable] = useState(["send_urgent_message"]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  // user_id → bool (backend yazımı sürerken).
  const [savingMap, setSavingMap] = useState({});
  // Task #32: Push gönderim metrikleri.
  const [metrics, setMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(true);

  const loadMetrics = useCallback(async () => {
    setMetricsLoading(true);
    try {
      const res = await axios.get("/admin/web-push/metrics", {
        params: { days: 30 },
      });
      setMetrics(res.data || null);
    } catch (err) {
      // Sessiz: panel kullanılamaz duruma düşmesin, ana liste çalışsın.
      // eslint-disable-next-line no-console
      console.warn("web-push metrics fetch failed", err?.message);
      setMetrics(null);
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get("/admin/tenant-users");
      setUsers(res.data?.users || []);
      if (Array.isArray(res.data?.grantable) && res.data.grantable.length) {
        setGrantable(res.data.grantable);
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || "Liste alınamadı.";
      toast({ title: "Hata", description: msg, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const f = filter.trim().toLowerCase();
    if (!f) return users;
    return users.filter((u) => {
      return (
        (u.name || "").toLowerCase().includes(f)
        || (u.email || "").toLowerCase().includes(f)
        || (u.username || "").toLowerCase().includes(f)
      );
    });
  }, [users, filter]);

  const toggleUrgent = useCallback(async (user) => {
    const has = (user.granted_permissions || []).includes("send_urgent_message");
    const next = has
      ? (user.granted_permissions || []).filter((p) => p !== "send_urgent_message")
      : Array.from(new Set([...(user.granted_permissions || []), "send_urgent_message"]));

    // Optimistic.
    setUsers((prev) => prev.map((u) =>
      u.id === user.id ? { ...u, granted_permissions: next } : u,
    ));
    setSavingMap((m) => ({ ...m, [user.id]: true }));

    try {
      const res = await axios.patch(
        `/admin/users/${user.id}/granted-permissions`,
        { permissions: next },
      );
      const confirmed = res?.data?.permissions ?? next;
      setUsers((prev) => prev.map((u) =>
        u.id === user.id ? { ...u, granted_permissions: confirmed } : u,
      ));
      toast({
        title: has ? "İzin kaldırıldı" : "İzin verildi",
        description: `${user.name || user.email} — Acil mesaj`,
      });
    } catch (err) {
      // Geri al.
      setUsers((prev) => prev.map((u) =>
        u.id === user.id
          ? { ...u, granted_permissions: user.granted_permissions || [] }
          : u,
      ));
      const msg = err?.response?.data?.detail || err?.message || "İzin güncellenemedi.";
      toast({ title: "Hata", description: msg, variant: "destructive" });
    } finally {
      setSavingMap((m) => {
        const cp = { ...m };
        delete cp[user.id];
        return cp;
      });
    }
  }, [toast]);

  return (
    <Layout currentModule="urgent-permission-admin">
      <div data-testid="urgent-permission-admin-page" className="min-h-screen bg-gray-50">
        <div className="max-w-5xl mx-auto p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-indigo-600" />
              <h1 className="text-xl font-bold text-gray-900">Acil Mesaj İzni Yönetimi</h1>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { load(); loadMetrics(); }}
              disabled={loading}
            >
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                       : <RefreshCw className="w-4 h-4 mr-2" />}
              Yenile
            </Button>
          </div>

          {/* Task #32: Push gönderim sayaçları */}
          <Card data-testid="urgent-permission-metrics-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <BellRing className="w-4 h-4 text-indigo-600" />
                Acil Mesaj — Push Gönderim İstatistikleri
              </CardTitle>
            </CardHeader>
            <CardContent>
              {metricsLoading ? (
                <div className="py-3 text-sm text-gray-500">
                  <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                  Yükleniyor...
                </div>
              ) : !metrics ? (
                <div className="py-3 text-sm text-gray-500">
                  İstatistik alınamadı.
                </div>
              ) : (metrics.totals?.attempted || 0) === 0 ? (
                <div className="py-3 text-sm text-gray-500">
                  Son {metrics.range_days} günde acil push bildirimi
                  gönderilmemiş.
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                      Bugün
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <MetricNumber label="Denenen" value={metrics.today?.attempted || 0} tone="info" />
                      <MetricNumber label="Gönderilen" value={metrics.today?.sent || 0} tone="good" />
                      <MetricNumber label="Başarısız" value={metrics.today?.failed || 0} tone="bad" />
                      <MetricNumber label="Anlık temizlenen" value={metrics.today?.pruned || 0} tone="muted" />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                      Son {metrics.range_days} gün
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <MetricNumber label="Denenen" value={metrics.totals?.attempted || 0} tone="info" />
                      <MetricNumber label="Gönderilen" value={metrics.totals?.sent || 0} tone="good" />
                      <MetricNumber label="Başarısız" value={metrics.totals?.failed || 0} tone="bad" />
                      <MetricNumber label="Anlık temizlenen" value={metrics.totals?.pruned || 0} tone="muted" />
                    </div>
                  </div>
                  <div className="text-[11px] text-gray-500 space-y-1">
                    <div>
                      "Anlık temizlenen": gönderim sırasında geçersiz bulunup
                      silinen abonelik sayısıdır.
                    </div>
                    <div>
                      Sistem geneli otomatik temizlik (tüm tenant'lar) —
                      bugün: <span className="font-medium tabular-nums">{metrics.system_scheduled_pruned_today || 0}</span>,
                      son {metrics.range_days} gün: <span className="font-medium tabular-nums">{metrics.system_scheduled_pruned || 0}</span>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="py-3 text-sm text-amber-900 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                Acil mesaj kanalı alıcıların ekranında alarm tetikler. Bu izni
                yalnızca güvendiğiniz operasyon kullanıcılarına verin. Yöneticiler
                ve süpervizörler bu izne zaten roller gereği sahiptir.
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Kullanıcılar ({filtered.length})</CardTitle>
              <div className="relative mt-2">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input
                  data-testid="urgent-permission-filter"
                  placeholder="İsim, e-posta veya kullanıcı adı..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="pl-9"
                />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="py-10 text-center text-sm text-gray-500">
                  <Loader2 className="w-5 h-5 animate-spin inline mr-2" />
                  Yükleniyor...
                </div>
              ) : filtered.length === 0 ? (
                <div className="py-10 text-center text-sm text-gray-500">
                  Kayıt bulunamadı.
                </div>
              ) : (
                <div className="divide-y">
                  {filtered.map((u) => {
                    const has = (u.granted_permissions || []).includes("send_urgent_message");
                    const saving = !!savingMap[u.id];
                    return (
                      <div
                        key={u.id}
                        data-testid={`urgent-permission-row-${u.id}`}
                        className="flex items-center gap-3 px-4 py-3"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {u.name || u.email || u.username}
                          </div>
                          <div className="text-xs text-gray-500 truncate">
                            {u.email}
                            <span className="ml-2 inline-block px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                              {roleLabel(u.role)}
                            </span>
                          </div>
                        </div>
                        <Button
                          data-testid={`urgent-permission-toggle-${u.id}`}
                          variant={has ? "default" : "outline"}
                          size="sm"
                          disabled={saving}
                          onClick={() => toggleUrgent(u)}
                        >
                          {saving ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : has ? (
                            "İzin Var (kaldır)"
                          ) : (
                            "İzin Ver"
                          )}
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {grantable.length > 1 && (
            <div className="text-xs text-gray-500">
              Atanabilir izinler: {grantable.join(", ")}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
