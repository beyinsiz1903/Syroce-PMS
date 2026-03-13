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
import {
  Network, CheckCircle, XCircle, RefreshCw, Link2, Unlink,
  Building2, ArrowDownUp, CalendarCheck, Clock, Activity,
  AlertTriangle, Loader2
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const HotelRunnerIntegration = ({ user, tenant, onLogout }) => {
  const [activeTab, setActiveTab] = useState('connection');
  const [loading, setLoading] = useState(false);
  const [connection, setConnection] = useState(null);
  const [rooms, setRooms] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [syncLogs, setSyncLogs] = useState([]);
  const [channels, setChannels] = useState([]);

  const [connectForm, setConnectForm] = useState({
    token: '', hr_id: '', property_name: '',
    auto_sync_reservations: true, auto_confirm_delivery: false, sync_interval_minutes: 15,
  });

  const headers = { Authorization: `Bearer ${user?.token || user?.access_token}` };

  const fetchConnection = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/channel-manager/hotelrunner/connection`, { headers });
      setConnection(data);
    } catch { setConnection({ connected: false }); }
  }, []);

  const fetchAll = useCallback(async () => {
    if (!connection?.connected) return;
    try {
      const [roomsRes, mappingsRes, logsRes, localRes] = await Promise.all([
        axios.get(`${API}/api/channel-manager/hotelrunner/room-mappings`, { headers }).catch(() => ({ data: { mappings: [] } })),
        axios.get(`${API}/api/channel-manager/hotelrunner/sync-logs?limit=20`, { headers }).catch(() => ({ data: { logs: [] } })),
        axios.get(`${API}/api/channel-manager/hotelrunner/reservations/local`, { headers }).catch(() => ({ data: { reservations: [] } })),
        axios.get(`${API}/api/channel-manager/hotelrunner/channels/connected`, { headers }).catch(() => ({ data: { channels: [] } })),
      ]);
      setMappings(roomsRes.data.mappings || []);
      setSyncLogs(logsRes.data.logs || []);
      setReservations(localRes.data.reservations || []);
      setChannels(mappingsRes.data.channels || []);
    } catch (e) { console.error(e); }
  }, [connection?.connected]);

  useEffect(() => { fetchConnection(); }, [fetchConnection]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleConnect = async () => {
    if (!connectForm.token || !connectForm.hr_id) {
      toast.error('Token ve HR_ID zorunludur');
      return;
    }
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/hotelrunner/connect`, connectForm, { headers });
      toast.success(data.message);
      setConnection({ connected: true, connection: data });
      fetchConnection();
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Baglanti hatasi');
    } finally { setLoading(false); }
  };

  const handleDisconnect = async () => {
    try {
      await axios.delete(`${API}/api/channel-manager/hotelrunner/disconnect`, { headers });
      toast.success('Baglanti kesildi');
      setConnection({ connected: false });
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleTestConnection = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/hotelrunner/test`, {}, { headers });
      if (data.connected) toast.success(`Baglanti basarili (${data.duration_ms}ms)`);
      else toast.error(`Baglanti hatasi: ${data.error}`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Test hatasi'); }
    finally { setLoading(false); }
  };

  const handleFetchRooms = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/api/channel-manager/hotelrunner/rooms`, { headers });
      setRooms(data.rooms || []);
      toast.success(`${data.count} oda/fiyat plani yuklendi`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Oda listesi alinamadi'); }
    finally { setLoading(false); }
  };

  const handleSyncReservations = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/hotelrunner/reservations/sync`, {}, { headers });
      toast.success(data.message);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Senkronizasyon hatasi'); }
    finally { setLoading(false); }
  };

  const isConnected = connection?.connected;

  return (
    <Layout user={user} onLogout={onLogout} tenant={tenant}>
      <div className="p-4 md:p-6 space-y-6" data-testid="hotelrunner-integration">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">HotelRunner Entegrasyonu</h1>
            <p className="text-sm text-slate-500 mt-1">Channel Manager &middot; ARI Push &middot; Rezervasyon Sync</p>
          </div>
          <Badge
            data-testid="hr-connection-badge"
            variant={isConnected ? 'default' : 'destructive'}
            className={isConnected ? 'bg-emerald-600' : ''}
          >
            {isConnected ? <><CheckCircle className="w-3 h-3 mr-1" /> Bagli</> : <><XCircle className="w-3 h-3 mr-1" /> Bagli Degil</>}
          </Badge>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid grid-cols-5 w-full max-w-2xl">
            <TabsTrigger value="connection" data-testid="tab-connection"><Link2 className="w-4 h-4 mr-1" /> Baglanti</TabsTrigger>
            <TabsTrigger value="rooms" data-testid="tab-rooms" disabled={!isConnected}><Building2 className="w-4 h-4 mr-1" /> Odalar</TabsTrigger>
            <TabsTrigger value="reservations" data-testid="tab-reservations" disabled={!isConnected}><CalendarCheck className="w-4 h-4 mr-1" /> Rezervasyonlar</TabsTrigger>
            <TabsTrigger value="mappings" data-testid="tab-mappings" disabled={!isConnected}><ArrowDownUp className="w-4 h-4 mr-1" /> Eslemeler</TabsTrigger>
            <TabsTrigger value="logs" data-testid="tab-logs" disabled={!isConnected}><Activity className="w-4 h-4 mr-1" /> Loglar</TabsTrigger>
          </TabsList>

          {/* Connection Tab */}
          <TabsContent value="connection" className="space-y-4 mt-4">
            {!isConnected ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Network className="w-5 h-5" /> HotelRunner Baglantisi Kur</CardTitle>
                  <CardDescription>HotelRunner Custom App bilgilerinizi girin</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="hr-token">API Token</Label>
                      <Input id="hr-token" data-testid="hr-token-input" type="password" placeholder="HotelRunner Token"
                        value={connectForm.token} onChange={e => setConnectForm(p => ({ ...p, token: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="hr-id">HR_ID (Property ID)</Label>
                      <Input id="hr-id" data-testid="hr-id-input" placeholder="HotelRunner Property ID"
                        value={connectForm.hr_id} onChange={e => setConnectForm(p => ({ ...p, hr_id: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="hr-name">Tesis Adi (opsiyonel)</Label>
                      <Input id="hr-name" data-testid="hr-name-input" placeholder="Ornek: Syroce Test Hotel"
                        value={connectForm.property_name} onChange={e => setConnectForm(p => ({ ...p, property_name: e.target.value }))} />
                    </div>
                    <div>
                      <Label htmlFor="hr-interval">Sync Araligi (dk)</Label>
                      <Input id="hr-interval" type="number" min={5} max={60}
                        value={connectForm.sync_interval_minutes} onChange={e => setConnectForm(p => ({ ...p, sync_interval_minutes: parseInt(e.target.value) || 15 }))} />
                    </div>
                  </div>
                  <div className="flex items-center gap-6 pt-2">
                    <div className="flex items-center gap-2">
                      <Switch checked={connectForm.auto_sync_reservations}
                        onCheckedChange={v => setConnectForm(p => ({ ...p, auto_sync_reservations: v }))} />
                      <Label>Otomatik Rezervasyon Sync</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch checked={connectForm.auto_confirm_delivery}
                        onCheckedChange={v => setConnectForm(p => ({ ...p, auto_confirm_delivery: v }))} />
                      <Label>Otomatik Teslimat Onayi</Label>
                    </div>
                  </div>
                  <Button data-testid="hr-connect-btn" onClick={handleConnect} disabled={loading} className="w-full">
                    {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />}
                    Baglan
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><CheckCircle className="w-5 h-5 text-emerald-600" /> Baglanti Aktif</CardTitle>
                    <CardDescription>
                      {connection.connection?.property_name || 'HotelRunner'} &middot;
                      Baglanti: {connection.connection?.connected_at ? new Date(connection.connection.connected_at).toLocaleString('tr-TR') : '-'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-3">
                      <Button data-testid="hr-test-btn" variant="outline" onClick={handleTestConnection} disabled={loading}>
                        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                        Baglanti Test
                      </Button>
                      <Button data-testid="hr-disconnect-btn" variant="destructive" onClick={handleDisconnect}>
                        <Unlink className="w-4 h-4 mr-2" /> Baglantivi Kes
                      </Button>
                    </div>
                    {channels.length > 0 && (
                      <div className="mt-4">
                        <p className="text-sm font-medium text-slate-700 mb-2">Bagli Kanallar:</p>
                        <div className="flex flex-wrap gap-2">
                          {channels.map((ch, i) => (
                            <Badge key={i} variant="secondary">{ch.name || ch.code}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>

          {/* Rooms Tab */}
          <TabsContent value="rooms" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>HotelRunner Odalari</CardTitle>
                  <CardDescription>Tesisinize ait oda tipleri ve fiyat planlari</CardDescription>
                </div>
                <Button data-testid="hr-fetch-rooms-btn" onClick={handleFetchRooms} disabled={loading}>
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                  Odalari Cek
                </Button>
              </CardHeader>
              <CardContent>
                {rooms.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">Henuz oda verisi yok. "Odalari Cek" ile HotelRunner'dan yukleyin.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="hr-rooms-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">Oda Adi</th>
                          <th className="pb-2 pr-4">Rate Code</th>
                          <th className="pb-2 pr-4">Inv Code</th>
                          <th className="pb-2 pr-4">Kapasite</th>
                          <th className="pb-2 pr-4">Fiyat Tipi</th>
                          <th className="pb-2 pr-4">Kanallar</th>
                          <th className="pb-2">Durum</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rooms.map((room, i) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-2 pr-4 font-medium">{room.name}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{room.rate_code}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{room.inv_code}</td>
                            <td className="py-2 pr-4">{room.adult_capacity}A / {room.room_capacity}T</td>
                            <td className="py-2 pr-4"><Badge variant="outline">{room.pricing_type}</Badge></td>
                            <td className="py-2 pr-4">
                              <div className="flex flex-wrap gap-1">
                                {(room.channel_codes || []).slice(0, 3).map((ch, j) => (
                                  <Badge key={j} variant="secondary" className="text-xs">{ch}</Badge>
                                ))}
                                {(room.channel_codes || []).length > 3 && <Badge variant="secondary" className="text-xs">+{room.channel_codes.length - 3}</Badge>}
                              </div>
                            </td>
                            <td className="py-2">
                              {room.sell_online ? <Badge className="bg-emerald-600">Aktif</Badge> : <Badge variant="destructive">Pasif</Badge>}
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

          {/* Reservations Tab */}
          <TabsContent value="reservations" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>HotelRunner Rezervasyonlari</CardTitle>
                  <CardDescription>OTA kanallarindan gelen rezervasyonlar</CardDescription>
                </div>
                <Button data-testid="hr-sync-reservations-btn" onClick={handleSyncReservations} disabled={loading}>
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                  Senkronize Et
                </Button>
              </CardHeader>
              <CardContent>
                {reservations.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">Henuz rezervasyon yok. "Senkronize Et" ile HotelRunner'dan cekin.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="hr-reservations-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">HR No</th>
                          <th className="pb-2 pr-4">Misafir</th>
                          <th className="pb-2 pr-4">Kanal</th>
                          <th className="pb-2 pr-4">Giris</th>
                          <th className="pb-2 pr-4">Cikis</th>
                          <th className="pb-2 pr-4">Tutar</th>
                          <th className="pb-2 pr-4">Durum</th>
                          <th className="pb-2">PMS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reservations.map((res, i) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-2 pr-4 font-mono text-xs">{res.hr_number}</td>
                            <td className="py-2 pr-4 font-medium">{res.guest_name}</td>
                            <td className="py-2 pr-4"><Badge variant="outline">{res.channel_display || res.channel}</Badge></td>
                            <td className="py-2 pr-4">{res.checkin_date}</td>
                            <td className="py-2 pr-4">{res.checkout_date}</td>
                            <td className="py-2 pr-4 font-medium">{res.total} {res.currency}</td>
                            <td className="py-2 pr-4">
                              <Badge className={res.state === 'confirmed' ? 'bg-emerald-600' : res.state === 'canceled' ? 'bg-red-600' : 'bg-amber-500'}>
                                {res.state}
                              </Badge>
                            </td>
                            <td className="py-2">
                              <Badge variant={res.pms_status === 'imported' ? 'default' : 'secondary'}>
                                {res.pms_status || 'pending'}
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
          </TabsContent>

          {/* Mappings Tab */}
          <TabsContent value="mappings" className="space-y-4 mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Oda Eslemeleri</CardTitle>
                <CardDescription>PMS oda tipleri ile HotelRunner oda/fiyat planlarini esleyin</CardDescription>
              </CardHeader>
              <CardContent>
                {mappings.length === 0 ? (
                  <div className="text-center py-8">
                    <ArrowDownUp className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">Henuz oda eslemesi yok</p>
                    <p className="text-xs text-slate-400 mt-1">Credential'lar geldiginde odalar cekilip eslenecek</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="hr-mappings-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">PMS Oda Tipi</th>
                          <th className="pb-2 pr-4">HR Inv Code</th>
                          <th className="pb-2 pr-4">HR Rate Code</th>
                          <th className="pb-2 pr-4">HR Oda Adi</th>
                          <th className="pb-2">Sync</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mappings.map((m, i) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-2 pr-4 font-medium">{m.pms_room_type}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{m.hr_inv_code}</td>
                            <td className="py-2 pr-4 font-mono text-xs">{m.hr_rate_code}</td>
                            <td className="py-2 pr-4">{m.hr_room_name}</td>
                            <td className="py-2">
                              <div className="flex gap-1">
                                {m.sync_availability && <Badge variant="secondary" className="text-xs">A</Badge>}
                                {m.sync_price && <Badge variant="secondary" className="text-xs">R</Badge>}
                                {m.sync_restrictions && <Badge variant="secondary" className="text-xs">I</Badge>}
                              </div>
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

          {/* Logs Tab */}
          <TabsContent value="logs" className="space-y-4 mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Senkronizasyon Loglari</CardTitle>
                  <CardDescription>HotelRunner API islem gecmisi</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={fetchAll}>
                  <RefreshCw className="w-4 h-4 mr-1" /> Yenile
                </Button>
              </CardHeader>
              <CardContent>
                {syncLogs.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">Henuz log kaydı yok</p>
                ) : (
                  <div className="space-y-2" data-testid="hr-sync-logs">
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

export default HotelRunnerIntegration;
