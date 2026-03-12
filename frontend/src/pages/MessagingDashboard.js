import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Mail, MessageSquare, Phone, Shield, RefreshCw, Send,
  AlertTriangle, CheckCircle2, XCircle, Clock, Eye,
  Settings, FileText, BarChart3, Loader2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const headers = () => ({
  Authorization: `Bearer ${localStorage.getItem('token')}`,
  'Content-Type': 'application/json',
});
const get = async (p) => { const r = await fetch(`${API}${p}`, { headers: headers() }); return r.json(); };
const post = async (p, b) => { const r = await fetch(`${API}${p}`, { method: 'POST', headers: headers(), body: JSON.stringify(b) }); return r.json(); };

const STATUS_COLORS = {
  sent: 'bg-emerald-100 text-emerald-800',
  delivered: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
  bounced: 'bg-red-100 text-red-800',
  queued: 'bg-amber-100 text-amber-800',
  sending: 'bg-blue-100 text-blue-800',
};

const CHANNEL_ICONS = { sms: Phone, email: Mail, whatsapp: MessageSquare };

function ProvidersTab() {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    const d = await get('/api/messaging-center/providers');
    setProviders(d.providers || []);
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const healthCheck = async () => {
    await post('/api/messaging-center/providers/health-check', {});
    load();
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">Provider Yapılandırması</h3>
        <Button data-testid="health-check-btn" size="sm" variant="outline" onClick={healthCheck}>
          <Shield className="h-4 w-4 mr-1" /> Sağlık Kontrolü
        </Button>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : providers.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">
          <Settings className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>Henüz provider tanımlanmamış. Ayarlar &gt; Messaging altından Twilio, SendGrid veya WhatsApp ekleyin.</p>
        </CardContent></Card>
      ) : (
        <div className="grid gap-3">
          {providers.map(p => (
            <Card key={p.id} data-testid={`provider-${p.provider_type}`}>
              <CardContent className="py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`h-3 w-3 rounded-full ${p.health_status === 'healthy' ? 'bg-emerald-500' : p.health_status === 'unhealthy' ? 'bg-red-500' : 'bg-gray-400'}`} />
                  <div>
                    <p className="font-medium">{p.provider_type.replace('_', ' ').toUpperCase()}</p>
                    <p className="text-xs text-muted-foreground">{p.is_sandbox ? 'Sandbox' : 'Production'} · {p.enabled ? 'Aktif' : 'Devre Dışı'}</p>
                  </div>
                </div>
                <Badge variant={p.health_status === 'healthy' ? 'default' : 'destructive'}>
                  {p.health_status || 'Bilinmiyor'}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function TemplatesTab() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      const d = await get('/api/messaging-center/templates');
      setTemplates(d.templates || []);
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">Mesaj Şablonları</h3>
      {templates.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">
          <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>Şablon yok. pre_arrival, room_ready, checkout gibi şablonlar oluşturun.</p>
        </CardContent></Card>
      ) : (
        <div className="grid gap-3">
          {templates.map(t => (
            <Card key={t.id}>
              <CardContent className="py-3">
                <div className="flex justify-between items-center">
                  <div>
                    <p className="font-medium">{t.name}</p>
                    <p className="text-xs text-muted-foreground">{t.category} · {t.channel} · v{t.version}</p>
                  </div>
                  <Badge variant={t.is_active ? 'default' : 'secondary'}>{t.is_active ? 'Aktif' : 'Devre Dışı'}</Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function DeliveryLogsTab() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const load = useCallback(async () => {
    setLoading(true);
    const params = filter !== 'all' ? `?status=${filter}` : '';
    const d = await get(`/api/messaging-center/delivery-logs${params}`);
    setLogs(d.logs || []);
    setLoading(false);
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const retry = async (id) => { await post(`/api/messaging-center/retry/${id}`, {}); load(); };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">Teslimat Logları</h3>
        <div className="flex gap-1">
          {['all', 'sent', 'failed', 'queued'].map(f => (
            <Button key={f} size="sm" variant={filter === f ? 'default' : 'outline'} onClick={() => setFilter(f)}>
              {f === 'all' ? 'Tümü' : f.charAt(0).toUpperCase() + f.slice(1)}
            </Button>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>
      ) : logs.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">Kayıt yok</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {logs.map(l => {
            const Icon = CHANNEL_ICONS[l.channel] || Mail;
            return (
              <Card key={l.id} data-testid={`delivery-log-${l.id}`}>
                <CardContent className="py-3 flex items-center gap-3">
                  <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{l.recipient}</p>
                    <p className="text-xs text-muted-foreground truncate">{l.use_case || l.channel} · {new Date(l.created_at).toLocaleString('tr-TR')}</p>
                  </div>
                  <Badge className={STATUS_COLORS[l.status] || 'bg-gray-100'}>{l.status}</Badge>
                  {l.status === 'failed' && l.retry_count < (l.max_retries || 3) && (
                    <Button size="sm" variant="ghost" onClick={() => retry(l.id)}><RefreshCw className="h-3 w-3" /></Button>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MetricsTab() {
  const [metrics, setMetrics] = useState(null);
  useEffect(() => {
    (async () => { const d = await get('/api/messaging-center/metrics?days=7'); setMetrics(d); })();
  }, []);

  if (!metrics) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  const channels = Object.entries(metrics.metrics_by_channel || {});
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">Teslimat Metrikleri (Son 7 Gün)</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="py-4 text-center">
          <p className="text-2xl font-bold">{metrics.total_messages}</p>
          <p className="text-xs text-muted-foreground">Toplam Mesaj</p>
        </CardContent></Card>
        {channels.map(([ch, stats]) => (
          <Card key={ch}><CardContent className="py-4 text-center">
            <p className="text-lg font-bold">{Object.values(stats).reduce((a, b) => a + b, 0)}</p>
            <p className="text-xs text-muted-foreground">{ch.toUpperCase()}</p>
            <div className="flex gap-1 justify-center mt-1">
              {stats.sent && <Badge variant="default" className="text-[10px]">{stats.sent} sent</Badge>}
              {stats.failed && <Badge variant="destructive" className="text-[10px]">{stats.failed} fail</Badge>}
            </div>
          </CardContent></Card>
        ))}
      </div>
    </div>
  );
}

export default function MessagingDashboard() {
  const { t } = useTranslation();
  return (
    <div data-testid="messaging-dashboard" className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("techDashboards.messagingDashboard")}</h1>
        <p className="text-sm text-muted-foreground">SMS, Email ve WhatsApp provider yönetimi, teslimat logları ve metrikler</p>
      </div>
      <Tabs defaultValue="logs">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger data-testid="tab-providers" value="providers">Providerlar</TabsTrigger>
          <TabsTrigger data-testid="tab-templates" value="templates">Şablonlar</TabsTrigger>
          <TabsTrigger data-testid="tab-logs" value="logs">Teslimat Logları</TabsTrigger>
          <TabsTrigger data-testid="tab-metrics" value="metrics">Metrikler</TabsTrigger>
        </TabsList>
        <TabsContent value="providers"><ProvidersTab /></TabsContent>
        <TabsContent value="templates"><TemplatesTab /></TabsContent>
        <TabsContent value="logs"><DeliveryLogsTab /></TabsContent>
        <TabsContent value="metrics"><MetricsTab /></TabsContent>
      </Tabs>
    </div>
  );
}
