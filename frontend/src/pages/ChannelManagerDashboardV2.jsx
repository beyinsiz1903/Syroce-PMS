import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Activity, AlertTriangle, ArrowRight, CheckCircle, Clock, Cloud,
  ExternalLink, Layers, Loader2, MapPin, Plug, RefreshCw, Shield,
  Signal, Wifi, WifiOff, X, Zap, Eye, ChevronDown, ChevronUp,
  ArrowLeftRight, BarChart3, Users,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const StatusBadge = ({ status }) => {
  const { t } = useTranslation();
  const map = {
    active: { cls: 'bg-emerald-100 text-emerald-800', label: 'Aktif' },
    paused: { cls: 'bg-amber-100 text-amber-800', label: 'Durduruldu' },
    error: { cls: 'bg-red-100 text-red-800', label: 'Hata' },
    draft: { cls: 'bg-slate-100 text-slate-600', label: 'Taslak' },
    disabled: { cls: 'bg-gray-100 text-gray-500', label: 'Devre Disi' },
  };
  const m = map[status] || { cls: 'bg-slate-100 text-slate-600', label: status };
  return <Badge className={`text-xs ${m.cls}`}>{m.label}</Badge>;
};

const ProviderBadge = ({ provider }) => {
  const colors = {
    hotelrunner: 'bg-blue-100 text-blue-700',
    exely: 'bg-indigo-100 text-indigo-700',
    siteminder: 'bg-teal-100 text-teal-700',
  };
  return <Badge variant="outline" className={`text-xs ${colors[provider] || 'bg-slate-100 text-slate-600'}`}>{provider}</Badge>;
};

const KpiCard = ({ icon: Icon, label, value, color, sub }) => (
  <Card className="relative overflow-hidden">
    <CardContent className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-slate-500 font-medium">{label}</p>
          <p className={`text-2xl font-bold mt-1 ${color || 'text-slate-800'}`}>{value}</p>
          {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
        </div>
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${color ? color.replace('text-', 'bg-').replace('800', '100').replace('700', '100').replace('600', '100').replace('500', '100') : 'bg-slate-100'}`}>
          <Icon className={`w-4.5 h-4.5 ${color || 'text-slate-500'}`} />
        </div>
      </div>
    </CardContent>
  </Card>
);

const TimeAgo = ({ ts }) => {
  if (!ts) return <span className="text-slate-400">—</span>;
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return <span className="text-emerald-600">Az once</span>;
  if (mins < 60) return <span className="text-slate-600">{mins}dk once</span>;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return <span className="text-slate-600">{hrs}sa once</span>;
  const days = Math.floor(hrs / 24);
  return <span className={`${days > 3 ? 'text-amber-600' : 'text-slate-600'}`}>{days}g once</span>;
};

const ChannelManagerDashboardV2 = ({ user, tenant, onLogout, embedded = false }) => {
  const navigate = useNavigate();
  const isSuperAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drilldown, setDrilldown] = useState(null);
  const [drilldownData, setDrilldownData] = useState(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);

  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const fetchDashboard = useCallback(async ({ silent = false } = {}) => {
    // Geçici ağ hatasında (backend restart, vite proxy ECONNREFUSED) tek
    // retry — kullanıcı görmeden önce. Backend gerçekten çökmüşse ikinci
    // denemede de hata alır, toast düşer.
    const tryOnce = () => axios.get('/channel-manager/v2/dashboard/overview', { headers });
    try {
      setLoading(true);
      let resp;
      try {
        resp = await tryOnce();
      } catch (firstErr) {
        const status = firstErr?.response?.status;
        // 4xx auth/yetki gerçek hata — retry etme
        if (status && status >= 400 && status < 500) throw firstErr;
        await new Promise(r => setTimeout(r, 1500));
        resp = await tryOnce();
      }
      setData(resp.data);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[CM Dashboard] fetch failed:',
        err?.response?.status, err?.response?.data || err?.message);
      if (!silent) {
        const detail = err?.response?.data?.detail
          || (err?.message?.includes('Network') ? 'Sunucuya ulaşılamıyor' : null);
        toast.error(detail
          ? `Dashboard verileri yüklenemedi: ${detail}`
          : 'Dashboard verileri yüklenemedi');
      }
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- headers stable per mount
  }, []);

  useEffect(() => { fetchDashboard({ silent: true }); }, [fetchDashboard]);

  const openDrilldown = useCallback(async (connectorId) => {
    setDrilldown(connectorId);
    setDrilldownLoading(true);
    try {
      const { data: d } = await axios.get(`/channel-manager/v2/dashboard/connector/${connectorId}`, { headers });
      setDrilldownData(d);
    } catch {
      toast.error('Connector detayları yüklenemedi');
    } finally {
      setDrilldownLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  if (loading && !data) {
    return (
      <Layout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout}>
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-[#C09D63]" />
        </div>
      </Layout>
    );
  }

  const kpis = data?.kpis || {};
  const connectors = data?.connectors || [];
  const recentRes = data?.recent_reservations || [];
  const mapping = data?.mapping_visibility || {};

  return (
    <Layout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout}>
      <div className="max-w-7xl mx-auto space-y-6" data-testid="cm-dashboard">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#C09D63]/10 flex items-center justify-center">
              <Cloud className="w-5 h-5 text-[#C09D63]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>
                Channel Manager Dashboard
              </h1>
              <p className="text-sm text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.tum_kanal_operasyonlarinin_birlesik_goru')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isSuperAdmin && (
              <Button variant="outline" size="sm" onClick={() => navigate('/channel-ops')} data-testid="cta-channel-ops">
                <Zap className="w-4 h-4 mr-1.5 text-amber-500" />
                Operasyon Merkezi
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={fetchDashboard} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              {t('cm.pages_ChannelManagerDashboardV2.yenile')}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3" data-testid="kpi-grid">
          <KpiCard icon={Plug} label={t('cm.pages_ChannelManagerDashboardV2.toplam_connector')} value={kpis.total_connectors || 0} />
          <KpiCard icon={CheckCircle} label="Saglikli" value={kpis.healthy || 0} color="text-emerald-600" />
          <KpiCard icon={AlertTriangle} label="Bozulmus" value={(kpis.degraded || 0) + (kpis.error || 0)} color={(kpis.degraded || 0) + (kpis.error || 0) > 0 ? 'text-red-600' : 'text-slate-500'} sub={`${kpis.degraded || 0} yavaslama, ${kpis.error || 0} hata`} />
          <KpiCard icon={Users} label="Son 24s Rez." value={kpis.recent_reservations_24h || 0} color="text-blue-600" />
          <KpiCard icon={WifiOff} label="Basarisiz Import" value={kpis.failed_imports || 0} color={kpis.failed_imports > 0 ? 'text-red-600' : 'text-slate-500'} />
          <KpiCard icon={Layers} label="Push Kuyrugu" value={kpis.push_queue_depth || 0} color={kpis.push_queue_depth > 10 ? 'text-amber-600' : 'text-slate-500'} sub={`${kpis.wire_failures_24h || 0} wire hatası`} />
        </div>

        {(kpis.review_queue > 0 || kpis.dlq_count > 0 || mapping.total_conflicts > 0) && (
          <div className="flex flex-wrap gap-2" data-testid="alert-strip">
            {kpis.review_queue > 0 && (
              <div
                className={`flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm ${isSuperAdmin ? 'cursor-pointer hover:bg-amber-100 transition-colors' : ''}`}
                onClick={isSuperAdmin ? () => navigate('/channel-ops') : undefined}
                data-testid="alert-review-queue"
              >
                <Eye className="w-4 h-4 text-amber-600" />
                <span className="text-amber-800 font-medium">{kpis.review_queue} rezervasyon inceleme bekliyor</span>
                {isSuperAdmin && <ArrowRight className="w-3.5 h-3.5 text-amber-500" />}
              </div>
            )}
            {kpis.dlq_count > 0 && (
              <div
                className={`flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm ${isSuperAdmin ? 'cursor-pointer hover:bg-red-100 transition-colors' : ''}`}
                onClick={isSuperAdmin ? () => navigate('/channel-ops') : undefined}
                data-testid="alert-dlq"
              >
                <Shield className="w-4 h-4 text-red-600" />
                <span className="text-red-800 font-medium">{kpis.dlq_count} mesaj DLQ&apos;da</span>
                {isSuperAdmin && <ArrowRight className="w-3.5 h-3.5 text-red-500" />}
              </div>
            )}
            {mapping.total_conflicts > 0 && (
              <div
                className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm cursor-pointer hover:bg-amber-100 transition-colors"
                onClick={() => navigate('/room-mapping-wizard')}
                data-testid="alert-mapping-conflicts"
              >
                <ArrowLeftRight className="w-4 h-4 text-amber-600" />
                <span className="text-amber-800 font-medium">{mapping.total_conflicts} mapping cakismasi</span>
                <ArrowRight className="w-3.5 h-3.5 text-amber-500" />
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Card data-testid="connector-table">
              <CardHeader className="pb-3">
                <CardTitle className="text-base" style={{ fontFamily: 'Manrope, sans-serif' }}>
                  Connector Durumu
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-slate-50">
                        <th className="text-left px-4 py-2 text-xs font-medium text-slate-500">Connector</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Saglayici</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.durum')}</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Son Sync</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.son_hata')}</th>
                        <th className="text-right px-3 py-2 text-xs font-medium text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.islem')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {connectors.length === 0 ? (
                        <tr><td colSpan={6} className="text-center py-8 text-slate-400">{t('cm.pages_ChannelManagerDashboardV2.connector_bulunamadi')}</td></tr>
                      ) : connectors.map((c, i) => (
                        <tr key={c.id || i} className="border-b last:border-0 hover:bg-slate-50 transition-colors" data-testid={`connector-row-${i}`}>
                          <td className="px-4 py-3">
                            <div className="font-medium text-slate-800">{c.display_name || c.id}</div>
                            <div className="text-[10px] text-slate-400">{c.property_id || ''}</div>
                          </td>
                          <td className="px-3 py-3"><ProviderBadge provider={c.provider} /></td>
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-1.5">
                              <StatusBadge status={c.status} />
                              {c.consecutive_failures > 0 && (
                                <span className="text-[10px] text-red-500">({c.consecutive_failures}x)</span>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-3 text-xs"><TimeAgo ts={c.last_successful_sync} /></td>
                          <td className="px-3 py-3">
                            {c.last_error ? (
                              <div className="max-w-[180px]">
                                <p className="text-xs text-red-600 truncate" title={c.last_error}>{c.last_error}</p>
                                <div className="text-[10px] text-slate-400"><TimeAgo ts={c.last_error_at} /></div>
                              </div>
                            ) : (
                              <span className="text-xs text-slate-400">—</span>
                            )}
                          </td>
                          <td className="px-3 py-3 text-right">
                            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => openDrilldown(c.id)} data-testid={`drilldown-btn-${i}`}>
                              <BarChart3 className="w-3.5 h-3.5 mr-1" />
                              Detay
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card data-testid="recent-reservations">
              <CardHeader className="pb-3">
                <CardTitle className="text-base" style={{ fontFamily: 'Manrope, sans-serif' }}>
                  Son Ithal Edilen Rezervasyonlar
                </CardTitle>
              </CardHeader>
              <CardContent>
                {recentRes.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-6">{t('cm.pages_ChannelManagerDashboardV2.henuz_ithal_edilen_rezervasyon_yok')}</p>
                ) : (
                  <div className="space-y-2">
                    {recentRes.map((r, i) => {
                      const statusColors = {
                        imported: 'bg-emerald-100 text-emerald-700',
                        review: 'bg-amber-100 text-amber-700',
                        failed: 'bg-red-100 text-red-700',
                        approved: 'bg-blue-100 text-blue-700',
                      };
                      return (
                        <div key={r.id || i} className="flex items-center gap-3 px-3 py-2 rounded-lg border bg-white hover:bg-slate-50 transition-colors" data-testid={`recent-res-${i}`}>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-slate-800 truncate">{r.guest_name || r.external_reservation_id || 'Bilinmeyen'}</span>
                              <Badge className={`text-[10px] ${statusColors[r.import_status] || 'bg-slate-100 text-slate-600'}`}>{r.import_status}</Badge>
                            </div>
                            <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                              {r.room_type && <span>{r.room_type}</span>}
                              {r.check_in && <span>• {new Date(r.check_in).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })}</span>}
                              {r.check_out && <><ArrowRight className="w-3 h-3" /> <span>{new Date(r.check_out).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })}</span></>}
                            </div>
                          </div>
                          <div className="text-[10px] text-slate-400"><TimeAgo ts={r.created_at} /></div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            <Card data-testid="mapping-visibility">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <ArrowLeftRight className="w-4 h-4 text-[#C09D63]" />
                  <CardTitle className="text-base" style={{ fontFamily: 'Manrope, sans-serif' }}>
                    Mapping Durumu
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2.5 rounded-lg bg-emerald-50 text-center">
                    <div className="text-lg font-bold text-emerald-700">{mapping.connectors_with_mappings || 0}</div>
                    <div className="text-[10px] text-emerald-600">Eslesmis</div>
                  </div>
                  <div className={`p-2.5 rounded-lg text-center ${mapping.total_review_pending > 0 ? 'bg-amber-50' : 'bg-slate-50'}`}>
                    <div className={`text-lg font-bold ${mapping.total_review_pending > 0 ? 'text-amber-700' : 'text-slate-400'}`}>{mapping.total_review_pending || 0}</div>
                    <div className="text-[10px] text-slate-500">Inceleme Bekliyor</div>
                  </div>
                </div>
                {mapping.total_conflicts > 0 && (
                  <div
                    className="p-2.5 rounded-lg bg-red-50 flex items-center gap-2 cursor-pointer hover:bg-red-100 transition-colors"
                    onClick={() => navigate('/room-mapping-wizard')}
                    data-testid="mapping-conflict-cta"
                  >
                    <AlertTriangle className="w-4 h-4 text-red-500" />
                    <div className="flex-1">
                      <div className="text-sm font-bold text-red-700">{mapping.total_conflicts} Cakisma</div>
                      <div className="text-[10px] text-red-600">Mapping Sihirbazi&apos;ndan cozun</div>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-red-400" />
                  </div>
                )}

                {(mapping.provider_summaries || []).length > 0 && (
                  <div className="space-y-2 pt-2 border-t">
                    <p className="text-xs font-medium text-slate-500">Provider Bazli</p>
                    {mapping.provider_summaries.map((ps, i) => (
                      <div key={i} className="p-2 rounded border bg-white text-xs space-y-1">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            <ProviderBadge provider={ps.provider} />
                            <span className="font-medium text-slate-700 truncate max-w-[120px]">{ps.connector_name}</span>
                          </div>
                          {ps.conflicts > 0 && <Badge className="bg-red-100 text-red-700 text-[10px]">{ps.conflicts} cakisma</Badge>}
                        </div>
                        <div className="flex gap-3 text-[10px] text-slate-500">
                          <span><span className="font-medium text-emerald-600">{ps.mapped}</span> eslesmis</span>
                          <span><span className="font-medium text-blue-600">{ps.auto_matched}</span> otomatik</span>
                          <span><span className="font-medium text-amber-600">{ps.needs_review}</span> inceleme</span>
                          <span><span className="font-medium text-red-600">{ps.unmatched}</span> eslesmedi</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card data-testid="ops-summary">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-500" />
                  <CardTitle className="text-base" style={{ fontFamily: 'Manrope, sans-serif' }}>
                    Operasyon Ozeti
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-2.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">Push Kuyrugu</span>
                  <Badge className={kpis.push_queue_depth > 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}>{kpis.push_queue_depth || 0}</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">Wire Hatalari (24s)</span>
                  <Badge className={kpis.wire_failures_24h > 0 ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-500'}>{kpis.wire_failures_24h || 0}</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">DLQ Mesajlari</span>
                  <Badge className={kpis.dlq_count > 0 ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-500'}>{kpis.dlq_count || 0}</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">Inceleme Kuyrugu</span>
                  <Badge className={kpis.review_queue > 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}>{kpis.review_queue || 0}</Badge>
                </div>
                {isSuperAdmin && (
                  <div className="pt-2 border-t mt-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full text-xs text-amber-700 hover:text-amber-800 hover:bg-amber-50"
                      onClick={() => navigate('/channel-ops')}
                      data-testid="ops-summary-cta"
                    >
                      <Zap className="w-3.5 h-3.5 mr-1.5" />
                      {t('cm.pages_ChannelManagerDashboardV2.detayli_operasyon_gorunumu')}
                      <ArrowRight className="w-3.5 h-3.5 ml-auto" />
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {drilldown && (
          <>
            <div className="fixed inset-0 bg-black/40 z-50" onClick={() => { setDrilldown(null); setDrilldownData(null); }} />
            <div className="fixed top-0 right-0 h-full w-[600px] max-w-[90vw] bg-white z-50 shadow-2xl overflow-y-auto animate-in slide-in-from-right" data-testid="connector-drilldown">
              {drilldownLoading ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 animate-spin text-[#C09D63]" />
                </div>
              ) : drilldownData ? (() => {
                const c = drilldownData.connector || {};
                const q = drilldownData.queue || {};
                const failures = drilldownData.recent_failures || [];
                const resSt = drilldownData.reservation_stats || {};
                const mp = drilldownData.mapping || {};
                return (
                  <>
                    <div className="sticky top-0 z-10 bg-white border-b px-5 py-4 flex items-center justify-between">
                      <div>
                        <h3 className="font-semibold text-slate-800">{c.display_name || c.id}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <ProviderBadge provider={c.provider} />
                          <StatusBadge status={c.status} />
                        </div>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => { setDrilldown(null); setDrilldownData(null); }} className="h-8 w-8 p-0">
                        <X className="w-4 h-4" />
                      </Button>
                    </div>

                    <div className="p-5 space-y-5">
                      <div className="grid grid-cols-3 gap-3">
                        <div className="p-3 rounded-lg bg-slate-50 text-center">
                          <div className="text-lg font-bold text-slate-800">{c.total_syncs || 0}</div>
                          <div className="text-[10px] text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.toplam_sync')}</div>
                        </div>
                        <div className="p-3 rounded-lg bg-slate-50 text-center">
                          <div className="text-lg font-bold text-red-600">{c.total_errors || 0}</div>
                          <div className="text-[10px] text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.toplam_hata')}</div>
                        </div>
                        <div className="p-3 rounded-lg bg-slate-50 text-center">
                          <div className="text-lg font-bold text-amber-600">{c.consecutive_failures || 0}</div>
                          <div className="text-[10px] text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.ardisik_hata')}</div>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-slate-500">{t('cm.pages_ChannelManagerDashboardV2.son_basarili_sync')}</span>
                          <TimeAgo ts={c.last_successful_sync} />
                        </div>
                        {c.last_error && (
                          <div className="p-3 bg-red-50 rounded-lg border border-red-100">
                            <div className="flex items-center gap-2 mb-1">
                              <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                              <span className="text-xs font-medium text-red-700">{t('cm.pages_ChannelManagerDashboardV2.son_hata_aeb44')}</span>
                              <TimeAgo ts={c.last_error_at} />
                            </div>
                            <p className="text-xs text-red-600">{c.last_error}</p>
                          </div>
                        )}
                      </div>

                      <div>
                        <h4 className="text-sm font-semibold text-slate-700 mb-2">Kuyruk Durumu</h4>
                        <div className="grid grid-cols-3 gap-2 text-center">
                          <div className="p-2 rounded bg-amber-50">
                            <div className="text-sm font-bold text-amber-700">{q.pending || 0}</div>
                            <div className="text-[10px] text-amber-600">Bekleyen</div>
                          </div>
                          <div className="p-2 rounded bg-blue-50">
                            <div className="text-sm font-bold text-blue-700">{q.retry || 0}</div>
                            <div className="text-[10px] text-blue-600">Tekrar</div>
                          </div>
                          <div className="p-2 rounded bg-red-50">
                            <div className="text-sm font-bold text-red-700">{q.dead_letter || 0}</div>
                            <div className="text-[10px] text-red-600">DLQ</div>
                          </div>
                        </div>
                      </div>

                      <div>
                        <h4 className="text-sm font-semibold text-slate-700 mb-2">{t('cm.pages_ChannelManagerDashboardV2.rezervasyon_istatistikleri')}</h4>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(resSt).map(([status, count]) => (
                            <div key={status} className="px-2.5 py-1 rounded-full bg-slate-100 text-xs">
                              <span className="font-medium text-slate-700">{count}</span>
                              <span className="text-slate-500 ml-1">{status}</span>
                            </div>
                          ))}
                          {Object.keys(resSt).length === 0 && <span className="text-xs text-slate-400">Veri yok</span>}
                        </div>
                      </div>

                      {mp.summary && (
                        <div>
                          <h4 className="text-sm font-semibold text-slate-700 mb-2">Mapping Durumu</h4>
                          <div className="flex flex-wrap gap-2 text-xs">
                            <Badge className="bg-emerald-100 text-emerald-700">{mp.summary.already_mapped || 0} eslesmis</Badge>
                            <Badge className="bg-blue-100 text-blue-700">{mp.summary.auto_matched || 0} otomatik</Badge>
                            <Badge className="bg-amber-100 text-amber-700">{mp.summary.needs_review || 0} inceleme</Badge>
                            <Badge className="bg-red-100 text-red-700">{mp.summary.unmatched || 0} eslesmedi</Badge>
                          </div>
                          {(mp.conflicts || []).length > 0 && (
                            <div className="mt-2 p-2 bg-red-50 rounded border border-red-100 space-y-1">
                              {mp.conflicts.map((cf, ci) => (
                                <div key={ci} className="text-[11px] text-red-700">• {cf.message}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {failures.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold text-slate-700 mb-2">Son Hatalar ({failures.length})</h4>
                          <div className="space-y-1.5 max-h-[250px] overflow-y-auto">
                            {failures.map((f, fi) => (
                              <div key={fi} className="p-2 rounded border bg-red-50/50 text-xs">
                                <div className="flex items-center justify-between">
                                  <span className="text-red-700 font-medium truncate max-w-[280px]">{f.error || f.reason || 'Bilinmeyen hata'}</span>
                                  <TimeAgo ts={f.created_at} />
                                </div>
                                {f.payload_summary && <p className="text-[10px] text-slate-500 mt-1 truncate">{JSON.stringify(f.payload_summary).slice(0, 100)}</p>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                );
              })() : null}
            </div>
          </>
        )}
      </div>
    </Layout>
  );
};

export default ChannelManagerDashboardV2;
