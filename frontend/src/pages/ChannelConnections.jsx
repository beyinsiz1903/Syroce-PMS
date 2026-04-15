import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import {
  Network, CheckCircle, XCircle, RefreshCw, Link2, Unlink,
  Building2, ArrowDownUp, Loader2, Eye, EyeOff, Info,
  Wifi, WifiOff, MapPin, Layers, ExternalLink, Settings2,
  ShieldCheck, Clock, AlertTriangle
} from 'lucide-react';

const API = "";

export default function ChannelConnections({ user, tenant, onLogout }) {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connectDialog, setConnectDialog] = useState(null); // 'hotelrunner' | 'exely' | null
  const [connecting, setConnecting] = useState(false);
  const [testing, setTesting] = useState(null);
  const [disconnecting, setDisconnecting] = useState(null);
  const [showPassword, setShowPassword] = useState({});

  const isSuperAdmin = user?.role === 'super_admin';

  const [hrForm, setHrForm] = useState({
    token: '', hr_id: '', property_name: '',
    auto_sync_reservations: true, sync_interval_minutes: 15,
  });

  const [exelyForm, setExelyForm] = useState({
    username: '', password: '', hotel_code: '', endpoint_url: '',
    property_name: '', currency: 'TRY', auto_sync_reservations: true, sync_interval_minutes: 15,
  });

  const headers = { Authorization: `Bearer ${user?.token || user?.access_token}` };

  const fetchOverview = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await axios.get(`/channel-manager/connections/overview`, { headers });
      setOverview(data);
    } catch (err) {
      toast.error('Bağlantı durumu alınamadı');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchOverview(); }, []);

  const getProvider = (name) => overview?.providers?.find(p => p.provider === name);

  // ── HotelRunner Connect ──
  const connectHR = async () => {
    if (!hrForm.token || !hrForm.hr_id) {
      toast.error('Token ve HR ID zorunludur');
      return;
    }
    setConnecting(true);
    try {
      const { data } = await axios.post(`/channel-manager/hotelrunner/connect`, {
        ...hrForm,
        environment: 'production',
      }, { headers });
      toast.success('HotelRunner bağlantısı başarıyla kuruldu!');
      setConnectDialog(null);
      setHrForm({ token: '', hr_id: '', property_name: '', auto_sync_reservations: true, sync_interval_minutes: 15 });
      fetchOverview();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'HotelRunner bağlantı hatası');
    } finally {
      setConnecting(false);
    }
  };

  // ── Exely Connect ──
  const connectExely = async () => {
    if (!exelyForm.username || !exelyForm.password || !exelyForm.hotel_code) {
      toast.error('Kullanıcı adı, şifre ve otel kodu zorunludur');
      return;
    }
    setConnecting(true);
    try {
      const { data } = await axios.post(`/channel-manager/exely/connect`, exelyForm, { headers });
      toast.success('Exely bağlantısı başarıyla kuruldu!');
      setConnectDialog(null);
      setExelyForm({ username: '', password: '', hotel_code: '', endpoint_url: '', property_name: '', currency: 'TRY', auto_sync_reservations: true, sync_interval_minutes: 15 });
      fetchOverview();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Exely bağlantı hatası');
    } finally {
      setConnecting(false);
    }
  };

  // ── Test Connection ──
  const testConnection = async (provider) => {
    setTesting(provider);
    try {
      const endpoint = provider === 'hotelrunner'
        ? `/channel-manager/hotelrunner/test`
        : `/channel-manager/exely/test`;
      const { data } = await axios.post(endpoint, {}, { headers });
      if (data.success || data.connected) {
        toast.success(`${provider === 'hotelrunner' ? 'HotelRunner' : 'Exely'} bağlantısı aktif ve çalışıyor!`);
      } else {
        toast.error(`Bağlantı testi başarısız: ${data.error || 'Bilinmeyen hata'}`);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bağlantı testi başarısız');
    } finally {
      setTesting(null);
    }
  };

  // ── Disconnect ──
  const disconnect = async (provider) => {
    setDisconnecting(provider);
    try {
      const endpoint = provider === 'hotelrunner'
        ? `/channel-manager/hotelrunner/disconnect`
        : `/channel-manager/exely/disconnect`;
      await axios.delete(endpoint, { headers });
      toast.success(`${provider === 'hotelrunner' ? 'HotelRunner' : 'Exely'} bağlantısı kesildi`);
      fetchOverview();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bağlantı kesilirken hata oluştu');
    } finally {
      setDisconnecting(null);
    }
  };

  const hr = getProvider('hotelrunner');
  const exely = getProvider('exely');

  // ── Collect all connected OTA channels across all providers ──
  const allConnectedChannels = [];
  if (hr?.connected && hr?.channels?.length > 0) {
    hr.channels.forEach(ch => {
      const name = ch.name || ch.code || ch;
      if (name && !allConnectedChannels.includes(name)) allConnectedChannels.push(name);
    });
  }

  // ── HOTEL USER VIEW (non-superadmin) ──
  if (!isSuperAdmin) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout}>
        <div className="p-4 md:p-6 space-y-6 max-w-4xl mx-auto" data-testid="channel-connections-page">

          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold text-slate-900" data-testid="page-title">Bagli Kanallar</h1>
              <p className="text-sm text-slate-500 mt-1">
                Otelinizin bagli oldugu satis kanallari ve acenteler
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchOverview}
              disabled={loading}
              data-testid="refresh-btn"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : allConnectedChannels.length > 0 ? (
            <>
              {/* Connection Status Summary */}
              <Card className="border-green-200 bg-green-50/50">
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                      <CheckCircle className="w-5 h-5 text-green-600" />
                    </div>
                    <div>
                      <p className="font-semibold text-green-800">Kanal Baglantisi Aktif</p>
                      <p className="text-sm text-green-600">
                        {allConnectedChannels.length} satis kanali uzerinden rezervasyon alinabiliyor
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Connected Channels Grid */}
              <div>
                <h2 className="text-base font-semibold text-slate-700 mb-3" data-testid="connected-channels-title">
                  Bagli Satis Kanallari ({allConnectedChannels.length})
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                  {allConnectedChannels.map((channel, i) => (
                    <Card key={i} className="border-slate-200 hover:border-green-300 transition-colors" data-testid={`channel-card-${i}`}>
                      <CardContent className="p-3 flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center shrink-0">
                          <CheckCircle className="w-4 h-4 text-green-600" />
                        </div>
                        <span className="text-sm font-medium text-slate-800 truncate">{channel}</span>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>

              {/* Sync Status */}
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <ArrowDownUp className="w-4 h-4 text-slate-500" />
                    <span className="text-sm font-medium text-slate-700">Senkronizasyon Durumu</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                    {hr?.connected && (
                      <div className="flex items-center justify-between p-2 rounded bg-slate-50">
                        <span className="text-slate-600">Otomatik Senk.</span>
                        {hr.auto_sync_reservations ? (
                          <span className="text-green-600 flex items-center gap-1 text-xs font-medium"><CheckCircle className="w-3 h-3" /> Aktif</span>
                        ) : (
                          <span className="text-slate-400 text-xs">Pasif</span>
                        )}
                      </div>
                    )}
                    {hr?.last_sync_at && (
                      <div className="flex items-center justify-between p-2 rounded bg-slate-50">
                        <span className="text-slate-600">Son Senkronizasyon</span>
                        <span className="text-xs text-slate-500">{new Date(hr.last_sync_at).toLocaleDateString('tr-TR')}</span>
                      </div>
                    )}
                    {exely?.connected && (
                      <div className="flex items-center justify-between p-2 rounded bg-slate-50">
                        <span className="text-slate-600">Otomatik Senk.</span>
                        {exely.auto_sync_reservations ? (
                          <span className="text-green-600 flex items-center gap-1 text-xs font-medium"><CheckCircle className="w-3 h-3" /> Aktif</span>
                        ) : (
                          <span className="text-slate-400 text-xs">Pasif</span>
                        )}
                      </div>
                    )}
                    {exely?.last_sync_at && (
                      <div className="flex items-center justify-between p-2 rounded bg-slate-50">
                        <span className="text-slate-600">Son Senkronizasyon</span>
                        <span className="text-xs text-slate-500">{new Date(exely.last_sync_at).toLocaleDateString('tr-TR')}</span>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            /* No Channels Connected */
            <Card className="border-slate-200">
              <CardContent className="p-8 text-center">
                <WifiOff className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <h3 className="text-lg font-semibold text-slate-700 mb-1">Henüz bagli kanal yok</h3>
                <p className="text-sm text-slate-500 max-w-md mx-auto">
                  Satis kanallari (Booking.com, Expedia vb.) uzerinden rezervasyon alabilmek icin
                  lutfen otel yoneticinize basvurun.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </Layout>
    );
  }

  // ── SUPER ADMIN VIEW (full technical details) ──
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto" data-testid="channel-connections-page">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900" data-testid="page-title">Kanal Yönetimi</h1>
            <p className="text-sm text-slate-500 mt-1">
              Kanal saglayicilarinizin baglanti durumunu yonetin ve yeni baglanti kurun
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchOverview}
            disabled={loading}
            data-testid="refresh-btn"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        </div>

        {/* Onboarding Guide */}
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="p-4">
            <div className="flex gap-3">
              <Info className="w-5 h-5 text-blue-600 mt-0.5 shrink-0" />
              <div className="text-sm text-blue-800 space-y-1">
                <p className="font-semibold">Yeni Otel Baglanti Rehberi</p>
                <ol className="list-decimal ml-4 space-y-0.5 text-blue-700">
                  <li>Kanal saglayicinizdan (HotelRunner / Exely) API kimlik bilgilerini alin</li>
                  <li>Asagidaki ilgili saglayici kartindan "Baglan" butonuna tiklayin</li>
                  <li>Kimlik bilgilerini girin — sistem otomatik olarak baglanti testi yapacak</li>
                  <li>Baglanti kurulduktan sonra oda eslemelerini yapin</li>
                  <li>Acenteler (Booking, Expedia vb.) HotelRunner/Exely panelinden baglanir</li>
                </ol>
                <p className="text-xs text-blue-600 mt-2">
                  <strong>Not:</strong> Her otel için ayri token/ID gereklidir. Bu bilgiler otele ozeldir ve saglayici tarafindan verilir.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* PMS Room Types Info */}
        {overview?.pms_room_types?.length > 0 && (
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Layers className="w-4 h-4 text-slate-500" />
                <span className="text-sm font-medium text-slate-700">PMS Oda Tipleri</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {overview.pms_room_types.map(rt => (
                  <Badge key={rt} variant="secondary" className="text-xs">{rt}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Provider Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* HotelRunner Card */}
          <ProviderCard
            provider="hotelrunner"
            displayName="HotelRunner"
            description="Booking.com, Expedia, EtsTur, JollyTur ve diger OTA baglantilari"
            data={hr}
            loading={loading}
            testing={testing === 'hotelrunner'}
            disconnecting={disconnecting === 'hotelrunner'}
            onConnect={() => setConnectDialog('hotelrunner')}
            onTest={() => testConnection('hotelrunner')}
            onDisconnect={() => disconnect('hotelrunner')}
            detailsPath="/hotelrunner"
            credentialFields={[
              { label: 'HR ID', value: hr?.hr_id },
              { label: 'Ortam', value: hr?.environment },
            ]}
            extraInfo={hr?.channels?.length > 0 ? (
              <div className="mt-3">
                <span className="text-xs font-medium text-slate-500">Bagli Acenteler:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {hr.channels.map((ch, i) => (
                    <Badge key={i} variant="outline" className="text-xs">
                      {ch.name || ch.code || ch}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          />

          {/* Exely Card */}
          <ProviderCard
            provider="exely"
            displayName="Exely"
            description="SOAP API ile acente baglantilari ve musaitlik yonetimi"
            data={exely}
            loading={loading}
            testing={testing === 'exely'}
            disconnecting={disconnecting === 'exely'}
            onConnect={() => setConnectDialog('exely')}
            onTest={() => testConnection('exely')}
            onDisconnect={() => disconnect('exely')}
            detailsPath="/exely"
            credentialFields={[
              { label: 'Otel Kodu', value: exely?.hotel_code },
              { label: 'Para Birimi', value: exely?.currency },
            ]}
            extraInfo={exely?.room_types?.length > 0 ? (
              <div className="mt-3">
                <span className="text-xs font-medium text-slate-500">Oda Tipleri ({exely.room_types.length}):</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {exely.room_types.slice(0, 5).map((rt, i) => (
                    <Badge key={i} variant="outline" className="text-xs">
                      {rt.name || rt.code || rt}
                    </Badge>
                  ))}
                  {exely.room_types.length > 5 && (
                    <Badge variant="outline" className="text-xs">+{exely.room_types.length - 5}</Badge>
                  )}
                </div>
              </div>
            ) : null}
          />
        </div>

        {/* HotelRunner Connect Dialog */}
        <Dialog open={connectDialog === 'hotelrunner'} onOpenChange={(o) => !o && setConnectDialog(null)}>
          <DialogContent className="max-w-md" data-testid="hr-connect-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Network className="w-5 h-5 text-orange-600" />
                HotelRunner Baglantisi Kur
              </DialogTitle>
              <DialogDescription>
                HotelRunner panelinizden aldiginiz API token ve HR ID bilgilerini girin.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <Label htmlFor="hr-token">API Token *</Label>
                <div className="relative">
                  <Input
                    id="hr-token"
                    type={showPassword.hrToken ? 'text' : 'password'}
                    value={hrForm.token}
                    onChange={e => setHrForm(f => ({ ...f, token: e.target.value }))}
                    placeholder="HotelRunner API token"
                    data-testid="hr-token-input"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    onClick={() => setShowPassword(p => ({ ...p, hrToken: !p.hrToken }))}
                  >
                    {showPassword.hrToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-slate-400 mt-1">HotelRunner &gt; Ayarlar &gt; API Entegrasyonu boluumunden alinir</p>
              </div>
              <div>
                <Label htmlFor="hr-id">HR ID (Otel ID) *</Label>
                <Input
                  id="hr-id"
                  value={hrForm.hr_id}
                  onChange={e => setHrForm(f => ({ ...f, hr_id: e.target.value }))}
                  placeholder="ornek: 12345"
                  data-testid="hr-id-input"
                />
                <p className="text-xs text-slate-400 mt-1">HotelRunner panelindeki otel kimlik numarası</p>
              </div>
              <div>
                <Label htmlFor="hr-name">Otel Adi</Label>
                <Input
                  id="hr-name"
                  value={hrForm.property_name}
                  onChange={e => setHrForm(f => ({ ...f, property_name: e.target.value }))}
                  placeholder="Grand Hotel Istanbul"
                  data-testid="hr-name-input"
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="hr-autosync" className="text-sm">Otomatik Rezervasyon Senkronizasyonu</Label>
                <Switch
                  id="hr-autosync"
                  checked={hrForm.auto_sync_reservations}
                  onCheckedChange={v => setHrForm(f => ({ ...f, auto_sync_reservations: v }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConnectDialog(null)} disabled={connecting}>İptal</Button>
              <Button onClick={connectHR} disabled={connecting} data-testid="hr-connect-submit">
                {connecting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />}
                Baglan ve Test Et
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Exely Connect Dialog */}
        <Dialog open={connectDialog === 'exely'} onOpenChange={(o) => !o && setConnectDialog(null)}>
          <DialogContent className="max-w-md" data-testid="exely-connect-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Network className="w-5 h-5 text-emerald-600" />
                Exely Baglantisi Kur
              </DialogTitle>
              <DialogDescription>
                Exely'den aldiginiz SOAP API kimlik bilgilerini girin.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <Label htmlFor="exely-user">Kullanici Adi *</Label>
                <Input
                  id="exely-user"
                  value={exelyForm.username}
                  onChange={e => setExelyForm(f => ({ ...f, username: e.target.value }))}
                  placeholder="PMSConnect.XXXXXX"
                  data-testid="exely-username-input"
                />
              </div>
              <div>
                <Label htmlFor="exely-pass">Sifre *</Label>
                <div className="relative">
                  <Input
                    id="exely-pass"
                    type={showPassword.exelyPass ? 'text' : 'password'}
                    value={exelyForm.password}
                    onChange={e => setExelyForm(f => ({ ...f, password: e.target.value }))}
                    placeholder="API sifresi"
                    data-testid="exely-password-input"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    onClick={() => setShowPassword(p => ({ ...p, exelyPass: !p.exelyPass }))}
                  >
                    {showPassword.exelyPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div>
                <Label htmlFor="exely-hotel">Otel Kodu *</Label>
                <Input
                  id="exely-hotel"
                  value={exelyForm.hotel_code}
                  onChange={e => setExelyForm(f => ({ ...f, hotel_code: e.target.value }))}
                  placeholder="501694"
                  data-testid="exely-hotelcode-input"
                />
                <p className="text-xs text-slate-400 mt-1">Exely tarafindan verilen otel kodu</p>
              </div>
              <div>
                <Label htmlFor="exely-name">Otel Adi</Label>
                <Input
                  id="exely-name"
                  value={exelyForm.property_name}
                  onChange={e => setExelyForm(f => ({ ...f, property_name: e.target.value }))}
                  placeholder="Grand Hotel Istanbul"
                  data-testid="exely-name-input"
                />
              </div>
              <div>
                <Label htmlFor="exely-endpoint">Endpoint URL (Opsiyonel)</Label>
                <Input
                  id="exely-endpoint"
                  value={exelyForm.endpoint_url}
                  onChange={e => setExelyForm(f => ({ ...f, endpoint_url: e.target.value }))}
                  placeholder="https://..."
                  data-testid="exely-endpoint-input"
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="exely-autosync" className="text-sm">Otomatik Rezervasyon Senkronizasyonu</Label>
                <Switch
                  id="exely-autosync"
                  checked={exelyForm.auto_sync_reservations}
                  onCheckedChange={v => setExelyForm(f => ({ ...f, auto_sync_reservations: v }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConnectDialog(null)} disabled={connecting}>İptal</Button>
              <Button onClick={connectExely} disabled={connecting} data-testid="exely-connect-submit">
                {connecting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />}
                Baglan ve Test Et
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

      </div>
    </Layout>
  );
}


// ── Reusable Provider Card ──────────────────────────────────────────
function ProviderCard({
  provider, displayName, description, data, loading,
  testing, disconnecting, onConnect, onTest, onDisconnect,
  detailsPath, credentialFields, extraInfo,
}) {
  const connected = data?.connected;
  const mappings = data?.room_mappings_count || 0;

  const colorMap = {
    hotelrunner: { border: 'border-orange-200', bg: 'bg-orange-50', accent: 'text-orange-600', badge: 'bg-orange-100 text-orange-700' },
    exely: { border: 'border-emerald-200', bg: 'bg-emerald-50', accent: 'text-emerald-600', badge: 'bg-emerald-100 text-emerald-700' },
  };
  const colors = colorMap[provider] || colorMap.hotelrunner;

  return (
    <Card className={`${connected ? colors.border : 'border-slate-200'} transition-all`} data-testid={`${provider}-card`}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${connected ? colors.bg : 'bg-slate-100'}`}>
              {connected
                ? <Wifi className={`w-5 h-5 ${colors.accent}`} />
                : <WifiOff className="w-5 h-5 text-slate-400" />
              }
            </div>
            <div>
              <CardTitle className="text-lg">{displayName}</CardTitle>
              <CardDescription className="text-xs mt-0.5">{description}</CardDescription>
            </div>
          </div>
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
          ) : (
            <Badge
              className={`text-xs ${connected ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}`}
              data-testid={`${provider}-status-badge`}
            >
              {connected ? 'Bagli' : 'Bagli Degil'}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {connected ? (
          <>
            {/* Connection Details */}
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-slate-500 text-xs">Otel</span>
                <p className="font-medium text-slate-800 truncate">{data.property_name || '-'}</p>
              </div>
              {credentialFields?.map((field, i) => (
                field.value ? (
                  <div key={i}>
                    <span className="text-slate-500 text-xs">{field.label}</span>
                    <p className="font-medium text-slate-800">{field.value}</p>
                  </div>
                ) : null
              ))}
              <div>
                <span className="text-slate-500 text-xs">Oda Eslemesi</span>
                <p className="font-medium text-slate-800">
                  {mappings > 0 ? (
                    <span className="text-green-600">{mappings} esleme</span>
                  ) : (
                    <span className="text-amber-600">Henüz yok</span>
                  )}
                </p>
              </div>
              <div>
                <span className="text-slate-500 text-xs">Oto. Senk.</span>
                <p className="font-medium text-slate-800">
                  {data.auto_sync_reservations ? (
                    <span className="text-green-600 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Aktif</span>
                  ) : (
                    <span className="text-slate-400">Pasif</span>
                  )}
                </p>
              </div>
            </div>

            {/* Timestamps */}
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 border-t pt-2">
              {data.connected_at && (
                <div className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Baglanti: {new Date(data.connected_at).toLocaleDateString('tr-TR')}
                </div>
              )}
              {data.last_sync_at && (
                <div className="flex items-center gap-1">
                  <ArrowDownUp className="w-3 h-3" />
                  Son senk: {new Date(data.last_sync_at).toLocaleDateString('tr-TR')}
                </div>
              )}
            </div>

            {/* Extra Info (channels, room types) */}
            {extraInfo}

            {/* Mapping Warning */}
            {mappings === 0 && (
              <div className="flex items-start gap-2 p-2 rounded bg-amber-50 border border-amber-200 text-xs text-amber-700">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium">Oda eslemesi gerekli</p>
                  <p>Musaitlik senkronizasyonu için PMS oda tiplerini kanal oda tipleriyle eslestirin.</p>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-2 pt-1">
              <Button
                size="sm"
                variant="outline"
                onClick={onTest}
                disabled={testing}
                data-testid={`${provider}-test-btn`}
              >
                {testing ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <ShieldCheck className="w-3 h-3 mr-1.5" />}
                Test Et
              </Button>
              <Button
                size="sm"
                variant="outline"
                asChild
              >
                <a href={detailsPath} data-testid={`${provider}-details-link`}>
                  <Settings2 className="w-3 h-3 mr-1.5" />
                  Detayli Yönetim
                </a>
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-red-500 hover:text-red-700 hover:bg-red-50"
                onClick={onDisconnect}
                disabled={disconnecting}
                data-testid={`${provider}-disconnect-btn`}
              >
                {disconnecting ? <Loader2 className="w-3 h-3 mr-1.5 animate-spin" /> : <Unlink className="w-3 h-3 mr-1.5" />}
                Baglantıyı Kes
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="text-center py-4">
              <WifiOff className="w-10 h-10 text-slate-300 mx-auto mb-2" />
              <p className="text-sm text-slate-500 mb-1">
                {displayName} baglantisi kurulmamis
              </p>
              <p className="text-xs text-slate-400 mb-4">
                Baglanmak için {displayName} API kimlik bilgilerinizi girin
              </p>
              <Button onClick={onConnect} data-testid={`${provider}-connect-btn`}>
                <Link2 className="w-4 h-4 mr-2" />
                {displayName} Baglan
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
