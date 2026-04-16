import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Monitor, Wifi, WifiOff, Loader2, Play, RefreshCw, Upload, Clock, Database, AlertTriangle } from 'lucide-react';

export default function KioskPage() {
  const [tab, setTab] = useState('kiosk');
  
  // Kiosk state
  const [sessions, setSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [properties, setProperties] = useState([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [kioskName, setKioskName] = useState('Lobby Kiosk');
  const [creatingSes, setCreatingSes] = useState(false);
  
  // Offline sync state
  const [pendingSyncs, setPendingSyncs] = useState([]);
  const [loadingSyncs, setLoadingSyncs] = useState(false);
  const [processing, setProcessing] = useState(null);

  useEffect(() => {
    loadProperties();
    loadSessions();
  }, []);

  useEffect(() => {
    if (tab === 'offline') loadPendingSyncs();
  }, [tab]);

  const loadProperties = async () => {
    try {
      const res = await api.getProperties();
      setProperties(res.properties || []);
    } catch (err) { console.error(err); }
  };

  const loadSessions = async () => {
    setLoadingSessions(true);
    try {
      const res = await api.getKioskSessions();
      setSessions(res.sessions || []);
    } catch (err) { console.error(err); }
    finally { setLoadingSessions(false); }
  };

  const createSession = async () => {
    if (!selectedProperty) return;
    setCreatingSes(true);
    try {
      await api.createKioskSession({ property_id: selectedProperty, kiosk_name: kioskName });
      loadSessions();
      setKioskName('Lobby Kiosk');
    } catch (err) { alert(err.message); }
    finally { setCreatingSes(false); }
  };

  const loadPendingSyncs = async () => {
    setLoadingSyncs(true);
    try {
      const res = await api.getPendingSyncs();
      setPendingSyncs(res.syncs || []);
    } catch (err) { console.error(err); }
    finally { setLoadingSyncs(false); }
  };

  const processSync = async (syncId) => {
    setProcessing(syncId);
    try {
      const res = await api.processSync(syncId);
      if (res.success) {
        loadPendingSyncs();
      }
    } catch (err) { alert(err.message); }
    finally { setProcessing(null); }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Kiosk & Offline</h1>
        <p className="text-gray-500 mt-1">Self-servis kiosk yönetimi ve çevrimdışı senkronizasyon</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-2 w-full max-w-md">
          <TabsTrigger value="kiosk"><Monitor className="w-4 h-4 mr-2" />Kiosk Modu</TabsTrigger>
          <TabsTrigger value="offline"><WifiOff className="w-4 h-4 mr-2" />Offline Sync</TabsTrigger>
        </TabsList>

        {/* Kiosk Tab */}
        <TabsContent value="kiosk" className="space-y-4">
          {/* Create Session */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Monitor className="w-5 h-5 text-blue-500" />
                Kiosk Oturumu Başlat
              </CardTitle>
              <CardDescription>Lobby self-servis terminali için yeni kiosk oturumu oluşturun</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="text-sm font-medium mb-1 block">Tesis</label>
                  <select className="w-full border rounded-md p-2 text-sm" value={selectedProperty} onChange={(e) => setSelectedProperty(e.target.value)}>
                    <option value="">Tesis Seçin</option>
                    {properties.map(p => (
                      <option key={p.property_id || p.id} value={p.property_id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium mb-1 block">Kiosk Adı</label>
                  <input className="w-full border rounded-md p-2 text-sm" value={kioskName} onChange={(e) => setKioskName(e.target.value)} />
                </div>
                <div className="flex items-end">
                  <Button onClick={createSession} disabled={creatingSes || !selectedProperty} className="w-full">
                    {creatingSes ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                    Oturum Başlat
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Active Sessions */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Kiosk Oturumları</CardTitle>
                <CardDescription>Aktif ve geçmiş oturumlar</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={loadSessions}><RefreshCw className="w-4 h-4" /></Button>
            </CardHeader>
            <CardContent>
              {loadingSessions ? (
                <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
              ) : sessions.length === 0 ? (
                <p className="text-center text-gray-500 py-8">Henüz kiosk oturumu yok</p>
              ) : (
                <div className="space-y-2">
                  {sessions.map((session) => (
                    <div key={session.session_id || session.id} className="p-3 border rounded-lg flex items-center justify-between hover:bg-gray-50">
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${session.status === 'active' ? 'bg-green-50' : 'bg-gray-50'}`}>
                          <Monitor className={`w-5 h-5 ${session.status === 'active' ? 'text-green-500' : 'text-gray-400'}`} />
                        </div>
                        <div>
                          <p className="font-medium">{session.kiosk_name}</p>
                          <div className="flex gap-3 text-xs text-gray-500">
                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(session.last_activity || session.started_at).toLocaleString('tr-TR')}</span>
                            <span>Tarama: {session.scan_count || 0}</span>
                            <span>Misafir: {session.guest_count || 0}</span>
                          </div>
                        </div>
                      </div>
                      <Badge variant={session.status === 'active' ? 'default' : 'secondary'}>
                        {session.status === 'active' ? 'Aktif' : session.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Kiosk Info */}
          <Card>
            <CardContent className="pt-4">
              <div className="bg-blue-50 rounded-lg p-4 space-y-2">
                <h4 className="font-semibold text-blue-800">Kiosk Modu Hakkında</h4>
                <ul className="text-sm text-blue-600 space-y-1">
                  <li>• Lobby'de self-servis kimlik tarama terminali</li>
                  <li>• Misafirler kendi kimliklerini tarayabilir</li>
                  <li>• Otomatik check-in işlemi</li>
                  <li>• Her oturumda tarama ve misafir sayıları takip edilir</li>
                  <li>• Session bazlı izleme ve raporlama</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Offline Sync Tab */}
        <TabsContent value="offline" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <WifiOff className="w-5 h-5 text-orange-500" />
                Çevrimdışı Senkronizasyon
              </CardTitle>
              <CardDescription>
                İnternet kesintisinde yerel olarak toplanan veriler burada senkronize edilir.
                Offline modda biriktirilen taramalar ve misafir kayıtları merkezi veritabanına aktarılır.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={loadPendingSyncs} className="mb-4">
                <RefreshCw className="w-4 h-4 mr-2" />Yenile
              </Button>

              {loadingSyncs ? (
                <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
              ) : pendingSyncs.length === 0 ? (
                <div className="text-center py-8">
                  <Wifi className="w-12 h-12 text-green-300 mx-auto mb-4" />
                  <p className="text-gray-500 font-medium">Bekleyen senkronizasyon yok</p>
                  <p className="text-sm text-gray-400">Tüm veriler güncel</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {pendingSyncs.map((sync) => (
                    <div key={sync.sync_id || sync.id} className="p-4 border rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Database className="w-5 h-5 text-orange-500" />
                          <div>
                            <p className="font-medium capitalize">{sync.data_type} Verileri</p>
                            <p className="text-xs text-gray-500">
                              {sync.record_count} kayıt • {new Date(sync.created_at).toLocaleString('tr-TR')}
                              {sync.device_id && ` • Cihaz: ${sync.device_id}`}
                            </p>
                          </div>
                        </div>
                        <Badge variant={sync.status === 'pending' ? 'outline' : sync.status === 'processed' ? 'default' : 'destructive'}>
                          {sync.status === 'pending' ? 'Bekliyor' : sync.status === 'processed' ? 'İşlendi' : sync.status}
                        </Badge>
                      </div>
                      {sync.status === 'pending' && (
                        <Button size="sm" onClick={() => processSync(sync.sync_id)} disabled={processing === sync.sync_id}>
                          {processing === sync.sync_id ? (
                            <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                          ) : (
                            <Upload className="w-3 h-3 mr-1" />
                          )}
                          Senkronize Et
                        </Button>
                      )}
                      {sync.errors && sync.errors.length > 0 && (
                        <div className="mt-2 text-sm text-red-600">
                          <AlertTriangle className="w-3 h-3 inline mr-1" />
                          {sync.errors.length} hata: {sync.errors[0]}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Offline Info */}
          <Card>
            <CardContent className="pt-4">
              <div className="bg-orange-50 rounded-lg p-4 space-y-2">
                <h4 className="font-semibold text-orange-800">Offline Mod Nasıl Çalışır?</h4>
                <ul className="text-sm text-orange-600 space-y-1">
                  <li>• İnternet kesildiğinde taramalar yerel olarak saklanır</li>
                  <li>• Bağlantı geldiğinde veriler otomatik yüklenebilir</li>
                  <li>• Her cihaz benzersiz ID ile takip edilir</li>
                  <li>• Çakışma yönetimi: Aynı misafir çift kaydı engellenir</li>
                  <li>• PWA desteği ile tarayıcı kapatılsa bile çalışır</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
