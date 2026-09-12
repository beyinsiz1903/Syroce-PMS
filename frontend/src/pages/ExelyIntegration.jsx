import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Network, CheckCircle, XCircle, RefreshCw, Link2, Unlink, Building2, ArrowDownUp, CalendarCheck, Activity, AlertTriangle, Loader2, Search, Download, ExternalLink, FlaskConical, Wand2, Trash2, Plus } from 'lucide-react';
import TestBookingVerification from '@/components/TestBookingVerification';
import { useTranslation } from 'react-i18next';
import { confirmDialog } from '@/lib/dialogs';
const API = "";

export const buildExelyRequestConfig = user => {
  const token = user?.token || user?.access_token;
  return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
};

export const parseExelyConnectionTestResult = data => ({
  connected: Boolean(data?.connected),
  durationMs: data?.duration_ms ?? 0,
  errorCode: data?.error_type || 'CONNECTION_TEST_FAILED'
});

export const getExelyErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail?.error_code) return detail.error_code;
  if (error?.code) return `${fallback} (${error.code})`;
  return fallback;
};

export const getExelyPullFailureMessage = data => {
  if (data?.success !== false) return null;
  return data.message || `EXELY_RESERVATION_PULL_FAILED:${data.error || 'EXELY_PROVIDER_READ_FAILED'}`;
};

export const getExelyImportFailureMessage = data => {
  if (data?.success !== false) return null;
  return data.message || `EXELY_RESERVATION_IMPORT_FAILED:${data.error || 'PMS_IMPORT_FAILED'}`;
};

export const buildExelyAutoMapPayload = (suggestions, rateSelections, ratePlans) => suggestions.map(suggestion => {
  const selectedCode = suggestion.provider_rate_plan_code || rateSelections[suggestion.provider_room_code];
  const selectedPlan = ratePlans.find(plan => plan.code === selectedCode);
  return {
    pms_room_type: suggestion.pms_room_type,
    provider_room_code: suggestion.provider_room_code,
    provider_room_name: suggestion.provider_room_name,
    provider_rate_plan_code: selectedCode || '',
    provider_rate_plan_name: suggestion.provider_rate_plan_name || selectedPlan?.name || ''
  };
});

export const hasCompleteExelyRatePlanSelection = mappings => mappings.every(mapping => Boolean(mapping.provider_rate_plan_code));

export const buildExelyManualMapPayload = (manualMap, providerRoomTypes = []) => {
  const providerRoom = providerRoomTypes.find(room => room.code === manualMap.exely_room_code);
  return {
    pms_room_type: manualMap.pms_room_type.trim(),
    exely_room_code: manualMap.exely_room_code.trim(),
    exely_rate_plan_code: manualMap.exely_rate_plan_code.trim(),
    pms_api_room_code: (manualMap.pms_api_room_code || '').trim(),
    pms_api_rate_plan_code: (manualMap.pms_api_rate_plan_code || '').trim(),
    exely_room_name: providerRoom?.name || manualMap.exely_room_name?.trim() || manualMap.exely_room_code.trim(),
    sync_availability: Boolean(manualMap.sync_availability),
    sync_price: Boolean(manualMap.sync_price),
    sync_restrictions: Boolean(manualMap.sync_restrictions)
  };
};

const emptyManualMap = () => ({
  pms_room_type: '',
  exely_room_code: '',
  exely_rate_plan_code: '',
  pms_api_room_code: '',
  pms_api_rate_plan_code: '',
  exely_room_name: '',
  sync_availability: true,
  sync_price: true,
  sync_restrictions: true
});

const ExelyIntegration = ({
  user,
  tenant,
  onLogout
}) => {
  const {
    t
  } = useTranslation();
  const [activeTab, setActiveTab] = useState('connection');
  const [loading, setLoading] = useState(false);
  const [connection, setConnection] = useState(null);
  const [roomTypes, setRoomTypes] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [syncLogs, setSyncLogs] = useState([]);
  const [syncStatus, setSyncStatus] = useState(null);
  const [autoMapOpen, setAutoMapOpen] = useState(false);
  const [autoMapSuggestions, setAutoMapSuggestions] = useState(null);
  const [autoMapLoading, setAutoMapLoading] = useState(false);
  const [mappingStatus, setMappingStatus] = useState(null);
  const [manualMapOpen, setManualMapOpen] = useState(false);
  const [editingMappingId, setEditingMappingId] = useState(null);
  const [manualMapSaving, setManualMapSaving] = useState(false);
  const [ariWriteLoading, setAriWriteLoading] = useState(false);
  const [manualMap, setManualMap] = useState(emptyManualMap);
  const [connectForm, setConnectForm] = useState({
    username: '',
    password: '',
    hotel_code: '',
    endpoint_url: '',
    property_name: '',
    currency: 'TRY',
    mode: 'sandbox',
    auto_sync_reservations: true,
    sync_interval_minutes: 15
  });
  // Cookie-authenticated sessions do not expose the access token on the
  // canonical user. Avoid replacing that valid session with "Bearer undefined".
  const requestConfig = buildExelyRequestConfig(user);
  const fetchConnection = useCallback(async () => {
    try {
      const {
        data
      } = await axios.get(`/channel-manager/exely/connection`, requestConfig);
      setConnection(data);
      if (data.connection?.room_types) setRoomTypes(data.connection.room_types);
      if (data.connection?.rate_plans) setRatePlans(data.connection.rate_plans);
    } catch {
      setConnection({
        connected: false
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);
  const fetchAll = useCallback(async () => {
    if (!connection?.connected) return;
    try {
      const [mappingsRes, logsRes, localRes, statusRes] = await Promise.all([axios.get(`/channel-manager/exely/room-mappings`, requestConfig).catch(() => ({
        data: {
          mappings: []
        }
      })), axios.get(`/channel-manager/exely/sync-logs?limit=20`, requestConfig).catch(() => ({
        data: {
          logs: []
        }
      })), axios.get(`/channel-manager/exely/reservations/local`, requestConfig).catch(() => ({
        data: {
          reservations: []
        }
      })), axios.get(`/channel-manager/exely/sync/status`, requestConfig).catch(() => ({
        data: {}
      }))]);
      setMappings(mappingsRes.data.mappings || []);
      setSyncLogs(logsRes.data.logs || []);
      setReservations(localRes.data.reservations || []);
      setSyncStatus(statusRes.data);
    } catch (e) {
      console.error(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [connection?.connected]);
  useEffect(() => {
    fetchConnection();
  }, [fetchConnection]);
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);
  const fetchMappingStatus = useCallback(async () => {
    try {
      const {
        data
      } = await axios.get(`/channel-manager/auto-map/status/exely`, requestConfig);
      setMappingStatus(data);
    } catch {/* ignore */}
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => {
    if (connection?.connected) fetchMappingStatus();
  }, [connection?.connected, fetchMappingStatus]);
  const handleAutoMapSuggest = async () => {
    setAutoMapLoading(true);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/auto-map/suggest`, {
        provider: 'exely'
      }, requestConfig);
      setAutoMapSuggestions(data);
      setAutoMapOpen(true);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Otomatik esleme onerisi alinamadi');
    } finally {
      setAutoMapLoading(false);
    }
  };
  const handleDeleteMapping = async mappingId => {
    if (!(await confirmDialog({
      message: 'Bu Exely oda ve fiyat planı eşlemesi kalıcı olarak silinecek. Devam edilsin mi?',
      variant: 'danger'
    }))) return;
    try {
      await axios.delete(`/channel-manager/exely/room-mappings/${mappingId}`, requestConfig);
      toast.success('Esleme silindi');
      fetchAll();
      fetchMappingStatus();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Silme hatası');
    }
  };
  const handleCreateMapping = async () => {
    const payload = buildExelyManualMapPayload(manualMap, mappingStatus?.provider_room_types || []);
    if (!payload.pms_room_type || !payload.exely_room_code || !payload.exely_rate_plan_code) {
      toast.error('PMS oda tipi, Exely oda tipi ve fiyat planı zorunludur');
      return;
    }
    if (!payload.sync_availability && !payload.sync_price && !payload.sync_restrictions) {
      toast.error('En az bir senkronizasyon türü seçilmelidir');
      return;
    }
    setManualMapSaving(true);
    try {
      if (editingMappingId) {
        await axios.patch(`/channel-manager/exely/room-mappings/${editingMappingId}`, payload, requestConfig);
      } else {
        await axios.post(`/channel-manager/exely/room-mappings`, payload, requestConfig);
      }
      toast.success(editingMappingId ? 'Eşleme güncellendi' : 'Oda ve fiyat planı eşlemesi oluşturuldu');
      setManualMapOpen(false);
      setEditingMappingId(null);
      setManualMap(emptyManualMap());
      await Promise.all([fetchAll(), fetchMappingStatus()]);
    } catch (error) {
      toast.error(getExelyErrorMessage(error, 'Eşleme oluşturulamadı'));
    } finally {
      setManualMapSaving(false);
    }
  };
  const handleConnect = async () => {
    if (!connectForm.username || !connectForm.password || !connectForm.hotel_code) {
      toast.error('Kullanıcı adı, şifre ve otel kodu zorunludur');
      return;
    }
    setLoading(true);
    try {
      const payload = {
        ...connectForm
      };
      if (!payload.endpoint_url) delete payload.endpoint_url;
      const {
        data
      } = await axios.post(`/channel-manager/exely/connect`, payload, requestConfig);
      toast.success(data.message);
      setConnection({
        connected: true,
        connection: data
      });
      if (data.room_types) setRoomTypes(data.room_types);
      if (data.rate_plans) setRatePlans(data.rate_plans);
      fetchConnection();
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Bağlantı hatası');
    } finally {
      setLoading(false);
    }
  };
  const handleDisconnect = async () => {
    if (!(await confirmDialog({
      message: 'Exely bağlantısı kesilecek. Rezervasyon çekme ve ARI aktarımı durur. Devam edilsin mi?',
      variant: 'danger'
    }))) return;
    try {
      await axios.delete(`/channel-manager/exely/disconnect`, requestConfig);
      toast.success('Exely baglantisi kesildi');
      setConnection({
        connected: false
      });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Hata');
    }
  };
  const handleCurrencyChange = async newCurrency => {
    if (!(await confirmDialog({
      message: `Exely para birimi ${newCurrency} olarak değiştirilecek. Yeni ARI fiyatları bu para birimiyle gönderilir. Devam edilsin mi?`,
      variant: 'danger'
    }))) return;
    try {
      await axios.patch(`/channel-manager/exely/currency`, {
        currency: newCurrency
      }, requestConfig);
      toast.success(`Para birimi ${newCurrency} olarak güncellendi`);
      fetchConnection();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Para birimi güncellenemedi');
    }
  };
  const handleTest = async () => {
    setLoading(true);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/exely/test`, {}, requestConfig);
      const result = parseExelyConnectionTestResult(data);
      if (result.connected) toast.success(`Bağlantı basarili (${result.durationMs}ms)`);else toast.error(`Bağlantı hatası: ${result.errorCode}`);
    } catch (e) {
      toast.error(getExelyErrorMessage(e, 'Bağlantı testi tamamlanamadı'));
    } finally {
      setLoading(false);
    }
  };
  const handleDiscover = async () => {
    setLoading(true);
    try {
      const {
        data
      } = await axios.get(`/channel-manager/exely/rooms/discover`, requestConfig);
      setRoomTypes(data.room_types || []);
      setRatePlans(data.rate_plans || []);
      toast.success(`${(data.room_types || []).length} oda tipi, ${(data.rate_plans || []).length} fiyat plani kesfedildi`);
    } catch (e) {
      toast.error(getExelyErrorMessage(e, 'Oda ve fiyat planı keşfi tamamlanamadı; bağlantı ve canlı erişim anahtarlarını kontrol edin'));
    } finally {
      setLoading(false);
    }
  };
  const handlePull = async () => {
    setLoading(true);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/exely/sync/reservations/pull`, {}, requestConfig);
      const pullFailure = getExelyPullFailureMessage(data);
      if (pullFailure) {
        toast.error(pullFailure);
        return;
      }
      toast.success(data.message);
      fetchAll();
    } catch (e) {
      toast.error(getExelyErrorMessage(e, 'Rezervasyon çekme tamamlanamadı; bağlantı ve canlı senkronizasyon anahtarlarını kontrol edin'));
    } finally {
      setLoading(false);
    }
  };
  const handleImport = async resId => {
    try {
      const {
        data
      } = await axios.post(`/channel-manager/exely/reservations/${resId}/import`, {}, requestConfig);
      const importFailure = getExelyImportFailureMessage(data);
      if (importFailure) {
        toast.error(importFailure);
        return;
      }
      toast.success(`${data.message} - Oda: ${data.room_number}`);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Import hatası');
    }
  };
  const handleAriWriteToggle = async () => {
    const enabled = !connection?.connection?.ari_write_enabled;
    if (!(await confirmDialog({
      message: enabled ? 'Bu tesis için Exely stok, fiyat ve kısıtlama gönderimleri açılacak. Devam edilsin mi?' : 'Bu tesis için Exely stok, fiyat ve kısıtlama gönderimleri durdurulacak. Devam edilsin mi?',
      variant: enabled ? 'warning' : 'danger'
    }))) return;
    setAriWriteLoading(true);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/exely/ari-write`, {
        enabled,
        confirmation: enabled ? 'ENABLE_EXELY_ARI_WRITE' : 'DISABLE_EXELY_ARI_WRITE'
      }, requestConfig);
      toast.success(data.message);
      await fetchConnection();
    } catch (e) {
      toast.error(getExelyErrorMessage(e, 'Exely ARI ayarı değiştirilemedi'));
    } finally {
      setAriWriteLoading(false);
    }
  };
  const isConnected = connection?.connected;
  return <>
      <div className="p-4 md:p-6 space-y-6" data-testid="exely-integration">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900" data-testid="exely-page-title">Exely Entegrasyonu</h1>
            <p className="text-sm text-slate-500 mt-1">{t('cm.pages_ExelyIntegration.soap_channel_manager_ota_standart_rezerv')}</p>
          </div>
          <Badge data-testid="exely-connection-badge" variant={isConnected ? 'default' : 'destructive'} className={isConnected ? 'bg-emerald-600' : ''}>
            {isConnected ? <><CheckCircle className="w-3 h-3 mr-1" /> Bagli</> : <><XCircle className="w-3 h-3 mr-1" /> Bagli Degil</>}
          </Badge>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid grid-cols-6 w-full max-w-3xl">
            <TabsTrigger value="connection" data-testid="exely-tab-connection"><Link2 className="w-4 h-4 mr-1" /> {t('cm.pages_ExelyIntegration.baglanti')}</TabsTrigger>
            <TabsTrigger value="rooms" data-testid="exely-tab-rooms" disabled={!isConnected}><Building2 className="w-4 h-4 mr-1" /> Odalar</TabsTrigger>
            <TabsTrigger value="reservations" data-testid="exely-tab-reservations" disabled={!isConnected}><CalendarCheck className="w-4 h-4 mr-1" /> Rezervasyonlar</TabsTrigger>
            <TabsTrigger value="test-booking" data-testid="exely-tab-test-booking" disabled={!isConnected}><FlaskConical className="w-4 h-4 mr-1" /> Test Booking</TabsTrigger>
            <TabsTrigger value="mappings" data-testid="exely-tab-mappings" disabled={!isConnected}><ArrowDownUp className="w-4 h-4 mr-1" /> Eslemeler</TabsTrigger>
            <TabsTrigger value="logs" data-testid="exely-tab-logs" disabled={!isConnected}><Activity className="w-4 h-4 mr-1" /> Loglar</TabsTrigger>
          </TabsList>

          {/* Connection Tab */}
          <TabsContent value="connection" className="space-y-4 mt-4">
            {!isConnected ? <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Network className="w-5 h-5" /> Exely SOAP Baglantisi Kur</CardTitle>
                  <CardDescription>Exely PMSConnect kullanıcı adı, şifre ve otel kodunu girin</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="exely-user">{t('cm.pages_ExelyIntegration.kullanici_adi')}</Label>
                      <Input id="exely-user" data-testid="exely-username-input" placeholder={t('cm.pages_ExelyIntegration.exely_kullanici_adi')} value={connectForm.username} onChange={e => setConnectForm(p => ({
                    ...p,
                    username: e.target.value
                  }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-pass">{t('cm.pages_ExelyIntegration.sifre')}</Label>
                      <Input id="exely-pass" data-testid="exely-password-input" type="password" placeholder={t('cm.pages_ExelyIntegration.exely_sifre')} value={connectForm.password} onChange={e => setConnectForm(p => ({
                    ...p,
                    password: e.target.value
                  }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-hotel">Otel Kodu</Label>
                      <Input id="exely-hotel" data-testid="exely-hotel-code-input" placeholder="Ornek: 12345" value={connectForm.hotel_code} onChange={e => setConnectForm(p => ({
                    ...p,
                    hotel_code: e.target.value
                  }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-name">{t('cm.pages_ExelyIntegration.tesis_adi_opsiyonel')}</Label>
                      <Input id="exely-name" data-testid="exely-name-input" placeholder="Ornek: Otelim" value={connectForm.property_name} onChange={e => setConnectForm(p => ({
                    ...p,
                    property_name: e.target.value
                  }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-url">Endpoint URL (opsiyonel)</Label>
                      <Input id="exely-url" data-testid="exely-url-input" placeholder="https://www.exely.com/ota/OTA" value={connectForm.endpoint_url} onChange={e => setConnectForm(p => ({
                    ...p,
                    endpoint_url: e.target.value
                  }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-mode">Bağlantı Ortamı</Label>
                      <select id="exely-mode" data-testid="exely-mode-select" value={connectForm.mode} onChange={e => setConnectForm(p => ({
                    ...p,
                    mode: e.target.value
                  }))} className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
                        <option value="sandbox">Sertifikasyon / Test</option>
                        <option value="production">Canlı</option>
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="exely-currency">Para Birimi</Label>
                      <select id="exely-currency" data-testid="exely-currency-select" value={connectForm.currency} onChange={e => setConnectForm(p => ({
                    ...p,
                    currency: e.target.value
                  }))} className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
                        <option value="TRY">TRY - Turk Lirasi</option>
                        <option value="USD">USD - Amerikan Dolari</option>
                        <option value="EUR">EUR - Euro</option>
                        <option value="GBP">GBP - Ingiliz Sterlini</option>
                        <option value="RUB">RUB - Rus Rublesi</option>
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="exely-interval">Sync Araligi (dk)</Label>
                      <Input id="exely-interval" type="number" min={5} max={60} value={connectForm.sync_interval_minutes} onChange={e => setConnectForm(p => ({
                    ...p,
                    sync_interval_minutes: parseInt(e.target.value) || 15
                  }))} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 pt-2">
                    <Switch checked={connectForm.auto_sync_reservations} onCheckedChange={v => setConnectForm(p => ({
                  ...p,
                  auto_sync_reservations: v
                }))} />
                    <Label>{t('cm.pages_ExelyIntegration.otomatik_rezervasyon_sync')}</Label>
                  </div>
                  <Button data-testid="exely-connect-btn" onClick={handleConnect} disabled={loading} className="w-full">
                    {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />}
                    Baglan
                  </Button>
                </CardContent>
              </Card> : <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><CheckCircle className="w-5 h-5 text-emerald-600" /> {t('cm.pages_ExelyIntegration.exely_baglantisi_aktif')}</CardTitle>
                    <CardDescription>
                      {connection.connection?.property_name || 'Exely'} &middot; Otel Kodu: {connection.connection?.hotel_code || '-'} {t('cm.pages_ExelyIntegration.baglanti_c9964')} {connection.connection?.connected_at ? new Date(connection.connection.connected_at).toLocaleString('tr-TR') : '-'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {connection.connection?.last_connection_test_status && <div className={`mb-4 rounded-lg border p-3 text-sm ${connection.connection.last_connection_test_status === 'healthy' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-rose-200 bg-rose-50 text-rose-800'}`} data-testid="exely-last-test-status">
                        <div className="font-medium">
                          {connection.connection.last_connection_test_status === 'healthy' ? 'Son bağlantı testi başarılı' : `Son bağlantı testi başarısız: ${connection.connection.last_connection_test_error || 'Bilinmeyen hata'}`}
                        </div>
                        {connection.connection.last_connection_test_at && <div className="mt-1 text-xs opacity-80">{new Date(connection.connection.last_connection_test_at).toLocaleString('tr-TR')}</div>}
                      </div>}
                    <div className="flex flex-wrap gap-3 items-center">
                      <Button data-testid="exely-test-btn" variant="outline" onClick={handleTest} disabled={loading}>
                        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                        {t('cm.pages_ExelyIntegration.baglanti_test')}
                      </Button>
                      <Button data-testid="exely-disconnect-btn" variant="destructive" onClick={handleDisconnect}>
                        <Unlink className="w-4 h-4 mr-2" /> Baglantivi Kes
                      </Button>
                      <Button
                        data-testid="exely-ari-write-toggle"
                        variant={connection.connection?.ari_write_enabled ? 'destructive' : 'default'}
                        onClick={handleAriWriteToggle}
                        disabled={ariWriteLoading || !syncStatus?.production_safety?.ari_write_allowed}
                        title={!syncStatus?.production_safety?.ari_write_allowed ? 'Önce global Exely ARI güvenlik anahtarı açılmalıdır' : undefined}
                      >
                        {ariWriteLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ArrowDownUp className="w-4 h-4 mr-2" />}
                        {connection.connection?.ari_write_enabled ? 'ARI Gönderimini Durdur' : 'ARI Gönderimini Aç'}
                      </Button>
                      <Badge variant={connection.connection?.ari_write_enabled ? 'default' : 'secondary'} className={connection.connection?.ari_write_enabled ? 'bg-emerald-600' : ''}>
                        Tesis ARI: {connection.connection?.ari_write_enabled ? 'Açık' : 'Kapalı'}
                      </Badge>
                      <div className="flex items-center gap-2 ml-auto">
                        <Label className="text-sm text-slate-600 whitespace-nowrap">Para Birimi:</Label>
                        <select
                          data-testid="exely-currency-change"
                          value={connection.connection?.currency || 'TRY'}
                          onChange={e => handleCurrencyChange(e.target.value)}
                          className="h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          <option value="TRY">TRY</option>
                          <option value="USD">USD</option>
                          <option value="EUR">EUR</option>
                          <option value="GBP">GBP</option>
                          <option value="RUB">RUB</option>
                        </select>
                      </div>
                    </div>
                    {syncStatus && <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">{t('cm.pages_ExelyIntegration.toplam_rezervasyon')}</p>
                          <p className="text-lg font-bold" data-testid="exely-total-reservations">{syncStatus.total_reservations || 0}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">Bekleyen Event</p>
                          <p className="text-lg font-bold">{syncStatus.pending_events || 0}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">Son 24 Saat Hata</p>
                          <p className="text-lg font-bold text-red-600">{syncStatus.error_events || 0}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">Scheduler</p>
                          <p className="text-lg font-bold">{syncStatus.scheduler_running ? 'Aktif' : 'Durdu'}</p>
                        </div>
                      </div>}
                  </CardContent>
                </Card>

                {/* Webhook section removed - using PULL mode only */}
              </div>}
          </TabsContent>

          {/* Rooms Tab */}
          <TabsContent value="rooms" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>{t('cm.pages_ExelyIntegration.exely_oda_tipleri_fiyat_planlari')}</CardTitle>
                  <CardDescription>OTA_HotelAvailRQ ile kesfedilen oda ve rate bilgileri</CardDescription>
                </div>
                <Button data-testid="exely-discover-btn" onClick={handleDiscover} disabled={loading}>
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
                  Kesfet
                </Button>
              </CardHeader>
              <CardContent className="space-y-6">
                {roomTypes.length === 0 && ratePlans.length === 0 ? <p className="text-sm text-slate-500 text-center py-8">{t('cm.pages_ExelyIntegration.henuz_oda_rate_kesfedilmedi_kesfet_buton')}</p> : <>
                    {roomTypes.length > 0 && <div>
                        <h3 className="text-sm font-semibold text-slate-700 mb-2">{t('cm.pages_ExelyIntegration.oda_tipleri')}{roomTypes.length})</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm" data-testid="exely-room-types-table">
                            <thead>
                              <tr className="border-b text-left text-slate-500">
                                <th className="pb-2 pr-4">Kod</th>
                                <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.oda_adi')}</th>
                                <th className="pb-2">Kapasite</th>
                              </tr>
                            </thead>
                            <tbody>
                              {roomTypes.map((rt, i) => <tr key={rt.id || i} className="border-b last:border-0">
                                  <td className="py-2 pr-4 font-mono text-xs">{rt.code}</td>
                                  <td className="py-2 pr-4 font-medium">{rt.name}</td>
                                  <td className="py-2">{rt.quantity || '-'}</td>
                                </tr>)}
                            </tbody>
                          </table>
                        </div>
                      </div>}
                    {ratePlans.length > 0 && <div>
                        <h3 className="text-sm font-semibold text-slate-700 mb-2">Fiyat Planlari ({ratePlans.length})</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm" data-testid="exely-rate-plans-table">
                            <thead>
                              <tr className="border-b text-left text-slate-500">
                                <th className="pb-2 pr-4">Kod</th>
                                <th className="pb-2">{t('cm.pages_ExelyIntegration.plan_adi')}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {ratePlans.map((rp, i) => <tr key={rp.id || i} className="border-b last:border-0">
                                  <td className="py-2 pr-4 font-mono text-xs">{rp.code}</td>
                                  <td className="py-2 font-medium">{rp.name || rp.code}</td>
                                </tr>)}
                            </tbody>
                          </table>
                        </div>
                      </div>}
                  </>}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Reservations Tab */}
          <TabsContent value="reservations" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Exely Rezervasyonlari</CardTitle>
                  <CardDescription>OTA_ReadRQ ile cekilen rezervasyonlar</CardDescription>
                </div>
                <Button data-testid="exely-pull-btn" onClick={handlePull} disabled={loading}>
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                  Rezervasyonlari Cek
                </Button>
              </CardHeader>
              <CardContent>
                {reservations.length === 0 ? <p className="text-sm text-slate-500 text-center py-8">{t('cm.pages_ExelyIntegration.henuz_rezervasyon_yok_rezervasyonlari_ce')}</p> : <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="exely-reservations-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">Rez. ID</th>
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.misafir')}</th>
                          <th className="pb-2 pr-4">Kanal</th>
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.giris')}</th>
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.cikis')}</th>
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.tutar')}</th>
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.durum')}</th>
                          <th className="pb-2">PMS</th>
                          <th className="pb-2">{t('cm.pages_ExelyIntegration.islem')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reservations.map((res, i) => <tr key={res.id || i} className="border-b last:border-0">
                            <td className="py-2 pr-4 font-mono text-xs">{res.external_id}</td>
                            <td className="py-2 pr-4 font-medium">{res.guest_name}</td>
                            <td className="py-2 pr-4"><Badge variant="outline">{res.channel_display || res.channel}</Badge></td>
                            <td className="py-2 pr-4">{res.checkin_date}</td>
                            <td className="py-2 pr-4">{res.checkout_date}</td>
                            <td className="py-2 pr-4 font-medium">{res.total} {res.currency}</td>
                            <td className="py-2 pr-4">
                              <Badge className={res.state === 'confirmed' ? 'bg-emerald-600' : res.state === 'cancelled' ? 'bg-red-600' : 'bg-amber-500'}>
                                {res.state}
                              </Badge>
                            </td>
                            <td className="py-2">
                              <Badge variant={res.pms_status === 'imported' ? 'default' : 'secondary'}>
                                {res.pms_status || 'pending'}
                              </Badge>
                            </td>
                            <td className="py-2">
                              {res.pms_status !== 'imported' && res.state === 'confirmed' ? <Button data-testid={`exely-import-btn-${i}`} size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleImport(res.id || res.external_id)}>
                                  <Download className="w-3 h-3 mr-1" /> PMS'e Aktar
                                </Button> : res.pms_status === 'imported' ? <span className="text-xs text-emerald-600 font-medium">Aktarildi</span> : null}
                            </td>
                          </tr>)}
                      </tbody>
                    </table>
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Test Booking Tab */}
          <TabsContent value="test-booking" className="space-y-4 mt-4">
            <TestBookingVerification />
          </TabsContent>

          {/* Mappings Tab */}
          <TabsContent value="mappings" className="space-y-4 mt-4">
            {/* Mapping Status Bar */}
            {mappingStatus && <Card data-testid="exely-mapping-status">
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="text-sm">
                        <span className="font-medium">Esleme Durumu:</span>{' '}
                        <span className="text-emerald-600 font-bold">{mappingStatus.mapped_count}</span>
                        <span className="text-slate-400"> / {mappingStatus.total_pms_types} PMS oda tipi</span>
                      </div>
                      <div className="w-32 bg-slate-200 rounded-full h-2">
                        <div className="h-2 rounded-full transition-all" style={{
                      width: `${mappingStatus.completion_pct}%`,
                      backgroundColor: mappingStatus.completion_pct === 100 ? '#22c55e' : mappingStatus.completion_pct >= 50 ? '#f59e0b' : '#ef4444'
                    }} />
                      </div>
                      <span className="text-xs text-slate-500">%{mappingStatus.completion_pct}</span>
                    </div>
                    <Button variant="outline" size="sm" onClick={handleAutoMapSuggest} disabled={autoMapLoading} data-testid="exely-auto-map-btn">
                      {autoMapLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Wand2 className="w-4 h-4 mr-1" />}
                      PMS API Kodlarını Gör
                    </Button>
                  </div>
                </CardContent>
              </Card>}

            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>{t('cm.pages_ExelyIntegration.oda_eslemeleri')}</CardTitle>
                  <CardDescription>PMS oda tipleri ile Exely oda/fiyat planlarini esleyin</CardDescription>
                </div>
                <div className="flex gap-2">
                  <Button variant="default" size="sm" onClick={() => { setEditingMappingId(null); setManualMap(emptyManualMap()); setManualMapOpen(true); }} data-testid="exely-add-rate-mapping-btn">
                    <Plus className="w-4 h-4 mr-1" /> Oda / Fiyat Planı Eşle
                  </Button>
                  {!mappingStatus && <Button variant="outline" size="sm" onClick={handleAutoMapSuggest} disabled={autoMapLoading} data-testid="exely-auto-map-btn-alt">
                      {autoMapLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Wand2 className="w-4 h-4 mr-1" />}
                      PMS API Kodlarını Gör
                    </Button>}
                </div>
              </CardHeader>
              <CardContent>
                {mappings.length === 0 ? <div className="text-center py-8">
                    <ArrowDownUp className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">{t('cm.pages_ExelyIntegration.henuz_oda_eslemesi_yok')}</p>
                    <p className="text-xs text-slate-400 mt-1">Odalar kesfedildikten sonra esleme yapilabilir</p>
                  </div> : <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="exely-mappings-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.pms_oda_tipi')}</th>
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.exely_oda_kodu')}</th>
                          <th className="pb-2 pr-4">Exely Rate Plan</th>
                          <th className="pb-2 pr-4">PMS API kodları</th>
                          <th className="pb-2 pr-4">{t('cm.pages_ExelyIntegration.exely_oda_adi')}</th>
                          <th className="pb-2 pr-4">Sync</th>
                          <th className="pb-2 text-right">{t('cm.pages_ExelyIntegration.islem_792e7')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mappings.map((m, i) => <tr key={m.id || i} className="border-b last:border-0" data-testid={`exely-mapping-row-${i}`}>
                            <td className="py-2 pr-4 font-medium">{m.pms_room_type}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{m.exely_room_code}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{m.exely_rate_plan_code}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{m.pms_api_room_code || '—'} / {m.pms_api_rate_plan_code || '—'}</td>
                            <td className="py-2 pr-4">{m.exely_room_name}</td>
                            <td className="py-2 pr-4">
                              <div className="flex gap-1">
                                {m.sync_availability && <Badge variant="secondary" className="text-xs">A</Badge>}
                                {m.sync_price && <Badge variant="secondary" className="text-xs">R</Badge>}
                                {m.sync_restrictions && <Badge variant="secondary" className="text-xs">I</Badge>}
                              </div>
                            </td>
                            <td className="py-2 text-right">
                              <Button variant="ghost" size="sm" onClick={() => { setEditingMappingId(m.id); setManualMap({ ...emptyManualMap(), ...m, pms_api_room_code: m.pms_api_room_code || m.exely_room_code, pms_api_rate_plan_code: m.pms_api_rate_plan_code || m.exely_rate_plan_code }); setManualMapOpen(true); }} data-testid={`exely-edit-mapping-${i}`} aria-label={`${m.pms_room_type} eşlemesini düzenle`}>
                                Düzenle
                              </Button>
                              <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-700 h-7 w-7 p-0" onClick={() => handleDeleteMapping(m.id)} data-testid={`exely-delete-mapping-${i}`}>
                                <Trash2 className="w-3.5 h-3.5" />
                              </Button>
                            </td>
                          </tr>)}
                      </tbody>
                    </table>
                  </div>}

                {/* Unmapped PMS Types Warning */}
                {mappingStatus && mappingStatus.unmapped_count > 0 && <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg" data-testid="exely-unmapped-warning">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-medium text-amber-800">{mappingStatus.unmapped_count} PMS oda tipi eslenmemis</p>
                        <p className="text-xs text-amber-600 mt-1">
                          {t('cm.pages_ExelyIntegration.eslenmemis_oda_tipleri_exely_ye_fiyat_mu')}
                        </p>
                      </div>
                    </div>
                  </div>}
              </CardContent>
            </Card>

            <Dialog open={manualMapOpen} onOpenChange={open => { setManualMapOpen(open); if (!open) setEditingMappingId(null); }}>
              <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>{editingMappingId ? 'Oda ve Fiyat Planı Eşlemesini Düzenle' : 'Oda ve Fiyat Planı Eşle'}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 mt-2">
                  <div>
                    <Label htmlFor="manual-pms-room">PMS oda tipi</Label>
                    <select id="manual-pms-room" data-testid="manual-pms-room" value={manualMap.pms_room_type} onChange={event => setManualMap(previous => ({ ...previous, pms_room_type: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-input bg-white px-3 text-sm">
                      <option value="">Oda tipi seçin</option>
                      {(mappingStatus?.pms_room_types || []).map(room => <option key={room.code} value={room.code}>{room.name} ({room.room_count} oda)</option>)}
                    </select>
                  </div>
                  <div>
                    <Label htmlFor="manual-exely-room">Exely ARI oda tipi ID</Label>
                    <Input id="manual-exely-room" data-testid="manual-exely-room" list="exely-room-code-options" value={manualMap.exely_room_code} onChange={event => setManualMap(previous => ({ ...previous, exely_room_code: event.target.value }))} placeholder="Keşfedilen odayı seçin veya kodu yazın" className="mt-1" />
                    <datalist id="exely-room-code-options">
                      {(mappingStatus?.provider_room_types || []).map(room => <option key={room.code} value={room.code}>{room.name}</option>)}
                    </datalist>
                    <p className="mt-1 text-xs text-slate-500">Exely oda tipi sayfasındaki ID; PMS için Exely API kodundan farklı olabilir.</p>
                  </div>
                  <div>
                    <Label htmlFor="manual-exely-rate">Exely ARI fiyat planı ID</Label>
                    <Input id="manual-exely-rate" data-testid="manual-exely-rate" list="exely-rate-code-options" value={manualMap.exely_rate_plan_code} onChange={event => setManualMap(previous => ({ ...previous, exely_rate_plan_code: event.target.value }))} placeholder="Keşfedilen planı seçin veya kodu yazın" className="mt-1" />
                    <datalist id="exely-rate-code-options">
                      {(mappingStatus?.provider_rate_plans || []).map(plan => <option key={plan.code} value={plan.code}>{plan.name || plan.code}</option>)}
                    </datalist>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="manual-pms-api-room">PMS API oda kodu (varsa)</Label>
                      <Input id="manual-pms-api-room" data-testid="manual-pms-api-room" value={manualMap.pms_api_room_code || ''} onChange={event => setManualMap(previous => ({ ...previous, pms_api_room_code: event.target.value }))} className="mt-1" />
                    </div>
                    <div>
                      <Label htmlFor="manual-pms-api-rate">PMS API fiyat kodu (varsa)</Label>
                      <Input id="manual-pms-api-rate" data-testid="manual-pms-api-rate" value={manualMap.pms_api_rate_plan_code || ''} onChange={event => setManualMap(previous => ({ ...previous, pms_api_rate_plan_code: event.target.value }))} className="mt-1" />
                    </div>
                  </div>
                  <p className="text-xs text-slate-500">ARI ID’leri dışarı stok/fiyat gönderiminde, PMS API kodları Exely rezervasyonlarını içeri eşleştirmede kullanılır.</p>
                  <div className="rounded-md border p-3 space-y-3">
                    <p className="text-sm font-medium">Senkronize edilecek bilgiler</p>
                    {[
                      ['sync_availability', 'Müsaitlik', 'A'],
                      ['sync_price', 'Fiyat', 'R'],
                      ['sync_restrictions', 'Kısıtlamalar', 'I']
                    ].map(([field, label, code]) => <div key={field} className="flex items-center justify-between gap-3">
                        <Label htmlFor={`manual-${field}`} className="font-normal">{label} ({code})</Label>
                        <Switch id={`manual-${field}`} data-testid={`manual-${field}`} checked={manualMap[field]} onCheckedChange={checked => setManualMap(previous => ({ ...previous, [field]: checked }))} />
                      </div>)}
                  </div>
                  <p className="text-xs text-slate-500">Her PMS oda tipi için yalnızca bir fiyat planında Müsaitlik (A) açık olmalıdır. Diğer planlarda sadece Fiyat/Kısıtlama seçin. Suite gibi henüz stok gönderilmeyecek odalarda Müsaitlik kapalı kalmalıdır.</p>
                  <Button className="w-full" onClick={handleCreateMapping} disabled={manualMapSaving} data-testid="manual-map-save">
                    {manualMapSaving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />} {editingMappingId ? 'Değişiklikleri Kaydet' : 'Eşlemeyi Kaydet'}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>

            {/* Auto-Map Dialog */}
            <Dialog open={autoMapOpen} onOpenChange={setAutoMapOpen}>
              <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2"><Wand2 className="w-5 h-5" /> PMS API Kod Önerileri</DialogTitle>
                </DialogHeader>
                {autoMapSuggestions && <div className="space-y-4 mt-2">
                    {autoMapSuggestions.suggestions.length > 0 ? <>
                        <p className="text-sm text-slate-600">{t('cm.pages_ExelyIntegration.isim_benzerligine_gore_eslesme_onerileri')}</p>
                        <div className="space-y-2">
                          {autoMapSuggestions.suggestions.map((s, i) => <div key={s.id || i} className="flex items-center justify-between p-3 bg-slate-50 border rounded-lg" data-testid={`auto-map-suggestion-${i}`}>
                              <div className="flex items-center gap-3">
                                <div>
                                  <p className="font-medium text-sm">{s.pms_room_name}</p>
                                  <p className="text-xs text-slate-500">PMS ({s.pms_room_count} oda)</p>
                                </div>
                                <ArrowDownUp className="w-4 h-4 text-slate-400" />
                                <div>
                                  <p className="font-medium text-sm">{s.provider_room_name}</p>
                                  <p className="text-xs text-slate-500">Exely ({s.provider_room_code})</p>
                                  <p className="mt-1 text-xs text-slate-500">PMS API oda kodu: {s.provider_room_code}</p>
                                </div>
                              </div>
                              <Badge className={s.confidence === 'high' ? 'bg-emerald-100 text-emerald-800' : s.confidence === 'medium' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'}>
                                %{Math.round(s.similarity_score * 100)}
                              </Badge>
                            </div>)}
                        </div>
                        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Bu öneriler PMS API kodlarına dayanır. Exely ARI oda ve fiyat planı ID’leri farklı olabileceğinden otomatik uygulanmaz. Exely panelindeki ID’leri doğrulayıp “Oda / Fiyat Planı Eşle” bölümünden kaydedin.</p>
                      </> : <div className="text-center py-4">
                        <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                        <p className="text-sm text-slate-600">{t('cm.pages_ExelyIntegration.otomatik_eslestirilecek_yeni_oda_tipi_bu')}</p>
                      </div>}

                    {/* Unmapped PMS types */}
                    {autoMapSuggestions.unmapped_pms_types?.length > 0 && <div className="border-t pt-4">
                        <p className="text-sm font-medium text-amber-700 mb-2">{t('cm.pages_ExelyIntegration.eslenmemis_pms_oda_tipleri_provider_da_k')}</p>
                        <div className="flex flex-wrap gap-2">
                          {autoMapSuggestions.unmapped_pms_types.map((t, i) => <Badge key={t.id || i} variant="outline" className="bg-amber-50 border-amber-300 text-amber-700" data-testid={`unmapped-pms-${i}`}>
                              <AlertTriangle className="w-3 h-3 mr-1" /> {t.name} ({t.room_count} oda)
                            </Badge>)}
                        </div>
                        <p className="text-xs text-slate-500 mt-2">Bu oda tiplerini Exely panelinden olusturup tekrar esleme yapabilirsiniz.</p>
                      </div>}

                    {/* Unmapped provider rooms */}
                    {autoMapSuggestions.unmapped_provider_rooms?.length > 0 && <div className="border-t pt-4">
                        <p className="text-sm font-medium text-blue-700 mb-2">Eslenmemis Provider Odalari:</p>
                        <div className="flex flex-wrap gap-2">
                          {autoMapSuggestions.unmapped_provider_rooms.map((r, i) => <Badge key={r.id || i} variant="outline" className="bg-blue-50 border-blue-300 text-blue-700">
                              {r.name} ({r.code})
                            </Badge>)}
                        </div>
                      </div>}
                  </div>}
              </DialogContent>
            </Dialog>
          </TabsContent>

          {/* Logs Tab */}
          <TabsContent value="logs" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Senkronizasyon Loglari</CardTitle>
                  <CardDescription>{t('cm.pages_ExelyIntegration.exely_soap_islem_gecmisi')}</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={fetchAll}>
                  <RefreshCw className="w-4 h-4 mr-1" /> {t('cm.pages_ExelyIntegration.yenile')}
                </Button>
              </CardHeader>
              <CardContent>
                {syncLogs.length === 0 ? <p className="text-sm text-slate-500 text-center py-8">{t('cm.pages_ExelyIntegration.henuz_log_kaydi_yok')}</p> : <div className="space-y-2" data-testid="exely-sync-logs">
                    {syncLogs.map((log, i) => <div key={log.id || i} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border">
                        <div className="flex items-center gap-3">
                          {log.status === 'success' ? <CheckCircle className="w-4 h-4 text-emerald-600" /> : <AlertTriangle className="w-4 h-4 text-red-500" />}
                          <div>
                            <p className="text-sm font-medium">{log.sync_type}</p>
                            <p className="text-xs text-slate-500">{log.initiator} &middot; {log.records_synced} {t('cm.pages_ExelyIntegration.kayit')}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-slate-500">{new Date(log.timestamp).toLocaleString('tr-TR')}</p>
                          {log.duration_ms > 0 && <p className="text-xs text-slate-400">{log.duration_ms}ms</p>}
                        </div>
                      </div>)}
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </>;
};
export default ExelyIntegration;
