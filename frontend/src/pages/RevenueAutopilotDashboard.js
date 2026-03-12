import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Zap, Shield, CheckCircle2, XCircle, RotateCcw, Clock,
  TrendingUp, AlertTriangle, Loader2, RefreshCw, Settings,
  ThumbsUp, ThumbsDown, BarChart3,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const hdrs = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });
const get = async (p) => (await fetch(`${API}${p}`, { headers: hdrs() })).json();
const post = async (p, b) => (await fetch(`${API}${p}`, { method: 'POST', headers: hdrs(), body: JSON.stringify(b) })).json();
const doPut = async (p, b) => (await fetch(`${API}${p}`, { method: 'PUT', headers: hdrs(), body: JSON.stringify(b) })).json();

const MODE_LABELS = { full_auto: 'Tam Otonom', supervised: 'Denetimli', advisory: 'Danışma' };
const STATUS_MAP = {
  pending: { label: 'Bekliyor', cls: 'bg-amber-100 text-amber-800', icon: Clock },
  approved: { label: 'Onaylandı', cls: 'bg-emerald-100 text-emerald-800', icon: CheckCircle2 },
  auto_applied: { label: 'Oto-Uygulanan', cls: 'bg-blue-100 text-blue-800', icon: Zap },
  rejected: { label: 'Reddedildi', cls: 'bg-red-100 text-red-800', icon: XCircle },
  rolled_back: { label: 'Geri Alındı', cls: 'bg-gray-100 text-gray-800', icon: RotateCcw },
};

export default function RevenueAutopilotDashboard() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('queue');

  const load = useCallback(async () => {
    setLoading(true);
    const d = await get('/api/revenue-autopilot/dashboard');
    setData(d);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const approve = async (id) => { await post(`/api/revenue-autopilot/queue/${id}/approve`, {}); load(); };
  const reject = async (id) => { await post(`/api/revenue-autopilot/queue/${id}/reject`, { reason: 'Manuel red' }); load(); };
  const rollback = async (id) => { await post(`/api/revenue-autopilot/queue/${id}/rollback`, {}); load(); };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const { policy = {}, pending_queue = [], daily_summary = {}, recent_applies = [] } = data || {};

  return (
    <div data-testid="revenue-autopilot-dashboard" className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("techDashboards.revenueAutopilot")}</h1>
          <p className="text-sm text-muted-foreground">ML bazlı fiyat önerileri, otomatik uygulama ve onay kuyruğu</p>
        </div>
        <Button data-testid="refresh-autopilot" variant="outline" size="sm" onClick={load}><RefreshCw className="h-4 w-4 mr-1" /> Yenile</Button>
      </div>

      {/* Policy Summary */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Card><CardContent className="py-3 text-center">
          <p className="text-xs text-muted-foreground">Mod</p>
          <p className="text-lg font-bold">{MODE_LABELS[policy.mode] || policy.mode}</p>
        </CardContent></Card>
        <Card><CardContent className="py-3 text-center">
          <p className="text-xs text-muted-foreground">Oto Eşik</p>
          <p className="text-lg font-bold">{(policy.confidence_threshold_auto * 100).toFixed(0)}%</p>
        </CardContent></Card>
        <Card><CardContent className="py-3 text-center">
          <p className="text-xs text-muted-foreground">Max Değişim</p>
          <p className="text-lg font-bold">{policy.max_price_change_pct}%</p>
        </CardContent></Card>
        <Card><CardContent className="py-3 text-center">
          <p className="text-xs text-muted-foreground">Bugün Toplam</p>
          <p className="text-lg font-bold">{daily_summary.total_recommendations}</p>
        </CardContent></Card>
        <Card><CardContent className="py-3 text-center">
          <p className="text-xs text-muted-foreground">Oto-Uygulanan</p>
          <p className="text-lg font-bold text-emerald-600">{daily_summary.auto_applied}</p>
        </CardContent></Card>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger data-testid="tab-queue" value="queue">
            Onay Kuyruğu {pending_queue.length > 0 && <Badge variant="destructive" className="ml-1 text-[10px]">{pending_queue.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger data-testid="tab-applied" value="applied">Son Uygulamalar</TabsTrigger>
          <TabsTrigger data-testid="tab-policy" value="policy">Politika</TabsTrigger>
        </TabsList>

        <TabsContent value="queue">
          {pending_queue.length === 0 ? (
            <Card><CardContent className="py-8 text-center text-muted-foreground">Bekleyen öneri yok</CardContent></Card>
          ) : (
            <div className="space-y-2">
              {pending_queue.map(item => (
                <Card key={item.id} data-testid={`queue-item-${item.id}`}>
                  <CardContent className="py-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">{item.room_type} · {item.target_date}</p>
                        <p className="text-sm text-muted-foreground">
                          {item.current_price}₺ → {item.recommended_price}₺
                          <span className={`ml-2 ${item.price_change_pct >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                            ({item.price_change_pct > 0 ? '+' : ''}{item.price_change_pct}%)
                          </span>
                        </p>
                        <p className="text-xs text-muted-foreground">Güven: {(item.confidence * 100).toFixed(0)}% · {item.reason}</p>
                      </div>
                      <div className="flex gap-1">
                        <Button data-testid={`approve-${item.id}`} size="sm" onClick={() => approve(item.id)}>
                          <ThumbsUp className="h-3 w-3 mr-1" /> Onayla
                        </Button>
                        <Button data-testid={`reject-${item.id}`} size="sm" variant="destructive" onClick={() => reject(item.id)}>
                          <ThumbsDown className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="applied">
          {recent_applies.length === 0 ? (
            <Card><CardContent className="py-8 text-center text-muted-foreground">Henüz uygulama yok</CardContent></Card>
          ) : (
            <div className="space-y-2">
              {recent_applies.map(a => (
                <Card key={a.id}>
                  <CardContent className="py-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{a.room_type}: {a.old_price}₺ → {a.new_price}₺</p>
                      <p className="text-xs text-muted-foreground">{new Date(a.created_at).toLocaleString('tr-TR')} · Kanallar: {(a.channels_pushed || []).join(', ')}</p>
                    </div>
                    <Badge variant={a.success ? 'default' : 'destructive'}>{a.success ? 'Başarılı' : 'Başarısız'}</Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="policy">
          <Card>
            <CardHeader><CardTitle className="text-base">Autopilot Politikası</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div><span className="text-muted-foreground">Mod:</span> <strong>{MODE_LABELS[policy.mode]}</strong></div>
                <div><span className="text-muted-foreground">Durum:</span> <strong>{policy.enabled ? 'Aktif' : 'Devre Dışı'}</strong></div>
                <div><span className="text-muted-foreground">Oto-Uygulama Eşiği:</span> <strong>{(policy.confidence_threshold_auto * 100).toFixed(0)}%</strong></div>
                <div><span className="text-muted-foreground">Kuyruk Eşiği:</span> <strong>{(policy.confidence_threshold_queue * 100).toFixed(0)}%</strong></div>
                <div><span className="text-muted-foreground">Max Fiyat Değişimi:</span> <strong>{policy.max_price_change_pct}%</strong></div>
                <div><span className="text-muted-foreground">Kara Tarihler:</span> <strong>{policy.blackout_dates?.length || 0}</strong></div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
