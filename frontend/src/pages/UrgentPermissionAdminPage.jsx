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

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { PageHeader } from "../components/ui/page-header";
import { useToast } from "../hooks/use-toast";
import { AlertTriangle, BellRing, Check, RefreshCw, Search, ShieldCheck, Loader2 } from "lucide-react";
import { useTranslation } from 'react-i18next';

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

// Sprint A intent paleti — rol rozetleri için.
const ROLE_BADGE = {
  super_admin: "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200",
  admin:       "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200",
  manager:     "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
  supervisor:  "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
  front_desk:  "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  housekeeping:"bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  finance:     "bg-slate-100 text-slate-700 ring-1 ring-slate-300",
  revenue:     "bg-slate-100 text-slate-700 ring-1 ring-slate-300",
  sales:       "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
};

function roleLabel(role) {
  return ROLE_LABELS[role] || role || "—";
}

// Defensive guard: backend her ne kadar decrypt etmek zorunda olsa da
// (KVKK strict mode regression olursa) ciphertext UI'ya sızdırılmasın.
// `aes256gcm:` ve `SYR1:` prefiksleri tespit edilirse boş string dönülür.
function safePii(value) {
  if (typeof value !== "string" || !value) return "";
  if (value.startsWith("aes256gcm:") || value.startsWith("SYR1:")) return "";
  return value;
}

function MetricNumber({ label, value, tone = "default" }) {
  const { t } = useTranslation();
  const toneCls = {
    default: "text-slate-900",
    good: "text-emerald-700",
    bad: "text-rose-700",
    info: "text-indigo-700",
    muted: "text-slate-600",
  }[tone] || "text-slate-900";
  return (
    <div className="flex flex-col">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
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
  const [metricsError, setMetricsError] = useState(null);

  const loadMetrics = useCallback(async () => {
    setMetricsLoading(true);
    setMetricsError(null);
    try {
      const res = await axios.get("/admin/web-push/metrics", {
        params: { days: 30 },
      });
      setMetrics(res.data || null);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      const msg = detail
        || (status === 403 ? "Bu istatistikler için yetkiniz yok."
        :  status === 404 ? "Push metrik servisi bu tenant'ta etkin değil."
        :  status ? `İstatistik alınamadı (HTTP ${status}).`
        :  "İstatistik servisine ulaşılamadı.");
      console.warn("web-push metrics fetch failed", err?.message);
      setMetrics(null);
      setMetricsError(msg);
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

  // Defensive normalize: PII ciphertext sızdırma — backend hatalı dönerse
  // bile UI'da `aes256gcm:...` görünmez, "—" gösterilir.
  const safeUsers = useMemo(() => users.map((u) => ({
    ...u,
    name: safePii(u.name),
    email: safePii(u.email),
    username: safePii(u.username),
  })), [users]);

  const filtered = useMemo(() => {
    const f = filter.trim().toLowerCase();
    if (!f) return safeUsers;
    return safeUsers.filter((u) => {
      return (
        (u.name || "").toLowerCase().includes(f)
        || (u.email || "").toLowerCase().includes(f)
        || (u.username || "").toLowerCase().includes(f)
      );
    });
  }, [safeUsers, filter]);

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
    <>
      <div data-testid="urgent-permission-admin-page">
        <div className="max-w-5xl mx-auto px-4 py-4 space-y-4">
          <PageHeader
            icon={ShieldCheck}
            iconClassName="text-indigo-600"
            title={t('cm.pages_UrgentPermissionAdminPage.acil_mesaj_izni_yonetimi')}
            subtitle={t('cm.pages_UrgentPermissionAdminPage.bu_izni_alan_kullanicilar_diger_personel')}
            actions={
              <Button
                variant="outline"
                size="sm"
                onClick={() => { load(); loadMetrics(); }}
                disabled={loading}
              >
                {loading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                         : <RefreshCw className="w-4 h-4 mr-1.5" />}
                {t('cm.pages_UrgentPermissionAdminPage.yenile')}
              </Button>
            }
          />

          {/* Task #32: Push gönderim sayaçları */}
          <Card data-testid="urgent-permission-metrics-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <BellRing className="w-4 h-4 text-indigo-600" />
                {t('cm.pages_UrgentPermissionAdminPage.acil_mesaj_push_gonderim_istatistikleri')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {metricsLoading ? (
                <div className="py-3 text-sm text-slate-500">
                  <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                  {t('cm.pages_UrgentPermissionAdminPage.yukleniyor')}
                </div>
              ) : !metrics ? (
                <div className="py-3 text-sm flex items-center justify-between gap-3">
                  <span className="text-rose-700">
                    {metricsError || "İstatistik alınamadı."}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={loadMetrics}
                  >
                    <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                    Tekrar dene
                  </Button>
                </div>
              ) : (metrics.totals?.attempted || 0) === 0 ? (
                <div className="py-3 text-sm text-slate-500">
                  Son {metrics.range_days} {t('cm.pages_UrgentPermissionAdminPage.gunde_acil_push_bildirimi_gonderilmemis')}
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">
                      {t('cm.pages_UrgentPermissionAdminPage.bugun')}
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <MetricNumber label="Denenen" value={metrics.today?.attempted || 0} tone="info" />
                      <MetricNumber label={t('cm.pages_UrgentPermissionAdminPage.gonderilen')} value={metrics.today?.sent || 0} tone="good" />
                      <MetricNumber label={t('cm.pages_UrgentPermissionAdminPage.basarisiz')} value={metrics.today?.failed || 0} tone="bad" />
                      <MetricNumber label={t('cm.pages_UrgentPermissionAdminPage.anlik_temizlenen')} value={metrics.today?.pruned || 0} tone="muted" />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">
                      Son {metrics.range_days} {t('cm.pages_UrgentPermissionAdminPage.gun')}
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <MetricNumber label="Denenen" value={metrics.totals?.attempted || 0} tone="info" />
                      <MetricNumber label={t('cm.pages_UrgentPermissionAdminPage.gonderilen_8963f')} value={metrics.totals?.sent || 0} tone="good" />
                      <MetricNumber label={t('cm.pages_UrgentPermissionAdminPage.basarisiz_3260d')} value={metrics.totals?.failed || 0} tone="bad" />
                      <MetricNumber label={t('cm.pages_UrgentPermissionAdminPage.anlik_temizlenen_cbf39')} value={metrics.totals?.pruned || 0} tone="muted" />
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500 space-y-1">
                    <div>
                      {t('cm.pages_UrgentPermissionAdminPage.anlik_temizlenen_gonderim_sirasinda_gece')}
                    </div>
                    <div>
                      {t('cm.pages_UrgentPermissionAdminPage.sistem_geneli_otomatik_temizlik_tum_tena')} <span className="font-medium tabular-nums">{metrics.system_scheduled_pruned_today || 0}</span>,
                      son {metrics.range_days} {t('cm.pages_UrgentPermissionAdminPage.gun_dc9ae')} <span className="font-medium tabular-nums">{metrics.system_scheduled_pruned || 0}</span>
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
                {t('cm.pages_UrgentPermissionAdminPage.acil_mesaj_kanali_alicilarin_ekraninda_a')}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{t('cm.pages_UrgentPermissionAdminPage.kullanicilar')}{filtered.length})</CardTitle>
              <div className="relative mt-2">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <Input
                  data-testid="urgent-permission-filter"
                  placeholder={t('cm.pages_UrgentPermissionAdminPage.isim_e_posta_veya_kullanici_adi')}
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="pl-9"
                />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="py-10 text-center text-sm text-slate-500">
                  <Loader2 className="w-5 h-5 animate-spin inline mr-2" />
                  {t('cm.pages_UrgentPermissionAdminPage.yukleniyor_4deb0')}
                </div>
              ) : filtered.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-500">
                  {t('cm.pages_UrgentPermissionAdminPage.kayit_bulunamadi')}
                </div>
              ) : (
                <div className="divide-y">
                  {filtered.map((u) => {
                    const has = (u.granted_permissions || []).includes("send_urgent_message");
                    const saving = !!savingMap[u.id];
                    const displayName = u.name || u.email || u.username || "—";
                    const secondary = u.email || u.username || "";
                    const roleCls = ROLE_BADGE[u.role] || "bg-slate-50 text-slate-700 ring-1 ring-slate-200";
                    return (
                      <div
                        key={u.id}
                        data-testid={`urgent-permission-row-${u.id}`}
                        className="flex items-center gap-3 px-4 py-3"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-sm font-medium text-slate-900 truncate">
                              {displayName}
                            </span>
                            <span
                              className={`shrink-0 inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${roleCls}`}
                            >
                              {roleLabel(u.role)}
                            </span>
                          </div>
                          {secondary && (
                            <div className="text-xs text-slate-500 truncate mt-0.5">
                              {secondary}
                            </div>
                          )}
                        </div>
                        <Button
                          data-testid={`urgent-permission-toggle-${u.id}`}
                          variant={has ? "default" : "outline"}
                          size="sm"
                          disabled={saving}
                          onClick={() => toggleUrgent(u)}
                          title={has ? "İzni kaldır" : "Acil mesaj iznini ver"}
                        >
                          {saving ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : has ? (
                            <><Check className="w-3.5 h-3.5 mr-1.5" />{t('cm.pages_UrgentPermissionAdminPage.izinli')}</>
                          ) : (
                            <>{t('cm.pages_UrgentPermissionAdminPage.izin_ver')}</>
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
            <div className="text-xs text-slate-500">
              Atanabilir izinler: {grantable.join(", ")}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
