import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Network, CheckCircle, XCircle, RefreshCw, Link2, Unlink,
  Building2, ArrowDownUp, CalendarCheck, Activity,
  AlertTriangle, Loader2, Search, Download, ExternalLink, FlaskConical,
  Wand2, Trash2
} from 'lucide-react';
import TestBookingVerification from '@/components/TestBookingVerification';

const API = import.meta.env.VITE_BACKEND_URL;

const ExelyIntegration = ({ user, tenant, onLogout }) => {
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

  const [connectForm, setConnectForm] = useState({
    username: '', password: '', hotel_code: '', endpoint_url: '',
    property_name: '', currency: 'TRY', auto_sync_reservations: true, sync_interval_minutes: 15,
  });

  const headers = { Authorization: `Bearer ${user?.token || user?.access_token}` };

  const fetchConnection = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/channel-manager/exely/connection`, { headers });
      setConnection(data);
      if (data.connection?.room_types) setRoomTypes(data.connection.room_types);
      if (data.connection?.rate_plans) setRatePlans(data.connection.rate_plans);
    } catch { setConnection({ connected: false }); }
  }, []);

  const fetchAll = useCallback(async () => {
    if (!connection?.connected) return;
    try {
      const [mappingsRes, logsRes, localRes, statusRes] = await Promise.all([
        axios.get(`${API}/api/channel-manager/exely/room-mappings`, { headers }).catch(() => ({ data: { mappings: [] } })),
        axios.get(`${API}/api/channel-manager/exely/sync-logs?limit=20`, { headers }).catch(() => ({ data: { logs: [] } })),
        axios.get(`${API}/api/channel-manager/exely/reservations/local`, { headers }).catch(() => ({ data: { reservations: [] } })),
        axios.get(`${API}/api/channel-manager/exely/sync/status`, { headers }).catch(() => ({ data: {} })),
      ]);
      setMappings(mappingsRes.data.mappings || []);
      setSyncLogs(logsRes.data.logs || []);
      setReservations(localRes.data.reservations || []);
      setSyncStatus(statusRes.data);
    } catch (e) { console.error(e); }
  }, [connection?.connected]);

  useEffect(() => { fetchConnection(); }, [fetchConnection]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const fetchMappingStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/channel-manager/auto-map/status/exely`, { headers });
      setMappingStatus(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (connection?.connected) fetchMappingStatus(); }, [connection?.connected]);

  const handleAutoMapSuggest = async () => {
    setAutoMapLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/auto-map/suggest`, { provider: 'exely' }, { headers });
      setAutoMapSuggestions(data);
      setAutoMapOpen(true);
    } catch (e) { toast.error(e.response?.data?.detail || 'Otomatik esleme onerisi alinamadi'); }
    finally { setAutoMapLoading(false); }
  };

  const handleAutoMapApply = async (selectedSuggestions) => {
    if (!selectedSuggestions?.length) return;
    setAutoMapLoading(true);
    try {
      const payload = {
        provider: 'exely',
        mappings: selectedSuggestions.map(s => ({
          pms_room_type: s.pms_room_type,
          provider_room_code: s.provider_room_code,
          provider_room_name: s.provider_room_name,
          provider_rate_plan_code: s.provider_rate_plan_code,
          provider_rate_plan_name: s.provider_rate_plan_name,
        })),
      };
      const { data } = await axios.post(`${API}/api/channel-manager/auto-map/apply`, payload, { headers });
      toast.success(data.message);
      setAutoMapOpen(false);
      fetchAll();
      fetchMappingStatus();
    } catch (e) { toast.error(e.response?.data?.detail || 'Esleme uygulanamadi'); }
    finally { setAutoMapLoading(false); }
  };

  const handleDeleteMapping = async (mappingId) => {
    try {
      await axios.delete(`${API}/api/channel-manager/exely/room-mappings/${mappingId}`, { headers });
      toast.success('Esleme silindi');
      fetchAll();
      fetchMappingStatus();
    } catch (e) { toast.error(e.response?.data?.detail || 'Silme hatasi'); }
  };

  const handleConnect = async () => {
    if (!connectForm.username || !connectForm.password || !connectForm.hotel_code) {
      toast.error('Kullanici adi, sifre ve otel kodu zorunludur');
      return;
    }
    setLoading(true);
    try {
      const payload = { ...connectForm };
      if (!payload.endpoint_url) delete payload.endpoint_url;
      const { data } = await axios.post(`${API}/api/channel-manager/exely/connect`, payload, { headers });
      toast.success(data.message);
      setConnection({ connected: true, connection: data });
      if (data.room_types) setRoomTypes(data.room_types);
      if (data.rate_plans) setRatePlans(data.rate_plans);
      fetchConnection();
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Baglanti hatasi');
    } finally { setLoading(false); }
  };

  const handleDisconnect = async () => {
    try {
      await axios.delete(`${API}/api/channel-manager/exely/disconnect`, { headers });
      toast.success('Exely baglantisi kesildi');
      setConnection({ connected: false });
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleTest = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/exely/test`, {}, { headers });
      if (data.connected) toast.success(`Baglanti basarili (${data.duration_ms}ms)`);
      else toast.error(`Baglanti hatasi: ${data.error}`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Test hatasi'); }
    finally { setLoading(false); }
  };

  const handleDiscover = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/api/channel-manager/exely/rooms/discover`, { headers });
      setRoomTypes(data.room_types || []);
      setRatePlans(data.rate_plans || []);
      toast.success(`${(data.room_types || []).length} oda tipi, ${(data.rate_plans || []).length} fiyat plani kesfedildi`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Kesfetme hatasi'); }
    finally { setLoading(false); }
  };

  const handlePull = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/exely/sync/reservations/pull`, {}, { headers });
      toast.success(data.message);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Pull hatasi'); }
    finally { setLoading(false); }
  };

  const handleImport = async (resId) => {
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/exely/reservations/${resId}/import`, {}, { headers });
      toast.success(`${data.message} - Oda: ${data.room_number}`);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Import hatasi'); }
  };

  const isConnected = connection?.connected;

  return (
    <Layout user={user} onLogout={onLogout} tenant={tenant}>
      <div className="p-4 md:p-6 space-y-6" data-testid="exely-integration">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900" data-testid="exely-page-title">Exely Entegrasyonu</h1>
            <p className="text-sm text-slate-500 mt-1">SOAP Channel Manager &middot; OTA Standart &middot; Rezervasyon Pull</p>
          </div>
          <Badge
            data-testid="exely-connection-badge"
            variant={isConnected ? 'default' : 'destructive'}
            className={isConnected ? 'bg-emerald-600' : ''}
          >
            {isConnected ? <><CheckCircle className="w-3 h-3 mr-1" /> Bagli</> : <><XCircle className="w-3 h-3 mr-1" /> Bagli Degil</>}
          </Badge>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid grid-cols-6 w-full max-w-3xl">
            <TabsTrigger value="connection" data-testid="exely-tab-connection"><Link2 className="w-4 h-4 mr-1" /> Baglanti</TabsTrigger>
            <TabsTrigger value="rooms" data-testid="exely-tab-rooms" disabled={!isConnected}><Building2 className="w-4 h-4 mr-1" /> Odalar</TabsTrigger>
            <TabsTrigger value="reservations" data-testid="exely-tab-reservations" disabled={!isConnected}><CalendarCheck className="w-4 h-4 mr-1" /> Rezervasyonlar</TabsTrigger>
            <TabsTrigger value="test-booking" data-testid="exely-tab-test-booking" disabled={!isConnected}><FlaskConical className="w-4 h-4 mr-1" /> Test Booking</TabsTrigger>
            <TabsTrigger value="mappings" data-testid="exely-tab-mappings" disabled={!isConnected}><ArrowDownUp className="w-4 h-4 mr-1" /> Eslemeler</TabsTrigger>
            <TabsTrigger value="logs" data-testid="exely-tab-logs" disabled={!isConnected}><Activity className="w-4 h-4 mr-1" /> Loglar</TabsTrigger>
          </TabsList>

          {/* Connection Tab */}
          <TabsContent value="connection" className="space-y-4 mt-4">
            {!isConnected ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Network className="w-5 h-5" /> Exely SOAP Baglantisi Kur</CardTitle>
                  <CardDescription>Exely channel manager WSSE kimlik bilgilerinizi girin</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="exely-user">Kullanici Adi</Label>
                      <Input id="exely-user" data-testid="exely-username-input" placeholder="Exely kullanici adi"
                        value={connectForm.username} onChange={e => setConnectForm(p => ({ ...p, username: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-pass">Sifre</Label>
                      <Input id="exely-pass" data-testid="exely-password-input" type="password" placeholder="Exely sifre"
                        value={connectForm.password} onChange={e => setConnectForm(p => ({ ...p, password: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-hotel">Otel Kodu</Label>
                      <Input id="exely-hotel" data-testid="exely-hotel-code-input" placeholder="Ornek: 12345"
                        value={connectForm.hotel_code} onChange={e => setConnectForm(p => ({ ...p, hotel_code: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-name">Tesis Adi (opsiyonel)</Label>
                      <Input id="exely-name" data-testid="exely-name-input" placeholder="Ornek: Otelim"
                        value={connectForm.property_name} onChange={e => setConnectForm(p => ({ ...p, property_name: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-url">Endpoint URL (opsiyonel)</Label>
                      <Input id="exely-url" data-testid="exely-url-input" placeholder="https://www.exely.com/ota/OTA"
                        value={connectForm.endpoint_url} onChange={e => setConnectForm(p => ({ ...p, endpoint_url: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="exely-currency">Para Birimi</Label>
                      <select id="exely-currency" data-testid="exely-currency-select"
                        value={connectForm.currency}
                        onChange={e => setConnectForm(p => ({ ...p, currency: e.target.value }))}
                        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
                        <option value="TRY">TRY - Turk Lirasi</option>
                        <option value="USD">USD - Amerikan Dolari</option>
                        <option value="EUR">EUR - Euro</option>
                        <option value="GBP">GBP - Ingiliz Sterlini</option>
                        <option value="RUB">RUB - Rus Rublesi</option>
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="exely-interval">Sync Araligi (dk)</Label>
                      <Input id="exely-interval" type="number" min={5} max={60}
                        value={connectForm.sync_interval_minutes} onChange={e => setConnectForm(p => ({ ...p, sync_interval_minutes: parseInt(e.target.value) || 15 }))} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 pt-2">
                    <Switch checked={connectForm.auto_sync_reservations}
                      onCheckedChange={v => setConnectForm(p => ({ ...p, auto_sync_reservations: v }))} />
                    <Label>Otomatik Rezervasyon Sync</Label>
                  </div>
                  <Button data-testid="exely-connect-btn" onClick={handleConnect} disabled={loading} className="w-full">
                    {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />}
                    Baglan
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><CheckCircle className="w-5 h-5 text-emerald-600" /> Exely Baglantisi Aktif</CardTitle>
                    <CardDescription>
                      {connection.connection?.property_name || 'Exely'} &middot; Otel Kodu: {connection.connection?.hotel_code || '-'} &middot;
                      Baglanti: {connection.connection?.connected_at ? new Date(connection.connection.connected_at).toLocaleString('tr-TR') : '-'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-3 items-center">
                      <Button data-testid="exely-test-btn" variant="outline" onClick={handleTest} disabled={loading}>
                        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                        Baglanti Test
                      </Button>
                      <Button data-testid="exely-disconnect-btn" variant="destructive" onClick={handleDisconnect}>
                        <Unlink className="w-4 h-4 mr-2" /> Baglantivi Kes
                      </Button>
                      <div className="flex items-center gap-2 ml-auto">
                        <Label className="text-sm text-slate-600 whitespace-nowrap">Para Birimi:</Label>
                        <select
                          data-testid="exely-currency-change"
                          value={connection.connection?.currency || 'TRY'}
                          onChange={async (e) => {
                            const newCurrency = e.target.value;
                            try {
                              await axios.patch(`${API}/api/channel-manager/exely/currency`, { currency: newCurrency }, { headers });
                              toast.success(`Para birimi ${newCurrency} olarak guncellendi`);
                              fetchConnection();
                            } catch (err) {
                              toast.error(err.response?.data?.detail || 'Para birimi guncellenemedi');
                            }
                          }}
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
                    {syncStatus && (
                      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">Toplam Rezervasyon</p>
                          <p className="text-lg font-bold" data-testid="exely-total-reservations">{syncStatus.total_reservations || 0}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">Bekleyen Event</p>
                          <p className="text-lg font-bold">{syncStatus.pending_events || 0}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">Hata Event</p>
                          <p className="text-lg font-bold text-red-600">{syncStatus.error_events || 0}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3 border">
                          <p className="text-xs text-slate-500">Scheduler</p>
                          <p className="text-lg font-bold">{syncStatus.scheduler_running ? 'Aktif' : 'Durdu'}</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Webhook section removed - using PULL mode only */}
              </div>
            )}
          </TabsContent>

          {/* Rooms Tab */}
          <TabsContent value="rooms" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Exely Oda Tipleri & Fiyat Planlari</CardTitle>
                  <CardDescription>OTA_HotelAvailRQ ile kesfedilen oda ve rate bilgileri</CardDescription>
                </div>
                <Button data-testid="exely-discover-btn" onClick={handleDiscover} disabled={loading}>
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
                  Kesfet
                </Button>
              </CardHeader>
              <CardContent className="space-y-6">
                {roomTypes.length === 0 && ratePlans.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">Henuz oda/rate kesfedilmedi. "Kesfet" butonu ile Exely'den yukleyin.</p>
                ) : (
                  <>
                    {roomTypes.length > 0 && (
                      <div>
                        <h3 className="text-sm font-semibold text-slate-700 mb-2">Oda Tipleri ({roomTypes.length})</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm" data-testid="exely-room-types-table">
                            <thead>
                              <tr className="border-b text-left text-slate-500">
                                <th className="pb-2 pr-4">Kod</th>
                                <th className="pb-2 pr-4">Oda Adi</th>
                                <th className="pb-2">Kapasite</th>
                              </tr>
                            </thead>
                            <tbody>
                              {roomTypes.map((rt, i) => (
                                <tr key={i} className="border-b last:border-0">
                                  <td className="py-2 pr-4 font-mono text-xs">{rt.code}</td>
                                  <td className="py-2 pr-4 font-medium">{rt.name}</td>
                                  <td className="py-2">{rt.quantity || '-'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {ratePlans.length > 0 && (
                      <div>
                        <h3 className="text-sm font-semibold text-slate-700 mb-2">Fiyat Planlari ({ratePlans.length})</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm" data-testid="exely-rate-plans-table">
                            <thead>
                              <tr className="border-b text-left text-slate-500">
                                <th className="pb-2 pr-4">Kod</th>
                                <th className="pb-2">Plan Adi</th>
                              </tr>
                            </thead>
                            <tbody>
                              {ratePlans.map((rp, i) => (
                                <tr key={i} className="border-b last:border-0">
                                  <td className="py-2 pr-4 font-mono text-xs">{rp.code}</td>
                                  <td className="py-2 font-medium">{rp.name || rp.code}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </>
                )}
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
                {reservations.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">Henuz rezervasyon yok. "Rezervasyonlari Cek" ile Exely'den aktarin.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="exely-reservations-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">Rez. ID</th>
                          <th className="pb-2 pr-4">Misafir</th>
                          <th className="pb-2 pr-4">Kanal</th>
                          <th className="pb-2 pr-4">Giris</th>
                          <th className="pb-2 pr-4">Cikis</th>
                          <th className="pb-2 pr-4">Tutar</th>
                          <th className="pb-2 pr-4">Durum</th>
                          <th className="pb-2">PMS</th>
                          <th className="pb-2">Islem</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reservations.map((res, i) => (
                          <tr key={i} className="border-b last:border-0">
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
                              {res.pms_status !== 'imported' && res.state === 'confirmed' ? (
                                <Button
                                  data-testid={`exely-import-btn-${i}`}
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs"
                                  onClick={() => handleImport(res.id || res.external_id)}
                                >
                                  <Download className="w-3 h-3 mr-1" /> PMS'e Aktar
                                </Button>
                              ) : res.pms_status === 'imported' ? (
                                <span className="text-xs text-emerald-600 font-medium">Aktarildi</span>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
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
            {mappingStatus && (
              <Card data-testid="exely-mapping-status">
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="text-sm">
                        <span className="font-medium">Esleme Durumu:</span>{' '}
                        <span className="text-emerald-600 font-bold">{mappingStatus.mapped_count}</span>
                        <span className="text-slate-400"> / {mappingStatus.total_pms_types} PMS oda tipi</span>
                      </div>
                      <div className="w-32 bg-slate-200 rounded-full h-2">
                        <div
                          className="h-2 rounded-full transition-all"
                          style={{
                            width: `${mappingStatus.completion_pct}%`,
                            backgroundColor: mappingStatus.completion_pct === 100 ? '#22c55e' : mappingStatus.completion_pct >= 50 ? '#f59e0b' : '#ef4444',
                          }}
                        />
                      </div>
                      <span className="text-xs text-slate-500">%{mappingStatus.completion_pct}</span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleAutoMapSuggest}
                      disabled={autoMapLoading}
                      data-testid="exely-auto-map-btn"
                    >
                      {autoMapLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Wand2 className="w-4 h-4 mr-1" />}
                      Otomatik Esle
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Oda Eslemeleri</CardTitle>
                  <CardDescription>PMS oda tipleri ile Exely oda/fiyat planlarini esleyin</CardDescription>
                </div>
                {!mappingStatus && (
                  <Button variant="outline" size="sm" onClick={handleAutoMapSuggest} disabled={autoMapLoading} data-testid="exely-auto-map-btn-alt">
                    {autoMapLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Wand2 className="w-4 h-4 mr-1" />}
                    Otomatik Esle
                  </Button>
                )}
              </CardHeader>
              <CardContent>
                {mappings.length === 0 ? (
                  <div className="text-center py-8">
                    <ArrowDownUp className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">Henuz oda eslemesi yok</p>
                    <p className="text-xs text-slate-400 mt-1">Odalar kesfedildikten sonra esleme yapilabilir</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="exely-mappings-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">PMS Oda Tipi</th>
                          <th className="pb-2 pr-4">Exely Oda Kodu</th>
                          <th className="pb-2 pr-4">Exely Rate Plan</th>
                          <th className="pb-2 pr-4">Exely Oda Adi</th>
                          <th className="pb-2 pr-4">Sync</th>
                          <th className="pb-2 text-right">Islem</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mappings.map((m, i) => (
                          <tr key={m.id || i} className="border-b last:border-0" data-testid={`exely-mapping-row-${i}`}>
                            <td className="py-2 pr-4 font-medium">{m.pms_room_type}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{m.exely_room_code}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{m.exely_rate_plan_code}</td>
                            <td className="py-2 pr-4">{m.exely_room_name}</td>
                            <td className="py-2 pr-4">
                              <div className="flex gap-1">
                                {m.sync_availability && <Badge variant="secondary" className="text-xs">A</Badge>}
                                {m.sync_price && <Badge variant="secondary" className="text-xs">R</Badge>}
                                {m.sync_restrictions && <Badge variant="secondary" className="text-xs">I</Badge>}
                              </div>
                            </td>
                            <td className="py-2 text-right">
                              <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-700 h-7 w-7 p-0" onClick={() => handleDeleteMapping(m.id)} data-testid={`exely-delete-mapping-${i}`}>
                                <Trash2 className="w-3.5 h-3.5" />
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Unmapped PMS Types Warning */}
                {mappingStatus && mappingStatus.unmapped_count > 0 && (
                  <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg" data-testid="exely-unmapped-warning">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-medium text-amber-800">{mappingStatus.unmapped_count} PMS oda tipi eslenmemis</p>
                        <p className="text-xs text-amber-600 mt-1">
                          Eslenmemis oda tipleri Exely'ye fiyat/musaitlik push edilemez. Provider'da karsilik gelen oda tipleri yoksa, Exely panelinden oda tipi olusturun.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Auto-Map Dialog */}
            <Dialog open={autoMapOpen} onOpenChange={setAutoMapOpen}>
              <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2"><Wand2 className="w-5 h-5" /> Otomatik Esleme Onerileri</DialogTitle>
                </DialogHeader>
                {autoMapSuggestions && (
                  <div className="space-y-4 mt-2">
                    {autoMapSuggestions.suggestions.length > 0 ? (
                      <>
                        <p className="text-sm text-slate-600">Isim benzerligine gore eslesme onerileri:</p>
                        <div className="space-y-2">
                          {autoMapSuggestions.suggestions.map((s, i) => (
                            <div key={i} className="flex items-center justify-between p-3 bg-slate-50 border rounded-lg" data-testid={`auto-map-suggestion-${i}`}>
                              <div className="flex items-center gap-3">
                                <div>
                                  <p className="font-medium text-sm">{s.pms_room_name}</p>
                                  <p className="text-xs text-slate-500">PMS ({s.pms_room_count} oda)</p>
                                </div>
                                <ArrowDownUp className="w-4 h-4 text-slate-400" />
                                <div>
                                  <p className="font-medium text-sm">{s.provider_room_name}</p>
                                  <p className="text-xs text-slate-500">Exely ({s.provider_room_code})</p>
                                </div>
                              </div>
                              <Badge className={s.confidence === 'high' ? 'bg-emerald-100 text-emerald-800' : s.confidence === 'medium' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'}>
                                %{Math.round(s.similarity_score * 100)}
                              </Badge>
                            </div>
                          ))}
                        </div>
                        <Button className="w-full" onClick={() => handleAutoMapApply(autoMapSuggestions.suggestions)} disabled={autoMapLoading} data-testid="auto-map-apply-btn">
                          {autoMapLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <CheckCircle className="w-4 h-4 mr-1" />}
                          Tum Onerileri Uygula ({autoMapSuggestions.suggestions.length})
                        </Button>
                      </>
                    ) : (
                      <div className="text-center py-4">
                        <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                        <p className="text-sm text-slate-600">Otomatik eslestirilecek yeni oda tipi bulunamadi.</p>
                      </div>
                    )}

                    {/* Unmapped PMS types */}
                    {autoMapSuggestions.unmapped_pms_types?.length > 0 && (
                      <div className="border-t pt-4">
                        <p className="text-sm font-medium text-amber-700 mb-2">Eslenmemis PMS Oda Tipleri (Provider'da karsiligi yok):</p>
                        <div className="flex flex-wrap gap-2">
                          {autoMapSuggestions.unmapped_pms_types.map((t, i) => (
                            <Badge key={i} variant="outline" className="bg-amber-50 border-amber-300 text-amber-700" data-testid={`unmapped-pms-${i}`}>
                              <AlertTriangle className="w-3 h-3 mr-1" /> {t.name} ({t.room_count} oda)
                            </Badge>
                          ))}
                        </div>
                        <p className="text-xs text-slate-500 mt-2">Bu oda tiplerini Exely panelinden olusturup tekrar esleme yapabilirsiniz.</p>
                      </div>
                    )}

                    {/* Unmapped provider rooms */}
                    {autoMapSuggestions.unmapped_provider_rooms?.length > 0 && (
                      <div className="border-t pt-4">
                        <p className="text-sm font-medium text-blue-700 mb-2">Eslenmemis Provider Odalari:</p>
                        <div className="flex flex-wrap gap-2">
                          {autoMapSuggestions.unmapped_provider_rooms.map((r, i) => (
                            <Badge key={i} variant="outline" className="bg-blue-50 border-blue-300 text-blue-700">
                              {r.name} ({r.code})
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </DialogContent>
            </Dialog>
          </TabsContent>

          {/* Logs Tab */}
          <TabsContent value="logs" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Senkronizasyon Loglari</CardTitle>
                  <CardDescription>Exely SOAP islem gecmisi</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={fetchAll}>
                  <RefreshCw className="w-4 h-4 mr-1" /> Yenile
                </Button>
              </CardHeader>
              <CardContent>
                {syncLogs.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">Henuz log kaydı yok</p>
                ) : (
                  <div className="space-y-2" data-testid="exely-sync-logs">
                    {syncLogs.map((log, i) => (
                      <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border">
                        <div className="flex items-center gap-3">
                          {log.status === 'success' ? (
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-red-500" />
                          )}
                          <div>
                            <p className="text-sm font-medium">{log.sync_type}</p>
                            <p className="text-xs text-slate-500">{log.initiator} &middot; {log.records_synced} kayit</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-slate-500">{new Date(log.timestamp).toLocaleString('tr-TR')}</p>
                          {log.duration_ms > 0 && <p className="text-xs text-slate-400">{log.duration_ms}ms</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default ExelyIntegration;
