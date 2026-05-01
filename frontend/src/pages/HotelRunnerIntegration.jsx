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
  Building2, ArrowDownUp, CalendarCheck, Clock, Activity,
  AlertTriangle, Loader2, Save, Trash2, Plus, Check, Wand2
} from 'lucide-react';

const API = "";

const HotelRunnerIntegration = ({ user, tenant, onLogout }) => {
  const [activeTab, setActiveTab] = useState('connection');
  const [loading, setLoading] = useState(false);
  const [connection, setConnection] = useState(null);
  const [rooms, setRooms] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [syncLogs, setSyncLogs] = useState([]);
  const [channels, setChannels] = useState([]);
  const [pmsRoomTypes, setPmsRoomTypes] = useState([]);
  const [mappingDraft, setMappingDraft] = useState({});
  const [savingMapping, setSavingMapping] = useState(null);
  const [newPmsType, setNewPmsType] = useState('');
  const [autoMapOpen, setAutoMapOpen] = useState(false);
  const [autoMapSuggestions, setAutoMapSuggestions] = useState(null);
  const [autoMapLoading, setAutoMapLoading] = useState(false);
  const [mappingStatus, setMappingStatus] = useState(null);

  const [connectForm, setConnectForm] = useState({
    token: '', hr_id: '', property_name: '',
    auto_sync_reservations: true, auto_confirm_delivery: false, sync_interval_minutes: 15,
  });

  const headers = { Authorization: `Bearer ${user?.token || user?.access_token}` };

  const fetchConnection = useCallback(async () => {
    try {
      const { data } = await axios.get(`/channel-manager/hotelrunner/connection`, { headers });
      setConnection(data);
    } catch { setConnection({ connected: false }); }
  }, []);

  const fetchAll = useCallback(async () => {
    if (!connection?.connected) return;
    try {
      const [roomsRes, mappingsRes, logsRes, localRes, pmsTypesRes, cachedRoomsRes] = await Promise.all([
        axios.get(`/channel-manager/hotelrunner/room-mappings`, { headers }).catch(() => ({ data: { mappings: [] } })),
        axios.get(`/channel-manager/hotelrunner/sync-logs?limit=20`, { headers }).catch(() => ({ data: { logs: [] } })),
        axios.get(`/channel-manager/hotelrunner/reservations/local`, { headers }).catch(() => ({ data: { reservations: [] } })),
        axios.get(`/channel-manager/hotelrunner/channels/connected`, { headers }).catch(() => ({ data: { channels: [] } })),
        axios.get(`/channel-manager/hotelrunner/pms-room-types`, { headers }).catch(() => ({ data: { room_types: [] } })),
        axios.get(`/channel-manager/hotelrunner/cached-rooms`, { headers }).catch(() => ({ data: { rooms: [] } })),
      ]);
      setMappings(roomsRes.data.mappings || []);
      setSyncLogs(logsRes.data.logs || []);
      setReservations(localRes.data.reservations || []);
      setChannels(mappingsRes.data.channels || []);
      setPmsRoomTypes(pmsTypesRes.data.room_types || []);
      if (cachedRoomsRes.data.rooms?.length > 0 && rooms.length === 0) {
        setRooms(cachedRoomsRes.data.rooms);
      }
    } catch (e) { console.error(e); }
  }, [connection?.connected]);

  useEffect(() => { fetchConnection(); }, [fetchConnection]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const fetchMappingStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`/channel-manager/auto-map/status/hotelrunner`, { headers });
      setMappingStatus(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (connection?.connected) fetchMappingStatus(); }, [connection?.connected]);

  const handleAutoMapSuggest = async () => {
    setAutoMapLoading(true);
    try {
      const { data } = await axios.post(`/channel-manager/auto-map/suggest`, { provider: 'hotelrunner' }, { headers });
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
        provider: 'hotelrunner',
        mappings: selectedSuggestions.map(s => ({
          pms_room_type: s.pms_room_type,
          provider_room_code: s.provider_room_code,
          provider_room_name: s.provider_room_name,
          provider_rate_plan_code: s.provider_rate_plan_code,
          provider_rate_plan_name: s.provider_rate_plan_name,
        })),
      };
      const { data } = await axios.post(`/channel-manager/auto-map/apply`, payload, { headers });
      toast.success(data.message);
      setAutoMapOpen(false);
      fetchAll();
      fetchMappingStatus();
    } catch (e) { toast.error(e.response?.data?.detail || 'Esleme uygulanamadi'); }
    finally { setAutoMapLoading(false); }
  };

  const handleConnect = async () => {
    if (!connectForm.token || !connectForm.hr_id) {
      toast.error('Token ve HR_ID zorunludur');
      return;
    }
    setLoading(true);
    try {
      const { data } = await axios.post(`/channel-manager/hotelrunner/connect`, connectForm, { headers });
      toast.success(data.message);
      setConnection({ connected: true, connection: data });
      fetchConnection();
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Bağlantı hatası');
    } finally { setLoading(false); }
  };

  const handleDisconnect = async () => {
    try {
      await axios.delete(`/channel-manager/hotelrunner/disconnect`, { headers });
      toast.success('Bağlantı kesildi');
      setConnection({ connected: false });
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleTestConnection = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`/channel-manager/hotelrunner/test`, {}, { headers });
      if (data.connected) toast.success(`Bağlantı basarili (${data.duration_ms}ms)`);
      else toast.error(`Bağlantı hatası: ${data.error}`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Test hatası'); }
    finally { setLoading(false); }
  };

  const handleFetchRooms = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`/channel-manager/hotelrunner/rooms`, { headers });
      setRooms(data.rooms || []);
      toast.success(`${data.count} oda/fiyat plani yüklendi`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Oda listesi alinamadi'); }
    finally { setLoading(false); }
  };

  const handleSyncReservations = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`/channel-manager/hotelrunner/reservations/sync`, {}, { headers });
      toast.success(data.message);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Senkronizasyon hatası'); }
    finally { setLoading(false); }
  };

  const handleSaveMapping = async (room) => {
    const key = room.inv_code;
    const draft = mappingDraft[key];
    const pmsType = draft?.pms_room_type;
    if (!pmsType) {
      toast.error('Lutfen bir PMS oda tipi seçin');
      return;
    }
    setSavingMapping(key);
    try {
      await axios.post(`/channel-manager/hotelrunner/room-mappings`, {
        pms_room_type: pmsType,
        hr_inv_code: room.inv_code,
        hr_rate_code: room.rate_code,
        hr_room_name: room.name,
        sync_availability: draft?.sync_availability ?? true,
        sync_price: draft?.sync_price ?? true,
        sync_restrictions: draft?.sync_restrictions ?? true,
      }, { headers });
      toast.success(`${room.name} → ${pmsType} eslendi`);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Esleme hatası'); }
    finally { setSavingMapping(null); }
  };

  const handleDeleteMapping = async (mappingId) => {
    try {
      await axios.delete(`/channel-manager/hotelrunner/room-mappings/${mappingId}`, { headers });
      toast.success('Esleme silindi');
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Silme hatası'); }
  };

  const handleSaveAllMappings = async () => {
    const toSave = rooms.filter(r => {
      const d = mappingDraft[r.inv_code];
      return d?.pms_room_type;
    });
    if (toSave.length === 0) {
      toast.error('Kaydedilecek esleme yok. Her oda için PMS tipi seçin.');
      return;
    }
    setLoading(true);
    try {
      const payload = toSave.map(r => {
        const d = mappingDraft[r.inv_code];
        return {
          pms_room_type: d.pms_room_type,
          hr_inv_code: r.inv_code,
          hr_rate_code: r.rate_code,
          hr_room_name: r.name,
          sync_availability: d.sync_availability ?? true,
          sync_price: d.sync_price ?? true,
          sync_restrictions: d.sync_restrictions ?? true,
        };
      });
      const { data } = await axios.post(`/channel-manager/hotelrunner/room-mappings/bulk`, payload, { headers });
      toast.success(data.message);
      fetchAll();
    } catch (e) { toast.error(e.response?.data?.detail || 'Toplu esleme hatası'); }
    finally { setLoading(false); }
  };

  const updateDraft = (invCode, field, value) => {
    setMappingDraft(prev => ({
      ...prev,
      [invCode]: { ...prev[invCode], [field]: value },
    }));
  };

  const getMappingForRoom = (invCode, rateCode) =>
    mappings.find(m => m.hr_inv_code === invCode && m.hr_rate_code === rateCode);

  const allRoomTypes = [...new Set([
    ...pmsRoomTypes,
    ...mappings.map(m => m.pms_room_type),
  ])].filter(Boolean);

  useEffect(() => {
    if (mappings.length > 0 && rooms.length > 0) {
      const initial = {};
      for (const room of rooms) {
        const m = getMappingForRoom(room.inv_code, room.rate_code);
        if (m) {
          initial[room.inv_code] = {
            pms_room_type: m.pms_room_type,
            sync_availability: m.sync_availability,
            sync_price: m.sync_price,
            sync_restrictions: m.sync_restrictions,
          };
        }
      }
      setMappingDraft(prev => ({ ...initial, ...prev }));
    }
  }, [mappings, rooms]);

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
            <TabsTrigger value="connection" data-testid="tab-connection"><Link2 className="w-4 h-4 mr-1" /> Bağlantı</TabsTrigger>
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
                    <CardTitle className="flex items-center gap-2"><CheckCircle className="w-5 h-5 text-emerald-600" /> Bağlantı Aktif</CardTitle>
                    <CardDescription>
                      {connection.connection?.property_name || 'HotelRunner'} &middot;
                      Bağlantı: {connection.connection?.connected_at ? new Date(connection.connection.connected_at).toLocaleString('tr-TR') : '-'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-3">
                      <Button data-testid="hr-test-btn" variant="outline" onClick={handleTestConnection} disabled={loading}>
                        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                        Bağlantı Test
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
                  <p className="text-sm text-slate-500 text-center py-8">Henüz oda verisi yok. "Odalari Cek" ile HotelRunner'dan yukleyin.</p>
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
                  <p className="text-sm text-slate-500 text-center py-8">Henüz rezervasyon yok. "Senkronize Et" ile HotelRunner'dan cekin.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="hr-reservations-table">
                      <thead>
                        <tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">HR No</th>
                          <th className="pb-2 pr-4">Misafir</th>
                          <th className="pb-2 pr-4">Kanal</th>
                          <th className="pb-2 pr-4">Giriş</th>
                          <th className="pb-2 pr-4">Çıkış</th>
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
            {/* Mapping Status Bar */}
            {mappingStatus && (
              <Card data-testid="hr-mapping-status">
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
                    <Button variant="outline" size="sm" onClick={handleAutoMapSuggest} disabled={autoMapLoading} data-testid="hr-auto-map-btn">
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
                  <CardDescription>HotelRunner oda tiplerini PMS oda tiplerinizle eslestirin</CardDescription>
                </div>
                <div className="flex gap-2">
                  {rooms.length > 0 && (
                    <Button
                      data-testid="hr-save-all-mappings-btn"
                      onClick={handleSaveAllMappings}
                      disabled={loading}
                    >
                      {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                      Tüm Eslemeleri Kaydet
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {rooms.length === 0 ? (
                  <div className="text-center py-8">
                    <ArrowDownUp className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">Henüz HotelRunner odasi cekilmedi</p>
                    <p className="text-xs text-slate-400 mt-1">Oncelikle "Odalar" sekmesinden odalari cekin</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-4"
                      onClick={() => { setActiveTab('rooms'); }}
                    >
                      <Building2 className="w-4 h-4 mr-1" /> Odalar Sekmesine Git
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* New PMS type input */}
                    <div className="flex items-end gap-2 p-3 bg-slate-50 rounded-lg border border-dashed">
                      <div className="flex-1">
                        <Label className="text-xs text-slate-500">Yeni PMS Oda Tipi Ekle</Label>
                        <Input
                          data-testid="new-pms-type-input"
                          placeholder="Ornek: Deluxe Oda, Suite, Standart..."
                          value={newPmsType}
                          onChange={e => setNewPmsType(e.target.value)}
                          className="mt-1"
                        />
                      </div>
                      <Button
                        data-testid="add-pms-type-btn"
                        variant="outline"
                        size="sm"
                        disabled={!newPmsType.trim()}
                        onClick={() => {
                          const val = newPmsType.trim();
                          if (val && !allRoomTypes.includes(val)) {
                            setPmsRoomTypes(prev => [...prev, val]);
                            toast.success(`"${val}" PMS oda tipi eklendi`);
                          }
                          setNewPmsType('');
                        }}
                      >
                        <Plus className="w-4 h-4 mr-1" /> Ekle
                      </Button>
                    </div>

                    {/* Mapping table */}
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm" data-testid="hr-mapping-table">
                        <thead>
                          <tr className="border-b text-left text-slate-500">
                            <th className="pb-2 pr-3">HR Oda Adi</th>
                            <th className="pb-2 pr-3">Inv / Rate Code</th>
                            <th className="pb-2 pr-3 min-w-[200px]">PMS Oda Tipi</th>
                            <th className="pb-2 pr-2 text-center">Musaitlik</th>
                            <th className="pb-2 pr-2 text-center">Fiyat</th>
                            <th className="pb-2 pr-2 text-center">Kisitlama</th>
                            <th className="pb-2 text-center">İşlem</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rooms.map((room) => {
                            const existingMapping = getMappingForRoom(room.inv_code, room.rate_code);
                            const draft = mappingDraft[room.inv_code] || {};
                            const isMapped = !!existingMapping;

                            return (
                              <tr
                                key={room.inv_code}
                                className={`border-b last:border-0 ${isMapped ? 'bg-emerald-50/50' : ''}`}
                                data-testid={`mapping-row-${room.inv_code}`}
                              >
                                <td className="py-3 pr-3">
                                  <div className="font-medium">{room.name}</div>
                                  <div className="text-xs text-slate-400">{room.pricing_type} &middot; {room.adult_capacity}A/{room.room_capacity}T</div>
                                </td>
                                <td className="py-3 pr-3">
                                  <div className="font-mono text-xs">{room.inv_code}</div>
                                  <div className="font-mono text-xs text-slate-400">{room.rate_code}</div>
                                </td>
                                <td className="py-3 pr-3">
                                  <select
                                    data-testid={`pms-type-select-${room.inv_code}`}
                                    className="w-full border rounded-md px-2 py-1.5 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                    value={draft.pms_room_type || ''}
                                    onChange={e => updateDraft(room.inv_code, 'pms_room_type', e.target.value)}
                                  >
                                    <option value="">-- PMS Tipi Sec --</option>
                                    {allRoomTypes.map(t => (
                                      <option key={t} value={t}>{t}</option>
                                    ))}
                                  </select>
                                </td>
                                <td className="py-3 pr-2 text-center">
                                  <Switch
                                    data-testid={`sync-avail-${room.inv_code}`}
                                    checked={draft.sync_availability ?? true}
                                    onCheckedChange={v => updateDraft(room.inv_code, 'sync_availability', v)}
                                  />
                                </td>
                                <td className="py-3 pr-2 text-center">
                                  <Switch
                                    data-testid={`sync-price-${room.inv_code}`}
                                    checked={draft.sync_price ?? true}
                                    onCheckedChange={v => updateDraft(room.inv_code, 'sync_price', v)}
                                  />
                                </td>
                                <td className="py-3 pr-2 text-center">
                                  <Switch
                                    data-testid={`sync-restrict-${room.inv_code}`}
                                    checked={draft.sync_restrictions ?? true}
                                    onCheckedChange={v => updateDraft(room.inv_code, 'sync_restrictions', v)}
                                  />
                                </td>
                                <td className="py-3 text-center">
                                  <div className="flex items-center justify-center gap-1">
                                    {isMapped ? (
                                      <>
                                        <Badge className="bg-emerald-600 text-xs gap-1" data-testid={`mapped-badge-${room.inv_code}`}>
                                          <Check className="w-3 h-3" /> Eslendi
                                        </Badge>
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          className="h-7 w-7 p-0 text-red-500 hover:text-red-700"
                                          data-testid={`delete-mapping-${room.inv_code}`}
                                          onClick={() => handleDeleteMapping(existingMapping.id)}
                                        >
                                          <Trash2 className="w-3.5 h-3.5" />
                                        </Button>
                                      </>
                                    ) : (
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        disabled={!draft.pms_room_type || savingMapping === room.inv_code}
                                        data-testid={`save-mapping-${room.inv_code}`}
                                        onClick={() => handleSaveMapping(room)}
                                      >
                                        {savingMapping === room.inv_code
                                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                          : <Save className="w-3.5 h-3.5 mr-1" />}
                                        Kaydet
                                      </Button>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    {/* Summary */}
                    <div className="flex items-center justify-between pt-2 border-t text-sm text-slate-500">
                      <span>{rooms.length} HR oda, {mappings.length} eşleme yapıldı</span>
                      {mappings.length > 0 && rooms.length > mappings.length && (
                        <Badge variant="outline" className="text-amber-600 border-amber-300">
                          <AlertTriangle className="w-3 h-3 mr-1" />
                          {rooms.length - mappings.length} oda henüz eslenmedi
                        </Badge>
                      )}
                      {mappings.length > 0 && mappings.length >= rooms.length && (
                        <Badge className="bg-emerald-600">
                          <CheckCircle className="w-3 h-3 mr-1" /> Tüm odalar eslendi
                        </Badge>
                      )}
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
                        <p className="text-sm text-slate-600">Isim benzerligine göre eslesme onerileri:</p>
                        <div className="space-y-2">
                          {autoMapSuggestions.suggestions.map((s, i) => (
                            <div key={i} className="flex items-center justify-between p-3 bg-slate-50 border rounded-lg" data-testid={`hr-auto-map-suggestion-${i}`}>
                              <div className="flex items-center gap-3">
                                <div>
                                  <p className="font-medium text-sm">{s.pms_room_name}</p>
                                  <p className="text-xs text-slate-500">PMS ({s.pms_room_count} oda)</p>
                                </div>
                                <ArrowDownUp className="w-4 h-4 text-slate-400" />
                                <div>
                                  <p className="font-medium text-sm">{s.provider_room_name}</p>
                                  <p className="text-xs text-slate-500">HotelRunner ({s.provider_room_code})</p>
                                </div>
                              </div>
                              <Badge className={s.confidence === 'high' ? 'bg-emerald-100 text-emerald-800' : s.confidence === 'medium' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'}>
                                %{Math.round(s.similarity_score * 100)}
                              </Badge>
                            </div>
                          ))}
                        </div>
                        <Button className="w-full" onClick={() => handleAutoMapApply(autoMapSuggestions.suggestions)} disabled={autoMapLoading} data-testid="hr-auto-map-apply-btn">
                          {autoMapLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <CheckCircle className="w-4 h-4 mr-1" />}
                          Tüm Onerileri Uygula ({autoMapSuggestions.suggestions.length})
                        </Button>
                      </>
                    ) : (
                      <div className="text-center py-4">
                        <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                        <p className="text-sm text-slate-600">Otomatik eşleştirilecek yeni oda tipi bulunamadı.</p>
                      </div>
                    )}

                    {autoMapSuggestions.unmapped_pms_types?.length > 0 && (
                      <div className="border-t pt-4">
                        <p className="text-sm font-medium text-amber-700 mb-2">Eslenmemis PMS Oda Tipleri (Provider'da karsiligi yok):</p>
                        <div className="flex flex-wrap gap-2">
                          {autoMapSuggestions.unmapped_pms_types.map((t, i) => (
                            <Badge key={i} variant="outline" className="bg-amber-50 border-amber-300 text-amber-700" data-testid={`hr-unmapped-pms-${i}`}>
                              <AlertTriangle className="w-3 h-3 mr-1" /> {t.name} ({t.room_count} oda)
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

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
                  <CardDescription>HotelRunner API işlem geçmişi</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={fetchAll}>
                  <RefreshCw className="w-4 h-4 mr-1" /> Yenile
                </Button>
              </CardHeader>
              <CardContent>
                {syncLogs.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">Henüz log kaydı yok</p>
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
                            <p className="text-xs text-slate-500">{log.initiator} &middot; {log.records_synced} kayıt</p>
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
