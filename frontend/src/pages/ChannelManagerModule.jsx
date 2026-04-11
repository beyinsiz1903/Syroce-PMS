import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { 
  Network, 
  Plus, 
  Download, 
  AlertTriangle, 
  CheckCircle, 
  Clock,
  XCircle,
  RefreshCw,
  Settings
} from 'lucide-react';

const ChannelManagerModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('connections');
  
  // Connections state
  const [connections, setConnections] = useState([]);
  const [showAddConnection, setShowAddConnection] = useState(false);
  const [newConnection, setNewConnection] = useState({
    channel_type: 'booking_com',
    channel_name: '',
    property_id: '',
    api_endpoint: '',
    api_key: '',
    api_secret: '',
    sync_rate_availability: true,
    sync_reservations: true
  });
  
  // Room mappings state
  const [roomMappings, setRoomMappings] = useState([]);
  const [mappingFilterChannel, setMappingFilterChannel] = useState('all');

  // Rate & Availability form state
  const [rateRoomType, setRateRoomType] = useState('');
  const [rateDateFrom, setRateDateFrom] = useState('');
  const [rateDateTo, setRateDateTo] = useState('');
  const [baseRate, setBaseRate] = useState('');
  const [discountPct, setDiscountPct] = useState('');

  const finalRate = useMemo(() => {
    const base = parseFloat(baseRate);
    const disc = parseFloat(discountPct);
    if (Number.isNaN(base)) return '';
    const pct = Number.isNaN(disc) ? 0 : disc;
    const final = base * (1 - pct / 100);
    return final > 0 ? final.toFixed(2) : '';
  }, [baseRate, discountPct]);
  const [channelSelection, setChannelSelection] = useState({
    all: true,
    booking_com: false,
    expedia: false,
    airbnb: false,
  });

  // Sync history state
  const [syncLogs, setSyncLogs] = useState([]);
  const [syncSummary, setSyncSummary] = useState(null);

  const getChannelLabel = (channel) => {
    switch (channel) {
      case 'booking_com':
        return 'Booking.com';
      case 'expedia':
        return 'Expedia';
      case 'airbnb':
        return 'Airbnb';
      case 'direct':
        return 'Direct Website';
      default:
        return channel || '-';
    }
  };

  // Rate parity state
  const [parityInfo, setParityInfo] = useState(null);

  // OTA Reservations state
  const [otaReservations, setOtaReservations] = useState([]);
  const [reservationFilter, setReservationFilter] = useState('pending');
  
  // Exceptions state
  const [exceptions, setExceptions] = useState([]);
  const [showAddMapping, setShowAddMapping] = useState(false);
  const [pmsRoomTypes, setPmsRoomTypes] = useState([]);
  const [newMapping, setNewMapping] = useState({
    channel_id: '',
    pms_room_type: '',
    channel_room_type: '',
    channel_room_id: ''
  });

  const [exceptionFilter, setExceptionFilter] = useState('all');
  
  const [loading, setLoading] = useState(false);

  const loadConnections = async () => {
    try {
      const response = await axios.get('/channel-manager/connections');
      // Backend returns { connections, count }
      const data = response.data;
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data.connections)
          ? data.connections
          : [];
      setConnections(list);
    } catch (error) {
      console.error('Failed to load connections:', error);
      setConnections([]);
    }
  };

  const loadRoomMappings = async () => {
    try {
      const response = await axios.get('/channel-manager/room-mappings');
      const data = response.data;
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data.mappings)
          ? data.mappings
          : [];
      setRoomMappings(list);
    } catch (error) {
      console.error('Failed to load room mappings:', error);
      setRoomMappings([]);
    }
  };

  const loadPmsRoomTypes = async () => {
    try {
      const response = await axios.get('/pms/rooms');
      const data = Array.isArray(response.data) ? response.data : [];
      // Unique room_type list
      const types = Array.from(
        new Set(data.map((room) => room.room_type).filter(Boolean))
      );
      setPmsRoomTypes(types);
    } catch (error) {
      console.error('Failed to load PMS rooms:', error);
      setPmsRoomTypes([]);
    }
  };

  useEffect(() => {
    loadConnections();
    loadRoomMappings();
    loadPmsRoomTypes();
    loadOtaReservations();
    loadExceptions();
    loadSyncHistory();
    loadRateParity();
  }, []);

  const loadOtaReservations = async () => {
    try {
      const response = await axios.get(`/channel-manager/ota-reservations?status=${reservationFilter}`);
      const data = response.data;
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data.reservations)
          ? data.reservations
          : [];
      setOtaReservations(list);
    } catch (error) {
      console.error('Failed to load OTA reservations:', error);
      setOtaReservations([]);
    }
  };

  const loadSyncHistory = async () => {
    try {
      const response = await axios.get('/channel-manager/sync-history?days=7');
      const data = response.data;
      setSyncSummary(data.summary || null);
      const logs = Array.isArray(data.sync_logs) ? data.sync_logs : [];
      setSyncLogs(logs);
    } catch (error) {
      console.error('Failed to load sync history:', error);
      setSyncLogs([]);
      setSyncSummary(null);
    }
  };

  const loadRateParity = async () => {
    try {
      const response = await axios.get('/channel-manager/rate-parity-check');
      setParityInfo(response.data || null);
    } catch (error) {
      console.error('Failed to load rate parity info:', error);
      setParityInfo(null);
    }
  };

  const loadExceptions = async () => {
    try {
      const url = exceptionFilter === 'all' 
        ? '/channel-manager/exceptions'
        : `/channel-manager/exceptions?status=${exceptionFilter}`;
      const response = await axios.get(url);
      const data = response.data;
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data.exceptions)
          ? data.exceptions
          : [];
      setExceptions(list);
    } catch (error) {
      console.error('Failed to load exceptions:', error);
      setExceptions([]);
    }
  };

  const handleCreateRoomMapping = async (mapping) => {
    try {
      await axios.post('/channel-manager/room-mappings', mapping);
      toast.success('Room mapping created');
      loadRoomMappings();
    } catch (error) {
      console.error('Failed to create room mapping:', error);
      toast.error(error.response?.data?.detail || 'Failed to create room mapping');
    }
  };

  const handleDeleteRoomMapping = async (mappingId) => {
    try {
      await axios.delete(`/channel-manager/room-mappings/${mappingId}`);
      toast.success('Room mapping deleted');
      loadRoomMappings();
    } catch (error) {
      console.error('Failed to delete room mapping:', error);
      toast.error(error.response?.data?.detail || 'Failed to delete room mapping');
    }
  };


  const handleAddConnection = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/channel-manager/connections', newConnection);
      toast.success('Channel connection added successfully!');
      setShowAddConnection(false);
      setNewConnection({
        channel_type: 'booking_com',
        channel_name: '',
        property_id: '',
        api_endpoint: '',
        api_key: '',
        api_secret: '',
        sync_rate_availability: true,
        sync_reservations: true
      });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateRates = async () => {
    try {
      if (!rateRoomType || !rateDateFrom || !rateDateTo || !baseRate) {
        toast.error('Lütfen oda tipi, tarih aralığı ve baz fiyatı doldurun');
        return;
      }

      const base = parseFloat(baseRate) || 0;
      const disc = parseFloat(discountPct) || 0;
      const final = base * (1 - (Number.isNaN(disc) ? 0 : disc) / 100);

      const selectedChannels = [];
      if (channelSelection.all) {
        selectedChannels.push('direct', 'booking_com', 'expedia', 'airbnb');
      } else {
        Object.entries(channelSelection).forEach(([key, value]) => {
          if (value && key !== 'all') selectedChannels.push(key);
        });
      }

      if (selectedChannels.length === 0) {
        toast.error('En az bir kanal seçmelisiniz');
        return;
      }

      setLoading(true);
      const payload = {
        room_type: rateRoomType,
        date_from: rateDateFrom,
        date_to: rateDateTo,
        base_rate: base,
        discount_pct: disc,
        new_rate: final,
        channels: selectedChannels,
      };

      const response = await axios.post('/channel-manager/update-rates', payload);
      toast.success(response.data?.message || 'Rates updated successfully');
    } catch (error) {
      console.error('Failed to update rates:', error);
      toast.error(error.response?.data?.detail || 'Failed to update rates');
    } finally {
      setLoading(false);
    }
  };

  const handleImportReservation = async (otaReservationId) => {
    try {
      setLoading(true);
      await axios.post(`/channel-manager/import-reservation/${otaReservationId}`);
      toast.success('Reservation imported successfully');
      loadOtaReservations();
      loadExceptions();
    } catch (error) {
      console.error('Failed to import reservation:', error);
      toast.error(error.response?.data?.detail || 'Failed to import reservation');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      active: { color: 'bg-green-500', label: 'Active' },
      inactive: { color: 'bg-gray-500', label: 'Inactive' },
      error: { color: 'bg-red-500', label: 'Error' },
      pending: { color: 'bg-yellow-500', label: 'Pending' },
      imported: { color: 'bg-blue-500', label: 'Imported' },
      failed: { color: 'bg-red-500', label: 'Failed' }
    };
    
    const config = statusConfig[status] || statusConfig.pending;
    return <Badge className={config.color}>{config.label}</Badge>;
  };

  const channelLogos = {
    booking_com: '🅱️',
    expedia: '🅴',
    airbnb: '🅰️',
    agoda: '🅰️',
    tripadvisor: '🅣'
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="channel-manager">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>
              Channel Manager
            </h1>
            <p className="text-gray-600">Manage OTA connections and reservations</p>
          </div>
          <Dialog open={showAddMapping} onOpenChange={setShowAddMapping}>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Yeni Room Mapping Ekle</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 mt-2">
                      <div>
                        <Label>Channel</Label>
                        <select
                          className="w-full border rounded-md p-2 mt-1"
                          value={newMapping.channel_id}
                          onChange={(e) => setNewMapping({ ...newMapping, channel_id: e.target.value })}
                        >
                          <option value="">Bir bağlantı seçin</option>
                          {connections.map((conn) => (
                            <option key={conn.id} value={conn.id}>
                              {conn.channel_type === 'booking_com' ? 'Booking.com' : conn.channel_name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <Label>PMS Room Type</Label>
                        <select
                          className="w-full border rounded-md p-2 mt-1"
                          value={newMapping.pms_room_type}
                          onChange={(e) => setNewMapping({ ...newMapping, pms_room_type: e.target.value })}
                        >
                          <option value="">Bir oda tipi seçin</option>
                          {pmsRoomTypes.map((rt) => (
                            <option key={rt} value={rt}>{rt}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <Label>Channel Room Type</Label>
                        <Input
                          className="mt-1"
                          value={newMapping.channel_room_type}
                          onChange={(e) => setNewMapping({ ...newMapping, channel_room_type: e.target.value })}
                          placeholder="Booking oda adı"
                        />
                      </div>
                      <div>
                        <Label>Channel Room ID</Label>
                        <Input
                          className="mt-1"
                          value={newMapping.channel_room_id}
                          onChange={(e) => setNewMapping({ ...newMapping, channel_room_id: e.target.value })}
                          placeholder="Booking oda ID"
                        />
                      </div>
                      <div className="flex justify-end gap-2 mt-4">
                        <Button
                          variant="outline"
                          type="button"
                          onClick={() => {
                            setShowAddMapping(false);
                            setNewMapping({
                              channel_id: '',
                              pms_room_type: '',
                              channel_room_type: '',
                              channel_room_id: ''
                            });
                          }}
                        >
                          İptal
                        </Button>
                        <Button
                          type="button"
                          onClick={() => {
                            if (!newMapping.channel_id || !newMapping.pms_room_type) {
                              toast.error('Lütfen kanal ve PMS oda tipini seçin');
                              return;
                            }
                            handleCreateRoomMapping(newMapping);
                            setShowAddMapping(false);
                            setNewMapping({
                              channel_id: '',
                              pms_room_type: '',
                              channel_room_type: '',
                              channel_room_id: ''
                            });
                          }}
                        >
                          Kaydet
                        </Button>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>

          <Dialog open={showAddConnection} onOpenChange={setShowAddConnection}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                Add Connection
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Add Channel Connection</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleAddConnection} className="space-y-4">
                <div>
                  <Label>Channel Type</Label>
                  <select
                    className="w-full border rounded-md p-2"
                    value={newConnection.channel_type}
                    onChange={(e) => setNewConnection({...newConnection, channel_type: e.target.value})}
                  >
                    <option value="booking_com">Booking.com</option>
                    <option value="expedia">Expedia</option>
                    <option value="airbnb">Airbnb</option>
                    <option value="agoda">Agoda</option>
                    <option value="tripadvisor">TripAdvisor</option>
                  </select>
                </div>
                <div>
                  <Label>Channel Name</Label>
                  <Input
                    value={newConnection.channel_name}
                    onChange={(e) => setNewConnection({...newConnection, channel_name: e.target.value})}
                    placeholder="e.g., Grand Hotel Istanbul"
                    required
                  />
                </div>
                <div>
                  <Label>Property ID</Label>
                  <Input
                    value={newConnection.property_id}
                    onChange={(e) => setNewConnection({...newConnection, property_id: e.target.value})}
                    placeholder="Property/Hotel ID from OTA"
                    required
                  />
                </div>
                <div>
                  <Label>API Key</Label>
                  <Input
                    value={newConnection.api_key}
                    onChange={(e) => setNewConnection({...newConnection, api_key: e.target.value})}
                    placeholder="API Key"
                  />
                </div>
                <div>
                  <Label>API Secret</Label>
                  <Input
                    type="password"
                    value={newConnection.api_secret}
                    onChange={(e) => setNewConnection({...newConnection, api_secret: e.target.value})}
                    placeholder="API Secret"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? 'Adding...' : 'Add Connection'}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {/* Tabs section moved below */}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="connections">
              <Network className="w-4 h-4 mr-2" />
              Connections
            </TabsTrigger>
            <TabsTrigger value="mappings">
              <Network className="w-4 h-4 mr-2" />
              Room Mappings
            </TabsTrigger>
            <TabsTrigger value="rates">
              <Settings className="w-4 h-4 mr-2" />
              Rate & Availability
            </TabsTrigger>
            <TabsTrigger value="reservations">
              <Download className="w-4 h-4 mr-2" />
              OTA Reservations
            </TabsTrigger>
            <TabsTrigger value="exceptions">
              <AlertTriangle className="w-4 h-4 mr-2" />
              Exceptions
            </TabsTrigger>
          </TabsList>

          {/* Connections Tab */}
          <TabsContent value="connections" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Active Connections</CardTitle>
                <CardDescription>
                  Manage your OTA channel connections and credentials
                </CardDescription>
              </CardHeader>
              <CardContent>
                {connections.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <Network className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>No channel connections yet</p>
                    <p className="text-sm">Add your first connection to start receiving OTA reservations</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {connections.map((conn) => (
                      <div key={conn.id} className="border rounded-lg p-4 flex items-center justify-between">
                        <div className="flex items-center space-x-4">
              {/* Parity Alert */}
              {parityInfo && (
                <div className="mt-4">
                  <Card className={parityInfo.parity_status === 'good' ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50'}>
                    <CardHeader className="py-2 flex items-center justify-between">
                      <div>
                        <CardTitle className="text-sm flex items-center gap-2">
                          {parityInfo.parity_status === 'good' ? (
                            <span className="inline-flex items-center text-green-700">
                              <span className="w-2 h-2 rounded-full bg-green-500 mr-1" />
                              Rate Parity İyi
                            </span>
                          ) : (
                            <span className="inline-flex items-center text-amber-700">
                              <span className="w-2 h-2 rounded-full bg-amber-500 mr-1" />
                              Rate Parity Sorunları
                            </span>
                          )}
                        </CardTitle>
                        <CardDescription className="text-xs mt-1">
                          {parityInfo.recommendation}
                        </CardDescription>
                      </div>
                      <Button
                        variant="outline"
                        size="xs"
                        onClick={loadRateParity}
                        disabled={loading}
                      >
                        <RefreshCw className="w-3 h-3 mr-1" /> Yenile
                      </Button>
                    </CardHeader>
                    {parityInfo.issues && parityInfo.issues.length > 0 && (
                      <CardContent className="pt-0 pb-3">
                        <ul className="text-xs list-disc list-inside space-y-1">
                          {parityInfo.issues.slice(0, 3).map((issue, idx) => (
                            <li key={idx}>
                              {issue.message || `${issue.channel}: ${issue.difference_pct}% fark`}
                            </li>
                          ))}
                          {parityInfo.issues.length > 3 && (
                            <li className="text-[11px] text-gray-600">
                              +{parityInfo.issues.length - 3} daha fazla parity issue...
                            </li>
                          )}
                        </ul>
                      </CardContent>
                    )}
                  </Card>
                </div>
              )}

                          <div className="text-4xl">
                            {channelLogos[conn.channel_type] || '🌐'}
                          </div>
                          <div>
                            <h3 className="font-semibold text-lg">{conn.channel_name}</h3>
                            <p className="text-sm text-gray-600">
                              Property ID: {conn.property_id}
                            </p>
                            <p className="text-sm text-gray-600">
                              Type: {conn.channel_type.replace('_', '.')}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center space-x-4">
                          {getStatusBadge(conn.status)}
                          <Button variant="outline" size="sm">
                            <Settings className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Room Mappings Tab */}
          <TabsContent value="mappings" className="mt-4">
            <Card>
              <CardHeader className="flex items-center justify-between">
                <div>
                  <CardTitle>Room & Rate Mappings</CardTitle>
                  <CardDescription>
                    PMS varlıklarınızı provider varlıkları ile eşleştirin. Detaylı mapping yönetimi için aşağıdaki butonu kullanın.
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="text-center py-8">
                <div className="flex flex-col items-center gap-4">
                  <Network className="w-12 h-12 text-blue-500" />
                  <p className="text-gray-600 text-sm max-w-md">
                    Mapping yönetimi artık geliştirilmiş arayüzde mevcut. Oda tipi, fiyat planı ve diğer tüm eşlemeleri
                    readiness skoru ve doğrulama kontrolleri ile yönetebilirsiniz.
                  </p>
                  <Button
                    className="bg-blue-600 hover:bg-blue-700 text-white"
                    onClick={() => window.location.href = '/mapping-manager'}
                    data-testid="go-to-mapping-manager"
                  >
                    <Settings className="w-4 h-4 mr-2" />
                    Mapping Yönetimine Git
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>



          {/* Rate & Availability Tab */}
          <TabsContent value="rates" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Fiyat & Müsaitlik Yönetimi</CardTitle>
                <CardDescription>
                  Tüm oda tiplerini aynı anda görüntüleyin ve toplu güncelleme yapın
                </CardDescription>
              </CardHeader>
              <CardContent className="text-center py-8">
                <div className="flex flex-col items-center gap-4">
                  <Settings className="w-12 h-12 text-orange-500" />
                  <p className="text-gray-600 text-sm max-w-md">
                    Fiyat ve müsaitlik yönetimi artık "Toplu Güncellemeler" sayfasına taşındı.
                    Tüm oda tiplerini aynı anda görebilir ve tek seferde güncelleyebilirsiniz.
                  </p>
                  <Button
                    className="bg-orange-600 hover:bg-orange-700 text-white"
                    onClick={() => window.location.href = '/rate-manager'}
                    data-testid="go-to-rate-manager"
                  >
                    <Settings className="w-4 h-4 mr-2" />
                    Toplu Güncellemeler Sayfasına Git
                  </Button>
                </div>
              </CardContent>
            </Card>

          {/* Sync History Block (below Rate & Availability) */}
          <Card className="border-gray-200">
            <CardHeader className="pb-3 flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Channel Sync History (Last 7 Days)</CardTitle>
                <CardDescription>
                  Son 7 gündeki kanal senkronizasyon özetini görüntüleyin.
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={loadSyncHistory}
                disabled={loading}
              >
                <RefreshCw className="w-4 h-4 mr-2" /> Yenile
              </Button>
            </CardHeader>
            <CardContent>
              {syncSummary && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
                  <div className="p-3 rounded bg-gray-50">
                    <div className="text-xs text-gray-500">Toplam Senkronizasyon</div>
                    <div className="text-lg font-semibold">{syncSummary.total_syncs}</div>
                  </div>
                  <div className="p-3 rounded bg-green-50">
                    <div className="text-xs text-green-700">Başarılı</div>
                    <div className="text-lg font-semibold text-green-800">{syncSummary.successful}</div>
                  </div>
                  <div className="p-3 rounded bg-red-50">
                    <div className="text-xs text-red-700">Hatalı</div>
                    <div className="text-lg font-semibold text-red-800">{syncSummary.failed}</div>
                  </div>
                  <div className="p-3 rounded bg-blue-50">
                    <div className="text-xs text-blue-700">Başarı Oranı</div>
                    <div className="text-lg font-semibold text-blue-800">{syncSummary.success_rate}%</div>
                  </div>
                </div>
              )}

              {syncLogs.length === 0 ? (
                <div className="text-center py-4 text-gray-500 text-sm">
                  Son 7 günde herhangi bir sync log kaydı bulunamadı.
                </div>
              ) : (
                <div className="max-h-64 overflow-y-auto border rounded">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left p-2">Zaman</th>
                        <th className="text-left p-2">Kanal</th>
                        <th className="text-left p-2">Tür</th>
                        <th className="text-left p-2">Durum</th>
                        <th className="text-left p-2">Kayıt</th>
                        <th className="text-left p-2">Süre (ms)</th>
                        <th className="text-left p-2">Kaynak</th>
                        <th className="text-left p-2">IP</th>
                        <th className="text-left p-2">Hata</th>
                      </tr>
                    </thead>
                    <tbody>
                      {syncLogs.map((log, idx) => (
                        <tr key={idx} className="border-t hover:bg-gray-50">
                          <td className="p-2 whitespace-nowrap text-[11px]">{log.timestamp}</td>
                          <td className="p-2">{getChannelLabel(log.channel)}</td>
                          <td className="p-2">{log.sync_type}</td>
                          <td className="p-2">
                            <span
                              className={
                                log.status === 'success'
                                  ? 'text-green-700'
                                  : 'text-red-700'
                              }
                            >
                              {log.status}
                            </span>
                          </td>
                          <td className="p-2">{log.records_synced ?? '-'}</td>
                          <td className="p-2">{log.duration_ms ?? '-'}</td>
                          <td className="p-2 text-[11px]">
                            {log.initiator_name
                              ? `${log.initiator_type || 'user'}: ${log.initiator_name}`
                              : log.initiator_type || '-'}
                          </td>
                          <td className="p-2 text-[11px]">{log.ip_address || '-'}</td>
                          <td className="p-2 max-w-xs truncate" title={log.error_message || ''}>
                            {log.error_message || '-'}
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

          {/* OTA Reservations Tab */}
          <TabsContent value="reservations" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex justify-between items-center">
                  <div>
                    <CardTitle>OTA Reservations</CardTitle>
                    <CardDescription>
                      Import reservations from connected channels
                    </CardDescription>
                  </div>
                  <div className="flex space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => window.location.href = '/reservation-lineage'}
                      data-testid="go-to-lineage"
                    >
                      Lineage & Geçmiş
                    </Button>
                    <Button
                      variant={reservationFilter === 'pending' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setReservationFilter('pending');
                        setTimeout(() => loadOtaReservations(), 100);
                      }}
                    >
                      Pending
                    </Button>
                    <Button
                      variant={reservationFilter === 'imported' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setReservationFilter('imported');
                        setTimeout(() => loadOtaReservations(), 100);
                      }}
                    >
                      Imported
                    </Button>
                    <Button
                      variant={reservationFilter === 'failed' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setReservationFilter('failed');
                        setTimeout(() => loadOtaReservations(), 100);
                      }}
                    >
                      Failed
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {otaReservations.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <Download className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>No {reservationFilter} reservations</p>
                    <p className="text-sm">OTA reservations will appear here automatically</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {otaReservations.map((reservation) => (
                      <div key={reservation.id} className="border rounded-lg p-4">
                        <div className="flex justify-between items-start">
                          <div className="space-y-2">
                            <div className="flex items-center space-x-2">
                              <h3 className="font-semibold">{reservation.guest_name}</h3>
                              {getStatusBadge(reservation.status)}
                            </div>
                            <div className="text-sm text-gray-600 space-y-1">
                              <p>📧 {reservation.guest_email}</p>
                              <p>📞 {reservation.guest_phone}</p>
                              <p>🏨 Room: {reservation.room_type}</p>
                              <p>📅 {reservation.check_in} → {reservation.check_out}</p>
                              <p>💰 ${reservation.total_amount}</p>
                              <p className="text-xs text-gray-500">
                                Channel: {reservation.channel_type} | OTA ID: {reservation.ota_booking_id}
                              </p>
                            </div>
                          </div>
                          <div className="space-y-2">
                            {reservation.status === 'pending' && (
                              <Button
                                size="sm"
                                onClick={() => handleImportReservation(reservation.id)}
                                disabled={loading}
                              >
                                <Download className="w-4 h-4 mr-2" />
                                Import
                              </Button>
                            )}
                            {reservation.status === 'imported' && (
                              <div className="flex items-center text-green-600 text-sm">
                                <CheckCircle className="w-4 h-4 mr-1" />
                                Imported
                              </div>
                            )}
                            {reservation.status === 'failed' && (
                              <div className="flex items-center text-red-600 text-sm">
                                <XCircle className="w-4 h-4 mr-1" />
                                Failed
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Exceptions Tab */}
          <TabsContent value="exceptions" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex justify-between items-center">
                  <div>
                    <CardTitle>Exception Queue</CardTitle>
                    <CardDescription>
                      Review and resolve channel integration issues
                    </CardDescription>
                  </div>
                  <div className="flex space-x-2">
                    <Button
                      variant={exceptionFilter === 'all' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setExceptionFilter('all');
                        setTimeout(() => loadExceptions(), 100);
                      }}
                    >
                      All
                    </Button>
                    <Button
                      variant={exceptionFilter === 'pending' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setExceptionFilter('pending');
                        setTimeout(() => loadExceptions(), 100);
                      }}
                    >
                      Pending
                    </Button>
                    <Button
                      variant={exceptionFilter === 'resolved' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => {
                        setExceptionFilter('resolved');
                        setTimeout(() => loadExceptions(), 100);
                      }}
                    >
                      Resolved
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {exceptions.length === 0 ? (
                  <div className="text-center py-8 text-green-600">
                    <CheckCircle className="w-12 h-12 mx-auto mb-4" />
                    <p className="font-semibold">No Exceptions!</p>
                    <p className="text-sm">All channel operations are running smoothly</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {exceptions.map((exception) => (
                      <div key={exception.id} className="border border-red-200 rounded-lg p-4 bg-red-50">
                        <div className="flex justify-between items-start">
                          <div className="space-y-2">
                            <div className="flex items-center space-x-2">
                              <AlertTriangle className="w-5 h-5 text-red-600" />
                              <h3 className="font-semibold text-red-900">
                                {exception.exception_type.replace(/_/g, ' ').toUpperCase()}
                              </h3>
                              {getStatusBadge(exception.status)}
                            </div>
                            <p className="text-sm text-red-800">{exception.error_message}</p>
                            <div className="text-xs text-red-600 space-y-1">
                              <p>Channel: {exception.channel_type}</p>
                              <p>Time: {new Date(exception.created_at).toLocaleString()}</p>
                              {exception.ota_booking_id && (
                                <p>OTA Booking: {exception.ota_booking_id}</p>
                              )}
                            </div>
                          </div>
                          <div className="space-y-2">
                            {exception.status === 'pending' && (
                              <Button size="sm" variant="outline">
                                <RefreshCw className="w-4 h-4 mr-2" />
                                Retry
                              </Button>
                            )}
                          </div>
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

export default ChannelManagerModule;
