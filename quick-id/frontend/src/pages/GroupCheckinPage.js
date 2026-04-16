import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Checkbox } from '../components/ui/checkbox';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { api } from '../lib/api';
import {
  UsersRound, RefreshCw, CheckCircle2, XCircle, Search, DoorOpen,
} from 'lucide-react';

export default function GroupCheckinPage() {
  const [guests, setGuests] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [selectedGuests, setSelectedGuests] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [guestsRes, roomsRes] = await Promise.allSettled([
        api.getGuests({ status: 'pending', limit: 100 }),
        api.getRooms({ status: 'available' }),
      ]);
      if (guestsRes.status === 'fulfilled') setGuests(guestsRes.value.guests || []);
      if (roomsRes.status === 'fulfilled') setRooms(roomsRes.value.rooms || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleGuest = (guestId) => {
    setSelectedGuests(prev =>
      prev.includes(guestId) ? prev.filter(id => id !== guestId) : [...prev, guestId]
    );
  };

  const handleGroupCheckin = async () => {
    if (selectedGuests.length === 0) return;
    setProcessing(true);
    setResult(null);
    try {
      const payload = {
        guest_ids: selectedGuests,
        ...(selectedRoom ? { room_id: selectedRoom } : {}),
      };
      const data = await api.groupCheckin(payload);
      setResult(data);
      setSelectedGuests([]);
      fetchData();
    } catch (e) {
      setResult({ success: false, error: e.message || 'Hata oluştu' });
    }
    setProcessing(false);
  };

  const selectAll = () => {
    const filtered = filteredGuests.map(g => g.id);
    setSelectedGuests(prev => {
      const allSelected = filtered.every(id => prev.includes(id));
      if (allSelected) return prev.filter(id => !filtered.includes(id));
      return [...new Set([...prev, ...filtered])];
    });
  };

  const filteredGuests = guests.filter(g => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (g.first_name || '').toLowerCase().includes(q) ||
           (g.last_name || '').toLowerCase().includes(q) ||
           (g.id_number || '').includes(q);
  });

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[60vh]">
        <RefreshCw className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <UsersRound className="w-7 h-7 text-blue-500" /> Grup Check-in
          </h1>
          <p className="text-muted-foreground mt-1">Birden fazla misafiri tek işlemde kayıt edin</p>
        </div>
        <Button variant="outline" onClick={fetchData}><RefreshCw className="w-4 h-4 mr-2" />Yenile</Button>
      </div>

      {/* Selection Panel */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Bekleyen Misafirler ({filteredGuests.length})</span>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input className="pl-9 w-64" placeholder="Misafir ara..." value={search} onChange={e => setSearch(e.target.value)} />
              </div>
              <Button variant="outline" size="sm" onClick={selectAll}>
                {filteredGuests.every(g => selectedGuests.includes(g.id)) ? 'Seçimi Kaldır' : 'Tümünü Seç'}
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {filteredGuests.length > 0 ? (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {filteredGuests.map(guest => (
                <div
                  key={guest.id}
                  className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                    selectedGuests.includes(guest.id) ? 'bg-blue-50 border-blue-200' : 'hover:bg-gray-50'
                  }`}
                  onClick={() => toggleGuest(guest.id)}
                >
                  <Checkbox checked={selectedGuests.includes(guest.id)} onCheckedChange={() => toggleGuest(guest.id)} />
                  <div className="flex-1">
                    <p className="font-medium">{guest.first_name} {guest.last_name}</p>
                    <p className="text-sm text-muted-foreground">
                      {guest.id_number || 'Kimlik No yok'} • {guest.nationality || '-'} • {guest.document_type || '-'}
                    </p>
                  </div>
                  <Badge variant="outline">Bekliyor</Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <UsersRound className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>Bekleyen misafir bulunmuyor</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Action Panel */}
      {selectedGuests.length > 0 && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">{selectedGuests.length} misafir seçildi</p>
                <p className="text-sm text-muted-foreground">Toplu check-in ve opsiyonel oda atama</p>
              </div>
              <div className="flex items-center gap-3">
                <div>
                  <Label className="text-xs">Oda Atama (opsiyonel)</Label>
                  <select className="border rounded-md p-2 text-sm w-48" value={selectedRoom} onChange={e => setSelectedRoom(e.target.value)}>
                    <option value="">Oda atama yapma</option>
                    {rooms.map(r => (
                      <option key={r.room_id} value={r.room_id}>Oda {r.room_number} ({r.room_type})</option>
                    ))}
                  </select>
                </div>
                <Button onClick={handleGroupCheckin} disabled={processing} className="h-10">
                  {processing ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
                  Grup Check-in ({selectedGuests.length})
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {result && (
        <Card className={result.success ? 'border-green-200' : 'border-red-200'}>
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-3">
              {result.success ? (
                <CheckCircle2 className="w-6 h-6 text-green-500" />
              ) : (
                <XCircle className="w-6 h-6 text-red-500" />
              )}
              <div>
                <p className="font-medium">{result.success ? 'Check-in Başarılı!' : 'Hata Oluştu'}</p>
                <p className="text-sm text-muted-foreground">
                  {result.successful_count || 0} başarılı, {result.failed_count || 0} başarısız
                </p>
              </div>
            </div>

            {result.results?.room_assignment && (
              <div className={`mt-2 p-3 rounded-lg ${result.results.room_assignment.success ? 'bg-green-50' : 'bg-amber-50'}`}>
                <div className="flex items-center gap-2">
                  <DoorOpen className="w-4 h-4" />
                  <span className="text-sm">
                    {result.results.room_assignment.success
                      ? `Oda ${result.results.room_assignment.room?.room_number} atandı`
                      : `Oda atama hatası: ${result.results.room_assignment.error}`}
                  </span>
                </div>
              </div>
            )}

            {result.results?.failed?.length > 0 && (
              <div className="mt-3 space-y-1">
                {result.results.failed.map((f, i) => (
                  <div key={i} className="text-sm text-red-600">
                    <XCircle className="w-3 h-3 inline mr-1" /> {f.guest_id}: {f.error}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
